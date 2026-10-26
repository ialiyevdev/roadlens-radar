import pytest

from roadlens.profiling import ResponseProfiler


def test_rolling_response_profile_bounds_history_and_interpolates_percentile():
    profiler = ResponseProfiler(window_size=3)
    for value in (1000, 1, 2, 3):
        profiler.record("GET /api/session", value)
    profile = profiler.snapshot()
    row = profile["routes"][0]
    assert row["window_samples"] == 3
    assert row["latest_ms"] == 3
    assert row["mean_ms"] == 2
    assert row["p95_ms"] == pytest.approx(2.9)
    for index in range(100):
        profiler.record(str(index), 1)
    assert len(profiler.snapshot()["routes"]) == 64
