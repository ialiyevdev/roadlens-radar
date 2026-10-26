"""Stateless reference matching, arithmetic, and spreadsheet-safe interchange.

An independent declaration records a dataset author's claim; this software cannot
authenticate a reference instrument or certify a real-world accuracy result.
"""

import csv
import io
import json
import math
import statistics
from pathlib import Path

from .validation_models import (
    EvaluationRequest, MetricSummary, ToleranceResult, ValidationDataset,
    ValidationGroup, ValidationOptions, ValidationRecord, ValidationReport, ValidationRow,
)

MAX_IMPORT_BYTES = 2 * 1024 * 1024
EXAMPLE_PATH = Path(__file__).resolve().parents[2] / "examples" / "validation" / "synthetic_reference_speeds.json"


def example_dataset() -> ValidationDataset:
    return ValidationDataset.model_validate_json(EXAMPLE_PATH.read_text(encoding="utf-8"))


def compare_record(record: ValidationRecord) -> ValidationRow:
    reasons = []
    if record.reference_speed_kmh is None:
        reasons.append("missing_reference_speed")
    if record.association != "matched":
        reasons.append(f"reference_association_{record.association}")
    expected = (record.recording_id, record.observation_id, record.measurement_id)
    reference = (record.reference_recording_id, record.reference_observation_id,
                 record.reference_measurement_id)
    if any(value is None for value in reference):
        reasons.append("missing_reference_event_identifiers")
    elif expected != reference:
        reasons.append("reference_event_mismatch")
    if not record.reference_independent:
        reasons.append("reference_not_declared_independent")
    method = (record.reference_method or "").strip().lower()
    if not method:
        reasons.append("missing_reference_method")
    elif any(term in method for term in ("roadlens", "self reference", "self-reference", "same estimate")):
        reasons.append("reference_uses_roadlens_estimate")
    matched = not reasons
    if record.estimated_speed_kmh is None:
        reasons.append("missing_estimated_speed")
    if record.status == "rejected":
        reasons.append("rejected_measurement")
    included = not reasons
    error = record.estimated_speed_kmh - record.reference_speed_kmh if included else None
    return ValidationRow(
        record=record, reference_matched=matched, comparison_included=included,
        error_kmh=error, absolute_error_kmh=abs(error) if error is not None else None,
        absolute_percentage_error_percent=(100 * abs(error) / record.reference_speed_kmh
                                          if error is not None and record.reference_speed_kmh > 0 else None),
        exclusion_reasons=reasons)


def _quantile_linear(values: list[float], fraction: float) -> float:
    """NumPy/pandas default linear quantile, without adding a runtime dependency."""
    ordered = sorted(values)
    position = (len(ordered) - 1) * fraction
    low, high = math.floor(position), math.ceil(position)
    return ordered[low] + (ordered[high] - ordered[low]) * (position - low)


def summarize(rows: list[ValidationRow], options: ValidationOptions) -> MetricSummary:
    included = [row for row in rows if row.comparison_included]
    errors = [row.error_kmh for row in included]
    absolute = [abs(value) for value in errors]
    percentages = [row.absolute_percentage_error_percent for row in included
                   if row.absolute_percentage_error_percent is not None]
    enough = len(errors) >= options.minimum_group_samples
    tolerances = [ToleranceResult(
        tolerance_kmh=band,
        within_count=sum(value <= band for value in absolute),
        within_percent=(100 * sum(value <= band for value in absolute) / len(errors)
                        if enough else None)) for band in options.tolerance_bands_kmh]
    return MetricSummary(
        n=len(errors), sufficient_sample=enough,
        mae_kmh=statistics.fmean(absolute) if enough else None,
        rmse_kmh=math.sqrt(statistics.fmean(value * value for value in errors)) if enough else None,
        bias_kmh=statistics.fmean(errors) if enough else None,
        median_absolute_error_kmh=statistics.median(absolute) if enough else None,
        p90_absolute_error_kmh=_quantile_linear(absolute, .9) if enough else None,
        mape_percent=statistics.fmean(percentages) if len(percentages) >= options.minimum_group_samples else None,
        percentage_sample_count=len(percentages), tolerance_bands=tolerances)


def evaluate(request: EvaluationRequest) -> ValidationReport:
    dataset, options = request.dataset, request.options
    rows = [compare_record(record) for record in dataset.records]
    groups = [ValidationGroup(id=key, label=label, metrics=summarize(selected, options))
              for key, label, selected in (
                  ("all_reference_matched", "All eligible reference-matched measurements", rows),
                  ("valid", "Valid measurements", [row for row in rows if row.record.status == "valid"]),
                  ("approximate", "Approximate measurements", [row for row in rows if row.record.status == "approximate"]))]
    ranges = [("speed_low", "Reference speed below 30 km/h", 0, 30),
              ("speed_medium", "Reference speed 30 to below 60 km/h", 30, 60),
              ("speed_high", "Reference speed at least 60 km/h", 60, math.inf)]
    for key, label, lower, upper in ranges:
        selected = [row for row in rows if row.comparison_included
                    and lower <= row.record.reference_speed_kmh < upper]
        if len(selected) >= options.minimum_group_samples:
            groups.append(ValidationGroup(id=key, label=label, metrics=summarize(selected, options)))
    for direction in ("A_to_B", "B_to_A"):
        selected = [row for row in rows if row.comparison_included and row.record.direction == direction]
        if len(selected) >= options.minimum_group_samples:
            groups.append(ValidationGroup(id=f"direction_{direction}", label=f"Direction {direction}",
                                          metrics=summarize(selected, options)))
    count = len(rows)
    rejected = sum(row.record.status == "rejected" for row in rows)
    completed = sum(row.record.status != "rejected" and row.record.estimated_speed_kmh is not None for row in rows)
    limitations = [
        "Reference independence and event identity are declared by the dataset author, not authenticated by RoadLens.",
        "Numeric comparisons exclude rejected measurements, missing values and ambiguous, mismatched or non-independent references.",
        "Rejection and completion rates use all imported records as their denominator; unrecorded attempts are unknown.",
        "P90 uses linear interpolation at (n-1)*0.90; percentage errors omit zero reference speeds.",
        f"Aggregate errors and tolerance percentages require at least {options.minimum_group_samples} eligible samples; this threshold does not establish statistical confidence.",
        "Tolerance bands are analysis settings, not accuracy guarantees or legal enforcement thresholds.",
    ]
    if dataset.provenance == "synthetic":
        limitations.insert(0, "Synthetic example: software arithmetic and matching only; no empirical road-speed accuracy claim.")
    return ValidationReport(
        dataset_name=dataset.name, provenance=dataset.provenance, description=dataset.description,
        total_records=count, reference_matched_count=sum(row.reference_matched for row in rows),
        compared_count=sum(row.comparison_included for row in rows), rejected_count=rejected,
        completed_count=completed, rejection_rate_percent=100 * rejected / count if count else None,
        completion_rate_percent=100 * completed / count if count else None,
        summary=summarize(rows, options), groups=groups, rows=rows, options=options, limitations=limitations)


_METADATA = ("dataset_name", "dataset_provenance", "dataset_description")
_FIELDS = tuple(ValidationRecord.model_fields)
_NULLABLE_FLOATS = {"estimated_speed_kmh", "reference_speed_kmh", "timestamp_s", "reference_timestamp_s",
                    "reference_interval_start_s", "reference_interval_end_s"}
_NULLABLE_STRINGS = {"vehicle_id", "reference_method", "reference_recording_id", "reference_observation_id",
                     "reference_measurement_id", "calibration_id"}


def _csv_rows(reader):
    try:
        yield from reader
    except csv.Error as error:
        raise ValueError(f"Malformed or oversized CSV field: {error}.") from error


def import_dataset(data: bytes, filename: str) -> ValidationDataset:
    if len(data) > MAX_IMPORT_BYTES:
        raise ValueError("Validation imports are limited to 2 MiB.")
    try:
        decoded = data.decode("utf-8-sig")
    except UnicodeDecodeError as error:
        raise ValueError("Use UTF-8 JSON or CSV.") from error
    suffix = Path(filename).suffix.lower()
    if suffix == ".json":
        return ValidationDataset.model_validate_json(decoded)
    if suffix != ".csv":
        raise ValueError("Choose a .json or .csv dataset.")
    # Every individual input field is bounded independently of the whole upload.
    # csv's default 128 KiB field cap also protects against oversized cells.
    reader = csv.DictReader(io.StringIO(decoded), strict=True)
    required = {"dataset_name", "dataset_provenance", "recording_id", "observation_id", "measurement_id", "status"}
    if not reader.fieldnames or not required.issubset(reader.fieldnames):
        raise ValueError("CSV is missing required dataset/event/status columns.")
    if len(set(reader.fieldnames)) != len(reader.fieldnames):
        raise ValueError("CSV column names must be unique.")
    unknown = set(reader.fieldnames) - set(_FIELDS) - set(_METADATA)
    if unknown:
        raise ValueError(f"Unsupported CSV columns: {', '.join(sorted(unknown))}.")
    metadata = None
    records = []
    for number, raw in enumerate(_csv_rows(reader), start=2):
        if len(records) >= 10000:
            raise ValueError("Validation datasets are limited to 10000 records.")
        if None in raw or any(value is None for value in raw.values()):
            raise ValueError(f"CSV row {number} has the wrong number of columns.")
        current = tuple(raw.get(key, "") for key in _METADATA)
        if metadata is None:
            metadata = current
        elif metadata != current:
            raise ValueError("CSV dataset metadata must be identical on every row.")
        record = {key: value for key, value in raw.items() if key in _FIELDS}
        for key in _NULLABLE_FLOATS | _NULLABLE_STRINGS:
            if key in record and record[key] == "":
                record[key] = None
        if "reference_independent" in record:
            boolean = record["reference_independent"].lower()
            if boolean not in ("true", "false", "1", "0", ""):
                raise ValueError(f"CSV row {number} has an invalid reference_independent boolean.")
            record["reference_independent"] = boolean in ("true", "1")
        if "diagnostics" in record:
            try:
                record["diagnostics"] = json.loads(record["diagnostics"] or "{}")
            except json.JSONDecodeError as error:
                raise ValueError(f"CSV row {number} diagnostics must be a JSON object.") from error
        records.append(record)
    if metadata is None:
        raise ValueError("An empty CSV cannot carry dataset metadata; use an empty JSON dataset.")
    return ValidationDataset(name=metadata[0], provenance=metadata[1], description=metadata[2], records=records)


def spreadsheet_cell(value):
    """Keep CSV text inert when opened by spreadsheet applications."""
    if value is None:
        return ""
    if isinstance(value, (dict, list)):
        value = json.dumps(value, ensure_ascii=False, allow_nan=False, separators=(",", ":"))
    if isinstance(value, str) and value.lstrip().startswith(("=", "+", "-", "@", "\t", "\r", "\n")):
        return "'" + value
    return value


def dataset_csv(dataset: ValidationDataset) -> str:
    output = io.StringIO(newline="")
    writer = csv.DictWriter(output, fieldnames=[*_METADATA, *_FIELDS])
    writer.writeheader()
    for record in dataset.records:
        row = {"dataset_name": dataset.name, "dataset_provenance": dataset.provenance,
               "dataset_description": dataset.description, **record.model_dump()}
        writer.writerow({key: spreadsheet_cell(value) for key, value in row.items()})
    return output.getvalue()


def report_csv(report: ValidationReport) -> str:
    output = io.StringIO(newline="")
    result_fields = ("reference_matched", "comparison_included", "error_kmh", "absolute_error_kmh",
                     "absolute_percentage_error_percent", "exclusion_reasons")
    report_fields = ("evaluation_version", "row_type", "total_records", "reference_matched_count",
                     "compared_count", "rejected_count", "completed_count", "rejection_rate_percent",
                     "completion_rate_percent", "summary_json", "options_json", "groups_json", "limitations_json")
    writer = csv.DictWriter(output, fieldnames=[*_METADATA, *report_fields, *_FIELDS, *result_fields])
    writer.writeheader()
    metadata = {"dataset_name": report.dataset_name, "dataset_provenance": report.provenance,
                "dataset_description": report.description,
                **report.model_dump(include={"evaluation_version", "total_records", "reference_matched_count",
                    "compared_count", "rejected_count", "completed_count", "rejection_rate_percent", "completion_rate_percent"}),
                "summary_json": report.summary.model_dump(), "options_json": report.options.model_dump(),
                "groups_json": [group.model_dump() for group in report.groups], "limitations_json": report.limitations}
    for result in report.rows:
        row = {**metadata, "row_type": "measurement", **result.record.model_dump(),
               **result.model_dump(exclude={"record"})}
        writer.writerow({key: spreadsheet_cell(value) for key, value in row.items()})
    if not report.rows:
        writer.writerow({key: spreadsheet_cell(value) for key, value in {**metadata, "row_type": "summary"}.items()})
    return output.getvalue()
