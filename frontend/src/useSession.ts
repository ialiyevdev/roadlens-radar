import { useCallback, useEffect, useRef, useState } from "react";
import { api } from "./api";
import type { Health, Session, StartOptions } from "./types";

export const initialSession: Session = {
  state: "idle",
  session_id: null,
  source_type: null,
  source_label: null,
  error: null,
  frame_index: 0,
  width: 0,
  height: 0,
  reported_fps: 0,
  capture_fps: 0,
  processing_fps: 0,
  inference_ms: 0,
  latency_ms: 0,
  dropped_frames: 0,
  timestamp_s: 0,
  timing_source: "",
  timing_warning: null,
  tracks: [],
  counts: { car: 0, truck: 0, bus: 0, motorcycle: 0 },
  total_tracks: 0,
  calibration_status: "required",
  source_id: null,
  geometry: null,
  calibration_id: null,
  calibration_warnings: [],
  gates: null,
  measurements: [],
  measurement_summary: {
    valid_count: 0,
    approximate_count: 0,
    rejected_count: 0,
    latest_speed_kmh: null,
    latest_status: null,
    average_speed_kmh: null,
  },
  measurement_status: "Calibration required",
  overlays: {
    boxes: true,
    trajectories: true,
    contact_points: false,
    gates: true,
    grid: false,
    speeds: true,
  },
};

export function errorMessage(error: unknown): string {
  return error instanceof Error
    ? error.message
    : "An unexpected error occurred. Please try again.";
}

export function useSession() {
  const [session, setSession] = useState<Session>(initialSession);
  const [health, setHealth] = useState<Health | null>(null);
  const [connected, setConnected] = useState<boolean | null>(null);
  const [busy, setBusy] = useState(false);
  const [actionError, setActionError] = useState<string | null>(null);
  const revision = useRef(0);
  const busyRef = useRef(false);

  useEffect(() => {
    let mounted = true;
    let polling = false;
    async function pollSession() {
      if (polling || busyRef.current) return;
      polling = true;
      const expectedRevision = revision.current;
      try {
        const current = await api.session();
        if (mounted && expectedRevision === revision.current) {
          setSession(current);
          setConnected(true);
        }
      } catch {
        if (mounted) setConnected(false);
      } finally {
        polling = false;
      }
    }
    async function pollHealth() {
      try {
        const current = await api.health();
        if (mounted) setHealth(current);
      } catch {
        if (mounted) setHealth(null);
      }
    }
    void pollSession();
    void pollHealth();
    const sessionTimer = window.setInterval(() => void pollSession(), 750);
    const healthTimer = window.setInterval(() => void pollHealth(), 10_000);
    return () => {
      mounted = false;
      window.clearInterval(sessionTimer);
      window.clearInterval(healthTimer);
    };
  }, []);

  const perform = useCallback(async (operation: () => Promise<Session>) => {
    if (busyRef.current) return;
    busyRef.current = true;
    revision.current += 1;
    setBusy(true);
    setActionError(null);
    try {
      setSession(await operation());
      setConnected(true);
    } catch (error) {
      setActionError(errorMessage(error));
    } finally {
      revision.current += 1;
      busyRef.current = false;
      setBusy(false);
    }
  }, []);

  return {
    session,
    health,
    connected,
    busy,
    actionError,
    setActionError,
    perform,
    start: (options: StartOptions) => perform(() => api.start(options)),
    control: (action: "stop" | "pause" | "resume" | "reset") =>
      perform(() => api.control(action)),
  };
}
