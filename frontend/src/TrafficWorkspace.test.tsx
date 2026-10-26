import { beforeEach, describe, expect, it, vi } from "vitest";
import {
  act,
  fireEvent,
  render,
  screen,
  waitFor,
  within,
} from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import TrafficWorkspace from "./TrafficWorkspace";
import { trafficApi } from "./trafficApi";
import { fieldApi } from "./fieldApi";
import { api } from "./api";
import { downloadResult } from "./validationApi";
import {
  trafficAnalysis,
  trafficArtifact,
  trafficConfig,
  trafficOverlays,
  trafficSession,
} from "./trafficTestFixtures";
import { initialSession } from "./useSession";
import type { TrafficAnalysis } from "./trafficTypes";

vi.mock("./trafficApi", () => ({
  trafficApi: {
    current: vi.fn(),
    list: vi.fn(),
    configuration: vi.fn(),
    configure: vi.fn(),
    overlays: vi.fn(),
    setOverlays: vi.fn(),
    analyze: vi.fn(),
    example: vi.fn(),
    archive: vi.fn(),
    export: vi.fn(),
    evaluate: vi.fn(),
  },
}));
vi.mock("./fieldApi", () => ({ fieldApi: { list: vi.fn() } }));
vi.mock("./api", () => ({
  api: { freeze: vi.fn(), calibrations: vi.fn(), overlays: vi.fn() },
}));
vi.mock("./validationApi", () => ({ downloadResult: vi.fn() }));
const saved = {
  id: "archive-1",
  session_id: "observation-1",
  name: "Synthetic approach",
  provenance: "synthetic",
};
beforeEach(() => {
  vi.clearAllMocks();
  vi.mocked(trafficApi.current).mockResolvedValue({
    snapshot: trafficArtifact,
    analytics: trafficAnalysis,
  });
  vi.mocked(trafficApi.configuration).mockResolvedValue(trafficConfig);
  vi.mocked(trafficApi.list).mockResolvedValue({ sessions: [saved] });
  vi.mocked(trafficApi.overlays).mockResolvedValue(trafficOverlays);
  vi.mocked(trafficApi.setOverlays).mockImplementation(async (value) => value);
  vi.mocked(trafficApi.analyze).mockImplementation(async (value) => ({
    ...trafficAnalysis,
    events: trafficAnalysis.events.filter(
      (e) =>
        (!value.category || e.category === value.category) &&
        (!value.direction || e.direction === value.direction) &&
        (!value.status || e.status === value.status),
    ),
  }));
  vi.mocked(trafficApi.example).mockResolvedValue(trafficArtifact);
  vi.mocked(trafficApi.archive).mockResolvedValue(trafficArtifact);
  vi.mocked(trafficApi.export).mockResolvedValue(new Blob(["synthetic rows"]));
  vi.mocked(fieldApi.list).mockResolvedValue({ sessions: [] });
});
async function ready() {
  const user = userEvent.setup();
  render(<TrafficWorkspace session={trafficSession} connected visible />);
  await waitFor(() => expect(trafficApi.analyze).toHaveBeenCalled());
  await screen.findByText("4", { selector: ".metric-value" });
  return user;
}
function card(label: string) {
  return screen
    .getByText(label, { selector: ".metric-label" })
    .closest<HTMLElement>(".metric-card")!;
}
describe("Traffic Intelligence workspace", () => {
  it("pages retained events without reducing the export selection", async () => {
    vi.mocked(trafficApi.analyze).mockResolvedValue({
      ...trafficAnalysis,
      events: Array.from({ length: 205 }, (_, i) => ({
        ...trafficAnalysis.events[0],
        id: `event-${i}`,
        track_id: i + 1,
      })),
    });
    const user = await ready();
    await user.click(screen.getByRole("tab", { name: "Traffic events" }));
    expect(
      within(
        screen.getByRole("table", { name: "Traffic crossing events" }),
      ).getAllByRole("row"),
    ).toHaveLength(101);
    await user.click(screen.getByRole("button", { name: "Next event page" }));
    await user.click(screen.getByRole("button", { name: "Next event page" }));
    expect(
      within(
        screen.getByRole("table", { name: "Traffic crossing events" }),
      ).getAllByRole("row"),
    ).toHaveLength(6);
    expect(
      screen.getByRole("button", { name: "Next event page" }),
    ).toBeDisabled();
    await user.click(screen.getByRole("tab", { name: "Compare & export" }));
    await user.click(
      screen.getByRole("button", { name: "Export traffic JSON" }),
    );
    expect(trafficApi.export).toHaveBeenCalledWith(
      expect.objectContaining({ session_ids: [], include_current: true }),
      "events",
      "json",
    );
  });
  it("serializes observation dates with timezone separately from source seconds", async () => {
    await ready();
    fireEvent.change(screen.getByLabelText("Observation start after"), {
      target: { value: "2026-10-24T09:00" },
    });
    fireEvent.change(screen.getByLabelText("Observation start before"), {
      target: { value: "2026-10-24T10:00" },
    });
    await waitFor(() =>
      expect(trafficApi.analyze).toHaveBeenLastCalledWith(
        expect.objectContaining({
          observation_started_after: new Date("2026-10-24T09:00").toISOString(),
          observation_started_before: new Date(
            "2026-10-24T10:00",
          ).toISOString(),
        }),
      ),
    );
    expect(screen.getByLabelText("Start source time · s")).toHaveValue(null);
    fireEvent.change(screen.getByLabelText("Observation start before"), {
      target: { value: "2026-10-24T08:00" },
    });
    expect(await screen.findByRole("alert")).toHaveTextContent(
      "Observation date end must follow its start",
    );
  });
  it("makes bounded-history scope visible before exporting retained subsets", async () => {
    vi.mocked(trafficApi.analyze).mockResolvedValue({
      ...trafficAnalysis,
      summary: {
        ...trafficAnalysis.summary,
        incomplete_retained_data: true,
        count_scope: "retained_filtered",
      },
    });
    await ready();
    expect(
      screen.getByText(/This observation exceeded retained-history limits/),
    ).toBeVisible();
  });
  it("shows observed KPIs and refuses to invent uncalibrated metric speeds", async () => {
    await ready();
    expect(within(card("Observed crossings")).getByText("2")).toBeVisible();
    expect(within(card("Valid average speed")).getByText("—")).toBeVisible();
    expect(
      screen.getByText(/No valid calibrated speed measurements/),
    ).toBeVisible();
    expect(
      screen.getByText(/incomplete recordings are not hourly forecasts/),
    ).toBeVisible();
  });
  it("opens synthetic evidence explicitly and selects the archived fixture", async () => {
    const user = await ready();
    await user.click(
      screen.getByRole("button", { name: "Load synthetic traffic example" }),
    );
    expect(await screen.findByText(/SYNTHETIC EVIDENCE/)).toBeVisible();
    await waitFor(() =>
      expect(trafficApi.analyze).toHaveBeenLastCalledWith(
        expect.objectContaining({
          session_ids: ["archive-1"],
          include_current: false,
        }),
      ),
    );
    expect(
      screen.getByRole("checkbox", { name: /Synthetic approach/ }),
    ).toBeChecked();
  });
  it("filters the event table by class, direction, status and source time", async () => {
    const user = await ready();
    await user.click(screen.getByRole("tab", { name: "Traffic events" }));
    expect(
      within(
        screen.getByRole("table", { name: "Traffic crossing events" }),
      ).getAllByRole("row"),
    ).toHaveLength(3);
    await user.selectOptions(
      screen.getByLabelText("Vehicle class filter"),
      "truck",
    );
    await waitFor(() =>
      expect(
        within(
          screen.getByRole("table", { name: "Traffic crossing events" }),
        ).getAllByRole("row"),
      ).toHaveLength(2),
    );
    await user.selectOptions(
      screen.getByLabelText("Direction filter"),
      "negative",
    );
    await user.selectOptions(
      screen.getByLabelText("Event status filter"),
      "suppressed",
    );
    fireEvent.change(screen.getByLabelText("Start source time · s"), {
      target: { value: "2" },
    });
    fireEvent.change(screen.getByLabelText("End source time · s"), {
      target: { value: "9" },
    });
    await waitFor(() =>
      expect(trafficApi.analyze).toHaveBeenLastCalledWith(
        expect.objectContaining({
          category: "truck",
          direction: "negative",
          status: "suppressed",
          start_s: 2,
          end_s: 9,
        }),
      ),
    );
    expect(screen.getByText("possible_fragmented_identity")).toBeVisible();
  });
  it("selects sessions and aggregation intervals for comparison without conflating source clocks", async () => {
    const user = await ready();
    await user.click(
      screen.getByRole("checkbox", { name: /Synthetic approach/ }),
    );
    await user.click(
      screen.getByRole("checkbox", { name: /Current observation/ }),
    );
    await user.selectOptions(
      screen.getByLabelText("Aggregation interval"),
      "15",
    );
    await user.click(screen.getByRole("tab", { name: "Compare & export" }));
    expect(
      screen.getByText(/Different durations, incomplete coverage/),
    ).toBeVisible();
    await waitFor(() =>
      expect(trafficApi.analyze).toHaveBeenLastCalledWith(
        expect.objectContaining({
          session_ids: ["archive-1"],
          include_current: false,
          interval_minutes: 15,
        }),
      ),
    );
  });
  it("exports all seven table types with the active request and exact extension", async () => {
    const user = await ready();
    await user.click(screen.getByRole("tab", { name: "Compare & export" }));
    for (const table of [
      "events",
      "classes",
      "flow",
      "zones",
      "speeds",
      "comparisons",
      "quality",
    ]) {
      await user.selectOptions(
        screen.getByLabelText("Traffic export table"),
        table,
      );
      await user.click(
        screen.getByRole("button", { name: "Export traffic CSV" }),
      );
      await waitFor(() =>
        expect(downloadResult).toHaveBeenLastCalledWith(
          expect.any(Blob),
          `roadlens-traffic-${table}.csv`,
        ),
      );
    }
    await user.click(
      screen.getByRole("button", { name: "Export traffic JSON" }),
    );
    expect(trafficApi.export).toHaveBeenLastCalledWith(
      expect.objectContaining({ speed_status: "valid" }),
      "quality",
      "json",
    );
  });
  it("keeps approximate speed evidence visibly separate", async () => {
    const user = await ready();
    await user.selectOptions(
      screen.getByLabelText("Speed evidence"),
      "approximate",
    );
    expect(screen.getByText("Approximate average speed")).toBeVisible();
    expect(
      screen.getByRole("heading", {
        name: "Approximate metric speed statistics",
      }),
    ).toBeVisible();
    expect(screen.queryByText("Valid average speed")).not.toBeInTheDocument();
    await waitFor(() =>
      expect(trafficApi.analyze).toHaveBeenLastCalledWith(
        expect.objectContaining({ speed_status: "approximate" }),
      ),
    );
  });
  it("handles a null initial snapshot and no archive without blocking the workspace", async () => {
    vi.mocked(trafficApi.current).mockResolvedValue({
      snapshot: null,
      analytics: trafficAnalysis,
    });
    vi.mocked(trafficApi.list).mockResolvedValue({ sessions: [] });
    render(<TrafficWorkspace session={initialSession} connected visible />);
    expect(
      await screen.findByText("No archived traffic observations."),
    ).toBeVisible();
    expect(
      screen.getByRole("button", { name: "Archive traffic observation" }),
    ).toBeDisabled();
    expect(screen.queryByRole("alert")).not.toBeInTheDocument();
  });
  it("controls traffic overlay flags independently of legacy boxes and speed layers", async () => {
    const user = await ready();
    await user.click(screen.getByRole("tab", { name: "Lines & zones" }));
    await user.click(screen.getByRole("checkbox", { name: "Tracking IDs" }));
    await waitFor(() =>
      expect(trafficApi.setOverlays).toHaveBeenCalledWith({
        ...trafficOverlays,
        track_ids: false,
      }),
    );
    expect(api.overlays).not.toHaveBeenCalled();
  });
  it("ignores late analytics responses after the user changes filters", async () => {
    await ready();
    let release!: (value: TrafficAnalysis) => void;
    vi.mocked(trafficApi.analyze).mockReturnValueOnce(
      new Promise((resolve) => {
        release = resolve;
      }),
    );
    fireEvent.change(screen.getByLabelText("Vehicle class filter"), {
      target: { value: "truck" },
    });
    await waitFor(() =>
      expect(trafficApi.analyze).toHaveBeenLastCalledWith(
        expect.objectContaining({ category: "truck" }),
      ),
    );
    fireEvent.change(screen.getByLabelText("Vehicle class filter"), {
      target: { value: "bus" },
    });
    await waitFor(() =>
      expect(trafficApi.analyze).toHaveBeenLastCalledWith(
        expect.objectContaining({ category: "bus" }),
      ),
    );
    await act(async () =>
      release({
        ...trafficAnalysis,
        summary: { ...trafficAnalysis.summary, total_crossings: 999 },
      }),
    );
    expect(
      within(card("Observed crossings")).queryByText("999"),
    ).not.toBeInTheDocument();
  });
  it("halts polling while hidden and preserves its filter draft", async () => {
    const view = render(
      <TrafficWorkspace session={trafficSession} connected visible={false} />,
    );
    expect(trafficApi.list).not.toHaveBeenCalled();
    expect(trafficApi.current).not.toHaveBeenCalled();
    view.rerender(
      <TrafficWorkspace session={trafficSession} connected visible />,
    );
    await waitFor(() => expect(trafficApi.current).toHaveBeenCalledOnce());
    fireEvent.change(screen.getByLabelText("Start source time · s"), {
      target: { value: "5" },
    });
    view.rerender(
      <TrafficWorkspace session={trafficSession} connected visible={false} />,
    );
    expect(screen.getByLabelText("Start source time · s")).toHaveValue(5);
  });
  it("blocks reversed source-time bounds and displays export failures", async () => {
    const user = await ready();
    fireEvent.change(screen.getByLabelText("Start source time · s"), {
      target: { value: "10" },
    });
    fireEvent.change(screen.getByLabelText("End source time · s"), {
      target: { value: "2" },
    });
    expect(await screen.findByRole("alert")).toHaveTextContent(
      "End source time must be after",
    );
    fireEvent.change(screen.getByLabelText("End source time · s"), {
      target: { value: "20" },
    });
    await user.click(screen.getByRole("tab", { name: "Compare & export" }));
    vi.mocked(trafficApi.export).mockRejectedValue(
      new Error("The selected archive is missing."),
    );
    await user.click(
      screen.getByRole("button", { name: "Export traffic JSON" }),
    );
    expect(await screen.findByRole("alert")).toHaveTextContent(
      "selected archive is missing",
    );
    expect(downloadResult).not.toHaveBeenCalled();
  });
});
