from fractions import Fraction
from types import SimpleNamespace

import numpy as np
import pytest

from roadlens.capture import CapturedFrame, VideoSource
from roadlens.timing import TimingIntegrity


def packet(index, timestamp, **extra):
    return CapturedFrame(np.zeros((8, 8, 3), np.uint8), index, timestamp, 100 + index / 10,
                         "video presentation timestamp", **extra)


def test_timing_integrity_separates_source_frames_processed_indices_and_latency_window():
    timing = TimingIntegrity()
    for index in range(1, 501):
        item = packet(index, (index - 1) / 10)
        timing.source(item)
        if index % 2 == 0:
            timing.processed(item, item.acquired_at + .02)
    result = timing.snapshot()
    assert result["source_frame_count"] == 500
    assert result["processed_frame_count"] == 250
    assert result["skipped_source_frames"] == 250
    assert result["effective_observation_rate_hz"] == pytest.approx(5)
    assert result["maximum_source_gap_s"] == pytest.approx(.1)
    assert result["maximum_observation_gap_s"] == pytest.approx(.2)
    assert result["source_interval_cv"] == pytest.approx(0, abs=1e-10)
    assert result["processing_latency"]["n"] == 240
    assert result["processing_latency"]["p95_ms"] == pytest.approx(20)
    assert result["warnings"] == []


def test_empty_timing_is_nullable_without_fabricated_rates_or_latency():
    result = TimingIntegrity().snapshot()
    assert result["source_frame_count"] == 0
    assert result["effective_observation_rate_hz"] is None
    assert result["source_interval_cv"] is None
    assert result["processing_latency"]["p95_ms"] is None


def test_duplicate_backward_missing_timestamps_and_timebase_changes_are_explicit():
    timing = TimingIntegrity()
    timing.source(packet(1, 0, raw_timestamp_s=0, time_base="1/10"))
    timing.source(packet(2, .1, raw_timestamp_s=0, time_base="1/10", timestamp_issue="duplicate_timestamp"))
    timing.source(packet(3, .2, raw_timestamp_s=-.1, time_base="1/20", timestamp_issue="backward_timestamp"))
    timing.source(packet(4, .3, timestamp_issue="missing_timestamp"))
    result = timing.snapshot()
    assert result["issues"] == {"duplicate_timestamp": 1, "backward_timestamp": 1, "timebase_changed": 1, "missing_timestamp": 1}
    assert result["latest_raw_timestamp_s"] is None
    assert result["warnings"]


def test_irregular_intervals_and_large_gaps_do_not_use_nominal_fps():
    timing = TimingIntegrity()
    for index, timestamp in enumerate([0, .1, .2, .3, .4, .5, .6, 2], 1):
        item = packet(index, timestamp)
        timing.source(item)
        timing.processed(item, item.acquired_at + .01)
    result = timing.snapshot()
    assert result["issues"]["large_source_gap"] == 1
    assert result["maximum_source_gap_s"] == pytest.approx(1.4)
    assert result["source_interval_cv"] > 1
    assert result["effective_observation_rate_hz"] == pytest.approx(3.5)


def test_decoder_preserves_original_pts_after_fallback_and_flags_timebase_change(monkeypatch, tmp_path):
    from roadlens import capture
    specs = [(0, Fraction(1, 10)), (1, Fraction(1, 10)), (1, Fraction(1, 10)), (8, Fraction(1, 20)), (None, Fraction(1, 20))]
    frames = [SimpleNamespace(pts=pts, time_base=base, to_ndarray=lambda **kwargs: np.zeros((8, 8, 3), np.uint8)) for pts, base in specs]
    stream = SimpleNamespace(codec_context=SimpleNamespace(width=8,height=8), average_rate=Fraction(10))
    container = SimpleNamespace(streams=SimpleNamespace(video=[stream]), decode=lambda _: iter(frames), close=lambda: None)
    monkeypatch.setattr(capture.av, "open", lambda _: container)
    source = VideoSource(tmp_path / "controlled.avi")
    try:
        packets = [source.read() for _ in specs]
        assert packets[2].timestamp_issue == "duplicate_timestamp"
        assert packets[2].raw_timestamp_s == pytest.approx(.1)
        assert packets[2].timestamp_s == pytest.approx(.2)
        assert packets[3].raw_timestamp_s == pytest.approx(.4)
        assert "timebase changed" in packets[3].timing_warning
        assert packets[4].raw_timestamp_s is None
        assert packets[4].timestamp_issue == "missing_timestamp"
        assert all(item.decode_ms >= 0 and item.decoded_at == item.acquired_at for item in packets)
    finally:
        source.close()
