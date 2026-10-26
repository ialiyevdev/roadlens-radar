"""Held-out field evaluation using the existing Phase 3 arithmetic and original statuses."""

import csv
import html
import io
import json
from collections import Counter, defaultdict
from time import perf_counter

from .field_alignment import eligibility, match_diagnostics
from .field_models import FieldEvaluationRequest, FieldSession, utc_now
from .field_store import assert_partitions
from .validation import compare_record, evaluate, spreadsheet_cell, summarize
from .validation_models import EvaluationRequest, ValidationDataset, ValidationRecord


def _validation_row(session, wrapped):
    diagnosis = match_diagnostics(session, wrapped.event_id, wrapped.variant)
    reference = next((item for item in session.reference_events if item.id == diagnosis["reference_id"]), None)
    measurement = wrapped.measurement
    record = ValidationRecord(
        recording_id=session.id, observation_id=wrapped.event_id, measurement_id=measurement.id,
        vehicle_id=str(measurement.track_id), estimated_speed_kmh=measurement.estimated_speed_kmh,
        reference_speed_kmh=reference.speed_kmh if reference else None,
        reference_method=reference.method if reference else None,
        reference_independent=diagnosis["reference_eligible"],
        reference_recording_id=session.id if reference else None,
        reference_observation_id=wrapped.event_id if reference else None,
        reference_measurement_id=measurement.id if reference else None,
        association=diagnosis["association"], status=measurement.status,
        calibration_id=measurement.calibration_id, direction=measurement.direction,
        timestamp_s=measurement.timestamp_s if measurement.timestamp_s is not None and measurement.timestamp_s >= 0 else None,
        reference_timestamp_s=(diagnosis["aligned_reference_timestamp_s"] if diagnosis["aligned_reference_timestamp_s"] is not None
                               and diagnosis["aligned_reference_timestamp_s"] >= 0 else None),
        diagnostics={"native_reference_id": reference.id if reference else None,
                     "synchronization_status": session.sync_diagnostics.status,
                     "reference_interval_separation_s": diagnosis["interval_separation_s"]})
    row = compare_record(record)
    row.exclusion_reasons = sorted(set(row.exclusion_reasons + diagnosis["exclusion_reasons"]))
    row.comparison_included = not row.exclusion_reasons
    return row, diagnosis


def evaluate_fields(sessions: list[FieldSession], request: FieldEvaluationRequest,
                    tracking_provider=None) -> dict:
    started = perf_counter()
    assert_partitions(sessions)
    if len(set(request.session_ids)) != len(request.session_ids):
        raise ValueError("Evaluation session identifiers must be unique.")
    by_id = {session.id: session for session in sessions}
    if any(identifier not in by_id for identifier in request.session_ids):
        raise ValueError("An evaluation session no longer exists.")
    selected = [by_id[identifier] for identifier in request.session_ids
                if request.partition is None or by_id[identifier].partition == request.partition]
    if not selected:
        raise ValueError("No selected sessions belong to the requested partition.")
    provenance_set = {session.provenance for session in selected}
    if len(provenance_set) != 1:
        raise ValueError("Evaluate synthetic, recorded-unverified and independent-reference evidence separately.")
    provenance = next(iter(provenance_set))
    rows, metadata, diagnostics = [], [], []
    for session in selected:
        for wrapped in session.measurements:
            if wrapped.variant != request.variant:
                continue
            row, diagnosis = _validation_row(session, wrapped)
            rows.append(row)
            diagnostics.append(diagnosis)
            metadata.append({"session_id": session.id, "session_name": session.name,
                             "event_id": wrapped.event_id, "measurement_id": wrapped.measurement.id,
                             "variant": wrapped.variant, "provenance": session.provenance,
                             "partition": session.partition,
                             "camera_configuration": session.camera.configuration_id,
                             "intrinsic_profile_id": session.camera.intrinsic_profile_id,
                             "calibration": wrapped.measurement.calibration_id or session.calibration_id or "none",
                             "direction": wrapped.measurement.direction,
                             "environment": session.environment_condition,
                             "tracker": session.camera.tracker,
                             "status": wrapped.measurement.status,
                             "original_measurement": wrapped.measurement.model_dump(mode="json"),
                             "original_reasons": wrapped.measurement.reasons,
                             "measurement_diagnostics": wrapped.measurement.diagnostics.model_dump(mode="json")})
    dataset = ValidationDataset(name="Field evaluation", provenance="synthetic" if provenance == "synthetic" else "real_world",
                                description=request.description, records=[row.record for row in rows])
    validation = evaluate(EvaluationRequest(dataset=dataset, options=request.options))
    # The field engine has additional synchronization/span checks; preserve those exclusions.
    validation.rows = rows
    validation.summary = summarize(rows, request.options)
    validation.compared_count = sum(row.comparison_included for row in rows)
    validation.reference_matched_count = sum(row.reference_matched for row in rows)
    groups, sample_counts = [], []
    for dimension in ("session_id", "camera_configuration", "calibration", "direction", "environment", "tracker", "status"):
        buckets = defaultdict(list)
        for row, meta in zip(rows, metadata):
            buckets[meta[dimension]].append(row)
        for value, bucket in buckets.items():
            metrics = summarize(bucket, request.options)
            sample_counts.append({"dimension": dimension, "value": value, "n": metrics.n})
            if metrics.sufficient_sample:
                groups.append({"dimension": dimension, "value": value, "metrics": metrics.model_dump(mode="json")})
    # Existing speed intervals use exactly the same eligible rows.
    # Recompute speed bins after field exclusions so no group bypasses alignment quality.
    validation.groups = []
    for label, low, high in (("below_30", 0, 30), ("30_to_below_60", 30, 60), ("at_least_60", 60, float("inf"))):
        bucket = [row for row in rows if row.comparison_included and low <= row.record.reference_speed_kmh < high]
        metrics = summarize(bucket, request.options)
        sample_counts.append({"dimension": "reference_speed_kmh", "value": label, "n": metrics.n})
        if metrics.sufficient_sample:
            groups.append({"dimension": "reference_speed_kmh", "value": label, "metrics": metrics.model_dump(mode="json")})
    event_count = sum(len({m.event_id for m in s.measurements if m.variant == request.variant}) for s in selected)
    denominator_known = all(s.expected_event_count is not None for s in selected)
    denominator = sum(s.expected_event_count for s in selected) if denominator_known else event_count
    completed = sum(row.record.status != "rejected" and row.record.estimated_speed_kmh is not None for row in rows)
    rejected = sum(row.record.status == "rejected" for row in rows)
    valid = sum(row.record.status == "valid" and row.record.estimated_speed_kmh is not None for row in rows)
    validation.rejection_rate_percent = 100 * rejected / denominator if denominator else None
    validation.completion_rate_percent = 100 * completed / denominator if denominator else None
    exclusions = Counter(reason for row in rows for reason in row.exclusion_reasons)
    # Count per-session IDs, because device-local reference IDs can repeat between recordings.
    unmatched_references = sum(sum(ref.id not in {m.reference_id for m in s.matches if m.association == "matched"}
                                     for ref in s.reference_events) for s in selected)
    comparisons = _paired_comparison(selected, request)
    timing = [{"session_id": s.id, "source_timebase": s.source_timebase, "statistics": s.timing_summary,
               "synchronization": s.sync_diagnostics.model_dump(mode="json")} for s in selected]
    tracking = [{"session_id": s.id, "metrics": tracking_provider(s.id)} for s in selected] if tracking_provider else []
    limitations = [
        "Independent reference provenance, uncertainty and vehicle correspondence are author declarations; RoadLens does not certify instruments or measurements.",
        "Source presentation timestamps and camera monotonic acquisition times are not independently verified exposure or wall-clock times.",
        "Synchronization uses source_time = offset + scale * reference_time. Confirmed events must fall inside the synchronization-anchor span.",
        "Alignment tolerance is an analysis setting. Supplied uncertainty bounds and fit residuals are not statistical confidence intervals.",
        "Rejected, missing, ambiguous, unconfirmed and time-mismatched observations are retained and excluded from numerical error comparisons.",
        "Whole source recordings, collection IDs and near-duplicate groups stay in one partition. Undeclared duplicate recordings cannot be detected from metadata alone.",
        "Held-out observations must not be used to tune camera geometry, gates, tracker or correction parameters.",
        f"Subgroup errors require N >= {request.options.minimum_group_samples}; this software threshold does not establish statistical confidence.",
    ]
    if provenance != "independent_reference":
        limitations.insert(0, "No real-world reference data available. This evaluation supplies no independently validated roadway speed-accuracy result.")
    if not denominator_known:
        limitations.append("No complete external crossing ledger was supplied for every session; rate denominators cover retained application events only.")
    if any("issues" not in session.timing_summary for session in selected):
        limitations.append("Detailed source timestamp-integrity counters were not supplied for every session; timing metadata alone does not establish independent clock quality.")
    # Phase 3 has no external crossing ledger. Field reports use the declared
    # ledger consistently, including the embedded reusable validation payload.
    validation.limitations = [line for line in validation.limitations
                              if not line.startswith("Rejection and completion rates use all imported records")]
    limitations.append("Rate denominators use the complete declared external crossing ledger when available for every session; otherwise they cover retained application events only.")
    validation.limitations = list(dict.fromkeys(validation.limitations + limitations))
    return {"schema_version": "1", "generated_at": utc_now().isoformat(), "description": request.description,
            "provenance": provenance, "partition": request.partition, "variant": request.variant,
            "real_world_reference_available": provenance == "independent_reference" and validation.compared_count > 0,
            "session_count": len(selected), "measurement_count": len(rows),
            "sessions": [_session_report(s) for s in selected],
            "validation": validation.model_dump(mode="json"), "groups": groups,
            "group_sample_counts": sample_counts, "row_metadata": metadata, "match_diagnostics": diagnostics,
            "counts": {"vehicle_events": event_count, "denominator": denominator,
                       "complete_event_ledger": denominator_known, "valid": valid, "rejected": rejected,
                       "completed": completed, "noncompleted": max(0, denominator - completed),
                       "missing_application_events": max(0, denominator - event_count) if denominator_known else None,
                       "missing_reference": sum("missing_reference" in row.exclusion_reasons for row in rows),
                       "unmatched_reference_events": unmatched_references,
                       "excluded_measurements": len(rows) - validation.compared_count,
                       "valid_measurement_percent": 100 * valid / denominator if denominator else None,
                       "rejection_percent": 100 * rejected / denominator if denominator else None,
                       "noncompletion_percent": 100 * max(0, denominator - completed) / denominator if denominator else None},
            "exclusions": dict(sorted(exclusions.items())), "timing": timing, "tracking": tracking,
            "pipeline_comparison": comparisons, "limitations": limitations,
            "reproduction": {"request": request.model_dump(mode="json"),
                             "application": "RoadLens Radar Phase 4", "error_definition": "estimate_minus_reference_kmh",
                             "p90_method": "linear interpolation at (n-1)*0.90",
                             "source_pixels_included": False},
            "performance": {"evaluation_ms": (perf_counter() - started) * 1000}}


def _session_report(session):
    return {"id": session.id, "name": session.name, "description": session.description,
            "source": session.source.model_dump(mode="json", exclude={"relative_path"}),
            "camera": session.camera.model_dump(mode="json"), "calibration_id": session.calibration_id,
            "calibration_compatible": session.calibration_compatible, "configuration_warnings": session.configuration_warnings,
            "calibration_metadata": session.calibration_metadata,
            "gates": session.gates.model_dump(mode="json") if session.gates else None,
            "started_at": session.started_at.isoformat() if session.started_at else None,
            "ended_at": session.ended_at.isoformat() if session.ended_at else None,
            "environment_notes": session.environment_notes, "environment_condition": session.environment_condition,
            "reference_description": session.reference_description, "partition": session.partition,
            "provenance": session.provenance, "status": session.status,
            "eligibility": eligibility(session)}


def _paired_comparison(sessions, request):
    pairs, baseline, improved = [], [], []
    for session in sessions:
        variants = {(item.event_id, item.variant): item for item in session.measurements}
        for event in sorted({item.event_id for item in session.measurements}):
            old = variants.get((event, "baseline"))
            new = variants.get((event, "improved"))
            if old is None or new is None:
                continue
            left, _ = _validation_row(session, old)
            right, _ = _validation_row(session, new)
            included = left.comparison_included and right.comparison_included
            pairs.append({"session_id": session.id, "event_id": event, "included": included,
                          "baseline": old.measurement.model_dump(mode="json"),
                          "improved": new.measurement.model_dump(mode="json"),
                          "baseline_error_kmh": left.error_kmh if included else None,
                          "improved_error_kmh": right.error_kmh if included else None,
                          "absolute_error_change_kmh": right.absolute_error_kmh - left.absolute_error_kmh if included else None,
                          "exclusion_reasons": sorted(set(left.exclusion_reasons + right.exclusion_reasons))})
            if included:
                baseline.append(left)
                improved.append(right)
    return {"paired_n": len(baseline), "pairs": pairs,
            "baseline": summarize(baseline, request.options).model_dump(mode="json"),
            "improved": summarize(improved, request.options).model_dump(mode="json"),
            "note": "Only explicitly saved baseline/improved measurements for the same event and reference are paired. Original results are retained."}


def field_report_csv(report: dict) -> str:
    fields = ["row_type", "session_id", "session_name", "event_id", "measurement_id", "variant", "provenance",
              "partition", "camera_configuration", "calibration", "direction", "environment", "tracker", "status",
              "estimated_speed_kmh", "reference_speed_kmh", "error_kmh", "absolute_error_kmh", "included",
              "exclusion_reasons", "original_reasons", "measurement_diagnostics", "original_measurement", "report_metadata"]
    output = io.StringIO(newline="")
    writer = csv.DictWriter(output, fieldnames=fields)
    writer.writeheader()
    # Even empty reports carry all counts, settings, provenance, timing and limitations.
    summary = {key: value for key, value in report.items() if key not in {"validation", "row_metadata", "match_diagnostics"}}
    summary["validation_summary"] = report["validation"]["summary"]
    writer.writerow({"row_type": "summary", "report_metadata": spreadsheet_cell(summary)})
    for row, meta in zip(report["validation"]["rows"], report["row_metadata"]):
        flat = {key: value for key, value in meta.items() if key in fields}
        flat.update(row_type="measurement", estimated_speed_kmh=row["record"]["estimated_speed_kmh"],
                    reference_speed_kmh=row["record"]["reference_speed_kmh"], error_kmh=row["error_kmh"],
                    absolute_error_kmh=row["absolute_error_kmh"], included=row["comparison_included"],
                    exclusion_reasons=row["exclusion_reasons"])
        writer.writerow({key: spreadsheet_cell(value) for key, value in flat.items()})
    return output.getvalue()


def field_report_html(report: dict) -> str:
    escape = lambda value: html.escape(str(value), quote=True)
    summary = report["validation"]["summary"]
    rows = []
    for row, meta in zip(report["validation"]["rows"], report["row_metadata"]):
        record = row["record"]
        values = [meta["session_name"], meta["event_id"], record["status"], record["estimated_speed_kmh"],
                  record["reference_speed_kmh"], row["error_kmh"], "; ".join(row["exclusion_reasons"])]
        rows.append("<tr>" + "".join(f"<td>{escape(value if value is not None else 'Unavailable')}</td>" for value in values) + "</tr>")
    facts = {"Evidence": report["provenance"], "Partition": report["partition"], "Sessions": report["session_count"],
             "Eligible comparisons": summary["n"], "MAE km/h": summary["mae_kmh"], "RMSE km/h": summary["rmse_kmh"],
             "Mean signed error km/h": summary["bias_kmh"], "Median absolute error km/h": summary["median_absolute_error_kmh"],
             "P90 absolute error km/h": summary["p90_absolute_error_kmh"]}
    facts_html = "".join(f"<dt>{escape(key)}</dt><dd>{escape(value if value is not None else 'Insufficient data')}</dd>" for key, value in facts.items())
    limit_html = "".join(f"<li>{escape(value)}</li>" for value in report["limitations"])
    banner = "Independent references declared by the dataset author; no certification." if report["real_world_reference_available"] else "No real-world reference data available."
    details = {key: report[key] for key in ("sessions", "counts", "exclusions", "timing", "tracking", "groups", "pipeline_comparison", "reproduction", "performance")}
    return ("<!doctype html><html lang=\"en\"><meta charset=\"utf-8\"><meta name=\"viewport\" content=\"width=device-width,initial-scale=1\">"
            "<meta http-equiv=\"Content-Security-Policy\" content=\"default-src 'none'; style-src 'unsafe-inline'\">"
            "<title>RoadLens field validation</title><style>body{font:16px system-ui;margin:2rem auto;padding:0 1rem;max-width:1100px;color:#20252c}"
            "table{border-collapse:collapse;width:100%;font-size:14px}td,th{border:1px solid #ccc;padding:.5rem;text-align:left}"
            ".scroll{overflow:auto}dt{font-weight:600}dd{margin-bottom:.7rem}pre{white-space:pre-wrap;overflow-wrap:anywhere}"
            ".notice{padding:1rem;border:2px solid #ad7315}</style><h1>RoadLens field validation</h1>"
            f"<p class=\"notice\">{escape(banner)}</p><p>{escape(report['description'])}</p><p>Generated {escape(report['generated_at'])}</p>"
            f"<dl>{facts_html}</dl><h2>Measurements</h2><div class=\"scroll\"><table><thead><tr>"
            "<th>Session</th><th>Event</th><th>Status</th><th>Estimate km/h</th><th>Reference km/h</th><th>Signed error km/h</th><th>Exclusions</th>"
            f"</tr></thead><tbody>{''.join(rows)}</tbody></table></div><h2>Limitations</h2><ul>{limit_html}</ul>"
            f"<h2>Reproduction and evidence</h2><pre>{escape(json.dumps(details, indent=2, ensure_ascii=False, allow_nan=False))}</pre></html>")
