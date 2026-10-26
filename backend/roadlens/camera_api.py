"""Offline checkerboard fitting, profile exchange, and explicit runtime selection."""

import asyncio

from fastapi import APIRouter, File, Form, HTTPException, UploadFile
from fastapi.responses import Response
from pydantic import Field

from .camera_calibration import MAX_IMAGE_BYTES, MAX_IMAGES, MAX_TOTAL_BYTES, calibrate_camera
from .camera_models import CameraCalibrationInput, CameraIntrinsicProfile, CameraModel
from .schemas import SessionSnapshot


class CameraActivation(CameraModel):
    profile_id: str | None = Field(default=None, max_length=100)
    confirm_unchanged: bool = False


def camera_routes(manager) -> APIRouter:
    router = APIRouter(prefix="/api")

    @router.get("/camera-profiles")
    def profiles():
        return {"profiles": manager.camera_profiles.list()}

    @router.post("/camera-profiles/import", response_model=CameraIntrinsicProfile)
    def import_profile(profile: CameraIntrinsicProfile):
        return manager.camera_profiles.put(profile)

    @router.post("/camera-profiles/calibrate", response_model=CameraIntrinsicProfile)
    async def calibrate(configuration: str = Form(...), files: list[UploadFile] = File(...)):
        try:
            if len(configuration) > 12000:
                raise HTTPException(413, "Camera calibration metadata is too large.")
            request = CameraCalibrationInput.model_validate_json(configuration)
            if not 6 <= len(files) <= MAX_IMAGES:
                raise ValueError("Upload between six and forty checkerboard images.")
            images = []
            total = 0
            for file in files:
                content = await file.read(MAX_IMAGE_BYTES + 1)
                if len(content) > MAX_IMAGE_BYTES:
                    raise HTTPException(413, "Each calibration image is limited to 8 MiB.")
                total += len(content)
                if total > MAX_TOTAL_BYTES:
                    raise HTTPException(413, "Calibration uploads are limited to 64 MiB in total.")
                images.append((file.filename or "image", content))
            profile = await asyncio.to_thread(calibrate_camera, images, request)
            return manager.camera_profiles.put(profile)
        finally:
            for file in files:
                await file.close()

    @router.get("/camera-profiles/{profile_id}", response_model=CameraIntrinsicProfile)
    def profile(profile_id: str):
        return manager.camera_profiles.get(profile_id)

    @router.get("/camera-profiles/{profile_id}/export")
    def export_profile(profile_id: str):
        profile = manager.camera_profiles.get(profile_id)
        return Response(profile.model_dump_json(indent=2), media_type="application/json",
                        headers={"Content-Disposition": f'attachment; filename="camera-{profile.id}.json"'})

    @router.get("/camera-profiles/{profile_id}/preview")
    def preview(profile_id: str, corrected: bool = True):
        return Response(manager.camera_preview(profile_id, corrected), media_type="image/jpeg")

    @router.delete("/camera-profiles/{profile_id}")
    def delete(profile_id: str):
        manager.delete_camera_profile(profile_id)
        return {"deleted": True}

    @router.put("/camera-model", response_model=SessionSnapshot)
    def activate(request: CameraActivation):
        return manager.configure_camera_model(request.profile_id, request.confirm_unchanged)

    return router
