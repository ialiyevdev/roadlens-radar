import { request } from "./api";
import type {
  TrafficAnalysis,
  TrafficArtifact,
  TrafficConfiguration,
  TrafficRequest,
  TrafficSessionSummary,
  TrafficTable,
  TrafficOverlays,
} from "./trafficTypes";

const json = (method: string, body?: unknown): RequestInit => ({
  method,
  headers: { "Content-Type": "application/json" },
  ...(body === undefined ? {} : { body: JSON.stringify(body) }),
});
export const trafficApi = {
  current: () =>
    request<{ snapshot: TrafficArtifact | null; analytics: TrafficAnalysis }>(
      "/traffic/current",
    ),
  configuration: () =>
    request<TrafficConfiguration | null>("/traffic/configuration"),
  overlays: () => request<TrafficOverlays>("/traffic/overlays"),
  setOverlays: (value: TrafficOverlays) =>
    request<TrafficOverlays>("/traffic/overlays", json("PUT", value)),
  configure: (value: TrafficConfiguration) =>
    request<TrafficConfiguration>("/traffic/configuration", json("PUT", value)),
  list: () =>
    request<{ sessions: TrafficSessionSummary[] }>("/traffic/sessions"),
  get: (id: string) =>
    request<TrafficArtifact>(`/traffic/sessions/${encodeURIComponent(id)}`),
  archive: () => request<TrafficArtifact>("/traffic/archive", json("POST")),
  example: () => request<TrafficArtifact>("/traffic/example", json("POST")),
  analyze: (value: TrafficRequest) =>
    request<TrafficAnalysis>("/traffic/analytics", json("POST", value)),
  evaluate: (value: {
    traffic_session_id: string;
    field_session_id: string;
    maximum_time_error_s: number;
    partition: string;
  }) =>
    request<Record<string, unknown>>("/traffic/evaluate", json("POST", value)),
  export: async (
    value: TrafficRequest,
    table: TrafficTable,
    format: "json" | "csv",
  ): Promise<Blob> => {
    const response = await fetch(
      `/api/traffic/export?table=${table}&format=${format}`,
      json("POST", value),
    );
    if (!response.ok) {
      let message = `Export failed (${response.status}).`;
      try {
        const body = await response.json();
        if (typeof body.detail === "string") message = body.detail;
      } catch {
        /* A proxy may return plain text. */
      }
      throw new Error(message);
    }
    return response.blob();
  },
};
