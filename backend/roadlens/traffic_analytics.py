"""Source-time traffic summaries with explicit exposure and retained-data limits."""

import csv
import io
import json
import math
import statistics
from collections import Counter, defaultdict
from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

from .validation import spreadsheet_cell


class TrafficAnalysisRequest(BaseModel):
    model_config = ConfigDict(extra="forbid", allow_inf_nan=False)
    session_ids: list[str] = Field(default_factory=list, max_length=200)
    include_current: bool = False
    interval_minutes: Literal[1, 5, 15, 30, 60] = 1
    category: str | None = Field(default=None, max_length=80)
    direction: str | None = Field(default=None, max_length=120)
    line_id: str | None = Field(default=None, max_length=160)
    status: Literal["counted", "suppressed"] | None = None
    start_s: float | None = Field(default=None, ge=0)
    end_s: float | None = Field(default=None, ge=0)
    speed_status: Literal["valid", "approximate"] = "valid"
    observation_started_after: datetime | None = None
    observation_started_before: datetime | None = None

    @model_validator(mode="after")
    def ordered_window(self):
        if len(set(self.session_ids)) != len(self.session_ids):
            raise ValueError("Choose each traffic observation once.")
        if self.start_s is not None and self.end_s is not None and self.end_s <= self.start_s:
            raise ValueError("The source-time end must follow its start.")
        for value in (self.observation_started_after, self.observation_started_before):
            if value is not None and (value.tzinfo is None or value.utcoffset() is None):
                raise ValueError("Observation date filters need an explicit timezone.")
        if (self.observation_started_after is not None and self.observation_started_before is not None
                and self.observation_started_before <= self.observation_started_after):
            raise ValueError("The observation date end must follow its start.")
        return self


def percentile(values, fraction):
    if not values:
        return None
    ordered = sorted(values)
    offset = (len(ordered) - 1) * fraction
    low, high = math.floor(offset), math.ceil(offset)
    return ordered[low] + (ordered[high] - ordered[low]) * (offset - low)


def speed_statistics(values):
    values = list(values)
    return {"n": len(values), "mean_kmh": statistics.fmean(values) if values else None,
            "median_kmh": statistics.median(values) if values else None,
            "minimum_kmh": min(values) if values else None, "maximum_kmh": max(values) if values else None,
            "p85_kmh": percentile(values, .85),
            "standard_deviation_kmh": statistics.pstdev(values) if values else None}


def _timestamp(row):
    value = row.get("timestamp_s")
    return value if isinstance(value, (int, float)) and not isinstance(value, bool) and math.isfinite(value) else None


def _in_window(value, request):
    return value is not None and (request.start_s is None or value >= request.start_s) and (
        request.end_s is None or value < request.end_s)


def merged_coverage(intervals, start=None, end=None):
    """Union exposure; overlapping rows never double the observed duration."""
    spans = []
    for row in intervals:
        left, right = row.get("start_s"), row.get("end_s")
        if not all(isinstance(t, (int, float)) and not isinstance(t, bool) and math.isfinite(t) for t in (left, right)):
            continue
        left, right = max(left, start) if start is not None else left, min(right, end) if end is not None else right
        if right > left:
            spans.append((left, right))
    merged = []
    for left, right in sorted(spans):
        if merged and left <= merged[-1][1]:
            merged[-1] = (merged[-1][0], max(merged[-1][1], right))
        else:
            merged.append((left, right))
    return merged


def _duration(intervals, start=None, end=None):
    return sum(right - left for left, right in merged_coverage(intervals, start, end))


def _rate(count, seconds, multiplier):
    return count * multiplier / seconds if seconds > 0 else None


def _configuration_signature(configuration):
    configuration = configuration or {}
    return json.dumps({key: configuration.get(key) for key in ("geometry", "lines", "zones", "calibration_id")},
                      sort_keys=True, separators=(",", ":"))


def _camera_signature(session):
    return json.dumps(session.get("camera", {}), sort_keys=True, separators=(",", ":"))


def _nonnegative_duration(value):
    return (isinstance(value, (int, float)) and not isinstance(value, bool)
            and math.isfinite(value) and value >= 0)


def analyze_traffic(sessions: list[dict], request: TrafficAnalysisRequest | None = None):
    request = request or TrafficAnalysisRequest()
    events, flow, zone_rows, measurements, occupancy, quality, comparisons = [], [], [], [], [], [], []
    current_states = []
    interval = request.interval_minutes * 60
    total_coverage, total_source_coverage, total_unconfigured_coverage, total_unknown_coverage, reported_count = 0.0, 0.0, 0.0, 0.0, 0
    reported_classes, reported_directions = Counter(), Counter()
    truncated_any, unsafe_rate, all_lifetime = False, False, bool(sessions)
    full_cohort = all(getattr(request, key) is None for key in ("category", "direction", "line_id", "status", "start_s", "end_s"))
    warnings = ["Counts are line crossings; summing multiple lines does not count unique physical vehicles.",
                "Normalized rates describe the covered source-time sample. Short or incomplete windows are not reliable hourly traffic volumes.",
                "Summed zone occupancy counts memberships; overlapping zones can include the same visible track more than once.",
                "Image occupancy and stationary thresholds are configurable heuristics, not complete road-network congestion or metric speed."]
    if request.observation_started_after is not None or request.observation_started_before is not None:
        selected = []
        for session in sessions:
            try:
                stamp = datetime.fromisoformat(session.get("started_at") or "")
                if stamp.tzinfo is None or stamp.utcoffset() is None:
                    raise ValueError("Missing timezone")
            except (ValueError, TypeError):
                quality.append({"session_id": session.get("id"), "code": "missing_observation_date",
                                "message": "Observation excluded from the date filter: no timezone-aware start metadata."})
                continue
            if ((request.observation_started_after is None or stamp >= request.observation_started_after)
                    and (request.observation_started_before is None or stamp <= request.observation_started_before)):
                selected.append(session)
        sessions = selected
        all_lifetime = bool(sessions)
        warnings.append("Observation date filters use declared start metadata only. Exposure and event rates still use source timestamps.")
    signatures = {_configuration_signature(session.get("configuration")) for session in sessions}
    camera_signatures = {_camera_signature(session) for session in sessions}
    if request.direction is not None or request.line_id is not None:
        warnings.append("Counting-line/direction speed filters require a uniquely linked speed_measurement_id. Speed subgroup directions refer to speed gates, which are independent of counting-line direction.")
    for session in sessions:
        sid = session.get("id") or session.get("session_id", "unknown")
        configurations = session.get("configurations") or ([session["configuration"]] if session.get("configuration") else [])
        known_configurations = {config.get("id"): config for config in configurations}
        line_configurations = {config.get("id") for config in configurations
                               if config.get("lines") and (request.line_id is None or any(
                                   line["id"] == request.line_id for line in config["lines"]))}
        source_coverage = session.get("coverage", [])
        coverage = [row for row in source_coverage if row.get("configuration_id") in line_configurations]
        source_seconds = _duration(source_coverage, request.start_s, request.end_s)
        unconfigured_seconds = _duration([row for row in source_coverage if row.get("configuration_id") in known_configurations
                                         and not known_configurations[row["configuration_id"]].get("lines")], request.start_s, request.end_s)
        unknown_seconds = _duration([row for row in source_coverage if row.get("configuration_id") not in known_configurations],
                                    request.start_s, request.end_s)
        seconds = _duration(coverage, request.start_s, request.end_s)
        rows = []
        missing_times = 0
        for event in session.get("events", []):
            if _timestamp(event) is None:
                missing_times += 1
                continue
            if not _in_window(_timestamp(event), request):
                continue
            if any(value is not None and event.get(key) != value for key, value in (
                    ("category", request.category), ("direction", request.direction),
                    ("line_id", request.line_id), ("status", request.status))):
                continue
            rows.append({**event, "session_id": sid})
        events.extend(rows)
        counted = [event for event in rows if event.get("status") == "counted"]
        diagnostics = session.get("diagnostics", {})
        truncated = bool(diagnostics.get("omitted_events") or diagnostics.get("omitted_coverage"))
        truncated_any |= truncated
        lifetime = session.get("summary", {})
        lifetime_available = (full_cohort and isinstance(lifetime.get("total_crossings"), int)
                              and not isinstance(lifetime.get("total_crossings"), bool))
        lifetime_counting_seconds = lifetime.get("covered_counting_duration_s")
        if not _nonnegative_duration(lifetime_counting_seconds):
            all_configurations_count = (bool(configurations) and all(config.get("lines") for config in configurations)
                                        and not diagnostics.get("omitted_configurations")
                                        and all(row.get("configuration_id") in line_configurations for row in source_coverage))
            lifetime_counting_seconds = lifetime.get("covered_duration_s") if all_configurations_count else None
        lifetime_exposure_available = full_cohort and _nonnegative_duration(lifetime_counting_seconds)
        all_lifetime &= lifetime_available
        count_for_summary = lifetime["total_crossings"] if lifetime_available else len(counted)
        seconds_for_summary = lifetime_counting_seconds if lifetime_exposure_available else seconds
        source_seconds_for_summary = (lifetime["covered_duration_s"] if full_cohort
                                      and _nonnegative_duration(lifetime.get("covered_duration_s")) else source_seconds)
        if lifetime_exposure_available and full_cohort and _nonnegative_duration(lifetime.get("covered_duration_s")):
            unconfigured_seconds = max(0, lifetime["covered_duration_s"] - lifetime_counting_seconds)
        unknown_alignment = unknown_seconds > 0 or bool(diagnostics.get("omitted_configurations"))
        session_unsafe_rate = ((truncated or unknown_alignment) and not (lifetime_available and lifetime_exposure_available))
        reported_count += count_for_summary
        total_coverage += seconds_for_summary
        total_source_coverage += source_seconds_for_summary
        total_unconfigured_coverage += unconfigured_seconds
        total_unknown_coverage += unknown_seconds
        unsafe_rate |= session_unsafe_rate
        reported_classes.update(lifetime.get("by_class", {}) if lifetime_available and lifetime.get("by_class")
                                else Counter(row.get("category", "unknown") for row in counted))
        reported_directions.update(lifetime.get("by_direction", {}) if lifetime_available and lifetime.get("by_direction")
                                   else Counter(row.get("direction", "unknown") for row in counted))
        config_ids = ({row.get("configuration_id") for row in coverage} | {row.get("configuration_id") for row in rows}) & line_configurations
        cumulative = 0
        for config_id in sorted(config_ids, key=str):
            config_coverage = [row for row in coverage if row.get("configuration_id") == config_id]
            config_events = [row for row in counted if row.get("configuration_id") == config_id]
            spans = merged_coverage(config_coverage, request.start_s, request.end_s)
            bins = {math.floor(row["timestamp_s"] / interval) for row in config_events}
            for left, right in spans:
                if math.ceil(right / interval) - math.floor(left / interval) > 10000:
                    raise ValueError("Choose a narrower source-time window; at most 10000 traffic intervals can be aggregated per coverage span.")
                bins.update(range(math.floor(left / interval), math.ceil(right / interval)))
            for index in sorted(bins):
                start, end = index * interval, (index + 1) * interval
                exposure = _duration(config_coverage, max(start, request.start_s) if request.start_s is not None else start,
                                     min(end, request.end_s) if request.end_s is not None else end)
                bucket = [row for row in config_events if start <= row["timestamp_s"] < end]
                cumulative += len(bucket)
                flow.append({"session_id": sid, "configuration_id": config_id, "start_s": start, "end_s": end,
                             "coverage_seconds": exposure, "count": len(bucket), "cumulative_count": cumulative,
                             "normalized_crossings_per_minute": None if truncated else _rate(len(bucket), exposure, 60),
                             "normalized_crossings_per_hour": None if truncated else _rate(len(bucket), exposure, 3600),
                             "retained_subset": truncated,
                             "complete_window": math.isclose(exposure, interval, abs_tol=1e-6),
                             "direction_counts": dict(Counter(row.get("direction", "unknown") for row in bucket)),
                             "class_counts": dict(Counter(row.get("category", "unknown") for row in bucket))})
        samples = [{**row, "session_id": sid} for row in session.get("occupancy_samples", []) if _in_window(_timestamp(row), request)]
        occupancy.extend(samples)
        latest = samples[-1] if samples else {}
        if request.start_s is None and request.end_s is None and session.get("summary"):
            latest = {**latest, **session["summary"], "configuration_id": (session.get("configuration") or {}).get("id")}
        current_states.append(latest)
        zone_definitions = {(config.get("id"), zone["id"]): zone for config in configurations for zone in config.get("zones", [])}
        for (config_id, zone_id), zone in zone_definitions.items():
            visits = [row for row in session.get("zone_events", []) if row.get("zone_id") == zone_id
                      and row.get("configuration_id") == config_id and _in_window(_timestamp(row), request)]
            dwell = [row["dwell_s"] for row in visits if row.get("kind") == "exit" and row.get("dwell_s") is not None]
            zone_rows.append({"session_id": sid, "configuration_id": config_id, "zone_id": zone_id, "zone_label": zone.get("label", zone_id),
                              "entries": sum(row.get("kind") == "entry" for row in visits),
                              "exits": sum(row.get("kind") == "exit" for row in visits),
                              "interrupted_visits": sum(row.get("kind") == "interrupted" for row in visits),
                              "completed_dwell_count": len(dwell), "mean_dwell_s": statistics.fmean(dwell) if dwell else None,
                              "maximum_dwell_s": max(dwell) if dwell else None,
                              "current_occupancy": latest.get("zone_occupancy", {}).get(zone_id, 0) if latest.get("configuration_id") == config_id else 0,
                              "coordinate_space": zone.get("coordinate_space", "image")})
        for wrapped in session.get("measurements", []):
            row = wrapped.get("measurement", wrapped)
            if ((request.direction is not None or request.line_id is not None)
                    and row.get("id") not in {event.get("speed_measurement_id") for event in counted if event.get("speed_measurement_id")}):
                continue
            if (row.get("status") != request.speed_status or row.get("calibration_id") is None
                    or not _in_window(_timestamp(row), request)):
                continue
            speed = row.get("estimated_speed_kmh")
            if not isinstance(speed, (int, float)) or isinstance(speed, bool) or not math.isfinite(speed) or speed < 0:
                continue
            if any(value is not None and row.get(key) != value for key, value in (("category", request.category),)):
                continue
            measurements.append({**row, "session_id": sid})
        session_warnings = []
        if len(signatures) > 1:
            session_warnings.append("Counting/zone geometry or calibration differs; these are not identical traffic streams.")
        if len(camera_signatures) > 1:
            session_warnings.append("Camera geometry, intrinsic profile or detector settings differ across observations.")
        if len(configurations) > 1:
            session_warnings.append("Configuration changed within this observation; intervals remain segmented.")
        if seconds < interval:
            session_warnings.append("Coverage is shorter than the requested interval.")
        if len(merged_coverage(coverage, request.start_s, request.end_s)) > 1:
            session_warnings.append("Observation coverage contains interruptions or source-time gaps.")
        if missing_times:
            quality.append({"session_id": sid, "code": "missing_event_timestamps", "value": missing_times,
                            "message": "Events without finite source timestamps are excluded from timed analytics."})
        if unconfigured_seconds > 0:
            quality.append({"session_id": sid, "code": "unconfigured_counting_coverage_seconds", "value": unconfigured_seconds,
                            "message": "Source coverage without an active counting line is excluded from crossing-rate exposure; occupancy and speed evidence remain available."})
        if unknown_alignment:
            quality.append({"session_id": sid, "code": "unknown_counting_configuration_coverage", "value": unknown_seconds,
                            "message": "Some source coverage cannot be assigned to retained counting configurations. Rates require the explicit lifetime counting-coverage counter."})
        for code, value in diagnostics.items():
            if value:
                quality.append({"session_id": sid, "code": code, "value": value,
                                "message": code.replace("_", " ")})
        if any("omitted" in key and value for key, value in diagnostics.items()):
            session_warnings.append("Retained records were bounded: filtered analytics and exports cover the retained subset, not lifetime totals.")
        for message in session_warnings:
            quality.append({"session_id": sid, "code": "coverage_or_comparison", "message": message})
        speeds = [row["estimated_speed_kmh"] for row in measurements if row["session_id"] == sid]
        comparisons.append({"session_id": sid, "name": session.get("name", sid), "source_id": session.get("source_id"),
                            "provenance": session.get("provenance", "recorded_unverified"),
                            "started_at": session.get("started_at"), "ended_at": session.get("ended_at"),
                            "coverage_seconds": seconds_for_summary, "count": count_for_summary,
                            "source_coverage_seconds": source_seconds_for_summary,
                            "unconfigured_source_coverage_seconds": unconfigured_seconds,
                            "unknown_configuration_coverage_seconds": unknown_seconds,
                            "retained_count": len(counted), "count_scope": "lifetime" if lifetime_available else "retained",
                            "normalized_crossings_per_minute": None if session_unsafe_rate else _rate(count_for_summary, seconds_for_summary, 60),
                            "normalized_crossings_per_hour": None if session_unsafe_rate else _rate(count_for_summary, seconds_for_summary, 3600),
                            "configuration_id": (session.get("configuration") or {}).get("id"),
                            "camera": session.get("camera", {}),
                            "comparable_configuration": len(signatures) <= 1 and len(camera_signatures) <= 1,
                            "speed_n": len(speeds), "mean_speed_kmh": statistics.fmean(speeds) if speeds else None,
                            "warnings": session_warnings})
    events.sort(key=lambda row: (row["session_id"], row["timestamp_s"], row.get("id", "")))
    flow.sort(key=lambda row: (row["session_id"], row["start_s"], str(row["configuration_id"])))
    chronological_counts = Counter()
    for row in flow:
        chronological_counts[row["session_id"]] += row["count"]
        row["cumulative_count"] = chronological_counts[row["session_id"]]
    counted = [row for row in events if row.get("status") == "counted"]
    classes = Counter({key: count for key, count in reported_classes.items() if count > 0})
    directions = Counter((row.get("direction", "unknown"), row.get("direction_label", row.get("direction", "unknown"))) for row in counted)
    speed_values = [row["estimated_speed_kmh"] for row in measurements]
    speeds = {"status": request.speed_status, **speed_statistics(speed_values)}
    speeds["distribution"] = [{"start_kmh": start, "end_kmh": start + 10, "count": sum(start <= v < start + 10 for v in speed_values)}
                              for start in range(0, (math.floor(max(speed_values, default=0) / 10) + 1) * 10, 10)]
    for key, dimension in (("by_class", "category"), ("by_direction", "direction")):
        groups = defaultdict(list)
        for row in measurements:
            groups[row.get(dimension, "unknown")].append(row["estimated_speed_kmh"])
        speeds[key] = [{dimension: label, **speed_statistics(values)} for label, values in sorted(groups.items())]
    speed_intervals = defaultdict(list)
    for row in measurements:
        speed_intervals[(row["session_id"], math.floor(row["timestamp_s"] / interval))].append(row["estimated_speed_kmh"])
    speeds["by_interval"] = [{"session_id": sid, "start_s": index * interval, "end_s": (index + 1) * interval,
                              **speed_statistics(values)} for (sid, index), values in sorted(speed_intervals.items())]
    return {"schema_version": 1, "interval_minutes": request.interval_minutes,
            "filters": request.model_dump(mode="json"),
            "selected_session_ids": [session.get("id") or session.get("session_id") for session in sessions],
            "units": {"timestamp_s": "source seconds", "coverage_seconds": "seconds",
                      "coverage_definition": "valid source-time exposure while at least one selected counting line is active",
                      "source_coverage_seconds": "seconds of all valid observation coverage", "dwell_s": "seconds",
                      "speed": "km/h", "normalized_crossings_per_minute": "crossings/minute of covered source time",
                      "normalized_crossings_per_hour": "crossings/hour of covered source time", "image_position": "configured image pixels"},
            "summary": {"total_crossings": reported_count, "counted_events": len(counted),
                        "retained_counted_events": len(counted), "count_scope": "lifetime" if all_lifetime else "retained" if full_cohort else "retained_filtered",
                        "incomplete_retained_data": truncated_any,
                        "suppressed_events": sum(row.get("status") == "suppressed" for row in events),
                        "coverage_seconds": total_coverage,
                        "source_coverage_seconds": total_source_coverage,
                        "unconfigured_source_coverage_seconds": total_unconfigured_coverage,
                        "unknown_configuration_coverage_seconds": total_unknown_coverage,
                        "normalized_crossings_per_minute": None if unsafe_rate else _rate(reported_count, total_coverage, 60),
                        "normalized_crossings_per_hour": None if unsafe_rate else _rate(reported_count, total_coverage, 3600),
                        "most_common_category": classes.most_common(1)[0][0] if classes else None,
                        "valid_speed_count": len(speed_values) if request.speed_status == "valid" else 0,
                        "speed_count": len(speed_values), "mean_speed_kmh": speeds["mean_kmh"],
                        "current_zone_occupancy": sum(sum(row.get("zone_occupancy", {}).values()) for row in current_states),
                        "visible_tracks": sum(row.get("visible_tracks", 0) for row in current_states),
                        "peak_interval_count": max((row["count"] for row in flow), default=0)},
            "events": events, "classes": [{"category": key, "count": count, "fraction": count / reported_count if reported_count else 0} for key, count in sorted(classes.items())],
            "directions": [{"direction": key, "direction_label": next((label for (d, label) in directions if d == key), key), "count": count}
                           for key, count in sorted(reported_directions.items())],
            "flow": flow,
            "zones": zone_rows, "speeds": speeds, "comparisons": comparisons, "quality": quality,
            "occupancy": occupancy, "warnings": warnings,
            "evidence_types": sorted({session.get("provenance", "recorded_unverified") for session in sessions})}


def traffic_table(report, table):
    if table == "speeds":
        value = report["speeds"]
        return [{"row_type": "overall", **{key: item for key, item in value.items() if not isinstance(item, (list, dict))}},
                *[{"row_type": "class", **row} for row in value["by_class"]],
                *[{"row_type": "direction", **row} for row in value["by_direction"]],
                *[{"row_type": "interval", **row} for row in value["by_interval"]]]
    if table not in ("events", "classes", "flow", "zones", "comparisons", "quality"):
        raise ValueError("Choose a supported traffic export table.")
    return report[table]


def traffic_export(report, table, format="json"):
    rows = traffic_table(report, table)
    if format == "json":
        return json.dumps({"schema_version": 1, "table": table, "interval_minutes": report["interval_minutes"],
                           "filters": report["filters"], "selected_session_ids": report["selected_session_ids"], "units": report["units"],
                           "summary": report["summary"], "warnings": report["warnings"], "evidence_types": report["evidence_types"], "rows": rows},
                          indent=2, ensure_ascii=False, allow_nan=False)
    if format != "csv":
        raise ValueError("Choose JSON or CSV.")
    columns = list(dict.fromkeys(key for row in rows for key in row)) or ["session_id"]
    output = io.StringIO(newline="")
    metadata = {"schema_version": 1, "table": table, "evidence_types": ";".join(report["evidence_types"]),
                "filters_json": json.dumps(report["filters"], ensure_ascii=False), "units_json": json.dumps(report["units"], ensure_ascii=False),
                "selected_session_ids_json": json.dumps(report["selected_session_ids"]), "warnings_json": json.dumps(report["warnings"], ensure_ascii=False),
                "incomplete_retained_data": report["summary"]["incomplete_retained_data"]}
    writer = csv.DictWriter(output, fieldnames=[*metadata, "export_row_type", *columns])
    writer.writeheader()
    for row in rows or [{}]:
        value = {**metadata, "export_row_type": "data" if rows else "metadata", **row}
        writer.writerow({key: spreadsheet_cell(json.dumps(item, ensure_ascii=False, allow_nan=False)
                         if isinstance(item, (list, dict)) else item) for key, item in value.items()})
    return output.getvalue()
