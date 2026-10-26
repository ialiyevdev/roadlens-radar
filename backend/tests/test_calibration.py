import cv2
import numpy as np
import pytest
from pydantic import ValidationError

from roadlens.calibration import CalibrationTransform, validate_calibration, validate_gates
from roadlens.calibration_models import (
    CalibrationInput, Correspondence, GateInput, ImageGeometry,
)


def references(image_points=None, matrix=None, **changes):
    image = np.asarray(image_points if image_points is not None else
                       [(100, 100), (900, 100), (900, 600), (100, 600)], dtype=float)
    matrix = np.asarray(matrix if matrix is not None else
                        [[0.05, 0, -5], [0, 0.04, -4], [0, 0, 1]], dtype=float)
    world = cv2.perspectiveTransform(image.reshape(-1, 1, 2), matrix).reshape(-1, 2)
    values = dict(name="Measured test plane", source_id="video:synthetic",
                  geometry=ImageGeometry(width=1000, height=700),
                  points=[Correspondence(image=tuple(a), world=tuple(b)) for a, b in zip(image, world)])
    values.update(changes)
    return CalibrationInput(**values)


def test_known_perspective_transform_and_inverse():
    matrix = [[0.06, 0.003, -5], [0.001, 0.05, -4], [0.0002, 0.0001, 1]]
    data = references(matrix=matrix)
    transform = CalibrationTransform(data)
    pixel = (430.0, 380.0)
    expected = cv2.perspectiveTransform(np.asarray([[pixel]]), np.asarray(matrix))[0, 0]
    assert transform.project(pixel) == pytest.approx(expected)
    assert transform.unproject(tuple(expected)) == pytest.approx(pixel)
    assert transform.diagnostics.fit_error_m < 1e-5
    assert transform.diagnostics.valid


def test_measurement_region_blocks_extrapolation_and_keeps_boundary():
    transform = CalibrationTransform(references())
    assert transform.project((500, 350)) == pytest.approx((20, 10))
    assert transform.project((100, 100)) == pytest.approx((0, 0), abs=1e-8)
    assert transform.project((20, 350)) is None
    assert transform.project((20, 350), require_inside=False) == pytest.approx((-4, 10))


def test_grid_is_bounded_and_coverage_is_a_fraction():
    transform = CalibrationTransform(references())
    diagnostics = transform.diagnostics
    assert diagnostics.coverage == pytest.approx(800 * 500 / (1000 * 700))
    assert 2 <= len(diagnostics.grid_image) <= 24
    for line in diagnostics.grid_image:
        assert len(line) == 2
        assert all(transform.project(point) is not None for point in line)
        ground = [transform.project(point) for point in line]
        assert abs(ground[0][0] - ground[1][0]) < 1e-7 or abs(ground[0][1] - ground[1][1]) < 1e-7


def test_four_point_residual_is_not_presented_as_accuracy():
    diagnostics = validate_calibration(references())
    assert diagnostics.fit_error_m < 1e-7
    assert any("zero fitting residual is not proof" in warning for warning in diagnostics.warnings)
    assert any("No independent check" in warning for warning in diagnostics.warnings)


def test_independent_checks_are_not_fitted():
    check = Correspondence(image=(500, 350), world=(21, 10))
    unchecked = validate_calibration(references())
    checked = validate_calibration(references(check_points=[check]))
    assert checked.valid
    assert checked.homography == unchecked.homography
    assert checked.check_error_m == pytest.approx(1)
    assert any("Independent check error" in warning for warning in checked.warnings)


def test_reused_fitting_point_is_not_an_independent_check():
    data = references()
    data.check_points = [data.points[0]]
    result = validate_calibration(data)
    assert not result.valid
    assert "Independent check points" in result.errors[0]


def test_robust_estimation_excludes_outlier_and_preserves_metric_scale():
    data = references([(100, 100), (500, 100), (900, 100), (900, 350),
                       (900, 600), (500, 600), (100, 600), (100, 350), (500, 350)])
    data.points[-1] = Correspondence(image=(500, 350), world=(80, -30))
    diagnostics = validate_calibration(data)
    assert diagnostics.valid
    assert diagnostics.inliers == [True] * 8 + [False]
    assert CalibrationTransform(data, diagnostics).project((400, 300)) == pytest.approx((15, 8))
    assert any("excluded 1" in warning for warning in diagnostics.warnings)


@pytest.mark.parametrize("image", [
    [(100, 100), (200, 200), (300, 300), (400, 400)],
    [(100, 100), (300, 101), (600, 102), (900, 103.01)],
    [(100, 100), (100, 100), (900, 600), (100, 600)],
    [(100, 100), (900, 100), (900, 700), (100, 600)],
    [(100, 100), (120, 100), (120, 120), (100, 120)],
])
def test_invalid_image_geometry_is_rejected(image):
    diagnostics = validate_calibration(references(image))
    assert not diagnostics.valid
    assert diagnostics.errors


def test_world_collinearity_and_duplicates_are_rejected():
    data = references()
    data.points = [Correspondence(image=point.image, world=(index * 2, index * 2))
                   for index, point in enumerate(data.points)]
    assert not validate_calibration(data).valid
    data.points[-1] = Correspondence(image=data.points[-1].image, world=data.points[0].world)
    assert any("duplicates" in error for error in validate_calibration(data).errors)


def test_three_collinear_of_four_cannot_define_invertible_homography():
    data = references([(100, 100), (500, 100), (900, 100), (500, 600)])
    data.points[-1] = Correspondence(image=data.points[-1].image, world=(0, 0))
    diagnostics = validate_calibration(data)
    assert not diagnostics.valid


def test_ill_conditioned_homography_is_rejected_after_normalization():
    data = references([(100, 100), (500, 100), (900, 100.000001), (500, 600)])
    data.points = [Correspondence(image=point.image, world=world) for point, world in
                   zip(data.points, [(0, 0), (40, 0), (40, 20), (0, 20)])]
    diagnostics = validate_calibration(data)
    assert not diagnostics.valid
    assert any("ill-conditioned" in error for error in diagnostics.errors)


def test_large_origin_does_not_reduce_local_metric_precision():
    data = references()
    offset = np.array([900_000.0, 1_400_000.0])
    data.points = [Correspondence(image=point.image, world=tuple(np.asarray(point.world) + offset))
                   for point in data.points]
    transform = CalibrationTransform(data)
    assert transform.project((330, 470)) == pytest.approx(offset + [11.5, 14.8], abs=1e-6)
    assert transform.diagnostics.fit_error_m < 1e-6


def test_bow_tie_world_mapping_has_a_horizon_inside_the_road():
    data = references()
    data.points = [Correspondence(image=point.image, world=world) for point, world in
                   zip(data.points, [(0, 0), (40, 0), (0, 20), (40, 20)])]
    diagnostics = validate_calibration(data)
    assert not diagnostics.valid
    assert any("horizon" in error for error in diagnostics.errors)


@pytest.mark.parametrize("value", [float("nan"), float("inf"), -float("inf")])
def test_nonfinite_input_has_clear_validation_error(value):
    with pytest.raises(ValidationError, match="finite"):
        Correspondence(image=(value, 20), world=(0, 0))
    transform = CalibrationTransform(references())
    assert transform.project((value, 200)) is None
    assert transform.unproject((value, 20)) is None


def test_pure_validator_also_defends_against_bypassed_model_validation():
    data = references()
    data.points[0] = Correspondence.model_construct(image=(float("nan"), 20), world=(0, 0))
    diagnostics = validate_calibration(data)
    assert not diagnostics.valid
    assert "finite" in diagnostics.errors[0]


def test_insufficient_points_and_invalid_calibration_cannot_be_used():
    data = references()
    data.points = data.points[:3]
    assert not validate_calibration(data).valid
    with pytest.raises(ValueError, match="Calibration required"):
        CalibrationTransform(data)


@pytest.mark.parametrize("change", [
    dict(width=1280), dict(height=720), dict(rotation=90), dict(mirrored=True),
    dict(crop=(50, 50, 900, 600)),
])
def test_calibration_invalidates_with_changed_geometry(change):
    data = references()
    transform = CalibrationTransform(data)
    assert transform.compatible(data.source_id, data.geometry)
    assert not transform.compatible("camera:0", data.geometry)
    assert not transform.compatible(data.source_id, data.geometry.model_copy(update=change))


def test_valid_gates_are_projected_and_may_be_nonparallel():
    result = validate_gates(CalibrationTransform(references()), GateInput(
        gate_a=((200, 200), (800, 200)), gate_b=((200, 500), (800, 550)), allow_reverse=True))
    assert result.valid
    assert result.world_a[0] == pytest.approx((5, 4))
    assert result.world_b[1] == pytest.approx((35, 18))
    assert result.allow_reverse


@pytest.mark.parametrize("gate_a,gate_b,error", [
    (((200, 200), (200, 200)), ((200, 500), (800, 500)), "distinct"),
    (((20, 200), (800, 200)), ((200, 500), (800, 500)), "inside"),
    (((200, 200), (800, 500)), ((200, 500), (800, 200)), "intersect"),
    (((200, 200), (800, 200)), ((200, 200), (800, 200)), "intersect"),
    (((200, 200), (800, 200)), ((800, 200), (800, 500)), "intersect"),
])
def test_invalid_gates_are_rejected(gate_a, gate_b, error):
    result = validate_gates(CalibrationTransform(references()), GateInput(gate_a=gate_a, gate_b=gate_b))
    assert not result.valid
    assert any(error in message for message in result.errors)


def test_collinear_disjoint_gates_are_separate_segments():
    result = validate_gates(CalibrationTransform(references()), GateInput(
        gate_a=((200, 200), (400, 200)), gate_b=((600, 200), (800, 200))))
    assert result.valid


def test_diagnostics_are_json_serializable():
    diagnostics = validate_calibration(references())
    assert '"homography"' in diagnostics.model_dump_json()
