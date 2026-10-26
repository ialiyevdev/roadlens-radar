"""Versioned, source-bound traffic configuration and immutable observation events."""

from math import hypot
from typing import Annotated, Literal
from uuid import uuid4

from pydantic import BaseModel, ConfigDict, Field, model_validator

from .calibration_models import ImageGeometry, Point
from .traffic_geometry import simple_polygon

TrafficCategory = Literal["car", "truck", "bus", "motorcycle", "unknown"]
DetectorCategory = Literal["car", "truck", "bus", "motorcycle"]
TrafficProvenance = Literal["synthetic", "recorded_unverified", "manually_annotated", "independent_reference"]


class _TrafficModel(BaseModel):
    model_config = ConfigDict(extra="forbid", allow_inf_nan=False, str_strip_whitespace=True)


class CountingLine(_TrafficModel):
    id: str = Field(default_factory=lambda: str(uuid4()), min_length=1, max_length=120)
    label: str = Field(default="Counting line", min_length=1, max_length=120)
    start: Point
    end: Point
    positive_label: str = Field(default="A → B", min_length=1, max_length=80)
    negative_label: str = Field(default="B → A", min_length=1, max_length=80)
    hysteresis_px: float = Field(default=3.0, ge=0, le=100)

    @model_validator(mode="after")
    def valid_segment(self):
        if hypot(self.end[0] - self.start[0], self.end[1] - self.start[1]) < 2:
            raise ValueError("A counting line must have length at least two image pixels.")
        return self


class MonitoringZone(_TrafficModel):
    id: str = Field(default_factory=lambda: str(uuid4()), min_length=1, max_length=120)
    label: str = Field(default="Monitoring zone", min_length=1, max_length=120)
    points: list[Point] = Field(min_length=3, max_length=32)
    coordinate_space: Literal["image", "ground"] = "image"
    hysteresis: float = Field(default=3.0, ge=0, le=100)

    @model_validator(mode="after")
    def valid_polygon(self):
        if not simple_polygon(self.points):
            raise ValueError("A zone must be a simple, nondegenerate polygon without repeated vertices.")
        if any(abs(value) > 1_000_000 for point in self.points for value in point):
            raise ValueError("Zone coordinates exceed the supported coordinate range.")
        return self


class TrafficConfiguration(_TrafficModel):
    id: str = Field(default_factory=lambda: str(uuid4()), min_length=1, max_length=120)
    name: str = Field(default="Traffic configuration", min_length=1, max_length=120)
    source_id: str = Field(min_length=1, max_length=240)
    geometry: ImageGeometry
    calibration_id: str | None = Field(default=None, min_length=1, max_length=120)
    lines: list[CountingLine] = Field(default_factory=list, max_length=16)
    zones: list[MonitoringZone] = Field(default_factory=list, max_length=16)
    max_gap_s: float = Field(default=1.0, gt=0, le=30)
    min_track_hits: int = Field(default=3, ge=1, le=100)
    class_min_observations: int = Field(default=3, ge=1, le=100)
    class_min_confidence: float = Field(default=.55, ge=0, le=1)
    class_min_margin: float = Field(default=.15, ge=0, le=1)
    identity_suppression_s: float = Field(default=.75, ge=0, le=5)
    identity_suppression_px: float = Field(default=12.0, ge=0, le=200)
    stationary_window_s: float = Field(default=3.0, gt=0, le=60)
    stationary_radius_px: float = Field(default=4.0, ge=0, le=100)
    slow_speed_kmh: float = Field(default=5.0, ge=0, le=100)
    occupancy_moderate: int = Field(default=3, ge=1, le=1000)
    occupancy_high: int = Field(default=8, ge=2, le=1000)

    @model_validator(mode="after")
    def compatible_geometry(self):
        if self.occupancy_high <= self.occupancy_moderate:
            raise ValueError("High occupancy must exceed the moderate occupancy threshold.")
        if len({line.id for line in self.lines}) != len(self.lines):
            raise ValueError("Counting line identifiers must be unique within a configuration.")
        if len({zone.id for zone in self.zones}) != len(self.zones):
            raise ValueError("Monitoring zone identifiers must be unique within a configuration.")
        image_points = [point for line in self.lines for point in (line.start, line.end)]
        image_points += [point for zone in self.zones if zone.coordinate_space == "image" for point in zone.points]
        if any(not (0 <= x <= self.geometry.width and 0 <= y <= self.geometry.height) for x, y in image_points):
            raise ValueError("Image traffic geometry must lie within the configured image dimensions.")
        if any(zone.coordinate_space == "ground" for zone in self.zones) and not self.calibration_id:
            raise ValueError("Ground-plane monitoring zones require a bound road calibration ID.")
        return self


class TrafficEvent(_TrafficModel):
    id: str = Field(default_factory=lambda: str(uuid4()), min_length=1, max_length=120)
    session_id: str = Field(min_length=1, max_length=240)
    source_id: str = Field(min_length=1, max_length=240)
    track_id: int = Field(ge=1)
    timestamp_s: float = Field(ge=0)
    line_id: str = Field(min_length=1, max_length=120)
    line_label: str = Field(min_length=1, max_length=120)
    direction: Literal["positive", "negative"]
    direction_label: str = Field(min_length=1, max_length=80)
    category: TrafficCategory = "unknown"
    class_score: float = Field(ge=0, le=1)
    class_observations: int = Field(ge=0)
    raw_category: str | None = Field(default=None, max_length=80)
    raw_confidence: float | None = Field(default=None, ge=0, le=1)
    class_evidence: dict[DetectorCategory, Annotated[float, Field(ge=0)]] = Field(default_factory=dict, max_length=4)
    status: Literal["counted", "suppressed"] = "counted"
    diagnostic_reasons: list[str] = Field(default_factory=list, max_length=32)
    configuration_id: str = Field(min_length=1, max_length=120)
    provenance: TrafficProvenance = "recorded_unverified"
    image_position: Point
    measured_speed_kmh: float | None = Field(default=None, ge=0, le=500)


class ZoneEvent(_TrafficModel):
    id: str = Field(default_factory=lambda: str(uuid4()), min_length=1, max_length=120)
    session_id: str = Field(min_length=1, max_length=240)
    source_id: str = Field(min_length=1, max_length=240)
    track_id: int = Field(ge=1)
    zone_id: str = Field(min_length=1, max_length=120)
    zone_label: str = Field(min_length=1, max_length=120)
    timestamp_s: float = Field(ge=0)
    kind: Literal["entry", "exit", "interrupted"]
    dwell_s: float | None = Field(default=None, ge=0)
    category: TrafficCategory = "unknown"
    configuration_id: str = Field(min_length=1, max_length=120)
    provenance: TrafficProvenance = "recorded_unverified"
    diagnostic_reasons: list[str] = Field(default_factory=list, max_length=32)
