"""Gate-to-gate displacement estimates using retained source-frame timestamps.

No positions are smoothed: raw bottom-center points and timestamps remain
available for inspection. Quality flags describe checks, not measured accuracy.
Defaults: >0.25 s sampling is approximate, >1 s breaks continuity, three
observations are required, and >250 km/h displacement is rejected. These
configurable heuristics require scene-specific evaluation, not legal authority.
"""

from collections import deque
from dataclasses import dataclass, field
from math import hypot, isfinite
from time import perf_counter
from typing import TYPE_CHECKING

from .measurement_models import Point, PositionSample, SpeedMeasurement
from .measurement_quality import QualityEvidence, box_overlap_fraction, summarize_quality

if TYPE_CHECKING:
    from .calibration import CalibrationTransform
    from .calibration_models import GateDiagnostics


@dataclass(frozen=True)
class SpeedOptions:
    # These are conservative continuity guards, not road limits or uncertainty bounds.
    approximate_gap_s: float = 0.25
    maximum_gap_s: float = 1.0
    maximum_speed_kmh: float = 250.0
    minimum_samples: int = 3
    history_size: int = 120
    maximum_measurements: int = 1000
    near_gate_distance_m: float = 1.0
    region_margin_warning_px: float = 8.0
    contact_residual_warning_px: float = 8.0

    def __post_init__(self):
        if not (0 < self.approximate_gap_s <= self.maximum_gap_s):
            raise ValueError("Sampling gap thresholds must be positive and ordered.")
        if not isfinite(self.maximum_speed_kmh) or self.maximum_speed_kmh <= 0:
            raise ValueError("The speed guard must be finite and positive.")
        if self.minimum_samples < 3 or self.history_size < 3 or self.maximum_measurements < 1:
            raise ValueError("Require at least three samples and a positive history limit.")
        if any(not isfinite(value) or value <= 0 for value in (
            self.near_gate_distance_m, self.region_margin_warning_px, self.contact_residual_warning_px,
        )):
            raise ValueError("Quality diagnostic thresholds must be finite and positive.")


@dataclass(frozen=True)
class Crossing:
    gate: str
    timestamp_s: float
    position: Point
    fraction: float
    interval_s: float = 0.0


def _cross(a: Point, b: Point) -> float:
    return a[0] * b[1] - a[1] * b[0]


def gate_intersection(start: Point, end: Point, gate: tuple[Point, Point]) -> tuple[float, Point] | None:
    """Return path fraction and position for a finite-segment crossing.

    A gate touch belongs to the segment ending there; excluding fraction zero
    prevents counting the same contact again on the next source frame.
    """
    if not all(isfinite(value) for point in (start, end, *gate) for value in point):
        return None
    movement = (end[0] - start[0], end[1] - start[1])
    line = (gate[1][0] - gate[0][0], gate[1][1] - gate[0][1])
    denominator = _cross(movement, line)
    if abs(denominator) < 1e-10:
        return None
    offset = (gate[0][0] - start[0], gate[0][1] - start[1])
    fraction = _cross(offset, line) / denominator
    along_gate = _cross(offset, movement) / denominator
    if not (1e-9 < fraction <= 1 + 1e-9 and -1e-9 <= along_gate <= 1 + 1e-9):
        return None
    fraction = min(fraction, 1.0)
    return fraction, (start[0] + movement[0] * fraction, start[1] + movement[1] * fraction)


@dataclass
class _TrackMeasurement:
    track_id: int
    category: str
    history: deque
    previous: PositionSample | None = None
    first: Crossing | None = None
    crossings: dict[str, Crossing] = field(default_factory=dict)
    pending_contacts: dict[str, tuple[Crossing, float]] = field(default_factory=dict)
    state: str = "waiting"
    sample_count: int = 0
    quality_reasons: list[str] = field(default_factory=list)
    result: SpeedMeasurement | None = None
    age_s: float | None = None
    evidence: QualityEvidence = field(default_factory=QualityEvidence)


class SpeedEstimator:
    def __init__(
        self,
        transform: "CalibrationTransform | None",
        gates: "GateDiagnostics | None",
        source_id: str,
        calibration_id: str | None,
        session_id: str,
        options: SpeedOptions | None = None,
    ):
        self.transform = transform
        self.gates = gates
        self.source_id = source_id
        self.calibration_id = calibration_id
        self.session_id = session_id
        self.options = options or SpeedOptions()
        self.measurements: list[SpeedMeasurement] = []
        self._results_by_track: dict[int, SpeedMeasurement] = {}
        self._tracks: dict[int, _TrackMeasurement] = {}
        self._last_timestamp: float | None = None
        self.last_profile = {"projection_ms": 0.0, "gate_events_ms": 0.0}
        self._gate_geometry = []
        if gates and gates.valid:
            for name, gate in (("A", gates.world_a), ("B", gates.world_b)):
                line = (gate[1][0] - gate[0][0], gate[1][1] - gate[0][1])
                self._gate_geometry.append((name, gate, line))

    @property
    def ready(self) -> bool:
        return bool(self.transform is not None and self.gates is not None and self.gates.valid)

    def clear(self, reason: str | None = None) -> None:
        """Begin an empty measurement history; previous IDs cannot leak into it."""
        self.measurements.clear()
        self._results_by_track.clear()
        self._tracks.clear()
        self._last_timestamp = None

    def interrupt(self, reason: str) -> None:
        """Break continuity across a pause, source gap, or configuration change."""
        for track in self._tracks.values():
            if track.state == "measuring":
                self._reject(track, reason, self._last_timestamp)
            track.previous = None
            track.pending_contacts.clear()

    def finish(self, reason: str = "Observation ended before both gates were crossed.") -> None:
        self.interrupt(reason)

    def update(self, tracks: list[dict], timestamp_s: float | None, timing_valid: bool = True) -> list[dict]:
        self.last_profile = {"projection_ms": 0.0, "gate_events_ms": 0.0}
        finite_time = timestamp_s is not None and isfinite(timestamp_s)
        chronological = finite_time and (self._last_timestamp is None or timestamp_s > self._last_timestamp)
        time_reason = None
        if not finite_time:
            time_reason = "Missing or nonfinite source-frame timestamp."
        elif not chronological:
            time_reason = "Source-frame timestamps must strictly increase."
        elif not timing_valid:
            time_reason = "Source timing is a diagnostic fallback and cannot measure speed."
        if time_reason:
            self.interrupt(time_reason)
        if chronological:
            self._last_timestamp = timestamp_s
        present = {track["id"] for track in tracks}
        for track in list(self._tracks.values()):
            if track.track_id not in present:
                if track.state == "measuring":
                    self._reject(track, "Track was lost between gates.", timestamp_s if finite_time else None)
                # Retain the bounded result for deduplication, not 120 position
                # samples for every vehicle in a long-running camera session.
                del self._tracks[track.track_id]

        enriched = []
        for raw in tracks:
            track = self._tracks.get(raw["id"])
            if track is None:
                result = self._results_by_track.get(raw["id"])
                track = _TrackMeasurement(raw["id"], raw["category"], deque(maxlen=self.options.history_size),
                                          result=result, state=("rejected" if result.status == "rejected" else "completed") if result else "waiting")
                self._tracks[raw["id"]] = track
            sample = self._position(raw, timestamp_s if finite_time else None, time_reason)
            track.age_s = raw.get("age_s")
            sample.overlap_fraction = max((box_overlap_fraction(raw["bbox"], other["bbox"])
                                           for other in tracks if other["id"] != raw["id"] and not other.get("missed", 0)), default=0.0)
            self._annotate_sample(track, sample)
            self._quality_warnings(sample, raw)
            if raw["category"] != track.category:
                sample.valid = False
                sample.reasons.append("Track category changed; a likely identity switch invalidates continuity.")
            track.history.append(sample)
            track.evidence.observe(sample, self.gates, self.options.near_gate_distance_m)
            if not self.ready:
                track.state = "not_calibrated"
            elif not sample.valid:
                if track.state == "measuring":
                    self._reject(track, "; ".join(sample.reasons), sample.timestamp_s)
                track.previous = None
                track.pending_contacts.clear()
            elif track.state not in {"completed", "rejected"}:
                event_started = perf_counter()
                self._observe(track, sample)
                self.last_profile["gate_events_ms"] += (perf_counter() - event_started) * 1000
            enriched.append({
                **raw,
                "image_position": sample.image_position,
                "world_position": sample.world_position,
                "measurement_state": track.state,
                "position_diagnostics": [*sample.reasons, *sample.quality_warnings],
                "position_history": [item.model_dump() for item in track.history],
                "estimated_speed_kmh": (
                    track.result.estimated_speed_kmh
                    if self.ready and sample.valid and track.result is not None and track.result.status == "valid" else None
                ),
            })
        return enriched

    @staticmethod
    def _annotate_sample(track: _TrackMeasurement, sample: PositionSample) -> None:
        if not track.history or sample.timestamp_s is None:
            return
        previous = track.history[-1]
        if previous.timestamp_s is not None and sample.timestamp_s > previous.timestamp_s:
            sample.observation_gap_s = sample.timestamp_s - previous.timestamp_s
        if len(track.history) < 2 or not sample.valid or not all(item.valid for item in list(track.history)[-2:]):
            return
        earlier = track.history[-2]
        interval = previous.timestamp_s - earlier.timestamp_s
        if interval <= 0 or sample.observation_gap_s is None:
            return
        ratio = sample.observation_gap_s / interval
        for name, residual in (("image_position", "contact_prediction_residual_px"), ("world_position", "contact_prediction_residual_m")):
            start, last, current = getattr(earlier, name), getattr(previous, name), getattr(sample, name)
            if start is not None and last is not None and current is not None:
                predicted = (last[0] + (last[0] - start[0]) * ratio, last[1] + (last[1] - start[1]) * ratio)
                setattr(sample, residual, hypot(current[0] - predicted[0], current[1] - predicted[1]))

    def _quality_warnings(self, sample: PositionSample, raw: dict) -> None:
        if sample.region_margin_px is not None and 0 <= sample.region_margin_px < self.options.region_margin_warning_px:
            sample.quality_warnings.append(f"Ground contact is within {self.options.region_margin_warning_px:g} px of the measured region boundary.")
        if sample.overlap_fraction >= 0.3:
            sample.quality_warnings.append("Vehicle boxes overlap by at least 30% of the smaller box; partial occlusion is possible.")
        if (sample.contact_prediction_residual_px is not None
                and sample.contact_prediction_residual_px > self.options.contact_residual_warning_px):
            sample.quality_warnings.append(f"Contact motion residual exceeds {self.options.contact_residual_warning_px:g} px; inspect box jitter, acceleration or identity changes.")
        if "box_area_shrink_possible_partial_occlusion" in raw.get("tracking_diagnostics", []):
            sample.quality_warnings.append("Vehicle box area shrank sharply; partial occlusion or detector instability is possible.")

    def _position(self, raw: dict, timestamp_s: float | None, time_reason: str | None) -> PositionSample:
        x1, y1, x2, y2 = raw["bbox"]
        image = ((x1 + x2) / 2, y2)
        reasons = [time_reason] if time_reason else []
        world = None
        if not all(isfinite(value) for value in raw["bbox"]) or x2 <= x1 or y2 <= y1:
            reasons.append("Invalid vehicle bounding box.")
            image = None
        if raw.get("missed", 0) > 0 or raw.get("state") == "lost":
            reasons.append("Track was not observed in this frame; continuity is lost.")
        ambiguous = bool(raw.get("association_ambiguous", False))
        if ambiguous:
            reasons.append("Track association is ambiguous; vehicle identity continuity is uncertain.")
        margin = None
        if self.transform is None:
            reasons.append("Calibration required.")
        else:
            geometry = self.transform.data.geometry
            if x1 <= 1 or y1 <= 1 or x2 >= geometry.width - 1 or y2 >= geometry.height - 1:
                reasons.append("Partial bounding box touches an image boundary.")
            if image is not None:
                margin = self.transform.region_margin_px(image)
            if not reasons:
                projection_started = perf_counter()
                world = self.transform.project(image, require_inside=True)
                self.last_profile["projection_ms"] += (perf_counter() - projection_started) * 1000
                if world is None:
                    reasons.append("Ground-contact point is outside the calibrated region or has invalid projection.")
        if self.gates is None or not self.gates.valid:
            reasons.append("Valid measurement gates are required.")
        return PositionSample(timestamp_s=timestamp_s, image_position=image, world_position=world,
                              valid=not reasons, reasons=reasons, region_margin_px=margin,
                              association_ambiguous=ambiguous,
                              bbox=tuple(raw["bbox"]) if image is not None else None,
                              detection_confidence=raw.get("confidence"),
                              tracking_diagnostics=list(raw.get("tracking_diagnostics", [])))

    def _observe(self, track: _TrackMeasurement, sample: PositionSample) -> None:
        track.sample_count += 1
        previous = track.previous
        track.previous = sample
        if previous is None:
            track.sample_count = 1
            track.quality_reasons.clear()
            track.evidence = QualityEvidence()
            track.evidence.observe(sample, self.gates, self.options.near_gate_distance_m)
            return
        for warning in sample.quality_warnings:
            self._add_quality(track, warning)
        elapsed = sample.timestamp_s - previous.timestamp_s
        distance = hypot(sample.world_position[0] - previous.world_position[0],
                         sample.world_position[1] - previous.world_position[1])
        if elapsed > self.options.maximum_gap_s:
            if track.state == "measuring":
                self._reject(track, "Source sampling gap exceeded the continuity limit.", sample.timestamp_s)
            else:
                track.sample_count = 1
                track.quality_reasons.clear()
                track.pending_contacts.clear()
            return
        if elapsed > self.options.approximate_gap_s:
            self._add_quality(track, f"Source sampling gap exceeded {self.options.approximate_gap_s:g} s; crossing interpolation is coarse.")
        events = []
        for name, gate, line in self._gate_geometry:
            if name in track.crossings:
                continue
            before = _cross(line, (previous.world_position[0] - gate[0][0], previous.world_position[1] - gate[0][1]))
            after = _cross(line, (sample.world_position[0] - gate[0][0], sample.world_position[1] - gate[0][1]))
            pending = track.pending_contacts.get(name)
            if pending is not None:
                if abs(after) > 1e-9:
                    del track.pending_contacts[name]
                    if pending[1] * after < 0:
                        # Confirm a true crossing after a frame exactly on the
                        # gate, retaining that contact frame's source time.
                        events.append(pending[0])
                else:
                    along_gate = ((sample.world_position[0] - gate[0][0]) * line[0]
                                  + (sample.world_position[1] - gate[0][1]) * line[1]) / (line[0] ** 2 + line[1] ** 2)
                    if not 0 <= along_gate <= 1:
                        del track.pending_contacts[name]
                    else:
                        self._add_quality(track, "Repeated observations on a gate make its crossing time approximate.")
                        track.pending_contacts[name] = (
                            Crossing(name, sample.timestamp_s, sample.world_position, 0, elapsed), pending[1],
                        )
                continue
            intersection = gate_intersection(previous.world_position, sample.world_position, gate)
            if intersection is not None:
                fraction, position = intersection
                event = Crossing(name, previous.timestamp_s + elapsed * fraction, position, fraction, elapsed)
                if abs(after) <= 1e-9:
                    track.pending_contacts[name] = (event, before)
                else:
                    events.append(event)
        events.sort(key=lambda event: event.timestamp_s)
        if distance / elapsed * 3.6 > self.options.maximum_speed_kmh:
            reason = "Implausible position jump suggests an identity switch or invalid calibration."
            sample.reasons.append(reason)
            sample.valid = False
            if track.first is not None or events:
                if track.first is None:
                    track.first = events[0]
                    track.crossings[events[0].gate] = events[0]
                self._reject(track, reason, sample.timestamp_s)
            else:
                track.previous = None
                track.pending_contacts.clear()
            return
        if len(events) == 2:
            for event in events:
                track.crossings[event.gate] = event
            track.first = events[0]
            self._reject(track, "Both gates were crossed within one source-frame interval; insufficient observations.", sample.timestamp_s)
            return
        for event in events:
            track.crossings[event.gate] = event
            if track.first is None:
                track.first = event
                track.state = "measuring"
                if event.gate == "B" and not self.gates.allow_reverse:
                    self._reject(track, "B-to-A traversal is disabled; Gate B was crossed first.", sample.timestamp_s)
                    return
            else:
                self._complete(track, event, sample.timestamp_s)

    @staticmethod
    def _add_quality(track: _TrackMeasurement, reason: str) -> None:
        if reason not in track.quality_reasons:
            track.quality_reasons.append(reason)

    def _complete(self, track: _TrackMeasurement, end: Crossing, timestamp_s: float) -> None:
        start = track.first
        distance = hypot(end.position[0] - start.position[0], end.position[1] - start.position[1])
        elapsed = end.timestamp_s - start.timestamp_s
        reason = None
        if track.sample_count < self.options.minimum_samples:
            reason = f"At least {self.options.minimum_samples} source observations are required."
        elif not isfinite(elapsed) or elapsed <= 0:
            reason = "Gate crossing timestamps do not have a positive elapsed interval."
        elif not isfinite(distance) or distance <= 0:
            reason = "Gate crossing positions do not define a positive finite distance."
        elif distance / elapsed * 3.6 > self.options.maximum_speed_kmh:
            reason = f"Estimated speed exceeds the configured {self.options.maximum_speed_kmh:g} km/h plausibility guard."
        if reason:
            self._reject(track, reason, timestamp_s)
            return
        calibration_warnings = getattr(getattr(self.transform, "diagnostics", None), "warnings", [])
        for warning in calibration_warnings:
            # General limitations remain visible in calibration diagnostics;
            # only an observed problem makes this traversal approximate.
            if not warning.startswith(("No independent check points", "Four inlier points", "A stationary camera")):
                self._add_quality(track, f"Calibration: {warning}")
        for warning in self.gates.warnings:
            self._add_quality(track, f"Gates: {warning}")
        result = self._record(track, timestamp_s, "approximate" if track.quality_reasons else "valid", list(track.quality_reasons))
        result.end_position = end.position
        result.distance_m = distance
        result.elapsed_seconds = elapsed
        result.estimated_speed_kmh = round(distance / elapsed * 3.6, 1)
        track.state = "completed"

    def _reject(self, track: _TrackMeasurement, reason: str, timestamp_s: float | None) -> None:
        if track.state == "rejected":
            return
        # If a continuity check invalidates a just-completed crossing, replace it.
        if track.result is not None:
            self.measurements.remove(track.result)
        self._record(track, timestamp_s, "rejected", [*track.quality_reasons, reason])
        track.state = "rejected"
        track.previous = None
        track.pending_contacts.clear()

    def _record(self, track: _TrackMeasurement, timestamp_s: float | None, status: str, reasons: list[str]) -> SpeedMeasurement:
        gate_a, gate_b = track.crossings.get("A"), track.crossings.get("B")
        first = track.first
        last = max(track.crossings.values(), key=lambda crossing: crossing.timestamp_s) if len(track.crossings) == 2 else None
        result = SpeedMeasurement(
            id=f"{self.session_id}:{track.track_id}", track_id=track.track_id,
            source_id=self.source_id, session_id=self.session_id, calibration_id=self.calibration_id,
            category=track.category, gate_a_timestamp_s=gate_a.timestamp_s if gate_a else None,
            gate_b_timestamp_s=gate_b.timestamp_s if gate_b else None,
            start_position=first.position if first else None,
            end_position=last.position if last else None,
            distance_m=(hypot(last.position[0] - first.position[0], last.position[1] - first.position[1])
                        if first and last else None),
            elapsed_seconds=last.timestamp_s - first.timestamp_s if first and last else None,
            direction=("A_to_B" if first.gate == "A" else "B_to_A") if first else "unknown",
            status=status, reasons=reasons, sample_count=track.sample_count, timestamp_s=timestamp_s,
            diagnostics=summarize_quality(track, self.transform, self.gates, self.options.near_gate_distance_m),
            position_samples=[sample.model_copy(deep=True) for sample in track.history],
            calibration_metadata=self._calibration_metadata(),
        )
        self.measurements.append(result)
        self._results_by_track[track.track_id] = result
        for evicted in self.measurements[:-self.options.maximum_measurements]:
            if self._results_by_track.get(evicted.track_id) is evicted:
                del self._results_by_track[evicted.track_id]
        del self.measurements[:-self.options.maximum_measurements]
        track.result = result
        return result

    def _calibration_metadata(self) -> dict:
        if self.transform is None:
            return {}
        data = self.transform.data
        return {
            "calibration_id": self.calibration_id,
            "geometry": data.geometry.model_dump(mode="json"),
            "points": [point.model_dump(mode="json") for point in data.points],
            "check_points": [point.model_dump(mode="json") for point in data.check_points],
            "diagnostics": self.transform.diagnostics.model_dump(mode="json"),
            "gates": self.gates.model_dump(mode="json") if self.gates else None,
        }
