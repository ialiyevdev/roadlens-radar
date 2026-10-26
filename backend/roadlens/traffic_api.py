"""Local traffic configuration, source-time analytics, exports and annotation evaluation."""

import json
from pathlib import Path
from time import perf_counter
from typing import Literal
from uuid import uuid4

from fastapi import APIRouter, HTTPException
from fastapi.responses import Response

from .field_evaluation import evaluate_fields
from .field_models import FieldEvaluationRequest
from .traffic_analytics import TrafficAnalysisRequest, analyze_traffic, traffic_export
from .traffic_evaluation import TrafficEvaluationRequest, evaluate_counting
from .traffic_models import TrafficConfiguration


EXAMPLE_PATH = Path(__file__).resolve().parents[2] / "examples" / "traffic" / "synthetic_traffic_session.json"


def traffic_routes(manager, field_store=None, annotation_provider=None):
    router = APIRouter(prefix="/api/traffic")
    store = manager.traffic_store
    field_store = field_store or getattr(manager, "field_store", None)
    annotation_provider = annotation_provider or (getattr(manager, "annotations", None).get if getattr(manager, "annotations", None) else None)

    def handle(operation):
        try:
            return operation()
        except KeyError as error:
            raise HTTPException(status_code=404, detail=str(error)) from error
        except RuntimeError as error:
            raise HTTPException(status_code=409, detail=str(error)) from error
        except ValueError as error:
            raise HTTPException(status_code=422, detail=str(error)) from error

    def selected(data):
        sessions = [store.get(identifier) for identifier in data.session_ids]
        if data.include_current:
            current = manager.traffic_snapshot()
            if current and current.get("source_id"):
                # A saved copy of the same current observation must not double its exposure/counts.
                sessions = [row for row in sessions if row["id"] != current.get("id")]
                sessions.append(current)
        return sessions

    @router.get("/current")
    def current(interval_minutes: Literal[1, 5, 15, 30, 60] = 1):
        def get():
            snapshot = manager.traffic_snapshot()
            return {"snapshot": snapshot, "analytics": analyze_traffic([snapshot] if snapshot and snapshot.get("source_id") else [],
                    TrafficAnalysisRequest(interval_minutes=interval_minutes))}
        return handle(get)

    @router.get("/configuration")
    def configuration():
        return handle(manager.traffic_configuration)

    @router.put("/configuration")
    def configure(data: TrafficConfiguration):
        def apply():
            manager.configure_traffic(data)
            return manager.traffic_configuration()
        return handle(apply)

    @router.get("/sessions")
    def sessions():
        return handle(lambda: {"sessions": store.list()})

    @router.get("/sessions/{identifier}")
    def session(identifier: str):
        return handle(lambda: store.get(identifier))

    @router.delete("/sessions/{identifier}")
    def delete(identifier: str):
        def remove():
            store.delete(identifier)
            return {"deleted": identifier}
        return handle(remove)

    @router.post("/archive")
    def archive():
        return handle(lambda: store.put(manager.traffic_snapshot()))

    @router.get("/example")
    def example():
        return handle(lambda: json.loads(EXAMPLE_PATH.read_text(encoding="utf-8")))

    @router.post("/example")
    def import_example():
        def save():
            snapshot = json.loads(EXAMPLE_PATH.read_text(encoding="utf-8"))
            identifier = str(uuid4())
            old_identifier = snapshot["id"]
            snapshot.update(id=identifier, session_id=identifier)
            for table in ("events", "zone_events", "measurements"):
                for row in snapshot.get(table, []):
                    if row.get("session_id") == old_identifier:
                        row["session_id"] = identifier
            return store.put(snapshot)
        return handle(save)

    @router.post("/analytics")
    def analytics(data: TrafficAnalysisRequest):
        return handle(lambda: analyze_traffic(selected(data), data))

    @router.post("/export")
    def export(data: TrafficAnalysisRequest,
               table: Literal["events", "classes", "flow", "zones", "speeds", "comparisons", "quality"] = "events",
               format: Literal["json", "csv"] = "json"):
        def create():
            started = perf_counter()
            content = traffic_export(analyze_traffic(selected(data), data), table, format)
            return Response(content, media_type="application/json" if format == "json" else "text/csv; charset=utf-8",
                            headers={"Content-Disposition": f'attachment; filename="roadlens-traffic-{table}.{format}"',
                                     "Cache-Control": "no-store", "X-Report-Generation-Ms": f"{(perf_counter() - started) * 1000:.6f}"})
        return handle(create)

    @router.post("/evaluate")
    def evaluate(data: TrafficEvaluationRequest):
        def create():
            if field_store is None or annotation_provider is None:
                raise ValueError("Field annotations are unavailable.")
            artifact = store.get(data.traffic_session_id)
            field = field_store.get(data.field_session_id)
            report = evaluate_counting(artifact, annotation_provider(field.id), field, data, field_store.list())
            report["speed_validation"] = evaluate_fields(field_store.list(), FieldEvaluationRequest(
                session_ids=[field.id], partition=data.partition))
            return report
        return handle(create)

    return router
