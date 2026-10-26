import { describe, expect, it } from "vitest";
import { fireEvent, render, screen } from "@testing-library/react";
import TrafficCharts, { flowChartRows, TrafficBarChart } from "./TrafficCharts";
import { trafficAnalysis } from "./trafficTestFixtures";
describe("traffic chart transformations", () => {
  it("bounds displayed chart rows and tolerates a focused group disappearing after filtering", () => {
    const rows = Array.from({ length: 70 }, (_, i) => ({
      label: `group ${i}`,
      value: i,
    }));
    const view = render(
      <TrafficBarChart title="Bounded flow" unit="crossings" rows={rows} />,
    );
    expect(screen.getByText(/latest 60 of 70 groups/)).toBeVisible();
    fireEvent.focus(
      screen.getByRole("img", { name: "group 69: 69 crossings" }),
    );
    view.rerender(
      <TrafficBarChart
        title="Bounded flow"
        unit="crossings"
        rows={[rows[0]]}
      />,
    );
    expect(
      screen.getByText("1 groups · focus or hover a bar for details"),
    ).toBeVisible();
  });
  it("distinguishes source-window counts from normalized rates and cumulative counts", () => {
    expect(flowChartRows(trafficAnalysis.flow, "count")[0]).toMatchObject({
      value: 2,
      note: expect.stringContaining("partial interval"),
    });
    expect(flowChartRows(trafficAnalysis.flow, "rate")[0].value).toBe(4);
    expect(
      flowChartRows(
        [{ ...trafficAnalysis.flow[0], normalized_crossings_per_minute: null }],
        "rate",
      ),
    ).toEqual([]);
  });
  it("reveals source coverage in keyboard and pointer chart details", () => {
    render(
      <TrafficBarChart
        title="Test flow"
        unit="crossings"
        rows={flowChartRows(trafficAnalysis.flow, "count")}
      />,
    );
    fireEvent.focus(
      screen.getByRole("img", { name: "0.0–60.0 s: 2 crossings" }),
    );
    expect(
      screen.getByText(/30.0 s covered · partial interval/, { selector: "p" }),
    ).toBeVisible();
  });
  it("shows honest empty speed and occupancy charts and supports trend changes", () => {
    render(<TrafficCharts analysis={trafficAnalysis} />);
    expect(
      screen.getByRole("img", { name: "Vehicle count over source time" }),
    ).toBeVisible();
    expect(screen.getAllByText("No observations in this filter.")).toHaveLength(
      2,
    );
    fireEvent.change(screen.getByLabelText("Count trend display"), {
      target: { value: "rate" },
    });
    expect(
      screen.getByRole("img", { name: "0.0–60.0 s: 4 crossings/min" }),
    ).toBeVisible();
  });
});
