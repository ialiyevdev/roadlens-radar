"""Small synthetic recordings and manual labels; no physical roadway evidence."""

import csv
import hashlib
import io
from concurrent.futures import ThreadPoolExecutor
from types import SimpleNamespace
from uuid import uuid4

import cv2
import numpy as np
import pytest
from fastapi import FastAPI
from fastapi.responses import JSONResponse
from fastapi.testclient import TestClient
from pydantic import ValidationError

from roadlens.annotation_api import AnnotationService, annotation_routes
from roadlens.annotation_metrics import annotation_metrics
from roadlens.annotation_models import AnnotationDocument, ProposalRequest
from roadlens.annotation_store import AnnotationRevisionConflict, AnnotationStore, annotations_csv, parse_annotations
from roadlens.camera_models import CameraIntrinsicProfile
from roadlens.camera_calibration import FrameUndistorter
from roadlens.camera_store import CameraProfileStore
from roadlens.detector import Detection
from roadlens.field_models import FieldSessionInput
from roadlens.field_store import FieldStore
from roadlens.schemas import SessionSnapshot


def truth(identity="vehicle-a", bbox=(5, 10, 20, 30), **changes):
    return dict(identity=identity, category="car", bbox=bbox, occluded=bbox is None,
                partial_visibility=False, entry=False, exit=False) | changes


def prediction(identifier=1, bbox=(5, 10, 20, 30), **changes):
    return dict(predicted_track_id=identifier, category="car", bbox=bbox, confidence=.8) | changes


def document(field, frames=None, **changes):
    return AnnotationDocument(field_session_id=field.id, source_id=field.source.source_id,
        geometry=field.camera.geometry, provenance="synthetic", frames=frames if frames is not None else [
            dict(index=1, timestamp_s=0, reviewed=True, objects=[truth()], predictions=[prediction()]),
            dict(index=2, timestamp_s=.1, reviewed=True, objects=[truth(bbox=None)], predictions=[]),
            dict(index=3, timestamp_s=.2, reviewed=True, objects=[], predictions=[]),
        ], **changes)


class SyntheticDetector:
    name = "Injected synthetic marker detector"

    def __init__(self, weights, confidence, input_size):
        self.calls = 0

    def detect(self, image):
        self.calls += 1
        return [Detection((5., 10., 20., 30.), .8, "car")]


@pytest.fixture
def scenario(tmp_path):
    uploads = tmp_path / "uploads"
    uploads.mkdir()
    path = uploads / "synthetic.avi"
    writer = cv2.VideoWriter(str(path), cv2.VideoWriter_fourcc(*"FFV1"), 10, (64, 48))
    assert writer.isOpened()
    for index in range(12):
        writer.write(np.full((48, 64, 3), index*15, np.uint8))
    writer.release()
    digest = hashlib.sha256(path.read_bytes()).hexdigest()
    fields = FieldStore(tmp_path / "fields")
    field = fields.put(FieldSessionInput(name="Synthetic annotation session",
        source={"source_id": "video:"+digest, "relative_path": path.name, "content_sha256": digest},
        camera={"geometry": {"width": 64, "height": 48}}, provenance="synthetic"))
    manager = SimpleNamespace(field_store=fields, upload_dir=uploads,
        camera_profiles=CameraProfileStore(tmp_path / "camera"), weights_path=tmp_path / "unused.onnx",
        detector_factory=SyntheticDetector, snapshot=lambda: SessionSnapshot(state="paused"))
    service = manager.annotations = AnnotationService(manager)
    yield SimpleNamespace(field=field, manager=manager, service=service, path=path)
    service.close()


@pytest.mark.parametrize("change", [
    {"bbox": [5, 10, 5, 30]}, {"bbox": [-1, 10, 20, 30]}, {"bbox": [5, 10, 65, 30]},
    {"bbox": [5, 10, 20, float("nan")]}, {"bbox": None, "occluded": False},
    {"identity": ""}, {"category": "person"}, {"entry": "yes"},
])
def test_invalid_manual_objects_fail(scenario, change):
    with pytest.raises(ValidationError):
        document(scenario.field, [dict(index=1, timestamp_s=0, objects=[truth(**change)])])


@pytest.mark.parametrize("frames", [
    [dict(index=1, objects=[truth(), truth()])],
    [dict(index=1), dict(index=1)],
    [dict(index=0)],
    [dict(index=True)],
    [dict(index=1, timestamp_s=float("inf"))],
    [dict(index=1, objects=[truth()]), dict(index=2, objects=[truth(category="bus")])],
    [dict(index=1, predictions=[prediction(), prediction()])],
    [dict(index=1, predictions=[prediction(identifier=0)])],
    [dict(index=1, predictions=[prediction(confidence=1.1)])],
])
def test_invalid_frames_fail(scenario, frames):
    with pytest.raises(ValidationError):
        document(scenario.field, frames)


def test_visibility_identity_labels_and_empty_reviewed_frames_roundtrip(scenario):
    data = document(scenario.field)
    data.frames[0].objects[0].partial_visibility = True
    data.frames[0].objects[0].entry = True
    assert data.frames[0].objects[0].identity == "vehicle-a"
    assert data.frames[0].predictions[0].predicted_track_id == 1
    for extension, content in [("json", data.model_dump_json()), ("csv", annotations_csv(data))]:
        assert parse_annotations(content.encode(), "labels."+extension) == data
    empty = document(scenario.field, [])
    assert parse_annotations(annotations_csv(empty).encode(), "empty.csv") == empty


def test_csv_preserves_proposal_settings(scenario):
    data = document(scenario.field, proposal_metadata=dict(start_index=1, end_index=3, tracker="improved",
        confidence=.35, input_size=416, elapsed_ms=1.25, model="synthetic"))
    assert parse_annotations(annotations_csv(data).encode(), "labels.csv") == data


@pytest.mark.parametrize("label", ["=SUM(1,1)", "+SUM(1,1)", "-SUM(1,1)", "@SUM(1,1)", "'=literal-name"])
def test_csv_formula_like_text_is_inert_and_lossless(scenario, label):
    data = document(scenario.field)
    data.source_id = "=SOURCE(1)"
    data.frames[0].objects[0].identity = label
    data.frames[1].objects[0].identity = label
    exported = annotations_csv(data)
    rows = list(csv.DictReader(io.StringIO(exported)))
    object_row = next(row for row in rows if row["record_type"] == "object")
    assert object_row["source_id"] == "'=SOURCE(1)"
    assert object_row["identity"] == (label if label.startswith("'") else "'"+label)
    assert parse_annotations(exported.encode(), "labels.csv") == data


def test_csv_rejects_inconsistent_metadata_and_missing_frame_records(scenario):
    data = document(scenario.field)
    text = annotations_csv(data)
    rows = list(csv.DictReader(io.StringIO(text)))
    rows[1]["source_id"] = "different-source"
    output = io.StringIO()
    writer = csv.DictWriter(output, fieldnames=list(rows[0]))
    writer.writeheader()
    writer.writerows(rows)
    with pytest.raises(ValueError, match="mixes document"):
        parse_annotations(output.getvalue().encode(), "labels.csv")
    with pytest.raises(ValueError, match="explicit frame record"):
        parse_annotations("\n".join(line for line in text.splitlines() if ',frame,' not in line).encode(), "labels.csv")


@pytest.mark.parametrize("content,filename", [(b"", "empty.json"), (b"\xff", "bad.csv"),
    (b"{}", "bad.txt"), (b"wrong,columns\n1,2", "bad.csv"), (b"{}", "bad.json")])
def test_bad_annotation_imports_fail(content, filename):
    with pytest.raises(ValueError):
        parse_annotations(content, filename)


def test_atomic_revision_conflict_preserves_existing_labels(scenario):
    data = document(scenario.field)
    saved = scenario.service.save(scenario.field.id, data)
    assert saved.revision == 1
    assert scenario.service.get(scenario.field.id) == saved
    with pytest.raises(AnnotationRevisionConflict):
        scenario.service.save(scenario.field.id, data)
    assert scenario.service.get(scenario.field.id) == saved


def test_two_concurrent_writers_cannot_overwrite(scenario):
    data = document(scenario.field)
    def save():
        try:
            return scenario.service.store.put(scenario.field, data).revision
        except AnnotationRevisionConflict:
            return "conflict"
    with ThreadPoolExecutor(max_workers=2) as executor:
        results = list(executor.map(lambda _: save(), range(2)))
    assert sorted(str(item) for item in results) == ["1", "conflict"]


def test_source_geometry_and_actual_timestamps_are_checked(scenario):
    data = document(scenario.field)
    data.frames[0].timestamp_s = .04
    with pytest.raises(ValueError, match="timestamp differs"):
        scenario.service.save(scenario.field.id, data)
    data.frames[0].timestamp_s = 0
    data.source_id = "other"
    with pytest.raises(ValueError, match="source or pixel geometry differs"):
        scenario.service.save(scenario.field.id, data)


def test_manual_ground_truth_metrics_count_switch_fragment_and_missing(scenario):
    data = document(scenario.field, [
        dict(index=1, reviewed=True, objects=[truth()], predictions=[prediction()]),
        dict(index=2, reviewed=True, objects=[truth()], predictions=[]),
        dict(index=3, reviewed=True, objects=[truth()], predictions=[prediction(2)]),
        dict(index=4, reviewed=True, objects=[truth(bbox=None)]),
        dict(index=5, reviewed=True, objects=[truth()], predictions=[prediction(2)]),
        dict(index=6, reviewed=False, objects=[truth()], predictions=[prediction(10)]),
        dict(index=7, reviewed=True, predictions=[prediction(8)]),
        dict(index=8, reviewed=True, objects=[truth("vehicle-b")], predictions=[prediction(3, category="bus")]),
    ])
    result = annotation_metrics(data)
    assert result["annotated_vehicles"] == 2
    assert result["reviewed_frames"] == 7
    assert result["predicted_frames"] == 5
    assert result["matched_observations"] == 3
    assert result["missed_observations"] == 2
    assert result["false_positive_observations"] == 2
    assert result["id_switches"] == result["fragments"] == 1
    assert any("not IDF1" in reason for reason in result["limitations"])


def test_metrics_exclude_unproposed_frames_when_single_run_is_known(scenario):
    data = document(scenario.field, proposal_metadata=dict(start_index=2, end_index=3, elapsed_ms=1))
    metrics = annotation_metrics(data)
    assert metrics["reviewed_frames"] == 3
    assert metrics["scored_frames"] == 2
    assert metrics["matched_observations"] == 0


def test_metric_assignment_maximizes_matches_and_uses_strict_iou_gate(scenario):
    data = document(scenario.field, [dict(index=1, reviewed=True,
        objects=[truth("a", (0, 0, 20, 10)), truth("b", (8, 0, 28, 10))],
        predictions=[prediction(1, (2, 0, 22, 10)), prediction(2, (0, 0, 12, 10))])])
    assert annotation_metrics(data)["matched_observations"] == 2
    boundary = document(scenario.field, [dict(index=1, reviewed=True,
        objects=[truth(bbox=(0, 0, 30, 10))], predictions=[prediction(bbox=(10, 0, 40, 10))])])
    assert annotation_metrics(boundary)["matched_observations"] == 0
    assert annotation_metrics(boundary)["missed_observations"] == 1


def test_offline_undistorted_pixel_space_uses_exact_profile(scenario):
    profile = CameraIntrinsicProfile(name="Synthetic 64px camera", camera_configuration_id="synthetic",
        id=str(uuid4()), width=64, height=48, camera_matrix=[[60, 0, 32], [0, 61, 24], [0, 0, 1]],
        distortion_coefficients=[.15, .02, 0, 0, 0], rms_reprojection_error_px=.1,
        per_image_error_px=[.1]*6, used_image_count=6, rejected_image_count=0, provenance="synthetic")
    scenario.manager.camera_profiles.put(profile)
    data = FieldSessionInput.model_validate(scenario.field.model_dump(exclude={"id", "created_at", "updated_at", "sync_diagnostics"}))
    data.camera.geometry = profile.geometry
    data.camera.intrinsic_profile_id = profile.id
    corrected = scenario.manager.field_store.put(data)
    info = scenario.service.frame(corrected.id, 4)
    assert info["coordinate_space"] == "undistorted"
    assert info["intrinsic_profile_id"] == profile.id
    image = cv2.imdecode(np.frombuffer(scenario.service.image(corrected.id, 4), np.uint8), cv2.IMREAD_COLOR)
    assert image.shape == (48, 64, 3)
    assert image[0, 0].mean() < image[24, 32].mean()


def test_archived_intrinsics_survive_profile_deletion_and_replacement(scenario):
    profile = CameraIntrinsicProfile(name="Archived synthetic camera", camera_configuration_id="synthetic",
        id=str(uuid4()), width=64, height=48, camera_matrix=[[60, 0, 32], [0, 61, 24], [0, 0, 1]],
        distortion_coefficients=[.15, .02, 0, 0, 0], rms_reprojection_error_px=.1,
        per_image_error_px=[.1]*6, used_image_count=6, rejected_image_count=0, provenance="synthetic")
    scenario.manager.camera_profiles.put(profile)
    data = FieldSessionInput.model_validate(scenario.field.model_dump(exclude={"id", "created_at", "updated_at", "sync_diagnostics"}))
    data.camera.geometry = profile.geometry
    data.camera.intrinsic_profile_id = profile.id
    data.calibration_metadata["intrinsic"] = profile.model_dump(mode="json")
    field = scenario.manager.field_store.put(data)
    raw = np.full((48, 64, 3), 45, np.uint8)
    expected = FrameUndistorter(profile).apply(raw)
    _, encoded = cv2.imencode(".jpg", expected, [cv2.IMWRITE_JPEG_QUALITY, 85])
    scenario.manager.camera_profiles.delete(profile.id)
    assert scenario.service.image(field.id, 4) == encoded.tobytes()
    scenario.service.close()
    scenario.manager.camera_profiles.put(profile.model_copy(update={"distortion_coefficients": [0.]*5}))
    assert scenario.service.image(field.id, 4) == encoded.tobytes()


def test_invalid_source_timestamps_abort_proposals_without_partial_save(scenario, monkeypatch):
    fake = SimpleNamespace(summary=lambda: {"frame_count": 2},
        metadata=lambda index: dict(index=index, timestamp_s=0, width=64, height=48),
        image=lambda index: np.zeros((48, 64, 3), np.uint8))
    monkeypatch.setattr(scenario.service, "_video", lambda field: (fake, None))
    with pytest.raises(ValueError, match="strictly increasing"):
        scenario.service.propose(scenario.field.id, ProposalRequest(start_index=1, end_index=2))
    assert scenario.service.get(scenario.field.id).revision == 0
    assert scenario.service.get(scenario.field.id).frames == []


def test_navigation_keeps_actual_pts_and_exact_pixels(scenario):
    info = scenario.service.frame(scenario.field.id, 4)
    assert info["index"] == 4
    assert info["timestamp_s"] == pytest.approx(.3)
    assert info["total_frames"] == 12
    assert info["coordinate_space"] == "source"
    image = cv2.imdecode(np.frombuffer(scenario.service.image(scenario.field.id, 4), np.uint8), cv2.IMREAD_COLOR)
    assert image.shape == (48, 64, 3)
    assert image.mean() == pytest.approx(45, abs=1)
    closest = scenario.service.frame_at(scenario.field.id, .31)
    assert closest["index"] == 4
    assert closest["requested_timestamp_s"] == .31
    assert closest["timestamp_distance_s"] == pytest.approx(.01)
    assert scenario.service.frame_at(scenario.field.id, 99)["index"] == 12
    with pytest.raises(ValueError, match="finite"):
        scenario.service.frame_at(scenario.field.id, float("nan"))


def test_changed_source_fingerprint_and_path_escape_fail(scenario):
    scenario.service.frame(scenario.field.id, 1)
    scenario.path.write_bytes(scenario.path.read_bytes()+b"changed")
    with pytest.raises(ValueError, match="fingerprint"):
        scenario.service.frame(scenario.field.id, 1)
    field = scenario.field.model_copy(deep=True)
    field.source.relative_path = "../outside.avi"
    with pytest.raises(ValueError, match="unavailable"):
        scenario.service._source_path(field)


def test_offline_proposals_preserve_truth_and_have_separate_identity_scope(scenario):
    saved = scenario.service.save(scenario.field.id, document(scenario.field))
    proposed = scenario.service.propose(scenario.field.id, ProposalRequest(start_index=1, end_index=4))
    assert proposed.revision == saved.revision+1
    assert proposed.frames[0].objects == saved.frames[0].objects
    assert proposed.frames[0].reviewed
    assert proposed.frames[0].predictions[0].predicted_track_id == 1
    assert proposed.frames[3].objects == []
    assert not proposed.frames[3].reviewed
    assert proposed.proposal_metadata.model == "Injected synthetic marker detector"
    rerun = scenario.service.propose(scenario.field.id, ProposalRequest(start_index=5, end_index=6, tracker="baseline"))
    assert all(not frame.predictions for frame in rerun.frames if frame.index < 5)
    assert rerun.frames[0].objects == saved.frames[0].objects
    assert rerun.proposal_metadata.tracker == "baseline"


@pytest.mark.parametrize("change", [{"start_index": 0}, {"start_index": 5, "end_index": 4},
    {"start_index": 1, "end_index": 101}, {"input_size": 1000}, {"tracker": "unknown"}])
def test_proposal_bounds_are_enforced(change):
    with pytest.raises(ValidationError):
        ProposalRequest(**change)


def test_cache_is_bounded_and_delete_removes_labels(scenario):
    scenario.service.save(scenario.field.id, document(scenario.field))
    fields = [scenario.field]
    for index in range(3):
        data = FieldSessionInput.model_validate(scenario.field.model_dump(exclude={"id", "created_at", "updated_at", "sync_diagnostics"}))
        data.name = f"Synthetic {index}"
        fields.append(scenario.manager.field_store.put(data))
    for field in fields:
        scenario.service.image(field.id, 1)
    assert len(scenario.service._videos) == 3
    assert scenario.field.id not in scenario.service._videos
    scenario.service.delete(scenario.field.id)
    assert scenario.service.get(scenario.field.id).revision == 0


def make_client(scenario):
    app = FastAPI()
    app.include_router(annotation_routes(scenario.manager))

    @app.exception_handler(ValueError)
    async def invalid(request, error):
        return JSONResponse({"detail": str(error)}, status_code=422)
    @app.exception_handler(KeyError)
    async def missing(request, error):
        return JSONResponse({"detail": str(error)}, status_code=404)
    return TestClient(app)


def test_annotation_api_save_conflict_export_import_and_metrics(scenario):
    client = make_client(scenario)
    base = f"/api/field-sessions/{scenario.field.id}"
    assert client.get(base+"/annotations").json()["revision"] == 0
    data = document(scenario.field)
    saved = client.put(base+"/annotations", json=data.model_dump(mode="json"))
    assert saved.status_code == 200
    assert saved.json()["revision"] == 1
    assert client.put(base+"/annotations", json=data.model_dump(mode="json")).status_code == 409
    exported = client.get(base+"/annotations/export?format=csv")
    assert exported.status_code == 200
    imported = client.post(base+"/annotations/import", files={"file": ("annotations.csv", exported.content, "text/csv")})
    assert imported.status_code == 200, imported.text
    assert imported.json()["revision"] == 2
    assert client.get(base+"/annotations/metrics").json()["matched_observations"] == 1
    assert client.get(base+"/annotations/export?format=json").json()["revision"] == 2


def test_annotation_api_frames_timestamp_navigation_and_proposals(scenario):
    client = make_client(scenario)
    base = f"/api/field-sessions/{scenario.field.id}"
    assert client.get(base+"/frames?index=3").json()["timestamp_s"] == pytest.approx(.2)
    assert client.get(base+"/frames?timestamp_s=0.21").json()["index"] == 3
    assert client.get(base+"/frames?timestamp_s=0.2&index=3").status_code == 422
    assert client.get(base+"/frames/image?index=3").headers["content-type"] == "image/jpeg"
    assert client.get(base+"/frames?index=0").status_code == 422
    proposed = client.post(base+"/proposals", json={"start_index": 1, "end_index": 3})
    assert proposed.status_code == 200, proposed.text
    assert len(proposed.json()["frames"]) == 3
    scenario.manager.snapshot = lambda: SessionSnapshot(state="running")
    assert client.post(base+"/proposals", json={"start_index": 1, "end_index": 3}).status_code == 409
