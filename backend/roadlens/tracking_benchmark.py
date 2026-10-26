"""Deterministic synthetic tracking evaluation, deliberately without inference.

Ground-truth boxes and identities are generated independently of tracker output.
This tiny suite tests software behavior; it is not a real traffic accuracy study.
"""

from collections import defaultdict
from datetime import datetime, timezone
import os
import platform
from statistics import mean
from time import perf_counter_ns

from .assignment import maximum_score_matching
from .detector import Detection
from .tracker_baseline import IoUTracker as BaselineTracker
from .tracker_baseline import intersection_over_union


def _object(identity: str, x: float, y: float = 10, jitter: float = 0, detected: bool = True) -> dict:
    bbox = (x, y, x + 40, y + 30)
    return {"identity": identity, "bbox": bbox, "detection": Detection(
        (x + jitter, y + jitter / 2, x + 40 + jitter, y + 30 + jitter / 2), 0.9, "car"
    ) if detected else None}


def benchmark_scenarios() -> list[dict]:
    """Versioned, fully specified deterministic motions and detector omissions."""
    scenarios = []
    def add(name, description, build, timestamps=None, frames=35):
        times = timestamps if timestamps is not None else [frame / 10 for frame in range(frames)]
        scenarios.append({"name": name, "description": description,
                          "frames": [{"timestamp_s": time, "objects": build(index, time)}
                                     for index, time in enumerate(times)]})
    add("constant_motion", "One box at a constant 40 pixels/source-second.",
        lambda i, t: [_object("a", 40 * t)])
    add("parallel_vehicles", "Two nearby same-class vehicles with equal motion and distinct boxes.",
        lambda i, t: [_object("a", 40 * t), _object("b", 55 + 40 * t)])
    add("crossing_paths", "Opposing vehicles cross with an 8-pixel vertical offset; no exact duplicate boxes.",
        lambda i, t: [_object("a", 70 * t, 10), _object("b", 241 - 70 * t, 18)])
    add("short_occlusion", "One vehicle has four missing detections, shorter than the one-second TTL.",
        lambda i, t: [_object("a", 50 * t, detected=not 12 <= i <= 15)])
    add("long_occlusion", "Twelve missing detections exceed TTL; a new ID is expected on return.",
        lambda i, t: [_object("a", 35 * t, detected=not 10 <= i <= 21)])
    jitter = (0, 5, -4, 3, -5, 1, 4, -2)
    add("box_jitter", "Deterministic contact-point jitter up to five pixels around true motion.",
        lambda i, t: [_object("a", 30 * t, jitter=jitter[i % len(jitter)])])
    add("different_speeds", "A faster vehicle overtakes a slower vehicle with a small lane offset.",
        lambda i, t: [_object("a", 18 * t, 10), _object("b", -70 + 85 * t, 20)])
    times, elapsed = [], 0.0
    for interval in [0.04, 0.11, 0.23, 0.07, 0.16] * 7:
        times.append(elapsed)
        elapsed += interval
    add("irregular_timestamps", "Constant motion sampled at irregular source intervals; no FPS substitution.",
        lambda i, t: [_object("a", 45 * t)], timestamps=times)
    add("ambiguous_overlap", "Closely overlapping opposing boxes with intermittent detections and jitter.",
        lambda i, t: [_object("a", 30 * t, 10, jitter=(2 if i % 2 else -2)),
                      _object("b", 103 - 30 * t, 12, detected=i not in (15, 16))])
    add("entry_exit", "Distinct objects enter and exit; absence is not treated as a continuing identity.",
        lambda i, t: ([_object("a", 30 * t)] if i < 12 else []) +
                      ([_object("b", 180 + 25 * (t - 1.7))] if 17 <= i < 30 else []))
    add("greedy_counterexample", "Two feasible matches exist, but the original best-edge-first strategy loses one.",
        lambda i, t: [_object("a", (0, -30)[i]), _object("b", (50, 20)[i])], frames=2)
    return scenarios


def _percentile(values: list[float], fraction: float) -> float:
    ordered = sorted(values)
    if not ordered:
        return 0.0
    index = (len(ordered) - 1) * fraction
    left = int(index)
    return ordered[left] + (ordered[min(left + 1, len(ordered) - 1)] - ordered[left]) * (index - left)


def _evaluate(factory, scenario: dict, timing_repetitions: int) -> tuple[dict, list[float]]:
    tracker = factory()
    previous_identity, ever_matched = {}, set()
    previously_visible = defaultdict(bool)
    switches = fragments = matched = truth_count = 0
    continuity = []
    observed_ids = set()
    for frame in scenario["frames"]:
        objects = frame["objects"]
        detections = [obj["detection"] for obj in objects if obj["detection"] is not None]
        tracks = tracker.update(detections, frame["timestamp_s"])
        observed = [track for track in tracks if not track["missed"]]
        observed_ids.update(track["id"] for track in observed)
        scores = {(i, j): intersection_over_union(obj["bbox"], track["bbox"])
                  for i, obj in enumerate(objects) for j, track in enumerate(observed)
                  if intersection_over_union(obj["bbox"], track["bbox"]) >= 0.5}
        assignments = maximum_score_matching(len(objects), len(observed), scores)
        current = {objects[i]["identity"]: observed[j]["id"] for i, j in assignments}
        for obj in objects:
            identity = obj["identity"]
            if identity in current:
                assigned = current[identity]
                if identity in previous_identity and previous_identity[identity] != assigned:
                    switches += 1
                if identity in ever_matched and not previously_visible[identity]:
                    fragments += 1
                previous_identity[identity] = assigned
                ever_matched.add(identity)
            previously_visible[identity] = identity in current
        matched += len(current)
        truth_count += len(objects)
        continuity.append({"timestamp_s": frame["timestamp_s"], "ground_truth_count": len(objects),
                           "observed_tracks": len(observed), "active_tracks": len(observed),
                           "lost_tracks": sum(track["state"] == "lost" for track in tracks)})
    times = []
    for _ in range(timing_repetitions):
        timed = factory()
        for frame in scenario["frames"]:
            detections = [obj["detection"] for obj in frame["objects"] if obj["detection"] is not None]
            start = perf_counter_ns()
            timed.update(detections, frame["timestamp_s"])
            times.append((perf_counter_ns() - start) / 1_000_000)
    diagnostics = getattr(tracker, "diagnostics", {})
    result = {"name": scenario["name"], "description": scenario["description"],
              "frames": len(scenario["frames"]), "ground_truth_observations": truth_count,
              "matched_observations": matched, "missed_observations": truth_count - matched,
              "id_switches": switches, "fragments": fragments, "created_tracks": len(observed_ids),
              "confirmed_tracks": tracker.total_tracks,
              "potential_id_switches": diagnostics.get("potential_id_switches", 0),
              "fragmentation_suspicions": diagnostics.get("fragmentation_suspicions", 0),
              "mean_update_ms": mean(times), "p95_update_ms": _percentile(times, .95),
              "runtime_ms": sum(times), "continuity": continuity}
    return result, times


def _run(factory, name: str, scenarios: list[dict], repetitions: int) -> dict:
    # Warm up Python code and allocations equally before measuring either tracker.
    warm = factory()
    for index in range(8):
        warm.update([Detection((index, 10, index + 40, 40), .9, "car")], index / 10)
    reports, times = [], []
    for scenario in scenarios:
        result, measured = _evaluate(factory, scenario, repetitions)
        reports.append(result)
        times.extend(measured)
    summed = ("frames", "ground_truth_observations", "matched_observations", "missed_observations",
              "id_switches", "fragments", "created_tracks", "confirmed_tracks", "potential_id_switches",
              "fragmentation_suspicions")
    return {"name": name, **{key: sum(row[key] for row in reports) for key in summed},
            "mean_update_ms": mean(times), "p95_update_ms": _percentile(times, .95),
            "runtime_ms": sum(times), "scenarios": reports}


def run_tracking_benchmark(*, baseline_only: bool = False, timing_repetitions: int = 5) -> dict:
    """Run the bounded fixed suite. Timings are actual local measurements, not SLA."""
    if not 1 <= timing_repetitions <= 20:
        raise ValueError("Timing repetitions must be between one and twenty.")
    scenarios = benchmark_scenarios()
    report = {
        "schema_version": 1, "provenance": "synthetic", "suite_version": "1.0",
        "generated_at_utc": datetime.now(timezone.utc).isoformat(),
        "hardware": {"os": platform.platform(), "cpu": platform.processor() or "unreported",
                     "logical_cpus": os.cpu_count(), "python": platform.python_version()},
        "methodology": {
            "matching": "Per-frame global maximum-cardinality, maximum-IoU assignment of currently observed tracker boxes to independently generated truth boxes; IoU >= 0.5. Lost tracks are not observations.",
            "identity_switches": "A truth identity receives a different tracker ID from its last matched observation, including after a gap. Counts are ground-truth based, unlike live potential_id_switches.",
            "fragmentations": "A previously matched truth identity becomes unmatched and later matched again while still in the scenario. Expected missing detections count too.",
            "timing": f"Source sequences identical; one untimed evaluation plus {timing_repetitions} timing repetitions per tracker, after eight warm-up updates. perf_counter_ns brackets update() only; excludes detection, evaluation, rendering and HTTP. Mean/P95 pool update durations; P95 uses linear interpolation. Baseline runs first; thermal/scheduler/order effects remain.",
            "limitations": "Synthetic boxes and scripted omissions only; no detector, physical camera, labeled real footage, appearance re-identification or real-world accuracy claim. IDF1 is not implemented. Baseline suspicion counters are unavailable and reported as zero. Long-occlusion ID replacement is expected. Ambiguous synthetic overlap can remain unresolved even with a stable ID."
        },
        "baseline": _run(BaselineTracker, "Phase 2 greedy motion + IoU", scenarios, timing_repetitions),
    }
    if not baseline_only:
        from .tracker import IoUTracker
        report["improved"] = _run(IoUTracker, "Global assignment + motion diagnostics", scenarios, timing_repetitions)
    return report
