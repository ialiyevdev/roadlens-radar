"""Sources assign capture times before frames enter expensive processing."""

import math
import sys
import time
from dataclasses import dataclass
from pathlib import Path

import av
import cv2
import numpy as np

from .schemas import CameraInfo, StartRequest


class SourceError(RuntimeError):
    pass


def positive_number(value: float) -> float | None:
    return float(value) if math.isfinite(value) and value > 0 else None


@dataclass(frozen=True)
class CapturedFrame:
    image: np.ndarray
    index: int
    timestamp_s: float
    acquired_at: float
    timing_source: str
    timing_warning: str | None = None
    raw_timestamp_s: float | None = None
    time_base: str | None = None
    pts: int | None = None
    timestamp_issue: str | None = None
    decoded_at: float | None = None
    decode_ms: float | None = None


def open_camera(index: int, width: int, height: int):
    backends = [cv2.CAP_DSHOW, cv2.CAP_MSMF] if sys.platform == "win32" else [cv2.CAP_ANY]
    for backend in backends:
        capture = cv2.VideoCapture(index, backend)
        if capture.isOpened():
            capture.set(cv2.CAP_PROP_FRAME_WIDTH, width)
            capture.set(cv2.CAP_PROP_FRAME_HEIGHT, height)
            capture.set(cv2.CAP_PROP_BUFFERSIZE, 1)
            return capture
        capture.release()
    raise SourceError(f"Camera {index} could not be opened. Check its connection and close other camera apps.")


class CameraSource:
    live = True

    def __init__(self, index: int, width: int, height: int):
        self.capture = open_camera(index, width, height)
        self.width = int(self.capture.get(cv2.CAP_PROP_FRAME_WIDTH))
        self.height = int(self.capture.get(cv2.CAP_PROP_FRAME_HEIGHT))
        self.reported_fps = positive_number(self.capture.get(cv2.CAP_PROP_FPS))
        self.label = f"Camera {index}"
        self._epoch = time.monotonic()
        self._index = 0

    def read(self) -> CapturedFrame:
        success, image = self.capture.read()
        acquired = time.monotonic()
        if not success or image is None:
            raise SourceError("The camera stopped delivering frames. Check its connection and restart the session.")
        self._index += 1
        return CapturedFrame(image, self._index, acquired - self._epoch, acquired, "monotonic acquisition",
                             raw_timestamp_s=acquired - self._epoch)

    def close(self):
        self.capture.release()


class VideoSource:
    live = False

    def __init__(self, path: Path, label: str | None = None):
        self.container = None
        try:
            self.container = av.open(str(path))
            streams = self.container.streams.video
            if not streams:
                raise SourceError("The selected file has no video stream.")
            self.stream = streams[0]
            self.width = self.stream.codec_context.width
            self.height = self.stream.codec_context.height
            rate = self.stream.average_rate
            self.reported_fps = positive_number(float(rate)) if rate else None
            self._frames = iter(self.container.decode(self.stream))
        except (av.FFmpegError, OSError, ValueError, SourceError) as error:
            self.close()
            raise SourceError("The video could not be decoded. Try a supported MP4, AVI, MOV, MKV, or WebM file.") from error
        self.label = label or path.name
        self._index = 0
        self._last_timestamp = None
        self._fallback = False
        self._last_raw_timestamp = None
        self._last_time_base = None
        self._timebase_changed = False

    def read(self) -> CapturedFrame | None:
        decoding_started = time.perf_counter()
        try:
            frame = next(self._frames)
            image = frame.to_ndarray(format="bgr24")
        except StopIteration:
            return None
        except (av.FFmpegError, ValueError) as error:
            raise SourceError("Video decoding failed before the end of the file.") from error
        acquired = time.monotonic()
        self._index += 1
        pts = float(frame.pts * frame.time_base) if frame.pts is not None and frame.time_base is not None else None
        time_base = str(frame.time_base) if frame.time_base is not None else None
        issue = None
        if pts is None or not math.isfinite(pts):
            issue = "missing_timestamp"
        elif self._last_raw_timestamp is not None and pts <= self._last_raw_timestamp:
            issue = "duplicate_timestamp" if pts == self._last_raw_timestamp else "backward_timestamp"
        valid = issue is None
        if self._last_time_base and time_base and time_base != self._last_time_base:
            self._timebase_changed = True
        self._last_time_base = time_base
        if pts is not None and math.isfinite(pts):
            self._last_raw_timestamp = pts
        if not valid:
            # Once a fallback occurs, keep a single consistent diagnostic timeline.
            self._fallback = True
        if self._fallback:
            interval = 1 / self.reported_fps if self.reported_fps else 1 / 30
            timestamp = 0.0 if self._last_timestamp is None else self._last_timestamp + interval
            timing_source = "nominal frame interval fallback"
            warning = "Missing or non-increasing video presentation timestamps. Nominal timing is diagnostic only."
            if self.reported_fps is None:
                warning += " No frame rate was declared; a 30 Hz diagnostic interval is used."
        else:
            timestamp = pts
            timing_source = "video presentation timestamp"
            warning = None
        if self._timebase_changed:
            warning = (warning + " " if warning else "") + "Video timebase changed within the source; timing needs independent review."
        self._last_timestamp = timestamp
        return CapturedFrame(image, self._index, timestamp, acquired, timing_source, warning,
                             raw_timestamp_s=pts if pts is not None and math.isfinite(pts) else None,
                             time_base=time_base, pts=frame.pts, timestamp_issue=issue,
                             decoded_at=acquired, decode_ms=(time.perf_counter() - decoding_started) * 1000)

    def close(self):
        if self.container is not None:
            self.container.close()
            self.container = None


def open_source(request: StartRequest, video_path: Path | None = None, label: str | None = None):
    if request.source_type == "camera":
        return CameraSource(request.camera_index, request.width, request.height)
    if video_path is None:
        raise SourceError("Upload and select a video before starting.")
    return VideoSource(video_path, label)


def discover_cameras(max_index: int = 5) -> list[CameraInfo]:
    cameras = []
    for index in range(max_index):
        capture = None
        try:
            capture = open_camera(index, 1280, 720)
            success, image = capture.read()
            if success and image is not None:
                cameras.append(CameraInfo(index=index, name=f"Camera {index}", width=image.shape[1], height=image.shape[0], fps=positive_number(capture.get(cv2.CAP_PROP_FPS))))
        except SourceError:
            continue
        finally:
            if capture is not None:
                capture.release()
    return cameras
