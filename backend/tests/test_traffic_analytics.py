"""Known source-time arithmetic, bounded exposure and spreadsheet-safe exports."""

import copy
import csv
import io
import json
from uuid import uuid4

import pytest

from roadlens.traffic_analytics import TrafficAnalysisRequest, analyze_traffic, merged_coverage, speed_statistics, traffic_export
from roadlens.traffic_models import TrafficConfiguration
from roadlens.traffic_store import TrafficStore


def artifact():
    sid = str(uuid4())
    config = TrafficConfiguration(source_id="synthetic:analytics", geometry={"width": 200, "height": 120},
        lines=[{"id": "line", "label": "Main", "start": [0, 60], "end": [200, 60]}],
        zones=[{"id": "zone", "label": "Approach", "points": [[0, 0], [200, 0], [200, 120], [0, 120]]}]).model_dump(mode="json")
    def event(index, timestamp, category, direction="positive", status="counted"):
        return {"id": f"event-{index}", "session_id": sid, "source_id": config["source_id"], "track_id": index,
                "timestamp_s": timestamp, "line_id": "line", "line_label": "Main", "direction": direction,
                "direction_label": "down" if direction == "positive" else "up", "category": category,
                "class_score": .9, "class_observations": 5, "status": status, "diagnostic_reasons": [],
                "configuration_id": config["id"], "provenance": "synthetic", "image_position": [50, 60]}
    def speed(index, value, status="valid", calibration="road"):
        return {"id": f"speed-{index}", "session_id": sid, "source_id": config["source_id"], "track_id": index,
                "timestamp_s": index * 5, "category": "car", "direction": "A_to_B", "status": status,
                "estimated_speed_kmh": value, "calibration_id": calibration}
    return {"schema_version": 1, "id": sid, "session_id": sid, "source_id": config["source_id"],
            "name": "SYNTHETIC analytic fixture", "provenance": "synthetic", "configuration": config,
            "configurations": [config], "events": [event(1, 10, "car"), event(2, 30, "bus", "negative"),
            event(3, 80, "car"), event(4, 81, "car", status="suppressed")],
            "coverage": [{"start_s": 0, "end_s": 40, "configuration_id": config["id"]},
                         {"start_s": 70, "end_s": 100, "configuration_id": config["id"]}],
            "zone_events": [{"zone_id": "zone", "configuration_id": config["id"], "kind": "entry", "timestamp_s": 10},
                            {"zone_id": "zone", "configuration_id": config["id"], "kind": "exit", "timestamp_s": 20, "dwell_s": 9}],
            "occupancy_samples": [{"timestamp_s": 80, "configuration_id": config["id"], "visible_tracks": 2,
                                   "zone_occupancy": {"zone": 2}}],
            "measurements": [speed(1, 20), speed(2, 40), speed(3, 60), speed(4, 200, "rejected"),
                             speed(5, 80, "approximate"), speed(6, 99, calibration=None)], "diagnostics": {}}


def test_source_time_exposure_and_incomplete_intervals():
    report = analyze_traffic([artifact()])
    assert report["summary"]["total_crossings"] == 3
    assert report["summary"]["suppressed_events"] == 1
    assert report["summary"]["coverage_seconds"] == 70
    assert report["summary"]["normalized_crossings_per_hour"] == pytest.approx(3 / 70 * 3600)
    assert [(row["count"], row["coverage_seconds"]) for row in report["flow"]] == [(2, 40), (1, 30)]
    assert all(not row["complete_window"] for row in report["flow"])
    assert report["flow"][-1]["cumulative_count"] == 3
    assert {row["category"]: row["count"] for row in report["classes"]} == {"bus": 1, "car": 2}
    assert report["summary"]["current_zone_occupancy"] == 2


def test_overlapping_coverage_is_not_double_counted_and_pauses_not_bridged():
    assert merged_coverage([{"start_s": 0, "end_s": 20}, {"start_s": 10, "end_s": 30},
                            {"start_s": 50, "end_s": 60}]) == [(0, 30), (50, 60)]
    data = artifact()
    data["coverage"] = []
    report = analyze_traffic([data])
    assert report["summary"]["normalized_crossings_per_hour"] is None
    assert report["summary"]["total_crossings"] == 3


@pytest.mark.parametrize("minutes", [1, 5, 15, 30, 60])
def test_supported_intervals_preserve_observed_counts(minutes):
    report = analyze_traffic([artifact()], TrafficAnalysisRequest(interval_minutes=minutes))
    assert sum(row["count"] for row in report["flow"]) == 3
    assert sum(row["coverage_seconds"] for row in report["flow"]) == 70


def test_filters_and_half_open_source_time_window():
    data = artifact()
    report = analyze_traffic([data], TrafficAnalysisRequest(category="car", direction="positive", line_id="line", start_s=10, end_s=80))
    assert report["summary"]["total_crossings"] == 1
    assert report["summary"]["coverage_seconds"] == 40
    assert len(report["events"]) == 1
    assert analyze_traffic([data], TrafficAnalysisRequest(status="suppressed"))["summary"]["total_crossings"] == 0


def test_valid_metric_speeds_only_and_approximate_separate():
    data = artifact()
    speeds = analyze_traffic([data])["speeds"]
    assert speeds["n"] == 3 and speeds["mean_kmh"] == 40
    assert speeds["p85_kmh"] == 54 and speeds["median_kmh"] == 40
    assert speeds["standard_deviation_kmh"] == pytest.approx((800 / 3) ** .5)
    assert sum(row["count"] for row in speeds["distribution"]) == 3
    approximate = analyze_traffic([data], TrafficAnalysisRequest(speed_status="approximate"))
    assert approximate["speeds"]["n"] == 1 and approximate["speeds"]["mean_kmh"] == 80
    assert approximate["summary"]["valid_speed_count"] == 0


def test_empty_statistics_do_not_invent_zero_speed_or_rate():
    report = analyze_traffic([])
    assert report["summary"]["total_crossings"] == 0
    assert report["summary"]["normalized_crossings_per_minute"] is None
    assert report["speeds"]["n"] == 0 and report["speeds"]["p85_kmh"] is None
    assert speed_statistics([35])["standard_deviation_kmh"] == 0


def test_missing_event_timestamps_excluded_with_quality_record():
    data = artifact()
    data["events"][0]["timestamp_s"] = None
    report = analyze_traffic([data])
    assert report["summary"]["total_crossings"] == 2
    assert any(row["code"] == "missing_event_timestamps" for row in report["quality"])


def test_zone_dwell_and_configurations_stay_separate():
    data = artifact()
    other = copy.deepcopy(data["configuration"])
    other["id"] = "another-configuration"
    other["zones"][0]["label"] = "Different meaning"
    data["configurations"].append(other)
    zones = analyze_traffic([data])["zones"]
    assert len(zones) == 2
    assert zones[0]["mean_dwell_s"] == 9 and zones[0]["completed_dwell_count"] == 1
    assert zones[1]["mean_dwell_s"] is None and zones[1]["current_occupancy"] == 0


def test_session_comparison_warns_different_geometry_coverage_and_truncated_data():
    first, second = artifact(), artifact()
    second["configuration"]["lines"][0]["end"] = [190, 60]
    second["diagnostics"]["omitted_events"] = 4
    report = analyze_traffic([first, second])
    assert report["summary"]["total_crossings"] == 6
    assert all(not row["comparable_configuration"] for row in report["comparisons"])
    assert any("retained subset" in row["message"] for row in report["quality"])


@pytest.mark.parametrize("table", ["events", "classes", "flow", "zones", "speeds", "comparisons", "quality"])
def test_export_tables_valid_json_and_csv(table):
    data = artifact()
    data["events"][0]["line_label"] = "=HYPERLINK(unsafe)"
    report = analyze_traffic([data])
    decoded = json.loads(traffic_export(report, table, "json"))
    assert decoded["table"] == table and decoded["evidence_types"] == ["synthetic"]
    rows = list(csv.DictReader(io.StringIO(traffic_export(report, table, "csv"))))
    assert all(row["table"] == table and row["schema_version"] == "1" for row in rows)
    if table == "events":
        assert rows[0]["line_label"].startswith("'=")
        assert json.loads(rows[0]["diagnostic_reasons"]) == []


def test_atomic_store_roundtrip_and_source_geometry_configuration_binding(tmp_path):
    store = TrafficStore(tmp_path)
    data = artifact()
    saved = store.put(data)
    assert store.get(saved["id"]) == saved
    assert store.list()[0]["crossing_count"] == 3
    store.save_configuration(data["configuration"])
    assert store.configuration_for(data["source_id"], data["configuration"]["geometry"]) == data["configuration"]
    assert store.configuration_for("different", data["configuration"]["geometry"]) is None
    store.delete(saved["id"])
    with pytest.raises(KeyError):
        store.get(saved["id"])


@pytest.mark.parametrize("identifier", ["../escape", "C:/outside", "", "not-a-uuid"])
def test_store_rejects_path_traversal(tmp_path, identifier):
    with pytest.raises(KeyError):
        TrafficStore(tmp_path).get(identifier)


def test_store_rejects_nonfinite_and_cross_session_identifiers(tmp_path):
    data = artifact()
    data["events"][0]["timestamp_s"] = float("nan")
    with pytest.raises(ValueError):
        TrafficStore(tmp_path).put(data)
    data = artifact()
    data["session_id"] = str(uuid4())
    with pytest.raises(ValueError):
        TrafficStore(tmp_path).put(data)


def test_lifetime_counters_survive_retained_event_and_coverage_limits():
    data = artifact()
    data["summary"] = {"total_crossings": 12000, "covered_duration_s": 1200,
                       "by_class": {"car": 11000, "truck": 1000}, "by_direction": {"positive": 12000}}
    data["diagnostics"] = {"omitted_events": 11996, "omitted_coverage": 10}
    report = analyze_traffic([data])
    assert report["summary"]["total_crossings"] == 12000
    assert report["summary"]["retained_counted_events"] == 3
    assert report["summary"]["count_scope"] == "lifetime"
    assert report["summary"]["normalized_crossings_per_hour"] == 36000
    assert report["summary"]["incomplete_retained_data"]
    assert sum(row["count"] for row in report["classes"]) == 12000
    assert all(row["normalized_crossings_per_hour"] is None for row in report["flow"])
    filtered = analyze_traffic([data], TrafficAnalysisRequest(category="car"))
    assert filtered["summary"]["total_crossings"] == 2
    assert filtered["summary"]["count_scope"] == "retained_filtered"
    assert filtered["summary"]["normalized_crossings_per_hour"] is None


def test_empty_export_retains_filters_units_and_no_fake_data_rows():
    report = analyze_traffic([], TrafficAnalysisRequest(category="car", interval_minutes=5))
    json_export = json.loads(traffic_export(report, "events"))
    assert json_export["filters"]["category"] == "car"
    assert json_export["units"]["speed"] == "km/h" and json_export["rows"] == []
    csv_export = list(csv.DictReader(io.StringIO(traffic_export(report, "events", "csv"))))
    assert len(csv_export) == 1 and csv_export[0]["export_row_type"] == "metadata"
    assert json.loads(csv_export[0]["filters_json"])["interval_minutes"] == 5
    assert json.loads(csv_export[0]["units_json"])["coverage_seconds"] == "seconds"


def test_calendar_filters_use_start_metadata_without_changing_source_exposure():
    first, second, unknown = artifact(), artifact(), artifact()
    first["started_at"] = "2026-10-24T09:00:00+03:00"
    second["started_at"] = "2026-10-25T09:00:00+03:00"
    request = TrafficAnalysisRequest(observation_started_after="2026-10-24T00:00:00+03:00",
                                     observation_started_before="2026-10-24T23:59:59+03:00")
    report = analyze_traffic([first, second, unknown], request)
    assert report["summary"]["total_crossings"] == 3
    assert report["summary"]["coverage_seconds"] == 70
    assert report["selected_session_ids"] == [first["id"]]
    assert any(row["code"] == "missing_observation_date" for row in report["quality"])
    with pytest.raises(ValueError, match="timezone"):
        TrafficAnalysisRequest(observation_started_after="2026-10-24T00:00:00")


def test_line_filter_uses_only_coverage_where_line_is_configured():
    data = artifact()
    old = copy.deepcopy(data["configuration"])
    old.update(id="old-config", lines=[])
    data["configurations"].append(old)
    data["coverage"].append({"start_s": 100, "end_s": 200, "configuration_id": old["id"]})
    report = analyze_traffic([data], TrafficAnalysisRequest(line_id="line"))
    assert report["summary"]["coverage_seconds"] == 70


def test_counting_direction_speed_filter_requires_unique_measurement_link():
    data = artifact()
    data["events"][0]["speed_measurement_id"] = data["measurements"][0]["id"]
    report = analyze_traffic([data], TrafficAnalysisRequest(direction="positive"))
    assert report["speeds"]["n"] == 1 and report["speeds"]["mean_kmh"] == 20


def late_counting_configuration():
    data = artifact()
    active = data["configuration"]
    empty = copy.deepcopy(active)
    empty.update(id="initial-without-lines", lines=[])
    data["configurations"] = [empty, active]
    data["coverage"] = [{"start_s": 0, "end_s": 10, "configuration_id": empty["id"]},
                        {"start_s": 10, "end_s": 20, "configuration_id": active["id"]}]
    data["events"] = [{**data["events"][0], "timestamp_s": 15}]
    data["summary"] = {"total_crossings": 1, "covered_duration_s": 20,
                       "covered_counting_duration_s": 10, "by_class": {"car": 1}, "by_direction": {"positive": 1}}
    return data


def test_initial_unconfigured_time_is_not_zero_traffic_counting_exposure():
    data = late_counting_configuration()
    report = analyze_traffic([data])
    assert report["summary"]["total_crossings"] == 1
    assert report["summary"]["coverage_seconds"] == 10
    assert report["summary"]["source_coverage_seconds"] == 20
    assert report["summary"]["unconfigured_source_coverage_seconds"] == 10
    assert report["summary"]["normalized_crossings_per_minute"] == 6
    assert report["comparisons"][0]["normalized_crossings_per_minute"] == 6
    assert len(report["flow"]) == 1 and report["flow"][0]["coverage_seconds"] == 10
    assert report["flow"][0]["normalized_crossings_per_minute"] == 6
    assert any(row["code"] == "unconfigured_counting_coverage_seconds" for row in report["quality"])


def test_legacy_mixed_configurations_reconstruct_counting_exposure_from_complete_spans():
    data = late_counting_configuration()
    del data["summary"]["covered_counting_duration_s"]
    report = analyze_traffic([data])
    assert report["summary"]["coverage_seconds"] == 10
    assert report["summary"]["normalized_crossings_per_minute"] == 6


def test_legacy_mixed_configuration_coverage_cannot_normalize_after_truncation():
    data = late_counting_configuration()
    del data["summary"]["covered_counting_duration_s"]
    data["diagnostics"]["omitted_coverage"] = 2
    report = analyze_traffic([data])
    assert report["summary"]["total_crossings"] == 1
    assert report["summary"]["normalized_crossings_per_minute"] is None
    assert report["comparisons"][0]["normalized_crossings_per_hour"] is None


def test_explicit_lifetime_counting_counter_preserves_rate_with_bounded_history():
    data = late_counting_configuration()
    data["configurations"] = [data["configuration"]]
    data["diagnostics"]["omitted_configurations"] = 1
    data["diagnostics"]["omitted_coverage"] = 1
    report = analyze_traffic([data])
    assert report["summary"]["normalized_crossings_per_minute"] == 6
    assert report["summary"]["coverage_seconds"] == 10
    assert report["summary"]["unknown_configuration_coverage_seconds"] == 10


def test_unknown_configuration_coverage_withholds_legacy_rate():
    data = artifact()
    data["coverage"].append({"start_s": 100, "end_s": 200, "configuration_id": "missing-history"})
    data["summary"] = {"total_crossings": 3, "covered_duration_s": 170}
    report = analyze_traffic([data])
    assert report["summary"]["coverage_seconds"] == 70
    assert report["summary"]["normalized_crossings_per_hour"] is None
    assert report["summary"]["unknown_configuration_coverage_seconds"] == 100


def test_counting_coverage_does_not_disable_occupancy_or_speed_evidence():
    data = artifact()
    data["configuration"]["lines"] = []
    data["events"] = []
    report = analyze_traffic([data])
    assert report["summary"]["coverage_seconds"] == 0
    assert report["summary"]["source_coverage_seconds"] == 70
    assert report["summary"]["normalized_crossings_per_minute"] is None
    assert report["flow"] == []
    assert report["summary"]["current_zone_occupancy"] == 2
    assert report["zones"][0]["completed_dwell_count"] == 1
    assert report["speeds"]["n"] == 3
