import { describe, expect, it, vi } from "vitest";
import { render, screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import SpeedPanel from "./SpeedPanel";
import { initialSession } from "./useSession";
import type { Session, SpeedMeasurement } from "./types";

const valid: SpeedMeasurement = {
  id: "m1",
  track_id: 7,
  source_id: "synthetic",
  session_id: "s1",
  calibration_id: "c1",
  category: "car",
  gate_a_timestamp_s: 1,
  gate_b_timestamp_s: 3,
  start_position: [0, 0],
  end_position: [20, 0],
  distance_m: 20,
  elapsed_seconds: 2,
  estimated_speed_kmh: 36,
  direction: "A_to_B",
  status: "valid",
  independently_validated: false,
  reasons: [],
  sample_count: 12,
  timestamp_s: 3,
};
const session: Session = {
  ...initialSession,
  calibration_status: "ready",
  measurements: [
    valid,
    {
      ...valid,
      id: "m2",
      track_id: 8,
      status: "rejected",
      estimated_speed_kmh: 500,
      reasons: ["Track lost between gates."],
    },
    {
      ...valid,
      id: "m3",
      track_id: 9,
      status: "approximate",
      estimated_speed_kmh: 35.5,
      reasons: ["Long observation gap."],
    },
  ],
  measurement_summary: {
    valid_count: 1,
    approximate_count: 1,
    rejected_count: 1,
    latest_speed_kmh: 36,
    latest_status: "valid",
    average_speed_kmh: 36,
  },
};
describe("measurement display", () => {
  it("exposes observed measurement evidence without implying a statistical error bound", async () => {
    const user = userEvent.setup();
    render(
      <SpeedPanel
        session={{
          ...session,
          measurements: [
            {
              ...valid,
              diagnostics: {
                calibration_check_error_m: 0.08349,
                minimum_region_margin_px: 4.56,
                maximum_observation_gap_s: 0.1406,
                maximum_contact_prediction_residual_px: 2.86,
                gate_a_near_samples: 3,
                gate_b_near_samples: 4,
                near_gate_distance_m: 2,
                gate_a_interpolation_interval_s: 0.08,
                gate_b_interpolation_interval_s: 0.12,
                ambiguous_observations: 1,
                overlapping_box_observations: 2,
                retained_position_samples: 12,
              },
            },
          ],
        }}
        onClear={vi.fn()}
      />,
    );
    const summary = screen.getByText("Measurement evidence");
    await user.click(summary);
    expect(summary.closest("details")).toHaveAttribute("open");
    for (const [label, value] of [
      ["Calibration check RMSE · m", "0.083"],
      ["Minimum hull margin · px", "4.6"],
      ["Maximum observation gap · s", "0.141"],
      ["Maximum motion residual · px", "2.9"],
      ["Gate A / B interpolation · s", "0.080 / 0.120"],
      ["Samples within 2 m of A / B", "3 / 4"],
      ["Ambiguous / overlapping observations", "1 / 2"],
    ])
      expect(
        within(screen.getByText(label).parentElement!).getByText(value),
      ).toBeVisible();
    expect(
      screen.getByText(/These observations are not an error bound/),
    ).toBeVisible();
    expect(
      screen.getByText(
        /retained source samples and original calibration geometry/,
      ),
    ).toBeVisible();
  });
  it("distinguishes unavailable evidence from zero and links completed history exports", async () => {
    const user = userEvent.setup();
    const onClear = vi.fn();
    render(
      <SpeedPanel
        session={{
          ...session,
          measurements: [
            {
              ...valid,
              diagnostics: {
                calibration_check_error_m: null,
                minimum_region_margin_px: null,
                maximum_observation_gap_s: 0,
                maximum_contact_prediction_residual_px: null,
                gate_a_near_samples: 0,
                gate_b_near_samples: 0,
                near_gate_distance_m: 2,
                gate_a_interpolation_interval_s: null,
                gate_b_interpolation_interval_s: null,
                ambiguous_observations: 0,
                overlapping_box_observations: 0,
                retained_position_samples: 0,
              },
            },
          ],
        }}
        onClear={onClear}
      />,
    );
    await user.click(screen.getByText("Measurement evidence"));
    expect(screen.getByText("No independent checks")).toBeVisible();
    expect(
      within(
        screen.getByText("Maximum observation gap · s").parentElement!,
      ).getByText("0.000"),
    ).toBeVisible();
    expect(
      within(
        screen.getByText("Minimum hull margin · px").parentElement!,
      ).getByText("—"),
    ).toBeVisible();
    expect(
      within(
        screen.getByText("Gate A / B interpolation · s").parentElement!,
      ).getByText("— / —"),
    ).toBeVisible();
    for (const format of ["CSV", "JSON"]) {
      const link = screen.getByRole("link", { name: `Export ${format}` });
      expect(link).toHaveAttribute(
        "href",
        `/api/exports/measurements?format=${format.toLowerCase()}`,
      );
      expect(link).toHaveAttribute("download");
    }
    await user.click(screen.getByRole("button", { name: "Clear history" }));
    expect(onClear).toHaveBeenCalledOnce();
  });
  it("distinguishes valid, approximate, and rejected results and their reasons", () => {
    render(<SpeedPanel session={session} onClear={vi.fn()} />);
    const table = screen.getByRole("table", {
      name: "Speed measurement history",
    });
    const rejected = within(table).getByText("#008").closest("tr")!;
    expect(rejected).toHaveTextContent("rejected");
    expect(rejected).toHaveTextContent("Track lost between gates.");
    expect(rejected).not.toHaveTextContent("500");
    expect(within(table).getByText("#007").closest("tr")).toHaveTextContent(
      "36.0",
    );
    expect(within(table).getByText("#009").closest("tr")).toHaveTextContent(
      "35.5approx.",
    );
    expect(
      screen.getByText(/not an independent accuracy certification/),
    ).toBeInTheDocument();
  });
  it("withholds numeric speeds when calibration is unavailable", () => {
    render(
      <SpeedPanel
        session={{ ...session, calibration_status: "incompatible" }}
        onClear={vi.fn()}
      />,
    );
    expect(screen.queryByText("36.0")).not.toBeInTheDocument();
    expect(screen.queryByText("35.5")).not.toBeInTheDocument();
  });
  it("shows an honest empty state without a fabricated observation table", () => {
    render(<SpeedPanel session={initialSession} onClear={vi.fn()} />);
    expect(screen.getByText("No completed measurements")).toBeInTheDocument();
    expect(screen.queryByRole("table")).not.toBeInTheDocument();
    expect(
      screen.queryByRole("link", { name: /Export/ }),
    ).not.toBeInTheDocument();
    expect(screen.queryByText("Measurement evidence")).not.toBeInTheDocument();
    expect(
      screen.getByRole("button", { name: "Clear history" }),
    ).toBeDisabled();
  });
});
