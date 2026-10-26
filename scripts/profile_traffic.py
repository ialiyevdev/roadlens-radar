"""Profile deterministic traffic aggregation/exports separately from inference."""

import argparse
import json
import platform
import statistics
from datetime import datetime, timezone
from pathlib import Path
from time import perf_counter
from uuid import UUID

from benchmark_traffic import configuration
from make_traffic_fixture import make_fixture
from roadlens.detector import Detection
from roadlens.traffic_analytics import analyze_traffic, percentile, traffic_export
from roadlens.traffic_engine import TrafficEngine
from roadlens.tracker import IoUTracker


def distribution(values):
    return {"n": len(values), "mean_ms": statistics.fmean(values), "median_ms": statistics.median(values),
            "p95_ms": percentile(values, .95), "maximum_ms": max(values)}


def measure(operation, repetitions):
    operation()
    values = []
    for _ in range(repetitions):
        started = perf_counter()
        operation()
        values.append((perf_counter() - started) * 1000)
    return distribution(values)


def run(repetitions=30):
    artifact, _ = make_fixture()
    report = analyze_traffic([artifact])
    config = configuration()
    engine = TrafficEngine(str(UUID(int=995)), config.source_id, config.geometry, config, "synthetic")
    # Dense, static synthetic boxes exercise association and polygon clipping; no detector is invoked.
    tracking_values, traffic_values, stages = [], [], []
    tracker = IoUTracker()
    for frame in range(200):
        detections = [Detection(bbox=(10 + col * 18, 20 + row * 20, 23 + col * 18, 35 + row * 20), confidence=.9, category="car")
                      for row in range(4) for col in range(8)]
        started = perf_counter()
        tracks = tracker.update(detections, frame / 10)
        if len(tracks) != 32:
            raise RuntimeError("The dense synthetic profile must retain all 32 valid input tracks.")
        tracking_values.append((perf_counter() - started) * 1000)
        started = perf_counter()
        engine.update(tracks, frame / 10, frame_index=frame + 1)
        traffic_values.append((perf_counter() - started) * 1000)
        stages.append(engine.snapshot()["profile"])
    dense = engine.snapshot()
    return {"schema_version": 1, "generated_at": datetime.now(timezone.utc).isoformat(), "evidence_type": "synthetic",
            "environment": {"platform": platform.platform(), "processor": platform.processor(), "python": platform.python_version()},
            "workload": {"repetitions": repetitions, "small_artifact_events": len(artifact["events"]),
                         "small_artifact_frames": 120, "dense_frames": 200, "dense_tracks_per_frame": 32,
                         "counting_lines": len(config.lines), "image_zones": len(config.zones)},
            "dense_tracking_per_frame": distribution(tracking_values),
            "dense_traffic_per_frame": distribution(traffic_values),
            "dense_traffic_stages": {key: distribution([row[key] for row in stages]) for key in stages[0]},
            "small_statistics_aggregation": measure(lambda: analyze_traffic([artifact]), repetitions),
            "dense_statistics_aggregation": measure(lambda: analyze_traffic([dense]), repetitions),
            "dashboard_snapshot_serialization": measure(lambda: json.dumps(dense, allow_nan=False), repetitions),
            "dashboard_analytics_serialization": measure(lambda: json.dumps(analyze_traffic([dense]), allow_nan=False), repetitions),
            "exports": {f"{table}_{format}": measure(lambda t=table, f=format: traffic_export(report, t, f), repetitions)
                        for table in ("events", "flow", "speeds", "zones") for format in ("json", "csv")},
            "limitations": ["Inference, video decode, network/HTTP and browser rendering are excluded; these are additional CPU software costs.",
                            "Tracker and traffic timings use deterministic 32-box inputs and one image zone, not measured roadway throughput.",
                            "Detection is unchanged; use the existing real-model pipeline profile for separate end-to-end inference evidence."]}


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path)
    parser.add_argument("--repetitions", type=int, default=30)
    args = parser.parse_args()
    if args.repetitions < 1:
        parser.error("Repetitions must be positive.")
    report = run(args.repetitions)
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(json.dumps(report, indent=2, allow_nan=False) + "\n", encoding="utf-8", newline="\n")
    print(json.dumps({key: value for key, value in report.items() if key != "exports"}, indent=2))
