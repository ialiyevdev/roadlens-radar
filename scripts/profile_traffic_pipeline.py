"""Actual YOLOX CPU still replay, with separate Phase 5 incremental costs."""

import argparse
import hashlib
import json
import os
import platform
from datetime import datetime, timezone
from pathlib import Path
from time import perf_counter
from uuid import UUID

import cv2

from profile_pipeline import cpu_name
from profile_traffic import distribution
from roadlens.detector import RoadLensDetector
from roadlens.traffic_analytics import analyze_traffic
from roadlens.traffic_engine import TrafficEngine
from roadlens.traffic_models import TrafficConfiguration
from roadlens.tracker import IoUTracker


def run(frames=12, input_size=640):
    root = Path(__file__).resolve().parents[1]
    fixture = root / "backend/tests/fixtures/city_traffic_cc0.jpg"
    original = cv2.imread(str(fixture))
    if original is None:
        raise RuntimeError("The existing CC0 still-image fixture is unavailable.")
    image = cv2.resize(original, (640, 360))
    model = root / "models/vehicle_detector.onnx"
    detector = RoadLensDetector(model, input_size=input_size)
    tracker = IoUTracker()
    config = TrafficConfiguration(source_id="synthetic:cc0-still-profile", geometry={"width": 640, "height": 360},
        lines=[{"id": "left", "label": "Synthetic left line", "start": [213, 0], "end": [213, 359]},
               {"id": "right", "label": "Synthetic right line", "start": [426, 0], "end": [426, 359]}],
        zones=[{"id": "region", "label": "Synthetic image region", "points": [[0, 0], [639, 0], [639, 359], [0, 359]]}])
    traffic = TrafficEngine(str(UUID(int=512)), config.source_id, config.geometry, config, "synthetic")
    detector.detect(image)
    stages = {key: [] for key in ("detection_ms", "tracking_ms", "traffic_ms", "classification_ms", "crossing_ms",
                                 "event_creation_ms", "zones_ms", "statistics_ms", "serialization_ms", "total_ms")}
    detection_counts, track_counts = [], []
    for frame in range(frames):
        started = perf_counter()
        detections = detector.detect(image)
        detected = perf_counter()
        tracks = tracker.update(detections, frame / 10)
        tracked = perf_counter()
        traffic.update(tracks, frame / 10, frame_index=frame + 1)
        updated = perf_counter()
        snapshot = traffic.snapshot()
        report = analyze_traffic([snapshot])
        analyzed = perf_counter()
        json.dumps({"snapshot": snapshot, "analytics": report}, allow_nan=False)
        ended = perf_counter()
        stages["detection_ms"].append((detected - started) * 1000)
        stages["tracking_ms"].append((tracked - detected) * 1000)
        stages["traffic_ms"].append((updated - tracked) * 1000)
        stages["statistics_ms"].append((analyzed - updated) * 1000)
        stages["serialization_ms"].append((ended - analyzed) * 1000)
        stages["total_ms"].append((ended - started) * 1000)
        for key in ("classification_ms", "crossing_ms", "event_creation_ms", "zones_ms"):
            stages[key].append(snapshot["profile"][key])
        detection_counts.append(len(detections))
        track_counts.append(len(tracks))
    return {"schema_version": 1, "generated_at": datetime.now(timezone.utc).isoformat(),
            "evidence_type": "actual_model_still_replay_with_synthetic_regions",
            "workload": "Actual YOLOX-S INT8 on a repeated CC0 image. Two manually configured counting lines and one image zone exercise the new code; vehicles do not move.",
            "hardware": {"cpu": cpu_name(), "logical_cpus": os.cpu_count(), "os": platform.platform(),
                         "python": platform.python_version(), "opencv": cv2.__version__, "opencv_threads": cv2.getNumThreads()},
            "frames": frames, "warm_up_frames": 1, "input_size": input_size, "image_geometry": [640, 360],
            "fixture_sha256": hashlib.sha256(fixture.read_bytes()).hexdigest(),
            "model_sha256": hashlib.sha256(model.read_bytes()).hexdigest(),
            "detection_counts": detection_counts, "track_counts": track_counts,
            "counting_lines": 2, "image_zones": 1, "crossings": traffic.snapshot()["summary"]["total_crossings"],
            "timings": {key: distribution(values) for key, values in stages.items()},
            "limitations": ["In-memory still replay excludes decode, lens correction, road projection, speed estimation, overlays, JPEG, HTTP and browser rendering.",
                            "Model loading and one warm-up inference are excluded. Source time advances by 0.1 seconds independently of perf_counter timings.",
                            "A still image provides no moving-vehicle counting accuracy or physical speed evidence. Synthetic regions establish no real camera geometry.",
                            "Additional traffic cost is measured separately; these timings do not establish a statistically significant throughput change."]}


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--frames", type=int, default=12)
    parser.add_argument("--input-size", type=int, choices=(320, 416, 640), default=640)
    parser.add_argument("--output", type=Path, default=Path("docs/benchmarks/phase5-model-performance.json"))
    args = parser.parse_args()
    if not 3 <= args.frames <= 1000:
        parser.error("Use 3–1000 measured frames.")
    result = run(args.frames, args.input_size)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, indent=2, allow_nan=False) + "\n", encoding="utf-8", newline="\n")
    print(json.dumps(result, indent=2, allow_nan=False))
