"""Clock alignment and bounded independent-reference interchange, separate from inference."""

import csv
import io
import json
import math
from pathlib import Path
from statistics import fmean

from .field_models import FieldSession, ReferenceEvent, SyncConfig, SyncDiagnostics


MAX_FIELD_BYTES = 8 * 1024 * 1024


def synchronization(config: SyncConfig) -> SyncDiagnostics:
    anchors = config.anchors
    warnings = []
    offset, scale = config.offset_s, 1.0
    span = max((a.reference_timestamp_s for a in anchors), default=0) - min(
        (a.reference_timestamp_s for a in anchors), default=0)
    if config.fit_drift:
        x_mean = fmean(a.reference_timestamp_s for a in anchors)
        y_mean = fmean(a.source_timestamp_s for a in anchors)
        denominator = sum((a.reference_timestamp_s - x_mean) ** 2 for a in anchors)
        if denominator <= 0:
            raise ValueError("Clock-drift fitting requires anchors spanning reference time.")
        scale = sum((a.reference_timestamp_s - x_mean) * (a.source_timestamp_s - y_mean)
                    for a in anchors) / denominator
        offset = y_mean - scale * x_mean
        if not math.isfinite(scale) or not math.isfinite(offset) or scale <= 0:
            raise ValueError("Synchronization anchors imply a nonpositive or nonfinite clock scale.")
    residuals = [a.source_timestamp_s - (offset + scale * a.reference_timestamp_s) for a in anchors]
    maximum = max((abs(value) for value in residuals), default=None)
    if len(anchors) < 2:
        warnings.append("At least two independent synchronization anchors spanning the observation are needed for confirmed alignment.")
    if any(not a.independent for a in anchors):
        warnings.append("Synchronization anchors are not all declared independent.")
    if not config.source_clock or not config.reference_clock:
        warnings.append("Describe both source and reference clocks.")
    if config.uncertainty_s is None or any(a.uncertainty_s is None for a in anchors):
        bound = None
        warnings.append("Synchronization uncertainty is unavailable; residual fit alone is not a timing-accuracy guarantee.")
    else:
        # Conservative declared bound, not a statistical confidence interval.
        bound = config.uncertainty_s + max((a.uncertainty_s for a in anchors), default=0) + (maximum or 0)
        if bound > config.maximum_alignment_error_s:
            warnings.append("Declared alignment uncertainty plus observed residual exceeds the analysis tolerance.")
    if abs(scale - 1) > .001:
        warnings.append("Clock scale differs by more than 1000 ppm; investigate clock units and timebase changes.")
    if anchors and span <= 0:
        warnings.append("Synchronization anchors do not span time.")
    eligible = (len(anchors) >= 2 and span > 0 and all(a.independent for a in anchors)
                and bool(config.source_clock and config.reference_clock) and bound is not None
                and bound <= config.maximum_alignment_error_s and abs(scale - 1) <= .001)
    status = "aligned" if eligible else "uncertain" if anchors or config.source_clock or config.reference_clock else "unconfigured"
    return SyncDiagnostics(status=status, offset_s=offset, scale=scale, drift_ppm=(scale - 1) * 1e6,
                           anchor_count=len(anchors), anchor_span_s=span, residuals_s=residuals,
                           maximum_residual_s=maximum, uncertainty_bound_s=bound, warnings=warnings)


def match_diagnostics(session: FieldSession, event_id: str, variant: str = "original") -> dict:
    wrapped = next((m for m in session.measurements if m.event_id == event_id and m.variant == variant), None)
    decision = next((m for m in session.matches if m.event_id == event_id), None)
    reference = next((r for r in session.reference_events
                      if decision is not None and r.id == decision.reference_id), None)
    sync = synchronization(session.sync)
    reasons = []
    if not session.calibration_compatible:
        reasons.append("archived_camera_configuration_changed")
    timing_issues = session.timing_summary.get("issues", {})
    flagged = (isinstance(timing_issues, dict) and any(
        isinstance(timing_issues.get(key), (int, float)) and timing_issues[key] > 0
        for key in ("missing_timestamp", "duplicate_timestamp", "backward_timestamp", "timebase_changed", "flagged_frames")))
    if flagged or "fallback" in session.source_timebase.casefold():
        reasons.append("source_timing_quality_flagged")
    if wrapped is None:
        reasons.append("missing_measurement_variant")
    if decision is None or decision.association != "matched":
        reasons.append("reference_association_" + (decision.association if decision else "unmatched"))
    if decision is not None and (not decision.correspondence_confirmed or not decision.method):
        reasons.append("event_correspondence_not_confirmed")
    if reference is None:
        reasons.append("missing_reference")
    elif not reference.independent or reference.provenance == "recorded_unverified":
        reasons.append("reference_not_independent")
    if session.provenance == "recorded_unverified":
        reasons.append("session_provenance_unverified")
    if reference is not None and session.provenance == "synthetic" and reference.provenance != "synthetic":
        reasons.append("mixed_synthetic_and_real_reference")
    if reference is not None and session.provenance == "independent_reference" and reference.provenance != "independent_reference":
        reasons.append("reference_provenance_mismatch")
    if sync.status != "aligned":
        reasons.append("synchronization_not_confirmed")
    aligned_start = aligned_end = delta = None
    if reference is not None:
        aligned_start = sync.offset_s + sync.scale * reference.timestamp_s
        aligned_end = sync.offset_s + sync.scale * (reference.interval_end_s if reference.interval_end_s is not None
                                                   else reference.timestamp_s)
        if aligned_start < 0 or aligned_end < 0:
            reasons.append("reference_time_before_source_origin")
    if wrapped is not None:
        measurement = wrapped.measurement
        matching_sources = {measurement.source_id, f"{measurement.source_id}:observation:{measurement.session_id}"}
        if session.source.source_id not in matching_sources:
            reasons.append("measurement_source_mismatch")
        start = measurement.gate_a_timestamp_s
        end = measurement.gate_b_timestamp_s
        if start is not None and end is not None:
            start, end = sorted((start, end))
        else:
            start = end = measurement.timestamp_s
        if start is not None and (start < 0 or end < 0):
            reasons.append("negative_measurement_timestamp")
        if start is None or aligned_start is None:
            reasons.append("missing_event_timing")
        else:
            # Compare intervals by separation, never select a reference by its numerical error.
            delta = max(0.0, aligned_start - end, start - aligned_end)
            tolerance = session.sync.maximum_alignment_error_s
            if delta > tolerance:
                reasons.append("reference_event_time_mismatch")
            if sync.anchor_count >= 2:
                anchor_min = min(a.source_timestamp_s for a in session.sync.anchors)
                anchor_max = max(a.source_timestamp_s for a in session.sync.anchors)
                if start < anchor_min or end > anchor_max:
                    reasons.append("event_outside_synchronization_anchor_span")
                if aligned_start < anchor_min or aligned_end > anchor_max:
                    reasons.append("reference_outside_synchronization_anchor_span")
        if measurement.status == "rejected":
            reasons.append("rejected_measurement")
        if measurement.estimated_speed_kmh is None:
            reasons.append("missing_estimated_speed")
    reference_reasons = [reason for reason in reasons if reason not in
                         {"rejected_measurement", "missing_estimated_speed"}]
    return {"event_id": event_id, "variant": variant,
            "reference_id": reference.id if reference else None,
            "association": decision.association if decision else "unmatched",
            "eligible": not reasons, "reference_eligible": not reference_reasons, "exclusion_reasons": reasons,
            "aligned_reference_timestamp_s": aligned_start,
            "aligned_reference_interval_end_s": aligned_end,
            "interval_separation_s": delta,
            "reference_speed_kmh": reference.speed_kmh if reference else None}


def eligibility(session: FieldSession) -> dict:
    rows = [match_diagnostics(session, item.event_id, item.variant) for item in session.measurements]
    events = {item.event_id for item in session.measurements}
    matched = sum(item.association == "matched" for item in session.matches)
    confirmed = {row["event_id"] for row in rows if row["eligible"]}
    warnings = ["Reference independence and event correspondence are author declarations, not instrument certification."]
    if "issues" not in session.timing_summary:
        warnings.append("Detailed source timestamp-integrity counters were not supplied; timing quality is not independently established by metadata alone.")
    return {"session_id": session.id, "provenance": session.provenance, "partition": session.partition,
            "measurement_count": len(session.measurements), "vehicle_event_count": len(events),
            "reference_count": len(session.reference_events), "matched_event_count": matched,
            "eligible_event_count": len(confirmed), "independent_real_world_eligible_count":
            len(confirmed) if session.provenance == "independent_reference" else 0,
            "real_world_reference_available": session.provenance == "independent_reference" and bool(confirmed),
            "sync_diagnostics": synchronization(session.sync).model_dump(mode="json"), "rows": rows,
            "warnings": warnings}


def import_references(data: bytes, filename: str) -> list[ReferenceEvent]:
    if len(data) > MAX_FIELD_BYTES:
        raise ValueError("Field imports are limited to 8 MiB.")
    try:
        decoded = data.decode("utf-8-sig")
    except UnicodeDecodeError as error:
        raise ValueError("Use UTF-8 CSV or JSON.") from error
    suffix = Path(filename).suffix.casefold()
    if suffix == ".json":
        raw = json.loads(decoded)
        if isinstance(raw, dict) and set(raw) == {"reference_events"}:
            raw = raw["reference_events"]
        if not isinstance(raw, list):
            raise ValueError("Reference JSON must be a list or an object containing only reference_events.")
    elif suffix == ".csv":
        reader = csv.DictReader(io.StringIO(decoded), strict=True)
        required = {"id", "timestamp_s", "speed", "units", "method", "provenance", "independent"}
        if not reader.fieldnames or not required.issubset(reader.fieldnames):
            raise ValueError("Reference CSV is missing required columns: " + ", ".join(sorted(required)))
        if len(set(reader.fieldnames)) != len(reader.fieldnames) or set(reader.fieldnames) - set(ReferenceEvent.model_fields):
            raise ValueError("Reference CSV columns must be unique supported fields.")
        raw = []
        for row in reader:
            if len(raw) >= 10000:
                raise ValueError("Reference imports are limited to 10000 events.")
            if None in row or any(value is None for value in row.values()):
                raise ValueError("Reference CSV row has the wrong number of columns.")
            boolean = row["independent"].casefold()
            if boolean not in {"true", "false", "1", "0"}:
                raise ValueError("Reference independent must be true or false.")
            row["independent"] = boolean in {"true", "1"}
            for key in ("interval_end_s", "instrument_id", "uncertainty_kmh"):
                if key in row and row[key] == "":
                    row[key] = None
            raw.append(row)
    else:
        raise ValueError("Choose .csv or .json references.")
    if len(raw) > 10000:
        raise ValueError("Reference imports are limited to 10000 events.")
    references = [ReferenceEvent.model_validate(item) for item in raw]
    if len({item.id for item in references}) != len(references):
        raise ValueError("Reference identifiers must be unique.")
    return references
