import json

import pytest

from roadlens.detector import Detection
from roadlens.tracking_benchmark import _evaluate, benchmark_scenarios, run_tracking_benchmark


def test_benchmark_reproduces_identity_counts_and_reports_measured_timing():
    report = run_tracking_benchmark(timing_repetitions=1)
    assert report["provenance"] == "synthetic"
    assert report["baseline"]["frames"] == report["improved"]["frames"] == 352
    assert report["baseline"]["ground_truth_observations"] == 484
    assert report["baseline"]["id_switches"] == 5
    assert report["improved"]["id_switches"] == 1
    assert report["baseline"]["fragments"] == report["improved"]["fragments"] == 3
    assert report["baseline"]["missed_observations"] == report["improved"]["missed_observations"] == 18
    for tracker in ("baseline", "improved"):
        assert report[tracker]["mean_update_ms"] > 0
        assert report[tracker]["p95_update_ms"] > 0
        assert report[tracker]["runtime_ms"] > 0
    assert len(report["improved"]["scenarios"]) == 11
    assert "not implemented" in report["methodology"]["limitations"]
    json.dumps(report, allow_nan=False)


def test_metric_counts_id_change_after_gap_and_fragment_separately():
    class ScriptedTracker:
        total_tracks = 2
        def update(self, detections, timestamp_s):
            return [] if not detections else [{"id": 1 if timestamp_s == 0 else 2,
                                               "bbox": detections[0].bbox, "missed": 0, "state": "confirmed"}]
    box = (0, 0, 40, 30)
    scenario = {"name": "metric_check", "description": "hand calculated", "frames": [
        {"timestamp_s": timestamp, "objects": [{"identity": "a", "bbox": box,
          "detection": None if timestamp == 1 else Detection(box, .9, "car")}]} for timestamp in (0, 1, 2)]}
    result, _ = _evaluate(ScriptedTracker, scenario, 1)
    assert result["ground_truth_observations"] == 3
    assert result["matched_observations"] == 2
    assert result["missed_observations"] == 1
    assert result["id_switches"] == 1
    assert result["fragments"] == 1


def test_scenario_data_covers_timing_occlusion_ambiguity_and_entry_exit():
    scenarios = {row["name"]: row for row in benchmark_scenarios()}
    assert {"constant_motion", "parallel_vehicles", "crossing_paths", "short_occlusion",
            "long_occlusion", "box_jitter", "different_speeds", "irregular_timestamps",
            "ambiguous_overlap", "entry_exit", "greedy_counterexample"} == scenarios.keys()
    intervals = [right["timestamp_s"] - left["timestamp_s"]
                 for left, right in zip(scenarios["irregular_timestamps"]["frames"],
                                        scenarios["irregular_timestamps"]["frames"][1:])]
    assert len({round(value, 3) for value in intervals}) > 1


@pytest.mark.parametrize("repetitions", [0, 21])
def test_benchmark_repetition_work_is_bounded(repetitions):
    with pytest.raises(ValueError):
        run_tracking_benchmark(timing_repetitions=repetitions)
