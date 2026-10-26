"""Measure Phase 4 offline costs on explicit synthetic input, without a camera."""

import argparse
import json
import math
import platform
import statistics
import sys
import tempfile
from pathlib import Path
from time import perf_counter
from types import SimpleNamespace

import av
import cv2
import numpy as np

from roadlens.field_alignment import import_references, match_diagnostics
from roadlens.field_evaluation import evaluate_fields, field_report_csv, field_report_html
from roadlens.field_models import FieldEvaluationRequest, FieldSessionInput, utc_now
from roadlens.field_store import FieldStore
from roadlens.offline_video import VideoNavigator
from roadlens.timing import TimingIntegrity


def distribution(values):
    ordered = sorted(values)
    position = .95 * (len(ordered) - 1)
    low, high = math.floor(position), math.ceil(position)
    return {"n": len(values), "mean_ms": statistics.fmean(values), "median_ms": statistics.median(values),
            "p95_ms": ordered[low] + (ordered[high] - ordered[low]) * (position - low),
            "maximum_ms": max(values)}


def measure(operation, iterations):
    operation()
    samples = []
    for _ in range(iterations):
        started = perf_counter()
        operation()
        samples.append((perf_counter() - started) * 1000)
    return distribution(samples)


def generated_video(path):
    writer = cv2.VideoWriter(str(path), cv2.VideoWriter_fourcc(*"FFV1"), 25, (320, 240))
    if not writer.isOpened():
        raise RuntimeError("Could not create the synthetic FFV1 fixture.")
    for index in range(120):
        image = np.full((240, 320, 3), 24, np.uint8)
        cv2.rectangle(image, (10 + index, 100), (50 + index, 150), (100, 180, 230), -1)
        cv2.putText(image, "SYNTHETIC SOFTWARE TEST", (6, 22), cv2.FONT_HERSHEY_SIMPLEX, .5, (255, 255, 255), 1)
        writer.write(image)
    writer.release()


def navigation_profile(path, iterations):
    profiles = {}
    for name, before, target in (("uncached_forward_to_frame_120", None, 120),
                                  ("sequential_next_frame", 20, 21),
                                  ("cached_previous_frame", 20, 19),
                                  ("uncached_previous_to_frame_1", 120, 1)):
        samples = []
        for _ in range(iterations):
            navigator = VideoNavigator(path)
            try:
                if before is not None:
                    navigator.image(before)
                started = perf_counter()
                navigator.image(target)
                samples.append((perf_counter() - started) * 1000)
            finally:
                navigator.close()
        profiles[name] = distribution(samples)
    index_times = []
    for _ in range(iterations):
        started = perf_counter()
        navigator = VideoNavigator(path)
        index_times.append((perf_counter() - started) * 1000)
        navigator.close()
    profiles["metadata_index_120_frames"] = distribution(index_times)
    return profiles


def timestamp_profile(iterations):
    packets = [SimpleNamespace(index=i + 1, timestamp_s=i / 25, raw_timestamp_s=i / 25,
                               timestamp_issue=None, time_base="1/25", acquired_at=100 + i / 25,
                               decoded_at=100 + i / 25 + .001, decode_ms=1.0, timing_warning=None)
               for i in range(1000)]
    def source_batch():
        integrity = TimingIntegrity()
        for packet in packets:
            integrity.source(packet)
    def processed_batch():
        integrity = TimingIntegrity()
        for packet in packets:
            integrity.processed(packet, packet.acquired_at + .01)
    source = measure(source_batch, iterations)
    processed = measure(processed_batch, iterations)
    integrity = TimingIntegrity()
    for packet in packets:
        integrity.source(packet)
        integrity.processed(packet, packet.acquired_at + .01)
    return {"source_batch_1000_frames": source, "processed_batch_1000_frames": processed,
            "mean_source_per_frame_ms": source["mean_ms"] / 1000,
            "mean_processed_per_frame_ms": processed["mean_ms"] / 1000,
            "snapshot_rolling_240_latencies": measure(integrity.snapshot, iterations)}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--iterations", type=int, default=30)
    parser.add_argument("--output", default="data/phase4-field-performance.json")
    args = parser.parse_args()
    if not 3 <= args.iterations <= 1000:
        parser.error("Use between 3 and 1000 iterations.")
    root = Path(__file__).resolve().parents[1]
    example = root / "examples/field/synthetic_field_session.json"
    references = (root / "examples/field/synthetic_reference_events.csv").read_bytes()
    with tempfile.TemporaryDirectory() as directory:
        temporary = Path(directory)
        session = FieldStore(temporary / "sessions").put(FieldSessionInput.model_validate_json(example.read_text(encoding="utf-8")))
        request = FieldEvaluationRequest(session_ids=[session.id])
        report = evaluate_fields([session], request)
        result = {"measured_at": utc_now().isoformat(), "evidence": "synthetic software workload; no physical camera, roadway or independent reference device tested",
                  "hardware": {"processor": platform.processor(), "machine": platform.machine(), "platform": platform.platform()},
                  "software": {"python": sys.version.split()[0], "opencv": cv2.__version__, "pyav": av.__version__},
                  "method": {"iterations": args.iterations, "warmup": "One untimed call for stateless operations; new decoders for navigation trials",
                             "clock": "perf_counter", "percentile": "P95 linear interpolation at (n-1)*0.95",
                             "video": "120 generated FFV1 frames, 320x240, 25 fps, labeled synthetic",
                             "field": "6 original events, 4 eligible comparisons, 4 baseline/improved pairs, 7 references",
                             "limitations": "Tiny cached local workload, variable scheduling/I/O; excludes ML inference, live capture, HTTP and browser rendering. Not a throughput or real-camera guarantee."},
                  "reference_import_7_events": measure(lambda: import_references(references, "synthetic.csv"), args.iterations),
                  "explicit_matching_one_event": measure(lambda: match_diagnostics(session, "event-001"), args.iterations),
                  "evaluation_complete_fixture": measure(lambda: evaluate_fields([session], request), args.iterations),
                  "report_json": measure(lambda: json.dumps(report, indent=2, allow_nan=False), args.iterations),
                  "report_csv": measure(lambda: field_report_csv(report), args.iterations),
                  "report_html": measure(lambda: field_report_html(report), args.iterations),
                  "timestamp_diagnostics": timestamp_profile(args.iterations)}
        video = temporary / "SYNTHETIC_navigation.avi"
        generated_video(video)
        result["annotation_navigation"] = navigation_profile(video, args.iterations)
    target = Path(args.output)
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(json.dumps(result, indent=2, allow_nan=False), encoding="utf-8")
    print(json.dumps(result, indent=2, allow_nan=False))


if __name__ == "__main__":
    main()
