"""Persistent metadata for local uploaded recordings; recordings are never copied."""

import hashlib
import json
import math
import os
import tempfile
import threading
from copy import deepcopy
from pathlib import Path, PurePosixPath, PureWindowsPath
from uuid import UUID, uuid4

import av


VIDEO_EXTENSIONS = {".mp4", ".m4v", ".avi", ".mov", ".mkv", ".webm"}


def _finite_positive(value):
    return value if value is not None and math.isfinite(value) and value > 0 else None


class VideoCatalog:
    def __init__(self, upload_dir: Path):
        self.upload_dir = Path(upload_dir).resolve()
        self._path = self.upload_dir / ".catalog.json"
        self._lock = threading.RLock()
        self._records = self._load()
        self._duplicate_files = {}

    def _contained(self, relative):
        if not isinstance(relative, str):
            return None
        portable = relative.replace("\\", "/")
        path = PurePosixPath(portable)
        if path.is_absolute() or PureWindowsPath(portable).drive or ".." in path.parts:
            return None
        resolved = (self.upload_dir / portable).resolve()
        return resolved if resolved.is_relative_to(self.upload_dir) else None

    def _load(self):
        if not self._path.exists():
            return {}
        if self._path.stat().st_size > 10 * 1024 * 1024:
            raise ValueError("The local video catalog exceeds 10 MiB; repair it before loading sources.")
        try:
            raw = json.loads(self._path.read_text(encoding="utf-8"))
            if raw.get("version") != 1 or not isinstance(raw.get("videos"), list):
                raise ValueError("Unsupported catalog schema.")
            records = {}
            for item in raw["videos"]:
                if (not isinstance(item, dict) or self._contained(item.get("relative_path")) is None
                        or not isinstance(item.get("source_id"), str)):
                    continue
                try:
                    identifier = str(UUID(item["video_id"]))
                except (ValueError, TypeError, KeyError):
                    continue
                records[identifier] = item
            return records
        except (OSError, ValueError, AttributeError) as error:
            raise ValueError("The local video catalog is unreadable; repair or remove .catalog.json to rediscover uploads.") from error

    def _save(self):
        self.upload_dir.mkdir(parents=True, exist_ok=True)
        temporary = None
        try:
            with tempfile.NamedTemporaryFile("w", encoding="utf-8", suffix=".tmp", dir=self.upload_dir, delete=False) as stream:
                temporary = Path(stream.name)
                json.dump({"version": 1, "videos": list(self._records.values())}, stream, indent=2, allow_nan=False)
                stream.flush()
                os.fsync(stream.fileno())
            os.replace(temporary, self._path)
        finally:
            if temporary is not None:
                temporary.unlink(missing_ok=True)

    @staticmethod
    def _public(record):
        return deepcopy({key: value for key, value in record.items() if not key.startswith("_")})

    def _current(self, record):
        try:
            path = self._contained(record.get("relative_path"))
            if path is None or not path.is_file() or path.suffix.casefold() not in VIDEO_EXTENSIONS:
                return False
            stat = path.stat()
            return stat.st_size == record.get("_size") and stat.st_mtime_ns == record.get("_mtime_ns")
        except OSError:
            return False

    def _describe(self, path: Path, label: str, source_id=None, video_id=None):
        try:
            with av.open(str(path)) as container:
                if not container.streams.video:
                    raise ValueError("The source has no video stream.")
                stream = container.streams.video[0]
                width, height = stream.codec_context.width, stream.codec_context.height
                if width < 2 or height < 2:
                    raise ValueError("The video does not declare usable image dimensions.")
                rate = _finite_positive(float(stream.average_rate)) if stream.average_rate else None
                duration = float(stream.duration * stream.time_base) if stream.duration is not None and stream.time_base else None
                duration = _finite_positive(duration)
                frame_count = stream.frames if stream.frames and stream.frames > 0 else None
                base = str(stream.time_base) if stream.time_base else None
        except (av.FFmpegError, OSError) as error:
            raise ValueError("The uploaded video metadata could not be read.") from error
        try:
            with path.open("rb") as stream:
                digest = hashlib.file_digest(stream, "sha256").hexdigest()
        except OSError as error:
            raise ValueError("The uploaded video could not be read for its recording fingerprint.") from error
        if source_id and source_id.startswith("video:") and len(source_id) == 70 and source_id[6:].lower() != digest:
            raise ValueError("The supplied video fingerprint does not match the uploaded recording.")
        stat = path.stat()
        name = "".join(character for character in Path(str(label).replace("\\", "/")).name if ord(character) >= 32)[:160]
        identifier = str(UUID(video_id)) if video_id else str(uuid4())
        return {"video_id": identifier, "name": name or "Uploaded video", "source_id": source_id or "video:" + digest,
                "content_sha256": digest, "relative_path": path.relative_to(self.upload_dir).as_posix(),
                "width": width, "height": height, "reported_fps": rate, "frame_count": frame_count,
                "duration_s": duration, "time_base": base,
                "geometry": {"width": width, "height": height, "rotation": 0, "mirrored": False,
                             "crop": None, "coordinate_space": "source", "intrinsic_profile_id": None},
                "_size": stat.st_size, "_mtime_ns": stat.st_mtime_ns}

    def register(self, path: Path, label: str, source_id: str | None = None,
                 video_id: str | None = None) -> dict | None:
        path = Path(path).resolve()
        if not path.is_relative_to(self.upload_dir):
            return None
        if path.suffix.casefold() not in VIDEO_EXTENSIONS or not path.is_file():
            raise ValueError("Choose an existing supported uploaded video.")
        with self._lock:
            # A changed file at a previously catalogued path receives a fresh identity.
            record = self._describe(path, label, source_id, video_id)
            for old in self._records.values():
                if old.get("content_sha256") == record["content_sha256"] and self._current(old):
                    return self._public(old)
            self._records = {key: value for key, value in self._records.items()
                             if value.get("relative_path") != record["relative_path"] and self._current(value)}
            self._records[record["video_id"]] = record
            self._save()
            return self._public(record)

    def sources(self) -> list[dict]:
        with self._lock:
            before = json.dumps(self._records, sort_keys=True)
            self._records = {key: value for key, value in self._records.items() if self._current(value)}
            known_paths = {value["relative_path"] for value in self._records.values()}
            for path in sorted(self.upload_dir.glob("*")):
                if not path.is_file() or path.suffix.casefold() not in VIDEO_EXTENSIONS:
                    continue
                resolved = path.resolve()
                if not resolved.is_relative_to(self.upload_dir) or resolved.relative_to(self.upload_dir).as_posix() in known_paths:
                    continue
                stat = resolved.stat()
                identity = (stat.st_size, stat.st_mtime_ns)
                duplicate = self._duplicate_files.get(str(resolved))
                if duplicate and duplicate[0] == identity and any(
                        old.get("content_sha256") == duplicate[1] for old in self._records.values()):
                    continue
                try:
                    record = self._describe(resolved, path.name)
                except ValueError:
                    continue  # A partial/invalid upload is not a selectable video.
                if any(old.get("content_sha256") == record["content_sha256"] for old in self._records.values()):
                    self._duplicate_files[str(resolved)] = (identity, record["content_sha256"])
                    continue
                self._records[record["video_id"]] = record
                known_paths.add(record["relative_path"])
            if json.dumps(self._records, sort_keys=True) != before:
                self._save()
            return sorted((self._public(value) for value in self._records.values()), key=lambda item: item["name"].casefold())

    def existing(self, source_id: str) -> dict | None:
        return next((record for record in self.sources() if record["source_id"] == source_id), None)
