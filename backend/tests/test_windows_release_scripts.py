"""Release copying must work with spaces and keep local runtime data private."""

from pathlib import Path
import shutil
import subprocess
import sys

import pytest


ROOT = Path(__file__).resolve().parents[2]
POWERSHELL = shutil.which("powershell.exe")
pytestmark = pytest.mark.skipif(sys.platform != "win32" or not POWERSHELL, reason="Windows PowerShell smoke")


def run_script(script: Path, *arguments: str) -> subprocess.CompletedProcess:
    return subprocess.run(
        [POWERSHELL, "-NoProfile", "-ExecutionPolicy", "Bypass", "-File", str(script), *arguments],
        cwd=script.parent.parent.parent, capture_output=True, text=True, timeout=30,
    )


@pytest.fixture
def release_source(tmp_path):
    root = tmp_path / "source with spaces"
    (root / "scripts").mkdir(parents=True)
    for name in ("smoke-install.ps1", "windows-common.ps1"):
        shutil.copyfile(ROOT / "scripts" / name, root / "scripts" / name)
    (root / "README.md").write_text("release source", encoding="utf-8")
    (root / ".gitattributes").write_text("* text=auto\n", encoding="utf-8")
    for name in (".github/workflows/deploy-showcase.yml", "backend/roadlens/source.py", "frontend/src/main.tsx", "frontend/public/example.json",
                 "examples/traffic/synthetic.json", "docs/setup.md", "third_party/NOTICE.md"):
        path = root / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text("portable source", encoding="utf-8")
    for name in (".env", "data/private-video.mp4", "models/vehicle_detector.onnx", ".venv/private.txt",
                 "frontend/node_modules/cache.txt", "frontend/dist/index.html", "frontend/dist-showcase/index.html",
                 "backend/__pycache__/source.pyc", "scripts/local.log", "frontend/.env.local",
                 "backend/.venv-experiment/local.txt", "backend/.ruff_cache/local.txt", "backend/.coverage.tmp"):
        path = root / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text("must not be copied", encoding="utf-8")
    return root


def test_source_copy_preserves_nested_sources_and_excludes_runtime_files(release_source, tmp_path):
    destination = tmp_path / "isolated release with spaces"
    result = run_script(release_source / "scripts/smoke-install.ps1", "-PrepareOnly", "-DestinationDirectory", str(destination))
    assert result.returncode == 0, result.stderr
    assert (destination / "backend/roadlens/source.py").read_text(encoding="utf-8") == "portable source"
    assert (destination / "frontend/src/main.tsx").is_file()
    assert (destination / "frontend/public/example.json").is_file()
    assert (destination / "examples/traffic/synthetic.json").is_file()
    assert (destination / ".gitattributes").is_file()
    assert (destination / ".github/workflows/deploy-showcase.yml").is_file()
    assert not (destination / "data").exists()
    assert not (destination / "models").exists()
    assert not (destination / ".venv").exists()
    assert not (destination / ".env").exists()
    assert not (destination / "frontend/node_modules").exists()
    assert not (destination / "frontend/dist").exists()
    assert not (destination / "frontend/dist-showcase").exists()
    assert not (destination / "frontend/.env.local").exists()
    assert not (destination / "backend/__pycache__").exists()
    assert not (destination / "scripts/local.log").exists()
    assert not (destination / "backend/.venv-experiment").exists()
    assert not (destination / "backend/.ruff_cache").exists()
    assert not (destination / "backend/.coverage.tmp").exists()
    assert (release_source / "data/private-video.mp4").is_file()


def test_existing_smoke_directory_is_preserved(release_source, tmp_path):
    destination = tmp_path / "existing isolated checkout"
    destination.mkdir()
    marker = destination / "keep.txt"
    marker.write_text("keep", encoding="utf-8")
    result = run_script(release_source / "scripts/smoke-install.ps1", "-PrepareOnly", "-DestinationDirectory", str(destination))
    assert result.returncode != 0
    assert "already exists" in result.stderr
    assert marker.read_text(encoding="utf-8") == "keep"


def test_smoke_destination_cannot_recurse_into_copied_source(release_source):
    destination = release_source / "frontend/nested isolated checkout"
    result = run_script(release_source / "scripts/smoke-install.ps1", "-PrepareOnly", "-DestinationDirectory", str(destination))
    assert result.returncode != 0
    assert "inside a source directory" in result.stderr
    assert not destination.exists()
