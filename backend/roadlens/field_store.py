"""Atomic local field-session persistence with conservative collection-level splits."""

import json
import os
import tempfile
import threading
from pathlib import Path
from uuid import UUID, uuid4

from .field_alignment import synchronization
from .field_models import FieldSession, FieldSessionInput, utc_now


def split_conflict(left: FieldSessionInput, right: FieldSessionInput) -> bool:
    if left.partition == right.partition:
        return False
    a, b = left.source, right.source
    # Split complete recordings/collections, even when declared segments do not overlap.
    # This also prevents adjacent-frame and intentionally cropped segment leakage.
    return bool(a.source_id == b.source_id
                or (a.content_sha256 and a.content_sha256 == b.content_sha256)
                or (a.near_duplicate_group and a.near_duplicate_group == b.near_duplicate_group)
                or (a.collection_id and a.collection_id == b.collection_id))


def assert_partitions(sessions: list[FieldSession]):
    for index, left in enumerate(sessions):
        for right in sessions[index + 1:]:
            if split_conflict(left, right):
                raise ValueError(f"Dataset split leakage between sessions {left.id} and {right.id}: "
                                 "a recording, collection or near-duplicate group spans partitions.")


class FieldStore:
    def __init__(self, directory: Path):
        self.directory = Path(directory)
        self._lock = threading.RLock()

    def _path(self, identifier: str):
        try:
            value = str(UUID(identifier))
        except (ValueError, TypeError, AttributeError) as error:
            raise KeyError("Unknown field session.") from error
        return self.directory / f"{value}.json"

    def get(self, identifier: str) -> FieldSession:
        with self._lock:
            target = self._path(identifier)
            if not target.is_file():
                raise KeyError("Unknown field session.")
            try:
                session = FieldSession.model_validate_json(target.read_text(encoding="utf-8"))
            except (ValueError, OSError) as error:
                raise ValueError("Stored field session is unreadable; repair or delete its JSON file.") from error
            if session.id != str(UUID(identifier)):
                raise ValueError("Stored field-session identifier does not match its filename.")
            session.sync_diagnostics = synchronization(session.sync)
            return session

    def list(self) -> list[FieldSession]:
        with self._lock:
            sessions = [self.get(path.stem) for path in self.directory.glob("*.json")]
        return sorted(sessions, key=lambda item: item.updated_at, reverse=True)

    def put(self, data: FieldSessionInput, identifier: str | None = None) -> FieldSession:
        with self._lock:
            old = self.get(identifier) if identifier else None
            # Revalidate even model instances because model_copy(update=...) skips validation.
            data = FieldSessionInput.model_validate(data.model_dump(mode="json"))
            if old and (old.source.source_id != data.source.source_id
                        or old.source.content_sha256 != data.source.content_sha256
                        or old.camera.geometry != data.camera.geometry
                        or old.camera.intrinsic_profile_id != data.camera.intrinsic_profile_id
                        or old.camera.zoom != data.camera.zoom or old.camera.lens_model != data.camera.lens_model):
                data.calibration_id = None
                data.gates = None
                data.calibration_compatible = False
                warning = ("Source or camera geometry changed. Archived calibration and gates were invalidated; "
                           "original measurement evidence is retained. Create a new observation/configuration for comparisons.")
                data.configuration_warnings = list(dict.fromkeys([*data.configuration_warnings, warning]))
            others = [item for item in self.list() if old is None or item.id != old.id]
            for item in others:
                if split_conflict(data, item):
                    raise ValueError("Dataset split leakage: the source recording, collection or near-duplicate "
                                     f"group is already assigned to {item.partition} in session {item.id}. "
                                     "Keep that complete group in one partition.")
            now = utc_now()
            session = FieldSession(**data.model_dump(), id=old.id if old else str(uuid4()),
                                   created_at=old.created_at if old else now, updated_at=now,
                                   sync_diagnostics=synchronization(data.sync))
            target = self._path(session.id)
            self.directory.mkdir(parents=True, exist_ok=True)
            temporary = None
            try:
                with tempfile.NamedTemporaryFile("w", encoding="utf-8", suffix=".tmp",
                                                 dir=self.directory, delete=False) as stream:
                    temporary = Path(stream.name)
                    json.dump(session.model_dump(mode="json"), stream, indent=2, allow_nan=False)
                    stream.flush()
                    os.fsync(stream.fileno())
                os.replace(temporary, target)
            finally:
                if temporary is not None:
                    temporary.unlink(missing_ok=True)
            return session

    def delete(self, identifier: str):
        with self._lock:
            self.get(identifier)
            self._path(identifier).unlink()


def session_input(session: FieldSession) -> dict:
    return {key: value for key, value in session.model_dump(mode="json").items()
            if key in FieldSessionInput.model_fields}
