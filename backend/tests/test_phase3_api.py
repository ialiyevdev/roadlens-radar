import copy
import csv
import io
import json

import pytest
from fastapi.testclient import TestClient

from roadlens.api import create_app
from roadlens.session import SessionManager


@pytest.fixture
def client(tmp_path):
    manager = SessionManager(calibration_dir=tmp_path / "calibrations", upload_dir=tmp_path / "uploads")
    with TestClient(create_app(manager), base_url="http://127.0.0.1:8000") as api:
        yield api


@pytest.fixture
def report(client):
    response = client.post("/api/benchmarks/tracking")
    assert response.status_code == 200, response.text
    return response.json()


def test_tracking_benchmark_runs_without_source_and_exports_same_measured_run(client, report):
    assert report["provenance"] == "synthetic"
    assert report["baseline"]["id_switches"] == 5
    assert report["improved"]["id_switches"] == 1
    assert report["improved"]["frames"] == 352
    assert report["hardware"]["cpu"]
    exported = client.post("/api/benchmarks/tracking/export?format=json", json=report)
    assert exported.status_code == 200, exported.text
    assert exported.json() == report
    exported_csv = client.post("/api/benchmarks/tracking/export?format=csv", json=report)
    rows = list(csv.DictReader(io.StringIO(exported_csv.text)))
    assert len(rows) == 24
    assert rows[0]["scenario"] == "all"
    assert float(rows[0]["mean_update_ms"]) == report["baseline"]["mean_update_ms"]
    assert json.loads(rows[0]["hardware"])["cpu"] == report["hardware"]["cpu"]
    assert client.get("/api/session").json()["state"] == "idle"


@pytest.mark.parametrize("scenarios", [[None], ["oops"], {"unexpected": "object"}, [{}]])
def test_malformed_benchmark_export_is_a_visible_input_error(client, report, scenarios):
    request = copy.deepcopy(report)
    request["baseline"]["scenarios"] = scenarios
    assert client.post("/api/benchmarks/tracking/export", json=request).status_code == 422


def test_benchmark_export_rejects_nonfinite_and_oversize_bodies(client, report):
    report["baseline"]["mean_update_ms"] = float("nan")
    assert client.post("/api/benchmarks/tracking/export", content=json.dumps(report)).status_code == 422
    response = client.post("/api/benchmarks/tracking/export", content=b" " * (2 * 1024 * 1024 + 1))
    assert response.status_code == 422
