export type ValidationStatus = "valid" | "approximate" | "rejected";
export interface ValidationRecord {
  recording_id: string;
  observation_id: string;
  measurement_id: string;
  status: ValidationStatus;
  vehicle_id?: string | null;
  calibration_id?: string | null;
  estimated_speed_kmh?: number | null;
  reference_speed_kmh?: number | null;
  reference_method?: string | null;
  reference_independent?: boolean;
  reference_recording_id?: string | null;
  reference_observation_id?: string | null;
  reference_measurement_id?: string | null;
  association?: "matched" | "ambiguous" | "unmatched" | "mismatched";
  direction?: "A_to_B" | "B_to_A" | "unknown";
  timestamp_s?: number | null;
  reference_timestamp_s?: number | null;
  reference_interval_start_s?: number | null;
  reference_interval_end_s?: number | null;
  diagnostics?: Record<string, string | number | boolean | null>;
}
export interface ValidationDataset {
  name: string;
  provenance: "synthetic" | "real_world";
  description: string;
  records: ValidationRecord[];
}
export interface ValidationOptions {
  tolerance_bands_kmh: number[];
  minimum_group_samples: number;
}
export interface MetricSummary {
  n: number;
  sufficient_sample: boolean;
  mae_kmh: number | null;
  rmse_kmh: number | null;
  bias_kmh: number | null;
  median_absolute_error_kmh: number | null;
  p90_absolute_error_kmh: number | null;
  mape_percent: number | null;
  percentage_sample_count: number;
  tolerance_bands: {
    tolerance_kmh: number;
    within_count: number;
    within_percent: number | null;
  }[];
}
export interface ValidationRow {
  record: ValidationRecord;
  reference_matched: boolean;
  comparison_included: boolean;
  error_kmh: number | null;
  absolute_error_kmh: number | null;
  absolute_percentage_error_percent: number | null;
  exclusion_reasons: string[];
}
export interface ValidationReport {
  dataset_name: string;
  provenance: ValidationDataset["provenance"];
  description: string;
  evaluation_version: string;
  total_records: number;
  reference_matched_count: number;
  compared_count: number;
  rejected_count: number;
  completed_count: number;
  rejection_rate_percent: number | null;
  completion_rate_percent: number | null;
  summary: MetricSummary;
  groups: { id: string; label: string; metrics: MetricSummary }[];
  rows: ValidationRow[];
  options: ValidationOptions;
  limitations: string[];
}
export interface TrackingContinuity {
  timestamp_s: number;
  ground_truth_count: number;
  observed_tracks: number;
  active_tracks: number;
  lost_tracks: number;
}
export interface TrackingMetrics {
  frames: number;
  ground_truth_observations: number;
  matched_observations: number;
  missed_observations: number;
  id_switches: number;
  fragments: number;
  created_tracks: number;
  confirmed_tracks: number;
  potential_id_switches: number;
  fragmentation_suspicions: number;
  mean_update_ms: number;
  p95_update_ms: number;
  runtime_ms: number;
}
export interface TrackingScenario extends TrackingMetrics {
  name: string;
  description: string;
  continuity: TrackingContinuity[];
}
export interface TrackingResult extends TrackingMetrics {
  name: string;
  scenarios: TrackingScenario[];
}
export interface TrackingReport {
  schema_version: number;
  provenance: "synthetic";
  generated_at_utc: string;
  hardware: {
    os: string;
    cpu: string;
    logical_cpus: number;
    python: string;
  };
  methodology: Record<string, string | string[]>;
  baseline: TrackingResult;
  improved: TrackingResult;
}
