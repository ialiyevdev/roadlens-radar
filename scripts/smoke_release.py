"""Exercise a source-only installation without a camera or developer data."""

from __future__ import annotations

import argparse
from datetime import datetime, timezone
import hashlib
import importlib.metadata
import json
from pathlib import Path
import socket
import subprocess
import sys
import time
import urllib.error
import urllib.request

import cv2
import roadlens

from roadlens.detector import RoadLensDetector


ROOT = Path(__file__).resolve().parents[1]
MODEL_SHA256 = "dcaae0aaa2fea4167f89235ee340eb869d3707b25712218d4c7ce921ac90e2ba"


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--report", type=Path, default=ROOT / "data" / "release-smoke.json")
    args = parser.parse_args()
    if not Path(roadlens.__file__).resolve().is_relative_to(ROOT):
        raise RuntimeError("roadlens was imported from outside this isolated source copy")
    model = ROOT / "models" / "vehicle_detector.onnx"
    digest = hashlib.sha256(model.read_bytes()).hexdigest()
    if digest != MODEL_SHA256:
        raise RuntimeError("The isolated model does not match the pinned SHA-256")
    frame = cv2.imread(str(ROOT / "backend" / "tests" / "fixtures" / "city_traffic_cc0.jpg"))
    detections = RoadLensDetector(model).detect(frame)
    if not detections:
        raise RuntimeError("The real detector did not detect vehicles on the licensed test still")

    with socket.socket() as available:
        available.bind(("127.0.0.1", 0))
        port = available.getsockname()[1]
    args.report.parent.mkdir(parents=True, exist_ok=True)
    log_path = args.report.with_suffix(".log")

    def request(path: str, payload: dict | None = None) -> dict:
        body = json.dumps(payload).encode() if payload is not None else None
        message = urllib.request.Request(
            f"http://127.0.0.1:{port}{path}", data=body,
            headers={"Content-Type": "application/json"} if body is not None else {},
        )
        with urllib.request.urlopen(message, timeout=10) as response:
            return json.load(response)

    with log_path.open("w", encoding="utf-8") as log:
        server = subprocess.Popen(
            [sys.executable, "-m", "uvicorn", "roadlens.api:app", "--host", "127.0.0.1", "--port", str(port)],
            cwd=ROOT, stdout=log, stderr=subprocess.STDOUT,
            creationflags=subprocess.CREATE_NO_WINDOW if sys.platform == "win32" else 0,
        )
        try:
            deadline = time.monotonic() + 30
            while True:
                if server.poll() is not None:
                    raise RuntimeError("The isolated backend exited before becoming healthy; inspect the local smoke log")
                try:
                    health = request("/api/health")
                    break
                except (urllib.error.URLError, TimeoutError):
                    if time.monotonic() >= deadline:
                        raise RuntimeError("The isolated backend did not become healthy within 30 seconds")
                    time.sleep(0.2)
            if health["status"] != "ok" or not health["model"]["ready"]:
                raise RuntimeError("Isolated API did not report the model ready")
            example = request("/api/traffic/example")
            if example["provenance"] != "synthetic":
                raise RuntimeError("The stored demonstration must be labeled synthetic")
            saved = request("/api/traffic/example", {})
            analysis = request("/api/traffic/analytics", {"session_ids": [saved["id"]]})
            if analysis["summary"]["total_crossings"] != 6 or analysis["speeds"]["n"] != 4:
                raise RuntimeError("The supplied synthetic traffic example did not reproduce its expected results")
            if analysis["speeds"]["mean_kmh"] != 28.5:
                raise RuntimeError("Synthetic scripted speed summary changed unexpectedly")
        finally:
            server.terminate()
            try:
                server.wait(timeout=10)
            except subprocess.TimeoutExpired:
                server.kill()
                server.wait(timeout=5)

    report = {
        "generated_at_utc": datetime.now(timezone.utc).isoformat(),
        "verification_scope": "isolated source copy on the existing Windows machine; not an external clean machine",
        "python_version": sys.version.split()[0],
        "project_version": importlib.metadata.version("roadlens-radar"),
        "imports_from_isolated_copy": True,
        "model_sha256": digest,
        "actual_model_still_detections": len(detections),
        "live_loopback_api": "passed",
        "stored_synthetic_example": {"crossings": 6, "scripted_speed_records": 4, "scripted_mean_kmh": 28.5},
        "camera_used": False,
        "independent_roadway_accuracy_verified": False,
    }
    args.report.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(report, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
