"""Synthetic camera geometry and image-target tests; no physical camera evidence."""

import json
from types import SimpleNamespace
from uuid import uuid4

import cv2
import numpy as np
import pytest
from fastapi import FastAPI
from fastapi.responses import JSONResponse
from fastapi.testclient import TestClient
from pydantic import ValidationError

from roadlens.calibration import CalibrationTransform
from roadlens.calibration_models import CalibrationInput, Correspondence, ImageGeometry
from roadlens.camera_api import camera_routes
from roadlens.camera_calibration import FrameUndistorter, calibrate_camera, checkerboard_object_points, fit_camera
from roadlens.camera_models import CameraCalibrationInput, CameraIntrinsicProfile
from roadlens.camera_store import CameraProfileStore
from roadlens.schemas import SessionSnapshot


def configuration():
    return CameraCalibrationInput(name="Synthetic target", camera_configuration_id="synthetic-camera",
                                  checkerboard={"inner_columns": 9, "inner_rows": 6, "square_size_mm": 25})


def synthetic_corners():
    config = configuration()
    matrix = np.array([[600., 0, 320], [0, 610., 240], [0, 0, 1]])
    distortion = np.array([-.12, .03, .001, -.001, .001])
    object_points = checkerboard_object_points(config)
    corners = []
    for i in range(10):
        rotation = np.array([-.3+.065*i, .22*np.cos(i), -.18+.035*i])
        translation = np.array([-125.+22*(i % 4), -90.+32*(i % 3), 570.+40*(i % 5)])
        image, _ = cv2.projectPoints(object_points, rotation, translation, matrix, distortion)
        corners.append(image)
    return corners, matrix, distortion


@pytest.fixture
def profile():
    corners, _, _ = synthetic_corners()
    return fit_camera(corners, (640, 480), configuration(), provenance="synthetic")


def checkerboard_images():
    # Pixel-only planar renders exercise OpenCV's real corner finder and fitter.
    board = np.zeros((7*60, 10*60), np.uint8)
    for y in range(7):
        for x in range(10):
            if (x+y) % 2 == 0:
                board[y*60:(y+1)*60, x*60:(x+1)*60] = 255
    matrix = np.array([[600., 0, 320], [0, 610., 240], [0, 0, 1]])
    outer = np.array([[-25., -25, 0], [225, -25, 0], [225, 150, 0], [-25, 150, 0]])
    pixels = np.array([[0., 0], [599, 0], [599, 419], [0, 419]], np.float32)
    images = []
    for i in range(8):
        rotation = np.array([-.35+.1*i, .25*np.cos(i), -.16+.05*i])
        translation = np.array([-130.+24*(i % 4), -85.+30*(i % 3), 560.+30*(i % 4)])
        projected, _ = cv2.projectPoints(outer, rotation, translation, matrix, np.zeros(5))
        homography = cv2.getPerspectiveTransform(pixels, projected.reshape(-1, 2).astype(np.float32))
        image = cv2.warpPerspective(board, homography, (640, 480), borderValue=180)
        ok, encoded = cv2.imencode(".png", image)
        assert ok
        images.append((f"synthetic-target-{i}.png", encoded.tobytes()))
    return images


def test_known_synthetic_intrinsics_are_recovered(profile):
    _, matrix, distortion = synthetic_corners()
    assert profile.rms_reprojection_error_px < .0001
    assert np.asarray(profile.camera_matrix) == pytest.approx(matrix, abs=.01)
    assert profile.distortion_coefficients == pytest.approx(distortion, abs=.001)
    assert len(profile.per_image_error_px) == profile.used_image_count == 10
    assert profile.provenance == "synthetic"
    assert "speed accuracy" in profile.warnings[0]


def test_real_corner_finder_runs_on_synthetic_image_set():
    images = checkerboard_images()
    ok, blank = cv2.imencode(".png", np.full((240, 320), 127, np.uint8))
    assert ok
    profile = calibrate_camera([("blank-other-resolution.png", blank.tobytes())]+images + [images[0]], configuration())
    assert profile.used_image_count >= 6
    assert profile.rejected_image_count >= 1
    assert any(image.reason == "Duplicate image." for image in profile.images)
    assert profile.rms_reprojection_error_px < .5
    assert all(image.reprojection_error_px is not None for image in profile.images if image.accepted)


def test_points_roundtrip_and_road_coordinates_remain_consistent(profile):
    _, matrix, distortion = synthetic_corners()
    normalized = np.array([[-.3, -.2, 1], [.25, -.15, 1], [.28, .22, 1], [-.25, .24, 1]])
    distorted, _ = cv2.projectPoints(normalized, np.zeros(3), np.zeros(3), matrix, distortion)
    expected = (matrix @ normalized.T).T[:, :2]
    corrected = FrameUndistorter(profile).undistort_points(distorted.reshape(-1, 2).tolist())
    assert np.asarray(corrected) == pytest.approx(expected, abs=.001)
    transform = CalibrationTransform(CalibrationInput(name="Corrected plane", source_id="synthetic",
        geometry=profile.geometry, points=[Correspondence(image=tuple(point), world=world)
            for point, world in zip(corrected, [(0, 0), (20, 0), (20, 10), (0, 10)])]))
    assert transform.project(corrected[0]) == pytest.approx((0, 0), abs=1e-5)
    assert transform.compatible("synthetic", profile.geometry)
    assert not transform.compatible("synthetic", ImageGeometry(width=640, height=480))


def test_undistortion_retains_shape_and_caches_maps(profile):
    undistorter = FrameUndistorter(profile)
    maps = undistorter._maps
    image = np.indices((480, 640)).sum(axis=0).astype(np.uint8)
    assert undistorter.apply(image).shape == image.shape
    assert undistorter.apply(np.dstack([image]*3)).shape == (480, 640, 3)
    assert undistorter._maps is maps
    assert undistorter.geometry.coordinate_space == "undistorted"
    assert undistorter.geometry.intrinsic_profile_id == profile.id


def test_identity_model_retains_pixels(profile):
    model = profile.model_copy(update={"distortion_coefficients": [0.]*5})
    image = np.random.default_rng(4).integers(0, 255, (480, 640, 3), dtype=np.uint8)
    assert np.array_equal(FrameUndistorter(model).apply(image), image)


@pytest.mark.parametrize("shape", [(240, 320), (640, 480, 3), (480, 640, 1, 1)])
def test_geometry_change_blocks_undistortion(profile, shape):
    with pytest.raises(ValueError, match="resolution changed"):
        FrameUndistorter(profile).apply(np.zeros(shape, np.uint8))


@pytest.mark.parametrize("change", [
    {"camera_matrix": [[0, 0, 320], [0, 610, 240], [0, 0, 1]]},
    {"camera_matrix": [[600, 0, 320], [0, 610, 240], [0, 1, 1]]},
    {"camera_matrix": [[600, 2, 320], [0, 610, 240], [0, 0, 1]]},
    {"camera_matrix": [[600, 0, 900], [0, 610, 240], [0, 0, 1]]},
    {"camera_matrix": [[600, 0, 320], [0, 610, 240]]},
    {"distortion_coefficients": [0, 0, 0, 0, 0, 0]},
    {"distortion_coefficients": [0, 0, 0, 0, 0, -10, 0, 0]},
    {"distortion_coefficients": [-10, 0, 0, 0, 0]},
    {"distortion_coefficients": [0, 0, 2, 0, 0]},
    {"distortion_coefficients": [float("nan"), 0, 0, 0, 0]},
    {"rms_reprojection_error_px": float("inf")},
    {"per_image_error_px": [-1]*10},
    {"used_image_count": 9},
    {"id": "../../escape"},
    {"pixel_coordinate_policy": "cropped"},
])
def test_invalid_profiles_are_rejected(profile, change):
    with pytest.raises(ValidationError):
        CameraIntrinsicProfile.model_validate(profile.model_dump() | change)


def test_geometry_requires_coordinate_space_profile_pair():
    with pytest.raises(ValidationError):
        ImageGeometry(width=640, height=480, coordinate_space="undistorted")
    with pytest.raises(ValidationError):
        ImageGeometry(width=640, height=480, intrinsic_profile_id="some-id")


def test_profile_store_is_immutable_and_roundtrips(tmp_path, profile):
    store = CameraProfileStore(tmp_path)
    assert store.list() == []
    store.put(profile)
    assert store.get(profile.id) == profile
    assert store.put(profile) == profile
    with pytest.raises(ValueError, match="immutable"):
        store.put(profile.model_copy(update={"name": "Replacement"}))
    with pytest.raises(KeyError):
        store.get("../../elsewhere")
    assert len(list(tmp_path.glob("*.json"))) == 1
    store.delete(profile.id)
    assert store.list() == []


def test_corrupt_and_mismatched_store_files_fail_closed(tmp_path, profile):
    store = CameraProfileStore(tmp_path)
    path = tmp_path / f"{profile.id}.json"
    path.write_text("invalid")
    with pytest.raises(ValueError, match="unreadable"):
        store.get(profile.id)
    path.write_text(profile.model_copy(update={"id": str(uuid4())}).model_dump_json())
    with pytest.raises(ValueError, match="filename"):
        store.get(profile.id)


def test_insufficient_duplicate_and_invalid_target_images_fail():
    images = checkerboard_images()
    with pytest.raises(ValueError, match="six"):
        calibrate_camera(images[:5], configuration())
    with pytest.raises(ValueError, match="Only 1 usable"):
        calibrate_camera([images[0]]*6, configuration())
    with pytest.raises(ValueError, match="could not be decoded"):
        calibrate_camera([(f"bad{i}.png", b"bad") for i in range(6)], configuration())


def test_fit_rejects_identical_views_and_invalid_corners():
    corners, _, _ = synthetic_corners()
    with pytest.raises(ValueError, match="diversity"):
        fit_camera([corners[0]]*6, (640, 480), configuration())
    with pytest.raises(ValueError, match="invalid"):
        fit_camera([np.array([[float("nan"), 1]])]*6, (640, 480), configuration())


def camera_client(tmp_path):
    snapshot = SessionSnapshot()
    manager = SimpleNamespace(camera_profiles=CameraProfileStore(tmp_path),
        configure_camera_model=lambda identifier, confirm: snapshot if not identifier or confirm else (_ for _ in ()).throw(ValueError("Confirm unchanged lens.")),
        camera_preview=lambda identifier, corrected: b"jpeg-corrected" if corrected else b"jpeg-source")
    manager.delete_camera_profile = manager.camera_profiles.delete
    app = FastAPI()
    app.include_router(camera_routes(manager))

    @app.exception_handler(ValueError)
    async def invalid(request, error):
        return JSONResponse({"detail": str(error)}, status_code=422)

    @app.exception_handler(KeyError)
    async def missing(request, error):
        return JSONResponse({"detail": str(error)}, status_code=404)
    return TestClient(app)


def test_camera_api_profile_exchange_and_explicit_activation(tmp_path, profile):
    client = camera_client(tmp_path)
    assert client.get("/api/camera-profiles").json() == {"profiles": []}
    assert client.post("/api/camera-profiles/import", json=profile.model_dump()).status_code == 200
    exported = client.get(f"/api/camera-profiles/{profile.id}/export")
    assert exported.json() == profile.model_dump(mode="json")
    assert client.put("/api/camera-model", json={"profile_id": profile.id}).status_code == 422
    assert client.put("/api/camera-model", json={"profile_id": profile.id, "confirm_unchanged": True}).status_code == 200
    assert client.get(f"/api/camera-profiles/{profile.id}/preview?corrected=false").content == b"jpeg-source"
    assert client.delete(f"/api/camera-profiles/{profile.id}").status_code == 200
    assert client.get(f"/api/camera-profiles/{profile.id}").status_code == 404


def test_camera_api_synthetic_image_upload(tmp_path):
    client = camera_client(tmp_path)
    response = client.post("/api/camera-profiles/calibrate",
        data={"configuration": configuration().model_dump_json()},
        files=[("files", (filename, content, "image/png")) for filename, content in checkerboard_images()])
    assert response.status_code == 200, response.text
    assert response.json()["used_image_count"] >= 6
    assert response.json()["rms_reprojection_error_px"] < .5
    assert len(client.get("/api/camera-profiles").json()["profiles"]) == 1


def test_camera_api_rejects_bad_metadata_and_missing_images(tmp_path):
    client = camera_client(tmp_path)
    response = client.post("/api/camera-profiles/calibrate", data={"configuration": "{}"},
                           files=[("files", ("a.png", b"bad", "image/png"))])
    assert response.status_code == 422
