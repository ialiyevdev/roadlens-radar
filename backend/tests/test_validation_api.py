"""Actual validation HTTP parsing/downloads, synthetic records only."""

import json

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from roadlens.validation import MAX_IMPORT_BYTES, dataset_csv, example_dataset
from roadlens.validation_api import validation_routes


@pytest.fixture
def client():
    app = FastAPI()
    app.include_router(validation_routes())
    with TestClient(app) as test_client:
        yield test_client


def test_example_evaluate_and_export_json_match(client):
    dataset = client.get("/api/validation/example").json()
    assert dataset["provenance"] == "synthetic"
    result = client.post("/api/validation/evaluate", json={"dataset": dataset})
    assert result.status_code == 200
    assert result.json()["compared_count"] == 12
    assert result.json()["summary"]["mae_kmh"] == pytest.approx(34 / 12)
    downloaded = client.post("/api/validation/export?format=json", json={"dataset": dataset})
    assert downloaded.status_code == 200
    assert downloaded.json() == result.json()
    assert "attachment" in downloaded.headers["content-disposition"]
    assert downloaded.headers["cache-control"] == "no-store"


@pytest.mark.parametrize("suffix", ["json", "csv"])
def test_import_multipart_supported_files(client, suffix):
    dataset = example_dataset()
    content = dataset.model_dump_json() if suffix == "json" else dataset_csv(dataset)
    result = client.post("/api/validation/import", files={"file": (f"reference.{suffix}", content.encode())})
    assert result.status_code == 200
    assert result.json() == dataset.model_dump(mode="json")


def test_export_csv_has_consistent_units_and_exclusions(client):
    result = client.post("/api/validation/export?format=csv", json={"dataset": example_dataset().model_dump()})
    assert result.status_code == 200
    assert result.headers["content-type"].startswith("text/csv")
    assert "estimated_speed_kmh,reference_speed_kmh" in result.text
    assert "reference_event_mismatch" in result.text
    assert 'filename="roadlens-validation.csv"' in result.headers["content-disposition"]


@pytest.mark.parametrize(("filename", "content"), [
    ("test.json", b"invalid"), ("test.txt", b"{}"), ("test.csv", b"wrong,headers\n1,2\n"),
    ("test.json", b"x" * (MAX_IMPORT_BYTES + 1)),
], ids=["invalid-json", "unsupported-extension", "missing-columns", "oversize"])
def test_invalid_uploads_return_422_visible_detail(client, filename, content):
    result = client.post("/api/validation/import", files={"file": (filename, content)})
    assert result.status_code == 422
    assert result.json()["detail"]


def test_missing_file_and_bad_export_format_return_422(client):
    assert client.post("/api/validation/import").status_code == 422
    result = client.post("/api/validation/export?format=xlsx", json={"dataset": example_dataset().model_dump()})
    assert result.status_code == 422


def test_duplicate_events_bad_provenance_and_invalid_values_return_422(client):
    dataset = example_dataset().model_dump()
    dataset["records"].append(dataset["records"][0])
    assert client.post("/api/validation/evaluate", json={"dataset": dataset}).status_code == 422
    dataset = example_dataset().model_dump()
    dataset["provenance"] = "trusted"
    assert client.post("/api/validation/evaluate", json={"dataset": dataset}).status_code == 422
    dataset = example_dataset().model_dump()
    dataset["records"][0]["estimated_speed_kmh"] = -1
    assert client.post("/api/validation/evaluate", json={"dataset": dataset}).status_code == 422


def test_nonfinite_json_input_rejected(client):
    dataset = example_dataset().model_dump()
    dataset["records"][0]["estimated_speed_kmh"] = float("nan")
    # JSON allows neither NaN nor infinities. Send raw invalid numeric JSON to exercise validation.
    result = client.post("/api/validation/import", files={"file": ("reference.json", json.dumps(dataset).encode())})
    assert result.status_code == 422


def test_empty_json_dataset_supported_and_options_validated(client):
    request = {"dataset": {"name": "No observations", "provenance": "synthetic", "records": []}}
    result = client.post("/api/validation/evaluate", json=request)
    assert result.status_code == 200
    assert result.json()["summary"]["mae_kmh"] is None
    request["options"] = {"minimum_group_samples": 2}
    assert client.post("/api/validation/evaluate", json=request).status_code == 422


@pytest.mark.parametrize("endpoint", ["evaluate", "export"])
def test_direct_json_body_bounded_before_parse(client, endpoint):
    result = client.post(f"/api/validation/{endpoint}", content=b" " * (MAX_IMPORT_BYTES + 1),
                         headers={"content-type": "application/json"})
    assert result.status_code == 422
    assert "2 MiB" in result.json()["detail"]


def test_nonfinite_diagnostics_in_direct_evaluation_rejected(client):
    dataset = example_dataset().model_dump()
    dataset["records"][0]["diagnostics"] = {"gap_s": float("inf")}
    result = client.post("/api/validation/evaluate", content=json.dumps({"dataset": dataset}),
                         headers={"content-type": "application/json"})
    assert result.status_code == 422
    assert "finite" in result.json()["detail"]


def test_csv_parser_errors_visible(client):
    header = "dataset_name,dataset_provenance,recording_id,observation_id,measurement_id,status\n"
    result = client.post("/api/validation/import", files={"file": ("reference.csv", (header + '"unterminated').encode())})
    assert result.status_code == 422
    assert "Malformed" in result.json()["detail"]
