export type SourceType = "camera" | "video";
export type SessionState =
  | "idle"
  | "starting"
  | "running"
  | "paused"
  | "stopped"
  | "completed"
  | "error";
export type Category = "car" | "truck" | "bus" | "motorcycle";
export type Point = [number, number];
export type Segment = [Point, Point];
export interface ImageGeometry {
  width: number;
  height: number;
  rotation: number;
  mirrored: boolean;
  crop: number[] | null;
  coordinate_space?: "source" | "undistorted";
  intrinsic_profile_id?: string | null;
}
export interface Correspondence {
  image: Point;
  world: Point;
}
export interface CalibrationInput {
  name: string;
  source_id: string;
  geometry: ImageGeometry;
  points: Correspondence[];
  check_points: Correspondence[];
}
export interface CalibrationDiagnostics {
  valid: boolean;
  errors: string[];
  warnings: string[];
  homography: number[][] | null;
  region_image: Point[];
  grid_image: Point[][];
  inliers: boolean[];
  coverage: number;
  fit_error_m: number | null;
  fit_error_px: number | null;
  check_error_m: number | null;
  condition_number: number | null;
}
export interface GateInput {
  gate_a: Segment;
  gate_b: Segment;
  allow_reverse: boolean;
}
export interface GateDiagnostics extends GateInput {
  valid: boolean;
  errors: string[];
  warnings: string[];
  world_a?: Segment | null;
  world_b?: Segment | null;
}
export interface CalibrationProfile extends CalibrationInput {
  id: string;
  diagnostics: CalibrationDiagnostics;
  gates: GateInput | null;
}
export interface FrozenFrame {
  frame_id: string;
  image_url: string;
  source_id: string;
  geometry: ImageGeometry;
  session_id: string;
}
export interface SpeedMeasurement {
  id: string;
  track_id: number;
  source_id: string;
  session_id: string;
  calibration_id: string | null;
  category: Category;
  gate_a_timestamp_s: number | null;
  gate_b_timestamp_s: number | null;
  start_position: Point | null;
  end_position: Point | null;
  distance_m: number | null;
  elapsed_seconds: number | null;
  estimated_speed_kmh: number | null;
  direction: "A_to_B" | "B_to_A" | "unknown";
  status: "valid" | "approximate" | "rejected";
  independently_validated: boolean;
  reasons: string[];
  sample_count: number;
  timestamp_s: number | null;
  diagnostics?: {
    calibration_check_error_m: number | null;
    minimum_region_margin_px: number | null;
    maximum_observation_gap_s: number | null;
    maximum_contact_prediction_residual_px: number | null;
    gate_a_near_samples: number;
    gate_b_near_samples: number;
    near_gate_distance_m: number;
    gate_a_interpolation_interval_s: number | null;
    gate_b_interpolation_interval_s: number | null;
    ambiguous_observations: number;
    overlapping_box_observations: number;
    retained_position_samples: number;
  };
  position_samples?: Record<string, unknown>[];
  calibration_metadata?: Record<string, unknown>;
}
export interface MeasurementSummary {
  valid_count: number;
  approximate_count: number;
  rejected_count: number;
  latest_speed_kmh: number | null;
  latest_status: "valid" | "approximate" | null;
  average_speed_kmh: number | null;
}
export interface Overlays {
  boxes: boolean;
  trajectories: boolean;
  contact_points: boolean;
  gates: boolean;
  grid: boolean;
  speeds: boolean;
}

export interface Track {
  id: number;
  category: Category;
  bbox: [number, number, number, number];
  confidence: number;
  state: string;
  hits: number;
  missed: number;
  history: [number, number][];
  image_position?: Point | null;
  world_position?: Point | null;
  measurement_state?: string;
  position_diagnostics?: string[];
  age_s?: number;
  observation_gap_s?: number;
  association_ambiguous?: boolean;
  tracking_diagnostics?: string[];
}

export interface Session {
  state: SessionState;
  session_id: string | null;
  source_type: SourceType | null;
  source_label: string | null;
  error: string | null;
  frame_index: number;
  preview_revision?: number;
  width: number;
  height: number;
  reported_fps: number | null;
  capture_fps: number | null;
  processing_fps: number | null;
  inference_ms: number | null;
  pipeline_profile?: Record<string, number>;
  tracking_diagnostics?: Record<string, number>;
  latency_ms: number | null;
  dropped_frames: number;
  timestamp_s: number | null;
  timing_source: string | null;
  timing_warning: string | null;
  timing_diagnostics?: Record<string, unknown>;
  camera_model_id?: string | null;
  tracks: Track[];
  counts: Record<Category, number>;
  total_tracks: number;
  source_id: string | null;
  geometry: ImageGeometry | null;
  calibration_status: "required" | "ready" | "incompatible";
  calibration_id: string | null;
  calibration_warnings: string[];
  gates: GateDiagnostics | null;
  measurements: SpeedMeasurement[];
  measurement_summary: MeasurementSummary;
  measurement_status: string;
  overlays: Overlays;
}

export interface Health {
  status: "ok";
  model: { ready: boolean; name: string; path: string; input_size: number };
}

export interface Camera {
  index: number;
  name: string;
  width: number;
  height: number;
  fps: number | null;
}
export interface Video {
  video_id: string;
  name: string;
}
export interface StartOptions {
  source_type: SourceType;
  camera_index: number;
  video_id?: string;
  confidence: number;
  input_size: number;
  width: number;
  height: number;
}
