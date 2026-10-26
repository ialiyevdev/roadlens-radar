import type { Session } from "./types";
import type { CameraCalibrationInput, CameraIntrinsicProfile } from "./cameraTypes";

async function request<T>(path: string, options?: RequestInit): Promise<T> {
  const response = await fetch(`/api${path}`, options);
  if (!response.ok) {
    let message = `Camera request failed (${response.status}).`;
    try {
      const body = await response.json() as { detail?: unknown };
      if (typeof body.detail === "string") message = body.detail;
      else if (Array.isArray(body.detail)) message = body.detail.map((item: { msg?: string }) => item.msg || "Invalid camera input").join("; ");
    } catch { /* Proxy responses can be plain text. */ }
    throw new Error(message);
  }
  return response.json() as Promise<T>;
}

export const cameraApi = {
  profiles: () => request<{ profiles: CameraIntrinsicProfile[] }>("/camera-profiles"),
  calibrate: (configuration: CameraCalibrationInput, files: File[]) => {
    const body = new FormData();
    body.append("configuration", JSON.stringify(configuration));
    files.forEach(file => body.append("files", file));
    return request<CameraIntrinsicProfile>("/camera-profiles/calibrate", { method: "POST", body });
  },
  importProfile: (profile: unknown) => request<CameraIntrinsicProfile>("/camera-profiles/import", {
    method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(profile),
  }),
  remove: (id: string) => request<{ deleted: boolean }>(`/camera-profiles/${encodeURIComponent(id)}`, { method: "DELETE" }),
  activate: (profileId: string | null, confirmUnchanged = false) => request<Session>("/camera-model", {
    method: "PUT", headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ profile_id: profileId, confirm_unchanged: confirmUnchanged }),
  }),
};
