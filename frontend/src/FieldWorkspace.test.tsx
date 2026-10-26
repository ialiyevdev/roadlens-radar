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
import FieldWorkspace from "./FieldWorkspace";
import FieldAlignment from "./FieldAlignment";
import FieldEvaluation, { FieldEvaluationResults } from "./FieldEvaluation";
import { emptyFieldSession } from "./FieldMetadata";
import { fieldApi } from "./fieldApi";
import { api } from "./api";
import { cameraApi } from "./cameraApi";
import { downloadResult } from "./validationApi";
import { initialSession } from "./useSession";
import type { FieldEvaluation as Evaluation, FieldSession } from "./fieldTypes";
import type { SpeedMeasurement } from "./types";
import type { MetricSummary } from "./validationTypes";

vi.mock("./fieldApi", () => ({
  fieldApi: {
    list: vi.fn(),
    sources: vi.fn(),
    get: vi.fn(),
    create: vi.fn(),
    update: vi.fn(),
    delete: vi.fn(),
    example: vi.fn(),
    fromObservation: vi.fn(),
    importSession: vi.fn(),
    exportSession: vi.fn(),
    eligibility: vi.fn(),
    annotationMetrics: vi.fn(),
    importReferences: vi.fn(),
    sync: vi.fn(),
    matches: vi.fn(),
    evaluate: vi.fn(),
    exportEvaluation: vi.fn(),
  },
}));
vi.mock("./api", () => ({ api: { calibrations: vi.fn(), upload: vi.fn() } }));
vi.mock("./cameraApi", () => ({ cameraApi: { profiles: vi.fn() } }));
vi.mock("./CameraIntrinsics", () => ({
  CameraIntrinsics: () => <div>Camera intrinsic controls</div>,
}));
vi.mock("./AnnotationStudio", () => ({
  default: ({
    fieldSessionId,
    onSaved,
  }: {
    fieldSessionId: string;
    onSaved?: () => void;
  }) => (
    <div>
      Annotation selection: {fieldSessionId}
      <button onClick={onSaved}>Complete annotation save</button>
    </div>
  ),
}));
vi.mock("./validationApi", () => ({ downloadResult: vi.fn() }));

const measurement: SpeedMeasurement = {
  id: "measurement-1",
  track_id: 4,
  source_id: "video:fixture",
  session_id: "observation-1",
  calibration_id: null,
  category: "car",
  gate_a_timestamp_s: 10,
  gate_b_timestamp_s: 12,
  start_position: [0, 0],
  end_position: [20, 0],
  distance_m: 20,
  elapsed_seconds: 2,
  estimated_speed_kmh: 36,
  direction: "A_to_B",
  status: "valid",
  independently_validated: false,
  reasons: [],
  sample_count: 8,
  timestamp_s: 12,
};
function field(): FieldSession {
  return {
    ...emptyFieldSession(),
    id: "field-1",
    name: "Window observation",
    source: { ...emptyFieldSession().source, source_id: "video:fixture" },
    created_at: "2026-10-24T12:00:00Z",
    updated_at: "2026-10-24T12:00:00Z",
    provenance: "synthetic",
    partition: "held_out",
    measurements: [{ event_id: "vehicle-1", variant: "original", measurement }],
    reference_events: [
      {
        id: "reference-1",
        timestamp_s: 12,
        interval_end_s: null,
        speed: 35,
        units: "km/h",
        method: "Synthetic independent reference",
        provenance: "synthetic",
        independent: true,
        instrument_id: null,
        uncertainty_kmh: null,
        quality_notes: "Generated software fixture",
      },
    ],
    sync_diagnostics: {
      status: "uncertain",
      offset_s: 0,
      scale: 1,
      drift_ppm: 0,
      anchor_count: 0,
      anchor_span_s: 0,
      residuals_s: [],
      maximum_residual_s: null,
      uncertainty_bound_s: null,
      warnings: ["Manual offset is uncertain."],
    },
  };
}
const summary: MetricSummary = {
  n: 3,
  sufficient_sample: true,
  mae_kmh: 1,
  rmse_kmh: 1,
  bias_kmh: 1,
  median_absolute_error_kmh: 1,
  p90_absolute_error_kmh: 1,
  mape_percent: 2,
  percentage_sample_count: 3,
  tolerance_bands: [],
};
function report(): Evaluation {
  const rows = [0, 1, 2].map((i) => ({
    record: {
      recording_id: "field-1",
      observation_id: `vehicle-${i}`,
      measurement_id: `measurement-${i}`,
      status: (i === 1 ? "approximate" : "valid") as "valid" | "approximate",
      estimated_speed_kmh: 36 + i,
      reference_speed_kmh: 35 + i,
      direction: (i === 2 ? "B_to_A" : "A_to_B") as "A_to_B" | "B_to_A",
    },
    reference_matched: true,
    comparison_included: true,
    error_kmh: 1,
    absolute_error_kmh: 1,
    absolute_percentage_error_percent: 100 / (35 + i),
    exclusion_reasons: [],
  }));
  return {
    provenance: "synthetic",
    partition: "held_out",
    variant: "original",
    real_world_reference_available: false,
    session_count: 1,
    sessions: [
      { id: "field-1", name: "Window observation", partition: "held_out" },
    ],
    validation: {
      dataset_name: "Field evaluation",
      provenance: "synthetic",
      description: "Generated fixtures",
      evaluation_version: "1",
      total_records: 3,
      reference_matched_count: 3,
      compared_count: 3,
      rejected_count: 0,
      completed_count: 3,
      rejection_rate_percent: 0,
      completion_rate_percent: 100,
      summary,
      groups: [],
      rows,
      options: { tolerance_bands_kmh: [3, 5], minimum_group_samples: 3 },
      limitations: [],
    },
    groups: [{ dimension: "session_id", value: "field-1", metrics: summary }],
    group_sample_counts: [{ dimension: "session_id", value: "field-1", n: 3 }],
    row_metadata: rows.map((row) => ({
      session_id: "field-1",
      session_name: "Window observation",
      event_id: row.record.observation_id,
      variant: "original",
      partition: "held_out",
      camera_configuration: "window",
      calibration: "none",
      direction: row.record.direction,
      environment: "dry",
      tracker: "global_motion",
      status: row.record.status,
      original_reasons: [],
      measurement_diagnostics: { maximum_observation_gap_s: 0.1 },
    })),
    counts: {
      vehicle_events: 3,
      denominator: 3,
      complete_event_ledger: false,
      valid: 2,
      rejected: 0,
      completed: 3,
      noncompleted: 0,
      missing_application_events: null,
      missing_reference: 0,
      unmatched_reference_events: 0,
      excluded_measurements: 0,
      valid_measurement_percent: 200 / 3,
      rejection_percent: 0,
      noncompletion_percent: 0,
    },
    exclusions: {},
    timing: [],
    tracking: [],
    pipeline_comparison: {
      paired_n: 0,
      pairs: [],
      baseline: { ...summary, n: 0, sufficient_sample: false, mae_kmh: null },
      improved: { ...summary, n: 0, sufficient_sample: false, mae_kmh: null },
      note: "Only explicit saved variants are compared.",
    },
    performance: { evaluation_ms: 0.5 },
    limitations: ["Synthetic evidence only."],
  };
}
beforeEach(() => {
  vi.resetAllMocks();
  vi.mocked(fieldApi.list).mockResolvedValue({ sessions: [] });
  vi.mocked(fieldApi.sources).mockResolvedValue({ sources: [] });
  vi.mocked(api.calibrations).mockResolvedValue({ profiles: [] });
  vi.mocked(cameraApi.profiles).mockResolvedValue({ profiles: [] });
  vi.mocked(fieldApi.eligibility).mockResolvedValue({
    matched_event_count: 0,
    eligible_event_count: 0,
    real_world_reference_available: false,
  });
  vi.mocked(fieldApi.annotationMetrics).mockResolvedValue({
    annotated_vehicles: 2,
  });
  vi.mocked(fieldApi.create).mockImplementation(async (input) => ({
    ...field(),
    ...input,
  }));
  vi.mocked(fieldApi.update).mockImplementation(async (_, input) => ({
    ...field(),
    ...input,
  }));
  vi.mocked(fieldApi.exportSession).mockResolvedValue(new Blob(["session"]));
  vi.mocked(fieldApi.exportEvaluation).mockResolvedValue(new Blob(["report"]));
  vi.mocked(fieldApi.evaluate).mockResolvedValue(report());
});
async function workspace(existing = false) {
  if (existing)
    vi.mocked(fieldApi.list).mockResolvedValue({ sessions: [field()] });
  const user = userEvent.setup();
  render(
    <FieldWorkspace
      session={initialSession}
      connected
      perform={async () => {}}
    />,
  );
  await waitFor(() =>
    expect(
      screen.getByRole("button", { name: "New field session" }),
    ).toBeEnabled(),
  );
  return user;
}

describe("field session workspace", () => {
  it("creates local metadata without inventing independent evidence", async () => {
    const user = await workspace();
    expect(
      screen.getByText("No real-world reference data available"),
    ).toBeVisible();
    expect(
      screen.getByRole("button", { name: "Save new field session" }),
    ).toBeDisabled();
    fireEvent.change(screen.getByLabelText("Session name"), {
      target: { value: "Third-floor daylight" },
    });
    await user.selectOptions(
      screen.getByLabelText("Dataset partition"),
      "held_out",
    );
    await user.click(
      screen.getByRole("button", { name: "Save new field session" }),
    );
    expect(
      await screen.findByText("Field session saved locally."),
    ).toBeVisible();
    expect(fieldApi.create).toHaveBeenCalledWith(
      expect.objectContaining({
        name: "Third-floor daylight",
        partition: "held_out",
        provenance: "recorded_unverified",
      }),
    );
    expect(
      screen.getByText("No real-world reference data available"),
    ).toBeVisible();
  });
  it("loads synthetic examples as unsaved drafts and keeps their provenance explicit", async () => {
    const { id, created_at, updated_at, sync_diagnostics, ...example } =
      field();
    void id;
    void created_at;
    void updated_at;
    void sync_diagnostics;
    vi.mocked(fieldApi.example).mockResolvedValue(example);
    const user = await workspace();
    await user.click(
      screen.getByRole("button", { name: "Load synthetic field example" }),
    );
    expect(
      await screen.findByText("Synthetic example loaded as an unsaved draft."),
    ).toBeVisible();
    expect(screen.getByLabelText("Evidence provenance")).toHaveValue(
      "synthetic",
    );
    expect(fieldApi.create).not.toHaveBeenCalled();
    await user.click(
      screen.getByRole("button", { name: "Save new field session" }),
    );
    expect(
      await screen.findByText(/The selected session is synthetic/),
    ).toBeVisible();
  });
  it("links an uploaded video once and retains relative source metadata", async () => {
    vi.mocked(api.upload).mockResolvedValue({
      video_id: "uploaded",
      name: "road.avi",
    });
    const user = await workspace();
    vi.mocked(fieldApi.sources).mockResolvedValue({
      sources: [
        {
          video_id: "uploaded",
          source_id: `video:${"a".repeat(64)}`,
          relative_path: "uploads/road.avi",
          name: "road.avi",
          width: 800,
          height: 600,
          reported_fps: 25,
          time_base: "1/25",
        },
      ],
    });
    await user.upload(
      screen.getByLabelText("Attach field video"),
      new File(["fixture"], "road.avi", { type: "video/avi" }),
    );
    expect(await screen.findByText(/Video registered once/)).toBeVisible();
    expect(screen.getByLabelText("Relative source path")).toHaveValue(
      "uploads/road.avi",
    );
    expect(screen.getByLabelText("Image width · pixels")).toHaveValue(800);
    expect(api.upload).toHaveBeenCalledTimes(1);
  });
  it("associates a compatible road-plane profile and retains its original diagnostics", async () => {
    const calibration = {
      id: "road-profile",
      name: "Measured road",
      source_id: "video:fixture",
      geometry: emptyFieldSession().camera.geometry,
      points: [],
      check_points: [],
      gates: {
        gate_a: [
          [100, 100],
          [100, 300],
        ] as [[number, number], [number, number]],
        gate_b: [
          [300, 100],
          [300, 300],
        ] as [[number, number], [number, number]],
        allow_reverse: false,
      },
      diagnostics: {
        valid: true,
        errors: [],
        warnings: [],
        homography: null,
        region_image: [],
        grid_image: [],
        inliers: [],
        coverage: 0.6,
        fit_error_m: 0.01,
        fit_error_px: 0.1,
        check_error_m: 0.02,
        condition_number: 10,
      },
    };
    vi.mocked(api.calibrations).mockResolvedValue({ profiles: [calibration] });
    const user = await workspace(true);
    await user.selectOptions(
      screen.getByLabelText("Road-plane calibration profile"),
      "road-profile",
    );
    expect(
      screen.getByText(/Independent check-point error: 0.020 m/),
    ).toBeVisible();
    await user.click(
      screen.getByRole("button", { name: "Save field session changes" }),
    );
    await waitFor(() =>
      expect(fieldApi.update).toHaveBeenCalledWith(
        "field-1",
        expect.objectContaining({
          calibration_id: "road-profile",
          gates: calibration.gates,
          calibration_metadata: { road_plane: calibration },
          measurements: field().measurements,
        }),
      ),
    );
  });
  it("exports and deletes the selected local record with an explicit deletion action", async () => {
    const user = await workspace(true);
    await user.click(
      screen.getByRole("button", { name: "Export field session JSON" }),
    );
    await waitFor(() =>
      expect(downloadResult).toHaveBeenCalledWith(
        expect.any(Blob),
        "roadlens-field-field-1.json",
      ),
    );
    await user.click(
      screen.getByRole("button", { name: "Delete field session" }),
    );
    expect(fieldApi.delete).not.toHaveBeenCalled();
    await user.click(
      screen.getByRole("button", { name: "Confirm field session deletion" }),
    );
    expect(await screen.findByText("Field session deleted.")).toBeVisible();
    expect(fieldApi.delete).toHaveBeenCalledWith("field-1");
  });
  it("passes selected session identity into annotation controls and opens camera controls on demand", async () => {
    const user = await workspace(true);
    expect(
      screen.queryByText("Camera intrinsic controls"),
    ).not.toBeInTheDocument();
    await user.click(screen.getByRole("tab", { name: "Vehicle annotations" }));
    expect(screen.getByText("Annotation selection: field-1")).toBeVisible();
    await user.click(screen.getByRole("tab", { name: "Camera intrinsics" }));
    expect(screen.getByText("Camera intrinsic controls")).toBeVisible();
    expect(
      screen.getByText("Annotated vehicles").nextElementSibling,
    ).toHaveTextContent("2");
  });
  it("retains a new unsaved draft when an earlier annotation refresh finishes", async () => {
    let finish!: (value: FieldSession) => void;
    vi.mocked(fieldApi.get).mockImplementation(
      () =>
        new Promise((resolve) => {
          finish = resolve;
        }),
    );
    const user = await workspace(true);
    await user.click(screen.getByRole("tab", { name: "Vehicle annotations" }));
    await user.click(
      screen.getByRole("button", { name: "Complete annotation save" }),
    );
    expect(fieldApi.get).toHaveBeenCalledWith("field-1");
    await user.click(screen.getByRole("button", { name: "New field session" }));
    fireEvent.change(screen.getByLabelText("Session name"), {
      target: { value: "New collection draft" },
    });
    await act(async () =>
      finish({ ...field(), name: "Refreshed old observation" }),
    );
    expect(screen.getByLabelText("Selected field session")).toHaveValue("");
    expect(screen.getByLabelText("Session name")).toHaveValue(
      "New collection draft",
    );
    expect(
      screen.getByRole("button", { name: "Save new field session" }),
    ).toBeEnabled();
    expect(
      screen.getByRole("option", { name: /Refreshed old observation/ }),
    ).toBeInTheDocument();
  });
  it("keeps unsaved metadata for the same session after an annotation refresh", async () => {
    let finish!: (value: FieldSession) => void;
    vi.mocked(fieldApi.get).mockImplementation(
      () =>
        new Promise((resolve) => {
          finish = resolve;
        }),
    );
    const user = await workspace(true);
    await user.click(screen.getByRole("tab", { name: "Vehicle annotations" }));
    await user.click(
      screen.getByRole("button", { name: "Complete annotation save" }),
    );
    await user.click(screen.getByRole("tab", { name: "Session details" }));
    fireEvent.change(screen.getByLabelText("Session name"), {
      target: { value: "Unsaved camera notes" },
    });
    await act(async () =>
      finish({ ...field(), name: "Previously saved observation" }),
    );
    expect(screen.getByLabelText("Selected field session")).toHaveValue(
      "field-1",
    );
    expect(screen.getByLabelText("Session name")).toHaveValue(
      "Unsaved camera notes",
    );
    expect(screen.getByText("Unsaved changes")).toBeVisible();
  });
  it("updates an earlier alignment result without switching away from another draft", async () => {
    let finish!: (value: FieldSession) => void;
    vi.mocked(fieldApi.matches).mockImplementation(
      () =>
        new Promise((resolve) => {
          finish = resolve;
        }),
    );
    const second = { ...field(), id: "field-2", name: "Second observation" };
    vi.mocked(fieldApi.list).mockResolvedValue({ sessions: [field(), second] });
    const user = await workspace();
    await user.click(screen.getByRole("tab", { name: "Reference alignment" }));
    await user.click(
      screen.getByRole("button", { name: "Save matching decisions" }),
    );
    expect(fieldApi.matches).toHaveBeenCalledWith("field-1", []);
    await user.selectOptions(
      screen.getByLabelText("Selected field session"),
      "field-2",
    );
    await user.click(screen.getByRole("tab", { name: "Session details" }));
    fireEvent.change(screen.getByLabelText("Session name"), {
      target: { value: "Second unsaved draft" },
    });
    await act(async () =>
      finish({ ...field(), name: "Aligned first observation" }),
    );
    expect(screen.getByLabelText("Selected field session")).toHaveValue(
      "field-2",
    );
    expect(screen.getByLabelText("Session name")).toHaveValue(
      "Second unsaved draft",
    );
    expect(
      screen.getByRole("option", { name: /Aligned first observation/ }),
    ).toBeInTheDocument();
  });
  it("preserves metadata after a save failure and exposes the server reason", async () => {
    vi.mocked(fieldApi.update).mockRejectedValue(
      new Error("Near-duplicate collection crosses dataset partitions."),
    );
    const user = await workspace(true);
    fireEvent.change(screen.getByLabelText("Session name"), {
      target: { value: "Edited observation" },
    });
    await user.click(
      screen.getByRole("button", { name: "Save field session changes" }),
    );
    expect(await screen.findByRole("alert")).toHaveTextContent(
      "Near-duplicate collection crosses dataset partitions.",
    );
    expect(screen.getByLabelText("Session name")).toHaveValue(
      "Edited observation",
    );
  });
});
describe("independent reference alignment", () => {
  it("imports a reference ledger and retains ambiguous matching decisions explicitly", async () => {
    const user = userEvent.setup(),
      onSaved = vi.fn();
    vi.mocked(fieldApi.importReferences).mockResolvedValue(field());
    vi.mocked(fieldApi.matches).mockResolvedValue(field());
    render(<FieldAlignment field={field()} connected onSaved={onSaved} />);
    const file = new File(["reference fixture"], "reference.csv", {
      type: "text/csv",
    });
    await user.upload(
      screen.getByLabelText("Import independent reference measurements"),
      file,
    );
    await waitFor(() =>
      expect(fieldApi.importReferences).toHaveBeenCalledWith("field-1", file),
    );
    expect(fieldApi.matches).not.toHaveBeenCalled();
    await user.selectOptions(
      screen.getByLabelText("Reference for vehicle-1"),
      "reference-1",
    );
    await user.selectOptions(
      screen.getByLabelText("Association for vehicle-1"),
      "ambiguous",
    );
    fireEvent.change(screen.getByLabelText("Matching evidence for vehicle-1"), {
      target: { value: "Two vehicles overlap" },
    });
    await user.click(
      screen.getByRole("button", { name: "Save matching decisions" }),
    );
    await waitFor(() =>
      expect(fieldApi.matches).toHaveBeenCalledWith("field-1", [
        expect.objectContaining({
          event_id: "vehicle-1",
          reference_id: "reference-1",
          association: "ambiguous",
          correspondence_confirmed: false,
          method: "Two vehicles overlap",
        }),
      ]),
    );
  });
  it("saves independent synchronization anchors and does not call manual offsets precise", async () => {
    const user = userEvent.setup();
    vi.mocked(fieldApi.sync).mockResolvedValue(field());
    render(<FieldAlignment field={field()} connected onSaved={vi.fn()} />);
    fireEvent.change(screen.getByLabelText("Manual source offset · seconds"), {
      target: { value: "2" },
    });
    fireEvent.change(screen.getByLabelText("Anchor reference time · s"), {
      target: { value: "10" },
    });
    fireEvent.change(screen.getByLabelText("Anchor source time · s"), {
      target: { value: "12" },
    });
    fireEvent.change(screen.getByLabelText("Anchor uncertainty · s"), {
      target: { value: "0.02" },
    });
    await user.click(screen.getByLabelText("Independent clock evidence"));
    await user.click(
      screen.getByRole("button", { name: "Add synchronization anchor" }),
    );
    await user.click(
      screen.getByRole("button", { name: "Save synchronization" }),
    );
    await waitFor(() =>
      expect(fieldApi.sync).toHaveBeenCalledWith(
        "field-1",
        expect.objectContaining({
          offset_s: 2,
          anchors: [
            expect.objectContaining({
              reference_timestamp_s: 10,
              source_timestamp_s: 12,
              uncertainty_s: 0.02,
              independent: true,
            }),
          ],
        }),
      ),
    );
    expect(screen.getByText("Manual offset is uncertain.")).toBeVisible();
    expect(
      screen.getByRole("img", {
        name: /Recorded measurements and aligned reference/,
      }),
    ).toBeVisible();
  });
  it("surfaces malformed reference errors without discarding existing events", async () => {
    const user = userEvent.setup();
    vi.mocked(fieldApi.importReferences).mockRejectedValue(
      new Error("Reference identifiers must be unique."),
    );
    render(<FieldAlignment field={field()} connected onSaved={vi.fn()} />);
    await user.upload(
      screen.getByLabelText("Import independent reference measurements"),
      new File(["bad"], "bad.csv", { type: "text/csv" }),
    );
    expect(await screen.findByRole("alert")).toHaveTextContent(
      "Reference identifiers must be unique.",
    );
    expect(
      within(
        screen.getByRole("table", { name: "Imported reference events" }),
      ).getByText("reference-1"),
    ).toBeVisible();
  });
});
describe("held-out evaluation presentation", () => {
  it("evaluates explicit session partitions, filters chart details, and exports HTML", async () => {
    const user = userEvent.setup();
    render(<FieldEvaluation sessions={[field()]} connected />);
    expect(
      screen.getByRole("button", { name: "Export field report HTML" }),
    ).toBeDisabled();
    await user.click(
      screen.getByRole("checkbox", { name: /Window observation/ }),
    );
    await user.click(
      screen.getByRole("button", { name: "Evaluate field sessions" }),
    );
    expect(
      await screen.findByRole("table", {
        name: "Field validation measurements",
      }),
    ).toBeVisible();
    expect(fieldApi.evaluate).toHaveBeenCalledWith(
      expect.objectContaining({
        session_ids: ["field-1"],
        partition: "held_out",
        variant: "original",
      }),
    );
    expect(
      screen.getByText("No real-world reference data available"),
    ).toBeVisible();
    expect(
      screen.getByRole("img", { name: "Signed speed error distribution" }),
    ).toBeVisible();
    await user.selectOptions(
      screen.getByLabelText("Measurement status"),
      "approximate",
    );
    expect(
      within(
        screen.getByRole("table", { name: "Field validation measurements" }),
      ).getAllByRole("row"),
    ).toHaveLength(2);
    await user.selectOptions(
      screen.getByLabelText("Travel direction"),
      "B_to_A",
    );
    expect(
      screen.getByText("No measurements match the current filters."),
    ).toBeVisible();
    await user.click(
      screen.getByRole("button", { name: "Export field report HTML" }),
    );
    await waitFor(() =>
      expect(fieldApi.exportEvaluation).toHaveBeenCalledWith(
        expect.objectContaining({ partition: "held_out" }),
        "html",
      ),
    );
    expect(downloadResult).toHaveBeenCalledWith(
      expect.any(Blob),
      "roadlens-field-validation.html",
    );
  });
  it("withholds aggregate errors for insufficient samples while retaining counts", () => {
    const value = report();
    value.validation.summary = {
      ...summary,
      n: 1,
      sufficient_sample: false,
      mae_kmh: null,
      rmse_kmh: null,
      bias_kmh: null,
      median_absolute_error_kmh: null,
      p90_absolute_error_kmh: null,
    };
    render(<FieldEvaluationResults report={value} />);
    expect(
      screen.getByText(
        /Insufficient comparisons for aggregate error statistics/,
      ),
    ).toBeVisible();
    expect(
      screen.getByText("Mean absolute error").parentElement,
    ).toHaveTextContent("—");
    expect(screen.queryByText(/No complete/)).not.toBeInTheDocument();
  });
  it("provides actionable empty and evaluation error states", async () => {
    const user = userEvent.setup();
    vi.mocked(fieldApi.evaluate).mockRejectedValue(
      new Error("Evaluate provenance groups separately."),
    );
    render(<FieldEvaluation sessions={[field()]} connected />);
    expect(screen.getByText("No field evaluation yet")).toBeVisible();
    await user.click(
      screen.getByRole("checkbox", { name: /Window observation/ }),
    );
    await user.click(
      screen.getByRole("button", { name: "Evaluate field sessions" }),
    );
    expect(await screen.findByRole("alert")).toHaveTextContent(
      "Evaluate provenance groups separately.",
    );
    expect(
      screen.getByRole("button", { name: "Export field report JSON" }),
    ).toBeDisabled();
  });
});
