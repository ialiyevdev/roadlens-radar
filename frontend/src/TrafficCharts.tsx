import { useState } from "react";
import type { TrafficAnalysis, TrafficFlow } from "./trafficTypes";

export function flowChartRows(
  rows: TrafficFlow[],
  mode: "count" | "cumulative" | "rate",
) {
  return rows
    .filter((row) => Number.isFinite(row.start_s))
    .map((row) => ({
      label: `${row.start_s.toFixed(1)}–${row.end_s.toFixed(1)} s`,
      value:
        mode === "count"
          ? row.count
          : mode === "cumulative"
            ? row.cumulative_count
            : row.normalized_crossings_per_minute,
      note: `${row.coverage_seconds.toFixed(1)} s covered · ${row.complete_window ? "complete interval" : "partial interval"} · ${row.session_id}`,
    }))
    .filter(
      (row): row is { label: string; value: number; note: string } =>
        typeof row.value === "number" && Number.isFinite(row.value),
    );
}
export function TrafficBarChart({
  title,
  rows: allRows,
  unit,
}: {
  title: string;
  rows: { label: string; value: number; note?: string }[];
  unit: string;
}) {
  const [focus, setFocus] = useState<number | null>(null);
  const rows = allRows.slice(-60);
  const focused = focus === null ? undefined : rows[focus];
  const maximum = Math.max(1, ...rows.map((r) => r.value));
  return (
    <section className="panel traffic-panel traffic-chart">
      <h3>{title}</h3>
      {allRows.length > 60 && (
        <p className="field-note">
          Showing the latest 60 of {allRows.length} groups. Use source-time
          filters or export the complete retained table.
        </p>
      )}
      {rows.length ? (
        <>
          <div className="traffic-chart-scroll">
            <svg
              viewBox={`0 0 620 ${Math.max(180, rows.length * 32 + 35)}`}
              role="img"
              aria-label={title}
            >
              {rows.map((row, i) => (
                <g
                  key={i}
                  tabIndex={0}
                  role="img"
                  aria-label={`${row.label}: ${row.value} ${unit}`}
                  onMouseEnter={() => setFocus(i)}
                  onFocus={() => setFocus(i)}
                  onMouseLeave={() => setFocus(null)}
                  onBlur={() => setFocus(null)}
                >
                  <text x="8" y={i * 32 + 23}>
                    {row.label.length > 24
                      ? `${row.label.slice(0, 22)}…`
                      : row.label}
                  </text>
                  <rect
                    className={`traffic-bar ${focus === i ? "focused" : ""}`}
                    x="190"
                    y={i * 32 + 8}
                    width={Math.max(
                      row.value > 0 ? 1 : 0,
                      (row.value / maximum) * 345,
                    )}
                    height="20"
                    rx="2"
                  />
                  <text x="547" y={i * 32 + 23}>
                    {Number.isInteger(row.value)
                      ? row.value
                      : row.value.toFixed(1)}
                  </text>
                  <title>
                    {row.label}: {row.value} {unit}
                    {row.note ? ` · ${row.note}` : ""}
                  </title>
                </g>
              ))}
            </svg>
          </div>
          <p className="field-note" aria-live="polite">
            {!focused
              ? `${rows.length} groups · focus or hover a bar for details`
              : `${focused.label} · ${focused.value.toFixed(2)} ${unit} ${focused.note ?? ""}`}
          </p>
        </>
      ) : (
        <p className="traffic-empty">No observations in this filter.</p>
      )}
    </section>
  );
}
export default function TrafficCharts({
  analysis,
}: {
  analysis: TrafficAnalysis;
}) {
  const [mode, setMode] = useState<"count" | "cumulative" | "rate">("count");
  const occupancy = analysis.occupancy
    .map((row) => ({
      label: `${Number(row.timestamp_s).toFixed(1)} s`,
      value:
        typeof row.zone_occupancy === "object" && row.zone_occupancy !== null
          ? Object.values(row.zone_occupancy).reduce<number>(
              (sum, n) => sum + (typeof n === "number" ? n : 0),
              0,
            )
          : Number(row.occupancy ?? row.total_occupancy ?? 0),
      note: `${String(row.session_id ?? "")} · overlapping zones may count a vehicle more than once`,
    }))
    .filter((row) => Number.isFinite(row.value));
  return (
    <>
      <label className="traffic-chart-mode">
        Count trend display
        <select
          value={mode}
          onChange={(e) => setMode(e.target.value as typeof mode)}
        >
          <option value="count">Observed crossings per interval</option>
          <option value="cumulative">Cumulative observed crossings</option>
          <option value="rate">Normalized crossings per minute</option>
        </select>
      </label>
      <div className="traffic-chart-grid">
        <TrafficBarChart
          title="Vehicle count over source time"
          rows={flowChartRows(analysis.flow, mode)}
          unit={mode === "rate" ? "crossings/min" : "crossings"}
        />
        <TrafficBarChart
          title="Directional flow"
          rows={analysis.directions.map((row) => ({
            label: row.direction_label || row.direction,
            value: row.count,
          }))}
          unit="crossings"
        />
        <TrafficBarChart
          title="Vehicle-class distribution"
          rows={analysis.classes.map((row) => ({
            label: row.category,
            value: row.count,
            note: `${(row.fraction * 100).toFixed(1)}% of included counts`,
          }))}
          unit="crossings"
        />
        <TrafficBarChart
          title="Observed speed distribution"
          rows={analysis.speeds.distribution.map((row) => ({
            label: `${row.start_kmh}–${row.end_kmh} km/h`,
            value: row.count,
          }))}
          unit="measurements"
        />
        <TrafficBarChart
          title="Observed occupancy over source time"
          rows={occupancy.slice(-50)}
          unit="tracked vehicles"
        />
      </div>
    </>
  );
}
