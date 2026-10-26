"""Bounded ordinal frame navigation for manual annotation, using actual decoder PTS.

Indexing decodes once without retaining image arrays. Forward requests reuse a
decoder and eight recent raw frames; older backward requests decode from the
start so variable-rate videos and keyframe seeking cannot change frame identity.
"""

import math
import threading
from collections import OrderedDict
from pathlib import Path
from time import perf_counter

import av


def frame_metadata(frame, index: int, previous_timestamp=None, previous_time_base=None) -> dict:
    pts = frame.pts
    base = frame.time_base
    timestamp = float(pts * base) if pts is not None and base is not None else None
    warnings = []
    if timestamp is None or not math.isfinite(timestamp):
        timestamp = None
        warnings.append("missing_or_nonfinite_presentation_timestamp")
    elif timestamp < 0:
        warnings.append("negative_presentation_timestamp")
    elif previous_timestamp is not None and timestamp <= previous_timestamp:
        warnings.append("duplicate_presentation_timestamp" if timestamp == previous_timestamp
                        else "backward_presentation_timestamp")
    time_base = str(base) if base is not None else None
    if previous_time_base is not None and time_base != previous_time_base:
        warnings.append("source_timebase_changed")
    return {"index": index, "timestamp_s": timestamp, "pts": pts, "time_base": time_base,
            "width": frame.width, "height": frame.height,
            "timing_warning": "; ".join(warnings) if warnings else None}


class VideoNavigator:
    MAX_CACHE_BYTES = 64 * 1024 * 1024

    def __init__(self, path: Path, max_frames: int = 100000):
        if isinstance(max_frames, bool) or not isinstance(max_frames, int) or not 1 <= max_frames <= 100000:
            raise ValueError("Annotation frame limit must be between 1 and 100000.")
        self.path = Path(path)
        self._lock = threading.RLock()
        self._metadata = []
        self._cache = OrderedDict()
        self._cache_bytes = 0
        self._container = None
        self._reader = None
        self._cursor = 0
        self._closed = False
        self.last_navigation_ms = None
        self.cache_hits = 0
        started = perf_counter()
        try:
            stat = self.path.stat()
            self._file_identity = (stat.st_size, stat.st_mtime_ns)
            with av.open(str(self.path)) as container:
                if not container.streams.video:
                    raise ValueError("The source has no video stream.")
                stream = container.streams.video[0]
                rate = float(stream.average_rate) if stream.average_rate else None
                fps = rate if rate is not None and math.isfinite(rate) and rate > 0 else None
                duration = float(stream.duration * stream.time_base) if stream.duration is not None and stream.time_base else None
                duration = duration if duration is not None and math.isfinite(duration) and duration >= 0 else None
                previous_timestamp, previous_base = None, None
                truncated = False
                for ordinal, frame in enumerate(container.decode(stream), start=1):
                    if ordinal > max_frames:
                        truncated = True
                        break
                    meta = frame_metadata(frame, ordinal, previous_timestamp, previous_base)
                    self._metadata.append(meta)
                    if meta["timestamp_s"] is not None:
                        previous_timestamp = meta["timestamp_s"]
                    previous_base = meta["time_base"]
                if not self._metadata:
                    raise ValueError("The source contains no decodable video frames.")
        except (av.FFmpegError, OSError) as error:
            raise ValueError("The annotation video could not be decoded.") from error
        timestamps = [m["timestamp_s"] for m in self._metadata if m["timestamp_s"] is not None]
        warnings = sorted({m["timing_warning"] for m in self._metadata if m["timing_warning"]})
        if truncated:
            warnings.append(f"Index limited to the first {max_frames} source frames; later frames are unavailable for annotation.")
        self._summary = {"frame_count": len(self._metadata), "reported_fps": fps, "duration_s": duration,
                         "observed_span_s": timestamps[-1] - timestamps[0] if len(timestamps) >= 2 else None,
                         "time_bases": sorted({m["time_base"] for m in self._metadata if m["time_base"]}),
                         "width": self._metadata[0]["width"], "height": self._metadata[0]["height"],
                         "timestamp_warning_frames": sum(m["timing_warning"] is not None for m in self._metadata),
                         "truncated": truncated, "warnings": warnings,
                         "indexing_ms": (perf_counter() - started) * 1000,
                         "timestamp_basis": "decoded presentation timestamps; no verified wall-clock claim"}

    def summary(self) -> dict:
        with self._lock:
            return {**self._summary, "time_bases": list(self._summary["time_bases"]),
                    "warnings": list(self._summary["warnings"]), "cache_hits": self.cache_hits,
                    "last_navigation_ms": self.last_navigation_ms, "cached_pixel_bytes": self._cache_bytes,
                    "maximum_cached_pixel_bytes": self.MAX_CACHE_BYTES}

    def metadata(self, index: int) -> dict:
        with self._lock:
            self._validate_index(index)
            return dict(self._metadata[index - 1])

    def _validate_index(self, index):
        if isinstance(index, bool) or not isinstance(index, int) or not 1 <= index <= len(self._metadata):
            raise ValueError("Frame index is outside the available 1-based source-frame range.")

    def _reset_reader(self):
        if self._container is not None:
            self._container.close()
        self._container = av.open(str(self.path))
        self._reader = iter(self._container.decode(self._container.streams.video[0]))
        self._cursor = 0

    def image(self, index: int):
        started = perf_counter()
        with self._lock:
            self._validate_index(index)
            if self._closed:
                raise ValueError("The annotation video navigator is closed.")
            try:
                stat = self.path.stat()
                if (stat.st_size, stat.st_mtime_ns) != self._file_identity:
                    raise ValueError("The source video changed after indexing; reopen it before annotating.")
                if index in self._cache:
                    self.cache_hits += 1
                    image = self._cache.pop(index)
                    self._cache[index] = image
                    self.last_navigation_ms = (perf_counter() - started) * 1000
                    return image.copy()
                if self._reader is None or index <= self._cursor:
                    self._reset_reader()
                target_image = None
                while self._cursor < index:
                    frame = next(self._reader)
                    self._cursor += 1
                    if self._cursor >= max(1, index - 7):
                        decoded = frame.to_ndarray(format="bgr24")
                        if self._cursor == index:
                            target_image = decoded
                        if decoded.nbytes <= self.MAX_CACHE_BYTES:
                            previous = self._cache.pop(self._cursor, None)
                            if previous is not None:
                                self._cache_bytes -= previous.nbytes
                            self._cache[self._cursor] = decoded
                            self._cache_bytes += decoded.nbytes
                            while len(self._cache) > 8 or self._cache_bytes > self.MAX_CACHE_BYTES:
                                self._cache_bytes -= self._cache.popitem(last=False)[1].nbytes
                self.last_navigation_ms = (perf_counter() - started) * 1000
                return self._cache[index].copy() if index in self._cache else target_image
            except (av.FFmpegError, OSError, StopIteration) as error:
                raise ValueError("The requested annotation frame could not be decoded.") from error

    def close(self):
        with self._lock:
            if self._container is not None:
                self._container.close()
                self._container = None
            self._reader = None
            self._cache.clear()
            self._cache_bytes = 0
            self._closed = True
