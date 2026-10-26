"""Measure synthetic pinhole fitting and cached correction; no camera or road accuracy test."""

import argparse
import json
import os
import platform
from pathlib import Path
from time import perf_counter

import cv2
import numpy as np

from roadlens.camera_calibration import FrameUndistorter, checkerboard_object_points, fit_camera
from roadlens.camera_models import CameraCalibrationInput


def run_benchmark(repetitions=200):
    configuration = CameraCalibrationInput(name="Synthetic pinhole fixture", camera_configuration_id="synthetic-640x480")
    matrix = np.array([[600., 0, 320], [0, 610., 240], [0, 0, 1]])
    distortion = np.array([-.12, .03, .001, -.001, .001])
    objects = checkerboard_object_points(configuration)
    corners = []
    for index in range(10):
        rotation = np.array([-.3+.065*index, .22*np.cos(index), -.18+.035*index])
        translation = np.array([-125.+22*(index % 4), -90.+32*(index % 3), 570.+40*(index % 5)])
        image, _ = cv2.projectPoints(objects, rotation, translation, matrix, distortion)
        corners.append(image)
    started = perf_counter()
    profile = fit_camera(corners, (640, 480), configuration, provenance="synthetic")
    fit_ms = (perf_counter()-started)*1000
    results = []
    for width, height in [(640, 480), (1280, 720)]:
        camera_matrix = np.asarray(profile.camera_matrix).copy()
        camera_matrix[0] *= width/640
        camera_matrix[1] *= height/480
        scaled = profile.model_copy(update={"width": width, "height": height, "camera_matrix": camera_matrix.tolist()})
        started = perf_counter()
        corrector = FrameUndistorter(scaled)
        map_ms = (perf_counter()-started)*1000
        rng = np.random.default_rng(2026)
        image = rng.integers(0, 255, (height, width, 3), dtype=np.uint8)
        for _ in range(10):
            corrector.apply(image)
        times = []
        for _ in range(repetitions):
            started = perf_counter()
            corrector.apply(image)
            times.append((perf_counter()-started)*1000)
        results.append({"width": width, "height": height, "map_initialization_ms": map_ms,
                        "cached_apply_mean_ms": float(np.mean(times)), "cached_apply_median_ms": float(np.median(times)),
                        "cached_apply_p95_ms": float(np.quantile(times, .95)), "repetitions": repetitions})
    return {"evidence": "synthetic projected corners and generated pixels; no physical camera, detection or speed validation",
            "hardware": {"processor": os.environ.get("PROCESSOR_IDENTIFIER") or platform.processor(),
                         "logical_cpus": os.cpu_count(), "platform": platform.platform(), "python": platform.python_version(),
                         "opencv": cv2.__version__, "opencv_threads": cv2.getNumThreads()},
            "method": "10 warm-up remaps; independent timed cached apply calls; K'=K, same dimensions, no crop; CPU load affects timings",
            "fit_ms": fit_ms, "synthetic_fit_rms_px": profile.rms_reprojection_error_px,
            "maximum_focal_error_px": float(np.max(np.abs(np.diag(np.asarray(profile.camera_matrix))[:2]-np.diag(matrix)[:2]))),
            "resolutions": results}


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path)
    parser.add_argument("--repetitions", type=int, default=200)
    args = parser.parse_args()
    if not 10 <= args.repetitions <= 10000:
        parser.error("Choose 10–10000 repetitions.")
    report = run_benchmark(args.repetitions)
    rendered = json.dumps(report, indent=2, allow_nan=False)
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(rendered + "\n", encoding="utf-8")
    print(rendered)
