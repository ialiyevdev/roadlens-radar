import { afterEach, describe, expect, it, vi } from "vitest";
import { annotationApi } from "./annotationApi";
import type { AnnotationDocument } from "./annotationApi";

afterEach(() => vi.unstubAllGlobals());
const document: AnnotationDocument = {
  schema_version: 1,
  field_session_id: "field-1",
  source_id: "synthetic-video",
  geometry: {
    width: 640,
    height: 480,
    rotation: 0,
    mirrored: false,
    crop: null,
    coordinate_space: "source",
    intrinsic_profile_id: null,
  },
  revision: 7,
  provenance: "synthetic",
  frames: [
    {
      index: 1,
      timestamp_s: 0,
      reviewed: true,
      objects: [
        {
          identity: "truth-vehicle-A",
          category: "car",
          bbox: [10, 20, 80, 90],
          occluded: false,
          partial_visibility: true,
          entry: true,
          exit: false,
        },
      ],
      predictions: [
        {
          predicted_track_id: 42,
          category: "car",
          bbox: [11, 21, 79, 89],
          confidence: 0.8,
        },
      ],
    },
  ],
};
describe("annotation API", () => {
  it("preserves manual identity, flags, source geometry and revision when saving", async () => {
    const fetch = vi
      .fn()
      .mockResolvedValue(new Response(JSON.stringify(document)));
    vi.stubGlobal("fetch", fetch);
    expect(await annotationApi.save("field/id", document)).toEqual(document);
    expect(fetch).toHaveBeenCalledWith(
      "/api/field-sessions/field%2Fid/annotations",
      expect.objectContaining({
        method: "PUT",
        body: JSON.stringify(document),
      }),
    );
  });
  it("requests actual frame indices and source timestamps independently", async () => {
    const fetch = vi.fn().mockImplementation(async () => new Response("{}"));
    vi.stubGlobal("fetch", fetch);
    await annotationApi.frame("field-1", 19);
    await annotationApi.frameAt("field-1", 1.2345);
    expect(fetch.mock.calls.map(([path]) => path)).toEqual([
      "/api/field-sessions/field-1/frames?index=19",
      "/api/field-sessions/field-1/frames?timestamp_s=1.2345",
    ]);
  });
  it("imports the selected file with browser multipart boundaries", async () => {
    const fetch = vi
      .fn()
      .mockResolvedValue(new Response(JSON.stringify(document)));
    vi.stubGlobal("fetch", fetch);
    const file = new File(["fixture"], "labels.csv", { type: "text/csv" });
    await annotationApi.import("field-1", file);
    const [path, options] = fetch.mock.calls[0] as [string, RequestInit];
    expect(path).toBe("/api/field-sessions/field-1/annotations/import");
    expect(options.headers).toBeUndefined();
    expect((options.body as FormData).get("file")).toBe(file);
  });
  it("requests a bounded tracker proposal range without changing ground-truth IDs", async () => {
    const fetch = vi
      .fn()
      .mockResolvedValue(new Response(JSON.stringify(document)));
    vi.stubGlobal("fetch", fetch);
    const result = await annotationApi.propose("field-1", 25, 49, "baseline");
    expect(result.frames[0].objects[0].identity).toBe("truth-vehicle-A");
    expect(fetch).toHaveBeenCalledWith(
      "/api/field-sessions/field-1/proposals",
      expect.objectContaining({
        method: "POST",
        body: JSON.stringify({
          start_index: 25,
          end_index: 49,
          input_size: 416,
          confidence: 0.35,
          tracker: "baseline",
        }),
      }),
    );
  });
  it("surfaces revision conflicts and schema validation failures", async () => {
    vi.stubGlobal(
      "fetch",
      vi
        .fn()
        .mockResolvedValueOnce(
          new Response(
            JSON.stringify({
              detail: "Annotation revision changed. Reload before saving.",
            }),
            { status: 409 },
          ),
        )
        .mockResolvedValueOnce(
          new Response(
            JSON.stringify({
              detail: [
                {
                  loc: ["body", "frames", 0, "objects", 0, "bbox"],
                  msg: "Box exceeds frame geometry",
                },
              ],
            }),
            { status: 422 },
          ),
        ),
    );
    await expect(annotationApi.save("field-1", document)).rejects.toThrow(
      "Annotation revision changed. Reload before saving.",
    );
    await expect(annotationApi.save("field-1", document)).rejects.toThrow(
      "frames.0.objects.0.bbox: Box exceeds frame geometry",
    );
  });
});
