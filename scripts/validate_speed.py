"""Reproduce deterministic source-time and homography validation without a camera."""

import json
from math import isclose
from pathlib import Path

from roadlens.calibration import CalibrationTransform, validate_gates
from roadlens.calibration_models import CalibrationInput, GateInput
from roadlens.speed import SpeedEstimator


def validate_fixture(path: Path) -> dict:
    fixture = json.loads(path.read_text(encoding="utf-8"))
    transform = CalibrationTransform(CalibrationInput.model_validate(fixture["calibration"]))
    gates = validate_gates(transform, GateInput.model_validate(fixture["gates"]))
    estimator = SpeedEstimator(transform, gates, transform.data.source_id, "synthetic-calibration", "synthetic-session")
    for index, sample in enumerate(fixture["samples"], start=1):
        x, y = sample["image_position"]
        estimator.update([{
            "id": 1, "category": "car", "bbox": (x - 8, y - 16, x + 8, y),
            "confidence": 1.0, "state": "confirmed", "hits": index, "missed": 0, "history": [],
        }], sample["timestamp_s"])
    assert len(estimator.measurements) == 1, "Expected one completed synthetic crossing."
    result = estimator.measurements[0]
    assert result.status == "valid", result.reasons
    for key, expected in fixture["expected"].items():
        actual = getattr(result, key)
        assert actual is not None and isclose(actual, expected, abs_tol=1e-7), f"{key}: {actual} != {expected}"
    return {"scenario": fixture["description"], "expected": fixture["expected"], "actual": result.model_dump(), "passed": True}


if __name__ == "__main__":
    path = Path(__file__).resolve().parents[1] / "backend" / "tests" / "fixtures" / "synthetic_trajectory.json"
    print(json.dumps(validate_fixture(path), indent=2))
