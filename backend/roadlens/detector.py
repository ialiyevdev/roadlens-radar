"""OpenCV Zoo YOLOX-S INT8 inference, restricted to COCO vehicle classes."""

from dataclasses import dataclass
from pathlib import Path

import cv2
import numpy as np


VEHICLE_CLASSES = {2: "car", 3: "motorcycle", 5: "bus", 7: "truck"}


@dataclass(frozen=True, slots=True)
class Detection:
    bbox: tuple[float, float, float, float]
    confidence: float
    category: str


def letterbox(frame: np.ndarray, size: int = 640) -> tuple[np.ndarray, float]:
    if frame.ndim != 3 or frame.shape[2] != 3 or not frame.size:
        raise ValueError("Expected a nonempty BGR image with three channels.")
    height, width = frame.shape[:2]
    scale = min(size / width, size / height)
    resized = cv2.resize(frame, (max(1, int(width * scale)), max(1, int(height * scale))))
    canvas = np.full((size, size, 3), 114, dtype=np.uint8)
    canvas[:resized.shape[0], :resized.shape[1]] = resized
    # This Zoo export follows its RGB demo, unlike some upstream YOLOX exports.
    blob = cv2.dnn.blobFromImage(canvas, swapRB=True, ddepth=cv2.CV_32F)
    return blob, scale


class RoadLensDetector:
    name = "YOLOX-S · INT8"

    def __init__(self, weights: Path, confidence: float = 0.35, input_size: int = 640):
        if not 0.05 <= confidence <= 0.95:
            raise ValueError("Confidence must be between 0.05 and 0.95.")
        if input_size not in (320, 416, 640):
            raise ValueError("Supported OpenCV inference sizes are 320, 416 and 640.")
        if not Path(weights).is_file():
            raise FileNotFoundError("Model weights missing. Run: python scripts/download_model.py")
        self.input_size = input_size
        self.confidence = confidence
        self.net = cv2.dnn.readNetFromONNX(str(weights))
        self.net.setPreferableBackend(cv2.dnn.DNN_BACKEND_OPENCV)
        self.net.setPreferableTarget(cv2.dnn.DNN_TARGET_CPU)
        grids, strides = [], []
        for stride in (8, 16, 32):
            axis = np.arange(input_size // stride)
            x, y = np.meshgrid(axis, axis)
            grid = np.stack((x, y), axis=-1).reshape(-1, 2)
            grids.append(grid)
            strides.append(np.full((len(grid), 1), stride))
        self.grids = np.concatenate(grids).astype(np.float32)
        self.strides = np.concatenate(strides).astype(np.float32)

    def detect(self, frame: np.ndarray) -> list[Detection]:
        blob, scale = letterbox(frame, self.input_size)
        self.net.setInput(blob)
        output = self.net.forward()
        return self.decode(output, scale, frame.shape[1], frame.shape[0])

    def decode(self, output: np.ndarray, scale: float, width: int, height: int) -> list[Detection]:
        predictions = np.asarray(output).reshape(-1, 85)
        if predictions.shape[0] != len(self.grids):
            raise ValueError("Unsupported model output. Download the documented OpenCV Zoo export.")
        classes = np.argmax(predictions[:, 5:], axis=1)
        scores = predictions[:, 4] * predictions[np.arange(len(predictions)), classes + 5]
        mask = np.isin(classes, list(VEHICLE_CLASSES)) & (scores >= self.confidence)
        mask &= np.isfinite(predictions).all(axis=1)
        if not mask.any():
            return []
        rows = predictions[mask]
        centers = (rows[:, :2] + self.grids[mask]) * self.strides[mask] / scale
        sizes = np.exp(np.clip(rows[:, 2:4], -15, 15)) * self.strides[mask] / scale
        xywh = np.concatenate((centers - sizes / 2, sizes), axis=1)
        scores, classes = scores[mask], classes[mask]
        detections = []
        for class_id, category in VEHICLE_CLASSES.items():
            indices = np.flatnonzero(classes == class_id)
            if not len(indices):
                continue
            keep = cv2.dnn.NMSBoxes(xywh[indices].tolist(), scores[indices].tolist(), self.confidence, 0.5)
            for local_index in np.asarray(keep).reshape(-1):
                index = indices[local_index]
                x, y, box_width, box_height = xywh[index]
                bbox = (
                    float(np.clip(x, 0, width)), float(np.clip(y, 0, height)),
                    float(np.clip(x + box_width, 0, width)), float(np.clip(y + box_height, 0, height)),
                )
                if bbox[2] > bbox[0] and bbox[3] > bbox[1]:
                    detections.append(Detection(bbox, float(scores[index]), category))
        return detections
