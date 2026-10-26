"""Bounded local-only validation interchange; no uploads are retained."""

import csv
from typing import Annotated, Literal

from fastapi import APIRouter, Depends, File, HTTPException, Request, UploadFile
from fastapi.responses import Response

from .validation import MAX_IMPORT_BYTES, evaluate, example_dataset, import_dataset, report_csv
from .validation_models import EvaluationRequest, ValidationDataset, ValidationReport


async def bounded_evaluation(request: Request) -> EvaluationRequest:
    """Bound direct JSON requests as well as file uploads before parsing."""
    data = bytearray()
    async for chunk in request.stream():
        data.extend(chunk)
        if len(data) > MAX_IMPORT_BYTES:
            raise HTTPException(status_code=422, detail="Validation requests are limited to 2 MiB.")
    try:
        return EvaluationRequest.model_validate_json(data)
    except ValueError as error:
        raise HTTPException(status_code=422, detail=str(error)) from error


def validation_routes() -> APIRouter:
    router = APIRouter(prefix="/api/validation")

    @router.get("/example", response_model=ValidationDataset)
    def example():
        return example_dataset()

    @router.post("/import", response_model=ValidationDataset)
    async def import_file(file: UploadFile = File(...)):
        try:
            data = await file.read(MAX_IMPORT_BYTES + 1)
            return import_dataset(data, file.filename or "")
        except (ValueError, csv.Error) as error:
            raise HTTPException(status_code=422, detail=str(error)) from error
        finally:
            await file.close()

    @router.post("/evaluate", response_model=ValidationReport)
    def evaluate_dataset(request: Annotated[EvaluationRequest, Depends(bounded_evaluation)]):
        return evaluate(request)

    @router.post("/export")
    def export(request: Annotated[EvaluationRequest, Depends(bounded_evaluation)], format: Literal["json", "csv"] = "json"):
        report = evaluate(request)
        if format == "csv":
            content, media_type, suffix = report_csv(report), "text/csv; charset=utf-8", "csv"
        else:
            content, media_type, suffix = report.model_dump_json(indent=2), "application/json", "json"
        return Response(content, media_type=media_type, headers={
            "Content-Disposition": f'attachment; filename="roadlens-validation.{suffix}"',
            "Cache-Control": "no-store"})

    return router
