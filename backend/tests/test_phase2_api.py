"""Real API/worker integration with controlled synthetic frames, never hardware."""

import json
import csv
import io
import queue
import threading
import time
from dataclasses import dataclass, field

import cv2
import numpy as np
import pytest
from fastapi.testclient import TestClient

from roadlens.api import create_app
from roadlens.capture import CapturedFrame
from roadlens.detector import Detection
from roadlens.session import SessionManager


class ControlledSource:
    """A sequential reader makes every retained source timestamp deterministic."""

    live = False
    width, height, reported_fps = 640, 480, 30

    def __init__(self):
        self.frames = queue.Queue()
        self.closed = threading.Event()
        self.index = 0
        self.last_image = None

    def read(self):
        specification = self.frames.get(timeout=10)
        if specification is None:
            return None
        x, timestamp, width, warning = specification
        self.index += 1
        image = np.zeros((self.height, width, 3), dtype=np.uint8)
        image[0, x, 0] = 255
        self.last_image = image
        return CapturedFrame(image, self.index, timestamp, time.monotonic(),
                             "video PTS" if warning is None else "nominal-rate fallback", warning)

    def close(self):
        self.closed.set()


class MarkerDetector:
    """Read the fixture marker; all tracking, geometry and measurement are real."""

    def __init__(self, *args, **kwargs):
        pass

    def detect(self, image):
        x = int(np.argmax(image[0, :, 0]))
        return [Detection((x - 40, 250, x + 40, 350), 0.95, "car")]


class BlockingMarkerDetector(MarkerDetector):
    def __init__(self):
        self.block_x = None
        self.entered = threading.Event()
        self.release = threading.Event()
        self.returned = threading.Event()

    def detect(self, image):
        if int(np.argmax(image[0, :, 0])) == self.block_x:
            self.entered.set()
            if not self.release.wait(timeout=5):
                raise AssertionError("The test did not release blocked detector inference.")
            self.returned.set()
        return super().detect(image)


def wait_for(manager, predicate, timeout=5):
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        snapshot = manager.snapshot()
        if predicate(snapshot):
            return snapshot
        if snapshot.state == "error":
            raise AssertionError(f"Unexpected worker error: {snapshot.error}")
        time.sleep(0.002)
    raise AssertionError(f"Timed out waiting for session state: {manager.snapshot()}")


@dataclass
class Scenario:
    client: TestClient
    manager: SessionManager
    video_id: str
    sources: list[ControlledSource] = field(default_factory=list)

    @property
    def source(self):
        return self.sources[-1]

    def start(self, **request):
        previous_count = len(self.sources)
        payload = {"source_type": "video", "video_id": self.video_id, **request}
        response = self.client.post("/api/sessions/start", json=payload)
        assert response.status_code == 200, response.text
        wait_for(self.manager, lambda snapshot: len(self.sources) > previous_count and snapshot.state == "running")
        self.send(150, 9.8)
        return self.client.get("/api/session").json()

    def send(self, x, timestamp, width=640, warning=None):
        expected = self.source.index + 1
        self.source.frames.put((x, timestamp, width, warning))
        return wait_for(self.manager, lambda snapshot: snapshot.frame_index >= expected)

    def finish(self):
        self.source.frames.put(None)
        snapshot = wait_for(self.manager, lambda item: item.state in {"completed", "error"})
        self.manager._worker.join(timeout=2)
        assert not self.manager._worker.is_alive()
        assert self.source.closed.is_set()
        return snapshot

    def configure(self):
        frozen = self.client.post("/api/calibration/freeze")
        assert frozen.status_code == 200, frozen.text
        created = self.client.post("/api/calibrations", json=calibration_payload(**frozen.json()))
        assert created.status_code == 200, created.text
        profile = created.json()
        activated = self.client.post(f"/api/calibrations/{profile['id']}/activate", json={"confirm_stationary": True})
        assert activated.status_code == 200, activated.text
        gates = self.client.put("/api/gates", json=gate_payload())
        assert gates.status_code == 200, gates.text
        return profile

    def complete_traversal(self, offset=0):
        for index, x in enumerate(range(150, 426, 25)):
            snapshot = self.send(x + offset, 10 + index * 0.15)
        return snapshot


def calibration_payload(source_id="video:synthetic", geometry=None, **ignored):
    points = [(50, 50), (590, 50), (590, 430), (50, 430)]
    return {
        "name": "Synthetic measured plane", "source_id": source_id,
        "geometry": geometry or {"width": 640, "height": 480},
        "points": [{"image": [x, y], "world": [x / 10, y / 10]} for x, y in points],
        "check_points": [{"image": [320, 240], "world": [32, 24]}],
    }


def gate_payload():
    return {"gate_a": [[200, 100], [200, 420]], "gate_b": [[400, 100], [400, 420]], "allow_reverse": False}


@pytest.fixture
def scenario(tmp_path):
    sources = []

    def source_factory(*args):
        source = ControlledSource()
        sources.append(source)
        return source

    manager = SessionManager(
        upload_dir=tmp_path / "uploads", calibration_dir=tmp_path / "calibrations",
        source_factory=source_factory, detector_factory=MarkerDetector,
    )
    video_id = manager.register_video(tmp_path / "synthetic.avi", "Synthetic trajectory", "video:synthetic")
    with TestClient(create_app(manager), base_url="http://127.0.0.1:8000") as client:
        try:
            yield Scenario(client, manager, video_id, sources)
        finally:
            for source in sources:
                source.frames.put(None)
            if manager._worker is not None:
                manager._worker.join(timeout=2)
            manager.stop()


def test_profile_crud_validation_and_unknown_identifiers(scenario):
    client = scenario.client
    assert client.get("/api/calibrations").json() == {"profiles": []}
    assert client.post("/api/calibration/freeze").status_code == 400
    invalid = calibration_payload()
    invalid["points"] = invalid["points"][:3]
    validation = client.post("/api/calibrations/validate", json=invalid)
    assert validation.status_code == 200
    assert not validation.json()["valid"]
    assert "four" in validation.json()["errors"][0]
    assert client.post("/api/calibrations", json=invalid).status_code == 422
    assert client.get("/api/calibrations").json()["profiles"] == []

    payload = calibration_payload()
    validation = client.post("/api/calibrations/validate", json=payload).json()
    assert validation["valid"]
    assert validation["check_error_m"] < 1e-6
    created = client.post("/api/calibrations", json=payload)
    assert created.status_code == 200, created.text
    profile = created.json()
    profile_id = profile["id"]
    assert profile["diagnostics"]["valid"]
    assert len(list(scenario.manager.calibrations.directory.glob("*.json"))) == 1
    assert client.post(f"/api/calibrations/{profile_id}/activate", json={"confirm_stationary": True}).status_code == 422
    payload["name"] = "Renamed measured plane"
    updated = client.put(f"/api/calibrations/{profile_id}", json=payload)
    assert updated.status_code == 200
    assert updated.json()["id"] == profile_id
    assert updated.json()["name"] == payload["name"]
    assert client.get("/api/calibrations").json()["profiles"][0]["name"] == payload["name"]
    assert client.delete(f"/api/calibrations/{profile_id}").json() == {"deleted": True}
    assert client.get("/api/calibrations").json()["profiles"] == []
    assert client.delete(f"/api/calibrations/{profile_id}").status_code == 404
    assert client.post("/api/calibrations/not-a-profile/activate", json={"confirm_stationary": True}).status_code == 404


def test_freeze_preserves_raw_coordinates_and_only_three_frames(scenario):
    snapshot = scenario.start()
    frames = [scenario.client.post("/api/calibration/freeze").json() for _ in range(4)]
    assert frames[-1]["geometry"]["width"] == snapshot["width"] == 640
    assert frames[-1]["geometry"]["height"] == snapshot["height"] == 480
    assert frames[-1]["source_id"] == snapshot["source_id"] == "video:synthetic"
    assert frames[-1]["session_id"] == snapshot["session_id"]
    assert scenario.client.get(frames[0]["image_url"]).status_code == 404
    for frame in frames[1:]:
        response = scenario.client.get(frame["image_url"])
        assert response.status_code == 200
        assert response.headers["content-type"] == "image/jpeg"
        success, raw_jpeg = cv2.imencode(".jpg", scenario.source.last_image, [cv2.IMWRITE_JPEG_QUALITY, 95])
        assert success
        assert response.content == raw_jpeg.tobytes()
    scenario.finish()
    scenario.client.post("/api/sessions/reset")
    assert scenario.client.get(frames[-1]["image_url"]).status_code == 404


def test_activation_requires_stationarity_matching_source_and_geometry(scenario):
    scenario.start()
    client = scenario.client
    profile = client.post("/api/calibrations", json=calibration_payload()).json()
    activate_url = f"/api/calibrations/{profile['id']}/activate"
    response = client.post(activate_url, json={})
    assert response.status_code == 422
    assert "Confirm" in response.json()["detail"]
    mismatch_source = client.post("/api/calibrations", json=calibration_payload(source_id="camera:8")).json()
    assert client.post(f"/api/calibrations/{mismatch_source['id']}/activate", json={"confirm_stationary": True}).status_code == 422
    mismatch_geometry = client.post("/api/calibrations", json=calibration_payload(
        geometry={"width": 640, "height": 480, "mirrored": True})).json()
    assert client.post(f"/api/calibrations/{mismatch_geometry['id']}/activate", json={"confirm_stationary": True}).status_code == 422
    activated = client.post(activate_url, json={"confirm_stationary": True})
    assert activated.status_code == 200
    assert activated.json()["calibration_status"] == "ready"
    assert activated.json()["calibration_id"] == profile["id"]
    assert activated.json()["measurement_status"] == "Configure Gate A and Gate B"


def test_gates_validate_persist_edit_and_reset(scenario):
    scenario.start()
    client = scenario.client
    assert client.put("/api/gates", json=gate_payload()).status_code == 422
    profile = scenario.configure()
    configured = client.get("/api/gates").json()
    assert configured["valid"]
    assert configured["world_a"][0] == pytest.approx([20, 10])
    assert configured["world_b"][1] == pytest.approx([40, 42])
    saved = client.get("/api/calibrations").json()["profiles"][0]
    assert saved["gates"] == gate_payload()
    invalid = gate_payload()
    invalid["gate_b"] = invalid["gate_a"]
    assert client.put("/api/gates", json=invalid).status_code == 422
    assert client.get("/api/gates").json() == configured
    changed = gate_payload()
    changed["gate_a"] = [[225, 100], [225, 420]]
    changed["allow_reverse"] = True
    assert client.put("/api/gates", json=changed).json()["allow_reverse"]
    snapshot = client.delete("/api/gates").json()
    assert snapshot["gates"] is None
    assert client.get("/api/gates").json() is None
    assert scenario.manager.calibrations.get(profile["id"]).gates is None


@pytest.mark.parametrize("offset", [0, 10], ids=["exact-gate-frame", "interpolated-between-frames"])
def test_real_worker_measures_twenty_meters_in_source_pts_interval(scenario, offset):
    initial = scenario.start()
    profile = scenario.configure()
    snapshot = scenario.complete_traversal(offset=offset)
    assert snapshot.total_tracks == 1
    assert len(snapshot.measurements) == 1
    result = snapshot.measurements[0]
    assert result.status == "valid", result.reasons
    assert result.source_id == "video:synthetic"
    assert result.session_id == initial["session_id"]
    assert result.calibration_id == profile["id"]
    assert result.track_id == 1
    assert result.direction == "A_to_B"
    assert result.gate_a_timestamp_s == pytest.approx(10.3 - offset * 0.006)
    assert result.gate_b_timestamp_s == pytest.approx(11.5 - offset * 0.006)
    assert result.distance_m == pytest.approx(20)
    assert result.elapsed_seconds == pytest.approx(1.2)
    assert result.estimated_speed_kmh == 60.0
    track = snapshot.tracks[0]
    assert track.world_position == pytest.approx((42.5 + offset / 10, 35))
    assert track.image_position == (425 + offset, 350)
    assert track.estimated_speed_kmh == 60.0
    assert track.position_history[-1].timestamp_s == pytest.approx(11.65)
    history = scenario.client.get("/api/measurements").json()
    assert history["independently_validated"] is False
    assert history["summary"]["valid_count"] == 1
    assert history["summary"]["latest_speed_kmh"] == history["summary"]["average_speed_kmh"] == 60.0
    assert history["measurements"][0]["distance_m"] == pytest.approx(20)


def test_pause_rejects_pending_traversal_and_resume_cannot_join_it(scenario):
    scenario.start()
    scenario.configure()
    for x, timestamp in [(150, 10), (175, 10.15), (200, 10.3), (225, 10.45)]:
        scenario.send(x, timestamp)
    assert scenario.manager.snapshot().tracks[0].measurement_state == "measuring"
    paused = scenario.client.post("/api/sessions/pause").json()
    assert paused["state"] == "paused"
    assert len(paused["measurements"]) == 1
    assert paused["measurements"][0]["status"] == "rejected"
    assert any("paused" in reason for reason in paused["measurements"][0]["reasons"])
    assert scenario.client.post("/api/sessions/resume").status_code == 200
    for index, x in enumerate(range(250, 426, 25)):
        scenario.send(x, 10.6 + index * 0.15)
    result = scenario.client.get("/api/measurements").json()
    assert result["summary"]["valid_count"] == 0
    assert result["summary"]["rejected_count"] == 1
    assert all(item["estimated_speed_kmh"] is None for item in result["measurements"])


def test_video_paused_during_inference_preserves_frame_pts_and_completed_metadata(scenario, monkeypatch):
    detector = BlockingMarkerDetector()
    scenario.manager.detector_factory = lambda *args, **kwargs: detector
    scenario.start()
    scenario.configure()
    completed = scenario.complete_traversal()
    assert completed.tracks[0].measurement_state == "completed"
    assert completed.tracks[0].estimated_speed_kmh == 60
    paused_wait = threading.Event()
    original_wait = scenario.manager._wait_until_running

    def observed_wait():
        if not scenario.manager._run_gate.is_set():
            paused_wait.set()
        return original_wait()

    monkeypatch.setattr(scenario.manager, "_wait_until_running", observed_wait)
    detector.block_x = 450
    scenario.source.frames.put((450, 11.8, 640, None))
    assert detector.entered.wait(timeout=2)
    paused = scenario.client.post("/api/sessions/pause")
    assert paused.status_code == 200
    detector.release.set()
    assert detector.returned.wait(timeout=2)
    assert paused_wait.wait(timeout=2), "The decoded video frame must wait for resume after in-flight inference."
    pending = scenario.manager.snapshot()
    assert pending.state == "paused"
    assert pending.frame_index == completed.frame_index
    assert pending.timestamp_s == completed.timestamp_s
    assert pending.tracks[0].measurement_state == "completed"
    assert pending.tracks[0].world_position == completed.tracks[0].world_position
    assert pending.tracks[0].estimated_speed_kmh == 60
    assert len(pending.measurements) == 1
    assert scenario.client.post("/api/sessions/resume").status_code == 200
    resumed = wait_for(scenario.manager, lambda item: item.frame_index == completed.frame_index + 1)
    assert resumed.timestamp_s == 11.8
    assert resumed.tracks[0].position_history[-1].timestamp_s == 11.8
    assert resumed.tracks[0].world_position == pytest.approx((45, 35))
    assert resumed.tracks[0].measurement_state == "completed"
    assert resumed.tracks[0].estimated_speed_kmh == 60
    assert len(resumed.measurements) == 1


def test_live_resume_discards_frames_acquired_before_resume(scenario, monkeypatch):
    source = ControlledSource()
    source.live = True

    def source_factory(*args):
        scenario.sources.append(source)
        return source

    detector = BlockingMarkerDetector()
    scenario.manager.source_factory = source_factory
    scenario.manager.detector_factory = lambda *args, **kwargs: detector
    scenario.start(source_type="camera", camera_index=0)
    scenario.configure()
    before_pause = scenario.send(150, 10)
    detector.block_x = 175
    source.frames.put((175, 10.15, 640, None))
    assert detector.entered.wait(timeout=2)
    assert scenario.client.post("/api/sessions/pause").status_code == 200
    # The acquisition worker remains live during pause, but these packets must
    # never become the first measurement position after resume.
    source.frames.put((225, 10.45, 640, None))
    wait_for(scenario.manager, lambda item: source.index == 4 and scenario.manager._queue.qsize() == 1)
    stale_packet_requested = threading.Event()
    next_packet_requested = threading.Event()
    original_get = scenario.manager._queue.get

    def observed_get(*args, **kwargs):
        if stale_packet_requested.is_set():
            next_packet_requested.set()
        packet = original_get(*args, **kwargs)
        if packet.index == 4:
            stale_packet_requested.set()
        return packet

    monkeypatch.setattr(scenario.manager._queue, "get", observed_get)
    detector.release.set()
    assert detector.returned.wait(timeout=2)
    assert scenario.client.post("/api/sessions/resume").status_code == 200
    assert stale_packet_requested.wait(timeout=2)
    assert next_packet_requested.wait(timeout=2), "The worker must skip the queued pre-resume acquisition."
    stale = scenario.manager.snapshot()
    assert stale.frame_index == before_pause.frame_index
    assert stale.timestamp_s == before_pause.timestamp_s
    assert stale.tracks[0].world_position == before_pause.tracks[0].world_position
    fresh = scenario.send(250, 10.6)
    assert fresh.timestamp_s == 10.6
    observed = next(track for track in fresh.tracks if track.missed == 0)
    assert observed.world_position == pytest.approx((25, 35))
    assert observed.measurement_state == "waiting"
    assert all(sample.timestamp_s not in {10.15, 10.45} for sample in observed.position_history)
    for index, x in enumerate(range(275, 426, 25)):
        final = scenario.send(x, 10.75 + index * 0.15)
    assert final.measurement_summary["valid_count"] == 0
    assert final.measurements[0].status == "rejected"
    assert final.measurements[0].estimated_speed_kmh is None


def test_stop_finalizes_incomplete_sequence_and_restart_clears_it(scenario):
    scenario.start()
    scenario.configure()
    for x, timestamp in [(150, 10), (175, 10.15), (200, 10.3), (225, 10.45)]:
        scenario.send(x, timestamp)
    assert scenario.manager.snapshot().tracks[0].measurement_state == "measuring"
    # Release the controlled reader before stop so shutdown cannot block on test I/O.
    scenario.source.frames.put((250, 10.6, 640, None))
    scenario.source.frames.put(None)
    stopped = scenario.client.post("/api/sessions/stop").json()
    assert stopped["state"] == "stopped"
    assert len(stopped["measurements"]) == 1
    assert stopped["measurements"][0]["status"] == "rejected"
    assert stopped["measurements"][0]["estimated_speed_kmh"] is None
    restarted = scenario.start()
    assert restarted["measurements"] == []
    assert restarted["calibration_status"] == "required"


def test_uncalibrated_pipeline_tracks_without_world_positions_or_speeds(scenario):
    scenario.start()
    snapshot = scenario.complete_traversal()
    assert snapshot.total_tracks == 1
    assert snapshot.calibration_status == "required"
    assert snapshot.measurement_status == "Calibration required"
    assert not snapshot.measurements
    assert snapshot.tracks[0].world_position is None
    assert snapshot.tracks[0].estimated_speed_kmh is None
    assert snapshot.tracks[0].history
    assert all(sample.world_position is None for sample in snapshot.tracks[0].position_history)


def test_fallback_timing_rejects_crossings_without_fabricated_speed(scenario):
    scenario.start()
    scenario.configure()
    for index, x in enumerate(range(150, 426, 25)):
        snapshot = scenario.send(x, 10 + index * 0.15, warning="Missing PTS; nominal-rate diagnostic timeline.")
    assert snapshot.calibration_status == "ready"
    assert snapshot.measurement_summary["valid_count"] == 0
    assert not snapshot.measurements
    assert snapshot.tracks[0].world_position is None
    assert any("diagnostic fallback" in reason for reason in snapshot.tracks[0].position_diagnostics)
    assert snapshot.tracks[0].estimated_speed_kmh is None


def test_nonmonotonic_source_time_is_visible_and_cannot_complete_speed(scenario):
    scenario.start()
    scenario.configure()
    for x, timestamp in [(150, 10), (175, 10.15), (200, 10.3), (225, 10.45)]:
        scenario.send(x, timestamp)
    scenario.source.frames.put((250, 10.45, 640, None))
    snapshot = wait_for(scenario.manager, lambda item: item.state == "error")
    assert "strictly increasing source timestamps" in snapshot.error
    scenario.manager._worker.join(timeout=2)
    snapshot = scenario.manager.snapshot()
    assert snapshot.measurement_summary["valid_count"] == 0
    assert snapshot.measurements[0].status == "rejected"
    assert snapshot.measurements[0].estimated_speed_kmh is None


def test_changed_resolution_disables_mapping_and_gates(scenario):
    scenario.start()
    scenario.configure()
    snapshot = scenario.send(175, 10, width=800)
    assert snapshot.width == snapshot.geometry.width == 800
    assert snapshot.calibration_status == "incompatible"
    assert snapshot.calibration_id is None
    assert snapshot.gates is None
    assert snapshot.measurement_status == "Calibration required"
    assert snapshot.tracks[0].world_position is None
    assert snapshot.tracks[0].estimated_speed_kmh is None
    assert any("geometry changed" in warning for warning in snapshot.calibration_warnings)


@pytest.mark.parametrize("action", ["invalidate", "edit", "delete"])
def test_manual_or_profile_changes_remove_stale_speed_labels(scenario, action):
    scenario.start()
    profile = scenario.configure()
    scenario.complete_traversal()
    assert scenario.manager.snapshot().tracks[0].estimated_speed_kmh == 60
    if action == "invalidate":
        response = scenario.client.post("/api/calibration/invalidate", json={"reason": "Camera zoom changed."})
    elif action == "edit":
        payload = calibration_payload()
        payload["name"] = "Revised references"
        response = scenario.client.put(f"/api/calibrations/{profile['id']}", json=payload)
    else:
        response = scenario.client.delete(f"/api/calibrations/{profile['id']}")
    assert response.status_code == 200, response.text
    snapshot = scenario.client.get("/api/session").json()
    assert snapshot["calibration_status"] == "required"
    assert snapshot["calibration_id"] is None
    assert snapshot["gates"] is None
    assert snapshot["tracks"][0]["estimated_speed_kmh"] is None
    assert snapshot["tracks"][0]["world_position"] is None
    assert snapshot["measurement_summary"]["latest_speed_kmh"] is None
    assert snapshot["measurement_summary"]["average_speed_kmh"] is None
    assert len(snapshot["measurements"]) == 1  # Completed history remains reviewable.


def test_history_clear_and_overlays_update_without_extra_source_frames(scenario):
    scenario.start()
    scenario.configure()
    scenario.complete_traversal()
    previous_frame = scenario.manager.frame()
    settings = {"boxes": False, "trajectories": False, "contact_points": False,
                "gates": False, "grid": False, "speeds": False}
    response = scenario.client.put("/api/overlays", json=settings)
    assert response.status_code == 200
    assert response.json()["overlays"] == settings
    assert scenario.manager.frame() != previous_frame
    assert response.json()["frame_index"] == scenario.source.index
    assert scenario.client.put("/api/overlays", json={"unknown": True}).status_code == 422
    cleared = scenario.client.delete("/api/measurements").json()
    assert cleared["measurements"] == []
    assert cleared["measurement_summary"]["valid_count"] == 0
    assert cleared["tracks"][0]["estimated_speed_kmh"] is None
    assert cleared["calibration_status"] == "ready"
    assert cleared["gates"]["valid"]


def test_stop_restart_source_change_and_reset_isolate_session_state(scenario):
    first = scenario.start()
    profile = scenario.configure()
    scenario.complete_traversal()
    frozen = scenario.client.post("/api/calibration/freeze").json()
    scenario.finish()
    stopped = scenario.client.post("/api/sessions/stop").json()
    assert stopped["state"] == "stopped"
    assert stopped["measurement_summary"]["valid_count"] == 1
    second = scenario.start(source_type="camera", camera_index=3)
    assert second["session_id"] != first["session_id"]
    assert second["source_id"] == "camera:3"
    assert second["calibration_status"] == "required"
    assert second["calibration_id"] is None
    assert second["gates"] is None
    assert second["measurements"] == []
    assert second["tracks"][0]["estimated_speed_kmh"] is None
    assert scenario.client.get(frozen["image_url"]).status_code == 404
    assert scenario.client.post(f"/api/calibrations/{profile['id']}/activate", json={"confirm_stationary": True}).status_code == 422
    scenario.finish()
    reset = scenario.client.post("/api/sessions/reset").json()
    assert reset["state"] == "idle"
    assert reset["source_id"] is None
    assert reset["measurements"] == []
    assert reset["geometry"] is None
    assert reset["gates"] is None
    assert scenario.client.get("/api/frame").status_code == 404
    assert len(scenario.client.get("/api/calibrations").json()["profiles"]) == 1


def test_persisted_homography_is_recomputed_and_corrupt_json_is_reported(scenario):
    scenario.start()
    created = scenario.client.post("/api/calibrations", json=calibration_payload()).json()
    path = scenario.manager.calibrations.directory / f"{created['id']}.json"
    stored = json.loads(path.read_text(encoding="utf-8"))
    stored["diagnostics"]["homography"] = [[1, 0, 0], [0, 1, 0], [0, 0, 1]]
    path.write_text(json.dumps(stored), encoding="utf-8")
    response = scenario.client.post(f"/api/calibrations/{created['id']}/activate", json={"confirm_stationary": True})
    assert response.status_code == 200
    assert scenario.client.put("/api/gates", json=gate_payload()).json()["world_a"][0] == pytest.approx([20, 10])
    path.write_text("{invalid JSON", encoding="utf-8")
    response = scenario.client.get("/api/calibrations")
    assert response.status_code == 422
    assert "unreadable" in response.json()["detail"]
    with pytest.raises(KeyError, match="Unknown calibration"):
        scenario.manager.calibrations.get("../outside-profile")


def test_phase3_exports_retain_measurements_quality_and_original_profile_after_invalidation(scenario):
    scenario.start()
    profile = scenario.configure()
    snapshot = scenario.complete_traversal()
    assert snapshot.measurements[0].estimated_speed_kmh == 60
    scenario.finish()
    client = scenario.client
    before = client.get("/api/exports/measurements?format=json")
    assert before.status_code == 200
    assert "attachment" in before.headers["content-disposition"]
    result = before.json()["measurements"][0]
    polled = client.get("/api/session").json()["measurements"][0]
    assert "position_samples" not in polled
    assert "calibration_metadata" not in polled
    assert polled["diagnostics"]["retained_position_samples"] > 0
    assert result["independently_validated"] is False
    assert result["calibration_metadata"]["calibration_id"] == profile["id"]
    assert result["diagnostics"]["gate_a_interpolation_interval_s"] == pytest.approx(.15)
    assert result["position_samples"][-1]["bbox"]
    assert "source_label" not in before.json()
    assert "image" not in result["calibration_metadata"]
    client.post("/api/calibration/invalidate", json={})
    after = client.get("/api/exports/measurements?format=json").json()
    assert after["measurements"][0] == result
    rows = list(csv.DictReader(io.StringIO(client.get("/api/exports/measurements?format=csv").text)))
    assert len(rows) == 1
    assert float(rows[0]["estimated_speed_kmh"]) == 60
    assert json.loads(rows[0]["calibration_metadata"])["calibration_id"] == profile["id"]
    assert float(rows[0]["diagnostic_gate_a_interpolation_interval_s"]) == pytest.approx(.15)


def test_phase3_profile_reports_measured_stages_without_altering_source_timestamps(scenario):
    scenario.start()
    scenario.configure()
    snapshot = scenario.complete_traversal()
    scenario.finish()
    assert snapshot.tracking_diagnostics["active_tracks"] == 1
    assert snapshot.tracking_diagnostics["potential_id_switches"] == 0
    assert snapshot.tracks[0].age_s > 0
    assert snapshot.tracks[0].observation_gap_s == pytest.approx(.15)
    assert set(snapshot.pipeline_profile) == {"tracking_ms", "projection_ms", "gate_events_ms", "decode_ms", "undistortion_ms"}
    assert all(value >= 0 for value in snapshot.pipeline_profile.values())
    response = scenario.client.get("/api/session")
    assert float(response.headers["X-RoadLens-Response-Ms"]) >= 0
    profile = scenario.client.get("/api/performance").json()
    assert profile["pipeline_latest_ms"] == snapshot.pipeline_profile
    assert profile["processed_fps"] > 0
    assert profile["dropped_frames"] == 0
    assert any(item["route"] == "GET /api/session" for item in profile["response_setup"]["routes"])
    assert snapshot.measurements[0].elapsed_seconds == pytest.approx(1.2)


def test_empty_measurement_exports_are_usable_and_reject_unknown_formats(scenario):
    assert scenario.client.get("/api/exports/measurements").json()["measurements"] == []
    content = scenario.client.get("/api/exports/measurements?format=csv").text
    reader = csv.DictReader(io.StringIO(content))
    assert "estimated_speed_kmh" in reader.fieldnames
    assert list(reader) == []
    assert scenario.client.get("/api/exports/measurements?format=xlsx").status_code == 422
