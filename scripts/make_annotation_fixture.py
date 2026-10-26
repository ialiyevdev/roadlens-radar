"""Create a labeled synthetic clip and matching example annotations for UI exercises."""

import argparse
import hashlib
import json
from pathlib import Path

import cv2
import numpy as np

from roadlens.annotation_metrics import annotation_metrics
from roadlens.annotation_models import AnnotationDocument
from roadlens.annotation_store import annotations_csv


def make_fixture(directory: Path, field_session_id: str):
    directory.mkdir(parents=True, exist_ok=True)
    video = directory / "synthetic_annotations.avi"
    if not video.exists():
        writer = cv2.VideoWriter(str(video), cv2.VideoWriter_fourcc(*"FFV1"), 10, (640, 480))
        if not writer.isOpened():
            raise ValueError("OpenCV could not create the FFV1 synthetic clip.")
        try:
            for index in range(1, 9):
                image = np.full((480, 640, 3), 35, np.uint8)
                if index in (1, 2, 4, 5, 6):
                    x = 100+10*(index-1)
                    cv2.rectangle(image, (x, 100), (x+80, 180), (100, 200, 100), -1)
                elif index == 8:
                    cv2.rectangle(image, (400, 200), (470, 270), (100, 170, 220), -1)
                cv2.putText(image, "SYNTHETIC annotation exercise - no road evidence", (18, 440),
                            cv2.FONT_HERSHEY_SIMPLEX, .55, (220, 220, 220), 1, cv2.LINE_AA)
                cv2.putText(image, f"Frame {index} / 8", (18, 465), cv2.FONT_HERSHEY_SIMPLEX, .5,
                            (220, 220, 220), 1, cv2.LINE_AA)
                writer.write(image)
        finally:
            writer.release()
    digest = hashlib.sha256(video.read_bytes()).hexdigest()
    frames = []
    for index in range(1, 9):
        objects, predictions = [], []
        if index <= 6:
            x = 100+10*(index-1)
            bbox = None if index == 3 else [x, 100, x+80, 180]
            objects.append({"identity": "manual-vehicle-001", "category": "car", "bbox": bbox,
                            "occluded": index == 3, "partial_visibility": index == 4,
                            "entry": index == 1, "exit": index == 6})
            if index not in (3, 5):
                predictions.append({"predicted_track_id": 1 if index <= 2 else 2,
                                    "category": "car", "bbox": bbox, "confidence": .8})
        if index == 7:
            predictions.append({"predicted_track_id": 3, "category": "car", "bbox": [300, 200, 370, 270], "confidence": .6})
        if index == 8:
            objects.append({"identity": "manual-vehicle-002", "category": "car", "bbox": [400, 200, 470, 270]})
        frames.append({"index": index, "timestamp_s": (index-1)/10, "reviewed": index != 8,
                       "objects": objects, "predictions": predictions})
    annotations = AnnotationDocument(field_session_id=field_session_id, source_id="video:"+digest,
        geometry={"width": 640, "height": 480}, provenance="synthetic", frames=frames)
    (directory / "annotations.json").write_text(annotations.model_dump_json(indent=2)+"\n", encoding="utf-8")
    (directory / "annotations.csv").write_text(annotations_csv(annotations), encoding="utf-8", newline="")
    metrics = {"evidence": "synthetic shapes, manually scripted predictions; not model inference or physical roadway data",
               "source_sha256": digest, "metrics": annotation_metrics(annotations)}
    (directory / "metrics.json").write_text(json.dumps(metrics, indent=2)+"\n", encoding="utf-8")
    return metrics


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--directory", type=Path, default=Path("data/annotation_fixture"))
    parser.add_argument("--field-session-id", default="00000000-0000-4000-8000-000000000004",
                        help="Use the UUID of the field session created for the uploaded generated clip.")
    args = parser.parse_args()
    print(json.dumps(make_fixture(args.directory, args.field_session_id), indent=2))
