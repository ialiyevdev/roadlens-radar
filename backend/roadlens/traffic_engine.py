"""Incremental source-time crossing, classification and manually configured zones.

Temporary tracker IDs remain hypotheses. A narrow, explicitly reported duplicate
heuristic can suppress one isolated repeated crossing after an identity change;
it never establishes physical vehicle identity.
"""

from collections import Counter, OrderedDict, deque
from copy import deepcopy
from dataclasses import dataclass, field
from math import hypot, isfinite
from time import perf_counter
from uuid import uuid4

from .calibration_models import ImageGeometry
from .traffic_geometry import polygon_area, polygon_box_area, polygon_membership, segment_crossing, signed_distance
from .traffic_models import TrafficConfiguration, TrafficEvent, ZoneEvent

CATEGORIES = ("car", "truck", "bus", "motorcycle")


@dataclass
class _Identity:
    first_s: float
    last_s: float
    observations: int = 0
    weights: Counter = field(default_factory=Counter)
    category: str = "unknown"
    class_score: float = 0.0
    anchors: dict = field(default_factory=dict)
    counted: set = field(default_factory=set)
    zones: dict = field(default_factory=dict)
    positions: deque = field(default_factory=lambda: deque(maxlen=128))


class TrafficEngine:
    EVENT_LIMIT = 10_000
    SAMPLE_LIMIT = 5_000
    COVERAGE_LIMIT = 10_000
    IDENTITY_LIMIT = 4_096
    CONFIGURATION_LIMIT = 128

    def __init__(self, session_id: str, source_id: str, geometry: ImageGeometry | dict,
                 configuration: TrafficConfiguration | dict, provenance: str = "recorded_unverified"):
        if not session_id or len(session_id) > 240 or not source_id or len(source_id) > 240:
            raise ValueError("Traffic observations require bounded session and source identifiers.")
        if provenance not in ("synthetic", "recorded_unverified", "manually_annotated", "independent_reference"):
            raise ValueError("Unsupported traffic evidence provenance.")
        self.session_id, self.source_id, self.provenance = session_id, source_id, provenance
        self.geometry = ImageGeometry.model_validate(geometry)
        self.configuration = self._validated_configuration(configuration)
        self._configurations = deque([self.configuration.model_dump(mode="json")], maxlen=self.CONFIGURATION_LIMIT)
        self._events = deque(maxlen=self.EVENT_LIMIT)
        self._zone_events = deque(maxlen=self.EVENT_LIMIT)
        self._samples = deque(maxlen=self.SAMPLE_LIMIT)
        self._coverage = deque(maxlen=self.COVERAGE_LIMIT)
        self._identities: dict[int, _Identity] = {}
        self._retired_counts = OrderedDict()
        self._recent = deque(maxlen=512)
        self._diagnostics = Counter()
        self._by_class = Counter()
        self._by_direction = Counter()
        self._by_line = Counter()
        self._zone_summary: dict[str, dict] = {}
        self._last_s: float | None = None
        self._previous_frame_s: float | None = None
        self._watermark_s: float | None = None
        self._last_index: int | None = None
        self._last_sample_s: float | None = None
        self._coverage_open = False
        self._covered_s = 0.0
        self._covered_counting_s = 0.0
        self._profile = {}
        self._current = self._empty_current()

    def _validated_configuration(self, configuration):
        result = TrafficConfiguration.model_validate(configuration).model_copy(deep=True)
        if result.source_id != self.source_id or result.geometry != self.geometry:
            raise ValueError("Traffic configuration source and complete pixel geometry must match the observation.")
        return result

    def _empty_current(self):
        return {"tracks": {}, "zone_occupancy": {zone.id: 0 for zone in self.configuration.zones},
                "zone_occupancy_proxy": {zone.id: None if zone.coordinate_space == "ground" else 0.0
                                         for zone in self.configuration.zones},
                "visible_tracks": 0, "stationary_tracks": 0, "slow_tracks": None,
                "occupancy_level": "low_observed_occupancy", "timestamp_valid": None}

    def configure(self, configuration: TrafficConfiguration | dict):
        updated = self._validated_configuration(configuration)
        if updated == self.configuration:
            return
        self.interrupt("configuration_changed")
        # Each edit is an immutable configuration version, including an edited
        # document whose supplied ID has aged out of the retained history.
        updated = updated.model_copy(update={"id": str(uuid4())})
        for state in self._identities.values():
            state.counted.clear()
        self._retired_counts.clear()
        self.configuration = updated
        self._append(self._configurations, updated.model_dump(mode="json"), "omitted_configurations")
        self._current = self._empty_current()
        self._diagnostics["configuration_changes"] += 1

    def change_geometry(self, geometry: ImageGeometry | dict,
                        configuration: TrafficConfiguration | dict | None = None):
        """Retire prior pixel geometry without transforming any manual definitions."""
        updated = ImageGeometry.model_validate(geometry)
        if updated == self.geometry and configuration is None:
            return
        candidate = (TrafficConfiguration.model_validate(configuration) if configuration is not None
                     else TrafficConfiguration(source_id=self.source_id, geometry=updated))
        if candidate.source_id != self.source_id or candidate.geometry != updated:
            raise ValueError("Replacement traffic configuration must match the new source pixel geometry.")
        self.interrupt("source_geometry_changed")
        self.geometry = updated
        candidate = candidate.model_copy(update={"id": str(uuid4())})
        for state in self._identities.values():
            state.counted.clear()
        self._retired_counts.clear()
        self.configuration = candidate.model_copy(deep=True)
        self._append(self._configurations, candidate.model_dump(mode="json"), "omitted_configurations")
        self._current = self._empty_current()
        self._diagnostics["geometry_changes"] += 1

    def _append(self, collection, value, omitted_key):
        if len(collection) == collection.maxlen:
            self._diagnostics[omitted_key] += 1
        collection.append(value)

    def _zone_event(self, identity, state, zone, kind, timestamp_s, dwell_s=None, reasons=None):
        event = ZoneEvent(session_id=self.session_id, source_id=self.source_id, track_id=identity,
                          zone_id=zone.id, zone_label=zone.label, timestamp_s=timestamp_s,
                          kind=kind, dwell_s=dwell_s, category=state.category,
                          configuration_id=self.configuration.id, provenance=self.provenance,
                          diagnostic_reasons=reasons or []).model_dump(mode="json")
        self._append(self._zone_events, event, "omitted_zone_events")
        summary_key = f"{self.configuration.id}:{zone.id}"
        if summary_key not in self._zone_summary and len(self._zone_summary) >= 2048:
            del self._zone_summary[next(iter(self._zone_summary))]
            self._diagnostics["omitted_zone_summaries"] += 1
        summary = self._zone_summary.setdefault(summary_key, {
            "configuration_id": self.configuration.id, "zone_id": zone.id,
            "entries": 0, "exits": 0, "interrupted_visits": 0,
            "completed_dwell_n": 0, "completed_dwell_s": 0.0})
        if kind == "entry":
            summary["entries"] += 1
        elif kind == "exit":
            summary["exits"] += 1
            summary["completed_dwell_n"] += 1
            summary["completed_dwell_s"] += dwell_s or 0.0
        else:
            summary["interrupted_visits"] += 1

    def _break_identity(self, identity, state, reason):
        zones = {zone.id: zone for zone in self.configuration.zones}
        for zone_id, membership in state.zones.items():
            if membership["inside"] and zone_id in zones:
                self._zone_event(identity, state, zones[zone_id], "interrupted", state.last_s,
                                 membership["dwell_s"], [reason, "incomplete_zone_visit"])
        state.anchors.clear()
        state.zones.clear()
        state.positions.clear()

    def interrupt(self, reason: str):
        """Break interpolation and dwell coverage, preserving prior event evidence."""
        reason = str(reason)[:120] or "observation_interrupted"
        for identity, state in self._identities.items():
            self._break_identity(identity, state, reason)
        self._coverage_open = False
        self._last_s = None
        self._previous_frame_s = None
        self._last_index = None
        self._last_sample_s = None
        self._recent.clear()
        self._current = self._empty_current()
        self._diagnostics["interruptions"] += 1
        reason_key = f"interruption:{reason}"
        if reason_key in self._diagnostics or len(self._diagnostics) < 128:
            self._diagnostics[reason_key] += 1
        else:
            self._diagnostics["other_interruptions"] += 1

    @staticmethod
    def _point(value):
        if not isinstance(value, (list, tuple)) or len(value) != 2:
            return None
        try:
            point = float(value[0]), float(value[1])
        except (TypeError, ValueError, OverflowError):
            return None
        return point if all(isfinite(item) for item in point) else None

    def _usable(self, track):
        if not isinstance(track, dict) or track.get("missed", 0) or track.get("state") in ("lost", "removed"):
            return None
        identity = track.get("id")
        if isinstance(identity, bool) or not isinstance(identity, int) or identity < 1:
            return None
        point = self._point(track.get("image_position"))
        bbox = track.get("bbox")
        if point is None:
            if not isinstance(bbox, (tuple, list)) or len(bbox) != 4:
                return None
            try:
                point = ((float(bbox[0]) + float(bbox[2])) / 2, float(bbox[3]))
            except (TypeError, ValueError, OverflowError):
                return None
        if not all(isfinite(value) for value in point):
            return None
        if not 0 <= point[0] <= self.geometry.width or not 0 <= point[1] <= self.geometry.height:
            return None
        return identity, point

    def _classify(self, state, track):
        category, confidence = track.get("category"), track.get("confidence", 0)
        if not isinstance(confidence, (int, float)) or not isfinite(confidence) or not 0 <= confidence <= 1:
            confidence = 0.0
        confidence = float(confidence)
        state.observations += 1
        if category in CATEGORIES:
            state.weights[category] += confidence
        leaders = state.weights.most_common(2)
        state.category, state.class_score = "unknown", 0.0
        if leaders:
            winner, weight = leaders[0]
            total = sum(state.weights.values())
            state.class_score = min(1.0, weight / state.observations)
            margin = (weight - (leaders[1][1] if len(leaders) > 1 else 0)) / total if total else 0
            if (state.observations >= self.configuration.class_min_observations
                    and state.class_score >= self.configuration.class_min_confidence
                    and margin >= self.configuration.class_min_margin):
                state.category = winner

    def _crossings(self, identity, state, track, point, timestamp_s):
        candidates = []
        config = self.configuration
        hits = track.get("hits", state.observations)
        confirmed = isinstance(hits, (int, float)) and hits >= config.min_track_hits
        for line in config.lines:
            distance = signed_distance(point, line.start, line.end)
            side = 1 if distance > line.hysteresis_px else -1 if distance < -line.hysteresis_px else 0
            if not side:
                continue
            anchor = state.anchors.get(line.id)
            if anchor and side != anchor[0]:
                crossing = segment_crossing(anchor[1], point, line.start, line.end)
                direction = "positive" if side > 0 else "negative"
                key = (config.id, line.id, direction)
                if crossing and key not in state.counted:
                    if confirmed:
                        fraction, position = crossing
                        event_s = anchor[2] + fraction * (timestamp_s - anchor[2])
                        reasons = ["finite_segment_crossing", "stable_sides_outside_hysteresis",
                                   "temporary_track_identity_unverified"]
                        if timestamp_s - anchor[2] > config.max_gap_s / 2:
                            reasons.append("crossing_interpolated_across_short_observation_gap")
                        if track.get("association_ambiguous"):
                            reasons.append("tracking_association_ambiguous")
                        if state.category == "unknown":
                            reasons.append("class_evidence_insufficient_or_uncertain")
                        candidates.append((identity, state, track, line, direction, event_s, position, reasons))
                        state.counted.add(key)
                    else:
                        self._diagnostics["tentative_crossings_not_counted"] += 1
                elif crossing:
                    self._diagnostics["repeat_track_crossings_ignored"] += 1
            state.anchors[line.id] = (side, point, timestamp_s)
        return candidates

    def _create_events(self, candidates, visible_ids):
        for identity, state, track, line, direction, timestamp_s, position, reasons in candidates:
            config = self.configuration
            nearby = [event for event in self._recent
                      if event["line_id"] == line.id and event["direction"] == direction
                      and event["track_id"] != identity and event["track_id"] not in visible_ids
                      and 0 <= timestamp_s - event["timestamp_s"] <= config.identity_suppression_s
                      and state.first_s > event["timestamp_s"]
                      and hypot(position[0] - event["image_position"][0], position[1] - event["image_position"][1])
                      <= config.identity_suppression_px]
            simultaneous = sum(other[3].id == line.id and other[4] == direction
                               and abs(other[5] - timestamp_s) <= config.identity_suppression_s
                               and hypot(other[6][0] - position[0], other[6][1] - position[1])
                               <= config.identity_suppression_px for other in candidates)
            suppressed = len(nearby) == 1 and simultaneous == 1
            if suppressed:
                reasons += ["possible_identity_fragment_duplicate_suppressed", "spatial_time_suppression_is_heuristic"]
            elif nearby:
                reasons += ["ambiguous_fragment_candidates_not_suppressed"]
                self._diagnostics["ambiguous_fragment_crossings"] += 1
            speed = track.get("estimated_speed_kmh")
            if (track.get("speed_status") != "valid" or not isinstance(speed, (int, float))
                    or not isfinite(speed) or not 0 <= speed <= 500):
                speed = None
            raw_confidence = track.get("confidence")
            if (not isinstance(raw_confidence, (int, float)) or not isfinite(raw_confidence)
                    or not 0 <= raw_confidence <= 1):
                raw_confidence = None
            raw_category = track.get("category")
            event = TrafficEvent(session_id=self.session_id, source_id=self.source_id, track_id=identity,
                                 timestamp_s=timestamp_s, line_id=line.id, line_label=line.label,
                                 direction=direction,
                                 direction_label=line.positive_label if direction == "positive" else line.negative_label,
                                 category=state.category, class_score=state.class_score,
                                 class_observations=state.observations,
                                 raw_category=str(raw_category)[:80] if raw_category is not None else None,
                                 raw_confidence=raw_confidence, class_evidence=dict(state.weights),
                                 status="suppressed" if suppressed else "counted",
                                 diagnostic_reasons=reasons, configuration_id=config.id,
                                 provenance=self.provenance, image_position=position,
                                 measured_speed_kmh=speed).model_dump(mode="json")
            self._append(self._events, event, "omitted_events")
            self._diagnostics["suppressed_crossings" if suppressed else "counted_crossings"] += 1
            if not suppressed:
                self._by_class[state.category] += 1
                self._by_direction[direction] += 1
                if line.id not in self._by_line and len(self._by_line) >= 2048:
                    del self._by_line[next(iter(self._by_line))]
                    self._diagnostics["omitted_line_summaries"] += 1
                self._by_line[line.id] += 1
                self._recent.append(event)

    def _zones(self, identity, state, track, point, timestamp_s):
        occupied, proxies = [], {}
        for zone in self.configuration.zones:
            position = point if zone.coordinate_space == "image" else self._point(track.get("world_position"))
            if position is None:
                previous = state.zones.pop(zone.id, None)
                if previous and previous["inside"]:
                    self._zone_event(identity, state, zone, "interrupted", state.last_s, previous["dwell_s"],
                                     ["missing_calibrated_ground_position", "incomplete_zone_visit"])
                continue
            inside, margin = polygon_membership(position, zone.points)
            previous = state.zones.get(zone.id)
            stable = inside if margin > zone.hysteresis else previous["inside"] if previous else False
            if previous is None:
                previous = {"inside": False, "last_s": timestamp_s, "dwell_s": 0.0}
            if stable and not previous["inside"]:
                previous["dwell_s"] = 0.0
                self._zone_event(identity, state, zone, "entry", timestamp_s,
                                 reasons=["first_observed_inside_zone"] if state.observations == 1 else [])
            elif stable and previous["inside"]:
                elapsed = timestamp_s - previous["last_s"]
                if (0 < elapsed <= self.configuration.max_gap_s
                        and previous["last_s"] == self._previous_frame_s):
                    previous["dwell_s"] += elapsed
            elif not stable and previous["inside"]:
                self._zone_event(identity, state, zone, "exit", timestamp_s, previous["dwell_s"],
                                 ["observed_inside_dwell_lower_bound"])
            previous.update(inside=stable, last_s=timestamp_s)
            state.zones[zone.id] = previous
            if stable:
                occupied.append(zone.id)
            if zone.coordinate_space == "image":
                bbox = track.get("bbox")
                if isinstance(bbox, (tuple, list)) and len(bbox) == 4:
                    try:
                        values = tuple(float(value) for value in bbox)
                        if all(isfinite(value) for value in values) and values[2] > values[0] and values[3] > values[1]:
                            proxies[zone.id] = polygon_box_area(zone.points, values) / polygon_area(zone.points)
                    except (ValueError, TypeError, OverflowError):
                        pass
        return occupied, proxies

    def _stationary(self, state, point, timestamp_s):
        # At most two samples per second: a 60 s configured window stays bounded.
        # Every observation can reset the window; sub-sample excursions must not
        # disappear when a moving object returns between retained samples.
        if any(hypot(point[0] - old[0], point[1] - old[1]) > self.configuration.stationary_radius_px
               for _, old in state.positions):
            state.positions.clear()
        if not state.positions or timestamp_s - state.positions[-1][0] >= .5:
            state.positions.append((timestamp_s, point))
        cutoff = timestamp_s - self.configuration.stationary_window_s
        while len(state.positions) > 1 and state.positions[1][0] <= cutoff:
            state.positions.popleft()
        return (bool(state.positions) and timestamp_s - state.positions[0][0] >= self.configuration.stationary_window_s
                and all(hypot(point[0] - old[0], point[1] - old[1]) <= self.configuration.stationary_radius_px
                        for _, old in state.positions))

    def _untimed_image_observation(self, tracks):
        """Retain visible image facts without a clock, trajectory or dwell claim."""
        current = self._empty_current()
        current.update(timestamp_valid=False, stationary_tracks=None,
                       observation_note="Untimed image observation; crossings, dwell, stationary and slow indicators are unavailable.")
        image_zones = [zone for zone in self.configuration.zones if zone.coordinate_space == "image"]
        current["unavailable_zone_ids"] = [zone.id for zone in self.configuration.zones if zone.coordinate_space == "ground"]
        for track in tracks:
            result = self._usable(track)
            if result is None:
                continue
            identity, point = result
            if identity in current["tracks"]:
                continue
            if len(current["tracks"]) >= self.IDENTITY_LIMIT:
                self._diagnostics["omitted_frame_tracks"] += 1
                continue
            occupied = []
            for zone in image_zones:
                inside, margin = polygon_membership(point, zone.points)
                if inside and margin > 1e-9:
                    occupied.append(zone.id)
                    current["zone_occupancy"][zone.id] += 1
                bbox = track.get("bbox")
                if isinstance(bbox, (tuple, list)) and len(bbox) == 4:
                    try:
                        values = tuple(float(value) for value in bbox)
                        if all(isfinite(value) for value in values) and values[2] > values[0] and values[3] > values[1]:
                            fraction = polygon_box_area(zone.points, values) / polygon_area(zone.points)
                            current["zone_occupancy_proxy"][zone.id] = min(1.0, current["zone_occupancy_proxy"][zone.id] + fraction)
                    except (ValueError, TypeError, OverflowError):
                        pass
            current["tracks"][identity] = {"category": "unknown", "class_score": None,
                "class_observations": 0, "stationary": None, "image_position": point, "zones": occupied}
        count = len(current["tracks"])
        current["visible_tracks"] = count
        current["occupancy_level"] = ("high_observed_occupancy" if count >= self.configuration.occupancy_high else
                                      "moderate_observed_occupancy" if count >= self.configuration.occupancy_moderate else
                                      "low_observed_occupancy")
        self._current = current

    def update(self, tracks: list[dict], timestamp_s: float | None, timing_valid: bool = True,
               frame_index: int | None = None):
        started = perf_counter()
        valid_time = (not isinstance(timestamp_s, bool) and isinstance(timestamp_s, (int, float))
                      and isfinite(timestamp_s) and timestamp_s >= 0 and timing_valid)
        if not valid_time or (self._watermark_s is not None and timestamp_s <= self._watermark_s):
            self.interrupt("invalid_source_timestamp")
            self._diagnostics["invalid_timestamp_frames"] += 1
            self._untimed_image_observation(tracks)
            return
        timestamp_s = float(timestamp_s)
        config = self.configuration
        if self._last_s is not None and timestamp_s - self._last_s > config.max_gap_s:
            self.interrupt("source_timestamp_gap")
        for identity, state in list(self._identities.items()):
            if timestamp_s - state.last_s > config.max_gap_s:
                self._break_identity(identity, state, "track_observation_gap")
                self._retired_counts[identity] = state.counted
                if len(self._retired_counts) > self.IDENTITY_LIMIT:
                    self._retired_counts.popitem(last=False)
                    self._diagnostics["omitted_identity_count_tombstones"] += 1
                del self._identities[identity]
        if not self._coverage_open:
            self._append(self._coverage, {"start_s": timestamp_s, "end_s": timestamp_s,
                         "configuration_id": config.id, "source_id": self.source_id, "frame_count": 1}, "omitted_coverage")
            self._coverage_open = True
        else:
            elapsed = timestamp_s - self._last_s
            self._covered_s += elapsed
            if config.lines:
                self._covered_counting_s += elapsed
            self._coverage[-1]["end_s"] = timestamp_s
            self._coverage[-1]["frame_count"] += 1
        if (isinstance(frame_index, int) and self._last_index is not None and frame_index > self._last_index + 1):
            self._diagnostics["skipped_source_frames"] += frame_index - self._last_index - 1
        self._previous_frame_s = self._last_s
        self._last_s, self._last_index = timestamp_s, frame_index
        self._watermark_s = timestamp_s
        usable, seen = [], set()
        for track in tracks:
            result = self._usable(track)
            if result is None:
                if not isinstance(track, dict) or (track.get("state") not in ("lost", "removed") and not track.get("missed", 0)):
                    self._diagnostics["invalid_track_observations"] += 1
                continue
            identity, point = result
            if identity in seen:
                self._diagnostics["duplicate_track_observations"] += 1
                continue
            if len(usable) >= self.IDENTITY_LIMIT:
                self._diagnostics["omitted_frame_tracks"] += 1
                continue
            seen.add(identity)
            if identity not in self._identities:
                if len(self._identities) >= self.IDENTITY_LIMIT:
                    old_id = min(self._identities, key=lambda key: self._identities[key].last_s)
                    self._break_identity(old_id, self._identities[old_id], "identity_state_capacity")
                    self._retired_counts[old_id] = self._identities[old_id].counted
                    if len(self._retired_counts) > self.IDENTITY_LIMIT:
                        self._retired_counts.popitem(last=False)
                        self._diagnostics["omitted_identity_count_tombstones"] += 1
                    del self._identities[old_id]
                    self._diagnostics["evicted_identity_states"] += 1
                self._identities[identity] = _Identity(timestamp_s, timestamp_s)
                self._identities[identity].counted = self._retired_counts.pop(identity, set())
            usable.append((identity, self._identities[identity], track, point))
        classification_started = perf_counter()
        for _, state, track, _ in usable:
            self._classify(state, track)
        classification_ms = (perf_counter() - classification_started) * 1000
        crossing_started = perf_counter()
        candidates = []
        for identity, state, track, point in usable:
            candidates.extend(self._crossings(identity, state, track, point, timestamp_s))
        crossing_ms = (perf_counter() - crossing_started) * 1000
        creation_started = perf_counter()
        self._create_events(candidates, seen)
        creation_ms = (perf_counter() - creation_started) * 1000
        zones_started = perf_counter()
        current = self._empty_current()
        current["timestamp_valid"] = True
        metric_speeds = []
        for identity, state, track, point in usable:
            occupied, proxies = self._zones(identity, state, track, point, timestamp_s)
            stationary = self._stationary(state, point, timestamp_s)
            current["tracks"][identity] = {"category": state.category, "class_score": state.class_score,
                "class_observations": state.observations, "stationary": stationary, "image_position": point,
                "zones": occupied}
            current["stationary_tracks"] += int(stationary)
            for zone_id in occupied:
                current["zone_occupancy"][zone_id] += 1
            for zone_id, fraction in proxies.items():
                current["zone_occupancy_proxy"][zone_id] = min(1.0, current["zone_occupancy_proxy"][zone_id] + fraction)
            speed = track.get("estimated_speed_kmh")
            if (track.get("speed_status") == "valid" and isinstance(speed, (int, float))
                    and isfinite(speed) and 0 <= speed <= 500):
                metric_speeds.append(float(speed))
            state.last_s = timestamp_s
        current["visible_tracks"] = len(usable)
        current["slow_tracks"] = int(sum(speed <= config.slow_speed_kmh for speed in metric_speeds)) if metric_speeds else None
        count = current["visible_tracks"]
        current["occupancy_level"] = ("high_observed_occupancy" if count >= config.occupancy_high else
                                      "moderate_observed_occupancy" if count >= config.occupancy_moderate else
                                      "low_observed_occupancy")
        self._current = current
        if self._last_sample_s is None or timestamp_s - self._last_sample_s >= 1:
            self._append(self._samples, {"timestamp_s": timestamp_s, "configuration_id": config.id,
                **{key: value for key, value in current.items() if key != "tracks"}}, "omitted_occupancy_samples")
            self._last_sample_s = timestamp_s
        self._diagnostics["processed_frames"] += 1
        self._profile = {"classification_ms": classification_ms, "crossing_ms": crossing_ms,
                         "event_creation_ms": creation_ms, "zones_ms": (perf_counter() - zones_started) * 1000,
                         "update_ms": (perf_counter() - started) * 1000}

    def overlay_state(self):
        """Current, bounded per-frame state; callers must treat it as read-only."""
        return self._current

    def snapshot(self):
        return deepcopy({"schema_version": 1, "id": self.session_id, "session_id": self.session_id,
                "source_id": self.source_id, "provenance": self.provenance,
                "configuration": self.configuration.model_dump(mode="json"),
                "configurations": list(self._configurations), "events": list(self._events),
                "zone_events": list(self._zone_events), "occupancy_samples": list(self._samples),
                "coverage": [dict(item) for item in self._coverage], "diagnostics": dict(self._diagnostics),
                "summary": {"total_crossings": self._diagnostics["counted_crossings"],
                    "suppressed_crossings": self._diagnostics["suppressed_crossings"],
                    "by_class": {category: self._by_class[category] for category in (*CATEGORIES, "unknown")},
                    "by_direction": dict(self._by_direction), "by_line": dict(self._by_line),
                    "covered_duration_s": self._covered_s,
                    "covered_counting_duration_s": self._covered_counting_s,
                    "zone_summaries": list(self._zone_summary.values()),
                    **{key: value for key, value in self._current.items() if key != "tracks"}},
                "classifications": {identity: {"category": state.category, "score": state.class_score,
                    "observations": state.observations, "weighted_evidence": dict(state.weights)}
                    for identity, state in self._identities.items()},
                "profile": dict(self._profile),
                "limits": {"events": self.EVENT_LIMIT, "zone_events": self.EVENT_LIMIT,
                    "occupancy_samples": self.SAMPLE_LIMIT, "coverage_segments": self.COVERAGE_LIMIT,
                    "identity_states": self.IDENTITY_LIMIT, "identity_count_tombstones": self.IDENTITY_LIMIT,
                    "frame_tracks": self.IDENTITY_LIMIT, "configurations": self.CONFIGURATION_LIMIT,
                    "zone_summaries": 2048, "line_summaries": 2048},
                "limitations": ["Temporary track IDs do not establish unique physical vehicle identity.",
                    "Cross-ID duplicate suppression is a spatial/time heuristic and can miss or merge real crossings.",
                    "Image occupancy sums clipped box areas, caps at one, and can double-count overlap; it is not traffic density.",
                    "Stationary refers to bounded image displacement, not measured real-world speed.",
                    "Zone dwell is observed inside time; interrupted visits are incomplete."]})
