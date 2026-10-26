import { beforeEach, describe, expect, it, vi } from "vitest";
import {
  fireEvent,
  render,
  screen,
  waitFor,
  within,
} from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import TrafficEvaluation from "./TrafficEvaluation";
import { trafficApi } from "./trafficApi";
import { fieldApi } from "./fieldApi";
import type { FieldSession } from "./fieldTypes";
vi.mock("./trafficApi", () => ({ trafficApi: { evaluate: vi.fn() } }));
vi.mock("./fieldApi", () => ({ fieldApi: { list: vi.fn() } }));
const fields = [
  {
    id: "field-1",
    name: "Manual fixture",
    partition: "held_out",
    provenance: "synthetic",
  },
  {
    id: "field-2",
    name: "Tuning clip",
    partition: "development",
    provenance: "recorded_unverified",
  },
] as FieldSession[];
const sessions = [
  { id: "traffic-1", name: "Predicted fixture", provenance: "synthetic" },
];
const report = {
  truth_count: 2,
  predicted_count: 3,
  matched_count: 2,
  duplicate_count: 1,
  missed_count: 0,
  precision: 2 / 3,
  recall: 1,
  classification_sample_count: 2,
  confusion_matrix: [{ truth: "car", prediction: "truck", count: 1 }],
  rows: [
    {
      outcome: "matched",
      truth: { identity: "manual-car", line_id: "approach", timestamp_s: 2 },
      prediction: { track_id: 7 },
      class_correct: false,
      direction_correct: true,
      time_error_s: 0.1,
    },
    {
      outcome: "duplicate",
      truth: null,
      prediction: { track_id: 8, timestamp_s: 2.1 },
    },
  ],
  limitations: ["Synthetic fixture only"],
};
beforeEach(() => {
  vi.clearAllMocks();
  vi.mocked(fieldApi.list).mockResolvedValue({ sessions: fields });
  vi.mocked(trafficApi.evaluate).mockResolvedValue(report);
});
async function selected() {
  const user = userEvent.setup();
  render(<TrafficEvaluation connected sessions={sessions} />);
  await screen.findByRole("option", { name: /Manual fixture/ });
  await user.selectOptions(
    screen.getByLabelText("Predicted traffic session"),
    "traffic-1",
  );
  await user.selectOptions(
    screen.getByLabelText("Manual field annotations"),
    "field-1",
  );
  return user;
}
describe("traffic annotation evidence", () => {
  it("refreshes newly saved field sessions when the evaluation view reopens", async () => {
    const view = render(
      <TrafficEvaluation connected sessions={sessions} visible={false} />,
    );
    expect(fieldApi.list).not.toHaveBeenCalled();
    view.rerender(<TrafficEvaluation connected sessions={sessions} visible />);
    await screen.findByRole("option", { name: /Manual fixture/ });
    view.rerender(
      <TrafficEvaluation connected sessions={sessions} visible={false} />,
    );
    vi.mocked(fieldApi.list).mockResolvedValue({
      sessions: [
        ...fields,
        { ...fields[0], id: "field-new", name: "New collected labels" },
      ],
    });
    view.rerender(<TrafficEvaluation connected sessions={sessions} visible />);
    expect(
      await screen.findByRole("option", { name: /New collected labels/ }),
    ).toBeInTheDocument();
    expect(fieldApi.list).toHaveBeenCalledTimes(2);
  });
  it("requires a saved predicted session and manual recording before evaluation", async () => {
    render(<TrafficEvaluation connected sessions={[]} />);
    expect(
      await screen.findByRole("button", {
        name: "Evaluate traffic predictions",
      }),
    ).toBeDisabled();
    expect(
      screen.getByText(/No independent real-world accuracy result/),
    ).toBeVisible();
  });
  it("defaults to held out and displays counts, classification errors and duplicated tracks", async () => {
    const user = await selected();
    await user.click(
      screen.getByRole("button", { name: "Evaluate traffic predictions" }),
    );
    expect(
      await screen.findByRole("heading", {
        name: "Traffic evaluation results",
      }),
    ).toBeVisible();
    expect(trafficApi.evaluate).toHaveBeenCalledWith({
      traffic_session_id: "traffic-1",
      field_session_id: "field-1",
      maximum_time_error_s: 0.5,
      partition: "held_out",
    });
    const rows = screen.getByRole("table", {
      name: "Predicted versus manual crossings",
    });
    expect(within(rows).getByText("duplicate")).toBeVisible();
    expect(within(rows).getByText("manual-car")).toBeVisible();
    expect(rows.querySelector(".traffic-evaluation-error")).toBeInTheDocument();
    expect(
      screen.getByRole("table", { name: "Vehicle class confusion matrix" }),
    ).toBeVisible();
  });
  it("clears results when evidence or evaluation tolerances change", async () => {
    const user = await selected();
    await user.click(
      screen.getByRole("button", { name: "Evaluate traffic predictions" }),
    );
    await screen.findByRole("heading", { name: "Traffic evaluation results" });
    fireEvent.change(
      screen.getByLabelText("Crossing alignment tolerance · s"),
      { target: { value: ".2" } },
    );
    expect(
      screen.queryByRole("heading", { name: "Traffic evaluation results" }),
    ).not.toBeInTheDocument();
    await user.click(
      screen.getByRole("button", { name: "Evaluate traffic predictions" }),
    );
    expect(trafficApi.evaluate).toHaveBeenLastCalledWith(
      expect.objectContaining({ maximum_time_error_s: 0.2 }),
    );
  });
  it("reports partition/source incompatibility and retains chosen evidence for correction", async () => {
    const user = await selected();
    vi.mocked(trafficApi.evaluate).mockRejectedValue(
      new Error("Field recording differs from the predicted source."),
    );
    await user.click(
      screen.getByRole("button", { name: "Evaluate traffic predictions" }),
    );
    expect(await screen.findByRole("alert")).toHaveTextContent(
      "recording differs",
    );
    expect(screen.getByLabelText("Manual field annotations")).toHaveValue(
      "field-1",
    );
    await waitFor(() =>
      expect(
        screen.getByRole("button", { name: "Evaluate traffic predictions" }),
      ).toBeEnabled(),
    );
  });
});
