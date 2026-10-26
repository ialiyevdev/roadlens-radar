import { beforeEach, describe, expect, it, vi } from "vitest";
import {
  fireEvent,
  render,
  screen,
  waitFor,
  within,
} from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import App from "./App";
import { api } from "./api";
import { validationApi } from "./validationApi";
import { fieldApi } from "./fieldApi";
import { cameraApi } from "./cameraApi";
import { initialSession } from "./useSession";
import type { Session } from "./types";

vi.mock("./api", () => ({
  api: {
    health: vi.fn(),
    session: vi.fn(),
    cameras: vi.fn(),
    start: vi.fn(),
    control: vi.fn(),
    upload: vi.fn(),
    calibrations: vi.fn(),
  },
}));
vi.mock("./fieldApi", () => ({
  fieldApi: {
    list: vi.fn(),
    sources: vi.fn(),
    eligibility: vi.fn(),
    annotationMetrics: vi.fn(),
  },
}));
vi.mock("./cameraApi", () => ({ cameraApi: { profiles: vi.fn() } }));
vi.mock("./validationApi", () => ({
  validationApi: { example: vi.fn() },
  downloadResult: vi.fn(),
}));

const readyHealth = {
  status: "ok" as const,
  model: {
    ready: true,
    name: "YOLOX-S · INT8",
    path: "models/yolox.onnx",
    input_size: 640,
  },
};
const running: Session = {
  ...initialSession,
  state: "running",
  session_id: "test-session",
  source_type: "video",
  source_label: "controlled.mp4",
  frame_index: 12,
  width: 1280,
  height: 720,
  reported_fps: null,
  capture_fps: 24.8,
  processing_fps: 7.2,
  inference_ms: 123.4,
  latency_ms: 130.5,
  timestamp_s: 1.2,
  timing_source: "video presentation timestamp",
  counts: { car: 1, truck: 0, bus: 0, motorcycle: 0 },
  total_tracks: 1,
  tracks: [
    {
      id: 4,
      category: "car",
      bbox: [10, 20, 40, 50],
      confidence: 0.87,
      state: "confirmed",
      hits: 5,
      missed: 0,
      history: [[25, 50]],
    },
  ],
};

beforeEach(() => {
  vi.resetAllMocks();
  vi.mocked(api.health).mockResolvedValue(readyHealth);
  vi.mocked(api.session).mockResolvedValue(initialSession);
  vi.mocked(api.cameras).mockResolvedValue({ cameras: [] });
  vi.mocked(api.calibrations).mockResolvedValue({ profiles: [] });
  vi.mocked(fieldApi.list).mockResolvedValue({ sessions: [] });
  vi.mocked(fieldApi.sources).mockResolvedValue({ sources: [] });
  vi.mocked(cameraApi.profiles).mockResolvedValue({ profiles: [] });
  vi.mocked(validationApi.example).mockResolvedValue({
    name: "Navigation example",
    provenance: "synthetic",
    description: "Synthetic navigation fixture.",
    records: [],
  });
  vi.mocked(api.start).mockImplementation(async () => {
    vi.mocked(api.session).mockResolvedValue(running);
    return running;
  });
  vi.mocked(api.control).mockImplementation(async (action) => {
    const next: Session =
      action === "reset"
        ? initialSession
        : {
            ...running,
            state:
              action === "pause"
                ? "paused"
                : action === "resume"
                  ? "running"
                  : "stopped",
          };
    vi.mocked(api.session).mockResolvedValue(next);
    return next;
  });
});

async function renderReady() {
  const user = userEvent.setup();
  render(<App />);
  await screen.findByText("Backend connected");
  await waitFor(() =>
    expect(
      screen.getByRole("button", { name: /Start observation/ }),
    ).toBeEnabled(),
  );
  return user;
}

describe("observation workspace", () => {
  it("loads field sessions only when opened and retains a draft across navigation", async () => {
    const user = await renderReady();
    expect(fieldApi.list).not.toHaveBeenCalled();
    await user.click(screen.getByRole("button", { name: "Field sessions" }));
    await waitFor(() =>
      expect(
        screen.getByRole("button", { name: "New field session" }),
      ).toBeEnabled(),
    );
    fireEvent.change(screen.getByLabelText("Session name"), {
      target: { value: "Retained collection draft" },
    });
    await user.click(screen.getByRole("button", { name: "Dashboard" }));
    await user.click(screen.getByRole("button", { name: "Field sessions" }));
    expect(screen.getByLabelText("Session name")).toHaveValue(
      "Retained collection draft",
    );
    expect(fieldApi.list).toHaveBeenCalledTimes(1);
    await user.click(
      screen.getByRole("button", { name: "Real-world validation" }),
    );
    expect(
      screen.getByRole("tab", { name: "Evaluation & reports" }),
    ).toHaveAttribute("aria-selected", "true");
    expect(
      screen.getByRole("heading", { name: "Real-world validation" }),
    ).toBeVisible();
  });
  it("loads validation only when opened and retains its dataset across navigation", async () => {
    const user = await renderReady();
    expect(validationApi.example).not.toHaveBeenCalled();
    await user.click(
      screen.getByRole("button", { name: "Validation & benchmarks" }),
    );
    expect(await screen.findByText("SYNTHETIC DATASET")).toBeInTheDocument();
    expect(
      screen.getByRole("heading", { name: "Validation & benchmarks" }),
    ).toBeInTheDocument();
    await user.click(screen.getByRole("button", { name: "Dashboard" }));
    expect(screen.getByText("No tracks to inspect yet")).toBeVisible();
    await user.click(
      screen.getByRole("button", { name: "Validation & benchmarks" }),
    );
    expect(screen.getByText("SYNTHETIC DATASET")).toBeVisible();
    expect(validationApi.example).toHaveBeenCalledTimes(1);
  });
  it("starts empty, requires calibration, and never invents observations or speed values", async () => {
    await renderReady();
    expect(
      screen.getByText("Calibration required", { selector: "strong" }),
    ).toBeInTheDocument();
    expect(screen.getByText("No tracks to inspect yet")).toBeInTheDocument();
    expect(screen.queryByText(/\d+\s*km\/h/)).not.toBeInTheDocument();
    expect(api.cameras).not.toHaveBeenCalled();
    expect(screen.getByRole("button", { name: "Stop" })).toBeDisabled();
  });

  it("requires a successful upload, retains its selection across methodology navigation, and starts that video", async () => {
    const user = await renderReady();
    vi.mocked(api.upload).mockResolvedValue({
      video_id: "local-video",
      name: "controlled.mp4",
    });
    await user.click(screen.getByRole("button", { name: "Video file" }));
    expect(
      screen.getByRole("button", { name: /Start observation/ }),
    ).toBeDisabled();
    const file = new File(["recorded fixture"], "controlled.mp4", {
      type: "video/mp4",
    });
    await user.upload(screen.getByLabelText("Choose video file"), file);
    expect(await screen.findByText("controlled.mp4")).toBeInTheDocument();
    expect(api.upload).toHaveBeenCalledWith(file);
    await user.click(screen.getByRole("button", { name: "Methodology" }));
    expect(
      screen.getByRole("heading", { name: "Built to be measured." }),
    ).toBeInTheDocument();
    await user.click(screen.getByRole("button", { name: "Dashboard" }));
    await user.click(screen.getByRole("button", { name: /Start observation/ }));
    await waitFor(() =>
      expect(api.start).toHaveBeenCalledWith({
        source_type: "video",
        video_id: "local-video",
        camera_index: 0,
        confidence: 0.35,
        input_size: 640,
        width: 1280,
        height: 720,
      }),
    );
    expect(await screen.findByText("24.8")).toBeInTheDocument();
  });

  it("reports a camera discovery failure and permits an explicit camera index", async () => {
    const user = await renderReady();
    await user.click(screen.getByRole("button", { name: /Scan cameras/ }));
    expect(await screen.findByText(/No camera found/)).toBeInTheDocument();
    const index = screen.getByRole("spinbutton", {
      name: "Camera device index",
    });
    await user.clear(index);
    await user.type(index, "2");
    await user.selectOptions(
      screen.getByLabelText("Requested capture resolution"),
      "640x480",
    );
    await user.selectOptions(screen.getByLabelText("Inference input"), "416");
    await user.click(screen.getByRole("button", { name: /Start observation/ }));
    await waitFor(() =>
      expect(api.start).toHaveBeenCalledWith(
        expect.objectContaining({
          source_type: "camera",
          camera_index: 2,
          width: 640,
          height: 480,
          input_size: 416,
        }),
      ),
    );
  });

  it("shows backend diagnostics, prediction confidence, and unavailable timing without coercing null to zero", async () => {
    vi.mocked(api.session).mockResolvedValue(running);
    render(<App />);
    expect(await screen.findByText("24.8")).toBeInTheDocument();
    expect(screen.getByText("7.2")).toBeInTheDocument();
    expect(screen.getByText("130.5")).toBeInTheDocument();
    const row = screen.getByText("Reported frame rate").closest("div")!;
    expect(within(row).getByText("—")).toBeInTheDocument();
    const tracks = screen.getByRole("table");
    expect(within(tracks).getByText("#004")).toBeInTheDocument();
    expect(within(tracks).getByText("87%")).toBeInTheDocument();
    expect(within(tracks).getByText("confirmed")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Live camera" })).toBeDisabled();
  });

  it("pauses, resumes, stops, and resets a running session through the API", async () => {
    vi.mocked(api.session).mockResolvedValue(running);
    const user = userEvent.setup();
    render(<App />);
    await screen.findByText("Backend connected");
    await user.click(screen.getByRole("button", { name: "Pause" }));
    await user.click(await screen.findByRole("button", { name: "Resume" }));
    await screen.findByRole("button", { name: "Pause" });
    await user.click(screen.getByRole("button", { name: "Stop" }));
    await waitFor(() =>
      expect(screen.getByRole("button", { name: "Stop" })).toBeDisabled(),
    );
    await user.click(screen.getByRole("button", { name: "Reset session" }));
    await screen.findByText("No tracks to inspect yet");
    expect(vi.mocked(api.control).mock.calls.map(([action]) => action)).toEqual(
      ["pause", "resume", "stop", "reset"],
    );
  });

  it("surfaces a start error and leaves the source editable for a retry", async () => {
    const user = await renderReady();
    vi.mocked(api.start).mockRejectedValue(
      new Error(
        "Camera 0 could not be opened. Check Windows camera permissions.",
      ),
    );
    await user.click(screen.getByRole("button", { name: /Start observation/ }));
    expect(await screen.findByRole("alert")).toHaveTextContent(
      "Camera 0 could not be opened",
    );
    expect(
      screen.getByRole("button", { name: /Start observation/ }),
    ).toBeEnabled();
    expect(
      screen.getByRole("spinbutton", { name: "Camera device index" }),
    ).toBeEnabled();
  });

  it("blocks start and explains an unavailable backend or missing model", async () => {
    vi.mocked(api.session).mockRejectedValue(new Error("offline"));
    vi.mocked(api.health).mockRejectedValue(new Error("offline"));
    render(<App />);
    expect(await screen.findByRole("alert")).toHaveTextContent(
      "Start the API on 127.0.0.1:8000",
    );
    expect(
      screen.getByRole("button", { name: /Start observation/ }),
    ).toBeDisabled();
  });

  it("keeps start disabled until the detector weights are available", async () => {
    vi.mocked(api.health).mockResolvedValue({
      ...readyHealth,
      model: { ...readyHealth.model, ready: false },
    });
    render(<App />);
    expect(
      await screen.findByText("Detector weights are not available."),
    ).toBeInTheDocument();
    expect(
      screen.getByRole("button", { name: /Start observation/ }),
    ).toBeDisabled();
  });

  it("shows an upload failure without offering to analyze the failed file", async () => {
    const user = await renderReady();
    vi.mocked(api.upload).mockRejectedValue(
      new Error("The selected video contains no decodable frames."),
    );
    await user.click(screen.getByRole("button", { name: "Video file" }));
    await user.upload(
      screen.getByLabelText("Choose video file"),
      new File(["bad"], "corrupt.mp4", { type: "video/mp4" }),
    );
    expect(await screen.findByRole("alert")).toHaveTextContent(
      "no decodable frames",
    );
    expect(
      screen.getByRole("button", { name: /Start observation/ }),
    ).toBeDisabled();
  });
});
