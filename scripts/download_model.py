#!/usr/bin/env python3
"""Download and verify RoadLens's pinned, Apache-2.0 vehicle detector."""

from __future__ import annotations

import argparse
import hashlib
import os
from pathlib import Path
import sys
import tempfile
import urllib.error
import urllib.parse
import urllib.request


REVISION = "48b10fa505aeb51fbd127fc60a5c660040e823b7"
MODEL_NAME = "object_detection_yolox_2022nov_int8bq.onnx"
MODEL_URL = (
    "https://media.githubusercontent.com/media/opencv/opencv_zoo/"
    f"{REVISION}/models/object_detection_yolox/{MODEL_NAME}"
)
EXPECTED_SHA256 = "dcaae0aaa2fea4167f89235ee340eb869d3707b25712218d4c7ce921ac90e2ba"
EXPECTED_BYTES = 9_744_418
DEFAULT_OUTPUT = Path(__file__).resolve().parents[1] / "models" / "vehicle_detector.onnx"
CHUNK_BYTES = 128 * 1024


def verified(path: Path) -> bool:
    """Accept only the exact, pinned artifact, including its expected size."""
    if not path.is_file() or path.stat().st_size != EXPECTED_BYTES:
        return False
    with path.open("rb") as stream:
        return hashlib.file_digest(stream, "sha256").hexdigest() == EXPECTED_SHA256


def download_model(output: Path = DEFAULT_OUTPUT) -> Path:
    output = output.expanduser().resolve()
    if output.exists():
        if not verified(output):
            raise ValueError(
                f"Existing model does not match the pinned artifact: {output}. "
                "Remove that file and rerun this script to download a verified copy."
            )
        print(f"Verified existing model: {output}")
        return output

    output.parent.mkdir(parents=True, exist_ok=True)
    temporary_path: Path | None = None
    request = urllib.request.Request(MODEL_URL, headers={"User-Agent": "RoadLens-Radar/0.1"})
    print(f"Downloading YOLOX-S INT8 block-quantized model ({EXPECTED_BYTES:,} bytes)...")
    try:
        with urllib.request.urlopen(request, timeout=30) as response:
            if urllib.parse.urlparse(response.geturl()).scheme != "https":
                raise ValueError("Model download redirected to a non-HTTPS address.")
            declared_size = response.headers.get("Content-Length")
            if declared_size is not None and int(declared_size) != EXPECTED_BYTES:
                raise ValueError("Download length does not match the pinned model.")
            digest = hashlib.sha256()
            downloaded = 0
            with tempfile.NamedTemporaryFile(
                mode="wb", dir=output.parent, prefix=f"{output.name}.", suffix=".part", delete=False
            ) as destination:
                temporary_path = Path(destination.name)
                while chunk := response.read(CHUNK_BYTES):
                    downloaded += len(chunk)
                    if downloaded > EXPECTED_BYTES:
                        raise ValueError("Download exceeded the pinned model's size limit.")
                    destination.write(chunk)
                    digest.update(chunk)
                destination.flush()
                os.fsync(destination.fileno())

        if downloaded != EXPECTED_BYTES or digest.hexdigest() != EXPECTED_SHA256:
            raise ValueError("Downloaded model failed size or SHA-256 verification.")
        os.replace(temporary_path, output)
        temporary_path = None
    finally:
        if temporary_path is not None:
            temporary_path.unlink(missing_ok=True)

    print(f"Verified model saved to: {output}")
    print(f"SHA-256: {EXPECTED_SHA256}")
    return output


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT, help="Destination ONNX file")
    args = parser.parse_args()
    try:
        download_model(args.output)
    except (OSError, ValueError, urllib.error.URLError) as error:
        print(f"Model download failed: {error}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
