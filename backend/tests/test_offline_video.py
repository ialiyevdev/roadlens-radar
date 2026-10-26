"""Real generated-file decoding and explicit synthetic invalid PTS sequences."""

from fractions import Fraction
from types import SimpleNamespace

import cv2
import numpy as np
import pytest

from roadlens.offline_video import VideoNavigator, frame_metadata


@pytest.fixture
def video(tmp_path):
    path = tmp_path / "synthetic.avi"
    writer = cv2.VideoWriter(str(path), cv2.VideoWriter_fourcc(*"FFV1"), 12, (96, 64))
    assert writer.isOpened()
    for index in range(20):
        writer.write(np.full((64, 96, 3), index * 10, np.uint8))
    writer.release()
    return path


def test_index_metadata_uses_actual_pts_without_image_storage(video):
    navigator = VideoNavigator(video)
    try:
        summary = navigator.summary()
        assert summary["frame_count"] == 20
        assert summary["reported_fps"] == 12
        assert summary["observed_span_s"] == pytest.approx(19 / 12)
        assert summary["timestamp_warning_frames"] == 0
        assert summary["indexing_ms"] >= 0
        assert not navigator._cache
        assert navigator.metadata(1)["timestamp_s"] == 0
        assert navigator.metadata(20)["timestamp_s"] == pytest.approx(19 / 12)
        assert navigator.metadata(20)["pts"] == 19
    finally:
        navigator.close()


def test_exact_ordinal_navigation_and_backward_cache_preserve_raw_frames(video):
    navigator = VideoNavigator(video)
    try:
        assert np.all(navigator.image(1) == 0)
        assert np.all(navigator.image(15) == 140)
        assert len(navigator._cache) == 8
        assert np.all(navigator.image(14) == 130)
        assert navigator.cache_hits == 1
        assert np.all(navigator.image(2) == 10)
        image = navigator.image(2)
        image[:] = 255  # Overlay/edit consumers cannot mutate cached source pixels.
        assert np.all(navigator.image(2) == 10)
        assert navigator.summary()["last_navigation_ms"] >= 0
    finally:
        navigator.close()
    with pytest.raises(ValueError, match="closed"):
        navigator.image(1)


@pytest.mark.parametrize("index", [0, -1, 21, 1.5, True, "1"])
def test_out_of_range_and_noninteger_ordinals_fail(video, index):
    navigator = VideoNavigator(video)
    try:
        with pytest.raises(ValueError, match="1-based"):
            navigator.metadata(index)
    finally:
        navigator.close()


def test_frame_limit_is_explicit_without_inventing_full_recording_count(video):
    navigator = VideoNavigator(video, max_frames=5)
    try:
        assert navigator.summary()["frame_count"] == 5
        assert navigator.summary()["truncated"]
        assert navigator.summary()["warnings"]
        with pytest.raises(ValueError):
            navigator.image(6)
    finally:
        navigator.close()


def test_changed_video_cannot_silently_reuse_annotation_coordinates(video):
    navigator = VideoNavigator(video)
    try:
        with video.open("ab") as stream:
            stream.write(b"changed")
        with pytest.raises(ValueError, match="changed after indexing"):
            navigator.image(1)
    finally:
        navigator.close()


def test_pixel_cache_is_bounded_by_bytes_as_well_as_frame_count(video):
    navigator = VideoNavigator(video)
    try:
        navigator.MAX_CACHE_BYTES = 96 * 64 * 3 * 2
        assert np.all(navigator.image(15) == 140)
        assert len(navigator._cache) == 2
        assert navigator.summary()["cached_pixel_bytes"] <= navigator.MAX_CACHE_BYTES
        navigator.MAX_CACHE_BYTES = 1  # Even one oversized frame is returned without retention.
        navigator.close()
    finally:
        navigator.close()
    oversized = VideoNavigator(video)
    try:
        oversized.MAX_CACHE_BYTES = 1
        assert np.all(oversized.image(1) == 0)
        assert oversized.summary()["cached_pixel_bytes"] == 0
        assert not oversized._cache
    finally:
        oversized.close()


@pytest.mark.parametrize("pts,previous,base,prior_base,warning", [
    (None, None, Fraction(1, 25), None, "missing_or_nonfinite"),
    (2, .08, Fraction(1, 25), "1/25", "duplicate"),
    (1, .08, Fraction(1, 25), "1/25", "backward"),
    (-1, None, Fraction(1, 25), None, "negative"),
    (4, .08, Fraction(1, 20), "1/25", "timebase_changed"),
])
def test_invalid_pts_are_preserved_and_flagged_without_nominal_time(pts, previous, base, prior_base, warning):
    frame = SimpleNamespace(pts=pts, time_base=base, width=96, height=64)
    metadata = frame_metadata(frame, 3, previous, prior_base)
    assert warning in metadata["timing_warning"]
    assert metadata["timestamp_s"] == (float(pts * base) if pts is not None else None)
    assert metadata["pts"] == pts


def test_bad_video_is_a_useful_domain_error(tmp_path):
    bad = tmp_path / "bad.mp4"
    bad.write_bytes(b"not video")
    with pytest.raises(ValueError, match="could not be decoded"):
        VideoNavigator(bad)
