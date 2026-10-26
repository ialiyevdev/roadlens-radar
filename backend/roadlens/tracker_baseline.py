"""Small motion-assisted IoU baseline, with session-scoped IDs and bounded history."""

from collections import deque
from dataclasses import dataclass, field
from math import hypot, isfinite

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
    last_seen: float
    hits: int = 1
    missed: int = 0
    confirmed: bool = False
    velocity: tuple[float, float] = (0.0, 0.0)
    history: deque = field(default_factory=lambda: deque(maxlen=40))

    def predict(self, timestamp: float) -> tuple:
        dx, dy = (value * (timestamp - self.last_seen) for value in self.velocity)
        x1, y1, x2, y2 = self.detection.bbox
        return x1 + dx, y1 + dy, x2 + dx, y2 + dy


class IoUTracker:
    def __init__(self, max_gap_s: float = 1.0, min_hits: int = 3):
        self.max_gap_s = max_gap_s
        self.min_hits = min_hits
        self._tracks: dict[int, _Track] = {}
        self._next_id = 1
        self._last_timestamp: float | None = None
        self.counts = {"car": 0, "truck": 0, "bus": 0, "motorcycle": 0}

    @property
    def total_tracks(self) -> int:
        return sum(self.counts.values())

    def update(self, detections: list[Detection], timestamp_s: float) -> list[dict]:
        if not isfinite(timestamp_s) or (self._last_timestamp is not None and timestamp_s <= self._last_timestamp):
            raise ValueError("Tracking requires finite, strictly increasing source timestamps.")
        self._last_timestamp = timestamp_s
        self._tracks = {
            key: track for key, track in self._tracks.items()
            if timestamp_s - track.last_seen <= self.max_gap_s
        }
        candidates = []
        for track_id, track in self._tracks.items():
            predicted = track.predict(timestamp_s)
            center = contact_point(predicted)
            diagonal = max(1.0, hypot(predicted[2] - predicted[0], predicted[3] - predicted[1]))
            for index, detection in enumerate(detections):
                if detection.category != track.detection.category:
                    continue
                other = contact_point(detection.bbox)
                distance = hypot(center[0] - other[0], center[1] - other[1]) / diagonal
                iou = intersection_over_union(predicted, detection.bbox)
                # The distance gate allows a short missed detection; it is not an identity guarantee.
                if iou >= 0.15 or distance <= 0.65:
                    candidates.append((iou + 0.25 * max(0, 1 - distance), track_id, index))
        matched_tracks, matched_detections = set(), set()
        for _, track_id, index in sorted(candidates, reverse=True):
            if track_id in matched_tracks or index in matched_detections:
                continue
            track, detection = self._tracks[track_id], detections[index]
            old, new = contact_point(track.detection.bbox), contact_point(detection.bbox)
            elapsed = timestamp_s - track.last_seen
            track.velocity = ((new[0] - old[0]) / elapsed, (new[1] - old[1]) / elapsed)
            track.detection, track.last_seen = detection, timestamp_s
            track.hits += 1
            track.missed = 0
            track.history.append(new)
            matched_tracks.add(track_id)
            matched_detections.add(index)
        for track_id, track in self._tracks.items():
            if track_id not in matched_tracks:
                track.missed += 1
        for index, detection in enumerate(detections):
            if index in matched_detections:
                continue
            track = _Track(self._next_id, detection, timestamp_s)
            track.history.append(contact_point(detection.bbox))
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
                "history": list(track.history),
            })
        return result
