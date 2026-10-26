import { beforeEach, describe, expect, it, vi } from "vitest";
import {
  fireEvent,
  render,
  screen,
  waitFor,
  within,
} from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import ValidationBenchmarks from "./ValidationBenchmarks";
import { formatMetric } from "./validationPresentation";
import { SpeedCharts, chartPairs } from "./ValidationCharts";
import { downloadResult, validationApi } from "./validationApi";
import type {
  MetricSummary,
  TrackingReport,
  TrackingScenario,
  ValidationDataset,
  ValidationRecord,
  ValidationReport,
  ValidationRow,
} from "./validationTypes";

vi.mock("./validationApi", () => ({
  validationApi: {
    example: vi.fn(),
    import: vi.fn(),
    evaluate: vi.fn(),
    export: vi.fn(),
    benchmark: vi.fn(),
    exportBenchmark: vi.fn(),
  },
  downloadResult: vi.fn(),
}));
const records: ValidationRecord[] = [40, 50, 60].map((speed, i) => ({
  recording_id: "synthetic-recording",
  observation_id: `event-${i}`,
  measurement_id: `measurement-${i}`,
  status: i === 1 ? "approximate" : "valid",
  estimated_speed_kmh: speed + [2, -2, 0][i],
  reference_speed_kmh: speed,
  reference_method: "Synthetic independent trajectory",
  reference_independent: true,
  association: "matched",
  reference_recording_id: "synthetic-recording",
  reference_observation_id: `event-${i}`,
  reference_measurement_id: `measurement-${i}`,
  diagnostics: { maximum_gap_s: 0.08 },
}));
const dataset: ValidationDataset = {
  name: "Synthetic example",
  provenance: "synthetic",
  description: "Generated test references only.",
  records,
};
const summary: MetricSummary = {
  n: 3,
  sufficient_sample: true,
  mae_kmh: 4 / 3,
  rmse_kmh: Math.sqrt(8 / 3),
  bias_kmh: 0,
  median_absolute_error_kmh: 2,
  p90_absolute_error_kmh: 2,
  mape_percent: 3,
  percentage_sample_count: 3,
  tolerance_bands: [
    { tolerance_kmh: 3, within_count: 3, within_percent: 100 },
    { tolerance_kmh: 5, within_count: 3, within_percent: 100 },
  ],
};
const included: ValidationRow[] = records.map((record, i) => ({
  record,
  reference_matched: true,
  comparison_included: true,
  error_kmh: [2, -2, 0][i],
  absolute_error_kmh: [2, 2, 0][i],
  absolute_percentage_error_percent: [5, 4, 0][i],
  exclusion_reasons: [],
}));
const report: ValidationReport = {
  dataset_name: dataset.name,
  provenance: "synthetic",
  description: dataset.description,
  evaluation_version: "1",
  total_records: 5,
  reference_matched_count: 4,
  compared_count: 3,
  rejected_count: 1,
  completed_count: 4,
  rejection_rate_percent: 20,
  completion_rate_percent: 80,
  summary,
  groups: [
    {
      id: "all_reference_matched",
      label: "All eligible reference pairs",
      metrics: summary,
    },
  ],
  rows: [
    ...included,
    {
      record: {
        ...records[0],
        measurement_id: "ambiguous-event",
        association: "ambiguous",
      },
      reference_matched: false,
      comparison_included: false,
      error_kmh: null,
      absolute_error_kmh: null,
      absolute_percentage_error_percent: null,
      exclusion_reasons: ["Ambiguous reference event"],
    },
    {
      record: {
        ...records[0],
        measurement_id: "rejected-event",
        status: "rejected",
        estimated_speed_kmh: null,
      },
      reference_matched: true,
      comparison_included: false,
      error_kmh: null,
      absolute_error_kmh: null,
      absolute_percentage_error_percent: null,
      exclusion_reasons: ["Rejected measurements are excluded"],
    },
  ],
  options: { tolerance_bands_kmh: [3, 5], minimum_group_samples: 3 },
  limitations: ["Synthetic results do not establish road accuracy."],
};
const scenario: TrackingScenario = {
  name: "crossing_paths",
  description: "Two synthetic paths cross.",
  frames: 3,
  ground_truth_observations: 6,
  matched_observations: 6,
  missed_observations: 0,
  id_switches: 1,
  fragments: 0,
  created_tracks: 2,
  confirmed_tracks: 2,
  potential_id_switches: 0,
  fragmentation_suspicions: 0,
  mean_update_ms: 0.1,
  p95_update_ms: 0.2,
  runtime_ms: 0.3,
  continuity: [0, 1, 2].map((timestamp_s) => ({
    timestamp_s,
    ground_truth_count: 2,
    observed_tracks: 2,
    active_tracks: 2,
    lost_tracks: 0,
  })),
};
const benchmark: TrackingReport = {
  schema_version: 1,
  provenance: "synthetic",
  generated_at_utc: "2026-10-23T12:00:00Z",
  hardware: { os: "Windows", cpu: "Test CPU", logical_cpus: 4, python: "3.13" },
  methodology: {
    matching: "Annotated synthetic identities",
    limitations: ["No inference included"],
  },
  baseline: { ...scenario, name: "Phase 2 baseline", scenarios: [scenario] },
  improved: {
    ...scenario,
    name: "Improved",
    id_switches: 0,
    potential_id_switches: 2,
    scenarios: [{ ...scenario, id_switches: 0 }],
  },
};

beforeEach(() => {
  vi.resetAllMocks();
  vi.mocked(validationApi.example).mockResolvedValue(dataset);
  vi.mocked(validationApi.evaluate).mockResolvedValue(report);
  vi.mocked(validationApi.benchmark).mockResolvedValue(benchmark);
  vi.mocked(validationApi.export).mockResolvedValue(new Blob(["test export"]));
  vi.mocked(validationApi.exportBenchmark).mockResolvedValue(
    new Blob(["benchmark export"]),
  );
});
async function ready() {
  const user = userEvent.setup();
  render(<ValidationBenchmarks connected />);
  await waitFor(() =>
    expect(
      screen.getByRole("button", { name: "Evaluate speed references" }),
    ).toBeEnabled(),
  );
  return user;
}
async function evaluated() {
  const user = await ready();
  await user.click(
    screen.getByRole("button", { name: "Evaluate speed references" }),
  );
  await screen.findByRole("table", { name: "Validation measurements" });
  return user;
}
describe("validation and benchmark workspace", () => {
  it("labels the synthetic example and starts without fabricated error statistics", async () => {
    await ready();
    expect(screen.getByText("SYNTHETIC DATASET")).toBeInTheDocument();
    expect(
      screen.getByText("Software validation, not measured road accuracy"),
    ).toBeInTheDocument();
    expect(screen.getByText("No speed evaluation yet")).toBeInTheDocument();
    expect(
      screen.getByRole("button", { name: "Export validation CSV" }),
    ).toBeDisabled();
    expect(validationApi.evaluate).not.toHaveBeenCalled();
  });
  it("evaluates explicit references and renders actual report counts, signed errors, and accessible charts", async () => {
    await evaluated();
    expect(validationApi.evaluate).toHaveBeenCalledWith(dataset, {
      tolerance_bands_kmh: [3, 5],
      minimum_group_samples: 3,
    });
    const inspection = screen.getByRole("table", {
      name: "Validation measurements",
    });
    expect(within(inspection).getByText("+2.00")).toBeInTheDocument();
    expect(within(inspection).getByText("-2.00")).toBeInTheDocument();
    expect(
      screen.getByRole("img", { name: /Estimated versus reference speed/ }),
    ).toBeInTheDocument();
    expect(
      screen.getByRole("img", { name: /Absolute error distribution/ }),
    ).toBeInTheDocument();
    expect(
      screen.getByRole("img", { name: /Signed error versus reference speed/ }),
    ).toBeInTheDocument();
    expect(screen.getByText("Ambiguous reference event")).toBeInTheDocument();
    expect(screen.getByText("20.00")).toBeInTheDocument();
    expect(
      screen.getByText("3 eligible speed comparisons"),
    ).toBeInTheDocument();
  });
  it("imports a dataset, changes provenance explicitly, and retains selectable datasets", async () => {
    const user = await ready();
    const imported: ValidationDataset = {
      ...dataset,
      name: "Independent field run",
      provenance: "real_world",
      description: "Reference precision documented separately.",
    };
    vi.mocked(validationApi.import).mockResolvedValue(imported);
    const file = new File(["recording_id,measurement_id"], "field-run.csv", {
      type: "text/csv",
    });
    await user.upload(screen.getByLabelText("Import validation dataset"), file);
    expect(validationApi.import).toHaveBeenCalledWith(file);
    expect(await screen.findByText("REAL-WORLD DATASET")).toBeInTheDocument();
    expect(
      screen.getByText("Reference quality must be established independently"),
    ).toBeInTheDocument();
    await user.selectOptions(screen.getByLabelText("Comparison dataset"), "0");
    expect(screen.getByText("SYNTHETIC DATASET")).toBeInTheDocument();
    expect(
      screen.getByRole("option", { name: /Independent field run/ }),
    ).toBeInTheDocument();
  });
  it("filters by quality, exclusion status, and measurement ID without changing report statistics", async () => {
    const user = await evaluated();
    const table = screen.getByRole("table", {
      name: "Validation measurements",
    });
    await user.selectOptions(
      screen.getByLabelText("Status filter"),
      "approximate",
    );
    expect(within(table).getByText("measurement-1")).toBeInTheDocument();
    expect(within(table).queryByText("measurement-0")).not.toBeInTheDocument();
    await user.selectOptions(
      screen.getByLabelText("Status filter"),
      "excluded",
    );
    expect(within(table).getByText("ambiguous-event")).toBeInTheDocument();
    expect(within(table).getByText("rejected-event")).toBeInTheDocument();
    await user.type(
      screen.getByLabelText("Search measurement or recording"),
      "no-such-event",
    );
    expect(
      screen.getByText("No measurements match these filters"),
    ).toBeInTheDocument();
    expect(
      screen.getByText("3 eligible speed comparisons"),
    ).toBeInTheDocument();
  });
  it("validates analysis settings and exports the evaluated dataset with the applied settings", async () => {
    const user = await ready();
    fireEvent.change(screen.getByLabelText("Tolerance band 1 · km/h"), {
      target: { value: "" },
    });
    expect(
      screen.getByRole("button", { name: "Evaluate speed references" }),
    ).toBeDisabled();
    fireEvent.change(screen.getByLabelText("Tolerance band 1 · km/h"), {
      target: { value: "1001" },
    });
    expect(
      screen.getByRole("button", { name: "Evaluate speed references" }),
    ).toBeDisabled();
    fireEvent.change(screen.getByLabelText("Tolerance band 1 · km/h"), {
      target: { value: "5.0" },
    });
    expect(
      screen.getByRole("button", { name: "Evaluate speed references" }),
    ).toBeDisabled();
    fireEvent.change(screen.getByLabelText("Tolerance band 1 · km/h"), {
      target: { value: "2" },
    });
    fireEvent.change(screen.getByLabelText("Minimum group samples"), {
      target: { value: "2" },
    });
    expect(
      screen.getByRole("button", { name: "Evaluate speed references" }),
    ).toBeDisabled();
    fireEvent.change(screen.getByLabelText("Minimum group samples"), {
      target: { value: "10001" },
    });
    expect(
      screen.getByRole("button", { name: "Evaluate speed references" }),
    ).toBeDisabled();
    fireEvent.change(screen.getByLabelText("Minimum group samples"), {
      target: { value: "4" },
    });
    const applied = {
      ...report,
      options: { tolerance_bands_kmh: [2, 5], minimum_group_samples: 4 },
    };
    vi.mocked(validationApi.evaluate).mockResolvedValue(applied);
    await user.click(
      screen.getByRole("button", { name: "Evaluate speed references" }),
    );
    await screen.findByRole("table", { name: "Validation measurements" });
    await user.click(
      screen.getByRole("button", { name: "Export validation CSV" }),
    );
    await waitFor(() =>
      expect(downloadResult).toHaveBeenCalledWith(
        expect.any(Blob),
        "roadlens-validation.csv",
      ),
    );
    expect(validationApi.export).toHaveBeenCalledWith(
      dataset,
      applied.options,
      "csv",
    );
    await user.click(
      screen.getByRole("button", { name: "Export validation JSON" }),
    );
    expect(validationApi.export).toHaveBeenLastCalledWith(
      dataset,
      applied.options,
      "json",
    );
  });
  it("retains original values and withholds aggregate metrics for an empty dataset", async () => {
    const empty: ValidationReport = {
      ...report,
      total_records: 0,
      completed_count: 0,
      compared_count: 0,
      reference_matched_count: 0,
      rejected_count: 0,
      completion_rate_percent: null,
      rejection_rate_percent: null,
      rows: [],
      groups: [],
      summary: {
        ...summary,
        n: 0,
        sufficient_sample: false,
        mae_kmh: null,
        rmse_kmh: null,
        bias_kmh: null,
      },
    };
    vi.mocked(validationApi.evaluate).mockResolvedValue(empty);
    const user = await ready();
    await user.click(
      screen.getByRole("button", { name: "Evaluate speed references" }),
    );
    expect(
      await screen.findByText("This dataset contains no measurements"),
    ).toBeInTheDocument();
    expect(screen.getByText(/Insufficient comparisons/)).toBeInTheDocument();
    expect(
      screen.getAllByText("No finite, included reference pairs to plot."),
    ).toHaveLength(3);
    expect(
      screen.queryByRole("img", { name: /Estimated versus reference speed/ }),
    ).not.toBeInTheDocument();
  });
  it("surfaces import, evaluation, and export errors without inventing a successful result", async () => {
    const user = await ready();
    vi.mocked(validationApi.import).mockRejectedValue(
      new Error("Duplicate reference event."),
    );
    await user.upload(
      screen.getByLabelText("Import validation dataset"),
      new File(["{}"], "bad.json", { type: "application/json" }),
    );
    expect(await screen.findByRole("alert")).toHaveTextContent(
      "Duplicate reference event.",
    );
    expect(screen.getByText("SYNTHETIC DATASET")).toBeInTheDocument();
    vi.mocked(validationApi.evaluate).mockRejectedValueOnce(
      new Error("Reference parser unavailable."),
    );
    await user.click(
      screen.getByRole("button", { name: "Evaluate speed references" }),
    );
    expect(await screen.findByRole("alert")).toHaveTextContent(
      "Reference parser unavailable.",
    );
    expect(screen.getByText("No speed evaluation yet")).toBeInTheDocument();
    await user.click(
      screen.getByRole("button", { name: "Evaluate speed references" }),
    );
    await screen.findByRole("table", { name: "Validation measurements" });
    vi.mocked(validationApi.export).mockRejectedValue(
      new Error("Export failed."),
    );
    await user.click(
      screen.getByRole("button", { name: "Export validation JSON" }),
    );
    expect(await screen.findByRole("alert")).toHaveTextContent(
      "Export failed.",
    );
    expect(downloadResult).not.toHaveBeenCalled();
  });
  it("runs the tracking comparison, distinguishes suspicions from ground truth, and exports the same run", async () => {
    const user = await ready();
    await user.click(
      screen.getByRole("button", { name: "Run tracking benchmark" }),
    );
    const table = await screen.findByRole("table", {
      name: "Tracking benchmark comparison",
    });
    expect(
      within(table).getByText("Annotated identity switches"),
    ).toBeInTheDocument();
    expect(
      within(table).getByText("Potential ID-switch suspicions"),
    ).toBeInTheDocument();
    expect(within(table).getAllByText("Unavailable")).toHaveLength(2);
    expect(
      screen.getByRole("img", {
        name: /Ground truth and baseline versus improved/,
      }),
    ).toBeInTheDocument();
    expect(screen.getByText(/Test CPU/)).toBeInTheDocument();
    await user.click(
      screen.getByRole("button", { name: "Export tracking benchmark JSON" }),
    );
    expect(validationApi.exportBenchmark).toHaveBeenCalledWith(
      benchmark,
      "json",
    );
    await waitFor(() =>
      expect(downloadResult).toHaveBeenCalledWith(
        expect.any(Blob),
        "roadlens-tracking-benchmark.json",
      ),
    );
  });
  it("shows a failed benchmark as an error with retry available", async () => {
    const user = await ready();
    vi.mocked(validationApi.benchmark).mockRejectedValue(
      new Error("Benchmark unavailable."),
    );
    await user.click(
      screen.getByRole("button", { name: "Run tracking benchmark" }),
    );
    expect(await screen.findByRole("alert")).toHaveTextContent(
      "Benchmark unavailable.",
    );
    expect(
      screen.queryByRole("table", { name: "Tracking benchmark comparison" }),
    ).not.toBeInTheDocument();
    expect(
      screen.getByRole("button", { name: "Run tracking benchmark" }),
    ).toBeEnabled();
  });
  it("permits import after an example-load failure and prevents actions while disconnected", async () => {
    vi.mocked(validationApi.example).mockRejectedValue(
      new Error("Example not available."),
    );
    render(<ValidationBenchmarks connected={false} />);
    expect(await screen.findByRole("alert")).toHaveTextContent(
      "Example not available.",
    );
    expect(
      screen.getByRole("button", { name: "Evaluate speed references" }),
    ).toBeDisabled();
    expect(
      screen.getByRole("button", { name: "Run tracking benchmark" }),
    ).toBeDisabled();
    expect(screen.getByLabelText("Import validation dataset")).toBeDisabled();
  });
});
describe("chart handling", () => {
  it("omits excluded, missing, and nonfinite pairs rather than plotting them at zero", () => {
    const invalid = [
      report.rows[3],
      { ...included[0], record: { ...records[0], estimated_speed_kmh: null } },
      { ...included[1], error_kmh: Number.NaN },
      {
        ...included[2],
        record: {
          ...records[2],
          reference_speed_kmh: Number.POSITIVE_INFINITY,
        },
      },
    ];
    expect(chartPairs([...included, ...invalid])).toEqual(included);
    const { container } = render(
      <SpeedCharts rows={[...included, ...invalid]} />,
    );
    expect(container.querySelectorAll("circle")).toHaveLength(6);
    expect(container.innerHTML).not.toMatch(
      /cx="(?:NaN|Infinity)"|cy="(?:NaN|Infinity)"/,
    );
    expect(formatMetric(null)).toBe("—");
    expect(formatMetric(0)).toBe("0.00");
  });
});
