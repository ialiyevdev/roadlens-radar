import time

import cv2
import numpy as np
import pytest

from roadlens.capture import CapturedFrame, SourceError, VideoSource
from roadlens.detector import Detection
from roadlens.schemas import StartRequest
from roadlens.session import SessionConflict, SessionManager


def wait_for(manager, predicate, timeout=5):
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        snapshot = manager.snapshot()
        if predicate(snapshot):
            return snapshot
        time.sleep(0.005)
    raise AssertionError(f"Session did not reach expected condition: {manager.snapshot()}")


def detector_factory(instances, delay=0.0):
    class FakeDetector:
        def __init__(self, weights, **kwargs):
            self.frames = 0
            instances.append(self)

        def detect(self, image):
            time.sleep(delay)
            self.frames += 1
            return [Detection((20, 15, 50, 40), 0.9, "car")]

    return FakeDetector


class LiveSource:
    live = True
    width, height, reported_fps = 96, 64, 100

    def __init__(self, disconnect_after=None):
        self.index, self.closed = 0, False
        self.disconnect_after = disconnect_after
        self.epoch = time.monotonic()

    def read(self):
        time.sleep(0.003)
        if self.disconnect_after is not None and self.index >= self.disconnect_after:
            raise SourceError("Camera disconnected during test.")
        self.index += 1
        now = time.monotonic()
        return CapturedFrame(np.zeros((64, 96, 3), np.uint8), self.index, now - self.epoch, now, "monotonic acquisition")

    def close(self):
        self.closed = True


def test_entire_recorded_video_pipeline_tracks_and_restarts_without_camera(tmp_path):
    path = tmp_path / "generated.avi"
    writer = cv2.VideoWriter(str(path), cv2.VideoWriter_fourcc(*"MJPG"), 12, (96, 64))
    assert writer.isOpened()
    for _ in range(12):
        writer.write(np.zeros((64, 96, 3), np.uint8))
    writer.release()
    instances, sources = [], []

    def source_factory(request, video_path, label):
        source = VideoSource(video_path, label)
        sources.append(source)
        return source

    manager = SessionManager(detector_factory=detector_factory(instances, delay=0.005), source_factory=source_factory)
    video_id = manager.register_video(path, "generated.avi")
    request = StartRequest(source_type="video", video_id=video_id)
    try:
        for iteration in range(2):
            manager.start(request)
            if iteration == 0:
                wait_for(manager, lambda item: item.frame_index >= 2)
                manager.pause()
                time.sleep(0.02)
                paused_frame = manager.snapshot().frame_index
                time.sleep(0.02)
                assert manager.snapshot().frame_index == paused_frame
                assert manager.snapshot().state == "paused"
                manager.resume()
            snapshot = wait_for(manager, lambda item: item.state in {"completed", "error"})
            assert snapshot.state == "completed", snapshot.error
            assert snapshot.frame_index == 12
            assert snapshot.timestamp_s == pytest.approx(11 / 12)
            assert snapshot.counts.car == 1
            assert snapshot.total_tracks == 1
            assert snapshot.tracks[0].id == 1
            assert snapshot.calibration_status == "required"
            assert snapshot.capture_fps > 0
            assert snapshot.processing_fps > 0
            assert snapshot.latency_ms >= snapshot.inference_ms
            assert cv2.imdecode(np.frombuffer(manager.frame(), dtype=np.uint8), cv2.IMREAD_COLOR).shape == (64, 96, 3)
            manager.stop()
        assert len(instances) == 2
        assert all(detector.frames == 12 for detector in instances)
        assert all(source.container is None for source in sources)
    finally:
        manager.stop()


def test_live_queue_is_bounded_pause_retains_latest_and_stop_releases_source():
    sources, instances = [], []

    def source_factory(*args):
        source = LiveSource()
        sources.append(source)
        return source

    manager = SessionManager(source_factory=source_factory, detector_factory=detector_factory(instances, delay=0.025))
    try:
        manager.start(StartRequest(source_type="camera"))
        wait_for(manager, lambda item: item.frame_index >= 5)
        with pytest.raises(SessionConflict):
            manager.start(StartRequest(source_type="camera"))
        with pytest.raises(SessionConflict, match="scanning"):
            manager.cameras()
        assert manager.pause().state == "paused"
        time.sleep(0.07)
        paused_index = manager.snapshot().frame_index
        time.sleep(0.04)
        assert manager.snapshot().frame_index == paused_index
        assert manager._queue.qsize() <= 1
        manager.resume()
        snapshot = wait_for(manager, lambda item: item.frame_index > paused_index + 3)
        assert snapshot.dropped_frames > 0
        assert snapshot.capture_fps > 0
        assert manager.stop().state == "stopped"
        assert sources[0].closed
        assert not manager._worker.is_alive()
        assert not manager._capture_worker.is_alive()
        assert manager.reset().state == "idle"
        assert manager.frame() is None
    finally:
        manager.stop()


def test_camera_disconnect_is_visible_and_restart_is_possible():
    sources = []

    def source_factory(*args):
        source = LiveSource(disconnect_after=4)
        sources.append(source)
        return source

    manager = SessionManager(source_factory=source_factory, detector_factory=detector_factory([]))
    try:
        manager.start(StartRequest(source_type="camera"))
        snapshot = wait_for(manager, lambda item: item.state == "error")
        manager._worker.join(timeout=1)
        assert "disconnected" in snapshot.error
        assert sources[0].closed
        manager.start(StartRequest(source_type="camera"))
        wait_for(manager, lambda item: item.state == "error")
        manager._worker.join(timeout=1)
        assert sources[1].closed
    finally:
        manager.stop()


def test_source_is_released_if_detector_initialization_fails():
    source = LiveSource()

    def fail_detector(*args, **kwargs):
        raise FileNotFoundError("Download the detector weights first.")

    manager = SessionManager(source_factory=lambda *args: source, detector_factory=fail_detector)
    try:
        manager.start(StartRequest(source_type="camera"))
        snapshot = wait_for(manager, lambda item: item.state == "error")
        manager._worker.join(timeout=1)
        assert "Download" in snapshot.error
        assert source.closed
    finally:
        manager.stop()


def test_no_hardware_is_touched_until_explicit_start_and_source_failure_is_reported():
    calls = []

    def unavailable(*args):
        calls.append("opened")
        raise SourceError("No camera was found.")

    manager = SessionManager(source_factory=unavailable, detector_factory=detector_factory([]))
    assert manager.snapshot().state == "idle"
    assert calls == []
    try:
        manager.start(StartRequest(source_type="camera"))
        snapshot = wait_for(manager, lambda item: item.state == "error")
        assert snapshot.error == "No camera was found."
        assert calls == ["opened"]
    finally:
        manager.stop()


def test_frame_wait_uses_notification_and_session_guard():
    manager = SessionManager()
    version = manager._frame_version
    # A running stream without a new frame waits rather than busy polling.
    with manager._lock:
        manager._snapshot.state = "running"
        manager._snapshot.session_id = "test-session"
    started = time.monotonic()
    result = manager.wait_for_frame(version, "test-session", timeout=0.04)
    assert time.monotonic() - started >= 0.03
    assert result[0] == version
    started = time.monotonic()
    manager.wait_for_frame(version, "old-session", timeout=1)
    assert time.monotonic() - started < 0.1


def test_failed_release_remains_visible_and_blocks_new_hardware_access():
    class BrokenReleaseSource(LiveSource):
        def close(self):
            raise RuntimeError("Device release failed.")

    source = BrokenReleaseSource(disconnect_after=1)
    manager = SessionManager(source_factory=lambda *args: source, detector_factory=detector_factory([]))
    manager.start(StartRequest(source_type="camera"))
    wait_for(manager, lambda item: item.state == "error")
    manager._worker.join(timeout=1)
    assert manager._release_failed
    assert manager.stop().state == "error"
    with pytest.raises(SessionConflict, match="released"):
        manager.start(StartRequest(source_type="camera"))
    with pytest.raises(SessionConflict):
        manager.reset()
    with pytest.raises(SessionConflict):
        manager.cameras()
