"""Actual local API contracts with deterministic synthetic field inputs."""

import json
from pathlib import Path

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from roadlens.field_api import field_routes
from roadlens.field_models import FieldSessionInput
from roadlens.field_store import FieldStore


EXAMPLES = Path(__file__).resolve().parents[2] / "examples/field"


@pytest.fixture
def client(tmp_path):
    app = FastAPI()
    raw = json.loads((EXAMPLES / "synthetic_field_session.json").read_text(encoding="utf-8"))
    app.include_router(field_routes(FieldStore(tmp_path), observation_provider=lambda: raw,
                                    tracking_provider=lambda identifier: {"annotation_count": 0}))
    with TestClient(app) as test_client:
        yield test_client


def create(client):
    example = client.get("/api/field-sessions/example")
    assert example.status_code == 200
    response = client.post("/api/field-sessions", json=example.json())
    assert response.status_code == 200
    return response.json()


def test_session_crud_and_export_reimport(client):
    assert client.get("/api/field-sessions").json() == {"sessions": []}
    session = create(client)
    assert client.get(f"/api/field-sessions/{session['id']}").json() == session
    assert len(client.get("/api/field-sessions").json()["sessions"]) == 1
    payload = {key: value for key, value in session.items() if key in FieldSessionInput.model_fields}
    payload["name"] = "Edited field session"
    assert client.put(f"/api/field-sessions/{session['id']}", json=payload).json()["name"] == "Edited field session"
    exported = client.get(f"/api/field-sessions/{session['id']}/export")
    assert exported.status_code == 200 and "attachment" in exported.headers["content-disposition"]
    imported = client.post("/api/field-sessions/import", files={"file": ("session.json", exported.content, "application/json")})
    assert imported.status_code == 200 and imported.json()["id"] != session["id"]
    assert imported.json()["measurements"] == session["measurements"]
    assert client.delete(f"/api/field-sessions/{session['id']}").status_code == 200
    assert client.get(f"/api/field-sessions/{session['id']}").status_code == 404


def test_capture_current_observation_merges_user_metadata(client):
    response = client.post("/api/field-sessions/from-observation", json={"name": "Captured source", "partition": "held_out", "provenance": "synthetic"})
    assert response.status_code == 200
    session = response.json()
    assert session["name"] == "Captured source" and session["source"]["source_id"] == "synthetic-phase4-demo"
    assert len(session["measurements"]) == 14


def test_reference_import_resets_decisions_and_sync_and_matches_can_be_saved(client):
    session = create(client)
    identifier = session["id"]
    response = client.post(f"/api/field-sessions/{identifier}/references/import",
                           files={"file": ("events.csv", (EXAMPLES / "synthetic_reference_events.csv").read_bytes(), "text/csv")})
    assert response.status_code == 200 and response.json()["matches"] == []
    saved = client.put(f"/api/field-sessions/{identifier}/matches", json={"matches": session["matches"]})
    assert saved.status_code == 200
    assert client.get(f"/api/field-sessions/{identifier}/eligibility").json()["eligible_event_count"] == 4
    uncertain = {**session["sync"], "anchors": [], "fit_drift": False}
    updated = client.put(f"/api/field-sessions/{identifier}/sync", json=uncertain)
    assert updated.status_code == 200 and updated.json()["sync_diagnostics"]["status"] == "uncertain"
    assert client.get(f"/api/field-sessions/{identifier}/eligibility").json()["eligible_event_count"] == 0


def test_reference_import_failure_does_not_mutate_retained_records(client):
    session = create(client)
    response = client.post(f"/api/field-sessions/{session['id']}/references/import", files={"file": ("bad.json", b'[{}]', "application/json")})
    assert response.status_code == 422
    assert client.get(f"/api/field-sessions/{session['id']}").json()["matches"] == session["matches"]


@pytest.mark.parametrize("format,content_type", [("json", "application/json"), ("csv", "text/csv"), ("html", "text/html")])
def test_evaluation_download_formats_and_timing(client, format, content_type):
    session = create(client)
    payload = {"session_ids": [session["id"]]}
    evaluation = client.post("/api/field-evaluation", json=payload)
    assert evaluation.status_code == 200
    assert evaluation.json()["validation"]["summary"]["mae_kmh"] == 2
    response = client.post(f"/api/field-evaluation/export?format={format}", json=payload)
    assert response.status_code == 200 and content_type in response.headers["content-type"]
    assert f".{format}" in response.headers["content-disposition"]
    assert float(response.headers["x-report-generation-ms"]) >= 0


def test_split_leakage_and_invalid_references_have_visible_errors(client):
    session = create(client)
    payload = {key: value for key, value in session.items() if key in FieldSessionInput.model_fields}
    payload["partition"] = "development"
    response = client.post("/api/field-sessions", json=payload)
    assert response.status_code == 422 and "split leakage" in response.json()["detail"]
    response = client.post("/api/field-evaluation", json={"session_ids": ["unknown"]})
    assert response.status_code == 422
    assert client.get("/api/field-sessions/not-a-uuid").status_code == 404
