"""Traffic routes use the same artifact/settings contracts as live observations."""

import csv
import io
from types import SimpleNamespace

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from roadlens.field_store import FieldStore
from roadlens.traffic_api import traffic_routes
from roadlens.traffic_store import TrafficStore
from test_traffic_analytics import artifact
from test_traffic_evaluation import evaluation_fixture


@pytest.fixture
def client(tmp_path):
    data = artifact()
    manager = SimpleNamespace(traffic_store=TrafficStore(tmp_path / "traffic"), field_store=FieldStore(tmp_path / "field"),
                              traffic_snapshot=lambda: data, traffic_configuration=lambda: data["configuration"])
    manager.configure_traffic = lambda configuration: data.update(configuration=configuration.model_dump(mode="json"))
    app = FastAPI()
    app.include_router(traffic_routes(manager))
    with TestClient(app) as client:
        yield client, data, manager


def test_current_configuration_and_archive_contracts(client):
    client, data, _ = client
    current = client.get("/api/traffic/current").json()
    assert current["snapshot"]["id"] == data["id"]
    assert current["analytics"]["summary"]["total_crossings"] == 3
    config = client.get("/api/traffic/configuration").json()
    config["name"] = "Edited traffic configuration"
    assert client.put("/api/traffic/configuration", json=config).json()["name"] == config["name"]
    saved = client.post("/api/traffic/archive").json()
    assert saved["id"] == data["id"]
    assert client.get("/api/traffic/sessions").json()["sessions"][0]["id"] == saved["id"]
    assert client.get(f"/api/traffic/sessions/{saved['id']}").json()["events"] == data["events"]
    assert client.delete(f"/api/traffic/sessions/{saved['id']}").status_code == 200
    assert client.get(f"/api/traffic/sessions/{saved['id']}").status_code == 404


def test_saved_and_current_same_observation_not_double_counted(client):
    client, data, _ = client
    client.post("/api/traffic/archive")
    report = client.post("/api/traffic/analytics", json={"session_ids": [data["id"]], "include_current": True}).json()
    assert report["summary"]["total_crossings"] == 3
    assert report["summary"]["coverage_seconds"] == 70


@pytest.mark.parametrize("table", ["events", "classes", "flow", "zones", "speeds", "comparisons", "quality"])
def test_exports_retain_table_units_filters_and_attachment_headers(client, table):
    client, data, _ = client
    client.post("/api/traffic/archive")
    request = {"session_ids": [data["id"]], "interval_minutes": 5, "category": "car"}
    json_result = client.post(f"/api/traffic/export?table={table}&format=json", json=request)
    assert json_result.status_code == 200 and json_result.json()["table"] == table
    assert json_result.json()["filters"]["category"] == "car"
    assert json_result.json()["units"]["speed"] == "km/h"
    csv_result = client.post(f"/api/traffic/export?table={table}&format=csv", json=request)
    assert csv_result.status_code == 200 and "attachment" in csv_result.headers["content-disposition"]
    assert float(csv_result.headers["x-report-generation-ms"]) >= 0
    assert list(csv.DictReader(io.StringIO(csv_result.text)))[0]["table"] == table


@pytest.mark.parametrize("payload", [{"interval_minutes": 2}, {"start_s": 8, "end_s": 2},
                                      {"speed_status": "rejected"}, {"session_ids": ["same", "same"]}])
def test_invalid_analytics_inputs_rejected(client, payload):
    client, _, _ = client
    assert client.post("/api/traffic/analytics", json=payload).status_code == 422


def test_missing_observation_and_unsupported_export_rejected(client):
    client, _, _ = client
    assert client.post("/api/traffic/analytics", json={"session_ids": ["../escape"]}).status_code == 404
    assert client.post("/api/traffic/export?table=unsupported", json={}).status_code == 422


def test_actual_synthetic_example_import_and_analysis(client):
    client, _, _ = client
    original = client.get("/api/traffic/example").json()
    saved = client.post("/api/traffic/example").json()
    assert saved["id"] != original["id"] and saved["provenance"] == "synthetic"
    assert all(row["session_id"] == saved["id"] for row in saved["events"])
    report = client.post("/api/traffic/analytics", json={"session_ids": [saved["id"]]}).json()
    assert report["summary"]["total_crossings"] == 6
    assert report["speeds"]["n"] == 4 and report["speeds"]["mean_kmh"] == 28.5


def test_annotation_evaluation_and_phase4_speed_report_are_separate(tmp_path):
    data, document, field, request = evaluation_fixture(tmp_path / "fields")
    field_store = FieldStore(tmp_path / "fields")
    store = TrafficStore(tmp_path / "traffic")
    store.put(data)
    manager = SimpleNamespace(traffic_store=store, field_store=field_store,
                              annotations=SimpleNamespace(get=lambda identifier: document))
    app = FastAPI()
    app.include_router(traffic_routes(manager))
    with TestClient(app) as client:
        response = client.post("/api/traffic/evaluate", json=request.model_dump())
    assert response.status_code == 200
    report = response.json()
    assert report["matched_count"] == 1 and report["classification_accuracy"] == 0
    assert report["speed_validation"]["validation"]["summary"]["n"] == 0
