"""Evaluate a CSV/JSON independent-reference dataset without running inference."""

import argparse
from pathlib import Path

from roadlens.validation import evaluate, example_dataset, import_dataset, report_csv
from roadlens.validation_models import EvaluationRequest, ValidationOptions


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("dataset", nargs="?", type=Path, help="UTF-8 JSON or CSV; omitted uses the synthetic example")
    parser.add_argument("--output", type=Path, help="Write full JSON report here")
    parser.add_argument("--csv-output", type=Path, help="Write per-event comparison CSV here")
    parser.add_argument("--tolerance", type=float, action="append", help="Repeat for each tolerance band in km/h")
    parser.add_argument("--minimum-samples", type=int, default=3)
    args = parser.parse_args()
    dataset = import_dataset(args.dataset.read_bytes(), args.dataset.name) if args.dataset else example_dataset()
    options = ValidationOptions(tolerance_bands_kmh=args.tolerance or [3, 5], minimum_group_samples=args.minimum_samples)
    report = evaluate(EvaluationRequest(dataset=dataset, options=options))
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(report.model_dump_json(indent=2) + "\n", encoding="utf-8")
    if args.csv_output:
        args.csv_output.parent.mkdir(parents=True, exist_ok=True)
        args.csv_output.write_text(report_csv(report), encoding="utf-8")
    print(report.model_dump_json(indent=2, exclude={"rows"}))


if __name__ == "__main__":
    main()
