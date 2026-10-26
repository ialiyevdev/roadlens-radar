import { afterEach, describe, expect, it, vi } from "vitest";
import { validationApi } from "./validationApi";
import type { ValidationDataset } from "./validationTypes";

afterEach(() => vi.unstubAllGlobals());
const dataset: ValidationDataset = {
  name: "Synthetic",
  provenance: "synthetic",
  description: "Fixture",
  records: [],
};
describe("validation API", () => {
  it("sends imports as multipart data without overriding its content boundary", async () => {
    const fetch = vi
      .fn()
      .mockResolvedValue(
        new Response(JSON.stringify(dataset), {
          headers: { "Content-Type": "application/json" },
        }),
      );
    vi.stubGlobal("fetch", fetch);
    const file = new File(["{}"], "synthetic.json", {
      type: "application/json",
    });
    expect(await validationApi.import(file)).toEqual(dataset);
    const [path, options] = fetch.mock.calls[0];
    expect(path).toBe("/api/validation/import");
    expect(options.method).toBe("POST");
    expect(options.headers).toBeUndefined();
    expect(options.body.get("file")).toBe(file);
  });
  it("preserves dataset provenance and applied options in exports", async () => {
    const fetch = vi
      .fn()
      .mockResolvedValue(new Response("measurement_id,error_kmh\n"));
    vi.stubGlobal("fetch", fetch);
    const options = { tolerance_bands_kmh: [2, 5], minimum_group_samples: 4 };
    const blob = await validationApi.export(dataset, options, "csv");
    expect(blob.size).toBeGreaterThan(0);
    expect(fetch).toHaveBeenCalledWith(
      "/api/validation/export?format=csv",
      expect.objectContaining({
        method: "POST",
        body: JSON.stringify({ dataset, options }),
      }),
    );
  });
  it("shows validation field locations from FastAPI input errors", async () => {
    vi.stubGlobal(
      "fetch",
      vi
        .fn()
        .mockResolvedValue(
          new Response(
            JSON.stringify({
              detail: [
                {
                  loc: ["body", "dataset", "records", 0, "reference_speed_kmh"],
                  msg: "Input should be finite",
                },
              ],
            }),
            { status: 422 },
          ),
        ),
    );
    await expect(validationApi.example()).rejects.toThrow(
      "dataset.records.0.reference_speed_kmh: Input should be finite",
    );
  });
  it("handles non-JSON local proxy errors", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn().mockResolvedValue(new Response("offline", { status: 502 })),
    );
    await expect(validationApi.benchmark()).rejects.toThrow(
      "Request failed (502).",
    );
  });
});
