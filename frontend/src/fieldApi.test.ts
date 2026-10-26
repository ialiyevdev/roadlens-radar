import { afterEach, describe, expect, it, vi } from "vitest";
import { fieldApi } from "./fieldApi";
import { emptyFieldSession } from "./FieldMetadata";

afterEach(() => vi.unstubAllGlobals());
describe("local field API", () => {
  it("posts structured metadata and encodes field identifiers", async () => {
    const fetch = vi
      .fn()
      .mockResolvedValue(
        new Response(JSON.stringify({ id: "saved" }), { status: 200 }),
      );
    vi.stubGlobal("fetch", fetch);
    const input = { ...emptyFieldSession(), name: "Local observation" };
    await fieldApi.update("field/identifier", input);
    expect(fetch).toHaveBeenCalledWith(
      "/api/field-sessions/field%2Fidentifier",
      expect.objectContaining({ method: "PUT", body: JSON.stringify(input) }),
    );
  });
  it("uploads references as multipart data without selecting event pairs", async () => {
    const fetch = vi
      .fn()
      .mockResolvedValue(new Response("{}", { status: 200 }));
    vi.stubGlobal("fetch", fetch);
    const file = new File(["id,timestamp_s"], "references.csv", {
      type: "text/csv",
    });
    await fieldApi.importReferences("field-1", file);
    const [path, options] = fetch.mock.calls[0] as [string, RequestInit];
    expect(path).toBe("/api/field-sessions/field-1/references/import");
    expect(options.body).toBeInstanceOf(FormData);
    expect((options.body as FormData).get("file")).toBe(file);
  });
  it("returns report downloads and preserves the evaluation partition", async () => {
    const fetch = vi
      .fn()
      .mockResolvedValue(new Response("<html>Report</html>", { status: 200 }));
    vi.stubGlobal("fetch", fetch);
    const request = {
      session_ids: ["field-1"],
      partition: "held_out" as const,
      variant: "original" as const,
      options: { minimum_group_samples: 3, tolerance_bands_kmh: [3, 5] },
      description: "Held-out observations",
    };
    const blob = await fieldApi.exportEvaluation(request, "html");
    expect(blob.size).toBeGreaterThan(0);
    expect(fetch).toHaveBeenCalledWith(
      "/api/field-evaluation/export?format=html",
      expect.objectContaining({ body: JSON.stringify(request) }),
    );
  });
  it("surfaces structured validation failures and plain proxy failures", async () => {
    vi.stubGlobal(
      "fetch",
      vi
        .fn()
        .mockResolvedValueOnce(
          new Response(
            JSON.stringify({
              detail: [
                {
                  loc: ["body", "source", "segment_end_s"],
                  msg: "End must follow start",
                },
              ],
            }),
            { status: 422 },
          ),
        )
        .mockResolvedValueOnce(new Response("Unavailable", { status: 503 })),
    );
    await expect(fieldApi.create(emptyFieldSession())).rejects.toThrow(
      "source.segment_end_s: End must follow start",
    );
    await expect(fieldApi.list()).rejects.toThrow("Request failed (503).");
  });
});
