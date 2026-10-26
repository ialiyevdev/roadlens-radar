"""Portable field observations, independent references and explicit matching decisions."""

import math
from datetime import datetime, timezone
from pathlib import PurePosixPath, PureWindowsPath
from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field, StringConstraints, model_validator

from .calibration_models import GateInput, ImageGeometry
from .measurement_models import MeasurementResult
from .validation_models import ValidationOptions


Identifier = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=160)]
Text = Annotated[str, StringConstraints(max_length=4000)]
Partition = Literal["development", "calibration", "held_out"]
Provenance = Literal["synthetic", "recorded_unverified", "independent_reference"]


class FieldModel(BaseModel):
    model_config = ConfigDict(extra="forbid", allow_inf_nan=False, str_strip_whitespace=True)


class FieldSource(FieldModel):
    source_id: Identifier
    video_id: Identifier | None = None
    relative_path: str | None = Field(default=None, max_length=500)
    content_sha256: str | None = Field(default=None, pattern=r"^[a-fA-F0-9]{64}$")
    segment_start_s: float | None = Field(default=None, ge=0)
    segment_end_s: float | None = Field(default=None, ge=0)
    collection_id: Identifier | None = None
    near_duplicate_group: Identifier | None = None

    @model_validator(mode="after")
    def local_reference(self):
        if self.relative_path:
            value = self.relative_path.replace("\\", "/")
            path = PurePosixPath(value)
            if path.is_absolute() or PureWindowsPath(value).drive or ".." in path.parts:
                raise ValueError("Source paths must be relative without parent traversal.")
            self.relative_path = str(path)
        start, end = self.segment_start_s, self.segment_end_s
        if (start is None) != (end is None) or (start is not None and end <= start):
            raise ValueError("Supply both segment endpoints with end after start, or neither.")
        if self.content_sha256:
            self.content_sha256 = self.content_sha256.lower()
        return self


class FieldCamera(FieldModel):
    configuration_id: Identifier = "unspecified"
    geometry: ImageGeometry
    intrinsic_profile_id: Identifier | None = None
    lens_model: str | None = Field(default=None, max_length=160)
    zoom: str | None = Field(default=None, max_length=160)
    notes: Text = ""
    detector_input_size: int | None = Field(default=None, ge=1, le=16384)
    detector_confidence: float | None = Field(default=None, ge=0, le=1)
    tracker: Identifier = "global_motion"

    @model_validator(mode="after")
    def coordinate_model(self):
        if self.intrinsic_profile_id != self.geometry.intrinsic_profile_id:
            raise ValueError("Field camera and image geometry must use the same intrinsic profile and coordinate space.")
        return self


class FieldMeasurement(FieldModel):
    event_id: Identifier
    variant: Literal["original", "baseline", "improved"] = "original"
    measurement: MeasurementResult


class ReferenceEvent(FieldModel):
    id: Identifier
    timestamp_s: float
    interval_end_s: float | None = None
    speed: float = Field(ge=0, le=10000)
    units: Literal["km/h", "m/s", "mph"] = "km/h"
    method: str = Field(min_length=1, max_length=500)
    provenance: Provenance = "recorded_unverified"
    independent: bool = Field(default=False, strict=True)
    instrument_id: Identifier | None = None
    uncertainty_kmh: float | None = Field(default=None, ge=0, le=10000)
    quality_notes: Text = ""

    @model_validator(mode="after")
    def reference_constraints(self):
        if self.interval_end_s is not None and self.interval_end_s <= self.timestamp_s:
            raise ValueError("Reference interval end must follow its timestamp.")
        text = self.method.casefold()
        if any(term in text for term in ("roadlens", "self-reference", "self reference", "same estimate")):
            raise ValueError("RoadLens-derived speeds cannot be independent reference events.")
        if self.speed_kmh > 10000:
            raise ValueError("Converted reference speed exceeds the supported range.")
        return self

    @property
    def speed_kmh(self) -> float:
        return self.speed * {"km/h": 1.0, "m/s": 3.6, "mph": 1.609344}[self.units]


class SyncAnchor(FieldModel):
    reference_timestamp_s: float
    source_timestamp_s: float = Field(ge=0)
    uncertainty_s: float | None = Field(default=None, ge=0)
    independent: bool = Field(default=False, strict=True)
    description: str = Field(default="", max_length=500)


class SyncConfig(FieldModel):
    source_clock: str = Field(default="", max_length=500)
    reference_clock: str = Field(default="", max_length=500)
    offset_s: float = 0
    fit_drift: bool = False
    anchors: list[SyncAnchor] = Field(default_factory=list, max_length=100)
    uncertainty_s: float | None = Field(default=None, ge=0)
    maximum_alignment_error_s: float = Field(default=0.25, gt=0, le=60)
    notes: Text = ""

    @model_validator(mode="after")
    def unique_anchors(self):
        times = [anchor.reference_timestamp_s for anchor in self.anchors]
        if len(set(times)) != len(times):
            raise ValueError("Synchronization anchors need distinct reference timestamps.")
        if self.fit_drift and (len(self.anchors) < 2 or not all(a.independent for a in self.anchors)):
            raise ValueError("Clock-drift fitting requires at least two independent synchronization anchors.")
        return self


class SyncDiagnostics(FieldModel):
    status: Literal["unconfigured", "uncertain", "aligned"] = "unconfigured"
    offset_s: float = 0
    scale: float = 1
    drift_ppm: float = 0
    anchor_count: int = 0
    anchor_span_s: float = 0
    residuals_s: list[float] = Field(default_factory=list)
    maximum_residual_s: float | None = None
    uncertainty_bound_s: float | None = None
    warnings: list[str] = Field(default_factory=list)


class EventMatch(FieldModel):
    event_id: Identifier
    reference_id: Identifier | None = None
    association: Literal["matched", "ambiguous", "unmatched"] = "unmatched"
    method: str = Field(default="", max_length=500)
    quality_notes: Text = ""
    correspondence_confirmed: bool = Field(default=False, strict=True)

    @model_validator(mode="after")
    def matched_reference(self):
        if self.association == "matched" and self.reference_id is None:
            raise ValueError("A matched event needs an explicit reference identifier.")
        return self


def _finite_json(value):
    if isinstance(value, float) and not math.isfinite(value):
        raise ValueError("Metadata must contain finite numbers.")
    if isinstance(value, dict):
        for key, item in value.items():
            if len(str(key)) > 160:
                raise ValueError("Metadata keys are limited to 160 characters.")
            _finite_json(item)
    elif isinstance(value, list):
        for item in value:
            _finite_json(item)


class FieldSessionInput(FieldModel):
    name: str = Field(min_length=1, max_length=160)
    description: Text = ""
    source: FieldSource
    camera: FieldCamera
    calibration_id: Identifier | None = None
    calibration_compatible: bool = True
    configuration_warnings: list[Annotated[str, StringConstraints(max_length=1000)]] = Field(default_factory=list, max_length=100)
    calibration_metadata: dict = Field(default_factory=dict, max_length=10)
    gates: GateInput | None = None
    started_at: datetime | None = None
    ended_at: datetime | None = None
    source_timebase: str = Field(default="", max_length=500)
    timing_summary: dict = Field(default_factory=dict, max_length=100)
    environment_notes: Text = ""
    environment_condition: str = Field(default="unspecified", max_length=160)
    reference_description: Text = ""
    validation_dataset_id: Identifier | None = None
    provenance: Provenance = "recorded_unverified"
    status: Literal["draft", "collecting", "ready", "evaluated"] = "draft"
    partition: Partition = "development"
    measurements: list[FieldMeasurement] = Field(default_factory=list, max_length=10000)
    reference_events: list[ReferenceEvent] = Field(default_factory=list, max_length=10000)
    sync: SyncConfig = Field(default_factory=SyncConfig)
    matches: list[EventMatch] = Field(default_factory=list, max_length=10000)
    expected_event_count: int | None = Field(default=None, ge=0, le=1000000)

    @model_validator(mode="after")
    def consistent_session(self):
        for stamp in (self.started_at, self.ended_at):
            if stamp is not None and (stamp.tzinfo is None or stamp.utcoffset() is None):
                raise ValueError("Session wall-clock metadata needs an explicit timezone.")
        if self.started_at and self.ended_at and self.ended_at < self.started_at:
            raise ValueError("Session end cannot precede its start.")
        keys = [(item.event_id, item.variant) for item in self.measurements]
        ids = [item.measurement.id for item in self.measurements]
        if len(set(keys)) != len(keys) or len(set(ids)) != len(ids):
            raise ValueError("Measurement IDs and event/variant pairs must be unique within a session.")
        ref_ids = [item.id for item in self.reference_events]
        if len(set(ref_ids)) != len(ref_ids):
            raise ValueError("Reference event IDs must be unique within a session.")
        events = {item.event_id for item in self.measurements}
        match_events = [item.event_id for item in self.matches]
        if len(set(match_events)) != len(match_events):
            raise ValueError("Store one matching decision per event.")
        used = set()
        for match in self.matches:
            if match.event_id not in events:
                raise ValueError("Matching decisions must refer to a retained measurement event.")
            if match.reference_id is not None and match.reference_id not in ref_ids:
                raise ValueError("Matching decisions must refer to a retained reference event.")
            if match.association == "matched":
                if match.reference_id in used:
                    raise ValueError("One reference event cannot be matched to multiple vehicle events.")
                used.add(match.reference_id)
        if self.expected_event_count is not None and self.expected_event_count < len(events):
            raise ValueError("Expected event count cannot be smaller than retained vehicle events.")
        _finite_json(self.timing_summary)
        _finite_json(self.calibration_metadata)
        return self


class FieldSession(FieldSessionInput):
    id: Identifier
    created_at: datetime
    updated_at: datetime
    sync_diagnostics: SyncDiagnostics = Field(default_factory=SyncDiagnostics)


class FromObservation(FieldModel):
    name: str = Field(min_length=1, max_length=160)
    partition: Partition = "development"
    provenance: Provenance = "recorded_unverified"
    environment_notes: Text = ""
    reference_description: Text = ""


class FieldEvaluationRequest(FieldModel):
    session_ids: list[Identifier] = Field(min_length=1, max_length=200)
    partition: Partition | None = "held_out"
    variant: Literal["original", "baseline", "improved"] = "original"
    options: ValidationOptions = Field(default_factory=ValidationOptions)
    description: Text = ""


def utc_now():
    return datetime.now(timezone.utc)
