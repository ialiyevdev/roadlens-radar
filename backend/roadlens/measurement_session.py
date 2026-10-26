"""Calibration and measurement state owned by the existing observation session.

The caller uses SessionManager's lock; detector inference never runs under it.
"""

from statistics import mean

from .calibration import CalibrationTransform, validate_gates
from .calibration_models import CalibrationProfile, GateInput, ImageGeometry
from .speed import SpeedEstimator
from .measurement_models import MeasurementResult


class MeasurementSession:
    def __init__(self):
        self.reset()

    def reset(self, source_id: str = "", session_id: str = ""):
        self.source_id = source_id
        self.session_id = session_id
        self.geometry: ImageGeometry | None = None
        self.profile: CalibrationProfile | None = None
        self.transform = None
        self.gates = None
        self.status = "required"
        self.warnings: list[str] = []
        self.estimator = SpeedEstimator(None, None, source_id, None, session_id)
        self._public_results = {}

    def set_geometry(self, geometry: ImageGeometry):
        if self.transform and not self.transform.compatible(self.source_id, geometry):
            self.invalidate("Source image geometry changed. Recheck calibration before measuring.")
            self.status = "incompatible"
        self.geometry = geometry

    def activate(self, profile: CalibrationProfile, confirm_stationary: bool):
        if not confirm_stationary:
            raise ValueError("Confirm that the camera placement, zoom, crop and orientation match the saved references.")
        if self.geometry is None:
            raise ValueError("Open a source and wait for a frame before applying calibration.")
        transform = CalibrationTransform(profile)
        if not transform.compatible(self.source_id, self.geometry):
            raise ValueError("Calibration source or image geometry is incompatible with this observation.")
        gates = validate_gates(transform, profile.gates) if profile.gates else None
        if gates is not None and not gates.valid:
            raise ValueError("Saved gates are invalid: " + "; ".join(gates.errors))
        self.profile, self.transform, self.gates = profile, transform, gates
        self.status = "ready"
        self.warnings = list(transform.diagnostics.warnings)
        self._new_estimator()

    def _new_estimator(self):
        self._public_results = {}
        self.estimator = SpeedEstimator(
            self.transform, self.gates, self.source_id,
            self.profile.id if self.profile else None, self.session_id,
        )

    def configure_gates(self, data: GateInput):
        if self.transform is None:
            raise ValueError("Apply a valid calibration before configuring gates.")
        diagnostics = validate_gates(self.transform, data)
        if not diagnostics.valid:
            raise ValueError("Invalid measurement gates: " + "; ".join(diagnostics.errors))
        self.gates = diagnostics
        self.profile = self.profile.model_copy(update={"gates": data})
        self._new_estimator()
        return diagnostics

    def remove_gates(self):
        self.gates = None
        if self.profile:
            self.profile = self.profile.model_copy(update={"gates": None})
        self._new_estimator()

    def invalidate(self, reason: str):
        self.estimator.finish(reason)
        self.transform = None
        self.profile = None
        self.gates = None
        self.status = "required"
        self.warnings = [reason]
        # Keep old history visible, but never project or label speeds with a stale mapping.
        self.estimator.transform = None
        self.estimator.gates = None

    def clear_history(self):
        self._new_estimator()

    def sync(self, snapshot):
        snapshot.geometry = self.geometry
        snapshot.calibration_status = self.status
        snapshot.calibration_id = self.profile.id if self.profile else None
        snapshot.calibration_warnings = self.warnings
        snapshot.gates = self.gates
        public = {}
        for item in self.estimator.measurements:
            cached = self._public_results.get(item.id)
            if cached is None or cached[0] is not item:
                cached = (item, MeasurementResult(**{key: getattr(item, key) for key in MeasurementResult.model_fields}))
            public[item.id] = cached
        self._public_results = public
        snapshot.measurements = [item[1] for item in public.values()]
        results = {item.track_id: item for item in snapshot.measurements}
        for track in snapshot.tracks:
            if track.id in results:
                result = results[track.id]
                track.measurement_state = "rejected" if result.status == "rejected" else "completed"
                track.estimated_speed_kmh = (
                    result.estimated_speed_kmh if result.status == "valid" and self.status == "ready"
                    and track.world_position is not None and not track.missed and not track.association_ambiguous else None
                )
        valid = [item for item in snapshot.measurements if item.status == "valid" and item.estimated_speed_kmh is not None]
        completed = [item for item in snapshot.measurements if item.status in {"valid", "approximate"} and item.estimated_speed_kmh is not None]
        snapshot.measurement_summary = {
            "valid_count": len(valid),
            "approximate_count": sum(item.status == "approximate" for item in snapshot.measurements),
            "rejected_count": sum(item.status == "rejected" for item in snapshot.measurements),
            "latest_speed_kmh": completed[-1].estimated_speed_kmh if completed and self.status == "ready" else None,
            "latest_status": completed[-1].status if completed and self.status == "ready" else None,
            "average_speed_kmh": round(mean(item.estimated_speed_kmh for item in valid), 1) if valid and self.status == "ready" else None,
        }
        snapshot.measurement_status = (
            "Calibration required" if self.status != "ready" else
            "Configure Gate A and Gate B" if self.gates is None else
            "Waiting for complete gate crossings; estimates are not independently validated"
        )
