"""Small, offline annotation workspace with bounded frame navigation and proposals."""

import asyncio
import hashlib
import math
import threading
from bisect import bisect_left
from collections import OrderedDict
from pathlib import Path
from time import perf_counter
from urllib.parse import quote

import cv2
from fastapi import APIRouter, File, HTTPException, Query, UploadFile
from fastapi.responses import Response

from .annotation_metrics import annotation_metrics
from .annotation_models import AnnotatedFrame, AnnotationDocument, ProposalMetadata, ProposalRequest, TrackPrediction
from .annotation_store import AnnotationRevisionConflict, AnnotationStore, annotations_csv, parse_annotations
from .camera_calibration import FrameUndistorter
from .camera_models import CameraIntrinsicProfile
from .detector import RoadLensDetector
from .offline_video import VideoNavigator
from .tracker import IoUTracker
from .tracker_baseline import IoUTracker as BaselineTracker


class AnnotationService:
    def __init__(self, manager, store: AnnotationStore | None = None):
        self.manager = manager
        self.store = store or AnnotationStore(manager.field_store.directory.parent / "annotations")
        self._lock = threading.RLock()
        self._videos = OrderedDict()
        self._timestamps = {}

    def close(self):
        with self._lock:
            for _, navigator, _ in self._videos.values():
                navigator.close()
            self._videos.clear()
            self._timestamps.clear()

    def delete(self, identifier):
        with self._lock:
            cached = self._videos.pop(identifier, None)
            if cached:
                cached[1].close()
            self._timestamps.pop(identifier, None)
            self.store.delete(identifier)

    def get(self, identifier):
        return self.store.get(self.manager.field_store.get(identifier))

    def _source_path(self, field):
        if not field.source.relative_path:
            raise ValueError("This field session has no local recorded video. Select an uploaded video source first.")
        base = Path(self.manager.upload_dir).resolve()
        path = (base / field.source.relative_path).resolve()
        if not path.is_relative_to(base) or not path.is_file():
            raise ValueError("The referenced annotation video is unavailable inside the local upload directory.")
        return path

    def _video(self, field):
        # Caller holds the service lock, including complete proposal runs.
        path = self._source_path(field)
        stat = path.stat()
        expected_hash = field.source.content_sha256
        if expected_hash is None and field.source.source_id.startswith("video:"):
            candidate = field.source.source_id[6:]
            if len(candidate) == 64 and all(c in "0123456789abcdefABCDEF" for c in candidate):
                expected_hash = candidate.lower()
        profile = None
        geometry = field.camera.geometry
        if geometry.coordinate_space == "undistorted":
            if field.camera.intrinsic_profile_id and field.camera.intrinsic_profile_id != geometry.intrinsic_profile_id:
                raise ValueError("Field-session camera profile and pixel coordinate profile differ.")
            archived = field.calibration_metadata.get("intrinsic")
            profile = (CameraIntrinsicProfile.model_validate(archived) if archived is not None
                       else self.manager.camera_profiles.get(geometry.intrinsic_profile_id))
            if profile.id != geometry.intrinsic_profile_id or profile.geometry != geometry:
                raise ValueError("The archived or saved intrinsic profile does not match the annotation pixel space.")
        profile_fingerprint = hashlib.sha256(profile.model_dump_json().encode()).hexdigest() if profile else None
        fingerprint = (str(path), stat.st_size, stat.st_mtime_ns, expected_hash,
                       geometry.model_dump_json(), profile_fingerprint)
        cached = self._videos.get(field.id)
        if cached and cached[0] == fingerprint:
            self._videos.move_to_end(field.id)
            return cached[1:]
        if cached:
            if cached[0][:3] != fingerprint[:3] and expected_hash is None:
                raise ValueError("The annotation source file changed. Restore it or create a new fingerprinted field session.")
            cached[1].close()
            del self._videos[field.id]
            self._timestamps.pop(field.id, None)
        if expected_hash:
            digest = hashlib.sha256()
            with path.open("rb") as stream:
                while chunk := stream.read(1024*1024):
                    digest.update(chunk)
            if digest.hexdigest() != expected_hash:
                raise ValueError("Video fingerprint differs from this field session. Restore the original source before annotating.")
        corrector = None
        if profile is not None:
            corrector = FrameUndistorter(profile)
        navigator = VideoNavigator(path)
        first = navigator.metadata(1)
        if first["width"] != geometry.width or first["height"] != geometry.height:
            navigator.close()
            raise ValueError("Video resolution differs from the field-session annotation geometry.")
        self._videos[field.id] = (fingerprint, navigator, corrector)
        while len(self._videos) > 3:
            expired_id, (_, expired, _) = self._videos.popitem(last=False)
            expired.close()
            self._timestamps.pop(expired_id, None)
        return navigator, corrector

    def _metadata(self, field, navigator, index):
        metadata = navigator.metadata(index)
        geometry = field.camera.geometry
        if (metadata["width"], metadata["height"]) != (geometry.width, geometry.height):
            raise ValueError("Source image resolution changes within this video; use a stable geometry segment.")
        return metadata

    def _image(self, field, navigator, corrector, index):
        self._metadata(field, navigator, index)
        image = navigator.image(index)
        return corrector.apply(image) if corrector else image

    def frame(self, identifier, index):
        field = self.manager.field_store.get(identifier)
        with self._lock:
            navigator, _ = self._video(field)
            metadata = self._metadata(field, navigator, index)
            return {**metadata, "total_frames": navigator.summary()["frame_count"],
                    "image_url": f"/api/field-sessions/{quote(field.id, safe='')}/frames/image?index={index}",
                    "coordinate_space": field.camera.geometry.coordinate_space,
                    "intrinsic_profile_id": field.camera.geometry.intrinsic_profile_id}

    def image(self, identifier, index):
        field = self.manager.field_store.get(identifier)
        with self._lock:
            navigator, corrector = self._video(field)
            image = self._image(field, navigator, corrector, index)
            success, jpeg = cv2.imencode(".jpg", image, [cv2.IMWRITE_JPEG_QUALITY, 85])
            if not success:
                raise ValueError("The annotation frame could not be encoded.")
            return jpeg.tobytes()

    def frame_at(self, identifier, timestamp_s):
        if not math.isfinite(timestamp_s):
            raise ValueError("Timestamp navigation requires a finite source timestamp.")
        field = self.manager.field_store.get(identifier)
        with self._lock:
            navigator, _ = self._video(field)
            if identifier not in self._timestamps:
                times = []
                for index in range(1, navigator.summary()["frame_count"]+1):
                    timestamp = navigator.metadata(index)["timestamp_s"]
                    if timestamp is not None and math.isfinite(timestamp):
                        times.append((timestamp, index))
                first_index = {}
                for timestamp, index in sorted(times):
                    first_index.setdefault(timestamp, index)
                self._timestamps[identifier] = sorted(first_index.items())
            times = self._timestamps[identifier]
            if not times:
                raise ValueError("This video has no finite presentation timestamps for navigation.")
            position = bisect_left(times, (timestamp_s, 0))
            candidates = times[max(0, position-1):min(len(times), position+1)]
            selected_time, selected_index = min(candidates, key=lambda value: (abs(value[0]-timestamp_s), value[1]))
            return {**self.frame(identifier, selected_index), "requested_timestamp_s": timestamp_s,
                    "timestamp_distance_s": abs(selected_time-timestamp_s)}

    def save(self, identifier, document):
        field = self.manager.field_store.get(identifier)
        self.store._compatible(field, document)
        # Portable imports can retain labels without the source file. When it is
        # present, verify ordinal timestamps against the actual recording.
        path = (Path(self.manager.upload_dir) / field.source.relative_path) if field.source.relative_path else None
        if path is not None and path.is_file():
            with self._lock:
                navigator, _ = self._video(field)
                for frame in document.frames:
                    metadata = self._metadata(field, navigator, frame.index)
                    expected = metadata["timestamp_s"]
                    if (expected is None) != (frame.timestamp_s is None) or (expected is not None and not math.isclose(expected, frame.timestamp_s, abs_tol=1e-7, rel_tol=0)):
                        raise ValueError(f"Frame {frame.index} timestamp differs from the source presentation timestamp.")
        return self.store.put(field, document)

    def import_document(self, identifier, content, filename):
        return self.save(identifier, parse_annotations(content, filename))

    def metrics(self, identifier):
        return annotation_metrics(self.get(identifier))

    def propose(self, identifier, request: ProposalRequest):
        field = self.manager.field_store.get(identifier)
        snapshot = self.manager.snapshot() if callable(getattr(self.manager, "snapshot", None)) else None
        if snapshot is not None and snapshot.state in ("starting", "running"):
            raise HTTPException(409, "Pause the live observation before running offline model proposals.")
        with self._lock:
            navigator, corrector = self._video(field)
            if request.end_index > navigator.summary()["frame_count"]:
                raise ValueError("Proposal range extends beyond the indexed source frames.")
            document = self.get(identifier)
            frames = {frame.index: frame.model_copy(deep=True) for frame in document.frames}
            # One run has one identity scope. Never stitch newly reset tracker
            # IDs into predictions from earlier runs or change manual labels.
            for frame in frames.values():
                frame.predictions = []
            factory = self.manager.detector_factory or RoadLensDetector
            started = perf_counter()
            try:
                detector = factory(self.manager.weights_path, confidence=request.confidence, input_size=request.input_size)
            except (FileNotFoundError, cv2.error) as error:
                raise ValueError(f"Offline detector unavailable: {error}") from error
            tracker = BaselineTracker() if request.tracker == "baseline" else IoUTracker()
            previous_timestamp = None
            for index in range(request.start_index, request.end_index+1):
                metadata = self._metadata(field, navigator, index)
                timestamp = metadata["timestamp_s"]
                if timestamp is None or timestamp < 0 or (previous_timestamp is not None and timestamp <= previous_timestamp):
                    raise ValueError("Offline tracking requires finite, nonnegative, strictly increasing source presentation timestamps.")
                previous_timestamp = timestamp
                image = self._image(field, navigator, corrector, index)
                detected = detector.detect(image)
                tracks = tracker.update(detected, timestamp)
                frame = frames.get(index) or AnnotatedFrame(index=index, timestamp_s=timestamp)
                frame.predictions = [TrackPrediction(predicted_track_id=track["id"], category=track["category"],
                                                     bbox=track["bbox"], confidence=track["confidence"])
                                     for track in tracks if track["missed"] == 0]
                frames[index] = frame
            document.frames = sorted(frames.values(), key=lambda frame: frame.index)
            document.proposal_metadata = ProposalMetadata(**request.model_dump(), elapsed_ms=(perf_counter()-started)*1000,
                model=getattr(detector, "name", type(detector).__name__))
            return self.store.put(field, document)


def annotation_routes(manager) -> APIRouter:
    service = getattr(manager, "annotations", None)
    if service is None:
        service = manager.annotations = AnnotationService(manager)
    router = APIRouter(prefix="/api/field-sessions")

    def conflict(operation):
        try:
            return operation()
        except AnnotationRevisionConflict as error:
            raise HTTPException(409, str(error)) from error

    @router.get("/{identifier}/annotations", response_model=AnnotationDocument)
    def annotations(identifier: str):
        return service.get(identifier)

    @router.put("/{identifier}/annotations", response_model=AnnotationDocument)
    def save(identifier: str, document: AnnotationDocument):
        return conflict(lambda: service.save(identifier, document))

    @router.post("/{identifier}/annotations/import", response_model=AnnotationDocument)
    async def import_annotations(identifier: str, file: UploadFile = File(...)):
        try:
            content = await file.read(8*1024*1024+1)
            return await asyncio.to_thread(conflict, lambda: service.import_document(identifier, content, file.filename or ""))
        finally:
            await file.close()

    @router.get("/{identifier}/annotations/export")
    def export_annotations(identifier: str, format: str = Query(default="json", pattern="^(json|csv)$")):
        document = service.get(identifier)
        body = annotations_csv(document) if format == "csv" else document.model_dump_json(indent=2)
        return Response(body, media_type="text/csv; charset=utf-8" if format == "csv" else "application/json",
                        headers={"Content-Disposition": f'attachment; filename="annotations-{document.field_session_id}.{format}"'})

    @router.get("/{identifier}/annotations/metrics")
    def metrics(identifier: str):
        return service.metrics(identifier)

    @router.get("/{identifier}/frames")
    def frame(identifier: str, index: int | None = Query(default=None, ge=1, le=100000),
              timestamp_s: float | None = Query(default=None)):
        if index is not None and timestamp_s is not None:
            raise ValueError("Navigate by frame index or source timestamp, not both.")
        return service.frame_at(identifier, timestamp_s) if timestamp_s is not None else service.frame(identifier, index or 1)

    @router.get("/{identifier}/frames/image")
    def image(identifier: str, index: int = Query(default=1, ge=1, le=100000)):
        return Response(service.image(identifier, index), media_type="image/jpeg")

    @router.post("/{identifier}/proposals", response_model=AnnotationDocument)
    def proposals(identifier: str, request: ProposalRequest):
        return conflict(lambda: service.propose(identifier, request))

    return router
