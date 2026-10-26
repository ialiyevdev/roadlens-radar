import { describe, expect, it } from "vitest";
import { render, screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import TrackTable from "./TrackTable";
import { initialSession } from "./useSession";
import type { Track } from "./types";

const track: Track = {
  id: 7,
  category: "car",
  bbox: [10, 20, 40, 50],
  confidence: 0.87,
  state: "confirmed",
  hits: 12,
  missed: 0,
  history: [[25, 50]],
  age_s: 2.346,
  observation_gap_s: 0.1256,
  world_position: [10.126, 4.345],
  measurement_state: "between_gates",
  association_ambiguous: true,
  position_diagnostics: [
    "Two nearby detections make the identity association uncertain.",
  ],
};

describe("track continuity inspection", () => {
  it("separates detection confidence from age, source observation gap, and uncertain identity", async () => {
    const user = userEvent.setup();
    render(
      <TrackTable
        session={{
          ...initialSession,
          calibration_status: "ready",
          tracks: [track],
        }}
      />,
    );
    const row = screen.getByText("#007").closest("tr")!;
    expect(within(row).getByText("87%")).toBeInTheDocument();
    expect(row).toHaveTextContent("2.35 / 0.126");
    expect(within(row).getByText(/identity uncertain/)).toBeInTheDocument();
    expect(within(row).getByText("10.13, 4.34")).toBeInTheDocument();
    expect(within(row).getByText("between gates")).toBeInTheDocument();
    await user.click(within(row).getByText("Position diagnostics"));
    expect(
      within(row).getByText(
        "Two nearby detections make the identity association uncertain.",
      ),
    ).toBeVisible();
    expect(
      screen.getByText(/Detection confidence describes the model prediction/),
    ).toHaveTextContent("It does not measure speed accuracy.");
  });
  it("does not substitute zero for legacy missing age and gap and retains lost-state evidence", () => {
    const { age_s, observation_gap_s, ...legacy } = track;
    void age_s;
    void observation_gap_s;
    render(
      <TrackTable
        session={{
          ...initialSession,
          tracks: [
            {
              ...legacy,
              state: "lost",
              missed: 2,
              association_ambiguous: false,
              position_diagnostics: [],
            },
          ],
        }}
      />,
    );
    const row = screen.getByText("#007").closest("tr")!;
    expect(row).toHaveTextContent("— / —");
    expect(within(row).getByText("lost")).toBeInTheDocument();
    expect(row).toHaveTextContent("2 missed");
    expect(
      within(row).queryByText(/identity uncertain/),
    ).not.toBeInTheDocument();
    expect(within(row).queryByText("10.13, 4.34")).not.toBeInTheDocument();
  });
  it("shows the empty state without inventing track age or certainty", () => {
    render(<TrackTable session={initialSession} />);
    expect(screen.getByText("No tracks to inspect yet")).toBeInTheDocument();
    expect(screen.queryByText(/identity uncertain/)).not.toBeInTheDocument();
    expect(screen.queryByText(/\d+\.\d+ \/ \d+\.\d+/)).not.toBeInTheDocument();
  });
});
