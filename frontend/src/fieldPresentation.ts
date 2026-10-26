import { finite } from "./ValidationCharts";

export function qualityEntries(
  value: Record<string, unknown>,
  prefix = "",
): [string, string | number][] {
  return Object.entries(value).flatMap(([key, item]) => {
    const label = `${prefix}${key.replaceAll("_", " ")}`;
    if (finite(item) || typeof item === "string")
      return [[label, item] as [string, string | number]];
    if (typeof item === "boolean")
      return [[label, item ? "yes" : "no"] as [string, string | number]];
    if (item && typeof item === "object" && !Array.isArray(item))
      return qualityEntries(item as Record<string, unknown>, `${label} · `);
    return [];
  });
}
