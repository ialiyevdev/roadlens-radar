"""Revision-checked annotation JSON and lossless, explicit-record CSV exchange."""

import csv
import io
import json
import os
import tempfile
import threading
from pathlib import Path
from uuid import UUID

from .annotation_models import AnnotationDocument
from .validation import spreadsheet_cell


class AnnotationRevisionConflict(ValueError):
    pass


class AnnotationStore:
    def __init__(self, directory: Path):
        self.directory = Path(directory)
        self._lock = threading.RLock()

    def _path(self, identifier):
        try:
            return self.directory / f"{str(UUID(identifier))}.json"
        except (ValueError, TypeError, AttributeError) as error:
            raise KeyError("Unknown annotation field session.") from error

    def get(self, field) -> AnnotationDocument:
        with self._lock:
            path = self._path(field.id)
            if not path.is_file():
                return AnnotationDocument(field_session_id=field.id, source_id=field.source.source_id,
                                          geometry=field.camera.geometry, provenance=field.provenance)
            try:
                document = AnnotationDocument.model_validate_json(path.read_text(encoding="utf-8"))
            except (ValueError, OSError) as error:
                raise ValueError("Stored annotations are unreadable.") from error
            self._compatible(field, document)
            return document

    @staticmethod
    def _compatible(field, document):
        if document.field_session_id != field.id or document.source_id != field.source.source_id or document.geometry != field.camera.geometry:
            raise ValueError("Annotation session, source or pixel geometry differs. Preserve this document and use a matching field session.")

    def put(self, field, document: AnnotationDocument) -> AnnotationDocument:
        document = AnnotationDocument.model_validate(document.model_dump())
        self._compatible(field, document)
        with self._lock:
            current = self.get(field)
            if current.revision != document.revision:
                raise AnnotationRevisionConflict("Annotations changed since loading. Reload before saving; existing labels were preserved.")
            saved = document.model_copy(update={"revision": document.revision+1}, deep=True)
            self.directory.mkdir(parents=True, exist_ok=True)
            target = self._path(field.id)
            temporary = None
            try:
                with tempfile.NamedTemporaryFile("w", encoding="utf-8", dir=self.directory, suffix=".tmp", delete=False) as output:
                    temporary = Path(output.name)
                    json.dump(saved.model_dump(mode="json"), output, indent=2, allow_nan=False)
                    output.flush()
                    os.fsync(output.fileno())
                os.replace(temporary, target)
            finally:
                if temporary is not None:
                    temporary.unlink(missing_ok=True)
            return saved

    def delete(self, identifier):
        with self._lock:
            self._path(identifier).unlink(missing_ok=True)


CSV_FIELDS = ["schema_version", "field_session_id", "source_id", "geometry_json", "revision", "provenance",
              "proposal_metadata_json", "index", "timestamp_s", "reviewed", "record_type", "identity", "category",
              "x1", "y1", "x2", "y2", "occluded", "partial_visibility", "entry", "exit", "predicted_track_id", "confidence",
              "escaped_text_fields_json"]
DATA_FIELDS = CSV_FIELDS[:-1]


def annotations_csv(document: AnnotationDocument) -> str:
    stream = io.StringIO(newline="")
    writer = csv.DictWriter(stream, fieldnames=CSV_FIELDS)
    writer.writeheader()

    def write(row):
        safe = {key: spreadsheet_cell(value) for key, value in row.items()}
        escaped = [key for key, value in row.items() if isinstance(value, str) and safe[key] != value]
        safe["escaped_text_fields_json"] = json.dumps(escaped, separators=(",", ":"))
        writer.writerow(safe)

    base = {"schema_version": 1, "field_session_id": document.field_session_id, "source_id": document.source_id,
            "geometry_json": document.geometry.model_dump_json(), "revision": document.revision,
            "provenance": document.provenance,
            "proposal_metadata_json": document.proposal_metadata.model_dump_json() if document.proposal_metadata else ""}
    if not document.frames:
        write({**base, "record_type": "document"})
    for frame in document.frames:
        common = {**base, "index": frame.index, "timestamp_s": frame.timestamp_s,
                  "reviewed": str(frame.reviewed).lower()}
        write({**common, "record_type": "frame"})
        for record_type, items in [("object", frame.objects), ("prediction", frame.predictions)]:
            for item in items:
                data = item.model_dump(exclude={"bbox"})
                data = {key: str(value).lower() if isinstance(value, bool) else value for key, value in data.items()}
                if item.bbox is not None:
                    data.update(dict(zip(["x1", "y1", "x2", "y2"], item.bbox)))
                write({**common, "record_type": record_type, **data})
    return stream.getvalue()


def _boolean(value):
    if value not in ("true", "false"):
        raise ValueError("Annotation CSV boolean values must be true or false.")
    return value == "true"


def _csv_rows(reader):
    try:
        yield from reader
    except csv.Error as error:
        raise ValueError("Annotation CSV is malformed or contains an oversized field.") from error


def parse_annotations(content: bytes, filename: str) -> AnnotationDocument:
    if not content or len(content) > 8*1024*1024:
        raise ValueError("Annotation imports must be nonempty and at most 8 MiB.")
    try:
        text = content.decode("utf-8-sig")
    except UnicodeDecodeError as error:
        raise ValueError("Annotation files must use UTF-8.") from error
    if filename.lower().endswith(".json"):
        return AnnotationDocument.model_validate_json(text)
    if not filename.lower().endswith(".csv"):
        raise ValueError("Choose a RoadLens annotation JSON or CSV export.")
    reader = csv.DictReader(io.StringIO(text, newline=""), strict=True)
    try:
        header = reader.fieldnames
    except csv.Error as error:
        raise ValueError("Annotation CSV has a malformed header.") from error
    if header != CSV_FIELDS:
        raise ValueError("Annotation CSV header differs from the documented export schema.")
    base = None
    frames = {}
    frame_records = set()
    document_record = False
    for row_index, row in enumerate(_csv_rows(reader)):
        if row_index >= 110001:
            raise ValueError("Annotation CSV contains too many records.")
        if None in row or any(value is None for value in row.values()):
            raise ValueError("Annotation CSV record has an inconsistent column count.")
        escaped = json.loads(row.pop("escaped_text_fields_json") or "[]")
        if not isinstance(escaped, list) or any(not isinstance(key, str) or key not in DATA_FIELDS for key in escaped) or len(set(escaped)) != len(escaped):
            raise ValueError("Invalid escaped text fields in annotation CSV.")
        for key in escaped:
            value = row[key]
            if not value.startswith("'") or spreadsheet_cell(value[1:]) != value:
                raise ValueError("Annotation CSV escape metadata does not match its guarded text cell.")
            row[key] = value[1:]
        metadata = {key: row[key] for key in CSV_FIELDS[:7]}
        if base is None:
            base = metadata
        elif metadata != base:
            raise ValueError("Annotation CSV mixes document metadata or revisions.")
        kind = row["record_type"]
        if kind == "document":
            if row_index != 0 or any(row[key] for key in DATA_FIELDS[7:] if key != "record_type"):
                raise ValueError("An empty annotation CSV has one document record.")
            document_record = True
            continue
        if document_record:
            raise ValueError("An empty document record cannot be mixed with frame records.")
        if kind not in ("frame", "object", "prediction"):
            raise ValueError("Unknown annotation CSV record type.")
        index = int(row["index"])
        stamp = float(row["timestamp_s"]) if row["timestamp_s"] else None
        reviewed = _boolean(row["reviewed"])
        if index not in frames:
            frames[index] = {"index": index, "timestamp_s": stamp, "reviewed": reviewed, "objects": [], "predictions": []}
        if frames[index]["timestamp_s"] != stamp or frames[index]["reviewed"] != reviewed:
            raise ValueError("Annotation CSV mixes metadata for one frame.")
        if kind == "frame":
            if any(row[key] for key in DATA_FIELDS[11:]):
                raise ValueError("Frame records cannot contain object or prediction fields.")
            if index in frame_records:
                raise ValueError("Duplicate frame record in annotation CSV.")
            frame_records.add(index)
            continue
        raw_box = [row[key] for key in ("x1", "y1", "x2", "y2")]
        if any(raw_box) and not all(raw_box):
            raise ValueError("Supply all four bounding box coordinates or leave all four empty.")
        bbox = [float(value) for value in raw_box] if all(raw_box) else None
        if kind == "object":
            if row["predicted_track_id"] or row["confidence"]:
                raise ValueError("Manual object records cannot contain predicted tracking IDs or confidence.")
            frames[index]["objects"].append({"identity": row["identity"], "category": row["category"], "bbox": bbox,
                **{key: _boolean(row[key]) for key in ("occluded", "partial_visibility", "entry", "exit")}})
        else:
            if any(row[key] for key in ("identity", "occluded", "partial_visibility", "entry", "exit")):
                raise ValueError("Prediction records cannot contain manual identity or visibility fields.")
            frames[index]["predictions"].append({"predicted_track_id": int(row["predicted_track_id"]),
                "category": row["category"], "bbox": bbox, "confidence": float(row["confidence"])})
    if base is None or set(frames) != frame_records:
        raise ValueError("Annotation CSV must retain an explicit frame record for every annotated frame.")
    return AnnotationDocument.model_validate({"schema_version": int(base["schema_version"]),
        "field_session_id": base["field_session_id"], "source_id": base["source_id"],
        "geometry": json.loads(base["geometry_json"]), "revision": int(base["revision"]), "provenance": base["provenance"],
        "proposal_metadata": json.loads(base["proposal_metadata_json"]) if base["proposal_metadata_json"] else None,
        "frames": list(frames.values())})
