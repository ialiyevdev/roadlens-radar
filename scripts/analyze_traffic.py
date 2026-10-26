"""Small dependency-free exploratory analysis of exported traffic JSON or CSV."""

import argparse
import csv
import json
import statistics
from collections import Counter
from pathlib import Path


def load_rows(path):
    with path.open(encoding="utf-8-sig", newline="") as stream:
        if path.suffix.lower() == ".csv":
            return list(csv.DictReader(stream))
        value = json.load(stream)
        return value["rows"] if isinstance(value, dict) else value


def describe(rows):
    rows = [row for row in rows if row.get("export_row_type") != "metadata"]
    counted = [row for row in rows if row.get("status") == "counted"]
    speeds = [float(row["measured_speed_kmh"]) for row in counted if row.get("measured_speed_kmh") not in (None, "")]
    return {"retained_rows": len(rows), "observed_counted_line_crossings": len(counted),
            "crossings_by_class": dict(Counter(row.get("category", "unknown") for row in counted)),
            "crossings_by_line_and_direction": dict(Counter(f"{row.get('line_id')}: {row.get('direction')}" for row in counted)),
            "crossing_attached_valid_speed_n": len(speeds),
            "crossing_attached_mean_speed_kmh": statistics.fmean(speeds) if speeds else None,
            "note": "One physical vehicle may cross several configured lines. Use the flow export's covered seconds before comparing normalized rates."}


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("events", type=Path, help="roadlens-traffic-events.json or .csv")
    args = parser.parse_args()
    print(json.dumps(describe(load_rows(args.events)), indent=2, allow_nan=False))
