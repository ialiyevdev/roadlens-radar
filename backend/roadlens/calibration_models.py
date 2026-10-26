"""Measured road references and calibration diagnostics shared by the local API."""

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator


Point = tuple[float, float]
Segment = tuple[Point, Point]


class _CalibrationModel(BaseModel):
    model_config = ConfigDict(extra="forbid", allow_inf_nan=False, str_strip_whitespace=True)


class ImageGeometry(_CalibrationModel):
    width: int = Field(ge=2, le=16384)
    height: int = Field(ge=2, le=16384)
    rotation: Literal[0, 90, 180, 270] = 0
    mirrored: bool = False
    crop: tuple[int, int, int, int] | None = None
    coordinate_space: Literal["source", "undistorted"] = "source"
    intrinsic_profile_id: str | None = None

    @model_validator(mode="after")
    def valid_crop(self):
        if (self.coordinate_space == "undistorted") != bool(self.intrinsic_profile_id):
            raise ValueError("Undistorted coordinates require an intrinsic profile ID; source coordinates must not have one.")
        if self.crop is not None:
            x, y, width, height = self.crop
            if x < 0 or y < 0 or width < 2 or height < 2:
                raise ValueError("Crop must specify nonnegative x/y and positive width/height.")
        return self


class Correspondence(_CalibrationModel):
    image: Point
    world: Point


class CalibrationInput(_CalibrationModel):
    name: str = Field(min_length=1, max_length=120)
    source_id: str = Field(min_length=1, max_length=240)
    geometry: ImageGeometry
    points: list[Correspondence] = Field(max_length=100)
    check_points: list[Correspondence] = Field(default_factory=list, max_length=100)


class CalibrationDiagnostics(_CalibrationModel):
    valid: bool = False
    errors: list[str] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)
    homography: list[list[float]] | None = None
    region_image: list[Point] = Field(default_factory=list)
    grid_image: list[list[Point]] = Field(default_factory=list)
    inliers: list[bool] = Field(default_factory=list)
    coverage: float = 0.0
    fit_error_m: float | None = None
    fit_error_px: float | None = None
    check_error_m: float | None = None
    condition_number: float | None = None


class GateInput(_CalibrationModel):
    gate_a: Segment
    gate_b: Segment
    allow_reverse: bool = False


class GateDiagnostics(_CalibrationModel):
    valid: bool = False
    errors: list[str] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)
    gate_a: Segment
    gate_b: Segment
    world_a: Segment | None = None
    world_b: Segment | None = None
    allow_reverse: bool = False


class CalibrationProfile(CalibrationInput):
    id: str
    diagnostics: CalibrationDiagnostics
    gates: GateInput | None = None
