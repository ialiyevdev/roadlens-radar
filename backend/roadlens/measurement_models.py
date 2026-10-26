"""Transport-independent records for observable measurement quality."""

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field


Point = tuple[float, float]
MeasurementState = Literal["waiting", "measuring", "completed", "rejected", "not_calibrated"]


class PositionSample(BaseModel):
    model_config = ConfigDict(allow_inf_nan=False)

    timestamp_s: float | None
    image_position: Point | None
    world_position: Point | None = None
    valid: bool
    reasons: list[str] = Field(default_factory=list)
    observation_gap_s: float | None = None
    region_margin_px: float | None = None
    contact_prediction_residual_px: float | None = None
    contact_prediction_residual_m: float | None = None
    association_ambiguous: bool = False
    overlap_fraction: float = 0.0
    bbox: tuple[float, float, float, float] | None = None
    detection_confidence: float | None = None
    quality_warnings: list[str] = Field(default_factory=list)
    tracking_diagnostics: list[str] = Field(default_factory=list)


class MeasurementDiagnostics(BaseModel):
    """Observed quantities, not confidence scores or empirical error bounds."""

    model_config = ConfigDict(allow_inf_nan=False)

    calibration_check_error_m: float | None = None
    calibration_fit_error_m: float | None = None
    calibration_coverage_fraction: float | None = None
    minimum_region_margin_px: float | None = None
    maximum_observation_gap_s: float | None = None
    maximum_contact_prediction_residual_px: float | None = None
    maximum_contact_prediction_residual_m: float | None = None
    gate_a_near_samples: int = 0
    gate_b_near_samples: int = 0
    near_gate_distance_m: float = 1.0
    gate_a_interpolation_interval_s: float | None = None
    gate_b_interpolation_interval_s: float | None = None
    ambiguous_observations: int = 0
    overlapping_box_observations: int = 0
    maximum_box_overlap_fraction: float = 0.0
    track_age_s: float | None = None
    gate_warnings: list[str] = Field(default_factory=list)
    calibration_warnings: list[str] = Field(default_factory=list)
    retained_position_samples: int = 0
    quality_observation_count: int = 0
    position_history_truncated: bool = False


class MeasurementResult(BaseModel):
    """Small polling record; retained sample evidence is exported on demand."""
    model_config = ConfigDict(allow_inf_nan=False)

    id: str
    track_id: int
    source_id: str
    session_id: str
    calibration_id: str | None
    category: str
    gate_a_timestamp_s: float | None = None
    gate_b_timestamp_s: float | None = None
    start_position: Point | None = None
    end_position: Point | None = None
    distance_m: float | None = None
    elapsed_seconds: float | None = None
    estimated_speed_kmh: float | None = None
    direction: Literal["A_to_B", "B_to_A", "unknown"] = "unknown"
    status: Literal["valid", "approximate", "rejected"]
    independently_validated: bool = False
    reasons: list[str] = Field(default_factory=list)
    sample_count: int = 0
    timestamp_s: float | None
    diagnostics: MeasurementDiagnostics = Field(default_factory=MeasurementDiagnostics)


class SpeedMeasurement(MeasurementResult):
    position_samples: list[PositionSample] = Field(default_factory=list)
    calibration_metadata: dict = Field(default_factory=dict)
