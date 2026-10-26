"""Calibration/profile routes attached to the existing local FastAPI app."""

from fastapi import APIRouter
from fastapi.responses import Response
from pydantic import BaseModel, ConfigDict, Field

from .calibration import validate_calibration
from .calibration_models import CalibrationDiagnostics, CalibrationInput, CalibrationProfile, GateDiagnostics, GateInput
from .schemas import OverlaySettings, SessionSnapshot


class ActivationRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    confirm_stationary: bool = False


class InvalidationRequest(BaseModel):
    reason: str = Field(default="Camera placement, zoom or image geometry changed. Recheck calibration.", max_length=300)


def calibration_routes(manager) -> APIRouter:
    router = APIRouter(prefix="/api")

    @router.post("/calibration/freeze")
    def freeze():
        return manager.freeze_frame()

    @router.get("/calibration/frame/{frame_id}")
    def frozen_frame(frame_id: str):
        return Response(manager.frozen_frame(frame_id), media_type="image/jpeg")

    @router.post("/calibration/invalidate", response_model=SessionSnapshot)
    def invalidate(request: InvalidationRequest):
        return manager.invalidate_calibration(request.reason)

    @router.get("/calibrations")
    def profiles():
        return {"profiles": manager.calibrations.list()}

    @router.post("/calibrations/validate", response_model=CalibrationDiagnostics)
    def validate(request: CalibrationInput):
        return validate_calibration(request)

    @router.post("/calibrations", response_model=CalibrationProfile)
    def create(request: CalibrationInput):
        return manager.save_calibration(request)

    @router.put("/calibrations/{profile_id}", response_model=CalibrationProfile)
    def update(profile_id: str, request: CalibrationInput):
        return manager.save_calibration(request, profile_id)

    @router.delete("/calibrations/{profile_id}")
    def delete(profile_id: str):
        manager.delete_calibration(profile_id)
        return {"deleted": True}

    @router.post("/calibrations/{profile_id}/activate", response_model=SessionSnapshot)
    def activate(profile_id: str, request: ActivationRequest):
        return manager.activate_calibration(profile_id, request.confirm_stationary)

    @router.get("/gates", response_model=GateDiagnostics | None)
    def gates():
        return manager.snapshot().gates

    @router.put("/gates", response_model=GateDiagnostics)
    def set_gates(request: GateInput):
        return manager.update_gates(request)

    @router.delete("/gates", response_model=SessionSnapshot)
    def remove_gates():
        return manager.remove_gates()

    @router.get("/measurements")
    def measurements():
        snapshot = manager.snapshot()
        return {"measurements": snapshot.measurements, "summary": snapshot.measurement_summary,
                "independently_validated": False}

    @router.delete("/measurements", response_model=SessionSnapshot)
    def clear_measurements():
        return manager.clear_measurements()

    @router.put("/overlays", response_model=SessionSnapshot)
    def overlays(request: OverlaySettings):
        return manager.set_overlays(request)

    return router
