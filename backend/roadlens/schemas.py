"""The local API contract; no speed values exist before calibration."""

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

from .calibration_models import GateDiagnostics, ImageGeometry
from .measurement_models import MeasurementResult, PositionSample


VehicleCategory = Literal["car", "truck", "bus", "motorcycle"]
SessionState = Literal["idle", "starting", "running", "paused", "stopped", "completed", "error"]


class StartRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    source_type: Literal["camera", "video"]
    camera_index: int = Field(default=0, ge=0, le=20)
    video_id: str | None = None
    confidence: float = Field(default=0.35, ge=0.05, le=0.95)
    input_size: Literal[320, 416, 640] = 640
    width: int = Field(default=1280, ge=160, le=3840)
    height: int = Field(default=720, ge=120, le=2160)

    @model_validator(mode="after")
    def require_video(self):
        if self.source_type == "video" and not self.video_id:
            raise ValueError("Select and upload a video first.")
        return self


class Counts(BaseModel):
    car: int = 0
    truck: int = 0
    bus: int = 0
    motorcycle: int = 0


class TrackSnapshot(BaseModel):
    id: int
    category: VehicleCategory
    bbox: tuple[float, float, float, float]
    confidence: float
    state: str
    hits: int
    missed: int
    history: list[tuple[float, float]] = Field(default_factory=list)
    image_position: tuple[float, float] | None = None
    world_position: tuple[float, float] | None = None
    measurement_state: str = "not_calibrated"
    position_diagnostics: list[str] = Field(default_factory=list)
    position_history: list[PositionSample] = Field(default_factory=list)
    estimated_speed_kmh: float | None = None
    age_s: float = 0.0
    observation_gap_s: float = 0.0
    association_ambiguous: bool = False
    tracking_diagnostics: list[str] = Field(default_factory=list)


class OverlaySettings(BaseModel):
    model_config = ConfigDict(extra="forbid")

    boxes: bool = True
    trajectories: bool = True
    contact_points: bool = True
    gates: bool = True
    grid: bool = False
    speeds: bool = True


class SessionSnapshot(BaseModel):
    state: SessionState = "idle"
    session_id: str | None = None
    source_type: Literal["camera", "video"] | None = None
    source_label: str | None = None
    source_id: str | None = None
    error: str | None = None
    frame_index: int = 0
    preview_revision: int = 0
    width: int = 0
    height: int = 0
    reported_fps: float | None = None
    capture_fps: float | None = None
    processing_fps: float | None = None
    inference_ms: float | None = None
    pipeline_profile: dict[str, float] = Field(default_factory=dict)
    tracking_diagnostics: dict[str, int] = Field(default_factory=dict)
    latency_ms: float | None = None
    dropped_frames: int = 0
    timestamp_s: float | None = None
    timing_source: str | None = None
    timing_warning: str | None = None
    timing_diagnostics: dict = Field(default_factory=dict)
    camera_model_id: str | None = None
    tracks: list[TrackSnapshot] = Field(default_factory=list)
    counts: Counts = Field(default_factory=Counts)
    total_tracks: int = 0
    calibration_status: Literal["required", "ready", "incompatible"] = "required"
    calibration_id: str | None = None
    geometry: ImageGeometry | None = None
    calibration_warnings: list[str] = Field(default_factory=list)
    gates: GateDiagnostics | None = None
    measurements: list[MeasurementResult] = Field(default_factory=list)
    measurement_summary: dict = Field(default_factory=lambda: {
        "valid_count": 0, "approximate_count": 0, "rejected_count": 0,
        "latest_speed_kmh": None, "latest_status": None, "average_speed_kmh": None,
    })
    measurement_status: str = "Calibration required"
    overlays: OverlaySettings = Field(default_factory=OverlaySettings)


class CameraInfo(BaseModel):
    index: int
    name: str
    width: int
    height: int
    fps: float | None = None
