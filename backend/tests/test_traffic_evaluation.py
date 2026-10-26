"""Counting/class/direction scores do not condition matching on predicted class."""

import copy

import pytest

from roadlens.annotation_models import AnnotationDocument
from roadlens.field_models import FieldSessionInput
from roadlens.field_store import FieldStore
from roadlens.traffic_evaluation import TrafficEvaluationRequest, evaluate_counting, truth_crossings
from test_traffic_analytics import artifact


def evaluation_fixture(tmp_path):
    data = artifact()
    field = FieldStore(tmp_path).put(FieldSessionInput(name="SYNTHETIC annotated recording",
        source={"source_id": data["source_id"]}, camera={"geometry": data["configuration"]["geometry"]},
        provenance="synthetic", partition="held_out"))
    frames = []
    for index, bottom in enumerate((20, 40, 80, 100), 1):
        frames.append({"index": index, "timestamp_s": index - 1, "reviewed": True,
                       "objects": [{"identity": "manual-A", "category": "car", "bbox": [40, bottom - 10, 60, bottom]}]})
    doc = AnnotationDocument(field_session_id=field.id, source_id=field.source.source_id,
        geometry=field.camera.geometry, provenance="synthetic", frames=frames)
    data["coverage"] = [{"start_s": 0, "end_s": 3, "configuration_id": data["configuration"]["id"]}]
    event = data["events"][0]
    event.update(timestamp_s=1.5, image_position=[50, 60], category="truck", direction="negative")
    data["events"] = [event]
    request = TrafficEvaluationRequest(traffic_session_id=data["id"], field_session_id=field.id)
    return data, doc, field, request


def test_count_match_independent_of_wrong_class_and_direction(tmp_path):
    data, doc, field, request = evaluation_fixture(tmp_path)
    report = evaluate_counting(data, doc, field, request)
    assert report["truth_count"] == report["matched_count"] == 1
    assert report["precision"] == report["recall"] == 1
    assert report["classification_accuracy"] == report["direction_accuracy"] == 0
    assert report["confusion_matrix"] == [{"truth": "car", "prediction": "truck", "count": 1}]
    assert report["evidence_type"] == "synthetic"
    assert report["tracking"]["available"] is False
    assert "missed_observations" not in report["tracking"]


def test_duplicate_false_positive_and_missed_crossing(tmp_path):
    data, doc, field, request = evaluation_fixture(tmp_path)
    duplicate = copy.deepcopy(data["events"][0])
    duplicate.update(id="duplicate", track_id=99, timestamp_s=1.6)
    false_positive = copy.deepcopy(duplicate)
    false_positive.update(id="false-positive", timestamp_s=2.9, image_position=[180, 60])
    data["events"].extend([duplicate, false_positive])
    report = evaluate_counting(data, doc, field, request)
    assert report["matched_count"] == 1 and report["duplicate_count"] == 1
    assert report["false_positive_count"] == 2 and report["count_error"] == 2
    assert report["precision"] == pytest.approx(1 / 3)
    data["events"] = []
    report = evaluate_counting(data, doc, field, request)
    assert report["missed_count"] == 1 and report["recall"] == 0 and report["precision"] is None


@pytest.mark.parametrize("change", ["unreviewed", "occluded", "sparse", "missing_timestamp", "large_gap"])
def test_no_truth_crossing_through_unobserved_segments(tmp_path, change):
    data, doc, field, request = evaluation_fixture(tmp_path)
    if change == "unreviewed":
        doc.frames[2].reviewed = False
    elif change == "occluded":
        doc.frames[2].objects[0].occluded = True
        doc.frames[2].objects[0].bbox = None
    elif change == "sparse":
        doc.frames[2].index = 10
        doc.frames[3].index = 11
    elif change == "missing_timestamp":
        doc.frames[2].timestamp_s = None
    else:
        doc.frames[2].timestamp_s = 20
        doc.frames[3].timestamp_s = 21
    truth, _ = truth_crossings(doc, data["configuration"])
    assert truth == []


def test_no_crossing_outside_finite_line(tmp_path):
    data, doc, _, _ = evaluation_fixture(tmp_path)
    data["configuration"]["lines"][0]["end"] = [20, 60]
    assert truth_crossings(doc, data["configuration"])[0] == []


def test_predictions_outside_reviewed_coverage_are_not_false_positives(tmp_path):
    data, doc, field, request = evaluation_fixture(tmp_path)
    extra = copy.deepcopy(data["events"][0])
    extra.update(id="outside-review", timestamp_s=90)
    data["events"].append(extra)
    report = evaluate_counting(data, doc, field, request)
    assert report["predicted_count"] == 1


@pytest.mark.parametrize("change", ["source", "geometry", "provenance", "partition"])
def test_evidence_bindings_enforced(tmp_path, change):
    data, doc, field, request = evaluation_fixture(tmp_path)
    if change == "source":
        data["source_id"] = "different recording"
    elif change == "geometry":
        data["configurations"][0]["geometry"]["width"] = 300
    elif change == "provenance":
        data["provenance"] = "recorded_unverified"
    else:
        request.partition = "development"
    with pytest.raises(ValueError):
        evaluate_counting(data, doc, field, request)


def test_empty_reviewed_coverage_is_explained(tmp_path):
    data, doc, field, request = evaluation_fixture(tmp_path)
    for frame in doc.frames:
        frame.reviewed = False
    with pytest.raises(ValueError, match="consecutive reviewed"):
        evaluate_counting(data, doc, field, request)


def test_pause_span_does_not_connect_old_stable_side_to_resumed_line_band(tmp_path):
    data, doc, field, request = evaluation_fixture(tmp_path)
    for frame, timestamp, bottom in zip(doc.frames, (0, .1, .2, .3), (20, 59, 59, 80)):
        frame.timestamp_s = timestamp
        frame.objects[0].bbox = (40, bottom - 10, 60, bottom)
    data["coverage"] = [{"start_s": 0, "end_s": .1, "configuration_id": data["configuration"]["id"]},
                        {"start_s": .2, "end_s": .3, "configuration_id": data["configuration"]["id"]}]
    data["events"] = []
    assert evaluate_counting(data, doc, field, request)["truth_count"] == 0


def test_occluded_interval_predictions_are_unscorable_not_false_positive(tmp_path):
    data, doc, field, request = evaluation_fixture(tmp_path)
    doc.frames[1].objects[0].occluded = True
    doc.frames[1].objects[0].bbox = None
    report = evaluate_counting(data, doc, field, request)
    assert report["truth_count"] == report["predicted_count"] == report["false_positive_count"] == 0


def test_real_counting_evidence_does_not_inherit_independent_speed_provenance(tmp_path):
    data, doc, field, request = evaluation_fixture(tmp_path)
    data["provenance"] = "recorded_unverified"
    field.provenance = doc.provenance = "independent_reference"
    report = evaluate_counting(data, doc, field, request)
    assert report["matched_count"] == 1
    assert report["evidence_type"] == "manually_annotated_video"
    assert report["prediction_provenance"] == "recorded_unverified"
