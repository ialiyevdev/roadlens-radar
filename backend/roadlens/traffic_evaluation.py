"""Counting checks from reviewed manual trajectories, separately from speed evidence."""

import math
from collections import Counter
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

from .annotation_metrics import annotation_metrics
from .annotation_models import AnnotationDocument
from .assignment import maximum_score_matching
from .field_store import assert_partitions
from .traffic_analytics import merged_coverage


class TrafficEvaluationRequest(BaseModel):
    model_config = ConfigDict(extra="forbid", allow_inf_nan=False)
    traffic_session_id: str = Field(min_length=1, max_length=160)
    field_session_id: str = Field(min_length=1, max_length=160)
    maximum_time_error_s: float = Field(default=.5, gt=0, le=10)
    maximum_position_error_px: float = Field(default=30, gt=0, le=1000)
    partition: Literal["development", "calibration", "held_out"] = "held_out"


def _side(point, line):
    start, end = line["start"], line["end"]
    dx, dy = end[0] - start[0], end[1] - start[1]
    return (dx * (point[1] - start[1]) - dy * (point[0] - start[0])) / math.hypot(dx, dy)


def _interpolate(left, right, line):
    first, second = _side(left[1], line), _side(right[1], line)
    if first * second >= 0:
        return None
    alpha = -first / (second - first)
    point = [left[1][0] + alpha * (right[1][0] - left[1][0]),
             left[1][1] + alpha * (right[1][1] - left[1][1])]
    dx, dy = line["end"][0] - line["start"][0], line["end"][1] - line["start"][1]
    fraction = ((point[0] - line["start"][0]) * dx + (point[1] - line["start"][1]) * dy) / (dx * dx + dy * dy)
    if not 0 <= fraction <= 1:
        return None
    return left[0] + alpha * (right[0] - left[0]), point, "positive" if second > first else "negative"


def truth_crossings(document: AnnotationDocument, configuration: dict, coverage=None):
    """Do not infer a crossing through an unreviewed/missing/occluded frame."""
    state, events, spans, counted = {}, [], [], set()
    previous = None
    gap = configuration.get("max_gap_s", 1)
    for frame in document.frames:
        continuous = (frame.reviewed and frame.timestamp_s is not None and previous is not None
                      and previous.reviewed and previous.timestamp_s is not None
                      and frame.index == previous.index + 1 and 0 < frame.timestamp_s - previous.timestamp_s <= gap)
        if continuous and coverage is not None:
            continuous = any(left <= previous.timestamp_s < frame.timestamp_s <= right for left, right in coverage)
        if continuous and any(item.occluded or item.bbox is None for observed in (previous, frame) for item in observed.objects):
            continuous = False
        if not continuous:
            state.clear()
        else:
            spans.append({"start_s": previous.timestamp_s, "end_s": frame.timestamp_s})
        if (not frame.reviewed or frame.timestamp_s is None
                or (coverage is not None and not any(left <= frame.timestamp_s <= right for left, right in coverage))):
            previous = frame
            continue
        visible = {item.identity for item in frame.objects if item.bbox is not None and not item.occluded}
        for key in list(state):
            if key[0] not in visible:
                del state[key]
        for item in frame.objects:
            if item.bbox is None or item.occluded:
                continue
            point = ((item.bbox[0] + item.bbox[2]) / 2, item.bbox[3])
            for line in configuration.get("lines", []):
                key = (item.identity, line["id"])
                side = _side(point, line)
                if abs(side) <= line.get("hysteresis_px", 3):
                    continue
                observed = (frame.timestamp_s, point)
                before = state.get(key)
                if before and _side(before[1], line) * side < 0:
                    crossing = _interpolate(before, observed, line)
                    crossing_key = (item.identity, line["id"], crossing[2]) if crossing else None
                    if crossing and crossing_key not in counted:
                        counted.add(crossing_key)
                        timestamp, position, direction = crossing
                        events.append({"id": f"manual:{item.identity}:{line['id']}:{len(events)}", "identity": item.identity,
                                       "timestamp_s": timestamp, "image_position": position, "category": item.category,
                                       "line_id": line["id"], "direction": direction,
                                       "configuration_id": configuration.get("id")})
                state[key] = observed
        previous = frame
    return events, merged_coverage(spans)


def evaluate_counting(artifact: dict, document: AnnotationDocument, field, request: TrafficEvaluationRequest,
                      all_fields=None):
    if all_fields is not None:
        assert_partitions(all_fields)
    if field.id != document.field_session_id or field.source.source_id != document.source_id:
        raise ValueError("Manual annotations do not belong to the selected field recording.")
    if field.partition != request.partition:
        raise ValueError("The selected field recording does not belong to the requested evaluation partition.")
    sources = {artifact.get("source_id"), artifact.get("field_source_id")}
    if field.source.source_id not in sources:
        raise ValueError("Traffic predictions and manual annotations must refer to the same original recording.")
    if ((artifact.get("provenance", "recorded_unverified") == "synthetic") != (field.provenance == "synthetic")
            or document.provenance != field.provenance):
        raise ValueError("Synthetic and recorded evidence must be evaluated separately with matching provenance.")
    configurations = artifact.get("configurations") or ([artifact["configuration"]] if artifact.get("configuration") else [])
    if not configurations:
        raise ValueError("Counting evaluation needs the archived counting-line configuration.")
    truth, evaluated_spans = [], []
    config_spans = {}
    for configuration in configurations:
        if configuration.get("geometry") != document.geometry.model_dump(mode="json"):
            raise ValueError("Counting lines and manual boxes must use identical source/undistorted image coordinates.")
        coverage = [row for row in artifact.get("coverage", []) if row.get("configuration_id") == configuration.get("id")]
        exposure = merged_coverage(coverage)
        candidates, reviewed = truth_crossings(document, configuration, exposure)
        spans = [(max(a, c), min(b, d)) for a, b in reviewed for c, d in exposure if min(b, d) > max(a, c)]
        config_spans[configuration.get("id")] = spans
        evaluated_spans.extend(spans)
        truth.extend(row for row in candidates if any(a <= row["timestamp_s"] <= b for a, b in spans))
    if not evaluated_spans:
        raise ValueError("No consecutive reviewed source frames overlap the counting observation coverage.")
    predictions = [row for row in artifact.get("events", []) if row.get("status") == "counted"
                   and isinstance(row.get("timestamp_s"), (int, float))
                   and any(a <= row["timestamp_s"] <= b for a, b in config_spans.get(row.get("configuration_id"), []))]
    scores = {}
    for i, expected in enumerate(truth):
        for j, predicted in enumerate(predictions):
            if expected["line_id"] != predicted.get("line_id") or expected["configuration_id"] != predicted.get("configuration_id"):
                continue
            dt = abs(expected["timestamp_s"] - predicted["timestamp_s"])
            position = predicted.get("image_position")
            if not position or len(position) != 2:
                continue
            distance = math.dist(expected["image_position"], position)
            if dt <= request.maximum_time_error_s and distance <= request.maximum_position_error_px:
                scores[(i, j)] = 2 - dt / request.maximum_time_error_s - distance / request.maximum_position_error_px
    pairs = maximum_score_matching(len(truth), len(predictions), scores)
    paired_truth, paired_predictions = {i for i, _ in pairs}, {j for _, j in pairs}
    confusion = Counter((truth[i]["category"], predictions[j].get("category", "unknown")) for i, j in pairs)
    correct_class = sum(n for (expected, predicted), n in confusion.items() if expected == predicted)
    correct_direction = sum(truth[i]["direction"] == predictions[j].get("direction") for i, j in pairs)
    duplicates = {j for j in range(len(predictions)) if j not in paired_predictions and any((i, j) in scores for i in paired_truth)}
    categories = sorted({row["category"] for row in truth} | {row.get("category", "unknown") for row in predictions})
    class_metrics = []
    for category in categories:
        tp = confusion[(category, category)]
        predicted_n = sum(row.get("category", "unknown") == category for row in predictions)
        truth_n = sum(row["category"] == category for row in truth)
        class_metrics.append({"category": category, "true_positive": tp, "predicted_n": predicted_n,
                              "truth_n": truth_n, "precision": tp / predicted_n if predicted_n else None,
                              "recall": tp / truth_n if truth_n else None})
    rows = [{"outcome": "matched", "truth": truth[i], "prediction": predictions[j],
             "class_correct": truth[i]["category"] == predictions[j].get("category"),
             "direction_correct": truth[i]["direction"] == predictions[j].get("direction"),
             "time_error_s": predictions[j]["timestamp_s"] - truth[i]["timestamp_s"]} for i, j in pairs]
    rows.extend({"outcome": "missed", "truth": row, "prediction": None} for i, row in enumerate(truth) if i not in paired_truth)
    rows.extend({"outcome": "duplicate" if j in duplicates else "false_positive", "truth": None, "prediction": row}
                for j, row in enumerate(predictions) if j not in paired_predictions)
    return {"schema_version": 1, "traffic_session_id": artifact.get("id"), "field_session_id": field.id,
            "partition": field.partition, "provenance": field.provenance,
            "prediction_provenance": artifact.get("provenance", "recorded_unverified"),
            "evidence_type": "synthetic" if field.provenance == "synthetic" else "manually_annotated_video",
            "truth_count": len(truth), "predicted_count": len(predictions), "matched_count": len(pairs),
            "missed_count": len(truth) - len(pairs), "false_positive_count": len(predictions) - len(pairs),
            "duplicate_count": len(duplicates), "count_error": len(predictions) - len(truth),
            "precision": len(pairs) / len(predictions) if predictions else None,
            "recall": len(pairs) / len(truth) if truth else None,
            "classification_sample_count": len(pairs), "classification_correct_count": correct_class,
            "classification_accuracy": correct_class / len(pairs) if pairs else None,
            "direction_sample_count": len(pairs), "direction_correct_count": correct_direction,
            "direction_accuracy": correct_direction / len(pairs) if pairs else None,
            "confusion_matrix": [{"truth": a, "prediction": b, "count": n} for (a, b), n in sorted(confusion.items())],
            "classes": class_metrics, "rows": rows, "reviewed_coverage": evaluated_spans,
            "tracking": ({"available": True, **annotation_metrics(document)}
                         if document.proposal_metadata is not None or any(frame.predictions for frame in document.frames)
                         else {"available": False, "reason": "No per-frame tracker proposal run or imported predictions are available; crossing events cannot score tracking continuity."}),
            "limitations": ["Truth crossings use bottom-center contacts on consecutive reviewed visible frames; unreviewed frames, occlusions and source gaps break trajectories.",
                            "A manual identity is counted once per line, configuration and direction, matching the engine's duplicate prevention definition.",
                            "Intervals adjacent to any fully occluded manual object are unscorable for all crossings; predictions there are excluded rather than treated as false positives.",
                            "Global maximum-cardinality time/line/position assignment ignores class and direction so their errors remain measurable.",
                            "Near-coincident crossings can remain ambiguous. Manual labels and identity continuity require independent review.",
                            "Only reviewed overlapping source-time coverage is scored. A duplicate is an unmatched prediction near an already matched truth crossing.",
                            "Counting/class evidence does not validate metric speed; independently matched references remain in Phase 4 validation."]}
