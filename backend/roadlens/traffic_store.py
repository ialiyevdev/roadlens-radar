"""Atomic traffic artifacts and source/geometry-specific configuration files."""

import hashlib
import json
import os
import tempfile
import threading
from datetime import datetime, timezone
from pathlib import Path
from uuid import UUID

from .traffic_analytics import merged_coverage


MAX_TRAFFIC_BYTES = 32 * 1024 * 1024


def _json_copy(value):
    if hasattr(value, "model_dump"):
        value = value.model_dump(mode="json")
    # Deep copying also rejects NaN/Infinity before they reach disk or the API.
    return json.loads(json.dumps(value, ensure_ascii=False, allow_nan=False))


def _atomic_json(target, value):
    target.parent.mkdir(parents=True, exist_ok=True)
    content = json.dumps(value, indent=2, ensure_ascii=False, allow_nan=False)
    if len(content.encode("utf-8")) > MAX_TRAFFIC_BYTES:
        raise ValueError("Traffic artifacts are limited to 32 MiB; retained engine histories must remain bounded.")
    temporary = None
    try:
        with tempfile.NamedTemporaryFile("w", encoding="utf-8", suffix=".tmp", dir=target.parent, delete=False) as stream:
            temporary = Path(stream.name)
            stream.write(content)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary, target)
    finally:
        if temporary is not None:
            temporary.unlink(missing_ok=True)


def traffic_summary(artifact):
    spans = merged_coverage(artifact.get("coverage", []))
    configuration = artifact.get("configuration") or {}
    summary = artifact.get("summary", {})
    retained = sum(row.get("status") == "counted" for row in artifact.get("events", []))
    return {"id": artifact["id"], "session_id": artifact.get("session_id", artifact["id"]),
            "name": artifact.get("name", artifact["id"]), "source_id": artifact.get("source_id"),
            "provenance": artifact.get("provenance", "recorded_unverified"),
            "started_at": artifact.get("started_at"), "ended_at": artifact.get("ended_at"),
            "saved_at": artifact.get("saved_at"), "configuration_id": configuration.get("id"),
            "geometry": configuration.get("geometry"), "crossing_count": summary.get("total_crossings", retained),
            "retained_counted_events": retained,
            "coverage_seconds": summary.get("covered_duration_s", sum(end - start for start, end in spans)),
            "diagnostics": artifact.get("diagnostics", {})}


class TrafficStore:
    def __init__(self, directory: Path):
        self.directory = Path(directory)
        self._lock = threading.RLock()

    def _path(self, identifier):
        try:
            identifier = str(UUID(identifier))
        except (TypeError, ValueError, AttributeError) as error:
            raise KeyError("Unknown traffic observation.") from error
        return self.directory / "sessions" / f"{identifier}.json"

    def put(self, snapshot: dict):
        with self._lock:
            artifact = _json_copy(snapshot)
            if not isinstance(artifact, dict):
                raise ValueError("Traffic observations must be JSON objects.")
            identifier = artifact.get("id") or artifact.get("session_id")
            target = self._path(identifier)
            identifier = target.stem
            if artifact.get("session_id", identifier) != identifier:
                raise ValueError("Traffic artifact and observation identifiers differ.")
            if not artifact.get("source_id"):
                raise ValueError("A traffic observation needs its original source identifier.")
            if artifact.get("schema_version", 1) != 1:
                raise ValueError("Unsupported traffic artifact schema.")
            from .traffic_models import TrafficConfiguration
            for configuration in ([artifact["configuration"]] if artifact.get("configuration") else []) + artifact.get("configurations", []):
                TrafficConfiguration.model_validate(configuration)
            for key in ("events", "zone_events", "occupancy_samples", "coverage", "measurements"):
                if not isinstance(artifact.get(key, []), list):
                    raise ValueError(f"Traffic {key} must be a list.")
            artifact.update(id=identifier, session_id=identifier, schema_version=1,
                            saved_at=datetime.now(timezone.utc).isoformat())
            _atomic_json(target, artifact)
            return artifact

    def get(self, identifier):
        with self._lock:
            path = self._path(identifier)
            if not path.is_file():
                raise KeyError("Unknown traffic observation.")
            try:
                if path.stat().st_size > MAX_TRAFFIC_BYTES:
                    raise ValueError("Traffic artifact exceeds the local size limit.")
                artifact = json.loads(path.read_text(encoding="utf-8"), parse_constant=lambda value: (_ for _ in ()).throw(ValueError(value)))
                if artifact.get("id") != path.stem or artifact.get("session_id", path.stem) != path.stem:
                    raise ValueError("Traffic artifact identifier differs from its filename.")
                return artifact
            except (OSError, ValueError, AttributeError) as error:
                raise ValueError("Stored traffic observation is unreadable; repair or remove its JSON file.") from error

    def list(self):
        with self._lock:
            rows = [traffic_summary(self.get(path.stem)) for path in (self.directory / "sessions").glob("*.json")]
        return sorted(rows, key=lambda row: row.get("saved_at") or "", reverse=True)

    def delete(self, identifier):
        with self._lock:
            self.get(identifier)
            self._path(identifier).unlink()

    def _configuration_key(self, source_id, geometry):
        geometry = geometry.model_dump(mode="json") if hasattr(geometry, "model_dump") else geometry
        return hashlib.sha256(json.dumps([source_id, geometry], sort_keys=True, separators=(",", ":")).encode()).hexdigest()

    def save_configuration(self, configuration):
        from .traffic_models import TrafficConfiguration
        configuration = TrafficConfiguration.model_validate(_json_copy(configuration)).model_dump(mode="json")
        key = self._configuration_key(configuration["source_id"], configuration["geometry"])
        with self._lock:
            _atomic_json(self.directory / "configurations" / f"{key}.json", configuration)
        return configuration

    def configuration_for(self, source_id, geometry):
        from .traffic_models import TrafficConfiguration
        key = self._configuration_key(source_id, geometry)
        with self._lock:
            path = self.directory / "configurations" / f"{key}.json"
            if not path.is_file():
                return None
            value = TrafficConfiguration.model_validate_json(path.read_text(encoding="utf-8")).model_dump(mode="json")
            if self._configuration_key(value["source_id"], value["geometry"]) != key:
                raise ValueError("Saved traffic configuration does not match this source geometry.")
            return value
