import json
from pathlib import Path

import pytest

from roadlens.calibration import CalibrationTransform, validate_gates
from roadlens.calibration_models import CalibrationInput, GateInput
from roadlens.speed import SpeedEstimator, SpeedOptions, gate_intersection


FIXTURE = json.loads((Path(__file__).parent / "fixtures" / "synthetic_trajectory.json").read_text())


def make_estimator(*, reverse=False, options=None):
    transform = CalibrationTransform(CalibrationInput.model_validate(FIXTURE["calibration"]))
    gates = validate_gates(transform, GateInput.model_validate({**FIXTURE["gates"], "allow_reverse": reverse}))
    return SpeedEstimator(transform, gates, "synthetic", "calibration-1", "session-1", options)


def car(x, y=300, *, track_id=1, **changes):
    return {"id": track_id, "category": "car", "bbox": (x - 8, y - 16, x + 8, y),
            "confidence": 0.9, "state": "confirmed", "hits": 3, "missed": 0, "history": [], **changes}


def run_fixture(estimator):
    for sample in FIXTURE["samples"]:
        x, y = sample["image_position"]
        enriched = estimator.update([car(x, y)], sample["timestamp_s"])
    return enriched


def test_known_20m_1_point_2_seconds_is_60_kmh_and_interpolates_crossings():
    estimator = make_estimator()
    track = run_fixture(estimator)[0]
    assert len(estimator.measurements) == 1
    result = estimator.measurements[0]
    assert result.status == "valid"
    for key, expected in FIXTURE["expected"].items():
        assert getattr(result, key) == pytest.approx(expected)
    assert result.start_position == pytest.approx((10, 20))
    assert result.end_position == pytest.approx((30, 20))
    assert result.direction == "A_to_B"
    assert track["measurement_state"] == "completed"
    assert track["estimated_speed_kmh"] == 60.0


@pytest.mark.parametrize(("start", "end", "gate", "fraction", "point"), [
    ((0, 0), (10, 0), ((4, -2), (4, 2)), 0.4, (4, 0)),
    ((10, 0), (0, 0), ((4, -2), (4, 2)), 0.6, (4, 0)),
    ((0, 0), (4, 0), ((4, 0), (4, 2)), 1, (4, 0)),
])
def test_finite_gate_intersection(start, end, gate, fraction, point):
    intersection = gate_intersection(start, end, gate)
    assert intersection[0] == pytest.approx(fraction)
    assert intersection[1] == pytest.approx(point)


@pytest.mark.parametrize(("start", "end", "gate"), [
    ((0, 3), (10, 3), ((4, -2), (4, 2))),
    ((4, 0), (10, 0), ((4, -2), (4, 2))),
    ((0, 0), (10, 0), ((1, 0), (4, 0))),
    ((0, 0), (float("nan"), 0), ((4, -2), (4, 2))),
])
def test_gate_does_not_count_line_extension_parallel_motion_or_previous_endpoint(start, end, gate):
    assert gate_intersection(start, end, gate) is None


def test_raw_positions_source_timestamps_and_original_box_are_preserved():
    estimator = make_estimator()
    raw = car(190)
    track = estimator.update([raw], 9.75)[0]
    assert track["bbox"] == raw["bbox"]
    assert track["history"] == raw["history"]
    assert track["image_position"] == (190, 300)
    assert track["world_position"] == pytest.approx((9, 20))
    sample = track["position_history"][0]
    assert sample["timestamp_s"] == 9.75
    assert sample["world_position"] == pytest.approx((9, 20))


def test_gate_jitter_and_completed_track_cannot_emit_duplicates():
    estimator = make_estimator()
    for index, x in enumerate([190, 205, 199, 202, 250, 300, 350, 390, 410, 399, 410]):
        estimator.update([car(x)], index * 0.2)
    assert len(estimator.measurements) == 1
    assert estimator.measurements[0].gate_a_timestamp_s == pytest.approx(0.2 * 10 / 15)


def test_touching_a_gate_and_returning_to_same_side_is_not_a_crossing():
    estimator = make_estimator()
    for index, x in enumerate([190, 200, 190]):
        track = estimator.update([car(x)], index * 0.2)[0]
    assert track["measurement_state"] == "waiting"
    assert estimator.measurements == []


def test_exact_contact_is_confirmed_on_far_side_with_original_contact_time():
    estimator = make_estimator()
    for index, x in enumerate([190, 200, 210, 250, 300, 350, 400, 410]):
        estimator.update([car(x)], index * 0.2)
    result = estimator.measurements[0]
    assert result.gate_a_timestamp_s == pytest.approx(0.2)
    assert result.gate_b_timestamp_s == pytest.approx(1.2)
    assert result.elapsed_seconds == pytest.approx(1.0)


def test_lingering_on_gate_uses_latest_contact_and_flags_timing_ambiguity():
    estimator = make_estimator()
    for index, x in enumerate([190, 200, 200, 210, 250, 300, 350, 400, 410]):
        estimator.update([car(x)], index * 0.2)
    result = estimator.measurements[0]
    assert result.gate_a_timestamp_s == pytest.approx(0.4)
    assert result.status == "approximate"
    assert any("Repeated observations" in reason for reason in result.reasons)


def test_touch_candidate_does_not_survive_a_large_gap():
    estimator = make_estimator()
    estimator.update([car(190)], 0)
    estimator.update([car(200)], 0.2)
    track = estimator.update([car(210)], 2)[0]
    assert track["measurement_state"] == "waiting"
    assert estimator.measurements == []


def test_reverse_disabled_rejected_and_enabled_measures_reverse():
    disabled, enabled = make_estimator(), make_estimator(reverse=True)
    for index, sample in enumerate(reversed(FIXTURE["samples"])):
        for estimator in (disabled, enabled):
            estimator.update([car(sample["image_position"][0])], index * 0.24)
    assert disabled.measurements[0].status == "rejected"
    assert "disabled" in disabled.measurements[0].reasons[-1]
    assert enabled.measurements[0].status == "valid"
    assert enabled.measurements[0].direction == "B_to_A"
    assert enabled.measurements[0].estimated_speed_kmh == 60


def test_irregular_source_times_and_retained_frames_use_elapsed_source_time():
    estimator = make_estimator()
    for timestamp in [0, 0.11, 0.29, 0.51, 0.72, 0.96, 1.2, 1.44, 1.68]:
        estimator.update([car(150 + timestamp * (500 / 3))], timestamp)
    result = estimator.measurements[0]
    assert result.status == "valid"
    assert result.elapsed_seconds == pytest.approx(1.2)
    assert result.estimated_speed_kmh == 60


def test_moderate_dropped_frames_mark_approximate_without_changing_source_speed():
    estimator = make_estimator()
    for timestamp in [0, 0.2, 0.6, 0.8, 1, 1.2, 1.6]:
        track = estimator.update([car(150 + timestamp * (500 / 3))], timestamp)[0]
    assert estimator.measurements[0].status == "approximate"
    assert estimator.measurements[0].estimated_speed_kmh == 60
    assert any("sampling gap" in reason for reason in estimator.measurements[0].reasons)
    assert track["estimated_speed_kmh"] is None


@pytest.mark.parametrize("timestamp", [None, float("nan"), float("inf"), 0.24, 0.1])
def test_missing_and_nonincreasing_timestamps_reject_active_crossing(timestamp):
    estimator = make_estimator()
    estimator.update([car(190)], 0)
    estimator.update([car(230)], 0.24)
    track = estimator.update([car(270)], timestamp)[0]
    assert track["measurement_state"] == "rejected"
    assert estimator.measurements[0].estimated_speed_kmh is None
    assert "timestamp" in estimator.measurements[0].reasons[-1]


def test_fallback_timing_cannot_generate_a_speed():
    estimator = make_estimator()
    estimator.update([car(190)], 0)
    estimator.update([car(230)], 0.24)
    estimator.update([car(270)], 0.48, timing_valid=False)
    assert estimator.measurements[0].status == "rejected"
    assert "fallback" in estimator.measurements[0].reasons[-1]


@pytest.mark.parametrize("mode", ["absent", "missed", "expired-gap", "category-change"])
def test_lost_track_identity_change_and_long_gap_reject_active_measurement(mode):
    estimator = make_estimator()
    estimator.update([car(190)], 0)
    estimator.update([car(230)], 0.24)
    if mode == "absent":
        estimator.update([], 0.48)
    elif mode == "missed":
        estimator.update([car(230, missed=1, state="lost")], 0.48)
    elif mode == "expired-gap":
        estimator.update([car(270)], 1.5)
    else:
        estimator.update([car(270, category="truck")], 0.48)
    estimator.update([car(430)], 1.74)
    assert len(estimator.measurements) == 1
    assert estimator.measurements[0].status == "rejected"
    assert estimator.measurements[0].estimated_speed_kmh is None


def test_pause_breaks_pending_pairs_and_rejects_active_traversal():
    estimator = make_estimator()
    estimator.update([car(190)], 0)
    estimator.update([car(230)], 0.24)
    estimator.interrupt("Observation paused before both gates.")
    estimator.update([car(430)], 0.48)
    assert len(estimator.measurements) == 1
    assert estimator.measurements[0].status == "rejected"
    assert "paused" in estimator.measurements[0].reasons[-1]


def test_pause_before_first_gate_requires_new_observation_pair():
    estimator = make_estimator()
    estimator.update([car(190)], 0)
    estimator.interrupt("Paused")
    estimator.update([car(230)], 0.24)
    assert estimator.measurements == []
    assert estimator._tracks[1].state == "waiting"


def test_finish_rejects_incomplete_and_preserves_completed_measurements():
    estimator = make_estimator()
    run_fixture(estimator)
    estimator.update([car(190, track_id=2)], 2)
    estimator.update([car(230, track_id=2)], 2.24)
    estimator.finish()
    assert [result.status for result in estimator.measurements] == ["valid", "rejected"]
    assert "ended" in estimator.measurements[-1].reasons[-1]


def test_missing_calibration_or_gates_does_not_stop_detection_tracking():
    for estimator in (SpeedEstimator(None, None, "source", None, "session"),
                      SpeedEstimator(make_estimator().transform, None, "source", "cal", "session")):
        track = run_fixture(estimator)[0]
        assert track["measurement_state"] == "not_calibrated"
        assert track["bbox"] == car(430)["bbox"]
        assert estimator.measurements == []


@pytest.mark.parametrize(("x", "y", "changes", "message"), [
    (5, 300, {}, "boundary"),
    (90, 300, {}, "outside"),
    (190, 300, {"bbox": (190, 300, 180, 280)}, "Invalid"),
    (190, 300, {"bbox": (float("nan"), 280, 200, 300)}, "Invalid"),
])
def test_partial_outside_and_invalid_positions_stay_explicit(x, y, changes, message):
    estimator = make_estimator()
    track = estimator.update([car(x, y, **changes)], 0)[0]
    assert track["world_position"] is None
    assert any(message in reason for reason in track["position_diagnostics"])
    assert track["position_history"][0]["valid"] is False
    if message == "Invalid":
        assert track["image_position"] is None


def test_both_gates_in_one_interval_rejected_for_insufficient_support():
    estimator = make_estimator(options=SpeedOptions(maximum_speed_kmh=1000))
    estimator.update([car(170)], 0)
    estimator.update([car(190)], 0.2)
    estimator.update([car(430)], 0.6)
    assert estimator.measurements[0].status == "rejected"
    assert "one source-frame" in estimator.measurements[0].reasons[-1]


def test_physically_implausible_jump_does_not_report_speed():
    estimator = make_estimator()
    estimator.update([car(190)], 0)
    estimator.update([car(230)], 0.24)
    estimator.update([car(430)], 0.25)
    result = estimator.measurements[0]
    assert result.status == "rejected"
    assert result.estimated_speed_kmh is None
    assert "Implausible" in result.reasons[-1]


def test_observed_bad_calibration_quality_marks_approximate_but_generic_caution_does_not():
    estimator = make_estimator()
    estimator.transform.diagnostics.warnings.append("Independent check error exceeds 0.25 m.")
    run_fixture(estimator)
    assert estimator.measurements[0].status == "approximate"
    assert any("Independent check error" in reason for reason in estimator.measurements[0].reasons)


def test_clear_and_new_session_do_not_keep_measurement_or_deduplication_state():
    estimator = make_estimator()
    run_fixture(estimator)
    estimator.clear()
    assert estimator.measurements == []
    assert estimator._tracks == {}
    assert run_fixture(estimator)[0]["measurement_state"] == "completed"
    assert len(estimator.measurements) == 1
    other_session = make_estimator()
    other_session.session_id = "session-2"
    run_fixture(other_session)
    assert other_session.measurements[0].id != estimator.measurements[0].id


def test_raw_history_and_results_are_bounded():
    estimator = make_estimator(options=SpeedOptions(history_size=4))
    track = run_fixture(estimator)[0]
    assert len(track["position_history"]) == 4


def test_invalidation_removes_numeric_labels_but_preserves_completed_history():
    estimator = make_estimator()
    run_fixture(estimator)
    estimator.transform = None
    estimator.gates = None
    track = estimator.update([car(450)], 2)[0]
    assert track["estimated_speed_kmh"] is None
    assert track["world_position"] is None
    assert track["measurement_state"] == "not_calibrated"
    assert estimator.measurements[0].estimated_speed_kmh == 60


def test_retired_tracks_release_history_and_retained_result_prevents_duplicate():
    estimator = make_estimator()
    run_fixture(estimator)
    estimator.update([], 2)
    assert estimator._tracks == {}
    assert len(estimator._results_by_track) == 1
    for sample in FIXTURE["samples"]:
        estimator.update([car(sample["image_position"][0])], sample["timestamp_s"] + 3)
    assert len(estimator.measurements) == 1


def test_history_limit_also_bounds_retired_deduplication_records():
    estimator = make_estimator(options=SpeedOptions(maximum_measurements=2))
    for track_id in range(4):
        for sample in FIXTURE["samples"]:
            estimator.update([car(sample["image_position"][0], track_id=track_id)], sample["timestamp_s"] + track_id * 2)
    estimator.update([], 9)
    assert len(estimator.measurements) == 2
    assert len(estimator._results_by_track) == 2
    assert estimator._tracks == {}


@pytest.mark.parametrize("options", [
    {"approximate_gap_s": 0}, {"maximum_gap_s": 0.1}, {"maximum_speed_kmh": float("nan")},
    {"minimum_samples": 2}, {"history_size": 2}, {"maximum_measurements": 0},
])
def test_invalid_configuration_is_rejected(options):
    with pytest.raises(ValueError):
        SpeedOptions(**options)


def test_result_retains_gate_support_projection_residuals_and_original_calibration():
    estimator = make_estimator()
    run_fixture(estimator)
    result = estimator.measurements[0]
    diagnostic = result.diagnostics
    assert diagnostic.gate_a_interpolation_interval_s == pytest.approx(.24)
    assert diagnostic.gate_b_interpolation_interval_s == pytest.approx(.24)
    assert diagnostic.maximum_observation_gap_s == pytest.approx(.24)
    assert diagnostic.maximum_contact_prediction_residual_px == pytest.approx(0, abs=1e-10)
    assert diagnostic.calibration_check_error_m == pytest.approx(0, abs=1e-5)
    assert diagnostic.gate_a_near_samples == 1
    assert diagnostic.gate_b_near_samples == 1
    assert diagnostic.retained_position_samples == len(result.position_samples)
    assert result.position_samples[-1].bbox == car(430)["bbox"]
    assert result.position_samples[-1].image_position == (430, 300)
    original = result.model_dump()
    estimator.transform.diagnostics.check_error_m = 100
    estimator.update([car(450)], 2)
    estimator.transform = None
    estimator.gates = None
    assert result.model_dump() == original
    assert result.calibration_metadata["geometry"]["width"] == 800


def test_ambiguous_association_rejects_a_traversal_without_claiming_verified_switch():
    estimator = make_estimator()
    estimator.update([car(190)], 0)
    estimator.update([car(230)], .24)
    estimator.update([car(270, association_ambiguous=True, age_s=.48)], .48)
    result = estimator.measurements[0]
    assert result.status == "rejected"
    assert result.estimated_speed_kmh is None
    assert result.diagnostics.ambiguous_observations == 1
    assert result.diagnostics.track_age_s == .48
    assert any("identity continuity is uncertain" in reason for reason in result.reasons)


def test_contact_prediction_residual_is_diagnostic_and_never_corrects_speed():
    estimator = make_estimator()
    for index, sample in enumerate(FIXTURE["samples"]):
        x, y = sample["image_position"]
        estimator.update([car(x, y + (12 if index == 3 else 0))], sample["timestamp_s"])
    result = estimator.measurements[0]
    assert result.status == "approximate"
    assert result.estimated_speed_kmh == 60
    assert result.diagnostics.maximum_contact_prediction_residual_px == pytest.approx(24)
    assert result.diagnostics.maximum_contact_prediction_residual_m == pytest.approx(2.4)
    assert any("inspect box jitter, acceleration" in reason for reason in result.reasons)


def test_region_edge_proximity_and_overlap_are_observations_not_error_bounds():
    estimator = make_estimator()
    gates = validate_gates(estimator.transform, GateInput(gate_a=((200, 100), (200, 180)), gate_b=((400, 100), (400, 180))))
    estimator = SpeedEstimator(estimator.transform, gates, "synthetic", "calibration-1", "session-1")
    for index, sample in enumerate(FIXTURE["samples"]):
        x, _ = sample["image_position"]
        estimator.update([car(x, 106), car(x + 4, 106, track_id=2)], sample["timestamp_s"])
    result = estimator.measurements[0]
    assert result.status == "approximate"
    assert result.diagnostics.minimum_region_margin_px == pytest.approx(6)
    assert result.diagnostics.maximum_box_overlap_fraction == pytest.approx(.75)
    assert result.diagnostics.overlapping_box_observations > 0
    assert any("partial occlusion is possible" in reason for reason in result.reasons)
    assert result.estimated_speed_kmh == 60


def test_projection_and_gate_profiling_never_replaces_source_time():
    estimator = make_estimator()
    run_fixture(estimator)
    assert estimator.last_profile["projection_ms"] >= 0
    assert estimator.last_profile["gate_events_ms"] >= 0
    assert estimator.measurements[0].elapsed_seconds == pytest.approx(1.2)
    assert estimator.measurements[0].gate_a_timestamp_s == pytest.approx(.3)


def test_quality_evidence_survives_raw_position_history_eviction():
    estimator = make_estimator(options=SpeedOptions(history_size=4))
    run_fixture(estimator)
    result = estimator.measurements[0]
    assert len(result.position_samples) == 4
    assert result.diagnostics.position_history_truncated
    assert result.diagnostics.quality_observation_count == len(FIXTURE["samples"])
    assert result.diagnostics.gate_a_near_samples == 1
    assert result.diagnostics.minimum_region_margin_px == pytest.approx(50)


@pytest.mark.parametrize("changes", [{"association_ambiguous": True}, {"missed": 1, "state": "lost"}, {"bbox": (1, 250, 20, 300)}])
def test_completed_result_is_preserved_but_invalid_current_identity_has_no_numeric_label(changes):
    from roadlens.measurement_session import MeasurementSession
    from roadlens.schemas import SessionSnapshot, TrackSnapshot

    estimator = make_estimator()
    run_fixture(estimator)
    enriched = estimator.update([car(450, **changes)], 2)[0]
    assert enriched["estimated_speed_kmh"] is None
    assert estimator.measurements[0].estimated_speed_kmh == 60
    measurement = MeasurementSession()
    measurement.estimator = estimator
    measurement.status = "ready"
    snapshot = SessionSnapshot(tracks=[TrackSnapshot.model_validate(enriched)])
    measurement.sync(snapshot)
    assert snapshot.tracks[0].estimated_speed_kmh is None
    assert snapshot.measurements[0].estimated_speed_kmh == 60
