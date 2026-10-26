import { describe, expect, it, vi } from "vitest";
import { fireEvent, render, screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import Showcase, { showcaseSteps } from "./Showcase";
import StaticShowcase from "./StaticShowcase";
import {
  showcaseAnalysis,
  showcaseArtifact,
  showcaseBenchmarks,
  showcaseDownloads,
  showcaseTracks,
  showcaseTrajectories,
} from "./showcaseData";

describe("Guided showcase", () => {
  it("visits all ten real capabilities and bounds previous/next navigation", async () => {
    const user = userEvent.setup();
    render(<Showcase />);
    expect(screen.getByText("SYNTHETIC DEMONSTRATION")).toBeVisible();
    expect(
      screen.getByText("STORED OUTPUTS · NO ACTIVE INFERENCE"),
    ).toBeVisible();
    expect(
      screen.getByRole("button", { name: "Previous step" }),
    ).toBeDisabled();
    for (let index = 0; index < showcaseSteps.length; index++) {
      expect(
        screen.getByRole("heading", { name: showcaseSteps[index].title }),
      ).toBeVisible();
      expect(
        within(
          screen.getByRole("navigation", { name: "Guided demo steps" }),
        ).getByRole("button", { current: "step" }),
      ).toHaveTextContent(showcaseSteps[index].title);
      if (index < showcaseSteps.length - 1)
        await user.click(screen.getByRole("button", { name: "Next step" }));
    }
    expect(screen.getByRole("button", { name: "Next step" })).toBeDisabled();
    await user.click(screen.getByRole("button", { name: "Previous step" }));
    expect(
      screen.getByRole("heading", { name: "Traffic analytics" }),
    ).toBeVisible();
  });

  it("supports keyboard step navigation without stealing keys from the frame slider", () => {
    render(<Showcase />);
    const navigation = screen.getByRole("group", { name: "Step navigation" });
    fireEvent.keyDown(screen.getByRole("slider"), { key: "ArrowRight" });
    expect(
      screen.getByRole("heading", { name: "Vehicle detection" }),
    ).toBeVisible();
    fireEvent.keyDown(navigation, { key: "End" });
    expect(
      screen.getByRole("heading", { name: "Validation & benchmarking" }),
    ).toBeVisible();
    fireEvent.keyDown(navigation, { key: "ArrowLeft" });
    expect(
      screen.getByRole("heading", { name: "Traffic analytics" }),
    ).toBeVisible();
    fireEvent.keyDown(navigation, { key: "Home" });
    fireEvent.keyDown(navigation, { key: "ArrowRight" });
    expect(
      screen.getByRole("heading", { name: "Multi-object tracking" }),
    ).toBeVisible();
  });

  it("opens the corresponding existing application views", async () => {
    const user = userEvent.setup();
    const open = vi.fn();
    render(<Showcase onOpenView={open} />);
    for (const [step, view, label] of [
      ["03 Perspective calibration", "calibration", "Calibration & gates"],
      ["09 Traffic analytics", "traffic", "Traffic Intelligence"],
      ["10 Validation & benchmarking", "validation", "Validation & benchmarks"],
    ]) {
      await user.click(screen.getByRole("button", { name: step }));
      await user.click(screen.getByRole("button", { name: `Open ${label}` }));
      expect(open).toHaveBeenLastCalledWith(view);
    }
  });

  it("scrubs original source coordinates and reuses the live track table", async () => {
    const user = userEvent.setup();
    render(<Showcase />);
    await user.click(
      screen.getByRole("button", { name: "02 Multi-object tracking" }),
    );
    expect(
      screen.getByRole("heading", { name: "Current tracks" }),
    ).toBeVisible();
    fireEvent.change(screen.getByRole("slider"), { target: { value: "20" } });
    expect(
      screen.getByRole("img", {
        name: /Synthetic fixture frame 21, source time 10.0 seconds/,
      }),
    ).toBeVisible();
    expect(
      screen.getByText(/Confidence values are supplied inputs/),
    ).toBeVisible();
  });

  it("uses interactive shared charts with the real stored synthetic totals", async () => {
    const user = userEvent.setup();
    render(<Showcase />);
    await user.click(
      screen.getByRole("button", { name: "09 Traffic analytics" }),
    );
    expect(
      screen.getByRole("img", { name: "Vehicle count over source time" }),
    ).toBeVisible();
    await user.selectOptions(
      screen.getByLabelText("Count trend display"),
      "rate",
    );
    expect(
      screen.getByRole("img", { name: /0.0–60.0 s: 6.0504/ }),
    ).toBeVisible();
    expect(
      screen.getByText(
        /Attached speeds test aggregation; they were not measured/,
      ),
    ).toBeVisible();
  });

  it("retains late unsupported fixture inputs without treating them as supported live detector classes", async () => {
    const user = userEvent.setup();
    render(<Showcase />);
    await user.click(
      screen.getByRole("button", { name: "02 Multi-object tracking" }),
    );
    fireEvent.change(screen.getByRole("slider"), { target: { value: "108" } });
    expect(showcaseTrajectories.frames[108].tracks[0].category).toBe(
      "unsupported",
    );
    expect(showcaseTracks(108)).toEqual([]);
    expect(screen.getByText("#6 · unsupported · known input")).toBeVisible();
    expect(screen.getByText("No tracks to inspect yet")).toBeVisible();
    expect(
      showcaseAnalysis.classes.find((row) => row.category === "unknown")?.count,
    ).toBe(1);
  });
});

describe("Bundled evidence", () => {
  it("keeps the original synthetic artifact and export totals consistent", () => {
    expect(showcaseArtifact.provenance).toBe("synthetic");
    expect(showcaseTrajectories.provenance).toBe("synthetic");
    expect(showcaseTrajectories.frames).toHaveLength(120);
    expect(showcaseAnalysis.summary.total_crossings).toBe(
      showcaseArtifact.events.filter((event) => event.status === "counted")
        .length,
    );
    expect(
      showcaseAnalysis.classes.reduce((sum, item) => sum + item.count, 0),
    ).toBe(6);
    expect(
      showcaseAnalysis.classes.find((row) => row.category === "unknown")?.count,
    ).toBe(1);
    expect(showcaseAnalysis.speeds.n).toBe(4);
    expect(
      showcaseAnalysis.speeds.distribution.reduce(
        (sum, row) => sum + row.count,
        0,
      ),
    ).toBe(4);
    expect(showcaseAnalysis.speeds.mean_kmh).toBe(28.5);
    expect(showcaseAnalysis.flow[0].complete_window).toBe(false);
    expect(showcaseTracks(8)[0].history.at(-1)).toEqual([45, 66]);
  });

  it("retains separate measured workloads and downloadable source reports", () => {
    expect(showcaseBenchmarks.counting.actual_crossings).toBe(17);
    expect(showcaseBenchmarks.model.frames).toBe(12);
    expect(showcaseBenchmarks.model.timings.detection_ms.mean_ms).toBeCloseTo(
      176.377575,
      5,
    );
    expect(showcaseBenchmarks.traffic.workload.dense_tracks_per_frame).toBe(32);
    expect(showcaseDownloads).toHaveLength(6);
    for (const asset of showcaseDownloads) expect(asset.url).toMatch(/\.json/);
  });
});

describe("Backend-free static showcase", () => {
  it("needs no API, camera, uploads or model inference while navigating and charting", async () => {
    const fetch = vi.fn(() =>
      Promise.reject(new Error("A static showcase must not fetch an API")),
    );
    vi.stubGlobal("fetch", fetch);
    const user = userEvent.setup();
    try {
      render(<StaticShowcase />);
      expect(screen.getByText("STATIC PORTFOLIO PREVIEW")).toBeVisible();
      expect(
        screen.getByText("Read-only portfolio build · no backend connection"),
      ).toBeVisible();
      await user.click(
        screen.getByRole("button", { name: "09 Traffic analytics" }),
      );
      await user.selectOptions(
        screen.getByLabelText("Count trend display"),
        "cumulative",
      );
      expect(
        screen.getByRole("img", { name: "Vehicle-class distribution" }),
      ).toBeVisible();
      expect(
        screen.queryByRole("button", { name: /^Open / }),
      ).not.toBeInTheDocument();
      expect(screen.queryByLabelText(/Upload/i)).not.toBeInTheDocument();
      expect(fetch).not.toHaveBeenCalled();
    } finally {
      vi.unstubAllGlobals();
    }
  });
});
