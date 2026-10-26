import { afterEach, describe, expect, it, vi } from "vitest";
import { api } from "./api";

afterEach(() => vi.unstubAllGlobals());

describe("local API client", () => {
  it("preserves a useful backend error instead of treating an error response as session data", async () => {
    vi.stubGlobal(
      "fetch",
      vi
        .fn()
        .mockResolvedValue(
          new Response(
            JSON.stringify({ detail: "Stop the active session first." }),
            { status: 409 },
          ),
        ),
    );
    await expect(api.control("reset")).rejects.toThrow(
      "Stop the active session first.",
    );
  });

  it("handles a non-JSON proxy error with a clear HTTP status", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn().mockResolvedValue(new Response("Bad Gateway", { status: 502 })),
    );
    await expect(api.session()).rejects.toThrow("Request failed (502).");
  });
  it("surfaces structured field validation errors", async () => {
    vi.stubGlobal(
      "fetch",
      vi
        .fn()
        .mockResolvedValue(
          new Response(
            JSON.stringify({
              detail: [
                {
                  loc: ["body", "points", 0, "world"],
                  msg: "Input should be finite",
                },
              ],
            }),
            { status: 422 },
          ),
        ),
    );
    await expect(api.session()).rejects.toThrow(
      "points.0.world: Input should be finite",
    );
  });
});
