"""Bounded, explicit contracts for independent reference-speed comparisons."""

from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field, StringConstraints, model_validator


Identifier = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=160)]
Speed = Annotated[float, Field(ge=0, le=10000)]
Timestamp = Annotated[float, Field(ge=0)]


class ValidationRecord(BaseModel):
    model_config = ConfigDict(extra="forbid", allow_inf_nan=False)

    recording_id: Identifier
    observation_id: Identifier
    measurement_id: Identifier
    vehicle_id: Identifier | None = None
    estimated_speed_kmh: Speed | None = None
    reference_speed_kmh: Speed | None = None
    reference_method: Annotated[str, StringConstraints(strip_whitespace=True, max_length=500)] | None = None
    reference_independent: bool = Field(default=False, strict=True)
    reference_recording_id: Identifier | None = None
    reference_observation_id: Identifier | None = None
    reference_measurement_id: Identifier | None = None
    association: Literal["matched", "ambiguous", "unmatched", "mismatched"] = "unmatched"
    status: Literal["valid", "approximate", "rejected"]
    calibration_id: Identifier | None = None
    direction: Literal["A_to_B", "B_to_A", "unknown"] = "unknown"
    timestamp_s: Timestamp | None = None
    reference_timestamp_s: Timestamp | None = None
    reference_interval_start_s: Timestamp | None = None
    reference_interval_end_s: Timestamp | None = None
    diagnostics: dict[str, str | float | bool | None] = Field(default_factory=dict, max_length=100)

    @model_validator(mode="after")
    def valid_interval(self):
        start, end = self.reference_interval_start_s, self.reference_interval_end_s
        if (start is None) != (end is None):
            raise ValueError("Supply both reference interval endpoints, or neither.")
        if start is not None and end <= start:
            raise ValueError("Reference interval end must be after its start.")
        if any(len(key) > 160 or (isinstance(value, str) and len(value) > 2000)
               for key, value in self.diagnostics.items()):
            raise ValueError("Diagnostic keys or values exceed the permitted length.")
        return self


class ValidationDataset(BaseModel):
    model_config = ConfigDict(extra="forbid", allow_inf_nan=False)

    name: Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=160)]
    provenance: Literal["synthetic", "real_world"]
    description: str = Field(default="", max_length=4000)
    records: list[ValidationRecord] = Field(default_factory=list, max_length=10000)

    @model_validator(mode="after")
    def unique_events(self):
        measurements, observations = set(), set()
        for record in self.records:
            measurement = (record.recording_id, record.measurement_id)
            observation = (record.recording_id, record.observation_id)
            if measurement in measurements:
                raise ValueError(f"Duplicate measurement ID in recording: {measurement!r}.")
            if observation in observations:
                raise ValueError(f"Duplicate observation event in recording: {observation!r}.")
            measurements.add(measurement)
            observations.add(observation)
        return self


class ValidationOptions(BaseModel):
    model_config = ConfigDict(extra="forbid", allow_inf_nan=False)

    tolerance_bands_kmh: list[Annotated[float, Field(ge=0, le=1000)]] = Field(
        default_factory=lambda: [3.0, 5.0], min_length=1, max_length=10)
    minimum_group_samples: int = Field(default=3, ge=3, le=10000)

    @model_validator(mode="after")
    def unique_tolerances(self):
        if len(set(self.tolerance_bands_kmh)) != len(self.tolerance_bands_kmh):
            raise ValueError("Tolerance bands must be unique.")
        return self


class EvaluationRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    dataset: ValidationDataset
    options: ValidationOptions = Field(default_factory=ValidationOptions)


class ToleranceResult(BaseModel):
    tolerance_kmh: float
    within_count: int
    within_percent: float | None


class MetricSummary(BaseModel):
    n: int
    sufficient_sample: bool
    mae_kmh: float | None = None
    rmse_kmh: float | None = None
    bias_kmh: float | None = None
    median_absolute_error_kmh: float | None = None
    p90_absolute_error_kmh: float | None = None
    mape_percent: float | None = None
    percentage_sample_count: int = 0
    tolerance_bands: list[ToleranceResult]


class ValidationRow(BaseModel):
    record: ValidationRecord
    reference_matched: bool
    comparison_included: bool
    error_kmh: float | None = None
    absolute_error_kmh: float | None = None
    absolute_percentage_error_percent: float | None = None
    exclusion_reasons: list[str] = Field(default_factory=list)


class ValidationGroup(BaseModel):
    id: str
    label: str
    metrics: MetricSummary


class ValidationReport(BaseModel):
    dataset_name: str
    provenance: Literal["synthetic", "real_world"]
    description: str
    evaluation_version: Literal["1"] = "1"
    total_records: int
    reference_matched_count: int
    compared_count: int
    rejected_count: int
    completed_count: int
    rejection_rate_percent: float | None
    completion_rate_percent: float | None
    summary: MetricSummary
    groups: list[ValidationGroup]
    rows: list[ValidationRow]
    options: ValidationOptions
    limitations: list[str]
