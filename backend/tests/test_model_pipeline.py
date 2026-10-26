"""Optional real inference on a recorded replay of a licensed still image.

This checks plumbing and track continuity, not tracking accuracy on moving traffic.
"""

import time
from pathlib import Path

import cv2
import pytest

from roadlens.schemas import StartRequest
from roadlens.session import SessionManager


WEIGHTS = Path(__file__).resolve().parents[2] / "models" / "vehicle_detector.onnx"


@pytest.mark.skipif(not WEIGHTS.exists(), reason="Run scripts/download_model.py for real-model tests")
def test_recorded_replay_with_real_cpu_detector(tmp_path):
    image = cv2.imread(str(Path(__file__).parent / "fixtures" / "city_traffic_cc0.jpg"))
    assert image is not None
    image = cv2.resize(image, (640, 360))
    path = tmp_path / "licensed-still-replay.avi"
    writer = cv2.VideoWriter(str(path), cv2.VideoWriter_fourcc(*"MJPG"), 10, (640, 360))
    assert writer.isOpened()
    for _ in range(5):
        writer.write(image)
    writer.release()
    manager = SessionManager(weights_path=WEIGHTS)
    video_id = manager.register_video(path, "CC0 still-image replay; not moving traffic")
    try:
        manager.start(StartRequest(source_type="video", video_id=video_id))
        deadline = time.monotonic() + 60
        while time.monotonic() < deadline:
            snapshot = manager.snapshot()
            if snapshot.state in {"completed", "error"}:
                break
            time.sleep(0.02)
        assert snapshot.state == "completed", snapshot.error
        assert snapshot.frame_index == 5
        assert snapshot.timestamp_s == pytest.approx(0.4)
        assert snapshot.timing_source == "video presentation timestamp"
        assert snapshot.timing_warning is None
        assert snapshot.total_tracks >= 1
        assert any(track.state == "confirmed" for track in snapshot.tracks)
        assert snapshot.calibration_status == "required"
        assert snapshot.measurements == []
        assert snapshot.measurement_summary["latest_speed_kmh"] is None
        assert all(track.estimated_speed_kmh is None for track in snapshot.tracks)
        assert manager.frame().startswith(b"\xff\xd8")
    finally:
        manager.stop()
