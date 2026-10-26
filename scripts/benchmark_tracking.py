"""Run synthetic inference-free tracking comparison, optionally writing JSON."""

import argparse
import json
from pathlib import Path

from roadlens.tracking_benchmark import run_tracking_benchmark


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path)
    parser.add_argument("--baseline-only", action="store_true", help="Snapshot Phase 2 before tracker changes.")
    parser.add_argument("--repetitions", type=int, default=5)
    args = parser.parse_args()
    report = run_tracking_benchmark(baseline_only=args.baseline_only, timing_repetitions=args.repetitions)
    rendered = json.dumps(report, indent=2, allow_nan=False)
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(rendered + "\n", encoding="utf-8")
    for key in ("baseline", "improved"):
        if key in report:
            summary = {name: value for name, value in report[key].items() if name != "scenarios"}
            print(json.dumps({key: summary}, indent=2))
    if args.output:
        print(f"Saved synthetic report: {args.output}")
