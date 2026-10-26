"""Source-clock integrity and bounded latency evidence, independent of inference."""

from collections import Counter, deque
from math import isfinite, sqrt
from statistics import median


def _distribution(values):
    if not values:
        return {"n": 0, "mean_ms": None, "median_ms": None, "p95_ms": None, "maximum_ms": None}
    ordered = sorted(values)
    position = .95 * (len(ordered) - 1)
    low = int(position)
    p95 = ordered[low] + (ordered[min(low + 1, len(ordered) - 1)] - ordered[low]) * (position - low)
    return {"n": len(values), "mean_ms": sum(values) / len(values), "median_ms": median(values),
            "p95_ms": p95, "maximum_ms": ordered[-1]}


class TimingIntegrity:
    def __init__(self):
        self.source_frames = self.processed_frames = self.skipped_frames = 0
        self.issues = Counter()
        self._source_last = self._processed_last = self._processed_first = None
        self._last_index = 0
        self._time_base = None
        self._interval_count = 0
        self._interval_mean = self._interval_m2 = 0.0
        self._max_source_gap = self._max_processed_gap = 0.0
        self._recent_intervals = deque(maxlen=120)
        self._latencies = deque(maxlen=240)
        self.latest_raw_timestamp_s = None
        self.latest_decode_ms = None
        self.latest_acquired_at = self.latest_decoded_at = None

    def source(self, packet):
        self.source_frames += 1
        raw = packet.raw_timestamp_s if getattr(packet, "raw_timestamp_s", None) is not None else packet.timestamp_s
        issue = getattr(packet, "timestamp_issue", None)
        if issue == "missing_timestamp":
            raw = None
        if issue:
            self.issues[issue] += 1
        if raw is None or not isfinite(raw):
            if issue != "missing_timestamp":
                self.issues["missing_timestamp"] += 1
        elif self._source_last is not None:
            interval = raw - self._source_last
            if interval == 0 and issue != "duplicate_timestamp":
                self.issues["duplicate_timestamp"] += 1
            elif interval < 0 and issue != "backward_timestamp":
                self.issues["backward_timestamp"] += 1
            elif interval > 0:
                if len(self._recent_intervals) >= 5 and interval > 5 * median(self._recent_intervals):
                    self.issues["large_source_gap"] += 1
                self._recent_intervals.append(interval)
                self._max_source_gap = max(self._max_source_gap, interval)
                self._interval_count += 1
                delta = interval - self._interval_mean
                self._interval_mean += delta / self._interval_count
                self._interval_m2 += delta * (interval - self._interval_mean)
        if raw is not None and isfinite(raw):
            self._source_last = raw
        time_base = getattr(packet, "time_base", None)
        if time_base and self._time_base and time_base != self._time_base:
            self.issues["timebase_changed"] += 1
        if time_base:
            self._time_base = time_base
        self.latest_raw_timestamp_s = raw if raw is not None and isfinite(raw) else None
        self.latest_decode_ms = getattr(packet, "decode_ms", None)
        self.latest_acquired_at = packet.acquired_at
        self.latest_decoded_at = getattr(packet, "decoded_at", None)
        if packet.timing_warning:
            self.issues["flagged_frames"] += 1

    def processed(self, packet, finished_at):
        self.processed_frames += 1
        self.skipped_frames += max(0, packet.index - self._last_index - 1)
        self._last_index = packet.index
        timestamp = packet.timestamp_s
        if timestamp is not None and isfinite(timestamp):
            if self._processed_first is None:
                self._processed_first = timestamp
            if self._processed_last is not None and timestamp > self._processed_last:
                self._max_processed_gap = max(self._max_processed_gap, timestamp - self._processed_last)
            self._processed_last = timestamp
        latency = (finished_at - packet.acquired_at) * 1000
        if isfinite(latency) and latency >= 0:
            self._latencies.append(latency)

    def snapshot(self):
        duration = (self._processed_last - self._processed_first
                    if self._processed_first is not None and self._processed_last is not None else 0)
        deviation = sqrt(self._interval_m2 / self._interval_count) if self._interval_count else None
        warnings = []
        if any(self.issues[key] for key in ("missing_timestamp", "duplicate_timestamp", "backward_timestamp", "timebase_changed", "flagged_frames")):
            warnings.append("Source timing contains flagged observations; review raw timestamps and timebase before independent validation.")
        if self.issues["large_source_gap"]:
            warnings.append("Some source intervals exceeded five times the recent median; variable-rate recording or acquisition gaps need review.")
        return {"source_frame_count": self.source_frames, "processed_frame_count": self.processed_frames,
                "skipped_source_frames": self.skipped_frames, "latest_raw_timestamp_s": self.latest_raw_timestamp_s,
                "effective_observation_rate_hz": (self.processed_frames - 1) / duration if duration > 0 else None,
                "source_interval_mean_s": self._interval_mean if self._interval_count else None,
                "source_interval_std_s": deviation,
                "source_interval_cv": deviation / self._interval_mean if deviation is not None and self._interval_mean > 0 else None,
                "maximum_source_gap_s": self._max_source_gap, "maximum_observation_gap_s": self._max_processed_gap,
                "time_base": self._time_base, "issues": dict(self.issues), "warnings": warnings,
                "processing_latency": _distribution(list(self._latencies)), "latency_window_size": 240,
                "latest_decode_ms": self.latest_decode_ms, "latest_acquisition_monotonic_s": self.latest_acquired_at,
                "latest_decode_completed_monotonic_s": self.latest_decoded_at,
                "clock_note": "Source PTS/acquisition, decode completion, inference and browser display are different clocks. No independently verified wall-clock guarantee is implied."}
