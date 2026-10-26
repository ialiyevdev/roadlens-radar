import { useState } from "react";
import { ContinuityChart } from "./ValidationCharts";
import type { TrackingReport } from "./validationTypes";

export default function TrackingBenchmarkResults({
  report,
}: {
  report: TrackingReport;
}) {
  const [scenario, setScenario] = useState("0");
  const baseline = report.baseline.scenarios[Number(scenario)];
  const improved = report.improved.scenarios[Number(scenario)];
  const comparisons: {
    label: string;
    baseline: number;
    improved: number;
    timing?: boolean;
  }[] = [
    {
      label: "Annotated identity switches",
      baseline: report.baseline.id_switches,
      improved: report.improved.id_switches,
    },
    {
      label: "Annotated track fragments",
      baseline: report.baseline.fragments,
      improved: report.improved.fragments,
    },
    {
      label: "Matched / ground-truth observations",
      baseline: report.baseline.matched_observations,
      improved: report.improved.matched_observations,
    },
    {
      label: "Missed observations",
      baseline: report.baseline.missed_observations,
      improved: report.improved.missed_observations,
    },
    {
      label: "Created tracks",
      baseline: report.baseline.created_tracks,
      improved: report.improved.created_tracks,
    },
    {
      label: "Confirmed tracks",
      baseline: report.baseline.confirmed_tracks,
      improved: report.improved.confirmed_tracks,
    },
    {
      label: "Mean tracking update · ms",
      baseline: report.baseline.mean_update_ms,
      improved: report.improved.mean_update_ms,
      timing: true,
    },
    {
      label: "P95 tracking update · ms",
      baseline: report.baseline.p95_update_ms,
      improved: report.improved.p95_update_ms,
      timing: true,
    },
  ];
  return (
    <>
      <div className="validation-benchmark-meta">
        <span className="validation-provenance">
          SYNTHETIC · ANNOTATED TRAJECTORIES
        </span>
        <span>
          {report.baseline.frames} frames per tracker ·{" "}
          {report.baseline.ground_truth_observations} ground-truth observations
        </span>
      </div>
      <p className="panel-description">
        Same deterministic detections and source timestamps for both trackers.
        Detection inference is excluded. Timings are local measurements, not a
        guaranteed performance improvement.
      </p>
      <div className="validation-tracking-layout">
        <div className="table-scroll">
          <table aria-label="Tracking benchmark comparison">
            <thead>
              <tr>
                <th>Metric</th>
                <th>Phase 2 baseline</th>
                <th>Improved</th>
              </tr>
            </thead>
            <tbody>
              {comparisons.map((row) => (
                <tr key={row.label}>
                  <td>{row.label}</td>
                  <td className="mono">
                    {row.timing ? row.baseline.toFixed(4) : row.baseline}
                  </td>
                  <td className="mono">
                    {row.timing ? row.improved.toFixed(4) : row.improved}
                  </td>
                </tr>
              ))}
              <tr>
                <td>Potential ID-switch suspicions</td>
                <td>Unavailable</td>
                <td className="mono">
                  {report.improved.potential_id_switches}
                </td>
              </tr>
              <tr>
                <td>Fragmentation suspicions</td>
                <td>Unavailable</td>
                <td className="mono">
                  {report.improved.fragmentation_suspicions}
                </td>
              </tr>
            </tbody>
          </table>
        </div>
        <div className="validation-continuity-panel">
          <label>
            Tracking scenario
            <select
              value={scenario}
              onChange={(event) => setScenario(event.target.value)}
            >
              {report.baseline.scenarios.map((item, i) => (
                <option value={i} key={item.name}>
                  {item.name.replaceAll("_", " ")}
                </option>
              ))}
            </select>
          </label>
          {baseline && improved && (
            <>
              <p className="panel-description">{baseline.description}</p>
              <ContinuityChart baseline={baseline} improved={improved} />
              <p className="validation-scenario-stats">
                Identity switches: {baseline.id_switches} →{" "}
                {improved.id_switches} · Fragments: {baseline.fragments} →{" "}
                {improved.fragments}
              </p>
            </>
          )}
        </div>
      </div>
      <p className="validation-hardware">
        Measured on {report.hardware.cpu || "CPU not identified"} ·{" "}
        {report.hardware.logical_cpus} logical CPUs · {report.hardware.os} ·
        Python {report.hardware.python}. Run: {report.generated_at_utc}
      </p>
      <details className="validation-methodology">
        <summary>Tracking benchmark definitions</summary>
        <dl>
          {Object.entries(report.methodology).map(([key, value]) => (
            <div key={key}>
              <dt>{key.replaceAll("_", " ")}</dt>
              <dd>{Array.isArray(value) ? value.join(" ") : value}</dd>
            </div>
          ))}
        </dl>
        <p>
          Live association suspicions are heuristic diagnostics. Only
          comparisons against these annotated synthetic identities produce
          verified benchmark identity-switch counts.
        </p>
      </details>
    </>
  );
}
