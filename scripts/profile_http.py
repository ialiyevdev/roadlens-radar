"""Measure idle localhost session responses; does not open a camera or source."""

import argparse
import json
from pathlib import Path
from statistics import fmean, median
from time import perf_counter
from urllib.request import urlopen

import numpy as np


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--port", type=int, default=8000)
    parser.add_argument("--requests", type=int, default=20)
    parser.add_argument("--output", type=Path, default=Path("data/profiling/http.json"))
    args = parser.parse_args()
    if not (1 <= args.port <= 65535 and 3 <= args.requests <= 1000):
        parser.error("Use a valid localhost port and 3–1000 requests.")
    setup, roundtrip = [], []
    payload_bytes = 0
    for index in range(args.requests + 3):
        started = perf_counter()
        with urlopen(f"http://127.0.0.1:{args.port}/api/session", timeout=10) as response:
            payload = response.read()
            sample = float(response.headers["X-RoadLens-Response-Ms"])
        elapsed_ms = (perf_counter() - started) * 1000
        if index >= 3:
            setup.append(sample)
            roundtrip.append(elapsed_ms)
            payload_bytes = len(payload)
    state = json.loads(payload)["state"]
    report = {"workload": "Local HTTP GET /api/session; 3 warm-up requests, sequential new client connections.",
              "source_state": state, "requests": args.requests, "payload_bytes": payload_bytes,
              "server_setup_ms": {"mean": fmean(setup), "median": median(setup), "p95": float(np.percentile(setup, 95))},
              "client_roundtrip_ms": {"mean": fmean(roundtrip), "median": median(roundtrip), "p95": float(np.percentile(roundtrip, 95))},
              "limits": "One local run on the documented host. Server header timing ends at response setup, before body transfer. Client timing includes loopback connection/read overhead. Idle results do not characterize a running or full-history session."}
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, indent=2), encoding="utf-8")
    print(json.dumps(report, indent=2))


if __name__ == "__main__":
    main()
