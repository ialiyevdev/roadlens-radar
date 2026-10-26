"""Reproduce an offline field evaluation; bundled input is explicitly synthetic."""

import argparse
import json
import tempfile
from pathlib import Path
from time import perf_counter

from roadlens.field_evaluation import evaluate_fields, field_report_csv, field_report_html
from roadlens.field_models import FieldEvaluationRequest, FieldSessionInput
from roadlens.field_store import FieldStore


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("input", nargs="?", default="examples/field/synthetic_field_session.json")
    parser.add_argument("--output", default="data/field-validation")
    args = parser.parse_args()
    data = FieldSessionInput.model_validate_json(Path(args.input).read_text(encoding="utf-8"))
    with tempfile.TemporaryDirectory() as directory:
        session = FieldStore(Path(directory)).put(data)
        request = FieldEvaluationRequest(session_ids=[session.id], partition=session.partition)
        report = evaluate_fields([session], request)
    target = Path(args.output)
    target.parent.mkdir(parents=True, exist_ok=True)
    serialization = {}
    for suffix, function in (("json", lambda report: json.dumps(report, indent=2, allow_nan=False)),
                             ("csv", field_report_csv), ("html", field_report_html)):
        started = perf_counter()
        content = function(report)
        serialization[suffix + "_generation_ms"] = (perf_counter() - started) * 1000
        target.with_suffix("." + suffix).write_text(content, encoding="utf-8")
    print(json.dumps({"provenance": report["provenance"], "session_count": report["session_count"],
                      "summary": report["validation"]["summary"], "counts": report["counts"],
                      "paired_n": report["pipeline_comparison"]["paired_n"],
                      "performance": {**report["performance"], **serialization}}, indent=2))


if __name__ == "__main__":
    main()
