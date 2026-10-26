"""Run the existing application with a labeled synthetic marker detector.

This optional test harness exercises recorded PTS, calibration UI, tracking and
gates. It does not test ML detection or accuracy on real traffic. The standard
roadlens.api:app entry point never uses this adapter.
"""

import argparse
import hashlib
import json
import time
from pathlib import Path

import cv2
import numpy as np
import uvicorn

from roadlens.api import create_app
from roadlens.capture import SourceError, VideoSource
from roadlens.detector import Detection
from roadlens.session import SessionManager


ROOT = Path(__file__).resolve().parents[1]
VIDEO = ROOT / "data" / "validation" / "SYNTHETIC_60kmh_validation.avi"


def prepare_fixture() -> tuple[Path, str]:
    VIDEO.parent.mkdir(parents=True, exist_ok=True)
    configuration = VIDEO.parent / "configuration.json"
    if VIDEO.is_file() and configuration.is_file():
        saved = json.loads(configuration.read_text(encoding="utf-8"))
        with VIDEO.open("rb") as stream:
            identifier = "video:" + hashlib.file_digest(stream, "sha256").hexdigest()
        if saved.get("calibration", {}).get("source_id") == identifier:
            return VIDEO, identifier
    writer = cv2.VideoWriter(str(VIDEO), cv2.VideoWriter_fourcc(*"FFV1"), 25, (800, 600))
    if not writer.isOpened():
        raise RuntimeError("The lossless FFV1 encoder is unavailable in this OpenCV installation.")
    try:
        for index in range(810):
            image = np.full((600, 800, 3), (25, 29, 30), np.uint8)
            cv2.putText(image, "SYNTHETIC GEOMETRY VALIDATION", (28, 35), cv2.FONT_HERSHEY_SIMPLEX, 0.8, (220, 230, 220), 1, cv2.LINE_AA)
            cv2.putText(image, "Color marker adapter - not real vehicle inference", (28, 65), cv2.FONT_HERSHEY_SIMPLEX, 0.5, (180, 185, 180), 1, cv2.LINE_AA)
            for x in range(100, 701, 100):
                cv2.line(image, (x, 100), (x, 550), (55, 65, 60), 1)
            for y in range(100, 551, 50):
                cv2.line(image, (100, y), (700, y), (55, 65, 60), 1)
            for label, point in enumerate(((100, 100), (700, 100), (700, 550), (100, 550)), 1):
                cv2.circle(image, point, 5, (80, 170, 110), -1)
                cv2.putText(image, f"P{label}", (point[0] + 9, point[1] - 7), cv2.FONT_HERSHEY_SIMPLEX, 0.5, (180, 220, 180), 1)
            # 0.1 m/pixel and 166 2/3 pixels/s give 60 km/h between x=200 and x=400.
            movement_s = max(0.0, (index - 375) / 25)
            x = round(min(550, 150 + movement_s * (500 / 3)))
            cv2.rectangle(image, (x - 30, 260), (x + 29, 299), (240, 200, 40), -1)
            cv2.putText(image, f"SOURCE FRAME {index:03d}  /  {index / 25:.2f} s", (28, 580), cv2.FONT_HERSHEY_SIMPLEX, 0.5, (170, 180, 170), 1)
            writer.write(image)
    finally:
        writer.release()
    with VIDEO.open("rb") as stream:
        source_id = "video:" + hashlib.file_digest(stream, "sha256").hexdigest()
    example = {
        "scenario": "SYNTHETIC ONLY: known drawing coordinates, not measured real roadway references",
        "calibration": {
            "name": "Synthetic 60 km/h validation", "source_id": source_id,
            "geometry": {"width": 800, "height": 600, "rotation": 0, "mirrored": False, "crop": None},
            "points": [
                {"image": [100, 100], "world": [0, 0]}, {"image": [700, 100], "world": [60, 0]},
                {"image": [700, 550], "world": [60, 45]}, {"image": [100, 550], "world": [0, 45]},
            ],
            "check_points": [{"image": [450, 350], "world": [35, 25]}],
        },
        "gates": {"gate_a": [[200, 200], [200, 450]], "gate_b": [[400, 200], [400, 450]], "allow_reverse": False},
        "expected": {"distance_m": 20, "elapsed_seconds": 1.2, "estimated_speed_kmh": 60.0},
    }
    configuration.write_text(json.dumps(example, indent=2), encoding="utf-8")
    return VIDEO, source_id


class MarkerDetector:
    def __init__(self, *args, **kwargs):
        pass

    def detect(self, image):
        mask = cv2.inRange(image, np.array([220, 180, 20]), np.array([255, 220, 60]))
        points = cv2.findNonZero(mask)
        if points is None:
            return []
        x, y, width, height = cv2.boundingRect(points)
        return [Detection((x, y, x + width, y + height), 1.0, "car")]


class PacedVideo(VideoSource):
    def read(self):
        time.sleep(1 / 25)
        return super().read()


class ValidationManager(SessionManager):
    def __init__(self, expected_source_id: str):
        self.expected_source_id = expected_source_id

        def source(request, video_path, label):
            if request.source_type != "video":
                raise SourceError("The validation harness accepts only the generated synthetic video.")
            return PacedVideo(video_path, label)

        super().__init__(detector_factory=MarkerDetector, source_factory=source,
                         upload_dir=VIDEO.parent / "uploads", calibration_dir=VIDEO.parent / "calibrations")

    def register_video(self, path, label, source_id=None):
        if source_id != self.expected_source_id:
            raise SourceError("Select SYNTHETIC_60kmh_validation.avi. Use the standard backend for real videos.")
        return super().register_video(path, label, source_id)

    def model_status(self):
        return {"ready": True, "name": "Synthetic marker · validation only", "path": "No ML model used by this test adapter", "input_size": 640}

    def cameras(self):
        return []


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--port", type=int, default=8000)
    args = parser.parse_args()
    path, identifier = prepare_fixture()
    print(f"SYNTHETIC TEST HARNESS: upload {path}", flush=True)
    print("Uses known drawing geometry and a color-marker detector; this is not traffic accuracy validation.", flush=True)
    uvicorn.run(create_app(ValidationManager(identifier)), host="127.0.0.1", port=args.port)
