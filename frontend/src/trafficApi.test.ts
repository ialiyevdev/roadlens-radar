import { afterEach, describe, expect, it, vi } from "vitest";
import { trafficApi } from "./trafficApi";
import { trafficConfig, trafficOverlays } from "./trafficTestFixtures";
afterEach(() => vi.unstubAllGlobals());
describe("traffic API", () => {
  it("uses dedicated traffic geometry and overlay contracts", async () => {
    const fetcher = vi
      .fn()
      .mockResolvedValue({ ok: true, json: async () => trafficConfig });
    vi.stubGlobal("fetch", fetcher);
    await trafficApi.configure(trafficConfig);
    expect(fetcher.mock.calls[0][0]).toBe("/api/traffic/configuration");
    expect(JSON.parse(fetcher.mock.calls[0][1].body)).toEqual(trafficConfig);
    await trafficApi.setOverlays(trafficOverlays);
    expect(fetcher.mock.calls[1][0]).toBe("/api/traffic/overlays");
    expect(JSON.parse(fetcher.mock.calls[1][1].body)).toEqual(trafficOverlays);
  });
  it("exports selected source-time datasets and units in CSV or JSON", async () => {
    const blob = new Blob(["timestamp_s,class\n1,car"]);
    const fetcher = vi
      .fn()
      .mockResolvedValue({ ok: true, blob: async () => blob });
    vi.stubGlobal("fetch", fetcher);
    const request = {
      session_ids: ["archive"],
      include_current: false,
      interval_minutes: 5,
      speed_status: "valid" as const,
      start_s: 2,
      end_s: 60,
    };
    expect(await trafficApi.export(request, "flow", "csv")).toBe(blob);
    expect(fetcher.mock.calls[0][0]).toBe(
      "/api/traffic/export?table=flow&format=csv",
    );
    expect(JSON.parse(fetcher.mock.calls[0][1].body)).toEqual(request);
  });
  it("encodes saved session identifiers and requests held-out evaluation explicitly", async () => {
    const fetcher = vi
      .fn()
      .mockResolvedValue({ ok: true, json: async () => ({}) });
    vi.stubGlobal("fetch", fetcher);
    await trafficApi.get("source/one");
    expect(fetcher.mock.calls[0][0]).toBe("/api/traffic/sessions/source%2Fone");
    await trafficApi.evaluate({
      traffic_session_id: "a",
      field_session_id: "b",
      maximum_time_error_s: 0.3,
      partition: "held_out",
    });
    expect(JSON.parse(fetcher.mock.calls[1][1].body)).toMatchObject({
      partition: "held_out",
      maximum_time_error_s: 0.3,
    });
  });
  it("surfaces validation and export failures without downloading error JSON", async () => {
    vi.stubGlobal(
      "fetch",
      vi
        .fn()
        .mockResolvedValue({
          ok: false,
          status: 422,
          json: async () => ({ detail: "Source geometry mismatch" }),
        }),
    );
    await expect(trafficApi.configure(trafficConfig)).rejects.toThrow(
      "Source geometry mismatch",
    );
    await expect(
      trafficApi.export(
        {
          session_ids: [],
          include_current: true,
          interval_minutes: 1,
          speed_status: "valid",
        },
        "events",
        "json",
      ),
    ).rejects.toThrow("Source geometry mismatch");
  });
});
