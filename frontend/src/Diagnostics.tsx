import Icon from "./Icon";
import { elapsed } from "./Preview";
import type { Session } from "./types";

export default function Diagnostics({ session }: { session: Session }) {
  const hasFrames = session.frame_index > 0;
  const number = (value: number | null | undefined, suffix = "", digits = 1) =>
    hasFrames && value != null && Number.isFinite(value)
      ? `${value.toFixed(digits)}${suffix}`
      : "—";
  const entries = [
    [
      "Source resolution",
      hasFrames ? `${session.width} × ${session.height}` : "—",
    ],
    ["Reported frame rate", number(session.reported_fps, " fps")],
    ["Inference time", number(session.inference_ms, " ms")],
    [
      "Video decode",
      session.source_type === "video"
        ? number(session.pipeline_profile?.decode_ms, " ms", 3)
        : "Not applicable",
    ],
    [
      "Undistortion",
      session.camera_model_id
        ? number(session.pipeline_profile?.undistortion_ms, " ms", 3)
        : "Disabled",
    ],
    [
      "Tracking update",
      number(session.pipeline_profile?.tracking_ms, " ms", 3),
    ],
    [
      "Homography projection",
      number(session.pipeline_profile?.projection_ms, " ms", 3),
    ],
    ["Gate events", number(session.pipeline_profile?.gate_events_ms, " ms", 3)],
    [
      "Dropped frames",
      hasFrames ? session.dropped_frames.toLocaleString() : "—",
    ],
    ["Source time", hasFrames ? elapsed(session.timestamp_s) : "—"],
    [
      "Timing method",
      session.timing_source ? session.timing_source.replaceAll("_", " ") : "—",
    ],
  ];
  const tracking = session.tracking_diagnostics;
  const timing = session.timing_diagnostics;
  const timingNumber = (key: string, suffix = "", digits = 1) =>
    number(
      typeof timing?.[key] === "number" ? (timing[key] as number) : null,
      suffix,
      digits,
    );
  const latency = timing?.processing_latency as
    Record<string, unknown> | undefined;
  const issues = timing?.issues as Record<string, unknown> | undefined;
  return (
    <section className="panel diagnostics-panel">
      <div className="panel-heading">
        <h2>Source diagnostics</h2>
        <Icon name="pulse" size={18} />
      </div>
      <dl className="diagnostics-list">
        {entries.map(([label, value]) => (
          <div key={label}>
            <dt>{label}</dt>
            <dd>{value}</dd>
          </div>
        ))}
      </dl>
      {timing && Object.keys(timing).length > 0 && (
        <>
          <h3>Timestamp integrity</h3>
          <dl className="diagnostics-list">
            {[
              [
                "Source / processed frames",
                `${timingNumber("source_frame_count", "", 0)} / ${timingNumber("processed_frame_count", "", 0)}`,
              ],
              [
                "Skipped source indices",
                timingNumber("skipped_source_frames", "", 0),
              ],
              [
                "Effective observations",
                timingNumber("effective_observation_rate_hz", " Hz", 2),
              ],
              [
                "Maximum source gap",
                timingNumber("maximum_source_gap_s", " s", 4),
              ],
              [
                "Maximum observation gap",
                timingNumber("maximum_observation_gap_s", " s", 4),
              ],
              ["Source interval CV", timingNumber("source_interval_cv", "", 3)],
              [
                "Latest original source time",
                timingNumber("latest_raw_timestamp_s", " s", 6),
              ],
              [
                "Latency P95 (last 240)",
                number(
                  typeof latency?.p95_ms === "number" ? latency.p95_ms : null,
                  " ms",
                ),
              ],
              ["Timebase", String(timing.time_base ?? "Not declared")],
              [
                "Duplicate / backward timestamps",
                `${issues?.duplicate_timestamp ?? 0} / ${issues?.backward_timestamp ?? 0}`,
              ],
              ["Timebase changes", String(issues?.timebase_changed ?? 0)],
              [
                "Pixel coordinates",
                session.geometry?.coordinate_space ?? "source",
              ],
            ].map(([label, value]) => (
              <div key={label}>
                <dt>{label}</dt>
                <dd>{value}</dd>
              </div>
            ))}
          </dl>
          <p className="subtle-caption">
            Rates use retained source timestamps. Decoding, acquisition,
            inference and browser display differ; source PTS do not verify
            wall-clock exposure time.
          </p>
          {Array.isArray(timing.warnings) &&
            timing.warnings.map((warning, index) => (
              <p className="timing-warning" key={index}>
                {String(warning)}
              </p>
            ))}
        </>
      )}
      {tracking && (
        <>
          <h3>Tracking continuity</h3>
          <dl className="diagnostics-list">
            {[
              [
                "Active / confirmed",
                `${tracking.active_tracks ?? 0} / ${tracking.confirmed_tracks ?? 0}`,
              ],
              [
                "Lost / removed",
                `${tracking.lost_tracks ?? 0} / ${tracking.removed_tracks ?? 0}`,
              ],
              ["Potential ID switches", tracking.potential_id_switches ?? 0],
              ["Fragment suspicions", tracking.fragmentation_suspicions ?? 0],
            ].map(([label, value]) => (
              <div key={label}>
                <dt>{label}</dt>
                <dd>{value}</dd>
              </div>
            ))}
          </dl>
          <p className="subtle-caption">
            Suspicions describe ambiguous associations; verified identity
            switches require annotated ground truth.
          </p>
        </>
      )}
      {session.timing_warning && (
        <p className="timing-warning">
          <Icon name="info" size={15} />
          {session.timing_warning}
        </p>
      )}
    </section>
  );
}
