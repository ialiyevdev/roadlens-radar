"""Inference-free synthetic counting scenarios with known crossing expectations."""

import argparse
import json
import platform
import statistics
from datetime import datetime, timezone
from pathlib import Path
from time import perf_counter
from uuid import UUID

from roadlens.traffic_analytics import percentile
from roadlens.traffic_engine import TrafficEngine
from roadlens.traffic_models import TrafficConfiguration


SOURCE = "synthetic:phase5-trajectories"


def track(identity, x, y, category="car"):
    return {"id": identity, "bbox": [x - 8, y - 12, x + 8, y], "category": category,
            "confidence": .9, "hits": 10, "state": "confirmed"}


def configuration(**changes):
    return TrafficConfiguration.model_validate({"id": "synthetic-main", "name": "SYNTHETIC counting configuration",
        "source_id": SOURCE, "geometry": {"width": 200, "height": 120},
        "lines": [{"id": "main", "label": "Synthetic main line", "start": [0, 60], "end": [200, 60],
                   "positive_label": "Down image", "negative_label": "Up image"}],
        "zones": [{"id": "approach", "label": "Synthetic approach", "points": [[20, 20], [180, 20], [180, 100], [20, 100]]}],
        **changes})


def scenarios():
    ys = [10, 20, 30, 45, 55, 70, 90, 110]
    def frames(objects):
        return [(index / 10, objects(index, y)) for index, y in enumerate(ys)]
    output = [
        ("single_crossing", configuration(), frames(lambda i, y: [track(1, 50, y)]), 1, 0),
        ("multiple_vehicles", configuration(), frames(lambda i, y: [track(j, 30 + j * 40, y) for j in (1, 2, 3)]), 3, 0),
        ("bidirectional", configuration(), frames(lambda i, y: [track(1, 50, y), track(2, 140, 120 - y, "bus")]), 2, 0),
        ("line_boundary_jitter", configuration(), [(i / 10, [track(1, 50, y)]) for i, y in enumerate([10, 20, 30, 58, 62, 59, 61, 50, 70, 90])], 1, 0),
        ("short_occlusion", configuration(), frames(lambda i, y: [] if i in (3, 4) else [track(1, 50, y)]), 1, 0),
        ("identity_fragment_duplicate", configuration(), [(i / 10, [track(1 if i < 5 else 2, 50, y)])
             for i, y in enumerate([10, 20, 30, 45, 70, 30, 45, 70, 90])], 1, 1),
        ("multiple_lines", configuration(lines=[{"id": "upper", "label": "Upper", "start": [0, 40], "end": [200, 40]},
              {"id": "lower", "label": "Lower", "start": [0, 80], "end": [200, 80]}]), frames(lambda i, y: [track(1, 50, y)]), 2, 0),
        ("source_time_gap", configuration(), [(0, [track(1, 50, 10)]), (.1, [track(1, 50, 30)]), (5, [track(1, 50, 90)])], 0, 0),
        ("missing_timestamp", configuration(), [(0, [track(1, 50, 10)]), (.1, [track(1, 50, 30)]),
             (None, [track(1, 50, 70)]), (.3, [track(1, 50, 90)])], 0, 0),
        ("unknown_category", configuration(), frames(lambda i, y: [track(1, 50, y, "unsupported")]), 1, 0),
        ("noisy_class_evidence", configuration(), frames(lambda i, y: [track(1, 50, y, "truck" if i == 2 else "car")]), 1, 0),
        ("simultaneous_close_vehicles", configuration(), frames(lambda i, y: [track(1, 50, y), track(2, 55, y)]), 2, 0),
        ("same_track_two_directions", configuration(), [(i / 10, [track(1, 50, y)]) for i, y in enumerate([10, 20, 30, 50, 70, 90, 70, 50, 30])], 2, 0),
        ("outside_finite_line", configuration(lines=[{"id": "short", "label": "Short", "start": [0, 60], "end": [30, 60]}]),
             frames(lambda i, y: [track(1, 80, y)]), 0, 0),
    ]
    return output


def run_case(item, number=1):
    name, config, frames, expected_count, expected_suppressed = item
    engine = TrafficEngine(str(UUID(int=number)), SOURCE, config.geometry, config, "synthetic")
    profiles, timings = [], []
    processed = 0
    for index, (timestamp, tracks) in enumerate(frames, 1):
        started = perf_counter()
        engine.update(tracks, timestamp, frame_index=index)
        timings.append((perf_counter() - started) * 1000)
        snapshot = engine.snapshot()
        accepted = snapshot["diagnostics"].get("processed_frames", 0)
        if accepted > processed:
            profiles.append(snapshot["profile"])
        processed = accepted
    result = engine.snapshot()
    count = sum(row["status"] == "counted" for row in result["events"])
    suppressed = sum(row["status"] == "suppressed" for row in result["events"])
    return {"scenario": name, "frames": len(frames), "expected_crossings": expected_count,
            "actual_crossings": count, "expected_suppressed": expected_suppressed, "actual_suppressed": suppressed,
            "expectation_met": count == expected_count and suppressed == expected_suppressed,
            "classes": result["summary"]["by_class"], "directions": result["summary"]["by_direction"],
            "zone_events": len(result["zone_events"]), "diagnostics": result["diagnostics"],
            "mean_update_ms": statistics.fmean(timings), "p95_update_ms": percentile(timings, .95)}, profiles


def run_benchmark(repetitions=30):
    cases = scenarios()
    rows, profiles = [], []
    for number, case in enumerate(cases, 1):
        result, _ = run_case(case, number)
        rows.append(result)
        for _ in range(repetitions):
            _, samples = run_case(case, number)
            profiles.extend(samples)
    stages = {key: {"n": len(values), "mean_ms": statistics.fmean(values), "p95_ms": percentile(values, .95), "maximum_ms": max(values)}
              for key in ("classification_ms", "crossing_ms", "event_creation_ms", "zones_ms", "update_ms")
              if (values := [row[key] for row in profiles if key in row])}
    return {"schema_version": 1, "generated_at": datetime.now(timezone.utc).isoformat(), "evidence_type": "synthetic",
            "description": "Known trajectory inputs enter the real traffic engine. No detection, tracking association, video decoding, HTTP or physical traffic is included.",
            "environment": {"platform": platform.platform(), "processor": platform.processor(), "python": platform.python_version()},
            "repetitions": repetitions, "scenario_count": len(rows), "frame_count": sum(row["frames"] for row in rows),
            "expectations_met": sum(row["expectation_met"] for row in rows),
            "expected_crossings": sum(row["expected_crossings"] for row in rows),
            "actual_crossings": sum(row["actual_crossings"] for row in rows),
            "expected_suppressed": sum(row["expected_suppressed"] for row in rows),
            "actual_suppressed": sum(row["actual_suppressed"] for row in rows), "scenarios": rows, "stages": stages}


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path)
    parser.add_argument("--repetitions", type=int, default=30)
    args = parser.parse_args()
    if args.repetitions < 1:
        parser.error("Repetitions must be positive.")
    report = run_benchmark(args.repetitions)
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(json.dumps(report, indent=2, allow_nan=False) + "\n", encoding="utf-8", newline="\n")
    print(json.dumps({key: value for key, value in report.items() if key != "scenarios"}, indent=2, allow_nan=False))
    if report["expectations_met"] != report["scenario_count"]:
        raise SystemExit(1)
