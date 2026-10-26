"""Release contracts that also work in an uncommitted, relocated source copy."""

import importlib.util
from pathlib import Path

from fastapi.testclient import TestClient

from roadlens import __version__
from roadlens.api import create_app
from roadlens.session import SessionManager


ROOT = Path(__file__).resolve().parents[2]
spec = importlib.util.spec_from_file_location("check_release", ROOT / "scripts/check_release.py")
release = importlib.util.module_from_spec(spec)
spec.loader.exec_module(release)


def test_release_versions_agree():
    assert release.version_errors(ROOT) == []


def test_documentation_links_resolve_inside_release():
    assert release.markdown_errors(ROOT, release.source_files(ROOT)) == []


def test_scan_reports_categories_without_exposing_values(tmp_path):
    path = tmp_path / "settings.py"
    private_value = "example" + "credential" + "for-scanner"
    key = "api" + "_key"
    path.write_text(key + " = " + repr(private_value), encoding="utf-8")
    errors = release.source_errors(tmp_path, [path])
    assert errors == ["settings.py: possible credential assignment"]
    assert private_value not in str(errors)


def test_link_checks_reject_missing_and_escaping_targets_with_spaces(tmp_path):
    root = tmp_path / "source with spaces"
    root.mkdir()
    page = root / "README.md"
    (root / "real file.md").write_text("ok", encoding="utf-8")
    page.write_text("[valid](real%20file.md) [missing](gone.md) [outside](../outside.md)", encoding="utf-8")
    errors = release.markdown_errors(root, [page])
    assert len(errors) == 2
    assert all("real%20file" not in error for error in errors)


def test_api_release_metadata_does_not_disclose_home_or_open_sources(tmp_path, monkeypatch):
    calls = []
    root = tmp_path / "source with spaces"
    root.mkdir()
    weights = root / "models" / "vehicle_detector.onnx"
    manager = SessionManager(weights_path=weights, upload_dir=root / "data/uploads",
                             calibration_dir=root / "data/calibrations",
                             source_factory=lambda *args: calls.append(args))
    monkeypatch.chdir(tmp_path)
    with TestClient(create_app(manager), base_url="http://127.0.0.1:8000") as client:
        health = client.get("/api/health")
        assert health.status_code == 200
        assert health.json()["version"] == __version__
        assert health.json()["model"]["path"] == "vehicle_detector.onnx"
        assert str(root) not in health.text
        assert client.get("/openapi.json").json()["info"]["version"] == __version__
        assert client.get("/api/session").json()["state"] == "idle"
        assert client.get("/api/traffic/current").json()["snapshot"] is None
        assert calls == []
