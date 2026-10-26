import { describe, expect, it } from "vitest";
import { gateErrors, imagePoint } from "./calibrationCoordinates";

describe("calibration source coordinates", () => {
  it("maps a resized preview to original source pixels", () => {
    expect(
      imagePoint(
        260,
        155,
        { left: 100, top: 65, width: 640, height: 360 },
        1280,
        720,
      ),
    ).toEqual([320, 180]);
  });
  it("accounts for letterboxing and rejects clicks outside the displayed image", () => {
    const rect = { left: 20, top: 30, width: 640, height: 480 };
    expect(imagePoint(340, 270, rect, 1280, 720)).toEqual([640, 360]);
    expect(imagePoint(340, 45, rect, 1280, 720)).toBeNull();
    expect(imagePoint(15, 270, rect, 1280, 720)).toBeNull();
  });
  it("rejects unloaded and zero-sized views", () => {
    expect(
      imagePoint(1, 1, { left: 0, top: 0, width: 0, height: 0 }, 640, 360),
    ).toBeNull();
  });
  it("requires two finite, nonzero gate segments", () => {
    expect(gateErrors(null, null)).toHaveLength(1);
    expect(
      gateErrors(
        [
          [10, 10],
          [10, 10],
        ],
        [
          [0, 30],
          [100, 30],
        ],
      ),
    ).toContain("Gate A needs distinct endpoints.");
    expect(
      gateErrors(
        [
          [0, 10],
          [100, 10],
        ],
        [
          [0, 30],
          [100, 30],
        ],
      ),
    ).toEqual([]);
  });
});
