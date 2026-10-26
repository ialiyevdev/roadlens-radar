"""Synthetic retained-state polling profile; never opens hardware or inference.

The state clones one synthetic result into 1000 records and tiles its raw
samples to 120 entries per record. These are storage fixtures, not independent
observations or chronological trajectories. Timings exclude state construction.
Three cached-sync/snapshot/JSON runs
measure only the public polling path. This is not live pipeline throughput.
"""

import argparse
import json
import platform
import statistics
import time
from pathlib import Path

from roadlens.calibration import CalibrationTransform, validate_gates
from roadlens.calibration_models import CalibrationInput, GateInput
from roadlens.measurement_session import MeasurementSession
from roadlens.session import SessionManager
from roadlens.speed import SpeedEstimator


def elapsed_ms(operation):
    started = time.perf_counter()
    value = operation()
    return value, (time.perf_counter() - started) * 1000


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--measurements", type=int, default=1000)
    parser.add_argument("--samples", type=int, default=120)
    parser.add_argument("--repeats", type=int, default=3)
    parser.add_argument("--output", type=Path, default=Path("data/validation/polling_profile.json"))
    args = parser.parse_args()
    if not (1 <= args.measurements <= 1000 and 3 <= args.samples <= 120 and 1 <= args.repeats <= 20):
        parser.error("Use 1–1000 measurements, 3–120 retained samples and 1–20 repetitions.")
    root = Path(__file__).resolve().parents[1]
    fixture = json.loads((root / "backend/tests/fixtures/synthetic_trajectory.json").read_text())
    transform = CalibrationTransform(CalibrationInput.model_validate(fixture["calibration"]))
    gates = validate_gates(transform, GateInput.model_validate(fixture["gates"]))
    estimator = SpeedEstimator(transform, gates, transform.data.source_id, "synthetic", "polling-profile")
    for index, sample in enumerate(fixture["samples"], 1):
        x, y = sample["image_position"]
        raw = dict(id=1, category="car", bbox=(x - 8, y - 16, x + 8, y), confidence=.9,
                   state="confirmed", hits=index, missed=0, history=[])
        estimator.update([raw], sample["timestamp_s"])
    base = estimator.measurements[0]
    base.position_samples = [base.position_samples[index % len(base.position_samples)].model_copy(deep=True)
                             for index in range(args.samples)]
    estimator.measurements = [base.model_copy(update={"id": f"polling-profile:{index}", "track_id": index}, deep=True)
                              for index in range(args.measurements)]
    measurement = MeasurementSession()
    measurement.estimator = estimator
    measurement.transform = transform
    measurement.gates = gates
    measurement.status = "ready"
    manager = SessionManager()
    manager._measurement = measurement
    _, first_sync_ms = elapsed_ms(lambda: measurement.sync(manager._snapshot))
    runs = []
    for _ in range(args.repeats):
        _, sync_ms = elapsed_ms(lambda: measurement.sync(manager._snapshot))
        snapshot, snapshot_ms = elapsed_ms(manager.snapshot)
        encoded, serialization_ms = elapsed_ms(snapshot.model_dump_json)
        assert '"position_samples":' not in encoded and '"calibration_metadata":' not in encoded
        assert len(estimator.measurements[0].position_samples) == args.samples
        runs.append({"cached_sync_ms": sync_ms, "snapshot_copy_ms": snapshot_ms,
                     "json_serialization_ms": serialization_ms,
                     "payload_bytes": len(encoded.encode("utf-8"))})
    report = {
        "provenance": "synthetic", "description": __doc__,
        "hardware": {"os": platform.platform(), "cpu": platform.processor(), "python": platform.python_version()},
        "measurement_records": args.measurements, "retained_samples_each": args.samples,
        "construction_excluded": True, "initial_public_cache_sync_ms": first_sync_ms, "runs": runs,
        "median_cached_sync_ms": statistics.median(run["cached_sync_ms"] for run in runs),
        "median_snapshot_copy_ms": statistics.median(run["snapshot_copy_ms"] for run in runs),
        "median_json_serialization_ms": statistics.median(run["json_serialization_ms"] for run in runs),
        "payload_MiB": runs[0]["payload_bytes"] / 1024 ** 2,
        "limitations": "Synthetic retained-state polling only; not physical camera, inference, full evidence export, or FPS profiling. Host load can affect timings.",
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(report, indent=2))


if __name__ == "__main__":
    main()
