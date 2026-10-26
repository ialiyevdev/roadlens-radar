import type {
  CalibrationDiagnostics,
  CalibrationInput,
  CalibrationProfile,
  Camera,
  FrozenFrame,
  GateDiagnostics,
  GateInput,
  Health,
  Overlays,
  Session,
  StartOptions,
  Video,
} from "./types";

export async function request<T>(path: string, options?: RequestInit): Promise<T> {
  const response = await fetch(`/api${path}`, options);
  if (!response.ok) {
    let message = `Request failed (${response.status}).`;
    try {
      const body: unknown = await response.json();
      if (
        body &&
        typeof body === "object" &&
        "detail" in body &&
        typeof body.detail === "string"
      ) {
        message = body.detail;
      } else if (
        body &&
        typeof body === "object" &&
        "detail" in body &&
        Array.isArray(body.detail)
      ) {
        message = body.detail
          .map(
            (issue: { loc?: (string | number)[]; msg?: string }) =>
              `${issue.loc?.slice(1).join(".") || "Input"}: ${issue.msg || "Invalid value"}`,
          )
          .join("; ");
      }
    } catch {
      /* A proxy error may return plain text instead of API JSON. */
    }
    throw new Error(message);
  }
  return response.json() as Promise<T>;
}

function json(method: string, body: unknown): RequestInit {
  return {
    method,
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  };
}

export const api = {
  freeze: () => request<FrozenFrame>("/calibration/freeze", { method: "POST" }),
  calibrations: () =>
    request<{ profiles: CalibrationProfile[] }>("/calibrations"),
  validateCalibration: (input: CalibrationInput) =>
    request<CalibrationDiagnostics>(
      "/calibrations/validate",
      json("POST", input),
    ),
  saveCalibration: (input: CalibrationInput, id?: string) =>
    request<CalibrationProfile>(
      id ? `/calibrations/${encodeURIComponent(id)}` : "/calibrations",
      json(id ? "PUT" : "POST", input),
    ),
  deleteCalibration: (id: string) =>
    request<unknown>(`/calibrations/${encodeURIComponent(id)}`, {
      method: "DELETE",
    }),
  activateCalibration: (id: string) =>
    request<Session>(
      `/calibrations/${encodeURIComponent(id)}/activate`,
      json("POST", { confirm_stationary: true }),
    ),
  invalidateCalibration: () =>
    request<Session>(
      "/calibration/invalidate",
      json("POST", {
        reason: "Camera position, zoom, or image geometry changed.",
      }),
    ),
  saveGates: (input: GateInput) =>
    request<GateDiagnostics>("/gates", json("PUT", input)),
  resetGates: () => request<unknown>("/gates", { method: "DELETE" }),
  clearMeasurements: () =>
    request<Session>("/measurements", { method: "DELETE" }),
  overlays: (overlays: Overlays) =>
    request<Session>("/overlays", json("PUT", overlays)),
  health: () => request<Health>("/health"),
  session: () => request<Session>("/session"),
  cameras: () => request<{ cameras: Camera[] }>("/cameras"),
  start: (options: StartOptions) =>
    request<Session>("/sessions/start", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(options),
    }),
  control: (action: "stop" | "pause" | "resume" | "reset") =>
    request<Session>(`/sessions/${action}`, { method: "POST" }),
  upload: (file: File) => {
    const body = new FormData();
    body.append("file", file);
    return request<Video>("/videos", { method: "POST", body });
  },
};
