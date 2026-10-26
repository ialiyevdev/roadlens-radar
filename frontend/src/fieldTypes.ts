import type {
  CalibrationProfile,
  GateInput,
  ImageGeometry,
  SpeedMeasurement,
} from "./types";
import type {
  MetricSummary,
  ValidationOptions,
  ValidationReport,
} from "./validationTypes";

export type FieldPartition = "development" | "calibration" | "held_out";
export type FieldProvenance =
  "synthetic" | "recorded_unverified" | "independent_reference";
export interface FieldSource {
  source_id: string;
  video_id: string | null;
  relative_path: string | null;
  content_sha256: string | null;
  segment_start_s: number | null;
  segment_end_s: number | null;
  collection_id: string | null;
  near_duplicate_group: string | null;
}
export interface FieldSourceOption {
  video_id: string;
  source_id: string;
  relative_path: string;
  name: string;
  width: number;
  height: number;
  reported_fps: number | null;
  frame_count?: number | null;
  duration_s?: number | null;
  time_base?: string | null;
}
export interface FieldCamera {
  configuration_id: string;
  geometry: ImageGeometry;
  intrinsic_profile_id: string | null;
  lens_model: string | null;
  zoom: string | null;
  notes: string;
  detector_input_size: number | null;
  detector_confidence: number | null;
  tracker: string;
}
export interface FieldMeasurement {
  event_id: string;
  variant: "original" | "baseline" | "improved";
  measurement: SpeedMeasurement;
}
export interface ReferenceEvent {
  id: string;
  timestamp_s: number;
  interval_end_s: number | null;
  speed: number;
  units: "km/h" | "m/s" | "mph";
  method: string;
  provenance: FieldProvenance;
  independent: boolean;
  instrument_id: string | null;
  uncertainty_kmh: number | null;
  quality_notes: string;
}
export interface SyncAnchor {
  reference_timestamp_s: number;
  source_timestamp_s: number;
  uncertainty_s: number | null;
  independent: boolean;
  description: string;
}
export interface SyncConfig {
  source_clock: string;
  reference_clock: string;
  offset_s: number;
  fit_drift: boolean;
  anchors: SyncAnchor[];
  uncertainty_s: number | null;
  maximum_alignment_error_s: number;
  notes: string;
}
export interface SyncDiagnostics {
  status: "unconfigured" | "uncertain" | "aligned";
  offset_s: number;
  scale: number;
  drift_ppm: number;
  anchor_count: number;
  anchor_span_s: number;
  residuals_s: number[];
  maximum_residual_s: number | null;
  uncertainty_bound_s: number | null;
  warnings: string[];
}
export interface EventMatch {
  event_id: string;
  reference_id: string | null;
  association: "matched" | "ambiguous" | "unmatched";
  method: string;
  quality_notes: string;
  correspondence_confirmed: boolean;
}
export interface FieldSessionInput {
  name: string;
  description: string;
  source: FieldSource;
  camera: FieldCamera;
  calibration_id: string | null;
  calibration_compatible?: boolean;
  configuration_warnings?: string[];
  calibration_metadata?: {
    road_plane?: CalibrationProfile | null;
    intrinsic?: Record<string, unknown> | null;
  };
  gates: GateInput | null;
  started_at: string | null;
  ended_at: string | null;
  source_timebase: string;
  timing_summary: Record<string, unknown>;
  environment_notes: string;
  environment_condition: string;
  reference_description: string;
  validation_dataset_id: string | null;
  provenance: FieldProvenance;
  status: "draft" | "collecting" | "ready" | "evaluated";
  partition: FieldPartition;
  measurements: FieldMeasurement[];
  reference_events: ReferenceEvent[];
  sync: SyncConfig;
  matches: EventMatch[];
  expected_event_count: number | null;
}
export interface FieldSession extends FieldSessionInput {
  id: string;
  created_at: string;
  updated_at: string;
  sync_diagnostics: SyncDiagnostics;
}
export interface FieldEligibility {
  eligible?: boolean;
  real_world_reference_available?: boolean;
  matched_count?: number;
  confirmed_matches?: number;
  warnings?: string[];
  reasons?: string[];
  rows?: {
    event_id: string;
    variant: string;
    reference_id: string | null;
    eligible: boolean;
    exclusion_reasons: string[];
  }[];
  [key: string]: unknown;
}
export interface FieldEvaluationRequest {
  session_ids: string[];
  partition: FieldPartition | null;
  variant: "original" | "baseline" | "improved";
  options: ValidationOptions;
  description: string;
}
export interface FieldEvaluation {
  validation: ValidationReport;
  provenance: FieldProvenance;
  partition: FieldPartition | null;
  variant: "original" | "baseline" | "improved";
  real_world_reference_available: boolean;
  session_count?: number;
  sessions?: { id: string; name: string; partition: FieldPartition }[];
  groups?: { dimension: string; value: string; metrics: MetricSummary }[];
  group_sample_counts: { dimension: string; value: string; n: number }[];
  row_metadata: {
    session_id: string;
    session_name: string;
    event_id: string;
    variant: string;
    partition: FieldPartition;
    camera_configuration: string;
    calibration: string;
    direction: string;
    environment: string;
    tracker: string;
    status: string;
    original_reasons: string[];
    measurement_diagnostics: Record<string, unknown>;
  }[];
  counts: {
    vehicle_events: number;
    denominator: number;
    complete_event_ledger: boolean;
    valid: number;
    rejected: number;
    completed: number;
    noncompleted: number;
    missing_application_events: number | null;
    missing_reference: number;
    unmatched_reference_events: number;
    excluded_measurements: number;
    valid_measurement_percent: number | null;
    rejection_percent: number | null;
    noncompletion_percent: number | null;
  };
  exclusions: Record<string, number>;
  timing: {
    session_id: string;
    source_timebase: string;
    statistics: Record<string, unknown>;
    synchronization: SyncDiagnostics;
  }[];
  tracking: { session_id: string; metrics: Record<string, unknown> }[];
  pipeline_comparison: {
    paired_n: number;
    pairs: Record<string, unknown>[];
    baseline: MetricSummary;
    improved: MetricSummary;
    note: string;
  };
  performance: { evaluation_ms: number };
  limitations?: string[];
  [key: string]: unknown;
}
