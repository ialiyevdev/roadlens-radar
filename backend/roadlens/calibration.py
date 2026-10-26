"""Road-plane homography validation. No metric scale is inferred from the image."""

from math import ceil, floor, log10

import cv2
import numpy as np

from .calibration_models import (
    CalibrationDiagnostics, CalibrationInput, GateDiagnostics, GateInput,
    ImageGeometry, Point, Segment,
)


# findHomography uses destination units: the destination here is measured meters.
RANSAC_THRESHOLD_M = 0.25
MIN_COVERAGE = 0.005


def _points(items, key: str) -> np.ndarray:
    return np.asarray([getattr(item, key) for item in items], dtype=np.float64).reshape(-1, 2)


def _hull(points: np.ndarray) -> np.ndarray:
    # Shift the origin before float32 conversion to retain local metric precision.
    origin = points[0]
    indices = cv2.convexHull((points - origin).astype(np.float32), returnPoints=False).ravel()
    return points[indices]


def _area(polygon: np.ndarray) -> float:
    shifted = polygon - polygon[0]
    return abs(float(np.sum(shifted[:, 0] * np.roll(shifted[:, 1], -1)
                            - shifted[:, 1] * np.roll(shifted[:, 0], -1)))) / 2


def _normalized(points: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
    center = points.mean(axis=0)
    centered = points - center
    scale = np.sqrt(2) / np.sqrt(np.mean(np.sum(centered * centered, axis=1)))
    matrix = np.array([[scale, 0, -scale * center[0]], [0, scale, -scale * center[1]], [0, 0, 1]])
    return centered * scale, matrix


def _design_condition(image: np.ndarray, world: np.ndarray) -> tuple[float, np.ndarray, np.ndarray]:
    source, source_norm = _normalized(image)
    target, target_norm = _normalized(world)
    rows = []
    for (x, y), (u, v) in zip(source, target):
        rows.extend(([-x, -y, -1, 0, 0, 0, u * x, u * y, u],
                     [0, 0, 0, -x, -y, -1, v * x, v * y, v]))
    singular = np.linalg.svd(rows, compute_uv=False)
    # For >4 points the final value represents the homography's null space.
    denominator = singular[-1] if len(image) == 4 else singular[-2]
    condition = float(singular[0] / max(denominator, np.finfo(float).eps))
    return condition, source_norm, target_norm


def _project_many(matrix: np.ndarray, points: np.ndarray) -> np.ndarray | None:
    homogeneous = np.column_stack((points, np.ones(len(points)))) @ matrix.T
    denominator = homogeneous[:, 2]
    scale = np.linalg.norm(matrix[2]) * np.linalg.norm(np.column_stack((points, np.ones(len(points)))), axis=1)
    if not np.isfinite(homogeneous).all() or np.any(np.abs(denominator) <= 1e-10 * scale):
        return None
    result = homogeneous[:, :2] / denominator[:, None]
    return result if np.isfinite(result).all() else None


def _spread_error(points: np.ndarray, label: str) -> str | None:
    if len(np.unique(points, axis=0)) != len(points):
        return f"{label} reference points contain duplicates."
    singular = np.linalg.svd(points - points.mean(axis=0), compute_uv=False)
    if singular[0] < 1e-9 or singular[1] / singular[0] < 0.01:
        return f"{label} reference points are collinear or nearly collinear; spread them across the road."
    return None


def _inside(point: Point, polygon: np.ndarray) -> bool:
    origin = polygon[0]
    local = (polygon - origin).astype(np.float32)
    return cv2.pointPolygonTest(local, tuple(np.asarray(point) - origin), True) >= -1e-5


def _grid(matrix_inverse: np.ndarray, world_region: np.ndarray, image_region: np.ndarray) -> list[list[Point]]:
    minimum, maximum = world_region.min(axis=0), world_region.max(axis=0)
    span = float(max(maximum - minimum))
    base = 10 ** floor(log10(span / 8))
    step = next(value * base for value in (1, 2, 5, 10) if value * base >= span / 8)
    result = []
    # Clip metric grid lines to the convex measurement region before projection.
    for axis in (0, 1):
        other = 1 - axis
        for index in range(ceil(minimum[axis] / step), floor(maximum[axis] / step) + 1):
            coordinate = index * step
            intersections = []
            for start, end in zip(world_region, np.roll(world_region, -1, axis=0)):
                delta = end[axis] - start[axis]
                if abs(delta) < 1e-10:
                    if abs(start[axis] - coordinate) < 1e-8:
                        intersections.extend((start, end))
                    continue
                fraction = (coordinate - start[axis]) / delta
                if -1e-8 <= fraction <= 1 + 1e-8:
                    intersections.append(start + fraction * (end - start))
            if len(intersections) < 2:
                continue
            ordered = sorted(intersections, key=lambda point: point[other])
            line = _project_many(matrix_inverse, np.asarray([ordered[0], ordered[-1]]))
            if line is not None and np.linalg.norm(line[-1] - line[0]) > 1e-5:
                if all(_inside(tuple(point), image_region) for point in line):
                    result.append([tuple(point) for point in line])
    return result


def validate_calibration(data: CalibrationInput) -> CalibrationDiagnostics:
    """Fit only reference points; independent check points never influence the fit."""
    result = CalibrationDiagnostics()
    if len(data.points) < 4:
        result.errors.append("At least four measured image/world reference pairs are required.")
        return result
    image, world = _points(data.points, "image"), _points(data.points, "world")
    checks_image, checks_world = _points(data.check_points, "image"), _points(data.check_points, "world")
    if not all(np.isfinite(points).all() for points in (image, world, checks_image, checks_world)):
        result.errors.append("All image and measured world coordinates must be finite.")
        return result
    for points, label in ((image, "Image"), (world, "World")):
        error = _spread_error(points, label)
        if error:
            result.errors.append(error)
    for points in (image, checks_image):
        if len(points) and (np.any(points < 0) or np.any(points[:, 0] > data.geometry.width - 1)
                            or np.any(points[:, 1] > data.geometry.height - 1)):
            result.errors.append("Reference and check points must lie inside the source image dimensions.")
            break
    if np.max(np.abs(world)) > 1e7 or (len(checks_world) and np.max(np.abs(checks_world)) > 1e7):
        result.errors.append("Use local measured meter coordinates with an origin near the roadway.")
    if np.ptp(world, axis=0).max() < 0.01:
        result.errors.append("Measured reference points have insufficient physical spread.")
    for check in checks_image:
        if np.any(np.linalg.norm(image - check, axis=1) < 1e-6):
            result.errors.append("Independent check points must differ from the points used to fit calibration.")
            break
    if result.errors:
        return result

    try:
        method = cv2.RANSAC if len(image) > 4 else 0
        # OpenCV's fitting path uses float32 points. Center meter coordinates so
        # a large user-selected origin cannot erase local roadway precision.
        origin = world.mean(axis=0)
        matrix, mask = cv2.findHomography(image, world - origin, method, RANSAC_THRESHOLD_M,
                                          maxIters=3000, confidence=0.995)
        if matrix is None or mask is None or not np.isfinite(matrix).all():
            result.errors.append("A finite road-plane transformation could not be estimated.")
            return result
        matrix = np.array([[1, 0, origin[0]], [0, 1, origin[1]], [0, 0, 1]]) @ matrix
        inliers = mask.ravel().astype(bool)
        result.inliers = inliers.tolist()
        if np.count_nonzero(inliers) < 4 or np.mean(inliers) < 0.6:
            result.errors.append("Too few consistent reference pairs remain after robust fitting.")
            return result
        fit_image, fit_world = image[inliers], world[inliers]
        for points, label in ((fit_image, "Inlier image"), (fit_world, "Inlier world")):
            error = _spread_error(points, label)
            if error:
                result.errors.append(error)
        if result.errors:
            return result
        condition, source_norm, target_norm = _design_condition(fit_image, fit_world)
        normalized_matrix = target_norm @ matrix @ np.linalg.inv(source_norm)
        condition = max(condition, float(np.linalg.cond(normalized_matrix)))
        result.condition_number = condition if np.isfinite(condition) else None
        if not np.isfinite(condition) or condition > 1e6:
            result.errors.append("The transformation is ill-conditioned; revise the reference point geometry.")
            return result
        region = _hull(fit_image)
        result.region_image = [tuple(point) for point in region]
        result.coverage = _area(region) / (data.geometry.width * data.geometry.height)
        if result.coverage < MIN_COVERAGE:
            result.errors.append("Reference points cover less than 0.5% of the source image; use a wider road region.")
        denominator = np.column_stack((region, np.ones(len(region)))) @ matrix[2]
        if np.min(denominator) <= 0 <= np.max(denominator):
            result.errors.append("The calibration crosses a projective horizon inside the measurement region.")
        inverse = np.linalg.inv(matrix)
        world_region = _project_many(matrix, region)
        predicted_world = _project_many(matrix, fit_image)
        predicted_image = _project_many(inverse, fit_world)
        if world_region is None or predicted_world is None or predicted_image is None:
            result.errors.append("The calibrated road region contains a singular or nonfinite projection.")
        elif _area(world_region) < 1e-6:
            result.errors.append("The projected ground-plane region has negligible area.")
        if result.errors:
            return result
        result.fit_error_m = float(np.sqrt(np.mean(np.sum((predicted_world - fit_world) ** 2, axis=1))))
        result.fit_error_px = float(np.sqrt(np.mean(np.sum((predicted_image - fit_image) ** 2, axis=1))))
        result.homography = matrix.tolist()
        result.grid_image = _grid(inverse, world_region, region)
        if len(checks_image):
            predicted_checks = _project_many(matrix, checks_image)
            if predicted_checks is None:
                result.errors.append("An independent check point has an invalid projection.")
            else:
                result.check_error_m = float(np.sqrt(np.mean(np.sum((predicted_checks - checks_world) ** 2, axis=1))))
                if result.check_error_m > RANSAC_THRESHOLD_M:
                    result.warnings.append("Independent check error exceeds 0.25 m; recheck measured references before trusting speeds.")
                if not all(_inside(tuple(point), region) for point in checks_image):
                    result.warnings.append("Some check points are outside the measurement region and test extrapolation only.")
        else:
            result.warnings.append("No independent check points: fitting residuals do not establish measurement accuracy.")
        if len(fit_image) == 4:
            result.warnings.append("Four inlier points can fit exactly; a zero fitting residual is not proof of accuracy.")
        if not np.all(inliers):
            result.warnings.append(f"Robust fitting excluded {int(np.sum(~inliers))} reference point(s) using a 0.25 m threshold.")
        if result.coverage < 0.1:
            result.warnings.append("References cover less than 10% of the image; measurements are limited to their convex hull.")
        if condition > 1e3:
            result.warnings.append("Point geometry is poorly conditioned; spread references more evenly across the road.")
        result.warnings.append("A stationary camera and measured planar references are required; camera movement or zoom requires recalibration.")
        result.valid = not result.errors
        return result
    except (cv2.error, np.linalg.LinAlgError, ValueError, FloatingPointError):
        result.errors.append("The reference geometry does not define a stable, invertible ground-plane mapping.")
        return result


class CalibrationTransform:
    """Precomputed homography; projections default to the inlier reference hull."""

    def __init__(self, data: CalibrationInput, diagnostics: CalibrationDiagnostics | None = None):
        self.data = data
        self.geometry = data.geometry
        self.diagnostics = diagnostics or validate_calibration(data)
        if not self.diagnostics.valid or self.diagnostics.homography is None:
            raise ValueError("Calibration required: " + "; ".join(self.diagnostics.errors))
        self.homography = np.asarray(self.diagnostics.homography, dtype=np.float64)
        self.inverse = np.linalg.inv(self.homography)
        self.region_image = np.asarray(self.diagnostics.region_image, dtype=np.float64)
        self._region_contour = self.region_image.astype(np.float32)

    def region_margin_px(self, point: Point) -> float:
        """Signed image distance to the measured hull; negative is outside."""
        return float(cv2.pointPolygonTest(self._region_contour, point, True))

    def project(self, point: Point, require_inside: bool = True) -> Point | None:
        try:
            value = np.asarray(point, dtype=np.float64)
            if value.shape != (2,) or not np.isfinite(value).all():
                return None
            if require_inside and not _inside(tuple(value), self.region_image):
                return None
            projected = _project_many(self.homography, value.reshape(1, 2))
            return tuple(projected[0]) if projected is not None else None
        except (ValueError, TypeError, cv2.error):
            return None

    def unproject(self, point: Point) -> Point | None:
        try:
            value = np.asarray(point, dtype=np.float64)
            if value.shape != (2,) or not np.isfinite(value).all():
                return None
            projected = _project_many(self.inverse, value.reshape(1, 2))
            return tuple(projected[0]) if projected is not None else None
        except (ValueError, TypeError):
            return None

    def compatible(self, source_id: str, geometry: ImageGeometry) -> bool:
        return self.data.source_id == source_id and self.geometry == geometry


def _cross(a: np.ndarray, b: np.ndarray) -> float:
    return float(a[0] * b[1] - a[1] * b[0])


def _segments_intersect(a: Segment, b: Segment) -> bool:
    first, second = np.asarray(a), np.asarray(b)
    r, s = first[1] - first[0], second[1] - second[0]
    denominator = _cross(r, s)
    delta = second[0] - first[0]
    tolerance = 1e-9 * max(1.0, float(np.linalg.norm(r) * np.linalg.norm(s)))
    if abs(denominator) <= tolerance:
        if abs(_cross(delta, r)) > tolerance:
            return False
        axis = int(np.argmax(np.abs(r)))
        return max(min(first[:, axis]), min(second[:, axis])) <= min(max(first[:, axis]), max(second[:, axis])) + 1e-9
    t, u = _cross(delta, s) / denominator, _cross(delta, r) / denominator
    return -1e-9 <= t <= 1 + 1e-9 and -1e-9 <= u <= 1 + 1e-9


def validate_gates(transform: CalibrationTransform, data: GateInput) -> GateDiagnostics:
    result = GateDiagnostics(gate_a=data.gate_a, gate_b=data.gate_b, allow_reverse=data.allow_reverse)
    projected = []
    for name, segment in (("A", data.gate_a), ("B", data.gate_b)):
        world = [transform.project(point) for point in segment]
        if any(point is None for point in world):
            result.errors.append(f"Gate {name} must lie entirely inside the calibrated reference region.")
            continue
        pair = (world[0], world[1])
        projected.append(pair)
        if np.linalg.norm(np.asarray(pair[1]) - pair[0]) < 1e-6:
            result.errors.append(f"Gate {name} must have distinct endpoints.")
        if name == "A":
            result.world_a = pair
        else:
            result.world_b = pair
    if len(projected) == 2 and not result.errors:
        if _segments_intersect(projected[0], projected[1]):
            result.errors.append("Gates must be separate and must not intersect or share endpoints.")
        centers = [np.mean(pair, axis=0) for pair in projected]
        if np.linalg.norm(centers[1] - centers[0]) < 0.5:
            result.warnings.append("Gates are close together; crossing jitter can dominate the measured interval.")
    result.valid = not result.errors
    return result
