"""Small atomic JSON store for named calibration profiles, never camera frames."""

import json
import os
import tempfile
import threading
from pathlib import Path
from uuid import UUID, uuid4

from .calibration import validate_calibration
from .calibration_models import CalibrationInput, CalibrationProfile


class CalibrationStore:
    def __init__(self, directory: Path):
        self.directory = Path(directory)
        self._lock = threading.RLock()

    def _path(self, profile_id: str) -> Path:
        try:
            identifier = str(UUID(profile_id))
        except (ValueError, TypeError, AttributeError) as error:
            raise KeyError("Unknown calibration profile.") from error
        return self.directory / f"{identifier}.json"

    def list(self) -> list[CalibrationProfile]:
        with self._lock:
            profiles = [self.get(path.stem) for path in self.directory.glob("*.json")]
        return sorted(profiles, key=lambda profile: profile.name.casefold())

    def get(self, profile_id: str) -> CalibrationProfile:
        with self._lock:
            path = self._path(profile_id)
            if not path.is_file():
                raise KeyError("Unknown calibration profile.")
            try:
                profile = CalibrationProfile.model_validate_json(path.read_text(encoding="utf-8"))
            except (ValueError, OSError) as error:
                raise ValueError(f"Calibration profile {profile_id} is unreadable; repair or delete its JSON file.") from error
            if profile.id != str(UUID(profile_id)):
                raise ValueError("The stored calibration identifier does not match its filename.")
            # Stored fitting results are descriptive; activation recomputes them from references.
            return profile

    def put(self, data: CalibrationInput, profile_id: str | None = None) -> CalibrationProfile:
        diagnostics = validate_calibration(data)
        if not diagnostics.valid:
            raise ValueError("Calibration required: " + "; ".join(diagnostics.errors))
        with self._lock:
            previous = self.get(profile_id) if profile_id else None
            profile = CalibrationProfile(
                **data.model_dump(), id=previous.id if previous else str(uuid4()),
                diagnostics=diagnostics, gates=None,
            )
            return self.save(profile)

    def save(self, profile: CalibrationProfile) -> CalibrationProfile:
        with self._lock:
            target = self._path(profile.id)
            self.directory.mkdir(parents=True, exist_ok=True)
            temporary = None
            try:
                with tempfile.NamedTemporaryFile("w", encoding="utf-8", dir=self.directory, suffix=".tmp", delete=False) as stream:
                    temporary = Path(stream.name)
                    json.dump(profile.model_dump(mode="json"), stream, indent=2, allow_nan=False)
                    stream.flush()
                    os.fsync(stream.fileno())
                os.replace(temporary, target)
            finally:
                if temporary is not None:
                    temporary.unlink(missing_ok=True)
            return profile

    def delete(self, profile_id: str):
        with self._lock:
            self.get(profile_id)
            self._path(profile_id).unlink()
