import { beforeEach, describe, expect, it, vi } from "vitest";
import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import CalibrationStudio from "./CalibrationStudio";
import { api } from "./api";
import { initialSession } from "./useSession";
import type {
  CalibrationDiagnostics,
  CalibrationProfile,
  FrozenFrame,
  GateDiagnostics,
  Session,
} from "./types";

vi.mock("./api", () => ({
  api: {
    calibrations: vi.fn(),
    freeze: vi.fn(),
    validateCalibration: vi.fn(),
    saveCalibration: vi.fn(),
    activateCalibration: vi.fn(),
    deleteCalibration: vi.fn(),
    saveGates: vi.fn(),
    resetGates: vi.fn(),
    invalidateCalibration: vi.fn(),
    overlays: vi.fn(),
  },
}));
const geometry = {
  width: 1280,
  height: 720,
  rotation: 0,
  mirrored: false,
  crop: null,
};
const frame: FrozenFrame = {
  frame_id: "frozen-1",
  source_id: "video:synthetic-test",
  geometry,
  session_id: "test-session",
  image_url: "/api/calibration/frame/frozen-1",
};
const diagnostics: CalibrationDiagnostics = {
  valid: true,
  errors: [],
  warnings: ["No independent check points were provided."],
  homography: [
    [1, 0, 0],
    [0, 1, 0],
    [0, 0, 1],
  ],
  region_image: [
    [0, 0],
    [1280, 0],
    [1280, 720],
    [0, 720],
  ],
  grid_image: [
    [
      [64, 36],
      [576, 36],
    ],
  ],
  inliers: [true, true, true, true],
  coverage: 0.64,
  fit_error_m: 0,
  fit_error_px: 0,
  check_error_m: null,
  condition_number: 12,
};
const profile: CalibrationProfile = {
  id: "cal-one",
  name: "Synthetic measured rectangle",
  source_id: frame.source_id,
  geometry,
  points: [
    { image: [128, 72], world: [0, 0] },
    { image: [1152, 72], world: [10, 0] },
    { image: [1152, 648], world: [10, 20] },
    { image: [128, 648], world: [0, 20] },
  ],
  check_points: [],
  diagnostics,
  gates: null,
};
const session: Session = {
  ...initialSession,
  state: "running",
  session_id: frame.session_id,
  source_id: frame.source_id,
  geometry,
  width: 1280,
  height: 720,
  frame_index: 10,
};
const perform = vi.fn(async (operation: () => Promise<Session>) => {
  await operation();
});

beforeEach(() => {
  vi.resetAllMocks();
  vi.mocked(api.calibrations).mockResolvedValue({ profiles: [profile] });
  vi.mocked(api.freeze).mockResolvedValue(frame);
  vi.mocked(api.validateCalibration).mockResolvedValue(diagnostics);
  vi.mocked(api.saveCalibration).mockResolvedValue(profile);
  vi.mocked(api.activateCalibration).mockResolvedValue({
    ...session,
    calibration_status: "ready",
    calibration_id: profile.id,
  });
  vi.mocked(api.resetGates).mockResolvedValue({});
});
async function frozen(current: Session = session) {
  const user = userEvent.setup();
  render(<CalibrationStudio session={current} connected perform={perform} />);
  await user.click(screen.getByRole("button", { name: "Freeze frame" }));
  const canvas = await screen.findByRole("img", { name: /Frozen road frame/ });
  vi.spyOn(canvas, "getBoundingClientRect").mockReturnValue({
    left: 0,
    top: 0,
    width: 640,
    height: 360,
    right: 640,
    bottom: 360,
    x: 0,
    y: 0,
    toJSON: () => ({}),
  });
  return { user, canvas };
}
function addReferences(canvas: HTMLElement) {
  [
    [64, 36],
    [576, 36],
    [576, 324],
    [64, 324],
  ].forEach(([clientX, clientY]) =>
    fireEvent.click(canvas, { clientX, clientY }),
  );
}
function measuredForm() {
  fireEvent.change(screen.getByLabelText("Calibration profile name"), {
    target: { value: "Synthetic measured rectangle" },
  });
  const coordinates = [
    [0, 0],
    [10, 0],
    [10, 20],
    [0, 20],
  ];
  for (let i = 0; i < coordinates.length; i++) {
    fireEvent.change(screen.getByLabelText(`Point ${i + 1} world X meters`), {
      target: { value: String(coordinates[i][0]) },
    });
    fireEvent.change(screen.getByLabelText(`Point ${i + 1} world Y meters`), {
      target: { value: String(coordinates[i][1]) },
    });
  }
}

describe("calibration workflow", () => {
  it("retains source pixels on a scaled frame and requires measured coordinates", async () => {
    const { user, canvas } = await frozen();
    addReferences(canvas);
    expect(screen.getByLabelText("Point 1 source x")).toHaveValue(128);
    expect(screen.getByLabelText("Point 1 source y")).toHaveValue(72);
    expect(screen.getByLabelText("Point 1 world X meters")).toHaveValue(null);
    await user.type(
      screen.getByLabelText("Calibration profile name"),
      "Unmeasured",
    );
    await user.click(
      screen.getByRole("button", { name: "Validate calibration" }),
    );
    expect(await screen.findByRole("alert")).toHaveTextContent(
      "measured, finite world X and Y",
    );
    expect(api.validateCalibration).not.toHaveBeenCalled();
  });
  it("validates measured input and displays independent-check limitations before saving", async () => {
    const { user, canvas } = await frozen();
    addReferences(canvas);
    measuredForm();
    await user.click(
      screen.getByRole("button", { name: "Validate calibration" }),
    );
    expect(await screen.findByText("Geometry accepted")).toBeInTheDocument();
    expect(
      screen.getByText("No independent check points were provided."),
    ).toBeInTheDocument();
    expect(api.validateCalibration).toHaveBeenCalledWith(
      expect.objectContaining({
        source_id: frame.source_id,
        geometry,
        points: profile.points,
        check_points: [],
      }),
    );
    await user.click(screen.getByRole("button", { name: "Save profile" }));
    await waitFor(() =>
      expect(api.saveCalibration).toHaveBeenCalledWith(
        expect.objectContaining({ points: profile.points }),
        undefined,
      ),
    );
    expect(
      await screen.findByRole("button", { name: "Update profile" }),
    ).toBeInTheDocument();
  });
  it("keeps a cleared source coordinate blank, rejects it, and accepts retyped pixels without an extra zero", async () => {
    const { user, canvas } = await frozen();
    addReferences(canvas);
    measuredForm();
    const coordinate = screen.getByLabelText("Point 1 source x");
    await user.clear(coordinate);
    expect(coordinate).toHaveValue(null);
    expect(screen.getByRole("button", { name: "Save profile" })).toBeDisabled();
    await user.click(
      screen.getByRole("button", { name: "Validate calibration" }),
    );
    expect(await screen.findByRole("alert")).toHaveTextContent(
      "Enter finite source x/y coordinates for every reference point.",
    );
    expect(api.validateCalibration).not.toHaveBeenCalled();
    await user.type(coordinate, "128");
    expect(coordinate).toHaveValue(128);
    await user.click(
      screen.getByRole("button", { name: "Validate calibration" }),
    );
    await waitFor(() =>
      expect(api.validateCalibration).toHaveBeenCalledWith(
        expect.objectContaining({ points: profile.points }),
      ),
    );
  });
  it("keeps check points independent and exposes geometry rejection reasons", async () => {
    const { user, canvas } = await frozen();
    addReferences(canvas);
    measuredForm();
    fireEvent.click(canvas, { clientX: 320, clientY: 180 });
    await user.type(screen.getByLabelText("Point 5 world X meters"), "5");
    await user.type(screen.getByLabelText("Point 5 world Y meters"), "10");
    await user.selectOptions(screen.getByLabelText("Point 5 role"), "check");
    vi.mocked(api.validateCalibration).mockResolvedValue({
      ...diagnostics,
      valid: false,
      errors: ["Independent projection error is too large."],
      warnings: [],
    });
    await user.click(
      screen.getByRole("button", { name: "Validate calibration" }),
    );
    expect(
      await screen.findByText("Independent projection error is too large."),
    ).toBeInTheDocument();
    expect(api.validateCalibration).toHaveBeenCalledWith(
      expect.objectContaining({
        check_points: [{ image: [640, 360], world: [5, 10] }],
      }),
    );
    expect(screen.getByRole("button", { name: "Save profile" })).toBeDisabled();
  });
  it("requires stationary-camera confirmation before applying a saved profile", async () => {
    const { user } = await frozen();
    await user.selectOptions(
      screen.getByLabelText("Saved calibration profiles"),
      profile.id,
    );
    const apply = screen.getByRole("button", {
      name: "Apply to this observation",
    });
    expect(apply).toBeDisabled();
    await user.click(screen.getByLabelText(/I confirm the camera/));
    await user.click(apply);
    await waitFor(() =>
      expect(api.activateCalibration).toHaveBeenCalledWith(profile.id),
    );
  });
  it("does not apply stale saved coordinates after editing a loaded profile", async () => {
    const { user } = await frozen({
      ...session,
      calibration_status: "ready",
      calibration_id: profile.id,
    });
    await user.selectOptions(
      screen.getByLabelText("Saved calibration profiles"),
      profile.id,
    );
    await user.click(screen.getByLabelText(/I confirm the camera/));
    const apply = screen.getByRole("button", {
      name: "Apply to this observation",
    });
    expect(apply).toBeEnabled();
    fireEvent.change(screen.getByLabelText("Point 1 world X meters"), {
      target: { value: "1" },
    });
    expect(apply).toBeDisabled();
    expect(screen.getByLabelText(/I confirm the camera/)).not.toBeChecked();
    expect(
      screen.getByText(
        "Unsaved references; validate and update profile before applying.",
      ),
    ).toBeInTheDocument();
    expect(screen.getByText("Calibration active")).toBeInTheDocument();
    await user.click(apply);
    expect(api.activateCalibration).not.toHaveBeenCalled();
    expect(api.invalidateCalibration).not.toHaveBeenCalled();
    await user.click(
      screen.getByRole("button", { name: "Validate calibration" }),
    );
    await screen.findByText("Geometry accepted");
    expect(apply).toBeDisabled();
    await user.click(screen.getByRole("button", { name: "Update profile" }));
    await waitFor(() =>
      expect(
        screen.queryByText(
          "Unsaved references; validate and update profile before applying.",
        ),
      ).not.toBeInTheDocument(),
    );
    expect(api.saveCalibration).toHaveBeenCalledWith(
      expect.objectContaining({
        points: [
          { image: [128, 72], world: [1, 0] },
          ...profile.points.slice(1),
        ],
      }),
      profile.id,
    );
    expect(apply).toBeDisabled();
    await user.click(screen.getByLabelText(/I confirm the camera/));
    await user.click(apply);
    await waitFor(() =>
      expect(api.activateCalibration).toHaveBeenCalledWith(profile.id),
    );
  });
  it("draws gates in source coordinates, edits an endpoint, and saves reverse traversal", async () => {
    const { user, canvas } = await frozen({
      ...session,
      calibration_status: "ready",
      calibration_id: profile.id,
    });
    await user.click(screen.getByRole("button", { name: "Draw Gate A" }));
    fireEvent.click(canvas, { clientX: 100, clientY: 100 });
    fireEvent.click(canvas, { clientX: 500, clientY: 100 });
    await user.click(screen.getByRole("button", { name: "Draw Gate B" }));
    fireEvent.click(canvas, { clientX: 100, clientY: 250 });
    fireEvent.click(canvas, { clientX: 500, clientY: 250 });
    const endpoint = screen.getByLabelText("Gate A endpoint 1 x");
    await user.clear(endpoint);
    expect(endpoint).toHaveValue(null);
    await user.click(screen.getByRole("button", { name: "Save gates" }));
    expect(await screen.findByRole("alert")).toHaveTextContent(
      "Gate A needs finite pixel coordinates.",
    );
    expect(api.saveGates).not.toHaveBeenCalled();
    await user.type(endpoint, "210");
    expect(endpoint).toHaveValue(210);
    await user.click(screen.getByLabelText("Also accept B → A"));
    const gates: GateDiagnostics = {
      valid: true,
      errors: [],
      warnings: [],
      gate_a: [
        [210, 200],
        [1000, 200],
      ],
      gate_b: [
        [200, 500],
        [1000, 500],
      ],
      allow_reverse: true,
    };
    vi.mocked(api.saveGates).mockResolvedValue(gates);
    await user.click(screen.getByRole("button", { name: "Save gates" }));
    await waitFor(() =>
      expect(api.saveGates).toHaveBeenCalledWith({
        gate_a: gates.gate_a,
        gate_b: gates.gate_b,
        allow_reverse: true,
      }),
    );
    expect(
      await screen.findByText("Gates saved to the active profile."),
    ).toBeInTheDocument();
    await user.click(screen.getByRole("button", { name: "Reset gates" }));
    expect(
      await screen.findByText("Gate configuration reset."),
    ).toBeInTheDocument();
    expect(
      screen.queryByLabelText("Gate A endpoint 1 x"),
    ).not.toBeInTheDocument();
  });
  it("rejects incomplete gate drafts with a useful message", async () => {
    const { user } = await frozen({ ...session, calibration_status: "ready" });
    await user.click(screen.getByRole("button", { name: "Save gates" }));
    expect(await screen.findByRole("alert")).toHaveTextContent(
      "Draw two endpoints for both Gate A and Gate B.",
    );
    expect(api.saveGates).not.toHaveBeenCalled();
  });
});
