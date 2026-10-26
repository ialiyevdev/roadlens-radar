import { finite } from "./ValidationCharts";
import type { ValidationRow } from "./validationTypes";

export function formatMetric(value: number | null | undefined, signed = false) {
  return finite(value)
    ? `${signed && value > 0 ? "+" : ""}${value.toFixed(2)}`
    : "—";
}
export function filterValidationRows(
  rows: ValidationRow[],
  status: string,
  search: string,
) {
  const term = search.trim().toLowerCase();
  return rows.filter(
    (row) =>
      (status === "all" ||
        (status === "excluded"
          ? !row.comparison_included
          : row.record.status === status)) &&
      (!term ||
        [
          row.record.measurement_id,
          row.record.vehicle_id,
          row.record.recording_id,
          row.record.observation_id,
        ].some((value) => value?.toLowerCase().includes(term))),
  );
}
