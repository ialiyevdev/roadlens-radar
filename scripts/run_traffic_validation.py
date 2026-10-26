"""Explicit synthetic browser harness; the normal backend always uses YOLOX.

Generated colored rectangles have known scripted labels. This exercises video
PTS, the actual tracker, traffic engine, UI and exports without field evidence.
"""

import argparse
import hashlib
import json
import time
from pathlib import Path

import cv2
import numpy as np
import uvicorn

from roadlens.annotation_models import AnnotationDocument
from roadlens.api import create_app
from roadlens.capture import SourceError, VideoSource
from roadlens.detector import Detection
from roadlens.session import SessionManager


ROOT = Path(__file__).resolve().parents[1]
DIRECTORY = ROOT / "data" / "traffic_validation"
VIDEO = DIRECTORY / "SYNTHETIC_traffic_workflow.avi"
FRAME_COUNT = 130
FPS = 20
COLORS = {"car": (240, 200, 40), "truck": (40, 160, 240)}


def objects(index):
    displacement = max(0, index - 60) * 6
    return [("manual-car", "car", [100 + displacement - 25, 300, 100 + displacement + 25, 350]),
            ("manual-truck", "truck", [540 - displacement - 30, 160, 540 - displacement + 30, 220])]


def prepare_fixture(field_session_id="00000000-0000-4000-8000-000000000005"):
    DIRECTORY.mkdir(parents=True, exist_ok=True)
    if not VIDEO.exists():
        writer = cv2.VideoWriter(str(VIDEO), cv2.VideoWriter_fourcc(*"FFV1"), FPS, (640, 480))
        if not writer.isOpened():
            raise RuntimeError("The synthetic harness requires the FFV1 encoder.")
        try:
            for index in range(FRAME_COUNT):
                image = np.full((480, 640, 3), (26, 31, 29), np.uint8)
                cv2.putText(image, "SYNTHETIC TRAFFIC WORKFLOW", (20, 30), cv2.FONT_HERSHEY_SIMPLEX, .65, (210, 225, 210), 1, cv2.LINE_AA)
                cv2.putText(image, "Scripted markers; no road or ML accuracy evidence", (20, 53), cv2.FONT_HERSHEY_SIMPLEX, .42, (160, 175, 160), 1, cv2.LINE_AA)
                cv2.line(image, (0, 260), (639, 260), (55, 65, 58), 2)
                for _, category, bbox in objects(index):
                    x1, y1, x2, y2 = bbox
                    cv2.rectangle(image, (x1, y1), (x2 - 1, y2 - 1), COLORS[category], -1)
                cv2.putText(image, f"Frame {index+1}/{FRAME_COUNT}  source {index/FPS:.2f} s", (20, 455), cv2.FONT_HERSHEY_SIMPLEX, .5, (180, 195, 180), 1, cv2.LINE_AA)
                writer.write(image)
        finally:
            writer.release()
    digest = hashlib.sha256(VIDEO.read_bytes()).hexdigest()
    annotations = AnnotationDocument(field_session_id=field_session_id, source_id="video:" + digest,
        geometry={"width": 640, "height": 480}, provenance="synthetic", frames=[
            {"index": index+1, "timestamp_s": index/FPS, "reviewed": True,
             "objects": [{"identity": identity, "category": category, "bbox": bbox,
                          "entry": index == 0, "exit": index == FRAME_COUNT-1}
                         for identity, category, bbox in objects(index)]}
            for index in range(FRAME_COUNT)])
    (DIRECTORY / "scripted_annotations.json").write_text(annotations.model_dump_json(indent=2), encoding="utf-8")
    return "video:" + digest


class MarkerDetector:
    def __init__(self, *args, **kwargs):
        pass

    def detect(self, image):
        detections = []
        for category, color in COLORS.items():
            center = np.asarray(color, dtype=np.int16)
            mask = cv2.inRange(image, np.maximum(0, center-5).astype(np.uint8), np.minimum(255, center+5).astype(np.uint8))
            points = cv2.findNonZero(mask)
            if points is not None:
                x, y, width, height = cv2.boundingRect(points)
                detections.append(Detection((x, y, x+width, y+height), .99, category))
        return detections


class PacedVideo(VideoSource):
    def read(self):
        time.sleep(.03)
        return super().read()


class TrafficValidationManager(SessionManager):
    traffic_provenance = "synthetic"

    def __init__(self):
        expected = prepare_fixture()
        def source(request, path, label):
            if request.source_type != "video":
                raise SourceError("This synthetic harness accepts its generated video only.")
            return PacedVideo(path, label)
        super().__init__(detector_factory=MarkerDetector, source_factory=source,
            upload_dir=DIRECTORY / "uploads", calibration_dir=DIRECTORY / "calibrations")
        self.expected_source_id = expected

    def register_video(self, path, label, source_id=None):
        if source_id != self.expected_source_id:
            raise SourceError("Select SYNTHETIC_traffic_workflow.avi; use the normal backend for actual YOLOX inference.")
        return super().register_video(path, label, source_id)

    def model_status(self):
        return {"ready": True, "name": "SYNTHETIC traffic markers", "path": "Explicit test adapter, no ML inference", "input_size": 640}

    def cameras(self):
        return []


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--port", type=int, default=8000)
    parser.add_argument("--prepare-only", action="store_true")
    parser.add_argument("--field-session-id", default="00000000-0000-4000-8000-000000000005")
    arguments = parser.parse_args()
    identifier = prepare_fixture(arguments.field_session_id)
    print(json.dumps({"evidence": "synthetic scripted rectangles and annotations; not physical or ML accuracy evidence",
                      "video": str(VIDEO), "source_id": identifier}, indent=2), flush=True)
    if not arguments.prepare_only:
        uvicorn.run(create_app(TrafficValidationManager()), host="127.0.0.1", port=arguments.port)
