"""Local measurement exports and reproducible tracker comparisons."""

import csv
import io
import json
from typing import Annotated, Literal

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import Response
from pydantic import BaseModel, ConfigDict, Field

from .validation import spreadsheet_cell


class _BenchmarkModel(BaseModel):
    model_config = ConfigDict(extra="forbid", allow_inf_nan=False)


class BenchmarkHardware(_BenchmarkModel):
    os: str = Field(max_length=500)
    cpu: str = Field(max_length=500)
    logical_cpus: int | None = None
    python: str = Field(max_length=100)


class BenchmarkMethodology(_BenchmarkModel):
    matching: str = Field(max_length=4000)
    identity_switches: str = Field(max_length=4000)
    fragmentations: str = Field(max_length=4000)
    timing: str = Field(max_length=4000)
    limitations: str = Field(max_length=4000)


class BenchmarkMetrics(_BenchmarkModel):
    frames: int = Field(ge=0)
    ground_truth_observations: int = Field(ge=0)
    matched_observations: int = Field(ge=0)
    missed_observations: int = Field(ge=0)
    id_switches: int = Field(ge=0)
    fragments: int = Field(ge=0)
    created_tracks: int = Field(ge=0)
    confirmed_tracks: int = Field(ge=0)
    potential_id_switches: int = Field(ge=0)
    fragmentation_suspicions: int = Field(ge=0)
    mean_update_ms: float = Field(ge=0)
    p95_update_ms: float = Field(ge=0)
    runtime_ms: float = Field(ge=0)


class ContinuitySample(_BenchmarkModel):
    timestamp_s: float
    ground_truth_count: int = Field(ge=0)
    observed_tracks: int = Field(ge=0)
    active_tracks: int = Field(ge=0)
    lost_tracks: int = Field(ge=0)


class BenchmarkScenario(BenchmarkMetrics):
    name: str = Field(max_length=160)
    description: str = Field(max_length=1000)
    continuity: list[ContinuitySample] = Field(max_length=1000)


class BenchmarkTracker(BenchmarkMetrics):
    name: str = Field(max_length=160)
    scenarios: list[BenchmarkScenario] = Field(max_length=50)


class BenchmarkReport(_BenchmarkModel):
    schema_version: Literal[1]
    suite_version: str = "1.0"
    provenance: Literal["synthetic"]
    generated_at_utc: str = Field(max_length=100)
    hardware: BenchmarkHardware
    methodology: BenchmarkMethodology
    baseline: BenchmarkTracker
    improved: BenchmarkTracker


async def bounded_benchmark(request: Request) -> BenchmarkReport:
    data = bytearray()
    async for chunk in request.stream():
        data.extend(chunk)
        if len(data) > 2 * 1024 * 1024:
            raise HTTPException(422, "Benchmark exports are limited to 2 MiB.")
    try:
        return BenchmarkReport.model_validate_json(data)
    except ValueError as error:
        raise HTTPException(422, str(error)) from error


def _csv(rows: list[dict], empty_fields=()) -> str:
    output = io.StringIO(newline="")
    fields = list(dict.fromkeys(key for row in rows for key in row)) or list(empty_fields)
    writer = csv.DictWriter(output, fieldnames=fields)
    writer.writeheader()
    for row in rows:
        writer.writerow({key: spreadsheet_cell(value) for key, value in row.items()})
    return output.getvalue()


def _download(value, format: str, name: str, rows: list[dict], empty_fields=()):
    content = _csv(rows, empty_fields) if format == "csv" else json.dumps(value, indent=2, ensure_ascii=False, allow_nan=False)
    return Response(content, media_type="text/csv; charset=utf-8" if format == "csv" else "application/json",
                    headers={"Content-Disposition": f'attachment; filename="{name}.{format}"'})


def phase3_routes(manager, response_profiler) -> APIRouter:
    router = APIRouter(prefix="/api")

    @router.get("/exports/measurements")
    def measurements(format: Literal["json", "csv"] = "json"):
        value = manager.measurement_export()
        records = value["measurements"]
        rows = []
        for record in records:
            row = {key: field for key, field in record.items() if key != "diagnostics"}
            row.update({"diagnostic_" + key: field for key, field in record["diagnostics"].items()})
            rows.append(row)
        return _download(value, format, "roadlens-measurements", rows,
                         ("id", "track_id", "session_id", "source_id", "status", "estimated_speed_kmh", "calibration_id", "reasons"))

    @router.post("/benchmarks/tracking", response_model=BenchmarkReport)
    def tracking():
        from .tracking_benchmark import run_tracking_benchmark
        return run_tracking_benchmark()

    @router.post("/benchmarks/tracking/export")
    def export_tracking(report: Annotated[BenchmarkReport, Depends(bounded_benchmark)], format: Literal["json", "csv"] = "json"):
        value = report.model_dump(mode="json")
        rows = []
        for key in ("baseline", "improved"):
            tracker = value[key]
            common = {"schema_version": 1, "provenance": value["provenance"], "generated_at_utc": value["generated_at_utc"],
                      "tracker": key, "hardware": value["hardware"], "methodology": value["methodology"]}
            rows.append({**common, "scenario": "all", **{field: item for field, item in tracker.items() if field != "scenarios"}})
            for scenario in tracker.get("scenarios", []):
                rows.append({**common, "scenario": scenario.get("name"), **scenario})
        return _download(value, format, "roadlens-tracking-benchmark", rows)

    @router.get("/performance")
    def performance():
        snapshot = manager.snapshot()
        return {"response_setup": response_profiler.snapshot(), "pipeline_latest_ms": snapshot.pipeline_profile,
                "detection_latest_ms": snapshot.inference_ms, "processed_fps": snapshot.processing_fps,
                "dropped_frames": snapshot.dropped_frames,
                "timing_note": "Profiling uses a separate performance clock; measurement uses the original source timestamps."}

    return router
