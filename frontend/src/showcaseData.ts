import sessionText from "../../examples/traffic/synthetic_traffic_session.json?raw";
import trajectoryText from "../../examples/traffic/synthetic_trajectories.json?raw";
import classText from "../../examples/traffic/synthetic_classes.json?raw";
import flowText from "../../examples/traffic/synthetic_flow.json?raw";
import zoneText from "../../examples/traffic/synthetic_zones.json?raw";
import speedText from "../../examples/traffic/synthetic_speeds.json?raw";
import qualityText from "../../examples/traffic/synthetic_quality.json?raw";
import countingText from "../../docs/benchmarks/phase5-counting.json?raw";
import modelText from "../../docs/benchmarks/phase5-model-performance.json?raw";
import performanceText from "../../docs/benchmarks/phase5-performance.json?raw";
import sessionUrl from "../../examples/traffic/synthetic_traffic_session.json?url";
import eventsUrl from "../../examples/traffic/synthetic_events.json?url";
import trajectoryUrl from "../../examples/traffic/synthetic_trajectories.json?url";
import countingUrl from "../../docs/benchmarks/phase5-counting.json?url";
import modelUrl from "../../docs/benchmarks/phase5-model-performance.json?url";
import performanceUrl from "../../docs/benchmarks/phase5-performance.json?url";
import type { Category, Point, Track } from "./types";
import type { TrafficAnalysis, TrafficArtifact } from "./trafficTypes";

interface StoredFrame {
  index: number;
  timestamp_s: number;
  tracks: {
    id: number;
    bbox: [number, number, number, number];
    category: string;
    confidence: number;
    hits: number;
    state: string;
  }[];
}
interface TableExport<T> {
  summary: TrafficAnalysis["summary"];
  rows: T;
  warnings: string[];
}

export const showcaseArtifact = JSON.parse(sessionText) as TrafficArtifact;
export const showcaseTrajectories = JSON.parse(trajectoryText) as {
  provenance: "synthetic";
  source_id: string;
  frames: StoredFrame[];
};
const classes = JSON.parse(classText) as TableExport<
  TrafficAnalysis["classes"]
>;
const flow = JSON.parse(flowText) as TableExport<TrafficAnalysis["flow"]>;
const zones = JSON.parse(zoneText) as TableExport<TrafficAnalysis["zones"]>;
const quality = JSON.parse(qualityText) as TableExport<
  TrafficAnalysis["quality"]
>;
const speeds = JSON.parse(speedText) as TableExport<
  ({ row_type: string } & TrafficAnalysis["speeds"])[]
>;
const overallSpeed = speeds.rows.find((row) => row.row_type === "overall")!;
const directionCounts = new Map<string, { label: string; count: number }>();
for (const event of showcaseArtifact.events.filter(
  (event) => event.status === "counted",
)) {
  const current = directionCounts.get(event.direction);
  directionCounts.set(event.direction, {
    label: event.direction_label || event.direction,
    count: (current?.count ?? 0) + 1,
  });
}
const speedDistribution = new Map<number, number>();
for (const measurement of showcaseArtifact.measurements ?? []) {
  if (
    measurement.status !== "valid" ||
    measurement.estimated_speed_kmh === null
  )
    continue;
  const start = Math.floor(measurement.estimated_speed_kmh / 10) * 10;
  speedDistribution.set(start, (speedDistribution.get(start) ?? 0) + 1);
}

export const showcaseAnalysis: TrafficAnalysis = {
  schema_version: 1,
  interval_minutes: 1,
  summary: classes.summary,
  events: showcaseArtifact.events,
  classes: classes.rows,
  directions: [...directionCounts].map(([direction, value]) => ({
    direction,
    direction_label: value.label,
    count: value.count,
  })),
  flow: flow.rows,
  zones: zones.rows,
  speeds: {
    ...overallSpeed,
    distribution: [...speedDistribution]
      .sort(([a], [b]) => a - b)
      .map(([start, count]) => ({
        start_kmh: start,
        end_kmh: start + 10,
        count,
      })),
    by_class: [],
    by_direction: [],
    by_interval: [],
  },
  comparisons: [],
  quality: quality.rows,
  occupancy: showcaseArtifact.occupancy_samples ?? [],
  warnings: classes.warnings,
};

export const showcaseBenchmarks = {
  counting: JSON.parse(countingText) as {
    scenario_count: number;
    expectations_met: number;
    expected_crossings: number;
    actual_crossings: number;
    actual_suppressed: number;
  },
  model: JSON.parse(modelText) as {
    hardware: { cpu: string };
    frames: number;
    input_size: number;
    timings: Record<string, { mean_ms: number; p95_ms: number }>;
  },
  traffic: JSON.parse(performanceText) as {
    workload: { dense_frames: number; dense_tracks_per_frame: number };
    dense_traffic_per_frame: { mean_ms: number; p95_ms: number };
  },
};

export const showcaseDownloads = [
  { label: "Synthetic traffic session", url: sessionUrl },
  { label: "Synthetic crossing export", url: eventsUrl },
  { label: "Synthetic trajectory inputs", url: trajectoryUrl },
  { label: "Counting benchmark report", url: countingUrl },
  { label: "Actual-model still replay report", url: modelUrl },
  { label: "32-track software profile", url: performanceUrl },
];

export function showcaseTracks(frameIndex: number): Track[] {
  const frame = showcaseTrajectories.frames[frameIndex];
  return frame.tracks
    .filter((track) =>
      ["car", "truck", "bus", "motorcycle"].includes(track.category),
    )
    .map((track) => ({
      ...track,
      category: track.category as Category,
      missed: 0,
      history: showcaseTrajectories.frames
        .slice(Math.max(0, frameIndex - 8), frameIndex + 1)
        .flatMap((previous) =>
          previous.tracks
            .filter((item) => item.id === track.id)
            .map((item): Point => [
              (item.bbox[0] + item.bbox[2]) / 2,
              item.bbox[3],
            ]),
        ),
      measurement_state: "uncalibrated",
    }));
}

// Drawing coordinates from scripts/run_validation.py, separate from the traffic fixture.
export const showcaseGeometry = {
  points: [
    [100, 100],
    [700, 100],
    [700, 550],
    [100, 550],
  ] as Point[],
  gateA: [
    [200, 200],
    [200, 450],
  ] as Point[],
  gateB: [
    [400, 200],
    [400, 450],
  ] as Point[],
  distance_m: 20,
  elapsed_seconds: 1.2,
};
