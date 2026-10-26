import type { Point, Segment } from "./types";

// SVG uses "meet": clicks in the letterbox must not become source pixels.
export function imagePoint(
  clientX: number,
  clientY: number,
  rect: Pick<DOMRect, "left" | "top" | "width" | "height">,
  width: number,
  height: number,
): Point | null {
  if (width <= 0 || height <= 0 || rect.width <= 0 || rect.height <= 0)
    return null;
  const scale = Math.min(rect.width / width, rect.height / height);
  const x = (clientX - rect.left - (rect.width - width * scale) / 2) / scale;
  const y = (clientY - rect.top - (rect.height - height * scale) / 2) / scale;
  if (!Number.isFinite(x + y) || x < 0 || y < 0 || x > width || y > height)
    return null;
  return [
    Math.min(width - 1, Math.round(x * 10) / 10),
    Math.min(height - 1, Math.round(y * 10) / 10),
  ];
}

export function gateErrors(a: Segment | null, b: Segment | null): string[] {
  if (!a || !b) return ["Draw two endpoints for both Gate A and Gate B."];
  const errors: string[] = [];
  for (const [name, segment] of [
    ["A", a],
    ["B", b],
  ] as const) {
    if (!segment.flat().every(Number.isFinite))
      errors.push(`Gate ${name} needs finite pixel coordinates.`);
    else if (
      Math.hypot(segment[1][0] - segment[0][0], segment[1][1] - segment[0][1]) <
      2
    )
      errors.push(`Gate ${name} needs distinct endpoints.`);
  }
  return errors;
}

export interface ReferenceRow {
  id: number;
  image: Point;
  x: string;
  y: string;
  check: boolean;
}
export type Mode = "points" | "A" | "B";
export type Drag = { row: number } | { gate: "A" | "B"; endpoint: number };
