"""Numerical evidence retained with a result, without altering its speed."""

from math import hypot
from dataclasses import dataclass

from .measurement_models import MeasurementDiagnostics


def segment_distance(point, segment) -> float:
    start, end = segment
    dx, dy = end[0] - start[0], end[1] - start[1]
    length_squared = dx * dx + dy * dy
    fraction = max(0.0, min(1.0, ((point[0] - start[0]) * dx + (point[1] - start[1]) * dy) / length_squared))
    return hypot(point[0] - start[0] - fraction * dx, point[1] - start[1] - fraction * dy)


def box_overlap_fraction(box, other) -> float:
    """Fraction of the smaller box overlapped; does not prove occlusion."""
    overlap = max(0, min(box[2], other[2]) - max(box[0], other[0])) * max(0, min(box[3], other[3]) - max(box[1], other[1]))
    area = min(max(0, box[2] - box[0]) * max(0, box[3] - box[1]),
               max(0, other[2] - other[0]) * max(0, other[3] - other[1]))
    return overlap / area if area else 0.0


@dataclass
class QualityEvidence:
    """Constant-size accumulators survive eviction from the raw sample window."""

    observations: int = 0
    minimum_margin: float | None = None
    maximum_gap: float | None = None
    maximum_residual_px: float | None = None
    maximum_residual_m: float | None = None
    gate_a_near: int = 0
    gate_b_near: int = 0
    ambiguous: int = 0
    overlapping: int = 0
    maximum_overlap: float = 0.0

    def observe(self, sample, gates, near_gate_distance_m):
        self.observations += 1
        for attribute, value, operation in (
            ("minimum_margin", sample.region_margin_px, min),
            ("maximum_gap", sample.observation_gap_s, max),
            ("maximum_residual_px", sample.contact_prediction_residual_px, max),
            ("maximum_residual_m", sample.contact_prediction_residual_m, max),
        ):
            if value is not None:
                previous = getattr(self, attribute)
                setattr(self, attribute, value if previous is None else operation(previous, value))
        if sample.valid and sample.world_position is not None and gates and gates.valid:
            self.gate_a_near += segment_distance(sample.world_position, gates.world_a) <= near_gate_distance_m
            self.gate_b_near += segment_distance(sample.world_position, gates.world_b) <= near_gate_distance_m
        self.ambiguous += sample.association_ambiguous
        self.overlapping += sample.overlap_fraction >= .3
        self.maximum_overlap = max(self.maximum_overlap, sample.overlap_fraction)


def summarize_quality(track, transform, gates, near_gate_distance_m: float) -> MeasurementDiagnostics:
    samples = list(track.history)
    evidence = track.evidence
    calibration = transform.diagnostics if transform else None
    intervals = {name: crossing.interval_s for name, crossing in track.crossings.items()}
    return MeasurementDiagnostics(
        calibration_check_error_m=calibration.check_error_m if calibration else None,
        calibration_fit_error_m=calibration.fit_error_m if calibration else None,
        calibration_coverage_fraction=calibration.coverage if calibration else None,
        minimum_region_margin_px=evidence.minimum_margin,
        maximum_observation_gap_s=evidence.maximum_gap,
        maximum_contact_prediction_residual_px=evidence.maximum_residual_px,
        maximum_contact_prediction_residual_m=evidence.maximum_residual_m,
        gate_a_near_samples=evidence.gate_a_near,
        gate_b_near_samples=evidence.gate_b_near,
        near_gate_distance_m=near_gate_distance_m,
        gate_a_interpolation_interval_s=intervals.get("A"),
        gate_b_interpolation_interval_s=intervals.get("B"),
        ambiguous_observations=evidence.ambiguous,
        overlapping_box_observations=evidence.overlapping,
        maximum_box_overlap_fraction=evidence.maximum_overlap,
        track_age_s=track.age_s,
        gate_warnings=list(gates.warnings) if gates else [],
        calibration_warnings=list(calibration.warnings) if calibration else [],
        retained_position_samples=len(samples),
        quality_observation_count=evidence.observations,
        position_history_truncated=evidence.observations > len(samples),
    )
