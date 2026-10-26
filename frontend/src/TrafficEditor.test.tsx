import { beforeEach, describe, expect, it, vi } from "vitest";
import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import TrafficEditor, { geometryMatches, groundToImage } from "./TrafficEditor";
import { api } from "./api";
import { trafficApi } from "./trafficApi";
import {
  trafficConfig,
  trafficFrame,
  trafficSession,
} from "./trafficTestFixtures";
import { initialSession } from "./useSession";

vi.mock("./api", () => ({ api: { freeze: vi.fn(), calibrations: vi.fn() } }));
vi.mock("./trafficApi", () => ({ trafficApi: { configure: vi.fn() } }));
beforeEach(() => {
  vi.clearAllMocks();
  vi.mocked(api.freeze).mockResolvedValue(trafficFrame);
  vi.mocked(api.calibrations).mockResolvedValue({ profiles: [] });
  vi.mocked(trafficApi.configure).mockImplementation(async (value) => value);
});
async function frozen(configuration = trafficConfig) {
  const user = userEvent.setup();
  render(
    <TrafficEditor
      session={trafficSession}
      connected
      configuration={configuration}
      onSaved={vi.fn()}
    />,
  );
  await user.click(
    screen.getByRole("button", { name: "Freeze counting frame" }),
  );
  const svg = await screen.findByRole("img", {
    name: "Traffic counting frame",
  });
  vi.spyOn(svg, "getBoundingClientRect").mockReturnValue({
    left: 0,
    top: 0,
    width: 640,
    height: 480,
    right: 640,
    bottom: 480,
    x: 0,
    y: 0,
    toJSON: () => ({}),
  });
  return { user, svg };
}
describe("traffic geometry editor", () => {
  it("saves removal of the final region so counting can be disabled", async () => {
    const { user } = await frozen();
    await user.selectOptions(
      screen.getByLabelText("Selected counting region"),
      "line:line-1",
    );
    await user.click(
      screen.getByRole("button", { name: "Delete selected region" }),
    );
    await user.click(
      screen.getByRole("button", { name: "Save traffic configuration" }),
    );
    await waitFor(() => expect(trafficApi.configure).toHaveBeenCalledOnce());
    expect(trafficApi.configure).toHaveBeenCalledWith(
      expect.objectContaining({ lines: [], zones: [] }),
    );
  });
  it("starts with no frame and never requires calibration for image regions", () => {
    render(
      <TrafficEditor
        session={initialSession}
        connected
        configuration={null}
        onSaved={vi.fn()}
      />,
    );
    expect(
      screen.getByRole("button", { name: "Freeze counting frame" }),
    ).toBeDisabled();
    expect(
      screen.getByText(/Image regions need no speed calibration/),
    ).toBeVisible();
    expect(
      screen.getByRole("button", { name: "Draw counting line" }),
    ).toBeDisabled();
  });
  it("draws a finite line, edits endpoints and direction labels, then saves source-bound coordinates", async () => {
    const { user, svg } = await frozen();
    await user.click(
      screen.getByRole("button", { name: "Draw counting line" }),
    );
    fireEvent.click(svg, { clientX: 100, clientY: 120 });
    fireEvent.click(svg, { clientX: 500, clientY: 120 });
    fireEvent.change(screen.getByLabelText("Counting line label"), {
      target: { value: "Second approach" },
    });
    fireEvent.change(screen.getByLabelText("Endpoint 1 x"), {
      target: { value: "110" },
    });
    fireEvent.change(screen.getByLabelText("Positive crossing label"), {
      target: { value: "Inbound" },
    });
    await user.click(
      screen.getByRole("button", { name: "Save traffic configuration" }),
    );
    await waitFor(() => expect(trafficApi.configure).toHaveBeenCalledOnce());
    expect(vi.mocked(trafficApi.configure).mock.calls[0][0]).toMatchObject({
      source_id: "video:fixture",
      geometry: trafficFrame.geometry,
      lines: [
        trafficConfig.lines[0],
        {
          label: "Second approach",
          start: [110, 120],
          end: [500, 120],
          positive_label: "Inbound",
        },
      ],
    });
  });
  it("creates overlapping image polygons, edits a vertex and deletes a selected zone", async () => {
    const { user, svg } = await frozen();
    await user.click(
      screen.getByRole("button", { name: "Draw monitoring zone" }),
    );
    for (const [x, y] of [
      [100, 100],
      [300, 100],
      [300, 300],
      [100, 300],
    ])
      fireEvent.click(svg, { clientX: x, clientY: y });
    await user.click(screen.getByRole("button", { name: "Finish polygon" }));
    fireEvent.change(screen.getByLabelText("Monitoring zone label"), {
      target: { value: "Waiting area" },
    });
    fireEvent.change(screen.getByLabelText("Vertex 2 x"), {
      target: { value: "320" },
    });
    await user.click(
      screen.getByRole("button", { name: "Save traffic configuration" }),
    );
    expect(
      vi.mocked(trafficApi.configure).mock.calls[0][0].zones[0],
    ).toMatchObject({
      label: "Waiting area",
      coordinate_space: "image",
      points: [
        [100, 100],
        [320, 100],
        [300, 300],
        [100, 300],
      ],
    });
    await user.click(
      screen.getByRole("button", { name: "Delete selected region" }),
    );
    expect(
      screen.queryByLabelText("Monitoring zone label"),
    ).not.toBeInTheDocument();
  });
  it("preserves dirty edits across configuration polling and blocks changed source geometry", async () => {
    const user = userEvent.setup();
    const view = render(
      <TrafficEditor
        session={trafficSession}
        connected
        configuration={trafficConfig}
        onSaved={vi.fn()}
      />,
    );
    fireEvent.change(screen.getByLabelText("Configuration name"), {
      target: { value: "My draft" },
    });
    view.rerender(
      <TrafficEditor
        session={trafficSession}
        connected
        configuration={{ ...trafficConfig, name: "Old polling name" }}
        onSaved={vi.fn()}
      />,
    );
    expect(screen.getByLabelText("Configuration name")).toHaveValue("My draft");
    vi.mocked(api.freeze).mockResolvedValue({
      ...trafficFrame,
      source_id: "video:another",
    });
    await user.click(
      screen.getByRole("button", { name: "Freeze counting frame" }),
    );
    expect(await screen.findByRole("alert")).toHaveTextContent(
      "Coordinates are never scaled",
    );
    expect(
      screen.getByRole("button", { name: "Save traffic configuration" }),
    ).toBeDisabled();
  });
  it("keeps edits pending and displays backend validation without discarding the draft", async () => {
    const { user } = await frozen();
    fireEvent.change(screen.getByLabelText("Configuration name"), {
      target: { value: "Retry draft" },
    });
    vi.mocked(trafficApi.configure).mockRejectedValue(
      new Error("High occupancy must exceed moderate occupancy."),
    );
    await user.click(
      screen.getByRole("button", { name: "Save traffic configuration" }),
    );
    expect(await screen.findByRole("alert")).toHaveTextContent(
      "High occupancy",
    );
    expect(screen.getByLabelText("Configuration name")).toHaveValue(
      "Retry draft",
    );
  });
  it("rejects source/undistorted and intrinsic-profile mismatches without scaling", () => {
    expect(geometryMatches(trafficConfig, trafficFrame)).toBe(true);
    expect(
      geometryMatches(trafficConfig, {
        ...trafficFrame,
        geometry: {
          ...trafficFrame.geometry,
          coordinate_space: "undistorted",
          intrinsic_profile_id: "lens",
        },
      }),
    ).toBe(false);
    expect(
      geometryMatches(trafficConfig, {
        ...trafficFrame,
        geometry: { ...trafficFrame.geometry, width: 1280 },
      }),
    ).toBe(false);
  });
  it("projects ground coordinates through inverse homography and rejects degenerate matrices", () => {
    const projected = groundToImage(
      [2, 4],
      [
        [0.1, 0, 0],
        [0, 0.1, 0],
        [0, 0, 1],
      ],
    )!;
    expect(projected[0]).toBeCloseTo(20);
    expect(projected[1]).toBeCloseTo(40);
    expect(
      groundToImage(
        [2, 4],
        [
          [0, 0, 0],
          [0, 0, 0],
          [0, 0, 0],
        ],
      ),
    ).toBeNull();
  });
});
