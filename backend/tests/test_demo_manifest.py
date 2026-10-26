"""Release assets retain their reviewed bytes, rights and evidence categories."""

import hashlib
import json
from pathlib import Path, PurePosixPath


ROOT = Path(__file__).resolve().parents[2]
MANIFEST = ROOT / "examples" / "demo" / "manifest.json"


def manifest():
    return json.loads(MANIFEST.read_text(encoding="utf-8"))


def test_demo_asset_paths_and_bytes_are_portable_and_intact():
    assets = manifest()["assets"]
    assert assets
    assert len({asset["filename"] for asset in assets}) == len(assets)
    for asset in assets:
        filename = asset["filename"]
        relative = PurePosixPath(filename)
        assert not relative.is_absolute() and ".." not in relative.parts
        assert "\\" not in filename and ":" not in filename
        target = (ROOT / filename).resolve()
        assert target.is_relative_to(ROOT)
        content = target.read_bytes()
        assert len(content) == asset["bytes"], filename
        assert hashlib.sha256(content).hexdigest() == asset["sha256"], filename


def test_demo_assets_keep_explicit_rights_and_no_independent_field_truth_claim():
    for asset in manifest()["assets"]:
        for key in ("source", "author_or_provider", "license", "attribution", "redistribution_permission",
                    "data_kind", "ground_truth_notes", "showcase_usage"):
            assert asset[key], (asset["filename"], key)
        assert asset["license"] in {"MIT", "CC0-1.0", "MIT AND CC0-1.0"}
        assert asset["redistribution_permission"] == "permitted_under_declared_license"
        assert asset["independent_ground_truth"] is False


def test_showcase_inputs_remain_synthetic_and_still_replay_is_distinct():
    assets = {asset["filename"]: asset for asset in manifest()["assets"]}
    for filename, asset in assets.items():
        if filename.startswith("examples/traffic/"):
            assert asset["data_kind"] == "synthetic"
            value = json.loads((ROOT / filename).read_text(encoding="utf-8"))
            assert "synthetic" in json.dumps(value).lower()
    replay = assets["docs/benchmarks/phase5-model-performance.json"]
    still = assets["backend/tests/fixtures/city_traffic_cc0.jpg"]
    assert replay["data_kind"] == "recorded_still_replay_with_synthetic_regions"
    assert still["data_kind"] == "recorded_still"
    assert still["license"] == "CC0-1.0"
    assert still["showcase_usage"] == "separate_inference_fixture"


def test_manifest_covers_the_stored_showcase_contract():
    assets = {asset["filename"] for asset in manifest()["assets"]}
    expected = {"examples/traffic/synthetic_traffic_session.json", "examples/traffic/synthetic_trajectories.json"}
    expected.update(f"examples/traffic/synthetic_{table}.json"
                    for table in ("events", "classes", "flow", "zones", "speeds", "quality"))
    expected.update(f"docs/benchmarks/{name}.json"
                    for name in ("phase5-counting", "phase5-performance", "phase5-model-performance"))
    assert expected <= assets
