"""Normal HTTP/worker wiring with controlled synthetic detections, never a camera."""

import json
import threading

import pytest

from roadlens.traffic_models import TrafficConfiguration
from test_phase2_api import scenario
from test_phase4_integration import camera_profile


def configure(scenario, lines=None, zones=None, **values):
    session = scenario.manager.snapshot()
    config = TrafficConfiguration(source_id=session.source_id, geometry=session.geometry,
        lines=lines if lines is not None else [{"id": "counter", "label": "Synthetic counter",
            "start": [300, 100], "end": [300, 420]}], zones=zones or [], **values)
    return scenario.client.put("/api/traffic/configuration", json=config.model_dump(mode="json"))


def traversal(scenario, start=10):
    for index, x in enumerate(range(160, 361, 20)):
        scenario.send(x, start + index * .1)


def test_traffic_snapshot_is_available_while_first_preview_is_being_encoded(scenario, monkeypatch):
    import cv2
    from test_phase2_api import wait_for

    encoding, released = threading.Event(), threading.Event()
    original = cv2.imencode
    def encode(*args, **kwargs):
        if threading.current_thread().name == "roadlens-processing":
            encoding.set()
            assert released.wait(timeout=4)
        return original(*args, **kwargs)
    monkeypatch.setattr(cv2, "imencode", encode)
    response = scenario.client.post("/api/sessions/start", json={"source_type": "video", "video_id": scenario.video_id})
    assert response.status_code == 200
    wait_for(scenario.manager, lambda item: item.state == "running")
    scenario.source.frames.put((150, 9.8, 640, None))
    assert encoding.wait(timeout=3)
    try:
        current = scenario.client.get("/api/traffic/current")
        assert current.status_code == 200, current.text
        assert current.json()["snapshot"]["camera"]["geometry"]["width"] == 640
        assert scenario.manager.snapshot().frame_index == 0
    finally:
        released.set()
    wait_for(scenario.manager, lambda item: item.frame_index == 1)
    scenario.finish()


def test_counting_without_speed_calibration_retains_source_time_and_autoarchives(scenario):
    scenario.start()
    assert configure(scenario).status_code == 409
    scenario.client.post("/api/sessions/pause")
    response = configure(scenario)
    assert response.status_code == 200, response.text
    scenario.client.post("/api/sessions/resume")
    traversal(scenario)
    current = scenario.client.get("/api/traffic/current").json()
    assert current["analytics"]["summary"]["total_crossings"] == 1
    event = current["snapshot"]["events"][0]
    assert event["timestamp_s"] == pytest.approx(10.7)
    assert event["category"] == "car" and event["status"] == "counted"
    assert event["measured_speed_kmh"] is None
    assert current["analytics"]["speeds"]["n"] == 0
    assert scenario.manager.snapshot().calibration_status == "required"
    assert scenario.manager.snapshot().gates is None
    scenario.finish()
    archived = scenario.manager.traffic_store.get(event["session_id"])
    assert archived["ended_at"] and archived["events"][0]["timestamp_s"] == event["timestamp_s"]
    assert archived["summary"]["total_crossings"] == 1
    json.dumps(archived, allow_nan=False)


def test_paused_counting_does_not_bridge_a_vehicle_across_the_line(scenario):
    scenario.start()
    scenario.client.post("/api/sessions/pause")
    assert configure(scenario).status_code == 200
    scenario.client.post("/api/sessions/resume")
    for index, x in enumerate((180, 200, 220, 240, 260, 280)):
        scenario.send(x, 10 + index * .1)
    scenario.client.post("/api/sessions/pause")
    scenario.client.post("/api/sessions/resume")
    scenario.send(320, 10.7)
    scenario.send(340, 10.8)
    assert scenario.manager.traffic_snapshot()["summary"]["total_crossings"] == 0
    scenario.finish()


def test_saved_counting_config_is_reused_but_events_are_isolated_on_restart(scenario):
    scenario.start()
    scenario.client.post("/api/sessions/pause")
    config = configure(scenario).json()
    scenario.client.post("/api/sessions/resume")
    traversal(scenario)
    first = scenario.manager.traffic_snapshot()
    scenario.finish()
    scenario.start()
    second = scenario.manager.traffic_snapshot()
    assert second["configuration"]["id"] == config["id"]
    assert second["id"] != first["id"]
    assert second["events"] == []
    traversal(scenario)
    assert scenario.manager.traffic_snapshot()["summary"]["total_crossings"] == 1
    scenario.finish()


def test_geometry_change_retires_counting_regions_but_preserves_original_events(scenario):
    scenario.start()
    scenario.client.post("/api/sessions/pause")
    assert configure(scenario).status_code == 200
    scenario.client.post("/api/sessions/resume")
    traversal(scenario)
    previous = scenario.manager.traffic_snapshot()
    scenario.client.post("/api/sessions/pause")
    profile = camera_profile()
    scenario.manager.camera_profiles.put(profile)
    response = scenario.client.put("/api/camera-model", json={"profile_id": profile.id, "confirm_unchanged": True})
    assert response.status_code == 200
    changed = scenario.manager.traffic_snapshot()
    assert changed["configuration"]["geometry"]["coordinate_space"] == "undistorted"
    assert changed["configuration"]["lines"] == []
    assert changed["events"] == previous["events"]
    assert len(changed["configurations"]) > len(previous["configurations"])
    scenario.finish()


def test_source_geometry_and_ground_region_compatibility_are_enforced(scenario):
    scenario.start()
    scenario.client.post("/api/sessions/pause")
    current = scenario.manager.snapshot()
    wrong = TrafficConfiguration(source_id="another-video", geometry=current.geometry)
    assert scenario.client.put("/api/traffic/configuration", json=wrong.model_dump(mode="json")).status_code == 422
    zone = {"id": "ground", "label": "Measured region", "coordinate_space": "ground", "hysteresis": .1,
            "points": [[10, 10], [30, 10], [30, 40], [10, 40]]}
    assert configure(scenario, zones=[zone], calibration_id="missing").status_code == 422
    profile = scenario.configure()
    response = configure(scenario, zones=[zone], calibration_id=profile["id"])
    assert response.status_code == 200, response.text
    zone["points"][0] = [-500, -500]
    assert configure(scenario, zones=[zone], calibration_id=profile["id"]).status_code == 422
    scenario.finish()


def test_traffic_layers_are_independent_of_original_overlay_schema(scenario):
    scenario.start()
    old = scenario.client.get("/api/session").json()["overlays"]
    before = scenario.manager.frame()
    flags = scenario.client.get("/api/traffic/overlays").json()
    flags.update(track_ids=False, vehicle_classes=False, direction_indicators=True)
    response = scenario.client.put("/api/traffic/overlays", json=flags)
    assert response.status_code == 200 and response.json() == flags
    assert scenario.client.get("/api/session").json()["overlays"] == old
    assert scenario.manager.frame() != before
    assert scenario.client.put("/api/traffic/overlays", json={"unsupported": True}).status_code == 422
    scenario.finish()


def test_invalid_source_timing_cannot_create_a_count_or_coverage_bridge(scenario):
    scenario.start()
    scenario.client.post("/api/sessions/pause")
    assert configure(scenario).status_code == 200
    scenario.client.post("/api/sessions/resume")
    scenario.send(220, 10)
    scenario.send(250, 10.1)
    scenario.send(280, 10.2)
    scenario.send(320, 10.3, warning="Missing PTS; nominal timing fallback")
    scenario.send(340, 10.4)
    assert scenario.manager.traffic_snapshot()["summary"]["total_crossings"] == 0
    scenario.finish()


def test_later_valid_speed_is_joined_only_inside_its_completed_gate_interval(scenario):
    scenario.start()
    scenario.client.post("/api/sessions/pause")
    scenario.configure()
    assert configure(scenario).status_code == 200
    scenario.client.post("/api/sessions/resume")
    scenario.complete_traversal()
    current = scenario.manager.traffic_snapshot()
    assert current["events"][0]["measured_speed_kmh"] == 60
    assert current["events"][0]["speed_measurement_id"]
    # A subsequent crossing outside the measured segment cannot borrow that speed.
    scenario.manager._traffic._events[0]["timestamp_s"] = 1
    assert scenario.manager.traffic_snapshot()["events"][0]["measured_speed_kmh"] is None
    scenario.finish()


def test_archive_failure_remains_visible_without_replacing_observation_state(scenario, monkeypatch):
    scenario.start()
    monkeypatch.setattr(scenario.manager.traffic_store, "put", lambda _: (_ for _ in ()).throw(OSError("disk unavailable")))
    scenario.finish()
    assert scenario.manager.snapshot().state == "completed"
    assert scenario.manager.traffic_snapshot()["archive_error"] == "disk unavailable"
