"""Create an explicitly synthetic traffic artifact and optional moving-shape video."""

import argparse
import json
from pathlib import Path
from uuid import UUID

from benchmark_traffic import SOURCE, configuration, track
from roadlens.traffic_analytics import analyze_traffic, traffic_export
from roadlens.traffic_engine import TrafficEngine


def make_fixture():
    config = configuration()
    session_id = str(UUID(int=5005))
    engine = TrafficEngine(session_id, SOURCE, config.geometry, config, "synthetic")
    categories = ["car", "truck", "bus", "motorcycle", "car", "unsupported"]
    frames = []
    for index in range(120):
        timestamp = index / 2
        tracks = [track(identity + 1, 45 + identity * 20, 10 + (timestamp - identity * 10) * 14, category)
                  for identity, category in enumerate(categories) if 0 <= timestamp - identity * 10 <= 7]
        engine.update(tracks, timestamp, frame_index=index + 1)
        frames.append({"index": index + 1, "timestamp_s": timestamp, "tracks": tracks})
    snapshot = engine.snapshot()
    snapshot.update(name="SYNTHETIC traffic intelligence example",
                    description="Generated moving-shape trajectories and scripted metric-speed values. This is software arithmetic evidence, not camera accuracy.",
                    started_at="2026-10-24T09:00:00+00:00", ended_at="2026-10-24T09:00:59.500000+00:00",
                    measurements=[])
    for event, speed, status in zip(snapshot["events"], [28, 36, 44, 32, 50, 18],
                                   ["valid", "valid", "approximate", "valid", "rejected", "valid"]):
        snapshot["measurements"].append({"id": f"synthetic-speed-{event['track_id']}", "session_id": session_id,
            "source_id": SOURCE, "track_id": event["track_id"], "timestamp_s": event["timestamp_s"] + 1,
            "category": event["category"], "direction": "A_to_B", "status": status,
            "estimated_speed_kmh": speed, "calibration_id": "synthetic-scripted-road", "independently_validated": False,
            "reasons": ["SYNTHETIC scripted value for aggregate arithmetic"]})
        if status == "valid":
            event["measured_speed_kmh"] = speed
            event["speed_measurement_id"] = f"synthetic-speed-{event['track_id']}"
    return snapshot, frames


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, default=Path("examples/traffic"))
    parser.add_argument("--video", type=Path, help="Optional FFV1 moving-shape clip; no detector performance is implied.")
    args = parser.parse_args()
    artifact, frames = make_fixture()
    args.output.mkdir(parents=True, exist_ok=True)
    (args.output / "synthetic_traffic_session.json").write_text(json.dumps(artifact, indent=2, allow_nan=False) + "\n", encoding="utf-8", newline="\n")
    (args.output / "synthetic_trajectories.json").write_text(json.dumps({"provenance": "synthetic", "source_id": SOURCE, "frames": frames}, indent=2) + "\n", encoding="utf-8", newline="\n")
    report = analyze_traffic([artifact])
    for table in ("events", "classes", "flow", "zones", "speeds", "comparisons", "quality"):
        for format in ("json", "csv"):
            (args.output / f"synthetic_{table}.{format}").write_text(traffic_export(report, table, format), encoding="utf-8", newline="\n")
    if args.video:
        import cv2
        import numpy as np
        args.video.parent.mkdir(parents=True, exist_ok=True)
        writer = cv2.VideoWriter(str(args.video), cv2.VideoWriter_fourcc(*"FFV1"), 2, (200, 120))
        if not writer.isOpened():
            raise RuntimeError("Could not create the requested FFV1 fixture video.")
        try:
            for frame in frames:
                image = np.full((120, 200, 3), 25, np.uint8)
                cv2.putText(image, "SYNTHETIC SHAPES", (5, 13), cv2.FONT_HERSHEY_SIMPLEX, .4, (255, 255, 255), 1)
                for item in frame["tracks"]:
                    left, top, right, bottom = map(round, item["bbox"])
                    cv2.rectangle(image, (left, top), (right, bottom), (40, 180, 230), -1)
                writer.write(image)
        finally:
            writer.release()
    print(json.dumps(report["summary"], indent=2))
