"""CPU box tracking with global gated assignment and observable uncertainty.

IDs are local hypotheses, not vehicle identities. There is no appearance model
or re-identification after expiry. The original Phase 2 implementation is frozen
in tracker_baseline.py for the independent synthetic comparison.
"""

from collections import deque
from dataclasses import dataclass, field
from math import hypot, isfinite

from .assignment import maximum_score_matching
from .detector import Detection


def intersection_over_union(a: tuple, b: tuple) -> float:
    overlap = max(0, min(a[2], b[2]) - max(a[0], b[0])) * max(0, min(a[3], b[3]) - max(a[1], b[1]))
    area_a = max(0, a[2] - a[0]) * max(0, a[3] - a[1])
    area_b = max(0, b[2] - b[0]) * max(0, b[3] - b[1])
    union = area_a + area_b - overlap
    return overlap / union if union else 0.0


def contact_point(bbox: tuple) -> tuple[float, float]:
    return ((bbox[0] + bbox[2]) / 2, bbox[3])


@dataclass
class _Track:
    id: int
    detection: Detection
    first_seen: float
    last_seen: float
    hits: int = 1
    missed: int = 0
    confirmed: bool = False
    velocity: tuple[float, float] = (0.0, 0.0)
    history: deque = field(default_factory=lambda: deque(maxlen=40))
    observation_gap_s: float = 0.0
    association_ambiguous: bool = False
    tracking_diagnostics: list[str] = field(default_factory=list)

    def predict(self, timestamp: float) -> tuple:
        dx, dy = (value * (timestamp - self.last_seen) for value in self.velocity)
        x1, y1, x2, y2 = self.detection.bbox
        return x1 + dx, y1 + dy, x2 + dx, y2 + dy


class IoUTracker:
    """Global motion/IoU association with source-time lifecycle and bounded state.

    All feasible edges are assigned together, maximizing match count and then
    score. Close competing choices flag ambiguity; a chosen ID does not resolve
    physical identity. Velocity smoothing affects association only: returned
    boxes and history retain the original observations used for measurement.
    """

    def __init__(self, max_gap_s: float = 1.0, min_hits: int = 3,
                 velocity_weight: float = .65, ambiguity_margin: float = .12):
        if not isfinite(max_gap_s) or max_gap_s <= 0:
            raise ValueError("Track expiry must be a positive finite source-time gap.")
        if isinstance(min_hits, bool) or not isinstance(min_hits, int) or min_hits < 1:
            raise ValueError("Track confirmation requires a positive integer hit count.")
        if not isfinite(velocity_weight) or not 0 < velocity_weight <= 1:
            raise ValueError("Velocity weight must lie in (0, 1].")
        if not isfinite(ambiguity_margin) or not 0 <= ambiguity_margin <= 1:
            raise ValueError("Ambiguity margin must lie in [0, 1].")
        self.max_gap_s, self.min_hits = max_gap_s, min_hits
        self.velocity_weight, self.ambiguity_margin = velocity_weight, ambiguity_margin
        self._tracks: dict[int, _Track] = {}
        self._recently_removed: deque = deque(maxlen=128)
        self._next_id = 1
        self._last_timestamp: float | None = None
        self._removed_count = 0
        self._potential_switches = 0
        self._fragmentation_suspicions = 0
        self._invalid_detections = 0
        self.counts = {"car": 0, "truck": 0, "bus": 0, "motorcycle": 0}

    @property
    def total_tracks(self) -> int:
        return sum(self.counts.values())

    def reset_associations(self):
        """Coordinate-system changes retire hypotheses without reusing IDs."""
        self._removed_count += len(self._tracks)
        self._tracks.clear()
        self._recently_removed.clear()

    @property
    def diagnostics(self) -> dict:
        return {
            "active_tracks": sum(not track.missed for track in self._tracks.values()),
            "confirmed_tracks": sum(track.confirmed and not track.missed for track in self._tracks.values()),
            "lost_tracks": sum(bool(track.missed) for track in self._tracks.values()),
            "removed_tracks": self._removed_count,
            "potential_id_switches": self._potential_switches,
            "fragmentation_suspicions": self._fragmentation_suspicions,
            "invalid_detections": self._invalid_detections,
        }

    def _feasible_score(self, track: _Track, detection: Detection, timestamp_s: float) -> float | None:
        if detection.category != track.detection.category:
            return None
        predicted = track.predict(timestamp_s)
        center, other = contact_point(predicted), contact_point(detection.bbox)
        diagonal = max(1.0, hypot(predicted[2] - predicted[0], predicted[3] - predicted[1]))
        distance = hypot(center[0] - other[0], center[1] - other[1]) / diagonal
        iou = intersection_over_union(predicted, detection.bbox)
        if iou < .15 and distance > .65:
            return None
        width, height = predicted[2] - predicted[0], predicted[3] - predicted[1]
        other_width, other_height = detection.bbox[2] - detection.bbox[0], detection.bbox[3] - detection.bbox[1]
        shape = min(width, other_width) / max(width, other_width) * min(height, other_height) / max(height, other_height)
        return iou + .25 * max(0, 1 - distance) + .1 * shape

    def update(self, detections: list[Detection], timestamp_s: float) -> list[dict]:
        if not isfinite(timestamp_s) or (self._last_timestamp is not None and timestamp_s <= self._last_timestamp):
            raise ValueError("Tracking requires finite, strictly increasing source timestamps.")
        self._last_timestamp = timestamp_s
        usable = []
        for detection in detections:
            bbox = detection.bbox
            if (len(bbox) != 4 or not all(isfinite(value) for value in bbox)
                    or bbox[2] <= bbox[0] or bbox[3] <= bbox[1]
                    or not isfinite(detection.confidence) or not 0 <= detection.confidence <= 1
                    or detection.category not in self.counts):
                self._invalid_detections += 1
            else:
                usable.append(detection)
        detections = usable
        for identity in list(self._tracks):
            track = self._tracks[identity]
            if timestamp_s - track.last_seen > self.max_gap_s:
                self._recently_removed.append((timestamp_s, track))
                self._removed_count += 1
                del self._tracks[identity]
        while self._recently_removed and timestamp_s - self._recently_removed[0][0] > self.max_gap_s:
            self._recently_removed.popleft()
        tracks = list(self._tracks.values())
        scores = {}
        for row, track in enumerate(tracks):
            for column, detection in enumerate(detections):
                score = self._feasible_score(track, detection, timestamp_s)
                if score is not None:
                    scores[row, column] = score
        assignments = maximum_score_matching(len(tracks), len(detections), scores)
        matched_tracks, matched_detections = set(), set()
        for row, column in assignments:
            track, detection = tracks[row], detections[column]
            score = scores[row, column]
            competitors = [other_score for (other_row, other_column), other_score in scores.items()
                           if (other_row == row and other_column != column)
                           or (other_column == column and other_row != row)]
            ambiguous = bool(competitors and max(competitors) >= score - self.ambiguity_margin)
            diagnostics = []
            if ambiguous:
                diagnostics.append("association_ambiguous")
                if not track.association_ambiguous:
                    self._potential_switches += 1
            if track.missed:
                diagnostics.append("reacquired_after_observation_gap")
            old_box, new_box = track.detection.bbox, detection.bbox
            old_area = (old_box[2] - old_box[0]) * (old_box[3] - old_box[1])
            new_area = (new_box[2] - new_box[0]) * (new_box[3] - new_box[1])
            if new_area < .6 * old_area:
                diagnostics.append("box_area_shrink_possible_partial_occlusion")
            elif new_area > old_area / .6:
                diagnostics.append("large_box_area_change")
            old, new = contact_point(old_box), contact_point(new_box)
            elapsed = timestamp_s - track.last_seen
            observed_velocity = ((new[0] - old[0]) / elapsed, (new[1] - old[1]) / elapsed)
            weight = 1.0 if track.hits == 1 else self.velocity_weight
            track.velocity = tuple(weight * value + (1 - weight) * previous
                                   for value, previous in zip(observed_velocity, track.velocity))
            track.observation_gap_s = elapsed
            track.detection, track.last_seen = detection, timestamp_s
            track.hits += 1
            track.missed = 0
            track.association_ambiguous = ambiguous
            track.tracking_diagnostics = diagnostics
            track.history.append(new)
            matched_tracks.add(track.id)
            matched_detections.add(column)
        for track in tracks:
            if track.id not in matched_tracks:
                track.missed += 1
                track.observation_gap_s = timestamp_s - track.last_seen
                track.tracking_diagnostics = ["missing_detection"]
                if track.association_ambiguous:
                    track.tracking_diagnostics.append("association_ambiguous")
        for index, detection in enumerate(detections):
            if index in matched_detections:
                continue
            track = _Track(self._next_id, detection, timestamp_s, timestamp_s)
            track.history.append(contact_point(detection.bbox))
            # A nearby new ID after expiry is a suspicion, never a re-ID or a
            # verified fragment. Recent removal storage is TTL- and size-bounded.
            if any(self._feasible_score(old, detection, timestamp_s) is not None
                   for _, old in self._recently_removed):
                track.tracking_diagnostics.append("possible_fragment_after_expiry")
                self._fragmentation_suspicions += 1
            self._tracks[track.id] = track
            self._next_id += 1
        result = []
        for track in self._tracks.values():
            if track.hits >= self.min_hits and not track.confirmed:
                track.confirmed = True
                self.counts[track.detection.category] += 1
            state = "lost" if track.missed else "confirmed" if track.confirmed else "tentative"
            result.append({
                "id": track.id, "category": track.detection.category,
                "bbox": track.detection.bbox, "confidence": track.detection.confidence,
                "state": state, "hits": track.hits, "missed": track.missed,
                "history": list(track.history), "age_s": timestamp_s - track.first_seen,
                "observation_gap_s": track.observation_gap_s,
                "association_ambiguous": track.association_ambiguous,
                "tracking_diagnostics": list(track.tracking_diagnostics),
            })
        return result
