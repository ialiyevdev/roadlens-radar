"""Local field session CRUD, explicit reference decisions and offline evaluation."""

import csv
import json
from pathlib import Path
from time import perf_counter
from typing import Literal

from fastapi import APIRouter, File, HTTPException, UploadFile
from fastapi.responses import Response
from pydantic import Field

from .field_alignment import MAX_FIELD_BYTES, eligibility, import_references
from .field_evaluation import evaluate_fields, field_report_csv, field_report_html
from .field_models import (EventMatch, FieldEvaluationRequest, FieldModel, FieldSession,
                           FieldSessionInput, FromObservation, SyncConfig)
from .field_store import FieldStore, session_input


EXAMPLE_PATH = Path(__file__).resolve().parents[2] / "examples" / "field" / "synthetic_field_session.json"


class MatchUpdate(FieldModel):
    matches: list[EventMatch] = Field(default_factory=list, max_length=10000)


def _response(content, media_type, filename, elapsed_ms=None):
    headers = {"Content-Disposition": f'attachment; filename="{filename}"', "Cache-Control": "no-store"}
    if elapsed_ms is not None:
        headers["X-Report-Generation-Ms"] = f"{elapsed_ms:.6f}"
    return Response(content, media_type=media_type, headers=headers)


def field_routes(store: FieldStore, observation_provider=None, tracking_provider=None, annotation_delete=None) -> APIRouter:
    router = APIRouter(prefix="/api")

    def handle(operation):
        try:
            return operation()
        except KeyError as error:
            raise HTTPException(status_code=404, detail=str(error)) from error
        except (ValueError, csv.Error) as error:
            raise HTTPException(status_code=422, detail=str(error)) from error

    @router.get("/field-sessions")
    def list_sessions():
        return handle(lambda: {"sessions": store.list()})

    @router.post("/field-sessions", response_model=FieldSession)
    def create_session(data: FieldSessionInput):
        return handle(lambda: store.put(data))

    @router.get("/field-sessions/example", response_model=FieldSessionInput)
    def example():
        return handle(lambda: FieldSessionInput.model_validate_json(EXAMPLE_PATH.read_text(encoding="utf-8")))

    @router.post("/field-sessions/from-observation", response_model=FieldSession)
    def capture_session(data: FromObservation):
        def create():
            if observation_provider is None:
                raise ValueError("Current observation capture is unavailable.")
            supplied = observation_provider()
            if isinstance(supplied, FieldSessionInput):
                supplied = supplied.model_dump(mode="json")
            return store.put(FieldSessionInput.model_validate({**supplied, **data.model_dump()}))
        return handle(create)

    @router.post("/field-sessions/import", response_model=FieldSession)
    async def import_session(file: UploadFile = File(...)):
        try:
            data = await file.read(MAX_FIELD_BYTES + 1)
            def create():
                if len(data) > MAX_FIELD_BYTES:
                    raise ValueError("Field imports are limited to 8 MiB.")
                if Path(file.filename or "").suffix.casefold() != ".json":
                    raise ValueError("Field-session imports use JSON exports.")
                raw = json.loads(data.decode("utf-8-sig"))
                if not isinstance(raw, dict):
                    raise ValueError("A field-session import must be a JSON object.")
                if "id" in raw:
                    raw = session_input(FieldSession.model_validate(raw))
                return store.put(FieldSessionInput.model_validate(raw))
            return handle(create)
        finally:
            await file.close()

    @router.get("/field-sessions/{identifier}", response_model=FieldSession)
    def get_session(identifier: str):
        return handle(lambda: store.get(identifier))

    @router.put("/field-sessions/{identifier}", response_model=FieldSession)
    def update_session(identifier: str, data: FieldSessionInput):
        return handle(lambda: store.put(data, identifier))

    @router.delete("/field-sessions/{identifier}")
    def delete_session(identifier: str):
        def remove():
            if annotation_delete is not None:
                annotation_delete(identifier)
            store.delete(identifier)
            return {"deleted": identifier}
        return handle(remove)

    @router.get("/field-sessions/{identifier}/eligibility")
    def session_eligibility(identifier: str):
        return handle(lambda: eligibility(store.get(identifier)))

    @router.put("/field-sessions/{identifier}/sync", response_model=FieldSession)
    def update_sync(identifier: str, data: SyncConfig):
        def save():
            session = store.get(identifier)
            raw = session_input(session)
            raw["sync"] = data.model_dump(mode="json")
            return store.put(FieldSessionInput.model_validate(raw), identifier)
        return handle(save)

    @router.put("/field-sessions/{identifier}/matches", response_model=FieldSession)
    def update_matches(identifier: str, data: MatchUpdate):
        def save():
            session = store.get(identifier)
            raw = session_input(session)
            raw["matches"] = [match.model_dump(mode="json") for match in data.matches]
            return store.put(FieldSessionInput.model_validate(raw), identifier)
        return handle(save)

    @router.post("/field-sessions/{identifier}/references/import", response_model=FieldSession)
    async def import_reference_file(identifier: str, file: UploadFile = File(...)):
        try:
            content = await file.read(MAX_FIELD_BYTES + 1)
            def save():
                session = store.get(identifier)
                references = import_references(content, file.filename or "")
                raw = session_input(session)
                raw["reference_events"] = [reference.model_dump(mode="json") for reference in references]
                # Never transfer matching decisions to a replacement device-event ledger.
                raw["matches"] = []
                return store.put(FieldSessionInput.model_validate(raw), identifier)
            return handle(save)
        finally:
            await file.close()

    @router.get("/field-sessions/{identifier}/export")
    def export_session(identifier: str):
        return handle(lambda: _response(store.get(identifier).model_dump_json(indent=2),
                                       "application/json", "roadlens-field-session.json"))

    @router.post("/field-evaluation")
    def evaluate(data: FieldEvaluationRequest):
        return handle(lambda: evaluate_fields(store.list(), data, tracking_provider))

    @router.post("/field-evaluation/export")
    def export_report(data: FieldEvaluationRequest, format: Literal["json", "csv", "html"] = "json"):
        def generate():
            started = perf_counter()
            report = evaluate_fields(store.list(), data, tracking_provider)
            if format == "html":
                content, media_type = field_report_html(report), "text/html; charset=utf-8"
            elif format == "csv":
                content, media_type = field_report_csv(report), "text/csv; charset=utf-8"
            else:
                content, media_type = json.dumps(report, indent=2, ensure_ascii=False, allow_nan=False), "application/json"
            return _response(content, media_type, f"roadlens-field-validation.{format}", (perf_counter() - started) * 1000)
        return handle(generate)

    return router
