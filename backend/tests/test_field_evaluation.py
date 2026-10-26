"""Real arithmetic on synthetic observations; no physical accuracy evidence."""

import csv
import io
import json
from pathlib import Path

import pytest

from roadlens.field_evaluation import evaluate_fields, field_report_csv, field_report_html
from roadlens.field_models import FieldEvaluationRequest, FieldSessionInput
from roadlens.field_store import FieldStore


@pytest.fixture
def session(tmp_path):
    fixture = Path(__file__).resolve().parents[2] / "examples/field/synthetic_field_session.json"
    return FieldStore(tmp_path).put(FieldSessionInput.model_validate_json(fixture.read_text(encoding="utf-8")))


def evaluate(session, **options):
    return evaluate_fields([session], FieldEvaluationRequest(session_ids=[session.id], **options))


def test_known_errors_and_external_ledger_rates(session):
    report = evaluate(session)
    summary = report["validation"]["summary"]
    assert summary["n"] == 4
    assert summary["mae_kmh"] == 2
    assert summary["rmse_kmh"] == pytest.approx(4.5 ** .5)
    assert summary["bias_kmh"] == .5
    assert summary["median_absolute_error_kmh"] == 2
    assert summary["p90_absolute_error_kmh"] == pytest.approx(2.7)
    assert report["counts"]["denominator"] == 8
    assert report["counts"]["missing_application_events"] == 2
    assert report["counts"]["valid_measurement_percent"] == 37.5
    assert report["counts"]["rejection_percent"] == 25
    assert report["counts"]["noncompletion_percent"] == 50
    assert report["validation"]["rejection_rate_percent"] == 25
    assert report["validation"]["completion_rate_percent"] == 50
    assert not any("all imported records as their denominator" in line for line in report["validation"]["limitations"])
    assert report["counts"]["unmatched_reference_events"] == 2
    assert not report["real_world_reference_available"]
    assert report["provenance"] == "synthetic"
    assert report["performance"]["evaluation_ms"] >= 0


def test_original_statuses_reasons_and_measurement_diagnostics_are_preserved(session):
    before = session.model_dump(mode="json")
    report = evaluate(session)
    assert session.model_dump(mode="json") == before
    originals = [m for m in session.measurements if m.variant == "original"]
    assert [r["record"]["status"] for r in report["validation"]["rows"]] == [m.measurement.status for m in originals]
    assert [r["original_reasons"] for r in report["row_metadata"]] == [m.measurement.reasons for m in originals]
    assert "reference_association_ambiguous" in report["exclusions"]
    assert report["exclusions"]["rejected_measurement"] == 2


def test_subgroups_emit_only_when_sample_size_supports_them(session):
    report = evaluate(session)
    assert any(g["dimension"] == "status" and g["value"] == "valid" for g in report["groups"])
    assert not any(g["dimension"] == "status" and g["value"] == "approximate" for g in report["groups"])
    assert all(g["metrics"]["n"] >= 3 for g in report["groups"])
    assert any(g["dimension"] == "status" and g["value"] == "approximate" and g["n"] == 1 for g in report["group_sample_counts"])


def test_paired_comparison_requires_identical_event_and_retains_both_results(session):
    report = evaluate(session)
    paired = report["pipeline_comparison"]
    assert paired["paired_n"] == 4
    assert paired["baseline"]["mae_kmh"] == 2.5
    assert paired["improved"]["mae_kmh"] == 2
    assert paired["pairs"][0]["baseline"]["id"] == "baseline-001"
    assert paired["pairs"][0]["improved"]["id"] == "improved-001"
    session.measurements = [m for m in session.measurements if not (m.event_id == "event-001" and m.variant == "improved")]
    assert evaluate(session)["pipeline_comparison"]["paired_n"] == 3


def test_missing_ledger_uses_retained_events_without_inventing_crossing_recall(session):
    session.expected_event_count = None
    report = evaluate(session)
    assert report["counts"]["denominator"] == 6
    assert report["counts"]["missing_application_events"] is None
    assert not report["counts"]["complete_event_ledger"]
    assert report["validation"]["rejection_rate_percent"] == pytest.approx(100 / 3)
    assert report["validation"]["completion_rate_percent"] == pytest.approx(200 / 3)
    assert any("external crossing ledger" in value for value in report["limitations"])


def test_missing_references_and_insufficient_samples_do_not_produce_zero_errors(session):
    session.reference_events = []
    session.matches = []
    report = evaluate(session)
    assert report["validation"]["summary"]["n"] == 0
    assert report["validation"]["summary"]["mae_kmh"] is None
    assert report["counts"]["missing_reference"] == 6
    assert report["counts"]["excluded_measurements"] == 6
    session.measurements = []
    session.expected_event_count = None
    report = evaluate(session)
    assert report["measurement_count"] == 0
    assert report["counts"]["rejection_percent"] is None
    assert report["validation"]["summary"]["bias_kmh"] is None


def test_uncertain_synchronization_is_not_eligible_even_with_identical_speeds(session):
    session.sync.anchors = session.sync.anchors[:1]
    session.sync.fit_drift = False
    for measurement in session.measurements:
        measurement.measurement.estimated_speed_kmh = 30
    report = evaluate(session)
    assert report["validation"]["summary"]["n"] == 0
    assert report["exclusions"]["synchronization_not_confirmed"] == 6


def test_bad_manual_offset_retains_negative_alignment_evidence_instead_of_crashing(session):
    session.sync.fit_drift = False
    session.sync.offset_s = -1000
    report = evaluate(session)
    assert report["validation"]["summary"]["n"] == 0
    assert report["match_diagnostics"][0]["aligned_reference_timestamp_s"] < 0
    assert report["exclusions"]["reference_time_before_source_origin"] == 6
    assert report["row_metadata"][0]["original_measurement"]["timestamp_s"] == 11


def test_default_partition_never_silently_evaluates_development(session):
    session.partition = "development"
    with pytest.raises(ValueError, match="requested partition"):
        evaluate(session)
    assert evaluate(session, partition="development")["partition"] == "development"


def test_mixed_evidence_and_duplicate_selection_are_not_pooled(session):
    other = session.model_copy(deep=True)
    other.id = "other"
    other.source.source_id = "another-source"
    other.source.content_sha256 = "a" * 64
    other.source.collection_id = "other-collection"
    other.provenance = "independent_reference"
    with pytest.raises(ValueError, match="separately"):
        evaluate_fields([session, other], FieldEvaluationRequest(session_ids=[session.id, other.id]))
    with pytest.raises(ValueError, match="unique"):
        evaluate_fields([session], FieldEvaluationRequest(session_ids=[session.id, session.id]))


def test_declared_independent_data_requires_eligible_matches_not_just_provenance_label(session):
    session.provenance = "independent_reference"
    assert not evaluate(session)["real_world_reference_available"]
    for reference in session.reference_events:
        reference.provenance = "independent_reference"
    report = evaluate(session)
    assert report["real_world_reference_available"]
    assert report["validation"]["summary"]["n"] == 4
    assert any("author declarations" in line for line in report["limitations"])


def test_tracking_provider_keeps_per_session_annotations_separate(session):
    report = evaluate_fields([session], FieldEvaluationRequest(session_ids=[session.id]),
                             tracking_provider=lambda identifier: {"annotated_vehicles": 2, "id_switches": 1, "evidence": "synthetic"})
    assert report["tracking"] == [{"session_id": session.id, "metrics": {"annotated_vehicles": 2, "id_switches": 1, "evidence": "synthetic"}}]


def test_reports_are_portable_scriptless_and_spreadsheet_safe(session):
    session.name = "=HYPERLINK(\"bad\")"
    session.description = '<script>alert("x")</script>'
    session.source.relative_path = "uploads/private-recording.mp4"
    report = evaluate(session, description='<img src=x onerror="alert(1)">')
    encoded = json.dumps(report, allow_nan=False)
    assert "private-recording.mp4" not in encoded
    rendered = field_report_html(report)
    assert "<script>" not in rendered and "<img src=x" not in rendered
    assert "&lt;script&gt;" in rendered and "&lt;img" in rendered
    assert "Content-Security-Policy" in rendered
    assert "No real-world reference data available" in rendered
    records = list(csv.DictReader(io.StringIO(field_report_csv(report))))
    assert records[0]["row_type"] == "summary"
    assert json.loads(records[0]["report_metadata"])["counts"]["denominator"] == 8
    assert records[1]["session_name"].startswith("'=HYPERLINK")
    assert records[-1]["status"] == "rejected"


def test_csv_empty_report_still_has_metadata_and_reproduction(session):
    session.measurements = []
    session.matches = []
    session.expected_event_count = None
    report = evaluate(session)
    records = list(csv.DictReader(io.StringIO(field_report_csv(report))))
    assert len(records) == 1
    summary = json.loads(records[0]["report_metadata"])
    assert summary["provenance"] == "synthetic"
    assert summary["reproduction"]["request"]["session_ids"] == [session.id]
