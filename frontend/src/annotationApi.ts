import { request } from "./api";
import type { ImageGeometry, Category } from "./types";

export interface GroundTruthObject {
  identity: string;
  category: Category;
  bbox: [number, number, number, number] | null;
  occluded: boolean;
  partial_visibility: boolean;
  entry: boolean;
  exit: boolean;
}
export interface TrackPrediction {
  predicted_track_id: number;
  category: Category;
  bbox: [number, number, number, number];
  confidence: number;
}
export interface AnnotatedFrame {
  index: number;
  timestamp_s: number | null;
  reviewed: boolean;
  objects: GroundTruthObject[];
  predictions: TrackPrediction[];
}
export interface AnnotationDocument {
  schema_version: 1;
  field_session_id: string;
  source_id: string;
  geometry: ImageGeometry;
  revision: number;
  provenance: "synthetic" | "recorded_unverified" | "independent_reference";
  frames: AnnotatedFrame[];
}
export interface AnnotationFrameInfo {
  index: number;
  timestamp_s: number | null;
  pts: number | null;
  time_base: string | null;
  width: number;
  height: number;
  timing_warning: string | null;
  total_frames: number;
  image_url: string;
  coordinate_space: "source" | "undistorted";
  intrinsic_profile_id: string | null;
}
export interface AnnotationMetrics {
  annotated_vehicles: number;
  reviewed_frames: number;
  predicted_frames: number;
  matched_observations: number;
  missed_observations: number;
  false_positive_observations: number;
  id_switches: number;
  fragments: number;
  limitations: string[];
}
const base = (id: string) => `/field-sessions/${encodeURIComponent(id)}`;
const json = (method: string, body: unknown): RequestInit => ({
  method,
  headers: { "Content-Type": "application/json" },
  body: JSON.stringify(body),
});
export const annotationApi = {
  get: (id: string) => request<AnnotationDocument>(`${base(id)}/annotations`),
  save: (id: string, document: AnnotationDocument) =>
    request<AnnotationDocument>(
      `${base(id)}/annotations`,
      json("PUT", document),
    ),
  frame: (id: string, index: number) =>
    request<AnnotationFrameInfo>(`${base(id)}/frames?index=${index}`),
  frameAt: (id: string, timestamp: number) =>
    request<AnnotationFrameInfo>(`${base(id)}/frames?timestamp_s=${timestamp}`),
  metrics: (id: string) =>
    request<AnnotationMetrics>(`${base(id)}/annotations/metrics`),
  import: (id: string, file: File) => {
    const body = new FormData();
    body.append("file", file);
    return request<AnnotationDocument>(`${base(id)}/annotations/import`, {
      method: "POST",
      body,
    });
  },
  propose: (id: string, start: number, end: number, tracker: string) =>
    request<AnnotationDocument>(
      `${base(id)}/proposals`,
      json("POST", {
        start_index: start,
        end_index: end,
        input_size: 416,
        confidence: 0.35,
        tracker,
      }),
    ),
};
