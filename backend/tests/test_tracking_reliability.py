"""Synthetic identity/lifecycle regressions independent of ML inference."""

import pytest

from roadlens.detector import Detection
from roadlens.tracker import IoUTracker


def car(x, y=10):
    return Detection((x, y, x + 40, y + 30), .8, "car")


def observed(tracks):
    return {track["id"]: track for track in tracks if not track["missed"]}


def test_global_assignment_solves_the_original_greedy_counterexample():
    tracker = IoUTracker(min_hits=1)
    tracker.update([car(0), car(50)], 0)
    result = observed(tracker.update([car(20), car(-30)], .1))
    assert set(result) == {1, 2}
    assert result[1]["bbox"][0] == -30
    assert result[2]["bbox"][0] == 20
    assert "association_ambiguous" in result[1]["tracking_diagnostics"]
    assert tracker.total_tracks == 2


def test_crossing_motion_keeps_ids_with_reversed_input_order():
    tracker = IoUTracker(min_hits=2)
    for index in range(35):
        a, b = car(7 * index), car(241 - 7 * index, 18)
        detections = [a, b] if index % 2 == 0 else [b, a]
        tracks = observed(tracker.update(detections, index / 10))
        assert tracks[1]["bbox"] == a.bbox
        assert tracks[2]["bbox"] == b.bbox


def test_source_time_prediction_reacquires_after_missing_detections():
    tracker = IoUTracker(min_hits=2)
    tracker.update([car(0)], 0)
    tracker.update([car(5)], .1)
    lost = tracker.update([], .35)[0]
    assert lost["state"] == "lost"
    assert lost["observation_gap_s"] == pytest.approx(.25)
    result = tracker.update([car(30)], .6)[0]
    assert result["id"] == 1
    assert result["state"] == "confirmed"
    assert result["age_s"] == pytest.approx(.6)
    assert result["observation_gap_s"] == pytest.approx(.5)
    assert "reacquired_after_observation_gap" in result["tracking_diagnostics"]


def test_ambiguous_assignment_is_flagged_without_claiming_verified_switch():
    tracker = IoUTracker(min_hits=1)
    tracker.update([car(0), car(10)], 0)
    result = tracker.update([car(5), car(5)], .1)
    assert all(track["association_ambiguous"] for track in result)
    assert tracker.diagnostics["potential_id_switches"] == 2
    tracker.update([], .2)
    assert tracker.diagnostics["potential_id_switches"] == 2
    assert tracker.diagnostics["active_tracks"] == 0
    assert tracker.diagnostics["lost_tracks"] == 2
    assert "id_switches" not in tracker.diagnostics


def test_expiry_is_inclusive_then_removes_and_flags_only_possible_fragment():
    tracker = IoUTracker(max_gap_s=.5, min_hits=1)
    tracker.update([car(0)], 0)
    assert tracker.update([], .5)[0]["id"] == 1
    result = tracker.update([car(0)], .50001)[0]
    assert result["id"] == 2
    assert "possible_fragment_after_expiry" in result["tracking_diagnostics"]
    assert tracker.diagnostics["removed_tracks"] == 1
    assert tracker.diagnostics["fragmentation_suspicions"] == 1
    assert tracker.total_tracks == 2
    assert tracker.diagnostics["confirmed_tracks"] == 1


def test_no_appearance_reidentification_after_expiry():
    tracker = IoUTracker(max_gap_s=.1, min_hits=1)
    tracker.update([car(0)], 0)
    tracker.update([], .2)
    result = tracker.update([car(0)], 2)[0]
    assert result["id"] == 2
    assert result["age_s"] == 0
    assert tracker.diagnostics["fragmentation_suspicions"] == 0


def test_smoothing_does_not_modify_observed_contact_points_or_boxes():
    tracker = IoUTracker(velocity_weight=.1)
    for index, x in enumerate((0, 4, 3, 8, 6)):
        detection = car(x)
        track = tracker.update([detection], index / 10)[0]
        assert track["bbox"] == detection.bbox
        assert track["history"][-1] == (x + 20, 40)


def test_box_shrink_exposes_possible_partial_occlusion_without_rewriting_box():
    tracker = IoUTracker()
    tracker.update([car(0)], 0)
    box = Detection((0, 10, 20, 40), .6, "car")
    result = tracker.update([box], .1)[0]
    assert result["bbox"] == box.bbox
    assert "box_area_shrink_possible_partial_occlusion" in result["tracking_diagnostics"]


def test_invalid_detection_cannot_poison_motion_or_count():
    tracker = IoUTracker(min_hits=1)
    malformed = [Detection((0, 0, float("nan"), 20), .9, "car"),
                 Detection((10, 0, 1, 20), .9, "car"),
                 Detection((0, 0, 20, 20), float("nan"), "car"),
                 Detection((0, 0, 20, 20), .9, "person")]
    assert tracker.update(malformed, 0) == []
    assert tracker.diagnostics["invalid_detections"] == 4
    assert tracker.update([car(1)], .1)[0]["id"] == 1


@pytest.mark.parametrize("timestamp", [0, -.1, float("nan"), float("inf"), -float("inf")])
def test_bad_timestamp_does_not_partially_update_tracker(timestamp):
    tracker = IoUTracker()
    tracker.update([car(0)], 0)
    with pytest.raises(ValueError, match="timestamps"):
        tracker.update([car(1000)], timestamp)
    result = tracker.update([car(5)], .1)[0]
    assert result["hits"] == 2
    assert result["id"] == 1


@pytest.mark.parametrize("options", [{"max_gap_s": 0}, {"max_gap_s": float("nan")},
                                    {"min_hits": 0}, {"min_hits": 1.5}, {"min_hits": True},
                                    {"velocity_weight": 0}, {"velocity_weight": 1.1},
                                    {"ambiguity_margin": -1}])
def test_invalid_tracker_options_rejected(options):
    with pytest.raises(ValueError):
        IoUTracker(**options)
