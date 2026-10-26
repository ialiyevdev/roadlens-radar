"""Checkerboard fitting and cached, same-size OpenCV undistortion."""

import hashlib
from uuid import uuid4

import cv2
import numpy as np

from .calibration_models import ImageGeometry
from .camera_models import CalibrationImageResult, CameraCalibrationInput, CameraIntrinsicProfile

MAX_IMAGE_BYTES = 8 * 1024 * 1024
MAX_TOTAL_BYTES = 64 * 1024 * 1024
MAX_IMAGES = 40


def checkerboard_object_points(configuration: CameraCalibrationInput) -> np.ndarray:
    board = configuration.checkerboard
    points = np.zeros((board.inner_columns * board.inner_rows, 3), np.float32)
    points[:, :2] = np.mgrid[:board.inner_columns, :board.inner_rows].T.reshape(-1, 2)
    return points * board.square_size_mm


def fit_camera(corners: list[np.ndarray], size: tuple[int, int], configuration: CameraCalibrationInput,
               images: list[CalibrationImageResult] | None = None,
               provenance: str = "checkerboard_images") -> CameraIntrinsicProfile:
    """Fit observed target corners; no images, footage, or extrinsics are retained."""
    if not 6 <= len(corners) <= MAX_IMAGES:
        raise ValueError("Use at least six distinct, well-spread checkerboard views (ten or more recommended).")
    object_points = checkerboard_object_points(configuration)
    points = [np.asarray(value, np.float32).reshape(-1, 1, 2) for value in corners]
    if any(len(value) != len(object_points) or not np.isfinite(value).all() for value in points):
        raise ValueError("Checkerboard corner arrays are invalid.")
    width, height = size
    if width < 2 or height < 2 or width > 16384 or height > 16384:
        raise ValueError("Unsupported calibration image dimensions.")
    normalized = [value.reshape(-1, 2) / np.array(size) for value in points]
    centroids = np.array([value.mean(axis=0) for value in normalized])
    scales = np.array([np.linalg.norm(value.max(axis=0)-value.min(axis=0)) for value in normalized])
    angles = np.unwrap([np.arctan2(*(value[configuration.checkerboard.inner_columns-1]-value[0])[::-1])
                        for value in normalized])
    if np.ptp(centroids, axis=0).max() < .05 and np.ptp(angles) < .12 and scales.max() < scales.min()*1.2:
        raise ValueError("Checkerboard views lack pose diversity. Move and tilt the target across the frame.")
    try:
        rms, matrix, distortion, rotations, translations = cv2.calibrateCamera(
            [object_points] * len(points), points, size, None, None,
            criteria=(cv2.TERM_CRITERIA_EPS + cv2.TERM_CRITERIA_MAX_ITER, 100, 1e-9),
        )
    except cv2.error as error:
        raise ValueError("OpenCV could not fit a stable camera model. Review target dimensions and views.") from error
    errors = []
    for observed, rotation, translation in zip(points, rotations, translations):
        projected, _ = cv2.projectPoints(object_points, rotation, translation, matrix, distortion)
        errors.append(float(np.sqrt(np.mean(np.sum((observed-projected)**2, axis=2)))))
    warnings = ["Reprojection residuals describe target fitting; they do not establish speed accuracy.",
                "Reconfirm lens, zoom, focus, crop, rotation, mirroring and resolution before reuse."]
    if len(points) < 10:
        warnings.append("Fewer than ten usable target views: collect more diverse views before field use.")
    if np.ptp(centroids, axis=0).min() < .15:
        warnings.append("Target centers have limited frame coverage. Add views near all image edges.")
    if max(errors) > 1:
        warnings.append("Some target views exceed 1 px reprojection RMS. Inspect blur, board flatness and corners.")
    if max(errors) > 3:
        warnings.append("High reprojection residuals: this model requires investigation before measurement.")
    diagnostics = [image.model_copy(deep=True) for image in images or []]
    error_index = 0
    for image in diagnostics:
        if image.accepted:
            image.reprojection_error_px = errors[error_index]
            error_index += 1
    return CameraIntrinsicProfile(
        **configuration.model_dump(), id=str(uuid4()), width=width, height=height,
        camera_matrix=matrix.tolist(), distortion_coefficients=distortion.reshape(-1).tolist(),
        rms_reprojection_error_px=float(rms), per_image_error_px=errors,
        used_image_count=len(points), rejected_image_count=sum(not image.accepted for image in diagnostics),
        images=diagnostics, warnings=warnings, provenance=provenance,
    )


def calibrate_camera(images: list[tuple[str, bytes]], configuration: CameraCalibrationInput) -> CameraIntrinsicProfile:
    if not 6 <= len(images) <= MAX_IMAGES:
        raise ValueError("Upload between six and forty checkerboard images.")
    if any(not content or len(content) > MAX_IMAGE_BYTES for _, content in images):
        raise ValueError("Each calibration image must be nonempty and at most 8 MiB.")
    if sum(len(content) for _, content in images) > MAX_TOTAL_BYTES:
        raise ValueError("The calibration image set exceeds 64 MiB.")
    board = configuration.checkerboard
    size = None
    seen = set()
    corners = []
    diagnostics = []
    for filename, content in images:
        digest = hashlib.sha256(content).hexdigest()
        label = "".join(c for c in filename.replace("\\", "/").rsplit("/", 1)[-1] if c.isprintable())[:160]
        result = CalibrationImageResult(filename=label, sha256=digest, accepted=False, reason="")
        diagnostics.append(result)
        gray = cv2.imdecode(np.frombuffer(content, np.uint8), cv2.IMREAD_GRAYSCALE)
        if gray is None:
            result.reason = "Image could not be decoded."
            continue
        current_size = (gray.shape[1], gray.shape[0])
        if min(current_size) < 64 or max(current_size) > 4096 or gray.size > 12_000_000:
            result.reason = "Use images between 64 px and 4096 px per side, at most 12 megapixels."
            continue
        decoded_hash = hashlib.sha256(gray.tobytes()).hexdigest()
        if decoded_hash in seen:
            result.reason = "Duplicate image."
            continue
        seen.add(decoded_hash)
        if size is not None and current_size != size:
            result.reason = "Image resolution differs from the first usable input."
            continue
        found, observed = cv2.findChessboardCornersSB(
            gray, (board.inner_columns, board.inner_rows), flags=cv2.CALIB_CB_NORMALIZE_IMAGE)
        if not found:
            found, observed = cv2.findChessboardCorners(
                gray, (board.inner_columns, board.inner_rows),
                flags=cv2.CALIB_CB_ADAPTIVE_THRESH | cv2.CALIB_CB_NORMALIZE_IMAGE | cv2.CALIB_CB_FAST_CHECK)
            if found:
                observed = cv2.cornerSubPix(gray, observed, (5, 5), (-1, -1),
                                            (cv2.TERM_CRITERIA_EPS + cv2.TERM_CRITERIA_MAX_ITER, 40, .001))
        if not found:
            result.reason = "Checkerboard inner corners not found."
            continue
        area = float(cv2.contourArea(cv2.convexHull(observed))) / gray.size
        result.coverage = area
        if area < .01:
            result.reason = "Target covers less than 1% of the image. Move it closer."
            continue
        normalized = observed.reshape(-1, 2) / np.array(current_size)
        if any(np.sqrt(np.mean((normalized-previous.reshape(-1, 2)/np.array(size))**2)) < .008
               for previous in corners):
            result.reason = "Near-duplicate target pose."
            continue
        corners.append(observed)
        if size is None:
            size = current_size
        result.accepted = True
        result.reason = "Checkerboard corners detected."
    if len(corners) < 6:
        reasons = "; ".join(f"{item.filename}: {item.reason}" for item in diagnostics if not item.accepted)
        raise ValueError(f"Only {len(corners)} usable checkerboard views; at least six are required. {reasons}")
    return fit_camera(corners, size, configuration, diagnostics)


class FrameUndistorter:
    """Maps are computed once; every downstream coordinate is in the corrected frame."""

    def __init__(self, profile: CameraIntrinsicProfile):
        self.profile = CameraIntrinsicProfile.model_validate(profile.model_dump())
        self.geometry = self.profile.geometry
        self.source_geometry = ImageGeometry(width=profile.width, height=profile.height,
                                              rotation=profile.rotation, mirrored=profile.mirrored, crop=profile.crop)
        self._matrix = np.asarray(profile.camera_matrix, np.float64)
        self._distortion = np.asarray(profile.distortion_coefficients, np.float64)
        self._maps = cv2.initUndistortRectifyMap(self._matrix, self._distortion, None, self._matrix,
                                              (profile.width, profile.height), cv2.CV_32FC1)
        if not all(np.isfinite(mapping).all() for mapping in self._maps):
            raise ValueError("Camera model generated nonfinite correction maps.")

    def apply(self, image: np.ndarray) -> np.ndarray:
        if image.ndim not in (2, 3) or image.shape[:2] != (self.profile.height, self.profile.width):
            raise ValueError("Camera model resolution changed. Disable correction and recheck camera geometry.")
        return cv2.remap(image, self._maps[0], self._maps[1], cv2.INTER_LINEAR, borderMode=cv2.BORDER_CONSTANT)

    def undistort_points(self, points: list[tuple[float, float]]) -> list[tuple[float, float]]:
        if not points:
            return []
        values = np.asarray(points, np.float64)
        if values.shape != (len(points), 2) or not np.isfinite(values).all():
            raise ValueError("Image points must be finite x/y pairs.")
        corrected = cv2.undistortPointsIter(values.reshape(-1, 1, 2), self._matrix, self._distortion,
                                           None, self._matrix,
                                           (cv2.TERM_CRITERIA_EPS + cv2.TERM_CRITERIA_MAX_ITER, 50, 1e-10))
        return [tuple(point) for point in corrected.reshape(-1, 2)]
