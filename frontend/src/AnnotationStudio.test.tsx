import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import {
  act,
  fireEvent,
  render,
  screen,
  waitFor,
} from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import AnnotationStudio from "./AnnotationStudio";
import { annotationApi } from "./annotationApi";
import type { AnnotationDocument, AnnotationFrameInfo } from "./annotationApi";

vi.mock("./annotationApi", () => ({
  annotationApi: {
    get: vi.fn(),
    frame: vi.fn(),
    frameAt: vi.fn(),
    save: vi.fn(),
    import: vi.fn(),
    propose: vi.fn(),
  },
}));
function fixture(): AnnotationDocument {
  return {
    schema_version: 1,
    field_session_id: "field-1",
    source_id: "synthetic-road-video",
    geometry: {
      width: 640,
      height: 480,
      rotation: 0,
      mirrored: false,
      crop: null,
      coordinate_space: "source",
      intrinsic_profile_id: null,
    },
    revision: 3,
    provenance: "synthetic",
    frames: [
      {
        index: 1,
        timestamp_s: 0,
        reviewed: false,
        objects: [
          {
            identity: "truth-A",
            category: "truck",
            bbox: [40, 60, 120, 150],
            occluded: false,
            partial_visibility: false,
            entry: false,
            exit: false,
          },
        ],
        predictions: [
          {
            predicted_track_id: 77,
            category: "car",
            bbox: [200, 100, 280, 190],
            confidence: 0.9,
          },
        ],
      },
    ],
  };
}
function info(index = 1): AnnotationFrameInfo {
  return {
    index,
    timestamp_s: (index - 1) / 25,
    pts: index - 1,
    time_base: "1/25",
    width: 640,
    height: 480,
    timing_warning: null,
    total_frames: 60,
    image_url: `/api/field-sessions/field-1/frames/image?index=${index}`,
    coordinate_space: "source",
    intrinsic_profile_id: null,
  };
}
beforeEach(() => {
  vi.resetAllMocks();
  vi.stubGlobal("PointerEvent", MouseEvent);
  vi.mocked(annotationApi.get).mockImplementation(async () => fixture());
  vi.mocked(annotationApi.frame).mockImplementation(async (_, index) =>
    info(index),
  );
  vi.mocked(annotationApi.frameAt).mockResolvedValue(info(3));
  vi.mocked(annotationApi.save).mockImplementation(async (_, value) => ({
    ...value,
    revision: value.revision + 1,
  }));
  vi.mocked(annotationApi.import).mockImplementation(async () => fixture());
  vi.mocked(annotationApi.propose).mockImplementation(async () => fixture());
});
afterEach(() => vi.unstubAllGlobals());
async function ready(onSaved = vi.fn()) {
  const user = userEvent.setup();
  render(
    <AnnotationStudio fieldSessionId="field-1" connected onSaved={onSaved} />,
  );
  await screen.findByRole("img", {
    name: "Annotation frame 1 in source image pixels",
  });
  await screen.findByRole("option", { name: "truth-A" });
  return user;
}
async function chooseTruth(user: ReturnType<typeof userEvent.setup>) {
  await user.selectOptions(
    screen.getByLabelText("Selected annotation"),
    "truth-A",
  );
}
function savedFrame() {
  return vi
    .mocked(annotationApi.save)
    .mock.calls.at(-1)![1]
    .frames.find((frame) => frame.index === 1)!;
}

describe("manual vehicle annotation", () => {
  it("requires saving changed labels before exporting and restores download links after save", async () => {
    const user = await ready();
    expect(screen.getByText("Export annotations JSON")).toHaveAttribute("href");
    await chooseTruth(user);
    fireEvent.change(screen.getByLabelText("Left x"), {
      target: { value: "45" },
    });
    expect(screen.getByText("Export annotations JSON")).not.toHaveAttribute(
      "href",
    );
    expect(screen.getByText("Export annotations CSV")).toHaveAttribute(
      "aria-disabled",
      "true",
    );
    expect(screen.getByText(/Save annotations before exporting/)).toBeVisible();
    await user.click(screen.getByRole("button", { name: "Save annotations" }));
    await screen.findByText("Annotations saved incrementally.");
    expect(screen.getByText("Export annotations JSON")).toHaveAttribute(
      "href",
      expect.stringContaining("format=json"),
    );
    expect(screen.getByText("Export annotations CSV")).toHaveAttribute(
      "aria-disabled",
      "false",
    );
  });
  it("edits boxes and review flags while keeping truth identity separate from predicted ID", async () => {
    const onSaved = vi.fn(),
      user = await ready(onSaved);
    await chooseTruth(user);
    fireEvent.change(screen.getByLabelText("Left x"), {
      target: { value: "45" },
    });
    await user.click(screen.getByLabelText("partial visibility"));
    await user.click(screen.getByLabelText("entry"));
    await user.click(
      screen.getByLabelText("Frame reviewed, including empty frames"),
    );
    await user.click(screen.getByRole("button", { name: "Save annotations" }));
    expect(
      await screen.findByText("Annotations saved incrementally."),
    ).toBeVisible();
    expect(savedFrame()).toEqual(
      expect.objectContaining({
        reviewed: true,
        timestamp_s: 0,
        objects: [
          expect.objectContaining({
            identity: "truth-A",
            bbox: [45, 60, 120, 150],
            partial_visibility: true,
            entry: true,
          }),
        ],
        predictions: [expect.objectContaining({ predicted_track_id: 77 })],
      }),
    );
    expect(annotationApi.save).toHaveBeenCalledWith(
      "field-1",
      expect.objectContaining({ revision: 3, provenance: "synthetic" }),
    );
    expect(onSaved).toHaveBeenCalledOnce();
    expect(screen.getByText("Revision 4")).toBeVisible();
  });
  it("draws a source-coordinate box using an explicit manual identity", async () => {
    await ready();
    fireEvent.change(screen.getByLabelText("Ground-truth identity"), {
      target: { value: "truth-B" },
    });
    const canvas = screen.getByRole("img", {
      name: "Annotation frame 1 in source image pixels",
    });
    Object.defineProperty(canvas, "getScreenCTM", {
      value: () => ({ inverse: () => ({}) }),
    });
    Object.defineProperty(canvas, "createSVGPoint", {
      value: () => {
        const point = {
          x: 0,
          y: 0,
          matrixTransform: () => ({ x: point.x, y: point.y }),
        };
        return point;
      },
    });
    fireEvent.pointerDown(canvas, { clientX: 100, clientY: 200 });
    fireEvent.pointerMove(canvas, { clientX: 210, clientY: 330 });
    fireEvent.pointerUp(canvas);
    expect(screen.getByLabelText("Selected annotation")).toHaveValue("truth-B");
    fireEvent.click(screen.getByRole("button", { name: "Save annotations" }));
    await screen.findByText("Annotations saved incrementally.");
    expect(
      savedFrame().objects.find((item) => item.identity === "truth-B"),
    ).toEqual(
      expect.objectContaining({ bbox: [100, 200, 210, 330], occluded: false }),
    );
  });
  it("marks full occlusion without a fabricated box and removes labels explicitly", async () => {
    const user = await ready();
    await chooseTruth(user);
    await user.click(
      screen.getByRole("button", {
        name: "Mark selected identity fully occluded",
      }),
    );
    expect(screen.queryByLabelText("Left x")).not.toBeInTheDocument();
    await user.click(screen.getByRole("button", { name: "Save annotations" }));
    await screen.findByText("Annotations saved incrementally.");
    expect(savedFrame().objects[0]).toEqual(
      expect.objectContaining({
        identity: "truth-A",
        bbox: null,
        occluded: true,
        partial_visibility: false,
      }),
    );
    await user.click(screen.getByRole("button", { name: "Remove annotation" }));
    await user.click(screen.getByRole("button", { name: "Save annotations" }));
    await waitFor(() => expect(annotationApi.save).toHaveBeenCalledTimes(2));
    expect(savedFrame().objects).toEqual([]);
  });
  it("rejects duplicate truth identities instead of treating a tracker proposal as truth", async () => {
    const user = await ready();
    fireEvent.change(screen.getByLabelText("Ground-truth identity"), {
      target: { value: "truth-A" },
    });
    await user.click(
      screen.getByRole("button", {
        name: "Use predicted #77 box with entered truth identity",
      }),
    );
    expect(screen.getByRole("alert")).toHaveTextContent(
      "Enter a unique ground-truth identity for this frame.",
    );
    expect(
      screen.getByRole("button", { name: "Save annotations" }),
    ).toBeDisabled();
    expect(annotationApi.save).not.toHaveBeenCalled();
  });
  it("accepts a proposed box only after assigning a separate truth identity", async () => {
    const user = await ready();
    expect(screen.getAllByRole("option", { name: "truth-A" })).toHaveLength(1);
    expect(annotationApi.save).not.toHaveBeenCalled();
    fireEvent.change(screen.getByLabelText("Ground-truth identity"), {
      target: { value: "independent-truth-B" },
    });
    await user.click(
      screen.getByRole("button", {
        name: "Use predicted #77 box with entered truth identity",
      }),
    );
    expect(
      screen.getByRole("button", { name: "Propose next 25 frames" }),
    ).toBeDisabled();
    await user.click(screen.getByRole("button", { name: "Save annotations" }));
    await screen.findByText("Annotations saved incrementally.");
    expect(
      savedFrame().objects.find(
        (item) => item.identity === "independent-truth-B",
      ),
    ).toEqual(expect.objectContaining({ bbox: [200, 100, 280, 190] }));
    expect(savedFrame().objects.map((item) => item.identity)).not.toContain(
      "77",
    );
  });
  it("preserves unsaved box edits when persistence fails and allows a retry", async () => {
    vi.mocked(annotationApi.save).mockRejectedValueOnce(
      new Error("Annotation revision changed; reload before saving."),
    );
    const user = await ready();
    await chooseTruth(user);
    fireEvent.change(screen.getByLabelText("Right x"), {
      target: { value: "130" },
    });
    await user.click(screen.getByRole("button", { name: "Save annotations" }));
    expect(await screen.findByRole("alert")).toHaveTextContent(
      "Annotation revision changed; reload before saving.",
    );
    expect(screen.getByLabelText("Right x")).toHaveValue(130);
    expect(screen.getByText("Unsaved changes")).toBeVisible();
    expect(
      screen.getByRole("button", { name: "Save annotations" }),
    ).toBeEnabled();
    expect(
      screen.getByRole("button", { name: "Propose next 25 frames" }),
    ).toBeDisabled();
  });
  it("prevents intervening edits from being lost while a save response is pending", async () => {
    let finish!: (value: AnnotationDocument) => void;
    vi.mocked(annotationApi.save).mockImplementation(
      () =>
        new Promise((resolve) => {
          finish = resolve;
        }),
    );
    const user = await ready();
    await chooseTruth(user);
    fireEvent.change(screen.getByLabelText("Left x"), {
      target: { value: "50" },
    });
    await user.click(screen.getByRole("button", { name: "Save annotations" }));
    expect(screen.getByLabelText("Left x")).toBeDisabled();
    expect(screen.getByLabelText("Edit identity")).toBeDisabled();
    expect(
      screen.getByRole("button", {
        name: "Use predicted #77 box with entered truth identity",
      }),
    ).toBeDisabled();
    await act(async () =>
      finish({
        ...vi.mocked(annotationApi.save).mock.calls[0][1],
        revision: 4,
      }),
    );
    expect(screen.getByLabelText("Left x")).toBeEnabled();
    expect(screen.getByLabelText("Left x")).toHaveValue(50);
  });
});
describe("annotation navigation and interchange", () => {
  it("navigates source frame indices and actual timestamp selections", async () => {
    const user = await ready();
    await user.click(screen.getByRole("button", { name: "Next frame" }));
    await screen.findByRole("img", {
      name: "Annotation frame 2 in source image pixels",
    });
    expect(annotationApi.frame).toHaveBeenLastCalledWith("field-1", 2);
    expect(screen.getByText(/source 0.040000 s/)).toBeVisible();
    fireEvent.change(screen.getByLabelText("Source timestamp · s"), {
      target: { value: "0.081" },
    });
    await user.click(screen.getByRole("button", { name: "Go to timestamp" }));
    await screen.findByRole("img", {
      name: "Annotation frame 3 in source image pixels",
    });
    expect(annotationApi.frameAt).toHaveBeenCalledWith("field-1", 0.081);
    fireEvent.change(screen.getByLabelText("Frame number"), {
      target: { value: "999" },
    });
    await user.click(screen.getByRole("button", { name: "Go to frame" }));
    expect(annotationApi.frame).toHaveBeenLastCalledWith("field-1", 3);
  });
  it("uses arrow navigation outside fields and ignores hidden annotation views", async () => {
    const { rerender } = render(
      <div>
        <AnnotationStudio fieldSessionId="field-1" connected />
      </div>,
    );
    const canvas = await screen.findByRole("img", {
      name: "Annotation frame 1 in source image pixels",
    });
    Object.defineProperty(canvas, "getClientRects", {
      value: () =>
        canvas.closest("[hidden]") ? [] : [new DOMRect(0, 0, 640, 480)],
    });
    fireEvent.keyDown(screen.getByLabelText("Ground-truth identity"), {
      key: "ArrowRight",
    });
    expect(annotationApi.frame).toHaveBeenCalledTimes(1);
    fireEvent.keyDown(window, { key: "ArrowRight" });
    await screen.findByRole("img", {
      name: "Annotation frame 2 in source image pixels",
    });
    expect(annotationApi.frame).toHaveBeenCalledTimes(2);
    rerender(
      <div hidden>
        <AnnotationStudio fieldSessionId="field-1" connected />
      </div>,
    );
    fireEvent.keyDown(window, { key: "ArrowRight" });
    expect(annotationApi.frame).toHaveBeenCalledTimes(2);
  });
  it("copies a persistent identity into a new frame while requiring review", async () => {
    const user = await ready();
    await user.click(screen.getByRole("button", { name: "Next frame" }));
    await screen.findByRole("img", {
      name: "Annotation frame 2 in source image pixels",
    });
    await user.click(
      screen.getByRole("button", { name: "Copy previous labels for review" }),
    );
    expect(screen.getByRole("option", { name: "truth-A" })).toBeInTheDocument();
    expect(
      screen.getByLabelText("Frame reviewed, including empty frames"),
    ).not.toBeChecked();
    await user.click(screen.getByRole("button", { name: "Save annotations" }));
    await screen.findByText("Annotations saved incrementally.");
    const second = vi
      .mocked(annotationApi.save)
      .mock.calls[0][1].frames.find((frame) => frame.index === 2)!;
    expect(second.objects[0].identity).toBe("truth-A");
    expect(second.timestamp_s).toBe(0.04);
    expect(second.objects[0].entry).toBe(false);
  });
  it("imports annotations, exposes both exports and bounds offline proposal requests", async () => {
    const user = await ready();
    const file = new File(["synthetic"], "annotations.json", {
      type: "application/json",
    });
    await user.upload(screen.getByLabelText("Import annotations"), file);
    expect(await screen.findByText("Annotations imported.")).toBeVisible();
    expect(annotationApi.import).toHaveBeenCalledWith("field-1", file);
    expect(
      screen.getByRole("link", { name: "Export annotations JSON" }),
    ).toHaveAttribute(
      "href",
      "/api/field-sessions/field-1/annotations/export?format=json",
    );
    expect(
      screen.getByRole("link", { name: "Export annotations CSV" }),
    ).toHaveAttribute(
      "href",
      "/api/field-sessions/field-1/annotations/export?format=csv",
    );
    await user.selectOptions(
      screen.getByLabelText("Proposal tracker"),
      "baseline",
    );
    await user.click(
      screen.getByRole("button", { name: "Propose next 25 frames" }),
    );
    await waitFor(() =>
      expect(annotationApi.propose).toHaveBeenCalledWith(
        "field-1",
        1,
        25,
        "baseline",
      ),
    );
    expect(await screen.findByText(/Offline proposals saved/)).toBeVisible();
  });
  it("shows missing-source and timing warnings without fabricating frame timestamps", async () => {
    vi.mocked(annotationApi.frame).mockRejectedValue(
      new Error("No uploaded source is associated with this field session."),
    );
    const { rerender } = render(
      <AnnotationStudio fieldSessionId="field-1" connected />,
    );
    expect(await screen.findByRole("alert")).toHaveTextContent(
      "No uploaded source is associated",
    );
    expect(screen.getByText("No navigable recording selected")).toBeVisible();
    vi.mocked(annotationApi.frame).mockResolvedValue({
      ...info(),
      timestamp_s: null,
      timing_warning: "Video PTS unavailable; inspect the original recording.",
    });
    rerender(<AnnotationStudio fieldSessionId="field-2" connected />);
    expect(
      await screen.findByText(
        "Video PTS unavailable; inspect the original recording.",
      ),
    ).toBeVisible();
    expect(screen.getByText(/source unavailable s/)).toBeVisible();
  });
});
