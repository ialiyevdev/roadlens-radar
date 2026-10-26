"""Actual API/session wiring with synthetic source and detector adapters only."""

import json
import threading
import time
from uuid import uuid4

import cv2
import numpy as np
import pytest

from roadlens.camera_models import CameraIntrinsicProfile
from roadlens.camera_calibration import FrameUndistorter
from test_phase2_api import scenario, wait_for, BlockingMarkerDetector


def camera_profile(width=640, height=480):
    return CameraIntrinsicProfile(name="SYNTHETIC runtime lens", id=str(uuid4()), camera_configuration_id="synthetic-adapter",
        width=width, height=height, camera_matrix=[[500,0,width/2],[0,500,height/2],[0,0,1]],
        distortion_coefficients=[-.1,.02,0,0,0], rms_reprojection_error_px=0,
        per_image_error_px=[0]*6, used_image_count=6, rejected_image_count=0, provenance="synthetic")


def test_camera_model_requires_pause_confirmation_and_matching_geometry(scenario):
    scenario.start()
    profile = camera_profile()
    scenario.manager.camera_profiles.put(profile)
    client = scenario.client
    assert client.put("/api/camera-model",json={"profile_id":profile.id,"confirm_unchanged":True}).status_code == 409
    client.post("/api/sessions/pause")
    assert client.put("/api/camera-model",json={"profile_id":profile.id}).status_code == 422
    wrong = camera_profile(width=800)
    scenario.manager.camera_profiles.put(wrong)
    assert client.put("/api/camera-model",json={"profile_id":wrong.id,"confirm_unchanged":True}).status_code == 422
    scenario.finish()


def test_intrinsics_invalidate_road_references_and_freeze_corrected_pixels(scenario):
    scenario.start()
    road = scenario.configure()
    client = scenario.client
    frozen = client.post("/api/calibration/freeze").json()
    client.post("/api/sessions/pause")
    profile = camera_profile()
    scenario.manager.camera_profiles.put(profile)
    result = client.put("/api/camera-model",json={"profile_id":profile.id,"confirm_unchanged":True})
    assert result.status_code == 200, result.text
    body = result.json()
    assert body["geometry"]["coordinate_space"] == "undistorted"
    assert body["geometry"]["intrinsic_profile_id"] == profile.id
    assert body["calibration_status"] == "required"
    assert body["tracks"] == []
    assert client.get(frozen["image_url"]).status_code == 404
    assert client.post(f"/api/calibrations/{road['id']}/activate",json={"confirm_stationary":True}).status_code == 422
    corrected = client.post("/api/calibration/freeze").json()
    image = FrameUndistorter(profile).apply(scenario.source.last_image)
    ok, expected = cv2.imencode(".jpg",image,[cv2.IMWRITE_JPEG_QUALITY,95])
    assert ok and client.get(corrected["image_url"]).content == expected.tobytes()
    assert client.get(f"/api/camera-profiles/{profile.id}/preview?corrected=false").status_code == 200
    archived = client.post("/api/field-sessions/from-observation",json={"name":"Synthetic corrected observation","provenance":"synthetic"})
    assert archived.status_code == 200, archived.text
    assert archived.json()["calibration_metadata"]["intrinsic"]["id"] == profile.id
    assert archived.json()["camera"]["geometry"]["coordinate_space"] == "undistorted"
    client.post("/api/sessions/resume")
    next_frame = scenario.send(200,10.1)
    assert all(track.id > 1 for track in next_frame.tracks)
    assert next_frame.camera_model_id == profile.id
    assert next_frame.pipeline_profile["undistortion_ms"] >= 0
    scenario.finish()


def test_inflight_recorded_frame_is_reinferred_after_paused_camera_change(scenario):
    detector = BlockingMarkerDetector()
    scenario.manager.detector_factory = lambda *args,**kwargs: detector
    scenario.start()
    detector.block_x = 210
    scenario.source.frames.put((210,10.1,640,None))
    assert detector.entered.wait(timeout=3)
    scenario.client.post("/api/sessions/pause")
    profile = camera_profile()
    scenario.manager.camera_profiles.put(profile)
    response = scenario.client.put("/api/camera-model",json={"profile_id":profile.id,"confirm_unchanged":True})
    assert response.status_code == 200, response.text
    detector.release.set()
    scenario.client.post("/api/sessions/resume")
    snapshot = wait_for(scenario.manager,lambda state:state.frame_index == 2)
    assert snapshot.timestamp_s == pytest.approx(10.1)
    assert snapshot.geometry.coordinate_space == "undistorted"
    assert snapshot.tracks[0].id > 1
    assert snapshot.timing_diagnostics["source_frame_count"] == 2
    assert snapshot.timing_diagnostics["processed_frame_count"] == 2
    scenario.finish()


def test_field_capture_reports_final_time_original_status_and_timestamp_diagnostics(scenario):
    scenario.start()
    scenario.configure()
    scenario.complete_traversal()
    scenario.finish()
    client = scenario.client
    result = client.post("/api/field-sessions/from-observation",json={"name":"Synthetic controlled observation","provenance":"synthetic","partition":"held_out"})
    assert result.status_code == 200,result.text
    field = result.json()
    assert field["started_at"] and field["ended_at"]
    assert field["timing_summary"]["processed_frame_count"] > 1
    assert field["measurements"][0]["measurement"]["status"] == "valid"
    assert field["measurements"][0]["measurement"]["estimated_speed_kmh"] == 60
    assert field["calibration_metadata"]["road_plane"]["diagnostics"]["check_error_m"] < 1e-6
    assert client.get(f"/api/field-sessions/{field['id']}/eligibility").json()["real_world_reference_available"] is False
    annotations = client.get(f"/api/field-sessions/{field['id']}/annotations").json()
    assert annotations["frames"] == [] and annotations["source_id"] == field["source"]["source_id"]
    assert client.delete(f"/api/field-sessions/{field['id']}").status_code == 200
    assert client.get(f"/api/field-sessions/{field['id']}/annotations").status_code == 404


def test_repeated_uploads_reuse_one_video_and_source_catalog_persists(scenario,tmp_path):
    path = tmp_path / "generated.avi"
    writer = cv2.VideoWriter(str(path),cv2.VideoWriter_fourcc(*"FFV1"),10,(96,64))
    assert writer.isOpened()
    for _ in range(3): writer.write(np.zeros((64,96,3),np.uint8))
    writer.release()
    content = path.read_bytes()
    first = scenario.client.post("/api/videos",files={"file":("first.avi",content,"video/x-msvideo")})
    second = scenario.client.post("/api/videos",files={"file":("again.avi",content,"video/x-msvideo")})
    assert first.status_code == second.status_code == 200
    assert first.json()["video_id"] == second.json()["video_id"]
    assert len(list(scenario.manager.upload_dir.glob("*.avi"))) == 1
    catalog = scenario.client.get("/api/field-sources").json()["sources"]
    assert len(catalog) == 1 and catalog[0]["relative_path"].endswith(".avi")
    assert not catalog[0]["relative_path"].startswith(str(tmp_path))
    assert catalog[0]["content_sha256"]


def test_camera_change_during_encoding_cannot_publish_old_coordinate_frame(scenario,monkeypatch):
    scenario.start()
    profile = camera_profile()
    scenario.manager.camera_profiles.put(profile)
    encoding = threading.Event()
    released = threading.Event()
    armed = threading.Event()
    original = cv2.imencode

    def encode(*args,**kwargs):
        if armed.is_set() and threading.current_thread().name == "roadlens-processing":
            encoding.set()
            assert released.wait(timeout=4)
        return original(*args,**kwargs)

    monkeypatch.setattr(cv2,"imencode",encode)
    armed.set()
    scenario.source.frames.put((210,10.1,640,None))
    assert encoding.wait(timeout=3)
    scenario.client.post("/api/sessions/pause")
    changed = scenario.client.put("/api/camera-model",json={"profile_id":profile.id,"confirm_unchanged":True}).json()
    revision = changed["preview_revision"]
    armed.clear()
    released.set()
    time.sleep(.04)
    current = scenario.manager.snapshot()
    assert current.frame_index == 1
    assert current.preview_revision == revision
    assert current.geometry.coordinate_space == "undistorted"
    assert current.tracks == []
    scenario.client.post("/api/sessions/resume")
    current = scenario.send(220,10.2)
    assert current.frame_index == 3
    assert current.tracks[0].id > 1
    assert current.timing_diagnostics["skipped_source_frames"] == 1
    scenario.finish()


def test_camera_change_while_freezing_cannot_reintroduce_old_coordinate_frame(scenario, monkeypatch):
    from concurrent.futures import ThreadPoolExecutor
    from roadlens.capture import SourceError

    scenario.start()
    scenario.client.post("/api/sessions/pause")
    profile = camera_profile()
    scenario.manager.camera_profiles.put(profile)
    encoding, released = threading.Event(), threading.Event()
    original = cv2.imencode
    def encode(*args, **kwargs):
        if threading.current_thread().name.startswith("freeze-qa"):
            encoding.set()
            assert released.wait(timeout=4)
        return original(*args, **kwargs)
    monkeypatch.setattr(cv2, "imencode", encode)
    with ThreadPoolExecutor(max_workers=1, thread_name_prefix="freeze-qa") as pool:
        pending = pool.submit(scenario.manager.freeze_frame)
        assert encoding.wait(timeout=3)
        scenario.manager.configure_camera_model(profile.id, True)
        released.set()
        with pytest.raises(SourceError, match="camera model changed"):
            pending.result(timeout=3)
    assert not scenario.manager._frozen
    assert scenario.manager.freeze_frame()["geometry"]["coordinate_space"] == "undistorted"
    scenario.finish()


def test_imported_measurement_from_another_source_is_retained_but_excluded(scenario):
    from roadlens.field_alignment import match_diagnostics
    from roadlens.field_models import FieldSessionInput
    from pathlib import Path

    fixture = json.loads((Path(__file__).resolve().parents[2] / "examples/field/synthetic_field_session.json").read_text(encoding="utf-8"))
    fixture["measurements"][0]["measurement"]["source_id"] = "a-different-video"
    stored = scenario.manager.field_store.put(FieldSessionInput.model_validate(fixture))
    event = fixture["measurements"][0]["event_id"]
    result = match_diagnostics(stored,event)
    assert not result["eligible"]
    assert "measurement_source_mismatch" in result["exclusion_reasons"]
    assert stored.measurements[0].measurement.status == "valid"


def test_live_observation_source_ids_bind_the_original_measurement_session(scenario):
    from roadlens.field_alignment import match_diagnostics
    from roadlens.field_models import FieldSessionInput
    from pathlib import Path

    fixture = json.loads((Path(__file__).resolve().parents[2] / "examples/field/synthetic_field_session.json").read_text(encoding="utf-8"))
    for wrapped in fixture["measurements"]:
        wrapped["measurement"]["source_id"] = "camera:0"
        wrapped["measurement"]["session_id"] = "observation-A"
    fixture["source"]["source_id"] = "camera:0:observation:observation-A"
    stored = scenario.manager.field_store.put(FieldSessionInput.model_validate(fixture))
    result = match_diagnostics(stored,fixture["measurements"][0]["event_id"])
    assert "measurement_source_mismatch" not in result["exclusion_reasons"]
