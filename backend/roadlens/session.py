"""One owner for camera access, processing workers, and session-scoped statistics."""

import logging
import hashlib
import queue
import threading
import time
import uuid
from datetime import datetime, timezone
from collections import defaultdict, deque
from pathlib import Path
from typing import Callable

import cv2
import numpy as np

from .capture import SourceError, discover_cameras, open_source
from .calibration_models import CalibrationInput, ImageGeometry, GateInput
from .calibration_store import CalibrationStore
from .camera_store import CameraProfileStore
from .camera_calibration import FrameUndistorter
from .measurement_session import MeasurementSession
from .schemas import Counts, OverlaySettings, SessionSnapshot, StartRequest, TrackSnapshot
from .timing import TimingIntegrity
from .video_catalog import VideoCatalog
from .traffic_engine import TrafficEngine
from .traffic_models import TrafficConfiguration
from .traffic_store import TrafficStore
from .traffic_overlay import TrafficOverlaySettings, draw_traffic_regions


logger = logging.getLogger(__name__)


class SessionConflict(RuntimeError):
    pass


def draw_tracks(frame: np.ndarray, tracks: list[dict], settings: OverlaySettings | None = None,
                grid: list | None = None, gates=None, traffic_settings=None, traffic_state=None,
                traffic_configuration=None, transform=None) -> np.ndarray:
    settings = settings or OverlaySettings()
    traffic_settings = traffic_settings or TrafficOverlaySettings()
    annotated = frame.copy()
    draw_traffic_regions(annotated, traffic_configuration, traffic_state, traffic_settings, transform)
    if settings.grid:
        for line in grid or []:
            points = np.asarray(line, dtype=np.int32)
            if len(points) > 1:
                cv2.polylines(annotated, [points.reshape(-1, 1, 2)], False, (105, 100, 75), 1, cv2.LINE_AA)
    if settings.gates and gates and gates.valid:
        for name, segment, color in (("A", gates.gate_a, (100, 210, 180)), ("B", gates.gate_b, (215, 160, 100))):
            start, end = (tuple(int(value) for value in point) for point in segment)
            cv2.line(annotated, start, end, color, 2, cv2.LINE_AA)
            cv2.putText(annotated, f"Gate {name}", start, cv2.FONT_HERSHEY_SIMPLEX, 0.55, color, 2, cv2.LINE_AA)
    for track in tracks:
        if track["missed"]:
            continue
        x1, y1, x2, y2 = (int(value) for value in track["bbox"])
        color = (180, 215, 80) if track["state"] == "confirmed" else (90, 165, 220)
        if settings.boxes:
            cv2.rectangle(annotated, (x1, y1), (x2, y2), color, 2)
        class_state = (traffic_state or {}).get("tracks", {}).get(track["id"], {})
        category = class_state.get("category", track["category"])
        parts = [f"#{track['id']}"] if traffic_settings.track_ids else []
        if traffic_settings.vehicle_classes:
            parts += [f"{category} {track['confidence']:.0%}"]
        label = " ".join(parts)
        if settings.speeds and track.get("estimated_speed_kmh") is not None:
            label += f" {track['estimated_speed_kmh']:.1f} km/h"
        if label and (settings.boxes or traffic_settings.track_ids or traffic_settings.vehicle_classes
                      or (settings.speeds and track.get("estimated_speed_kmh") is not None)):
            cv2.putText(annotated, label, (max(0, x1), max(18, y1 - 8)), cv2.FONT_HERSHEY_SIMPLEX, 0.55, color, 2, cv2.LINE_AA)
        history = np.asarray(track["history"], dtype=np.int32)
        if settings.trajectories and len(history) > 1:
            cv2.polylines(annotated, [history.reshape(-1, 1, 2)], False, color, 1, cv2.LINE_AA)
        if traffic_settings.direction_indicators and len(history) > 1:
            cv2.arrowedLine(annotated, tuple(history[-2]), tuple(history[-1]), color, 2, cv2.LINE_AA, tipLength=.35)
        if settings.contact_points and track.get("image_position") is not None:
            point = tuple(int(value) for value in track["image_position"])
            cv2.circle(annotated, point, 3, (245, 220, 120), -1, cv2.LINE_AA)
    return annotated


class SessionManager:
    def __init__(
        self,
        weights_path: Path | None = None,
        upload_dir: Path | None = None,
        detector_factory: Callable | None = None,
        source_factory: Callable = open_source,
        tracker_factory: Callable | None = None,
        calibration_dir: Path | None = None,
        camera_profile_dir: Path | None = None,
        traffic_dir: Path | None = None,
    ):
        root = Path(__file__).resolve().parents[2]
        self.weights_path = weights_path or root / "models" / "vehicle_detector.onnx"
        self.upload_dir = upload_dir or root / "data" / "uploads"
        self.video_catalog = VideoCatalog(self.upload_dir)
        self.detector_factory = detector_factory
        self.source_factory = source_factory
        self.tracker_factory = tracker_factory
        self.calibrations = CalibrationStore(calibration_dir or root / "data" / "calibrations")
        self.camera_profiles = CameraProfileStore(camera_profile_dir or (self.calibrations.directory.parent / "camera_profiles"))
        traffic_base = self.upload_dir.parent if upload_dir is not None and calibration_dir is None else self.calibrations.directory.parent
        self.traffic_store = TrafficStore(traffic_dir or traffic_base / "traffic")
        self.traffic_overlays = TrafficOverlaySettings()
        self._traffic: TrafficEngine | None = None
        self._traffic_archive_error: str | None = None
        self._measurement = MeasurementSession()
        self._lock = threading.RLock()
        self._control_lock = threading.RLock()
        self._frames_changed = threading.Condition(self._lock)
        self._snapshot = SessionSnapshot()
        self._worker: threading.Thread | None = None
        self._capture_worker: threading.Thread | None = None
        self._stop = threading.Event()
        self._run_gate = threading.Event()
        self._run_gate.set()
        self._queue = queue.Queue(maxsize=1)
        self._capture_error: Exception | None = None
        self._release_failed = False
        self._capture_done = threading.Event()
        self._jpeg: bytes | None = None
        self._frame_version = 0
        self._videos: dict[str, tuple[Path, str, str]] = {}
        self._raw_image: np.ndarray | None = None
        self._frozen: dict[str, tuple[bytes, dict]] = {}
        self._configuration_revision = 0
        self._resume_after = 0.0
        self._source_image = None
        self._undistorter = None
        self._camera_revision = 0
        self._timing = TimingIntegrity()
        self._started_at = self._ended_at = None
        self._start_options = None

    def _ensure_traffic_locked(self, geometry: ImageGeometry):
        if self._traffic is None:
            stored = self.traffic_store.configuration_for(self._snapshot.source_id, geometry)
            configuration = TrafficConfiguration.model_validate(stored) if stored else TrafficConfiguration(
                source_id=self._snapshot.source_id, geometry=geometry)
            self._traffic = TrafficEngine(self._snapshot.session_id, self._snapshot.source_id, geometry,
                                          configuration, getattr(self, "traffic_provenance", "recorded_unverified"))
        elif self._traffic.geometry != geometry:
            self._traffic.change_geometry(geometry)

    def traffic_configuration(self):
        with self._lock:
            return self._traffic.configuration.model_dump(mode="json") if self._traffic else None

    def configure_traffic(self, configuration: TrafficConfiguration):
        with self._control_lock, self._lock:
            if self._snapshot.state in {"running", "starting"}:
                raise SessionConflict("Pause or stop the observation before editing counting lines and monitoring zones.")
            if self._raw_image is None or self._snapshot.geometry is None:
                raise ValueError("Open a source and wait for a frame before configuring traffic geometry.")
            if configuration.source_id != self._snapshot.source_id or configuration.geometry != self._snapshot.geometry:
                raise ValueError("Traffic source and full image geometry must match the current observation.")
            ground = [zone for zone in configuration.zones if zone.coordinate_space == "ground"]
            if ground:
                transform = self._measurement.transform
                if transform is None or configuration.calibration_id != self._snapshot.calibration_id:
                    raise ValueError("Ground zones require the currently active, compatible road-plane calibration.")
                for zone in ground:
                    for point in zone.points:
                        pixel = transform.unproject(point)
                        if pixel is None or transform.region_margin_px(pixel) < -1e-6:
                            raise ValueError("Ground-zone vertices must lie inside the measured road calibration region.")
            self._ensure_traffic_locked(configuration.geometry)
            self._traffic.configure(configuration)
            self.traffic_store.save_configuration(self._traffic.configuration)
            self._configuration_revision += 1
            self._refresh_preview_locked()
            return self.traffic_configuration()

    def set_traffic_overlays(self, settings: TrafficOverlaySettings):
        with self._lock:
            self.traffic_overlays = settings
            self._configuration_revision += 1
            self._refresh_preview_locked()

    def traffic_snapshot(self):
        with self._lock:
            if self._traffic is None:
                return None
            result = self._traffic.snapshot()
            measurements = [item.model_dump(mode="json") for item in self._snapshot.measurements]
            result.update(name=self._snapshot.source_label or "Traffic observation", state=self._snapshot.state,
                          started_at=self._started_at.isoformat() if self._started_at else None,
                          ended_at=self._ended_at.isoformat() if self._ended_at else None,
                          timing_summary=self._timing.snapshot(), source_type=self._snapshot.source_type,
                          source_timebase=self._snapshot.timing_source, measurements=measurements,
                          calibration_id=self._snapshot.calibration_id,
                          calibration_available=self._snapshot.calibration_status == "ready",
                          calibration_metadata={
                              "road_plane": self._measurement.profile.model_dump(mode="json") if self._measurement.profile else None,
                              "intrinsic": self._undistorter.profile.model_dump(mode="json") if self._undistorter else None},
                          camera={"geometry": self._traffic.geometry.model_dump(mode="json"),
                                  "intrinsic_profile_id": self._snapshot.camera_model_id,
                                  "detector_input_size": self._start_options.input_size if self._start_options else None,
                                  "detector_confidence": self._start_options.confidence if self._start_options else None},
                          traffic_overlays=self.traffic_overlays.model_dump())
            if self._traffic_archive_error:
                result["archive_error"] = self._traffic_archive_error
            result["field_source_id"] = (f"{self._snapshot.source_id}:observation:{self._snapshot.session_id}"
                                         if self._snapshot.source_type == "camera" else self._snapshot.source_id)
            if self._traffic.configuration.calibration_id != self._snapshot.calibration_id and any(
                    zone.coordinate_space == "ground" for zone in self._traffic.configuration.zones):
                result["limitations"].append("Ground zones are inactive because their road calibration is unavailable or changed.")
            if self._snapshot.source_type == "camera":
                result["limitations"].append("Saved image regions cannot detect camera movement; recheck the view before interpreting counts.")
            # An event can acquire a later completed speed only for a unique,
            # same-track gate interval containing its source crossing timestamp.
            speed_by_track = defaultdict(list)
            for item in measurements:
                if item["status"] == "valid" and item["estimated_speed_kmh"] is not None:
                    speed_by_track[(item["track_id"], item["source_id"], item["session_id"])].append(item)
            for event in result["events"]:
                event["measured_speed_kmh"] = None
                candidates = [item for item in speed_by_track[(event["track_id"], event["source_id"], event["session_id"])]
                              if item["gate_a_timestamp_s"] is not None and item["gate_b_timestamp_s"] is not None
                              and min(item["gate_a_timestamp_s"], item["gate_b_timestamp_s"]) <= event["timestamp_s"]
                              <= max(item["gate_a_timestamp_s"], item["gate_b_timestamp_s"])]
                if len(candidates) == 1:
                    event["measured_speed_kmh"] = candidates[0]["estimated_speed_kmh"]
                    event["speed_measurement_id"] = candidates[0]["id"]
            return result

    def _traffic_drawing_locked(self):
        return {"traffic_settings": self.traffic_overlays,
                "traffic_state": self._traffic.overlay_state() if self._traffic else None,
                "traffic_configuration": self._traffic.configuration if self._traffic else None,
                "transform": self._measurement.transform}

    def snapshot(self) -> SessionSnapshot:
        with self._lock:
            return self._snapshot.model_copy(deep=True)

    def measurement_export(self) -> dict:
        with self._lock:
            # Completed records are immutable after publication. Capture their
            # references under the lock and serialize evidence outside it.
            records = tuple(self._measurement.estimator.measurements)
            metadata = {"schema_version": 1, "independently_validated": False,
                        "units": {"speed": "km/h", "distance": "m", "time": "s", "image_position": "px"},
                        "session_id": self._snapshot.session_id, "source_id": self._snapshot.source_id,
                        "measurement_summary": dict(self._snapshot.measurement_summary),
                        "pipeline_profile_ms": dict(self._snapshot.pipeline_profile)}
        return {**metadata, "measurements": [record.model_dump(mode="json") for record in records]}

    def model_status(self) -> dict:
        return {"ready": self.weights_path.is_file(), "name": "YOLOX-S · INT8", "path": self.weights_path.name, "input_size": 640}

    def configure_camera_model(self, profile_id: str | None, confirm_unchanged: bool):
        with self._control_lock, self._lock:
            if self._snapshot.state in {"running", "starting"}:
                raise SessionConflict("Pause or stop the observation before changing the camera model.")
            if self._source_image is None:
                raise ValueError("Open a source and wait for a frame before selecting a camera model.")
            if profile_id is not None and not confirm_unchanged:
                raise ValueError("Confirm unchanged camera, lens, zoom, focus and image geometry before applying intrinsics.")
            model = FrameUndistorter(self.camera_profiles.get(profile_id)) if profile_id else None
            height, width = self._source_image.shape[:2]
            if model and model.source_geometry != ImageGeometry(width=width, height=height):
                raise ValueError("Camera model resolution, crop, rotation or mirroring does not match the captured source.")
            corrected = model.apply(self._source_image) if model else self._source_image
            self._undistorter = model
            self._camera_revision += 1
            self._configuration_revision += 1
            self._snapshot.camera_model_id = profile_id
            self._measurement.invalidate("Camera model changed. Rebuild road references and gates in the selected image coordinates.")
            self._measurement.set_geometry(model.geometry if model else ImageGeometry(width=width, height=height))
            self._ensure_traffic_locked(self._measurement.geometry)
            self._raw_image = corrected
            self._frozen.clear()
            self._snapshot.tracks = []
            self._measurement.sync(self._snapshot)
            self._refresh_preview_locked(clear_track_speeds=True)
            return self.snapshot()

    def camera_preview(self, profile_id: str, corrected: bool):
        profile = self.camera_profiles.get(profile_id)
        with self._lock:
            if self._source_image is None:
                raise SourceError("Open a source and wait for a frame before previewing a camera model.")
            image = self._source_image
        if corrected:
            image = FrameUndistorter(profile).apply(image)
        success, encoded = cv2.imencode(".jpg", image, [cv2.IMWRITE_JPEG_QUALITY, 90])
        if not success:
            raise SourceError("Could not encode camera-model preview.")
        return encoded.tobytes()

    def delete_camera_profile(self, profile_id: str):
        with self._control_lock, self._lock:
            if self._snapshot.camera_model_id == profile_id:
                self.configure_camera_model(None, False)
            self.camera_profiles.delete(profile_id)

    def field_observation(self):
        with self._lock:
            snapshot = self._snapshot
            if not snapshot.session_id or snapshot.geometry is None:
                raise ValueError("Start an observation and wait for a frame before creating a field session.")
            video = next((value for value in self._videos.values() if value[2] == snapshot.source_id), None)
            relative = None
            if video:
                try:
                    relative = video[0].resolve().relative_to(self.upload_dir.resolve()).as_posix()
                except ValueError:
                    pass
            digest = snapshot.source_id.removeprefix("video:") if snapshot.source_id.startswith("video:") else None
            if digest and (len(digest) != 64 or any(c not in "0123456789abcdef" for c in digest)):
                digest = None
            options = self._start_options
            profile = self._measurement.profile
            field_source_id = (f"{snapshot.source_id}:observation:{snapshot.session_id}" if snapshot.source_type == "camera" else snapshot.source_id)
            return {"source": {"source_id": field_source_id, "relative_path": relative, "content_sha256": digest},
                    "camera": {"configuration_id": snapshot.camera_model_id or "source-camera",
                               "geometry": snapshot.geometry.model_dump(mode="json"), "intrinsic_profile_id": snapshot.camera_model_id,
                               "detector_input_size": options.input_size if options else None,
                               "detector_confidence": options.confidence if options else None, "tracker": "global_motion"},
                    "calibration_id": snapshot.calibration_id,
                    "calibration_metadata": {"road_plane": profile.model_dump(mode="json") if profile else None,
                                             "intrinsic": self._undistorter.profile.model_dump(mode="json") if self._undistorter else None},
                    "gates": profile.gates.model_dump(mode="json") if profile and profile.gates else None,
                    "started_at": self._started_at, "ended_at": self._ended_at,
                    "source_timebase": snapshot.timing_source or "", "timing_summary": self._timing.snapshot(),
                    "measurements": [{"event_id": item.id, "variant": "original", "measurement": item.model_dump(mode="json")} for item in snapshot.measurements]}

    def register_video(self, path: Path, label: str, source_id: str | None = None) -> str:
        if source_id is None:
            with path.open("rb") as stream:
                source_id = "video:" + hashlib.file_digest(stream, "sha256").hexdigest()
        video_id = str(uuid.uuid4())
        catalog = self.video_catalog.register(path, label, source_id, video_id)
        if catalog is not None:
            video_id, label, source_id = catalog["video_id"], catalog["name"], catalog["source_id"]
            path = self.upload_dir / catalog["relative_path"]
        with self._lock:
            self._videos[video_id] = (path, label, source_id)
        return video_id

    def field_sources(self):
        sources = self.video_catalog.sources()
        with self._lock:
            for source in sources:
                self._videos[source["video_id"]] = (self.upload_dir / source["relative_path"], source["name"], source["source_id"])
        return sources

    def video_file(self, video_id):
        with self._lock:
            return self._videos[video_id][0]

    def cameras(self):
        with self._control_lock:
            snapshot = self.snapshot()
            processing_camera = snapshot.source_type == "camera" and self._worker is not None and self._worker.is_alive()
            capture_active = self._capture_worker is not None and self._capture_worker.is_alive()
            if processing_camera or capture_active or self._release_failed:
                raise SessionConflict("Stop the camera session before scanning for cameras.")
            return discover_cameras()

    def start(self, request: StartRequest) -> SessionSnapshot:
        with self._control_lock:
            if self._release_failed:
                raise SessionConflict("The previous source could not be released. Restart the backend before opening another source.")
            if self._worker is not None and self._worker.is_alive():
                raise SessionConflict("Stop the current session before starting another.")
            if self._capture_worker is not None and self._capture_worker.is_alive():
                raise SessionConflict("The camera is still releasing. Wait before starting another session.")
            video_path, label = None, f"Camera {request.camera_index}"
            source_id = f"camera:{request.camera_index}"
            if request.source_type == "video":
                with self._lock:
                    video = self._videos.get(request.video_id)
                if video is None:
                    raise SourceError("This upload is unavailable. Select and upload the video again.")
                video_path, label, source_id = video
            with self._lock:
                self._configuration_revision += 1
                self._snapshot = SessionSnapshot(state="starting", session_id=str(uuid.uuid4()), source_type=request.source_type, source_label=label, source_id=source_id,
                                                 overlays=self._snapshot.overlays)
                self._measurement.reset(source_id, self._snapshot.session_id)
                self._traffic = None
                self._traffic_archive_error = None
                self._undistorter = None
                self._camera_revision += 1
                self._source_image = None
                self._timing = TimingIntegrity()
                self._started_at, self._ended_at = datetime.now(timezone.utc), None
                self._start_options = request
                self._resume_after = 0.0
                self._raw_image = None
                self._frozen.clear()
                self._jpeg = None
                self._frame_version += 1
                self._capture_error = None
                self._capture_worker = None
                self._capture_done.clear()
                self._stop.clear()
                self._run_gate.set()
                self._queue = queue.Queue(maxsize=1)
                self._frames_changed.notify_all()
            self._worker = threading.Thread(target=self._process, args=(request, video_path, label), name="roadlens-processing", daemon=True)
            self._worker.start()
            return self.snapshot()

    def pause(self) -> SessionSnapshot:
        with self._control_lock, self._lock:
            if self._snapshot.state != "running":
                raise SessionConflict("Only a running session can be paused.")
            self._run_gate.clear()
            self._snapshot.state = "paused"
            self._measurement.estimator.interrupt("Observation paused before both gates were crossed.")
            if self._traffic:
                self._traffic.interrupt("Observation paused; trajectories and zone visits cannot bridge the pause.")
            self._measurement.sync(self._snapshot)
            self._refresh_preview_locked()
            return self.snapshot()

    def resume(self) -> SessionSnapshot:
        with self._control_lock, self._lock:
            if self._snapshot.state != "paused":
                raise SessionConflict("Only a paused session can be resumed.")
            self._snapshot.state = "running"
            if self._snapshot.source_type == "camera":
                self._resume_after = time.monotonic()
            self._run_gate.set()
            return self.snapshot()

    def stop(self) -> SessionSnapshot:
        with self._control_lock:
            self._stop.set()
            self._run_gate.set()
            with self._frames_changed:
                self._frames_changed.notify_all()
            if self._worker is not None:
                self._worker.join(timeout=8)
                if self._worker.is_alive():
                    with self._lock:
                        self._snapshot.state = "error"
                        self._snapshot.error = "The source has not released yet. Close other camera applications and wait before restarting."
                    return self.snapshot()
            capture_active = self._capture_worker is not None and self._capture_worker.is_alive()
            if capture_active or self._release_failed:
                with self._lock:
                    self._snapshot.state = "error"
                    self._snapshot.error = "The source has not released. Restart the backend before opening another source."
                return self.snapshot()
            with self._frames_changed:
                self._measurement.estimator.finish("Observation stopped before both gates were crossed.")
                self._measurement.sync(self._snapshot)
                self._snapshot.state = "stopped"
                self._frames_changed.notify_all()
            return self.snapshot()

    def reset(self) -> SessionSnapshot:
        with self._control_lock:
            self.stop()
            worker_active = self._worker is not None and self._worker.is_alive()
            capture_active = self._capture_worker is not None and self._capture_worker.is_alive()
            if worker_active or capture_active or self._release_failed:
                raise SessionConflict("The source is still stopping; session statistics have been kept.")
            with self._frames_changed:
                self._configuration_revision += 1
                self._snapshot = SessionSnapshot()
                self._measurement.reset()
                self._traffic = None
                self._traffic_archive_error = None
                self._undistorter = None
                self._camera_revision += 1
                self._source_image = None
                self._timing = TimingIntegrity()
                self._raw_image = None
                self._frozen.clear()
                self._jpeg = None
                self._frame_version += 1
                self._frames_changed.notify_all()
            return self.snapshot()

    def frame(self) -> bytes | None:
        with self._lock:
            return self._jpeg

    def freeze_frame(self) -> dict:
        with self._lock:
            if self._raw_image is None or self._measurement.geometry is None:
                raise SourceError("Start a source and wait for a frame before freezing calibration.")
            image = self._raw_image
            camera_revision = self._camera_revision
            metadata = {"source_id": self._snapshot.source_id, "geometry": self._measurement.geometry.model_dump(),
                        "session_id": self._snapshot.session_id}
        success, encoded = cv2.imencode(".jpg", image, [cv2.IMWRITE_JPEG_QUALITY, 95])
        if not success:
            raise SourceError("The calibration frame could not be encoded.")
        frame_id = str(uuid.uuid4())
        metadata.update(frame_id=frame_id, image_url=f"/api/calibration/frame/{frame_id}")
        with self._lock:
            if metadata["session_id"] != self._snapshot.session_id or camera_revision != self._camera_revision:
                raise SourceError("The observation or camera model changed while freezing. Freeze the current source again.")
            self._frozen[frame_id] = (encoded.tobytes(), metadata)
            while len(self._frozen) > 3:
                del self._frozen[next(iter(self._frozen))]
        return metadata

    def frozen_frame(self, frame_id: str) -> bytes:
        with self._lock:
            if frame_id not in self._frozen:
                raise KeyError("This frozen frame is unavailable; freeze the current source again.")
            return self._frozen[frame_id][0]

    def save_calibration(self, data: CalibrationInput, profile_id: str | None = None):
        with self._lock:
            profile = self.calibrations.put(data, profile_id)
            if self._measurement.profile and self._measurement.profile.id == profile.id:
                self._invalidate_locked("Calibration references were edited. Apply the saved profile again.")
            return profile

    def delete_calibration(self, profile_id: str):
        with self._lock:
            self.calibrations.delete(profile_id)
            if self._measurement.profile and self._measurement.profile.id == profile_id:
                self._invalidate_locked("The active calibration profile was deleted.")

    def activate_calibration(self, profile_id: str, confirm_stationary: bool):
        with self._lock:
            profile = self.calibrations.get(profile_id)
            self._measurement.activate(profile, confirm_stationary)
            self._configuration_revision += 1
            self._measurement.sync(self._snapshot)
            self._refresh_preview_locked(clear_track_speeds=True)
            return self.snapshot()

    def _invalidate_locked(self, reason: str):
        self._configuration_revision += 1
        self._measurement.invalidate(reason)
        self._measurement.sync(self._snapshot)
        self._refresh_preview_locked(clear_track_speeds=True)

    def invalidate_calibration(self, reason: str):
        with self._lock:
            self._invalidate_locked(reason)
            return self.snapshot()

    def update_gates(self, data: GateInput):
        with self._lock:
            result = self._measurement.configure_gates(data)
            self._configuration_revision += 1
            self.calibrations.save(self._measurement.profile)
            self._measurement.sync(self._snapshot)
            self._refresh_preview_locked(clear_track_speeds=True)
            return result

    def remove_gates(self):
        with self._lock:
            self._measurement.remove_gates()
            self._configuration_revision += 1
            if self._measurement.profile:
                self.calibrations.save(self._measurement.profile)
            self._measurement.sync(self._snapshot)
            self._refresh_preview_locked(clear_track_speeds=True)
            return self.snapshot()

    def clear_measurements(self):
        with self._lock:
            self._measurement.clear_history()
            self._configuration_revision += 1
            self._measurement.sync(self._snapshot)
            self._refresh_preview_locked(clear_track_speeds=True)
            return self.snapshot()

    def set_overlays(self, settings: OverlaySettings):
        with self._lock:
            self._snapshot.overlays = settings
            self._configuration_revision += 1
            self._refresh_preview_locked()
            return self.snapshot()

    def _refresh_preview_locked(self, clear_track_speeds: bool = False):
        if clear_track_speeds:
            for track in self._snapshot.tracks:
                track.estimated_speed_kmh = None
                track.world_position = None
                track.position_history = []
                track.position_diagnostics = ["Measurement configuration changed; waiting for a new source observation."]
                track.measurement_state = "waiting" if self._measurement.transform else "not_calibrated"
        if self._raw_image is None:
            return
        tracks = [track.model_dump() for track in self._snapshot.tracks]
        grid = self._measurement.transform.diagnostics.grid_image if self._measurement.transform else []
        annotated = draw_tracks(self._raw_image, tracks, self._snapshot.overlays, grid, self._measurement.gates,
                                **self._traffic_drawing_locked())
        success, encoded = cv2.imencode(".jpg", annotated, [cv2.IMWRITE_JPEG_QUALITY, 82])
        if success:
            self._jpeg = encoded.tobytes()
            self._frame_version += 1
            self._snapshot.preview_revision = self._frame_version
            self._frames_changed.notify_all()

    def wait_for_frame(self, version: int, session_id: str | None, timeout: float = 1.0):
        with self._frames_changed:
            self._frames_changed.wait_for(
                lambda: self._frame_version != version
                or (session_id is not None and session_id != self._snapshot.session_id)
                or self._snapshot.state in {"idle", "stopped", "completed", "error"},
                timeout=timeout,
            )
            return self._frame_version, self._jpeg, self._snapshot.state, self._snapshot.session_id

    def _wait_until_running(self) -> bool:
        while not self._stop.is_set():
            if self._run_gate.wait(timeout=0.1):
                return not self._stop.is_set()
        return False

    def _acquire(self, source):
        times = deque(maxlen=120)
        try:
            while not self._stop.is_set():
                packet = source.read()
                if packet is None:
                    raise SourceError("The camera stopped delivering frames.")
                times.append(packet.acquired_at)
                with self._lock:
                    self._timing.source(packet)
                    self._snapshot.timing_diagnostics = self._timing.snapshot()
                    if len(times) > 1 and times[-1] > times[0]:
                        self._snapshot.capture_fps = (len(times) - 1) / (times[-1] - times[0])
                try:
                    self._queue.put_nowait(packet)
                except queue.Full:
                    try:
                        self._queue.get_nowait()
                    except queue.Empty:
                        pass
                    else:
                        with self._lock:
                            self._snapshot.dropped_frames += 1
                    self._queue.put_nowait(packet)
        except Exception as error:
            with self._lock:
                self._capture_error = error
        finally:
            self._capture_done.set()

    def _process(self, request: StartRequest, video_path: Path | None, label: str):
        source = None
        finished = False
        processing_times = deque(maxlen=120)
        capture_times = deque(maxlen=120)
        try:
            source = self.source_factory(request, video_path, label)
            if self._stop.is_set():
                return
            if self.detector_factory is None:
                from .detector import RoadLensDetector
                detector_factory = RoadLensDetector
            else:
                detector_factory = self.detector_factory
            if self.tracker_factory is None:
                from .tracker import IoUTracker
                tracker_factory = IoUTracker
            else:
                tracker_factory = self.tracker_factory
            detector = detector_factory(self.weights_path, confidence=request.confidence, input_size=request.input_size)
            tracker = tracker_factory()
            tracker_camera_revision = self._camera_revision
            with self._lock:
                self._snapshot.width = source.width
                self._snapshot.height = source.height
                self._snapshot.reported_fps = source.reported_fps
                self._snapshot.state = "running"
            if source.live:
                self._capture_worker = threading.Thread(target=self._acquire, args=(source,), name="roadlens-capture", daemon=True)
                self._capture_worker.start()
            while self._wait_until_running():
                if source.live:
                    try:
                        packet = self._queue.get(timeout=0.1)
                    except queue.Empty:
                        if self._capture_done.is_set():
                            raise SourceError(str(self._capture_error or "Camera acquisition stopped.")) from self._capture_error
                        continue
                else:
                    packet = source.read()
                    if packet is None:
                        finished = True
                        break
                    capture_times.append(packet.acquired_at)
                    with self._lock:
                        self._timing.source(packet)
                if not self._wait_until_running():
                    break
                if source.live and packet.acquired_at < self._resume_after:
                    continue
                prepared = False
                while self._wait_until_running():
                    with self._lock:
                        camera_model, camera_revision = self._undistorter, self._camera_revision
                    undistort_started = time.perf_counter()
                    image = camera_model.apply(packet.image) if camera_model else packet.image
                    undistortion_ms = (time.perf_counter() - undistort_started) * 1000 if camera_model else 0.0
                    inference_started = time.monotonic()
                    detections = detector.detect(image)
                    inference_ms = (time.monotonic() - inference_started) * 1000
                    retry_camera = False
                    while self._wait_until_running():
                        with self._lock:
                            if self._snapshot.state != "running":
                                continue
                            if source.live and packet.acquired_at < self._resume_after:
                                break
                            if camera_revision != self._camera_revision:
                                retry_camera = True
                                break
                            if tracker_camera_revision != camera_revision:
                                if hasattr(tracker, "reset_associations"):
                                    tracker.reset_associations()
                                else:
                                    tracker = tracker_factory()
                                tracker_camera_revision = camera_revision
                            tracking_started = time.perf_counter()
                            tracks = tracker.update(detections, packet.timestamp_s)
                            tracking_ms = (time.perf_counter() - tracking_started) * 1000
                            tracking_diagnostics = dict(getattr(tracker, "diagnostics", {}))
                            geometry = camera_model.geometry if camera_model else ImageGeometry(width=image.shape[1], height=image.shape[0])
                            self._measurement.set_geometry(geometry)
                            self._ensure_traffic_locked(geometry)
                            self._source_image = packet.image
                            self._raw_image = image
                            tracks = self._measurement.estimator.update(tracks, packet.timestamp_s,
                                timing_valid=packet.timing_warning is None and "fallback" not in packet.timing_source.lower())
                            traffic_tracks = [{**track,
                                "world_position": track.get("world_position") if self._traffic.configuration.calibration_id == (
                                    self._measurement.profile.id if self._measurement.profile else None) else None,
                                "speed_status": "valid" if track.get("estimated_speed_kmh") is not None else None}
                                for track in tracks]
                            self._traffic.update(traffic_tracks, packet.timestamp_s,
                                timing_valid=packet.timing_warning is None and "fallback" not in packet.timing_source.lower(),
                                frame_index=packet.index)
                            pipeline_profile = {"tracking_ms": tracking_ms, "undistortion_ms": undistortion_ms,
                                                "decode_ms": packet.decode_ms or 0.0, **self._measurement.estimator.last_profile}
                            grid = self._measurement.transform.diagnostics.grid_image if self._measurement.transform else []
                            annotated = draw_tracks(image, tracks, self._snapshot.overlays, grid, self._measurement.gates,
                                                    **self._traffic_drawing_locked())
                            render_revision = self._configuration_revision
                            prepared = True
                            break
                    if not retry_camera:
                        break
                if not prepared:
                    if self._stop.is_set():
                        break
                    continue
                success, encoded = cv2.imencode(".jpg", annotated, [cv2.IMWRITE_JPEG_QUALITY, 82])
                if not success:
                    raise SourceError("The processed video frame could not be encoded.")
                finished_at = time.monotonic()
                processing_times.append(finished_at)
                with self._frames_changed:
                    if camera_revision != self._camera_revision:
                        # The new model has already repainted the paused image.
                        # Never publish old-coordinate boxes under its geometry.
                        continue
                    if render_revision != self._configuration_revision:
                        # Configuration can change while JPEG encoding runs. Never publish stale speed labels.
                        tracks = [{**track, "estimated_speed_kmh": None, "world_position": None,
                                   "position_history": [], "measurement_state": "waiting" if self._measurement.transform else "not_calibrated"}
                                  for track in tracks]
                        grid = self._measurement.transform.diagnostics.grid_image if self._measurement.transform else []
                        annotated = draw_tracks(image, tracks, self._snapshot.overlays, grid, self._measurement.gates,
                                                **self._traffic_drawing_locked())
                        success, encoded = cv2.imencode(".jpg", annotated, [cv2.IMWRITE_JPEG_QUALITY, 82])
                        if not success:
                            raise SourceError("The updated preview could not be encoded.")
                    self._snapshot.frame_index = packet.index
                    self._snapshot.width = packet.image.shape[1]
                    self._snapshot.height = packet.image.shape[0]
                    self._snapshot.timestamp_s = packet.timestamp_s
                    self._snapshot.timing_source = packet.timing_source
                    self._snapshot.timing_warning = packet.timing_warning
                    self._timing.processed(packet, finished_at)
                    self._snapshot.timing_diagnostics = self._timing.snapshot()
                    self._snapshot.inference_ms = inference_ms
                    self._snapshot.pipeline_profile = pipeline_profile
                    self._snapshot.tracking_diagnostics = tracking_diagnostics
                    self._snapshot.latency_ms = (finished_at - packet.acquired_at) * 1000
                    if len(processing_times) > 1 and processing_times[-1] > processing_times[0]:
                        self._snapshot.processing_fps = (len(processing_times) - 1) / (processing_times[-1] - processing_times[0])
                    if not source.live and len(capture_times) > 1 and capture_times[-1] > capture_times[0]:
                        self._snapshot.capture_fps = (len(capture_times) - 1) / (capture_times[-1] - capture_times[0])
                    self._snapshot.tracks = [TrackSnapshot.model_validate(track) for track in tracks]
                    self._snapshot.counts = Counts.model_validate(tracker.counts)
                    self._snapshot.total_tracks = tracker.total_tracks
                    self._measurement.sync(self._snapshot)
                    self._jpeg = encoded.tobytes()
                    self._frame_version += 1
                    self._snapshot.preview_revision = self._frame_version
                    self._frames_changed.notify_all()
        except Exception as error:
            # Worker exceptions must become visible API state, including unexpected inference failures.
            logger.exception("Session processing failed")
            with self._frames_changed:
                self._ended_at = datetime.now(timezone.utc)
                if not self._stop.is_set():
                    self._snapshot.state = "error"
                    self._snapshot.error = str(error) or type(error).__name__
                self._frames_changed.notify_all()
        finally:
            self._stop.set()
            self._run_gate.set()
            if self._capture_worker is not None:
                self._capture_worker.join(timeout=2)
            if source is not None:
                try:
                    source.close()
                except Exception as error:
                    logger.exception("Source release failed")
                    with self._lock:
                        self._release_failed = True
                        self._snapshot.state = "error"
                        self._snapshot.error = f"The source could not be released: {error}"
            if self._capture_worker is not None and self._capture_worker.is_alive():
                self._capture_worker.join(timeout=2)
                with self._lock:
                    if self._capture_worker.is_alive():
                        self._snapshot.state = "error"
                        self._snapshot.error = "Camera acquisition did not release. Restart the backend before opening another camera."
            with self._frames_changed:
                self._measurement.estimator.finish("Observation ended before both gates were crossed.")
                if self._traffic:
                    self._traffic.interrupt("Observation ended; any occupied zone visit is incomplete.")
                self._ended_at = datetime.now(timezone.utc)
                self._measurement.sync(self._snapshot)
                if self._snapshot.state != "error":
                    self._snapshot.state = "completed" if finished else "stopped"
                self._frames_changed.notify_all()
            try:
                artifact = self.traffic_snapshot()
                if artifact is not None:
                    self.traffic_store.put(artifact)
            except (OSError, ValueError, KeyError, TypeError) as error:
                logger.exception("Traffic observation could not be archived")
                with self._lock:
                    self._traffic_archive_error = str(error)
