"""Immutable local intrinsic profile JSON; calibration photographs are never stored."""

import json
import os
import tempfile
import threading
from pathlib import Path
from uuid import UUID

from .camera_models import CameraIntrinsicProfile


class CameraProfileStore:
    def __init__(self, directory: Path):
        self.directory = Path(directory)
        self._lock = threading.RLock()

    def _path(self, identifier: str) -> Path:
        try:
            value = str(UUID(identifier))
        except (ValueError, TypeError, AttributeError) as error:
            raise KeyError("Unknown camera intrinsic profile.") from error
        return self.directory / f"{value}.json"

    def list(self) -> list[CameraIntrinsicProfile]:
        with self._lock:
            return sorted((self.get(path.stem) for path in self.directory.glob("*.json")),
                          key=lambda value: value.name.casefold())

    def get(self, identifier: str) -> CameraIntrinsicProfile:
        with self._lock:
            path = self._path(identifier)
            if not path.is_file():
                raise KeyError("Unknown camera intrinsic profile.")
            try:
                result = CameraIntrinsicProfile.model_validate_json(path.read_text(encoding="utf-8"))
            except (OSError, ValueError) as error:
                raise ValueError("Stored camera intrinsic profile is unreadable.") from error
            if result.id != path.stem:
                raise ValueError("Camera intrinsic identifier does not match its filename.")
            return result

    def put(self, profile: CameraIntrinsicProfile) -> CameraIntrinsicProfile:
        profile = CameraIntrinsicProfile.model_validate(profile.model_dump())
        with self._lock:
            target = self._path(profile.id)
            if target.exists():
                if self.get(profile.id) == profile:
                    return profile
                raise ValueError("Camera intrinsic profiles are immutable. Import a new profile ID to change parameters.")
            self.directory.mkdir(parents=True, exist_ok=True)
            temporary = None
            try:
                with tempfile.NamedTemporaryFile("w", encoding="utf-8", dir=self.directory, suffix=".tmp", delete=False) as output:
                    temporary = Path(output.name)
                    json.dump(profile.model_dump(mode="json"), output, indent=2, allow_nan=False)
                    output.flush()
                    os.fsync(output.fileno())
                os.replace(temporary, target)
            finally:
                if temporary is not None:
                    temporary.unlink(missing_ok=True)
            return profile

    def delete(self, identifier: str):
        with self._lock:
            self.get(identifier)
            self._path(identifier).unlink()
