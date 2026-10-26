import type { ImageGeometry, Point, SpeedMeasurement } from "./types";

export interface CountingLine {
  id: string;
  label: string;
  start: Point;
  end: Point;
  positive_label: string;
  negative_label: string;
  hysteresis_px: number;
}
export interface TrafficZone {
  id: string;
  label: string;
  points: Point[];
  coordinate_space: "image" | "ground";
  hysteresis: number;
}
export interface TrafficConfiguration {
  id: string;
  name: string;
  source_id: string;
  geometry: ImageGeometry;
  calibration_id: string | null;
  lines: CountingLine[];
  zones: TrafficZone[];
  max_gap_s: number;
  min_track_hits: number;
  class_min_observations: number;
  class_min_confidence: number;
  class_min_margin: number;
  identity_suppression_s: number;
  identity_suppression_px: number;
  stationary_window_s: number;
  stationary_radius_px: number;
  slow_speed_kmh: number;
  occupancy_moderate: number;
  occupancy_high: number;
}
export interface TrafficEvent {
  id: string;
  session_id: string;
  track_id: number;
  timestamp_s: number | null;
  line_id: string;
  line_label?: string;
  direction: string;
  direction_label?: string;
  category: string;
  status: string;
  diagnostic_reasons: string[];
  speed_kmh?: number | null;
  class_confidence?: number | null;
  [key: string]: unknown;
}
export interface TrafficArtifact {
  id?: string;
  session_id: string | null;
  name?: string;
  source_id?: string | null;
  provenance?: string;
  configuration: TrafficConfiguration | null;
  events: TrafficEvent[];
  zone_events?: Record<string, unknown>[];
  occupancy_samples?: Record<string, unknown>[];
  measurements?: SpeedMeasurement[];
  coverage?: Record<string, unknown>;
  summary?: Record<string, unknown>;
  diagnostics?: Record<string, unknown>;
  warnings?: string[];
  [key: string]: unknown;
}
export interface TrafficSessionSummary {
  id: string;
  session_id?: string;
  name?: string;
  source_id?: string;
  provenance?: string;
  total_crossings?: number;
  [key: string]: unknown;
}
export interface TrafficRequest {
  session_ids: string[];
  include_current: boolean;
  interval_minutes: number;
  category?: string;
  direction?: string;
  line_id?: string;
  status?: string;
  start_s?: number;
  end_s?: number;
  observation_started_after?: string;
  observation_started_before?: string;
  speed_status: "valid" | "approximate";
}
export type TrafficTable =
  | "events"
  | "classes"
  | "flow"
  | "zones"
  | "speeds"
  | "comparisons"
  | "quality";
export interface TrafficAnalysis {
  schema_version: number;
  interval_minutes: number;
  summary: {
    total_crossings: number;
    counted_events: number;
    suppressed_events: number;
    coverage_seconds: number;
    normalized_crossings_per_minute: number | null;
    normalized_crossings_per_hour: number | null;
    most_common_category: string | null;
    valid_speed_count: number;
    mean_speed_kmh: number | null;
    current_zone_occupancy: number;
    visible_tracks: number;
    peak_interval_count: number;
    count_scope?: "lifetime" | "retained" | "retained_filtered";
    incomplete_retained_data?: boolean;
    retained_counted_events?: number;
  };
  events: TrafficEvent[];
  classes: { category: string; count: number; fraction: number }[];
  directions: { direction: string; direction_label: string; count: number }[];
  flow: TrafficFlow[];
  zones: {
    session_id: string;
    zone_id: string;
    zone_label: string;
    entries: number;
    exits: number;
    interrupted_visits: number;
    completed_dwell_count: number;
    mean_dwell_s: number | null;
    maximum_dwell_s: number | null;
    current_occupancy: number;
  }[];
  speeds: TrafficSpeeds;
  comparisons: Record<string, unknown>[];
  quality: {
    session_id: string;
    code: string;
    message: string;
    value?: unknown;
  }[];
  occupancy: Record<string, unknown>[];
  warnings: string[];
}
export interface TrafficFlow {
  session_id: string;
  configuration_id: string;
  start_s: number;
  end_s: number;
  coverage_seconds: number;
  count: number;
  normalized_crossings_per_minute: number | null;
  normalized_crossings_per_hour: number | null;
  complete_window: boolean;
  cumulative_count: number;
  direction_counts: Record<string, number>;
  class_counts: Record<string, number>;
}
export interface TrafficSpeeds {
  status: string;
  n: number;
  mean_kmh: number | null;
  median_kmh: number | null;
  minimum_kmh: number | null;
  maximum_kmh: number | null;
  p85_kmh: number | null;
  standard_deviation_kmh: number | null;
  distribution: { start_kmh: number; end_kmh: number; count: number }[];
  by_class: Record<string, unknown>[];
  by_direction: Record<string, unknown>[];
  by_interval: Record<string, unknown>[];
}
export interface TrafficOverlays {
  track_ids: boolean;
  vehicle_classes: boolean;
  traffic_lines: boolean;
  traffic_zones: boolean;
  direction_indicators: boolean;
  zone_occupancy: boolean;
}
export function newTrafficConfiguration(
  source_id: string,
  geometry: ImageGeometry,
): TrafficConfiguration {
  return {
    id: crypto.randomUUID(),
    name: "Road monitoring",
    source_id,
    geometry,
    calibration_id: null,
    lines: [],
    zones: [],
    max_gap_s: 1,
    min_track_hits: 3,
    class_min_observations: 3,
    class_min_confidence: 0.55,
    class_min_margin: 0.15,
    identity_suppression_s: 0.75,
    identity_suppression_px: 12,
    stationary_window_s: 3,
    stationary_radius_px: 4,
    slow_speed_kmh: 5,
    occupancy_moderate: 3,
    occupancy_high: 8,
  };
}
