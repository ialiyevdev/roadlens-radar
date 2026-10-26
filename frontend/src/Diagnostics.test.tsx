import { describe, expect, it } from "vitest";
import { render, screen, within } from "@testing-library/react";
import Diagnostics from "./Diagnostics";
import { initialSession } from "./useSession";
import type { Session } from "./types";

function expectEntry(label: string, value: string) {
  expect(
    within(screen.getByText(label).parentElement!).getByText(value),
  ).toBeInTheDocument();
}
const observed: Session = {
  ...initialSession,
  frame_index: 10,
  width: 800,
  height: 600,
  inference_ms: 110.26,
  reported_fps: null,
  dropped_frames: 4,
  timestamp_s: 1.25,
  timing_source: "video_presentation_timestamp",
  pipeline_profile: {
    tracking_ms: 0.01673,
    projection_ms: 0.0044,
    gate_events_ms: 0,
  },
};

describe("source and tracking diagnostics", () => {
  it("shows source-time integrity, acquisition latency and explicit corrected-pixel coordinates", () => {
    render(
      <Diagnostics
        session={{
          ...observed,
          source_type: "video",
          camera_model_id: "intrinsic-1",
          geometry: {
            width: 800,
            height: 600,
            rotation: 0,
            mirrored: false,
            crop: null,
            coordinate_space: "undistorted",
            intrinsic_profile_id: "intrinsic-1",
          },
          pipeline_profile: {
            ...observed.pipeline_profile,
            decode_ms: 0.5234,
            undistortion_ms: 0.1278,
          },
          timing_diagnostics: {
            source_frame_count: 105,
            processed_frame_count: 100,
            skipped_source_frames: 5,
            effective_observation_rate_hz: 24.876,
            maximum_source_gap_s: 0.08001,
            maximum_observation_gap_s: 0.12002,
            source_interval_cv: 0.01234,
            latest_raw_timestamp_s: 4.12345678,
            processing_latency: { p95_ms: 175.26 },
            time_base: "1/25000",
            issues: {
              duplicate_timestamp: 2,
              backward_timestamp: 1,
              timebase_changed: 1,
            },
            warnings: ["Source PTS interval changed; inspect the recording."],
          },
        }}
      />,
    );
    expectEntry("Source / processed frames", "105 / 100");
    expectEntry("Skipped source indices", "5");
    expectEntry("Effective observations", "24.88 Hz");
    expectEntry("Maximum source gap", "0.0800 s");
    expectEntry("Maximum observation gap", "0.1200 s");
    expectEntry("Source interval CV", "0.012");
    expectEntry("Latest original source time", "4.123457 s");
    expectEntry("Latency P95 (last 240)", "175.3 ms");
    expectEntry("Timebase", "1/25000");
    expectEntry("Duplicate / backward timestamps", "2 / 1");
    expectEntry("Timebase changes", "1");
    expectEntry("Pixel coordinates", "undistorted");
    expectEntry("Video decode", "0.523 ms");
    expectEntry("Undistortion", "0.128 ms");
    expect(
      screen.getByText("Source PTS interval changed; inspect the recording."),
    ).toBeVisible();
    expect(
      screen.getByText(/source PTS do not verify wall-clock exposure time/),
    ).toBeVisible();
  });
  it("leaves unavailable timestamp statistics blank and never prints nonfinite values", () => {
    const { rerender } = render(
      <Diagnostics
        session={{
          ...observed,
          timing_diagnostics: {
            source_frame_count: 0,
            processed_frame_count: 0,
            effective_observation_rate_hz: null,
            maximum_source_gap_s: Number.NaN,
            maximum_observation_gap_s: Number.POSITIVE_INFINITY,
            processing_latency: { p95_ms: null },
          },
        }}
      />,
    );
    expectEntry("Source / processed frames", "0 / 0");
    for (const label of [
      "Effective observations",
      "Maximum source gap",
      "Maximum observation gap",
      "Latest original source time",
      "Latency P95 (last 240)",
    ])
      expectEntry(label, "—");
    expectEntry("Timebase", "Not declared");
    expectEntry("Undistortion", "Disabled");
    expect(screen.queryByText(/NaN|Infinity/)).not.toBeInTheDocument();
    rerender(<Diagnostics session={{ ...observed, timing_diagnostics: {} }} />);
    expect(
      screen.queryByRole("heading", { name: "Timestamp integrity" }),
    ).not.toBeInTheDocument();
  });
  it("preserves millisecond stage precision and distinguishes measured zero from unavailable timing", () => {
    render(<Diagnostics session={observed} />);
    expectEntry("Tracking update", "0.017 ms");
    expectEntry("Homography projection", "0.004 ms");
    expectEntry("Gate events", "0.000 ms");
    expectEntry("Inference time", "110.3 ms");
    expectEntry("Reported frame rate", "—");
    expectEntry("Dropped frames", "4");
    expectEntry("Timing method", "video presentation timestamp");
    expect(
      screen.queryByRole("heading", { name: "Tracking continuity" }),
    ).not.toBeInTheDocument();
  });
  it("withholds stage timings before observations and rejects missing or nonfinite stage values", () => {
    const { rerender } = render(
      <Diagnostics session={{ ...observed, frame_index: 0 }} />,
    );
    for (const label of [
      "Tracking update",
      "Homography projection",
      "Gate events",
      "Inference time",
      "Dropped frames",
    ])
      expectEntry(label, "—");
    rerender(
      <Diagnostics
        session={{
          ...observed,
          pipeline_profile: {
            tracking_ms: Number.NaN,
            projection_ms: Number.POSITIVE_INFINITY,
          },
          timing_warning:
            "Source timing fell back to nominal frame intervals; speed is unavailable.",
        }}
      />,
    );
    for (const label of [
      "Tracking update",
      "Homography projection",
      "Gate events",
    ])
      expectEntry(label, "—");
    expect(
      screen.getByText(/Source timing fell back to nominal frame intervals/),
    ).toBeInTheDocument();
  });
  it("shows lifecycle counts and labels switch and fragmentation counters as heuristic suspicions", () => {
    render(
      <Diagnostics
        session={{
          ...observed,
          tracking_diagnostics: {
            active_tracks: 4,
            confirmed_tracks: 3,
            lost_tracks: 1,
            removed_tracks: 2,
            potential_id_switches: 2,
            fragmentation_suspicions: 1,
          },
        }}
      />,
    );
    expect(
      screen.getByRole("heading", { name: "Tracking continuity" }),
    ).toBeInTheDocument();
    expectEntry("Active / confirmed", "4 / 3");
    expectEntry("Lost / removed", "1 / 2");
    expectEntry("Potential ID switches", "2");
    expectEntry("Fragment suspicions", "1");
    expect(
      screen.getByText(
        /verified identity switches require annotated ground truth/,
      ),
    ).toBeInTheDocument();
  });
});
