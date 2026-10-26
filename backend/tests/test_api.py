import time

import cv2
import numpy as np
import pytest
from fastapi.testclient import TestClient

from roadlens.api import create_app
from roadlens.detector import Detection
from roadlens.session import SessionManager


@pytest.fixture
def video_bytes(tmp_path):
    path = tmp_path / "upload.avi"
    writer = cv2.VideoWriter(str(path), cv2.VideoWriter_fourcc(*"MJPG"), 10, (96, 64))
    assert writer.isOpened()
    for _ in range(6):
        writer.write(np.zeros((64, 96, 3), np.uint8))
    writer.release()
    return path.read_bytes()


class FakeDetector:
    def __init__(self, *args, **kwargs):
        pass

    def detect(self, image):
        return [Detection((10, 10, 40, 40), 0.8, "car")]


def test_health_and_idle_state_do_not_open_camera(tmp_path):
    calls = []
    manager = SessionManager(weights_path=tmp_path / "missing.onnx", source_factory=lambda *args: calls.append("camera"))
    with TestClient(create_app(manager), base_url="http://127.0.0.1:8000") as client:
        health = client.get("/api/health")
        assert health.status_code == 200
        assert health.json()["model"]["ready"] is False
        assert health.json()["model"]["input_size"] == 640
        snapshot = client.get("/api/session").json()
        assert snapshot["state"] == "idle"
        assert snapshot["calibration_status"] == "required"
        assert client.get("/api/frame").status_code == 404
        assert calls == []


def test_upload_start_poll_frame_and_complete_pipeline(tmp_path, video_bytes):
    manager = SessionManager(upload_dir=tmp_path / "uploads", detector_factory=FakeDetector)
    with TestClient(create_app(manager), base_url="http://127.0.0.1:8000") as client:
        uploaded = client.post("/api/videos", files={"file": ("../../private.avi", video_bytes, "video/x-msvideo")})
        assert uploaded.status_code == 200, uploaded.text
        payload = uploaded.json()
        assert payload["name"] == "private.avi"
        assert payload["width"] == 96
        assert "path" not in payload
        # Phase 4 also persists .catalog.json beside the single recording.
        assert len(list(manager.upload_dir.glob("*.avi"))) == 1
        assert (manager.upload_dir / ".catalog.json").is_file()
        start = client.post("/api/sessions/start", json={"source_type": "video", "video_id": payload["video_id"]})
        assert start.status_code == 200, start.text
        session_id = start.json()["session_id"]
        deadline = time.monotonic() + 5
        while time.monotonic() < deadline:
            snapshot = client.get("/api/session").json()
            if snapshot["state"] in {"completed", "error"}:
                break
            time.sleep(0.005)
        assert snapshot["state"] == "completed", snapshot
        assert snapshot["counts"]["car"] == 1
        assert snapshot["frame_index"] == 6
        frame = client.get("/api/frame")
        assert frame.status_code == 200
        assert frame.headers["content-type"] == "image/jpeg"
        assert frame.content[:2] == b"\xff\xd8"
        stream = client.get("/api/stream", params={"session": session_id})
        assert stream.status_code == 200
        assert b"Content-Type: image/jpeg" in stream.content
        assert client.get("/api/stream", params={"session": "previous-session"}).status_code == 404
        assert client.post("/api/sessions/stop").json()["state"] == "stopped"
        assert client.post("/api/sessions/reset").json()["state"] == "idle"


def test_invalid_uploads_are_rejected_and_removed(tmp_path, video_bytes):
    manager = SessionManager(upload_dir=tmp_path / "uploads")
    with TestClient(create_app(manager, max_upload_bytes=100), base_url="http://127.0.0.1:8000") as client:
        assert client.post("/api/videos", files={"file": ("huge.avi", video_bytes)}).status_code == 413
        assert client.post("/api/videos", files={"file": ("broken.avi", b"invalid")}).status_code == 400
        assert client.post("/api/videos", files={"file": ("empty.avi", b"")}).status_code == 400
        assert client.post("/api/videos", files={"file": ("program.exe", b"invalid")}).status_code == 400
        assert list(manager.upload_dir.iterdir()) == []


def test_api_validates_configuration_and_control_transitions(tmp_path):
    manager = SessionManager(upload_dir=tmp_path / "uploads")
    with TestClient(create_app(manager), base_url="http://127.0.0.1:8000") as client:
        assert client.post("/api/sessions/start", json={"source_type": "video"}).status_code == 422
        assert client.post("/api/sessions/start", json={"source_type": "video", "video_id": "C:/secret.avi"}).status_code == 400
        assert client.post("/api/sessions/start", json={"source_type": "camera", "input_size": 512}).status_code == 422
        assert client.post("/api/sessions/start", json={"source_type": "camera", "video_path": "C:/secret.avi"}).status_code == 422
        assert client.post("/api/sessions/pause").status_code == 409
        assert client.post("/api/sessions/resume").status_code == 409


def test_local_api_rejects_cross_origin_and_dns_rebinding_requests():
    with TestClient(create_app(), base_url="http://127.0.0.1:8000") as client:
        assert client.post("/api/sessions/stop", headers={"Origin": "https://example.com"}).status_code == 403
        assert client.post("/api/sessions/stop", headers={"Sec-Fetch-Site": "cross-site"}).status_code == 403
        assert client.get("/api/health", headers={"Host": "attacker.example:8000"}).status_code == 403
        assert client.post("/api/sessions/stop", headers={"Origin": "http://localhost:5173"}).status_code == 200
        assert client.get("/api/health").headers["cache-control"] == "no-store"
