"""Measure the CPU pipeline on a CC0 still replay, with synthetic geometry.

This is a repeatable workload, not moving traffic or road-speed validation.
No camera is opened. Timings use perf_counter independently of source time.
"""

import argparse
import hashlib
import json
import os
import platform
from pathlib import Path
from statistics import fmean, median
from time import perf_counter

import cv2
import numpy as np

from roadlens.calibration import CalibrationTransform, validate_gates
from roadlens.calibration_models import CalibrationInput, GateInput
from roadlens.detector import RoadLensDetector
from roadlens.session import draw_tracks
from roadlens.speed import SpeedEstimator
from roadlens.tracker import IoUTracker


def cpu_name():
    try:
        import winreg
        with winreg.OpenKey(winreg.HKEY_LOCAL_MACHINE, r"HARDWARE\DESCRIPTION\System\CentralProcessor\0") as key:
            return winreg.QueryValueEx(key, "ProcessorNameString")[0].strip()
    except (ImportError, OSError):
        return platform.processor()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--frames", type=int, default=12)
    parser.add_argument("--input-size", type=int, choices=(320, 416, 640), default=640)
    parser.add_argument("--output", type=Path, default=Path("data/profiling/pipeline.json"))
    args = parser.parse_args()
    if not 3 <= args.frames <= 1000:
        parser.error("Use 3–1000 measured frames.")
    root = Path(__file__).resolve().parents[1]
    fixture = root / "backend/tests/fixtures/city_traffic_cc0.jpg"
    image = cv2.resize(cv2.imread(str(fixture)), (640, 360))
    detector = RoadLensDetector(root / "models/vehicle_detector.onnx", input_size=args.input_size)
    transform = CalibrationTransform(CalibrationInput.model_validate({
        "name": "SYNTHETIC plane for profiling only", "source_id": "synthetic:cc0-still-replay",
        "geometry": {"width": 640, "height": 360},
        "points": [{"image": [x, y], "world": [x / 10, y / 10]} for x, y in ((0, 0), (639, 0), (639, 359), (0, 359))],
        "check_points": [],
    }))
    gates = validate_gates(transform, GateInput(gate_a=((213, 20), (213, 340)), gate_b=((426, 20), (426, 340))))
    estimator = SpeedEstimator(transform, gates, "synthetic:cc0-still-replay", "synthetic-profile", "profile-run")
    tracker = IoUTracker()
    detector.detect(image)  # One unmeasured warm-up; model loading is excluded.
    stages = {name: [] for name in ("detection_ms", "tracking_ms", "projection_ms", "gate_events_ms", "render_encode_ms", "total_ms")}
    detection_counts = []
    started = perf_counter()
    for index in range(args.frames):
        frame_started = perf_counter()
        detections = detector.detect(image)
        detected = perf_counter()
        tracks = tracker.update(detections, index / 10)
        tracked = perf_counter()
        tracks = estimator.update(tracks, index / 10)
        render_started = perf_counter()
        encoded, _ = cv2.imencode(".jpg", draw_tracks(image, tracks, gates=gates), [cv2.IMWRITE_JPEG_QUALITY, 82])
        if not encoded:
            raise RuntimeError("Could not encode profiling preview.")
        finished = perf_counter()
        stages["detection_ms"].append((detected - frame_started) * 1000)
        stages["tracking_ms"].append((tracked - detected) * 1000)
        for name in ("projection_ms", "gate_events_ms"):
            stages[name].append(estimator.last_profile[name])
        stages["render_encode_ms"].append((finished - render_started) * 1000)
        stages["total_ms"].append((finished - frame_started) * 1000)
        detection_counts.append(len(detections))
    elapsed = perf_counter() - started
    report = {
        "workload": "Actual YOLOX CPU on a repeated CC0 still; synthetic calibration geometry, no physical camera or moving traffic.",
        "hardware": {"cpu": cpu_name(), "logical_cpus": os.cpu_count(), "os": platform.platform(), "python": platform.python_version(),
                     "opencv": cv2.__version__, "opencv_threads": cv2.getNumThreads()},
        "frames": args.frames, "warm_up_frames": 1, "input_size": args.input_size, "image_geometry": [640, 360],
        "fixture_sha256": hashlib.sha256(fixture.read_bytes()).hexdigest(), "detection_counts": detection_counts,
        "timings": {name: {"mean": fmean(values), "median": median(values), "p95": float(np.percentile(values, 95))} for name, values in stages.items()},
        "effective_processed_fps": args.frames / elapsed, "dropped_frames": 0,
        "limits": "In-memory sequential replay; excludes source decode, camera, HTTP and browser. Zero drops are by construction, not a live performance claim. Synthetic geometry establishes no metric scale for this photograph.",
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, indent=2), encoding="utf-8")
    print(json.dumps(report, indent=2))


if __name__ == "__main__":
    main()
