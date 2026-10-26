"""Synthetic arithmetic/matching tests; no instrument or road accuracy claims."""

import csv
import io
import json
import math

import pytest
from pydantic import ValidationError

from roadlens.validation import (
    MAX_IMPORT_BYTES, compare_record, dataset_csv, evaluate, example_dataset,
    import_dataset, report_csv, spreadsheet_cell,
)
from roadlens.validation_models import EvaluationRequest, ValidationDataset, ValidationOptions, ValidationRecord


def event(index=1, reference=40, estimate=42, **updates):
    values = dict(recording_id="recording", observation_id=f"event-{index}", measurement_id=f"measurement-{index}",
                  estimated_speed_kmh=estimate, reference_speed_kmh=reference,
                  reference_method="Independent measured reference instrument", reference_independent=True,
                  reference_recording_id="recording", reference_observation_id=f"event-{index}",
                  reference_measurement_id=f"measurement-{index}", association="matched", status="valid")
    values.update(updates)
    return ValidationRecord(**values)


def report(records, **options):
    dataset = ValidationDataset(name="Controlled arithmetic", provenance="synthetic", records=records)
    return evaluate(EvaluationRequest(dataset=dataset, options=ValidationOptions(**options)))


def test_hand_calculated_metrics_linear_quantile_and_tolerances():
    result = report([event(1, 10, 8), event(2, 20, 24), event(3, 30, 31)])
    stats = result.summary
    assert stats.n == 3 and stats.sufficient_sample
    assert stats.mae_kmh == pytest.approx(7 / 3)
    assert stats.rmse_kmh == pytest.approx(math.sqrt(7))
    assert stats.bias_kmh == 1
    assert stats.median_absolute_error_kmh == 2
    assert stats.p90_absolute_error_kmh == pytest.approx(3.6)
    assert stats.mape_percent == pytest.approx((20 + 20 + 100 / 30) / 3)
    assert stats.percentage_sample_count == 3
    assert [(band.within_count, band.within_percent) for band in stats.tolerance_bands] == [(2, 200 / 3), (3, 100)]


def test_bundled_example_actual_results_and_exclusions():
    result = evaluate(EvaluationRequest(dataset=example_dataset()))
    assert (result.total_records, result.reference_matched_count, result.compared_count) == (18, 14, 12)
    assert (result.rejected_count, result.completed_count) == (1, 16)
    assert result.summary.mae_kmh == pytest.approx(34 / 12)
    assert result.summary.rmse_kmh == pytest.approx(math.sqrt(128 / 12))
    assert result.summary.bias_kmh == pytest.approx(16 / 12)
    assert result.summary.median_absolute_error_kmh == 2.5
    assert result.summary.p90_absolute_error_kmh == pytest.approx(4.9)
    assert result.summary.percentage_sample_count == 11
    assert result.rejection_rate_percent == pytest.approx(100 / 18)
    assert result.completion_rate_percent == pytest.approx(1600 / 18)
    assert [band.within_count for band in result.summary.tolerance_bands] == [8, 11]
    assert all(row.exclusion_reasons for row in result.rows[12:])
    assert "Synthetic" in result.limitations[0]


@pytest.mark.parametrize("count", [0, 1, 2])
def test_empty_and_insufficient_samples_have_no_aggregate_error(count):
    result = report([event(i) for i in range(count)])
    assert result.summary.n == count
    assert not result.summary.sufficient_sample
    assert result.summary.mae_kmh is None
    assert result.summary.rmse_kmh is None
    assert result.summary.bias_kmh is None
    assert result.summary.p90_absolute_error_kmh is None
    assert result.summary.mape_percent is None
    assert all(band.within_percent is None for band in result.summary.tolerance_bands)
    if count == 0:
        assert result.completion_rate_percent is None
        assert result.rejection_rate_percent is None


def test_zero_references_have_no_percentage_error_or_division_by_zero():
    result = report([event(i, 0, i) for i in range(3)])
    assert result.summary.mae_kmh == 1
    assert result.summary.mape_percent is None
    assert result.summary.percentage_sample_count == 0
    assert all(row.absolute_percentage_error_percent is None for row in result.rows)


def test_percentage_sample_minimum_separate_from_absolute_sample_minimum():
    result = report([event(0, 0, 1), event(1, 10, 11), event(2, 20, 22)])
    assert result.summary.n == 3
    assert result.summary.mae_kmh is not None
    assert result.summary.percentage_sample_count == 2
    assert result.summary.mape_percent is None


@pytest.mark.parametrize(("changes", "reason"), [
    ({"reference_speed_kmh": None}, "missing_reference_speed"),
    ({"estimated_speed_kmh": None}, "missing_estimated_speed"),
    ({"reference_independent": False}, "reference_not_declared_independent"),
    ({"reference_method": None}, "missing_reference_method"),
    ({"reference_method": "RoadLens exported speed"}, "reference_uses_roadlens_estimate"),
    ({"reference_method": "self-reference"}, "reference_uses_roadlens_estimate"),
    ({"reference_method": "same estimate in another field"}, "reference_uses_roadlens_estimate"),
    ({"association": "ambiguous"}, "reference_association_ambiguous"),
    ({"association": "unmatched"}, "reference_association_unmatched"),
    ({"association": "mismatched"}, "reference_association_mismatched"),
    ({"reference_measurement_id": None}, "missing_reference_event_identifiers"),
    ({"reference_measurement_id": "different-vehicle"}, "reference_event_mismatch"),
    ({"reference_recording_id": "different-recording"}, "reference_event_mismatch"),
    ({"reference_observation_id": "different-event"}, "reference_event_mismatch"),
    ({"status": "rejected"}, "rejected_measurement"),
])
def test_invalid_reference_or_measurement_excluded_with_explicit_reason(changes, reason):
    row = compare_record(event(**changes))
    assert not row.comparison_included
    assert row.error_kmh is None and row.absolute_error_kmh is None
    assert reason in row.exclusion_reasons


def test_rejected_matching_reference_counted_but_not_compared():
    result = report([event(1, status="rejected"), event(2, estimate=None), event(3, association="ambiguous")])
    assert result.reference_matched_count == 2
    assert result.compared_count == 0
    assert result.completed_count == 1
    assert result.rejected_count == 1
    assert result.completion_rate_percent == pytest.approx(100 / 3)
    assert result.rejection_rate_percent == pytest.approx(100 / 3)


def test_status_groups_sample_counts_and_supported_speed_direction_groups():
    records = [event(i, reference=50, status="valid", direction="A_to_B") for i in range(3)]
    records += [event(i, reference=70, status="approximate", direction="B_to_A") for i in range(3, 6)]
    records += [event(6, reference=20, direction="unknown")]
    result = report(records)
    groups = {group.id: group for group in result.groups}
    assert groups["valid"].metrics.n == 4
    assert groups["approximate"].metrics.n == 3
    assert groups["speed_medium"].metrics.n == groups["speed_high"].metrics.n == 3
    assert groups["direction_A_to_B"].metrics.n == groups["direction_B_to_A"].metrics.n == 3
    assert "speed_low" not in groups


def test_analysis_options_do_not_modify_original_estimates():
    records = [event(i, reference=40, estimate=42 + i) for i in range(3)]
    result = report(records, tolerance_bands_kmh=[0, 2], minimum_group_samples=4)
    assert result.summary.n == 3 and result.summary.mae_kmh is None
    assert [r.record.estimated_speed_kmh for r in result.rows] == [42, 43, 44]
    assert [band.within_count for band in result.summary.tolerance_bands] == [0, 1]


@pytest.mark.parametrize("value", [float("nan"), float("inf"), -float("inf"), -1])
@pytest.mark.parametrize("field", ["estimated_speed_kmh", "reference_speed_kmh", "timestamp_s", "reference_timestamp_s"])
def test_nonfinite_and_negative_numeric_values_rejected(field, value):
    with pytest.raises(ValidationError):
        event(**{field: value})


def test_nonfinite_diagnostics_rejected():
    with pytest.raises(ValidationError):
        event(diagnostics={"gap": float("nan")})


@pytest.mark.parametrize("changes", [
    {"reference_interval_start_s": 2},
    {"reference_interval_end_s": 2},
    {"reference_interval_start_s": 2, "reference_interval_end_s": 1},
    {"reference_interval_start_s": 2, "reference_interval_end_s": 2},
])
def test_incomplete_or_invalid_reference_intervals_rejected(changes):
    with pytest.raises(ValidationError):
        event(**changes)


def test_reference_interval_accepted_and_preserved():
    row = compare_record(event(reference_interval_start_s=1, reference_interval_end_s=2))
    assert row.comparison_included
    assert row.record.reference_interval_start_s == 1
    assert row.record.reference_interval_end_s == 2


@pytest.mark.parametrize("kind", ["measurement", "observation"])
def test_duplicate_event_identifiers_rejected(kind):
    first = event(1)
    second = event(2, **{f"{kind}_id": getattr(first, f"{kind}_id")})
    with pytest.raises(ValidationError, match="Duplicate"):
        report([first, second])


def test_identifiers_may_repeat_in_different_recordings():
    result = report([event(1), event(1, recording_id="other", reference_recording_id="other")])
    assert result.compared_count == 2


@pytest.mark.parametrize("changes", [
    {"tolerance_bands_kmh": [3, 3]}, {"tolerance_bands_kmh": [-1]},
    {"tolerance_bands_kmh": [float("nan")]}, {"tolerance_bands_kmh": []},
    {"minimum_group_samples": 2},
])
def test_invalid_analysis_options_rejected(changes):
    with pytest.raises(ValidationError):
        ValidationOptions(**changes)


def test_json_and_csv_round_trip_example():
    dataset = example_dataset()
    assert import_dataset(dataset.model_dump_json().encode(), "reference.json") == dataset
    assert import_dataset(dataset_csv(dataset).encode("utf-8-sig"), "reference.CSV") == dataset


@pytest.mark.parametrize(("content", "filename", "message"), [
    (b"invalid", "dataset.txt", ".json or .csv"),
    (b"\xff", "dataset.json", "UTF-8"),
    (b"a,b\n1,2\n", "dataset.csv", "required"),
    (b"{broken", "dataset.json", "Invalid JSON"),
    (b"x" * (MAX_IMPORT_BYTES + 1), "dataset.json", "2 MiB"),
], ids=["unsupported-extension", "invalid-utf8", "missing-columns", "invalid-json", "oversize"])
def test_invalid_imports(content, filename, message):
    with pytest.raises(ValueError, match=message):
        import_dataset(content, filename)


def test_csv_metadata_must_match_every_row():
    text = dataset_csv(example_dataset()).replace("Synthetic independent-reference arithmetic example", "Different dataset", 1)
    with pytest.raises(ValueError, match="identical"):
        import_dataset(text.encode(), "dataset.csv")


def test_csv_unknown_columns_and_duplicate_headers_rejected():
    content = dataset_csv(example_dataset())
    with pytest.raises(ValueError, match="Unsupported"):
        import_dataset(content.replace("vehicle_id,", "unexpected,", 1).encode(), "dataset.csv")
    with pytest.raises(ValueError, match="unique"):
        import_dataset(content.replace("vehicle_id,", "measurement_id,", 1).encode(), "dataset.csv")


@pytest.mark.parametrize("text", ["=SUM(1,2)", "+formula", "-command", "@formula", "  =formula", "\t=cmd"])
def test_spreadsheet_formula_text_inert(text):
    assert spreadsheet_cell(text) == "'" + text
    assert spreadsheet_cell(-2) == -2
    assert spreadsheet_cell(2.5) == 2.5


def test_csv_report_preserves_units_results_original_ids_and_diagnostic_json():
    result = report([event(1, measurement_id="=unsafe", diagnostics={"gap_s": .2})])
    row = next(csv.DictReader(io.StringIO(report_csv(result))))
    assert row["measurement_id"] == "'=unsafe"
    assert row["estimated_speed_kmh"] == "42.0"
    assert row["reference_speed_kmh"] == "40.0"
    assert json.loads(row["diagnostics"]) == {"gap_s": .2}
    assert json.loads(row["exclusion_reasons"]) == ["reference_event_mismatch"]
    assert row["error_kmh"] == ""
    assert result.rows[0].record.measurement_id == "=unsafe"


def test_csv_report_includes_summary_options_groups_and_empty_metadata():
    result = report([event(i) for i in range(3)])
    row = next(csv.DictReader(io.StringIO(report_csv(result))))
    assert row["row_type"] == "measurement"
    assert row["total_records"] == "3"
    assert json.loads(row["summary_json"])["mae_kmh"] == 2
    assert json.loads(row["options_json"])["tolerance_bands_kmh"] == [3, 5]
    assert json.loads(row["groups_json"])[0]["metrics"]["n"] == 3
    empty = list(csv.DictReader(io.StringIO(report_csv(report([])))))
    assert len(empty) == 1
    assert empty[0]["row_type"] == "summary"
    assert empty[0]["measurement_id"] == ""
    assert json.loads(empty[0]["summary_json"])["n"] == 0


def test_malformed_csv_quoting_returns_domain_error():
    header = "dataset_name,dataset_provenance,recording_id,observation_id,measurement_id,status\n"
    with pytest.raises(ValueError, match="Malformed"):
        import_dataset((header + '"unterminated').encode(), "dataset.csv")


def test_dataset_record_limit_and_reference_declaration_boolean():
    with pytest.raises(ValidationError):
        ValidationDataset(name="Too many", provenance="synthetic", records=[event()] * 10001)
    with pytest.raises(ValidationError):
        event(reference_independent="yes")


def test_real_world_provenance_preserved_without_synthetic_claim():
    dataset = ValidationDataset(name="Future independent observations", provenance="real_world", records=[])
    result = evaluate(EvaluationRequest(dataset=dataset))
    assert result.provenance == "real_world"
    assert all("Synthetic example" not in message for message in result.limitations)
    assert "not authenticated" in result.limitations[0]
