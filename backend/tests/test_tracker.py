import pytest

from roadlens.detector import Detection
from roadlens.tracker import IoUTracker


def car(x, category="car"):
    return Detection((x, 10, x + 40, 40), 0.8, category)


def test_short_gap_keeps_id_and_counts_only_once():
    tracker = IoUTracker(min_hits=2)
    assert tracker.update([car(0)], 0)[0]["state"] == "tentative"
    assert tracker.update([car(4)], 0.1)[0]["id"] == 1
    assert tracker.update([], 0.2)[0]["state"] == "lost"
    assert tracker.update([car(12)], 0.3)[0]["id"] == 1
    assert tracker.counts["car"] == 1
    assert tracker.total_tracks == 1


def test_expired_track_new_id_and_other_categories_do_not_associate():
    tracker = IoUTracker(max_gap_s=0.5, min_hits=1)
    tracker.update([car(0)], 0)
    tracks = tracker.update([car(0, "truck")], 0.1)
    assert {track["id"] for track in tracks} == {1, 2}
    assert tracker.update([car(0)], 1)[0]["id"] == 3


def test_two_vehicles_keep_separate_ids_and_bounded_histories():
    tracker = IoUTracker()
    for frame in range(70):
        tracks = tracker.update([car(frame), car(200 + frame)], frame / 30)
    assert [track["id"] for track in tracks] == [1, 2]
    assert all(len(track["history"]) == 40 for track in tracks)
    assert tracker.total_tracks == 2
    assert tracks[0]["history"][-1] == (89, 40)


@pytest.mark.parametrize("timestamp", [0, -1, float("nan"), float("inf")])
def test_invalid_or_reversed_timing_rejected(timestamp):
    tracker = IoUTracker()
    tracker.update([car(0)], 0)
    with pytest.raises(ValueError, match="timestamps"):
        tracker.update([car(1)], timestamp)
