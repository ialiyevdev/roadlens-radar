from fractions import Fraction
from types import SimpleNamespace

import cv2
import numpy as np
import pytest

from roadlens import capture


def test_recorded_video_uses_decoder_presentation_timestamps(tmp_path):
    path = tmp_path / "generated.avi"
    writer = cv2.VideoWriter(str(path), cv2.VideoWriter_fourcc(*"MJPG"), 12, (96, 64))
    assert writer.isOpened()
    for index in range(8):
        image = np.zeros((64, 96, 3), np.uint8)
        cv2.rectangle(image, (index * 2, 20), (index * 2 + 20, 40), (255, 255, 255), -1)
        writer.write(image)
    writer.release()
    source = capture.VideoSource(path)
    try:
        packets = []
        while (packet := source.read()) is not None:
            packets.append(packet)
        assert len(packets) == 8
        assert [packet.timestamp_s for packet in packets] == pytest.approx([i / 12 for i in range(8)])
        assert all(packet.timing_source == "video presentation timestamp" for packet in packets)
        assert all(packet.timing_warning is None for packet in packets)
        assert packets[-1].image.shape == (64, 96, 3)
    finally:
        source.close()
    assert source.container is None


@pytest.mark.parametrize("timestamps", [[None, None, None], [0, 1, 1], [0, 2, 1]])
def test_missing_or_nonincreasing_pts_switches_to_explicit_diagnostic_fallback(monkeypatch, tmp_path, timestamps):
    frames = [SimpleNamespace(pts=pts, time_base=Fraction(1, 10), to_ndarray=lambda **kwargs: np.zeros((8, 8, 3), np.uint8)) for pts in timestamps]
    stream = SimpleNamespace(codec_context=SimpleNamespace(width=8, height=8), average_rate=Fraction(10))
    container = SimpleNamespace(streams=SimpleNamespace(video=[stream]), decode=lambda _: iter(frames), close=lambda: None)
    monkeypatch.setattr(capture.av, "open", lambda _: container)
    source = capture.VideoSource(tmp_path / "synthetic.avi")
    packets = [source.read() for _ in timestamps]
    assert all(b.timestamp_s > a.timestamp_s for a, b in zip(packets, packets[1:]))
    assert packets[-1].timing_source == "nominal frame interval fallback"
    assert "diagnostic only" in packets[-1].timing_warning
    source.close()


def test_windows_camera_backend_fallback_releases_failed_backend(monkeypatch):
    attempts = []

    class FakeCapture:
        def __init__(self, index, backend):
            self.backend, self.released = backend, False
            attempts.append(self)

        def isOpened(self):
            return self.backend == cv2.CAP_MSMF

        def set(self, *args):
            pass

        def release(self):
            self.released = True

    monkeypatch.setattr(capture.sys, "platform", "win32")
    monkeypatch.setattr(capture.cv2, "VideoCapture", FakeCapture)
    selected = capture.open_camera(0, 1280, 720)
    assert [item.backend for item in attempts] == [cv2.CAP_DSHOW, cv2.CAP_MSMF]
    assert attempts[0].released
    assert selected is attempts[1]


def test_camera_timestamp_is_acquisition_time_and_disconnection_is_explicit(monkeypatch):
    calls = []
    image = np.zeros((24, 32, 3), np.uint8)
    frames = iter([(True, image), (False, None)])
    device = SimpleNamespace(read=lambda: next(frames), get=lambda prop: {cv2.CAP_PROP_FRAME_WIDTH: 32, cv2.CAP_PROP_FRAME_HEIGHT: 24, cv2.CAP_PROP_FPS: 0}[prop], release=lambda: calls.append("released"))
    clock = iter([100.0, 100.25, 100.5])
    monkeypatch.setattr(capture, "open_camera", lambda *args: device)
    monkeypatch.setattr(capture.time, "monotonic", lambda: next(clock))
    source = capture.CameraSource(0, 32, 24)
    packet = source.read()
    assert packet.timestamp_s == 0.25
    assert packet.acquired_at == 100.25
    assert source.reported_fps is None
    with pytest.raises(capture.SourceError, match="stopped delivering"):
        source.read()
    source.close()
    assert calls == ["released"]
