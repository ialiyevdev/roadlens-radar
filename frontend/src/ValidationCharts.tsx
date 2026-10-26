import { useId } from "react";
import type { TrackingScenario, ValidationRow } from "./validationTypes";

const W = 420,
  H = 260,
  L = 53,
  R = 22,
  T = 20,
  B = 51;
const plotW = W - L - R,
  plotH = H - T - B;
export function finite(value: unknown): value is number {
  return typeof value === "number" && Number.isFinite(value);
}
export function chartPairs(rows: ValidationRow[]) {
  return rows.filter(
    (row) =>
      row.comparison_included &&
      finite(row.record.reference_speed_kmh) &&
      finite(row.record.estimated_speed_kmh) &&
      finite(row.error_kmh) &&
      finite(row.absolute_error_kmh),
  );
}
function ticks(max: number) {
  return Array.from({ length: 5 }, (_, i) => (max * i) / 4);
}
function label(value: number) {
  return Number.isInteger(value) ? String(value) : value.toFixed(1);
}
function Axes({
  xMax,
  yMin = 0,
  yMax,
  xLabel,
  yLabel,
}: {
  xMax: number;
  yMin?: number;
  yMax: number;
  xLabel: string;
  yLabel: string;
}) {
  return (
    <>
      {ticks(xMax).map((value, i) => (
        <g key={`x${i}`}>
          <line
            className="chart-grid"
            x1={L + (plotW * i) / 4}
            y1={T}
            x2={L + (plotW * i) / 4}
            y2={T + plotH}
          />
          <text x={L + (plotW * i) / 4} y={H - B + 20} textAnchor="middle">
            {label(value)}
          </text>
        </g>
      ))}
      {ticks(yMax - yMin).map((value, i) => (
        <g key={`y${i}`}>
          <line
            className="chart-grid"
            x1={L}
            y1={T + plotH - (plotH * i) / 4}
            x2={W - R}
            y2={T + plotH - (plotH * i) / 4}
          />
          <text x={L - 9} y={T + plotH - (plotH * i) / 4 + 3} textAnchor="end">
            {label(value + yMin)}
          </text>
        </g>
      ))}
      <text
        x={L + plotW / 2}
        y={H - 8}
        textAnchor="middle"
        className="chart-axis-title"
      >
        {xLabel}
      </text>
      <text
        transform={`translate(13 ${T + plotH / 2}) rotate(-90)`}
        textAnchor="middle"
        className="chart-axis-title"
      >
        {yLabel}
      </text>
    </>
  );
}
function ChartEmpty() {
  return (
    <div className="validation-chart-empty">
      No finite, included reference pairs to plot.
    </div>
  );
}
export function SpeedCharts({ rows }: { rows: ValidationRow[] }) {
  const id = useId();
  const pairs = chartPairs(rows);
  const speeds = pairs.flatMap((row) => [
    row.record.reference_speed_kmh!,
    row.record.estimated_speed_kmh!,
  ]);
  const maxSpeed = Math.max(10, ...speeds) * 1.08;
  const maxError =
    Math.max(1, ...pairs.map((row) => Math.abs(row.error_kmh!))) * 1.15;
  const maxAbsolute = Math.max(
    1,
    ...pairs.map((row) => row.absolute_error_kmh!),
  );
  const binWidth = maxAbsolute / 5;
  const bins = Array.from({ length: 5 }, () => 0);
  pairs.forEach(
    (row) =>
      bins[Math.min(4, Math.floor(row.absolute_error_kmh! / binWidth))]++,
  );
  const maxCount = Math.ceil(Math.max(1, ...bins) / 4) * 4;
  const cx = (value: number) => L + (value / maxSpeed) * plotW;
  const cy = (value: number) => T + plotH - (value / maxSpeed) * plotH;
  return (
    <div className="validation-charts">
      <section className="panel validation-chart">
        <h3>Estimated vs reference speed</h3>
        <p>{pairs.length} included pairs · km/h</p>
        {pairs.length ? (
          <svg
            viewBox={`0 0 ${W} ${H}`}
            role="img"
            aria-labelledby={`${id}-scatter`}
          >
            <title id={`${id}-scatter`}>
              Estimated versus reference speed, with ideal estimation line
            </title>
            <Axes
              xMax={maxSpeed}
              yMax={maxSpeed}
              xLabel="Reference speed · km/h"
              yLabel="Estimated speed · km/h"
            />
            <line
              className="chart-ideal"
              x1={L}
              y1={T + plotH}
              x2={W - R}
              y2={T}
            />
            {pairs.map((row, i) => (
              <circle
                key={i}
                className={`chart-point ${row.record.status}`}
                cx={cx(row.record.reference_speed_kmh!)}
                cy={cy(row.record.estimated_speed_kmh!)}
                r="4"
              >
                <title>
                  {row.record.measurement_id}: reference{" "}
                  {row.record.reference_speed_kmh}, estimate{" "}
                  {row.record.estimated_speed_kmh} km/h
                </title>
              </circle>
            ))}
          </svg>
        ) : (
          <ChartEmpty />
        )}
        <div className="chart-legend">
          <span className="ideal-key" /> Ideal estimate{" "}
          <span className="point-key" /> Valid{" "}
          <span className="point-key approximate" /> Approximate
        </div>
      </section>
      <section className="panel validation-chart">
        <h3>Absolute error distribution</h3>
        <p>Five equal-width bins · {pairs.length} comparisons</p>
        {pairs.length ? (
          <svg
            viewBox={`0 0 ${W} ${H}`}
            role="img"
            aria-labelledby={`${id}-distribution`}
          >
            <title id={`${id}-distribution`}>
              Absolute error distribution for included comparisons
            </title>
            <Axes
              xMax={maxAbsolute}
              yMax={maxCount}
              xLabel="Absolute error · km/h"
              yLabel="Comparisons"
            />
            {bins.map((count, i) => (
              <rect
                key={i}
                className="chart-bar"
                x={L + (plotW * i) / 5 + 3}
                y={T + plotH - (count / maxCount) * plotH}
                width={plotW / 5 - 6}
                height={(count / maxCount) * plotH}
              >
                <title>
                  {(i * binWidth).toFixed(2)}–{((i + 1) * binWidth).toFixed(2)}{" "}
                  km/h: {count} comparisons
                </title>
              </rect>
            ))}
          </svg>
        ) : (
          <ChartEmpty />
        )}
        <div className="chart-legend">
          Final bin includes its upper boundary.
        </div>
      </section>
      <section className="panel validation-chart">
        <h3>Error vs reference speed</h3>
        <p>Signed error = estimate − reference</p>
        {pairs.length ? (
          <svg
            viewBox={`0 0 ${W} ${H}`}
            role="img"
            aria-labelledby={`${id}-errors`}
          >
            <title id={`${id}-errors`}>
              Signed error versus reference speed, with zero error line
            </title>
            <Axes
              xMax={maxSpeed}
              yMin={-maxError}
              yMax={maxError}
              xLabel="Reference speed · km/h"
              yLabel="Signed error · km/h"
            />
            <line
              className="chart-ideal"
              x1={L}
              y1={T + plotH / 2}
              x2={W - R}
              y2={T + plotH / 2}
            />
            {pairs.map((row, i) => (
              <circle
                key={i}
                className={`chart-point ${row.record.status}`}
                cx={cx(row.record.reference_speed_kmh!)}
                cy={T + plotH / 2 - (row.error_kmh! / (2 * maxError)) * plotH}
                r="4"
              >
                <title>
                  {row.record.measurement_id}: signed error {row.error_kmh} km/h
                </title>
              </circle>
            ))}
          </svg>
        ) : (
          <ChartEmpty />
        )}
        <div className="chart-legend">
          Individual pairs shown; small samples do not establish accuracy.
        </div>
      </section>
    </div>
  );
}
export function ContinuityChart({
  baseline,
  improved,
}: {
  baseline: TrackingScenario;
  improved: TrackingScenario;
}) {
  const id = useId();
  const a = baseline.continuity.filter(
    (point) => finite(point.timestamp_s) && finite(point.active_tracks),
  );
  const b = improved.continuity.filter(
    (point) => finite(point.timestamp_s) && finite(point.active_tracks),
  );
  const all = [...a, ...b];
  const maxTime = Math.max(1, ...all.map((point) => point.timestamp_s));
  const maxCount = Math.max(
    1,
    ...all.flatMap((point) => [point.ground_truth_count, point.active_tracks]),
  );
  const path = (points: typeof a, groundTruth = false) =>
    points
      .map(
        (point, i) =>
          `${i ? "L" : "M"}${L + (point.timestamp_s / maxTime) * plotW},${T + plotH - ((groundTruth ? point.ground_truth_count : point.active_tracks) / maxCount) * plotH}`,
      )
      .join(" ");
  return (
    <div className="validation-continuity validation-chart">
      <h3>Tracking continuity · active track count</h3>
      <p>
        Counts through source time; identity switches and fragments appear in
        the comparison table.
      </p>
      {all.length ? (
        <svg
          viewBox={`0 0 ${W} ${H}`}
          role="img"
          aria-labelledby={`${id}-continuity`}
        >
          <title id={`${id}-continuity`}>
            Ground truth and baseline versus improved active track counts
          </title>
          <Axes
            xMax={maxTime}
            yMax={maxCount}
            xLabel="Source timestamp · s"
            yLabel="Active tracks"
          />
          <path className="chart-ideal" d={path(a, true)} fill="none" />
          <path className="chart-baseline" d={path(a)} fill="none" />
          <path className="chart-improved" d={path(b)} fill="none" />
        </svg>
      ) : (
        <div className="validation-chart-empty">
          No continuity samples in this scenario.
        </div>
      )}
      <div className="chart-legend">
        <span className="ideal-key" /> Ground truth{" "}
        <span className="line-key baseline" /> Baseline{" "}
        <span className="line-key" /> Improved
      </div>
    </div>
  );
}
