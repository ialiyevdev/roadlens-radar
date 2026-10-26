"""Optional pinhole lens models, independent of road-plane calibration."""

import math
from typing import Literal
from uuid import UUID

import numpy as np
from pydantic import BaseModel, ConfigDict, Field, model_validator

from .calibration_models import ImageGeometry


class CameraModel(BaseModel):
    model_config = ConfigDict(extra="forbid", allow_inf_nan=False, str_strip_whitespace=True)


class CameraMetadata(CameraModel):
    camera: str = Field(default="", max_length=200)
    lens: str = Field(default="", max_length=200)
    zoom: str = Field(default="", max_length=100)
    focus: str = Field(default="", max_length=100)
    notes: str = Field(default="", max_length=2000)


class Checkerboard(CameraModel):
    inner_columns: int = Field(default=9, ge=3, le=20)
    inner_rows: int = Field(default=6, ge=3, le=20)
    square_size_mm: float = Field(default=25, gt=0, le=1000)


class CameraCalibrationInput(CameraModel):
    name: str = Field(min_length=1, max_length=120)
    camera_configuration_id: str = Field(min_length=1, max_length=200)
    checkerboard: Checkerboard = Field(default_factory=Checkerboard)
    metadata: CameraMetadata = Field(default_factory=CameraMetadata)
    rotation: Literal[0, 90, 180, 270] = 0
    mirrored: bool = False
    crop: tuple[int, int, int, int] | None = None

    @model_validator(mode="after")
    def crop_valid(self):
        if self.crop is not None and (self.crop[0] < 0 or self.crop[1] < 0 or self.crop[2] < 2 or self.crop[3] < 2):
            raise ValueError("Invalid camera crop metadata.")
        return self


class CalibrationImageResult(CameraModel):
    filename: str = Field(max_length=160)
    sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    accepted: bool
    reason: str = Field(max_length=300)
    coverage: float | None = Field(default=None, ge=0, le=1)
    reprojection_error_px: float | None = Field(default=None, ge=0)


class CameraIntrinsicProfile(CameraCalibrationInput):
    id: str
    width: int = Field(ge=2, le=16384)
    height: int = Field(ge=2, le=16384)
    model: Literal["opencv_pinhole"] = "opencv_pinhole"
    camera_matrix: list[list[float]]
    distortion_coefficients: list[float] = Field(min_length=5, max_length=8)
    rms_reprojection_error_px: float = Field(ge=0)
    per_image_error_px: list[float] = Field(min_length=6, max_length=40)
    used_image_count: int = Field(ge=6, le=40)
    rejected_image_count: int = Field(ge=0, le=40)
    images: list[CalibrationImageResult] = Field(default_factory=list, max_length=40)
    warnings: list[str] = Field(default_factory=list, max_length=100)
    pixel_coordinate_policy: Literal["same_size_same_K_no_crop"] = "same_size_same_K_no_crop"
    provenance: Literal["checkerboard_images", "imported", "synthetic"] = "checkerboard_images"

    @model_validator(mode="after")
    def physically_valid(self):
        try:
            identifier = UUID(self.id)
        except (ValueError, TypeError) as error:
            raise ValueError("Camera profile ID must be a UUID.") from error
        if str(identifier) != self.id:
            raise ValueError("Camera profile ID must use canonical lowercase UUID format.")
        if len(self.camera_matrix) != 3 or any(len(row) != 3 for row in self.camera_matrix):
            raise ValueError("Camera matrix must be 3 by 3.")
        k = np.asarray(self.camera_matrix, dtype=np.float64)
        if not np.isfinite(k).all() or not np.allclose(k[2], [0, 0, 1], atol=1e-10):
            raise ValueError("Camera matrix requires finite values and last row [0, 0, 1].")
        if abs(k[0, 1]) > 1e-10 or abs(k[1, 0]) > 1e-10:
            raise ValueError("The OpenCV pinhole model requires zero skew.")
        scale = max(self.width, self.height)
        if not all(.05 * scale <= value <= 100 * scale for value in (k[0, 0], k[1, 1])):
            raise ValueError("Camera focal lengths must be positive and within a supported range.")
        if not (0 <= k[0, 2] < self.width and 0 <= k[1, 2] < self.height):
            raise ValueError("Camera principal point must be inside the calibrated image.")
        d = self.distortion_coefficients
        if len(d) not in (5, 8) or not all(math.isfinite(v) and abs(v) <= 10 for v in d):
            raise ValueError("Use five or eight finite OpenCV distortion coefficients within the supported range.")
        if abs(d[2]) > 1 or abs(d[3]) > 1:
            raise ValueError("Tangential distortion coefficients are outside the supported range.")
        # Reject rational denominator poles within the calibrated image domain.
        radius2 = max(((x-k[0, 2])/k[0, 0])**2 + ((y-k[1, 2])/k[1, 1])**2
                      for x in (0, self.width-1) for y in (0, self.height-1))
        r2 = np.linspace(0, radius2 * 1.25, 200)
        numerator = 1 + d[0]*r2 + d[1]*r2**2 + d[4]*r2**3
        denominator = np.ones_like(r2) if len(d) == 5 else 1 + d[5]*r2 + d[6]*r2**2 + d[7]*r2**3
        if np.any(denominator <= .1) or np.any(numerator <= .05):
            raise ValueError("Distortion model is singular or folds within the calibrated image domain.")
        radial = np.sqrt(r2) * numerator / denominator
        if np.any(np.diff(radial) <= 0):
            raise ValueError("Distortion model folds within the calibrated image domain.")
        if len(self.per_image_error_px) != self.used_image_count or any(v < 0 for v in self.per_image_error_px):
            raise ValueError("Per-image errors must match the used-image count and be nonnegative.")
        if self.used_image_count + self.rejected_image_count > 40:
            raise ValueError("Camera target sets are limited to forty images.")
        if self.images and (len(self.images) != self.used_image_count + self.rejected_image_count
                            or sum(image.accepted for image in self.images) != self.used_image_count):
            raise ValueError("Image diagnostics must agree with accepted and rejected counts.")
        return self

    @property
    def geometry(self) -> ImageGeometry:
        return ImageGeometry(width=self.width, height=self.height, rotation=self.rotation,
                             mirrored=self.mirrored, crop=self.crop, coordinate_space="undistorted",
                             intrinsic_profile_id=self.id)
