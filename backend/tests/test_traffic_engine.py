"""Deterministic tracker hypotheses, not physical-camera accuracy evidence."""

import json

import numpy as np
import pytest
from pydantic import ValidationError

from roadlens.calibration_models import ImageGeometry
from roadlens.detector import VEHICLE_CLASSES
from roadlens.traffic_engine import TrafficEngine
from roadlens.traffic_geometry import polygon_box_area, polygon_membership, segment_crossing
from roadlens.traffic_models import CountingLine, MonitoringZone, TrafficConfiguration, TrafficEvent


def configuration(**changes):
    values = dict(id="config-1", source_id="video:fixture", geometry={"width": 200, "height": 100},
                  lines=[{"id": "line-1", "label": "North approach", "start": [0, 50], "end": [200, 50]}])
    values.update(changes)
    return TrafficConfiguration.model_validate(values)


def engine(**changes):
    config = configuration(**changes)
    return TrafficEngine("observation-1", config.source_id, config.geometry, config, provenance="synthetic")


def vehicle(identity=1, x=50, y=25, category="car", confidence=.9, **extra):
    return dict(id=identity, category=category, confidence=confidence, bbox=(x - 3, y - 8, x + 3, y),
                image_position=(x, y), hits=5, state="confirmed", missed=0, **extra)


def cross(traffic, identity=1, x=50, start=.0, reverse=False, **extra):
    for offset, y in enumerate((75, 65, 25) if reverse else (25, 35, 75)):
        traffic.update([vehicle(identity, x, y, **extra)], start + offset * .1)


def events(traffic, status="counted"):
    return [event for event in traffic.snapshot()["events"] if event["status"] == status]


def test_single_crossing_preserves_interpolated_source_timestamp_and_metadata():
    traffic = engine()
    cross(traffic)
    event = events(traffic)[0]
    assert event["timestamp_s"] == pytest.approx(.1375)
    assert event["image_position"] == [50, 50]
    assert event["session_id"] == "observation-1"
    assert event["source_id"] == "video:fixture"
    assert event["track_id"] == 1
    assert event["configuration_id"] == "config-1"
    assert event["line_id"] == "line-1"
    assert event["direction"] == "positive"
    assert event["category"] == "car"
    assert event["class_observations"] == 3
    assert event["class_score"] == pytest.approx(.9)
    assert event["raw_category"] == "car"
    assert event["raw_confidence"] == .9
    assert event["class_evidence"] == pytest.approx({"car": 2.7})
    assert event["provenance"] == "synthetic"
    assert "temporary_track_identity_unverified" in event["diagnostic_reasons"]
    assert traffic.snapshot()["summary"]["total_crossings"] == 1


def test_multiple_simultaneous_vehicles_are_separate_counts():
    traffic = engine()
    for index, y in enumerate((25, 35, 75)):
        traffic.update([vehicle(1, 50, y), vehicle(2, 55, y)], index * .1)
    assert len(events(traffic)) == 2
    assert not events(traffic, "suppressed")
    assert traffic.snapshot()["summary"]["by_class"]["car"] == 2


def test_bidirectional_crossings_and_once_per_track_direction():
    traffic = engine()
    cross(traffic)
    traffic.update([vehicle(y=25)], .3)
    traffic.update([vehicle(y=75)], .4)
    traffic.update([vehicle(y=25)], .5)
    assert [event["direction"] for event in events(traffic)] == ["positive", "negative"]
    assert traffic.snapshot()["diagnostics"]["repeat_track_crossings_ignored"] == 2


def test_line_hysteresis_ignores_boundary_jitter():
    traffic = engine()
    for index, y in enumerate((25, 49, 51, 48, 52, 50, 49)):
        traffic.update([vehicle(y=y)], index * .05)
    assert events(traffic) == []
    traffic.update([vehicle(y=60)], .4)
    assert len(events(traffic)) == 1


def test_crossing_extension_outside_finite_segment_is_not_counted():
    traffic = engine(lines=[{"id": "short", "start": [20, 50], "end": [80, 50]}])
    cross(traffic, x=100)
    assert events(traffic) == []


def test_crossing_at_segment_endpoint_is_included():
    traffic = engine(lines=[{"id": "short", "start": [20, 50], "end": [80, 50]}])
    cross(traffic, x=80)
    assert len(events(traffic)) == 1


def test_multiple_independent_counting_lines():
    traffic = engine(lines=[{"id": "first", "start": [0, 40], "end": [200, 40]},
                            {"id": "second", "start": [0, 60], "end": [200, 60]}])
    cross(traffic)
    assert {event["line_id"] for event in events(traffic)} == {"first", "second"}
    assert traffic.snapshot()["summary"]["total_crossings"] == 2


def test_short_occlusion_can_bridge_crossing_with_original_identity():
    traffic = engine(class_min_observations=2)
    traffic.update([vehicle(y=25)], 0)
    traffic.update([vehicle(y=25, missed_override=1) | {"missed": 1, "state": "lost"}], .2)
    traffic.update([vehicle(y=75)], .8)
    event = events(traffic)[0]
    assert event["timestamp_s"] == pytest.approx(.4)
    assert "crossing_interpolated_across_short_observation_gap" in event["diagnostic_reasons"]


def test_track_loss_beyond_gap_does_not_invent_crossing():
    traffic = engine(max_gap_s=.3)
    traffic.update([vehicle(y=25)], 0)
    traffic.update([], .1)
    traffic.update([], .2)
    traffic.update([vehicle(y=75)], .5)
    assert events(traffic) == []
    assert traffic.snapshot()["coverage"][0]["end_s"] == .5


def test_isolated_repeated_crossing_after_identity_change_is_flagged_and_suppressed():
    traffic = engine()
    cross(traffic)
    cross(traffic, identity=2, start=.3)
    assert len(events(traffic)) == 1
    suppressed = events(traffic, "suppressed")[0]
    assert suppressed["track_id"] == 2
    assert "possible_identity_fragment_duplicate_suppressed" in suppressed["diagnostic_reasons"]
    assert "spatial_time_suppression_is_heuristic" in suppressed["diagnostic_reasons"]
    assert traffic.snapshot()["summary"]["suppressed_crossings"] == 1


def test_simultaneous_old_and_new_ids_prevent_fragment_suppression():
    traffic = engine()
    cross(traffic)
    for index, y in enumerate((25, 35, 75)):
        traffic.update([vehicle(1, 50, 75), vehicle(2, 50, y)], .3 + index * .1)
    assert len(events(traffic)) == 2


def test_preexisting_vehicle_does_not_become_fragment_of_prior_event():
    traffic = engine()
    for index, (y1, y2) in enumerate(((25, 25), (75, 30), (75, 75))):
        traffic.update([vehicle(1, 50, y1), vehicle(2, 50, y2)], index * .1)
    assert len(events(traffic)) == 2


def test_two_fragment_candidates_are_not_automatically_suppressed():
    traffic = engine()
    cross(traffic)
    for index, y in enumerate((25, 35, 75)):
        traffic.update([vehicle(2, 50, y), vehicle(3, 52, y)], .3 + index * .1)
    assert len(events(traffic)) == 3
    assert not events(traffic, "suppressed")
    assert traffic.snapshot()["diagnostics"]["ambiguous_fragment_crossings"] == 2


def test_classifications_use_loaded_model_categories_and_weighted_evidence():
    assert set(VEHICLE_CLASSES.values()) == {"car", "truck", "bus", "motorcycle"}
    traffic = engine()
    for index, category in enumerate(("car", "truck", "car", "car", "car")):
        traffic.update([vehicle(category=category)], index * .1)
    classification = traffic.snapshot()["classifications"][1]
    assert classification["category"] == "car"
    assert classification["score"] == pytest.approx(.72)
    assert classification["observations"] == 5
    assert classification["weighted_evidence"] == pytest.approx({"car": 3.6, "truck": .9})


@pytest.mark.parametrize("category,confidence", [("bicycle", .99), ("car", .2), ("unknown", 1)])
def test_unsupported_or_low_confidence_classes_stay_unknown(category, confidence):
    traffic = engine()
    cross(traffic, category=category, confidence=confidence)
    assert events(traffic)[0]["category"] == "unknown"
    assert traffic.snapshot()["summary"]["by_class"]["unknown"] == 1


def test_conflicting_classes_remain_uncertain_instead_of_flipping():
    traffic = engine(class_min_confidence=.4)
    for index, category in enumerate(("car", "truck", "car", "truck", "car", "truck")):
        traffic.update([vehicle(category=category)], index * .1)
    assert traffic.overlay_state()["tracks"][1]["category"] == "unknown"


def test_tentative_track_crossing_does_not_count():
    traffic = engine()
    traffic.update([vehicle(y=25) | {"hits": 1, "state": "tentative"}], 0)
    traffic.update([vehicle(y=75) | {"hits": 2, "state": "tentative"}], .1)
    traffic.update([vehicle(y=80)], .2)
    assert not events(traffic)
    assert traffic.snapshot()["diagnostics"]["tentative_crossings_not_counted"] == 1


def zone_config(**changes):
    return dict(lines=[], zones=[{"id": "waiting", "label": "Waiting area", "points": [(20, 20), (80, 20), (80, 80), (20, 80)],
                                 "hysteresis": 3}], **changes)


def test_zone_entry_exit_occupancy_and_observed_dwell():
    traffic = engine(**zone_config())
    for index, x in enumerate((10, 30, 35, 40, 90)):
        traffic.update([vehicle(x=x, y=50)], index * .2)
    snapshot = traffic.snapshot()
    assert [event["kind"] for event in snapshot["zone_events"]] == ["entry", "exit"]
    assert snapshot["zone_events"][1]["dwell_s"] == pytest.approx(.4)
    assert snapshot["summary"]["zone_occupancy"] == {"waiting": 0}
    assert snapshot["summary"]["zone_summaries"][0]["completed_dwell_n"] == 1


def test_zone_boundary_jitter_does_not_alternate_entries_and_exits():
    traffic = engine(**zone_config())
    for index, x in enumerate((10, 30, 21, 19, 20, 22, 19, 30)):
        traffic.update([vehicle(x=x, y=50)], index * .1)
    assert [event["kind"] for event in traffic.snapshot()["zone_events"]] == ["entry"]
    assert traffic.overlay_state()["zone_occupancy"]["waiting"] == 1


def test_short_invisible_intervals_are_not_added_to_zone_dwell():
    traffic = engine(**zone_config())
    traffic.update([vehicle(x=40, y=50)], 0)
    traffic.update([], .2)
    assert traffic.overlay_state()["zone_occupancy"]["waiting"] == 0
    traffic.update([vehicle(x=40, y=50)], .4)
    traffic.update([vehicle(x=40, y=50)], .6)
    traffic.update([vehicle(x=90, y=50)], .8)
    exit_event = traffic.snapshot()["zone_events"][-1]
    assert exit_event["dwell_s"] == pytest.approx(.2)


def test_overlapping_zones_maintain_independent_occupancy():
    traffic = engine(lines=[], zones=[
        {"id": "a", "points": [(20, 20), (80, 20), (80, 80), (20, 80)]},
        {"id": "b", "points": [(40, 20), (100, 20), (100, 80), (40, 80)]}])
    traffic.update([vehicle(x=50, y=50)], 0)
    assert traffic.overlay_state()["zone_occupancy"] == {"a": 1, "b": 1}
    assert len(traffic.snapshot()["zone_events"]) == 2


def test_ground_zone_requires_real_ground_positions_and_has_no_image_proxy():
    traffic = engine(lines=[], calibration_id="road-1", zones=[
        {"id": "ground", "coordinate_space": "ground", "hysteresis": .1,
         "points": [(0, 0), (10, 0), (10, 10), (0, 10)]}])
    traffic.update([vehicle(x=50, y=50)], 0)
    assert not traffic.snapshot()["zone_events"]
    traffic.update([vehicle(x=50, y=50, world_position=(5, 5))], .1)
    assert traffic.overlay_state()["zone_occupancy"]["ground"] == 1
    assert traffic.overlay_state()["zone_occupancy_proxy"]["ground"] is None
    traffic.update([vehicle()], .2)
    assert traffic.snapshot()["zone_events"][-1]["kind"] == "interrupted"


def test_pause_interrupt_breaks_trajectory_and_incomplete_dwell():
    traffic = engine(**(zone_config() | {"lines": configuration().lines}))
    traffic.update([vehicle(y=30)], 0)
    traffic.interrupt("paused")
    traffic.update([vehicle(y=70)], .1)
    assert not events(traffic)
    assert len(traffic.snapshot()["coverage"]) == 2
    assert traffic.snapshot()["zone_events"][1]["kind"] == "interrupted"
    assert traffic.snapshot()["summary"]["covered_duration_s"] == 0


def test_source_gap_is_not_added_to_coverage_or_crossing_interpolation():
    traffic = engine()
    traffic.update([vehicle(y=25)], 0)
    traffic.update([vehicle(y=30)], .1)
    traffic.update([vehicle(y=75)], 5)
    traffic.update([vehicle(y=80)], 5.1)
    snapshot = traffic.snapshot()
    assert not events(traffic)
    assert snapshot["summary"]["covered_duration_s"] == pytest.approx(.2)
    assert [(row["start_s"], row["end_s"]) for row in snapshot["coverage"]] == [(0, .1), (5, 5.1)]


@pytest.mark.parametrize("timestamp", [None, float("nan"), float("inf"), -1, True])
def test_missing_or_invalid_source_timestamp_disables_counting_and_coverage(timestamp):
    traffic = engine()
    traffic.update([vehicle(y=25)], 0)
    traffic.update([vehicle(y=75)], timestamp)
    assert not events(traffic)
    assert traffic.snapshot()["diagnostics"]["invalid_timestamp_frames"] == 1
    assert traffic.snapshot()["summary"]["covered_duration_s"] == 0
    json.dumps(traffic.snapshot(), allow_nan=False)


def test_invalid_timing_flag_and_nonmonotonic_pts_never_create_coverage():
    traffic = engine()
    traffic.update([vehicle(y=25)], 1)
    traffic.update([vehicle(y=75)], 1.1, timing_valid=False)
    traffic.update([vehicle(y=25)], .5)
    traffic.update([vehicle(y=75)], 1)
    traffic.update([vehicle(y=75)], 1.2)
    assert not events(traffic)
    assert traffic.snapshot()["diagnostics"]["invalid_timestamp_frames"] == 3


def test_dropped_frame_indices_are_explicit_but_source_time_is_preserved():
    traffic = engine()
    traffic.update([vehicle(y=25)], 0, frame_index=1)
    traffic.update([vehicle(y=75)], .5, frame_index=6)
    assert events(traffic)[0]["timestamp_s"] == .25
    assert traffic.snapshot()["diagnostics"]["skipped_source_frames"] == 4
    assert traffic.snapshot()["summary"]["covered_duration_s"] == .5


def test_configuration_edits_segment_coverage_preserve_events_and_rotate_reused_id():
    traffic = engine()
    cross(traffic)
    old_event = events(traffic)[0]
    updated = configuration(name="Edited line", lines=[{"id": "line-1", "start": [0, 55], "end": [200, 55]}])
    traffic.configure(updated)
    assert traffic.configuration.id != "config-1"
    traffic.update([vehicle(y=25)], .3)
    traffic.update([vehicle(y=75)], .4)
    snapshot = traffic.snapshot()
    assert len(snapshot["configurations"]) == 2
    assert len(events(traffic)) == 2
    assert events(traffic)[0] == old_event
    assert snapshot["coverage"][0]["configuration_id"] == "config-1"
    assert snapshot["coverage"][1]["configuration_id"] == traffic.configuration.id


def test_geometry_change_clears_manual_definitions_preserves_prior_ledger():
    traffic = engine()
    cross(traffic)
    traffic.change_geometry(ImageGeometry(width=400, height=200))
    assert traffic.configuration.lines == []
    assert traffic.configuration.zones == []
    assert traffic.configuration.geometry.width == 400
    assert len(events(traffic)) == 1
    assert traffic.snapshot()["configurations"][0]["geometry"]["width"] == 200
    assert traffic.snapshot()["summary"]["total_crossings"] == 1


def test_incompatible_source_or_pixel_space_is_rejected_without_mutation():
    traffic = engine()
    for change in ({"source_id": "other"}, {"geometry": {"width": 400, "height": 200}},
                   {"geometry": {"width": 200, "height": 100, "coordinate_space": "undistorted", "intrinsic_profile_id": "lens"}}):
        with pytest.raises(ValueError, match="source and complete pixel geometry"):
            traffic.configure(configuration(**change))
    assert traffic.configuration.id == "config-1"


def test_session_isolation_and_snapshot_is_not_mutable_engine_state():
    first, second = engine(), engine()
    cross(first)
    result = first.snapshot()
    result["events"][0]["category"] = "truck"
    result["coverage"][0]["end_s"] = 1000
    assert events(first)[0]["category"] == "car"
    assert first.snapshot()["coverage"][0]["end_s"] == .2
    assert not events(second)


def test_uncalibrated_pixel_stationarity_never_creates_metric_speed():
    traffic = engine(stationary_window_s=1)
    for index in range(6):
        traffic.update([vehicle(estimated_speed_kmh=3)], index * .25)
    current = traffic.overlay_state()
    assert current["stationary_tracks"] == 1
    assert current["slow_tracks"] is None
    assert "speed_kmh" not in current["tracks"][1]


def test_only_explicit_valid_metric_speed_can_enter_current_slow_indicator():
    traffic = engine()
    traffic.update([vehicle(1, speed_status="valid", estimated_speed_kmh=4),
                    vehicle(2, speed_status="approximate", estimated_speed_kmh=1),
                    vehicle(3, speed_status="rejected", estimated_speed_kmh=0)], 0)
    assert traffic.overlay_state()["slow_tracks"] == 1
    cross(traffic, identity=4, start=.1, speed_status="valid", estimated_speed_kmh=40)
    assert events(traffic)[0]["measured_speed_kmh"] == 40


def test_image_proxy_is_explicit_capped_box_area_fraction():
    traffic = engine(**zone_config())
    traffic.update([vehicle(x=50, y=50)], 0)
    assert traffic.overlay_state()["zone_occupancy_proxy"]["waiting"] == pytest.approx(48 / 3600)
    assert polygon_box_area([(0, 0), (10, 0), (10, 10), (0, 10)], (5, 5, 15, 15)) == 25


def test_retained_event_caps_do_not_change_lifetime_counts():
    traffic = engine(identity_suppression_s=0)
    traffic.EVENT_LIMIT = 2
    traffic._events = __import__("collections").deque(maxlen=2)
    for identity in range(1, 6):
        cross(traffic, identity, start=(identity - 1) * 2)
    assert len(events(traffic)) == 2
    assert traffic.snapshot()["summary"]["total_crossings"] == 5
    assert traffic.snapshot()["diagnostics"]["omitted_events"] == 3


def test_bounded_samples_coverage_and_configuration_retention_are_reported():
    traffic = engine()
    traffic._samples = __import__("collections").deque(maxlen=2)
    traffic._coverage = __import__("collections").deque(maxlen=2)
    traffic._configurations = __import__("collections").deque(traffic._configurations, maxlen=2)
    for index in range(4):
        traffic.update([], index * 2)
        traffic.configure(configuration(id=f"config-{index + 2}"))
    snapshot = traffic.snapshot()
    assert len(snapshot["occupancy_samples"]) == 2
    assert len(snapshot["coverage"]) == 2
    assert snapshot["diagnostics"]["omitted_occupancy_samples"] == 2
    assert snapshot["diagnostics"]["omitted_coverage"] == 2
    assert snapshot["diagnostics"]["omitted_configurations"] == 3


def test_invalid_and_duplicate_track_observations_are_diagnosed():
    traffic = engine()
    traffic.update([vehicle(), vehicle(), vehicle(2, x=float("nan")), None], 0)
    assert traffic.overlay_state()["visible_tracks"] == 1
    assert traffic.snapshot()["diagnostics"]["duplicate_track_observations"] == 1
    assert traffic.snapshot()["diagnostics"]["invalid_track_observations"] == 2


def test_public_event_model_rejects_unknown_status_and_nonfinite_timestamp():
    traffic = engine()
    cross(traffic)
    payload = events(traffic)[0]
    for change in ({"timestamp_s": float("nan")}, {"status": "validated"}, {"category": "van"}):
        with pytest.raises(ValidationError):
            TrafficEvent.model_validate(payload | change)


@pytest.mark.parametrize("change", [
    {"lines": [{"start": [50, 50], "end": [50, 50]}]},
    {"lines": [{"start": [-1, 0], "end": [50, 50]}]},
    {"lines": [{"start": [0, 0], "end": [300, 50]}]},
    {"lines": [{"start": [0, 0], "end": [float("inf"), 50]}]},
    {"max_gap_s": 0}, {"max_gap_s": float("nan")}, {"occupancy_moderate": 8},
    {"zones": [{"points": [(0, 0), (50, 50), (0, 50), (50, 0)]}]},
    {"zones": [{"points": [(0, 0), (20, 20), (40, 40)]}]},
    {"zones": [{"points": [(0, 0), (50, 0), (50, 50), (0, 0)]}]},
    {"zones": [{"coordinate_space": "ground", "points": [(0, 0), (50, 0), (50, 50)]}]},
    {"zones": [{"points": [(0, 0), (250, 0), (50, 50)]}]},
    {"lines": [{"id": "same", "start": [0, 0], "end": [50, 50]},
               {"id": "same", "start": [0, 10], "end": [50, 60]}]},
])
def test_invalid_configuration_is_rejected(change):
    with pytest.raises(ValidationError):
        configuration(**change)


def test_geometric_predicates_cover_concavity_and_parallel_paths():
    concave = [(0, 0), (10, 0), (10, 10), (5, 5), (0, 10)]
    assert polygon_membership((5, 2), concave)[0]
    assert not polygon_membership((5, 8), concave)[0]
    assert segment_crossing((0, 0), (10, 0), (0, 5), (10, 5)) is None
    assert segment_crossing((0, 0), (10, 10), (0, 10), (10, 0)) == (.5, (5, 5))


def test_existing_counted_id_is_not_recounted_after_pause_or_long_gap():
    traffic = engine()
    cross(traffic)
    traffic.interrupt("paused")
    traffic.update([vehicle(y=25)], 5)
    traffic.update([vehicle(y=75)], 5.1)
    assert len(events(traffic)) == 1


def test_pipeline_profile_has_dedicated_cpu_stage_measurements():
    traffic = engine()
    traffic.update([vehicle()], 0)
    profile = traffic.snapshot()["profile"]
    assert set(profile) == {"classification_ms", "crossing_ms", "event_creation_ms", "zones_ms", "update_ms"}
    assert all(value >= 0 for value in profile.values())


def test_numpy_metric_values_from_existing_speed_estimator_remain_json_safe():
    traffic = engine()
    traffic.update([vehicle(confidence=np.float64(.9), estimated_speed_kmh=np.float64(12.5), speed_status="valid")],
                   np.float64(0))
    snapshot = traffic.snapshot()
    assert type(snapshot["summary"]["slow_tracks"]) is int
    assert snapshot["summary"]["slow_tracks"] == 0
    json.dumps(snapshot, allow_nan=False)


def test_each_configuration_edit_versions_ids_and_keeps_identity_count_sets_bounded():
    traffic = engine()
    cross(traffic)
    for index in range(5):
        traffic.configure(configuration(id="reused-import-id", name=f"Version {index}"))
        assert traffic.configuration.id != "reused-import-id"
        assert traffic._identities[1].counted == set()
    versions = [item["id"] for item in traffic.snapshot()["configurations"]]
    assert len(set(versions)) == 6


def test_fast_image_excursion_between_retained_samples_resets_stationarity_window():
    traffic = engine(stationary_window_s=1)
    for index in range(5):
        traffic.update([vehicle(x=50)], index * .25)
    assert traffic.overlay_state()["stationary_tracks"] == 1
    traffic.update([vehicle(x=80)], 1.1)
    traffic.update([vehicle(x=50)], 1.2)
    assert traffic.overlay_state()["stationary_tracks"] == 0
    for index in range(1, 5):
        traffic.update([vehicle(x=50)], 1.2 + index * .25)
    assert traffic.overlay_state()["stationary_tracks"] == 1


def test_untimed_frame_retains_image_observables_without_events_dwell_or_class_history():
    traffic = engine(**(zone_config() | {"lines": configuration().lines}))
    traffic.update([vehicle(x=50, y=25)], 0)
    classifications = traffic.snapshot()["classifications"]
    traffic.update([vehicle(x=50, y=65), vehicle(2, x=55, y=60)], None)
    current = traffic.overlay_state()
    assert current["visible_tracks"] == 2
    assert current["zone_occupancy"] == {"waiting": 2}
    assert current["zone_occupancy_proxy"]["waiting"] > 0
    assert current["timestamp_valid"] is False
    assert current["stationary_tracks"] is None
    assert current["slow_tracks"] is None
    assert all(value["category"] == "unknown" for value in current["tracks"].values())
    assert traffic.snapshot()["classifications"] == classifications
    assert not events(traffic)
    assert [event["kind"] for event in traffic.snapshot()["zone_events"]] == ["entry", "interrupted"]
    assert len(traffic.snapshot()["occupancy_samples"]) == 1
    assert traffic.snapshot()["summary"]["covered_duration_s"] == 0
    traffic.update([vehicle(x=50, y=70)], .2)
    assert not events(traffic)
    assert traffic.overlay_state()["timestamp_valid"] is True
    assert len(traffic.snapshot()["coverage"]) == 2
    json.dumps(traffic.snapshot(), allow_nan=False)


def test_untimed_frame_does_not_evaluate_ground_zones_or_calibrated_slow_values():
    traffic = engine(lines=[], calibration_id="road", zones=[{
        "id": "ground", "coordinate_space": "ground", "hysteresis": .1,
        "points": [(0, 0), (10, 0), (10, 10), (0, 10)]}])
    traffic.update([vehicle(world_position=(5, 5), speed_status="valid", estimated_speed_kmh=1)], None)
    current = traffic.overlay_state()
    assert current["visible_tracks"] == 1
    assert current["zone_occupancy"]["ground"] == 0
    assert current["unavailable_zone_ids"] == ["ground"]
    assert current["slow_tracks"] is None
    assert not traffic.snapshot()["zone_events"]


def test_counting_exposure_excludes_unconfigured_time_pause_and_source_gaps():
    traffic = engine(lines=[])
    traffic.update([], 0)
    traffic.update([], .5)
    assert traffic.snapshot()["summary"]["covered_counting_duration_s"] == 0
    traffic.configure(configuration())
    traffic.update([], 1)
    traffic.update([], 1.5)
    traffic.interrupt("paused")
    traffic.update([], 2)
    traffic.update([], 2.5)
    traffic.update([], 5)
    traffic.update([], 5.5)
    traffic.configure(configuration(lines=[]))
    traffic.update([], 6)
    traffic.update([], 6.5)
    summary = traffic.snapshot()["summary"]
    assert summary["covered_duration_s"] == 2.5
    assert summary["covered_counting_duration_s"] == 1.5
    assert len(traffic.snapshot()["coverage"]) == 5
