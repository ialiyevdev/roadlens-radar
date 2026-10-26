"""The Pages release contains only reviewed standalone showcase artifacts."""

import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import subprocess

import pytest


ROOT = Path(__file__).resolve().parents[2]
NODE = shutil.which("node")
pytestmark = pytest.mark.skipif(not NODE, reason="Node.js is required for static artifact checks")
SCREENSHOTS = ("phase6-showcase.png", "phase6-showcase-mobile.png", "phase6-dashboard.png")
NOTICES = ("LICENSE", "third_party/NOTICE.md", "third_party/opencv_yolox_LICENSE.txt",
           "backend/tests/fixtures/README.md", "frontend/node_modules/react/LICENSE",
           "frontend/node_modules/react-dom/LICENSE", "frontend/node_modules/scheduler/LICENSE")


def prepare(source, output):
    script = (
        "const { prepareShowcase } = await import(process.argv[1]); "
        "await prepareShowcase({root:process.argv[2],directory:process.argv[3]});"
    )
    return subprocess.run([NODE, "--input-type=module", "-e", script,
                           (ROOT / "scripts/prepare_showcase.mjs").as_uri(), str(source), str(output)],
                          capture_output=True, text=True, timeout=20)


def check(output, base="/roadlens-radar/"):
    return subprocess.run([NODE, str(ROOT / "scripts/check_showcase.mjs"), "--directory", str(output),
                           "--base", base], capture_output=True, text=True, timeout=20)


@pytest.fixture
def artifact_factory(tmp_path):
    def create(base="/roadlens-radar/"):
        source = tmp_path / "source with spaces"
        output = tmp_path / "static output with spaces"
        (output / "assets").mkdir(parents=True)
        for name in NOTICES:
            target = source / name
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_text("Preserved license or attribution fixture\n", encoding="utf-8")
        assets = []
        for name in SCREENSHOTS:
            content = bytes([137, 80, 78, 71, 13, 10, 26, 10]) + name.encode()
            filename = "docs/screenshots/" + name
            target = source / filename
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes(content)
            assets.append({"filename": filename, "bytes": len(content),
                           "sha256": hashlib.sha256(content).hexdigest(),
                           "redistribution_permission": "permitted_under_declared_license"})
        manifest = source / "examples/demo/manifest.json"
        manifest.parent.mkdir(parents=True)
        manifest.write_text(json.dumps({"assets": assets}), encoding="utf-8")
        (output / "index.html").write_text(
            f'<script src="{base}assets/index-abcd1234.js"></script>'
            f'<link href="{base}favicon.svg">', encoding="utf-8")
        (output / "favicon.svg").write_text("<svg></svg>", encoding="utf-8")
        (output / "assets/index-abcd1234.js").write_text('import("./StaticShowcase-abcd1234.js");', encoding="utf-8")
        download = 'new URL("example-abcd1234.json",import.meta.url).href' if base == "./" else f'"{base}assets/example-abcd1234.json"'
        (output / "assets/StaticShowcase-abcd1234.js").write_text(
            f'const download={download};', encoding="utf-8")
        (output / "assets/example-abcd1234.json").write_text('{"provenance":"synthetic"}', encoding="utf-8")
        return source, output
    return create


@pytest.mark.parametrize("base", ["/roadlens-radar/", "./"])
def test_reviewed_packaging_and_artifact_checks_work_with_spaces_and_bases(artifact_factory, base):
    source, output = artifact_factory(base)
    result = prepare(source, output)
    assert result.returncode == 0, result.stderr
    result = check(output, base)
    assert result.returncode == 0, result.stderr
    assert "3 screenshots" in result.stdout
    assert (output / "notices/npm/react-LICENSE.txt").read_bytes() == (source / "frontend/node_modules/react/LICENSE").read_bytes()
    assert not (output / "backend").exists()
    assert not (output / "node_modules").exists()


def test_packaging_refuses_screenshot_changes_before_copying(artifact_factory):
    source, output = artifact_factory()
    (source / "docs/screenshots/phase6-dashboard.png").write_bytes(b"unreviewed pixels")
    result = prepare(source, output)
    assert result.returncode != 0
    assert "differs from the reviewed manifest" in result.stderr
    assert not (output / "screenshots").exists()


def test_checker_rejects_backend_access_in_static_javascript(artifact_factory):
    source, output = artifact_factory()
    assert prepare(source, output).returncode == 0
    (output / "assets/StaticShowcase-abcd1234.js").write_text('fetch("/api/session")', encoding="utf-8")
    result = check(output)
    assert result.returncode != 0
    assert "Backend or camera access" in result.stderr


@pytest.mark.parametrize("problem", ["base", "download", "notice", "screenshot", "private"])
def test_checker_rejects_broken_or_unreviewed_artifacts(artifact_factory, problem):
    source, output = artifact_factory()
    assert prepare(source, output).returncode == 0
    if problem == "base":
        page = output / "index.html"
        page.write_text(page.read_text(encoding="utf-8").replace("/roadlens-radar/", "/"), encoding="utf-8")
    elif problem == "download":
        (output / "assets/example-abcd1234.json").unlink()
    elif problem == "notice":
        (output / "notices/npm/react-LICENSE.txt").unlink()
    elif problem == "screenshot":
        (output / "screenshots/phase6-dashboard.png").write_bytes(b"changed")
    else:
        (output / "data").mkdir()
        (output / "data/private.mp4").write_bytes(b"test fixture")
    result = check(output)
    assert result.returncode != 0


def test_checker_rejects_hard_links_in_pages_artifact(artifact_factory):
    source, output = artifact_factory()
    assert prepare(source, output).returncode == 0
    try:
        os.link(output / "assets/index-abcd1234.js", output / "assets/linked-abcd1234.js")
    except OSError:
        pytest.skip("Filesystem does not support hard links")
    result = check(output)
    assert result.returncode != 0
    assert "Links are not allowed" in result.stderr


def test_workflow_uploads_only_verified_showcase_with_official_pinned_actions():
    workflow = (ROOT / ".github/workflows/deploy-showcase.yml").read_text(encoding="utf-8")
    actions = re.findall(r"uses: (actions/[a-z-]+)@([0-9a-f]{40})", workflow)
    assert {name for name, _ in actions} == {
        "actions/checkout", "actions/setup-node", "actions/configure-pages",
        "actions/upload-pages-artifact", "actions/deploy-pages"}
    assert "branches: [main]" in workflow and "workflow_dispatch:" in workflow
    assert "node-version: '24.16.0'" in workflow
    assert "run: npm ci" in workflow
    assert "run: npm run build:showcase -- --base=/roadlens-radar/" in workflow
    assert "run: node scripts/check_showcase.mjs --directory frontend/dist-showcase --base /roadlens-radar/" in workflow
    assert "path: frontend/dist-showcase" in workflow
    assert "needs: build" in workflow and "name: github-pages" in workflow
    build, deploy = workflow.split("\n  deploy:\n")
    assert "id-token: write" not in build and "pages: write" not in build
    assert "id-token: write" in deploy and "pages: write" in deploy
    assert "contents: write" not in workflow and "setup-python" not in workflow
