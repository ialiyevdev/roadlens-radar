import { useState } from "react";
import { fieldApi } from "./fieldApi";
import type {
  FieldEvaluation as Evaluation,
  FieldEvaluationRequest,
  FieldPartition,
  FieldSession,
} from "./fieldTypes";
import { downloadResult } from "./validationApi";
import { chartPairs, finite, SpeedCharts } from "./ValidationCharts";
import { formatMetric } from "./validationPresentation";
import { qualityEntries } from "./fieldPresentation";
import type { ValidationRow } from "./validationTypes";

export function SignedErrorDistribution({ rows }: { rows: ValidationRow[] }) {
  const pairs = chartPairs(rows),
    extent = Math.max(1, ...pairs.map((row) => Math.abs(row.error_kmh!)));
  const bins = Array.from({ length: 7 }, () => 0);
  pairs.forEach(
    (row) =>
      bins[
        Math.min(6, Math.floor(((row.error_kmh! + extent) / (2 * extent)) * 7))
      ]++,
  );
  const max = Math.max(1, ...bins);
  return (
    <section className="panel field-panel field-signed-chart">
      <h3>Signed error distribution</h3>
      <p className="panel-description">
        Estimate − reference · {pairs.length} included pairs · seven equal-width
        bins
      </p>
      {pairs.length ? (
        <svg
          viewBox="0 0 630 230"
          role="img"
          aria-label="Signed speed error distribution"
        >
          <line x1="45" y1="185" x2="610" y2="185" className="chart-grid" />
          {bins.map((count, i) => (
            <g key={i}>
              <rect
                className="chart-bar"
                x={50 + i * 80}
                y={185 - (count / max) * 145}
                width="68"
                height={(count / max) * 145}
              >
                <title>
                  {(-extent + (2 * extent * i) / 7).toFixed(2)} to{" "}
                  {(-extent + (2 * extent * (i + 1)) / 7).toFixed(2)} km/h:{" "}
                  {count} comparisons
                </title>
              </rect>
              <text
                x={84 + i * 80}
                y={175 - (count / max) * 145}
                textAnchor="middle"
              >
                {count}
              </text>
            </g>
          ))}
          <text x="45" y="210">
            {(-extent).toFixed(1)} km/h
          </text>
          <text x="327" y="210" textAnchor="middle">
            0
          </text>
          <text x="610" y="210" textAnchor="end">
            +{extent.toFixed(1)} km/h
          </text>
        </svg>
      ) : (
        <p className="field-empty">
          No eligible error pairs in the current filter.
        </p>
      )}
    </section>
  );
}
function Metric({
  label,
  value,
  note,
  unit,
}: {
  label: string;
  value: unknown;
  note?: string;
  unit?: string;
}) {
  return (
    <div className="metric-card">
      <div className="metric-label">{label}</div>
      <div className="metric-value">
        {typeof value === "string"
          ? value
          : finite(value)
            ? formatMetric(value)
            : "—"}
        <span>{unit}</span>
      </div>
      {note && <p>{note}</p>}
    </div>
  );
}
export function FieldEvaluationResults({ report }: { report: Evaluation }) {
  const [status, setStatus] = useState("all"),
    [direction, setDirection] = useState("all"),
    [selectedSession, setSelectedSession] = useState("all"),
    [search, setSearch] = useState("");
  const [minimumSpeed, setMinimumSpeed] = useState(""),
    [maximumSpeed, setMaximumSpeed] = useState("");
  const rows = report.validation.rows.filter(
    (row, index) =>
      (status === "all" || row.record.status === status) &&
      (direction === "all" || row.record.direction === direction) &&
      (selectedSession === "all" ||
        report.row_metadata[index]?.session_id === selectedSession) &&
      (!search ||
        `${row.record.measurement_id} ${row.record.observation_id} ${row.exclusion_reasons.join(" ")}`
          .toLowerCase()
          .includes(search.toLowerCase())) &&
      (minimumSpeed === "" ||
        (finite(row.record.reference_speed_kmh) &&
          row.record.reference_speed_kmh >= Number(minimumSpeed))) &&
      (maximumSpeed === "" ||
        (finite(row.record.reference_speed_kmh) &&
          row.record.reference_speed_kmh <= Number(maximumSpeed))),
  );
  const summary = report.validation.summary;
  return (
    <div className="field-stack">
      <div
        className={`validation-provenance-banner ${report.provenance === "synthetic" ? "synthetic" : "real_world"}`}
      >
        <span className="validation-provenance">
          {report.provenance.replaceAll("_", " ").toUpperCase()}
        </span>
        <div>
          <strong>
            {report.real_world_reference_available
              ? "Independent references matched; precision depends on supplied evidence"
              : "No real-world reference data available"}
          </strong>
          <p>
            {report.session_count} sessions · {report.validation.compared_count}{" "}
            eligible comparisons ·{" "}
            {report.partition || "all selected partitions"}.{" "}
            {report.provenance === "synthetic" &&
              "Synthetic software evidence does not establish roadway accuracy."}
          </p>
        </div>
      </div>
      <div className="validation-metrics">
        <Metric
          label="Eligible comparisons"
          value={String(summary.n)}
          note={`${report.validation.total_records} retained measurements`}
        />
        <Metric
          label="Mean absolute error"
          value={summary.mae_kmh}
          unit="km/h"
        />
        <Metric
          label="Root mean squared error"
          value={summary.rmse_kmh}
          unit="km/h"
        />
        <Metric
          label="Mean signed error"
          value={summary.bias_kmh}
          unit="km/h"
        />
        <Metric
          label="Median absolute error"
          value={summary.median_absolute_error_kmh}
          unit="km/h"
        />
        <Metric
          label="90th percentile absolute error"
          value={summary.p90_absolute_error_kmh}
          unit="km/h"
        />
        <Metric
          label="Valid measurements"
          value={report.counts.valid_measurement_percent}
          unit="%"
        />
        <Metric
          label="Rejection rate"
          value={report.counts.rejection_percent}
          unit="%"
        />
        <Metric
          label="Non-completion rate"
          value={report.counts.noncompletion_percent}
          unit="%"
        />
      </div>
      {!summary.sufficient_sample && (
        <p className="studio-notice" role="status">
          Insufficient comparisons for aggregate error statistics. N ={" "}
          {summary.n}; at least{" "}
          {report.validation.options.minimum_group_samples} required by the
          analysis settings.
        </p>
      )}
      <p className="field-note">
        Rates use {report.counts.denominator}{" "}
        {report.counts.complete_event_ledger
          ? "expected events from the supplied external ledger"
          : "retained application events; a complete crossing ledger was not supplied"}
        . {report.counts.missing_reference} missing references;{" "}
        {report.counts.unmatched_reference_events} unmatched reference events;{" "}
        {report.counts.excluded_measurements} excluded measurements.
      </p>
      <section className="panel field-panel">
        <h2>Filter charts and measurements</h2>
        <div className="field-filter-grid">
          <label>
            Measurement status
            <select value={status} onChange={(e) => setStatus(e.target.value)}>
              <option value="all">All statuses</option>
              {["valid", "approximate", "rejected"].map((v) => (
                <option key={v}>{v}</option>
              ))}
            </select>
          </label>
          <label>
            Travel direction
            <select
              value={direction}
              onChange={(e) => setDirection(e.target.value)}
            >
              <option value="all">All directions</option>
              <option value="A_to_B">A → B</option>
              <option value="B_to_A">B → A</option>
              <option value="unknown">Unknown</option>
            </select>
          </label>
          <label>
            Result session
            <select
              value={selectedSession}
              onChange={(e) => setSelectedSession(e.target.value)}
            >
              <option value="all">All evaluated sessions</option>
              {report.sessions?.map((session) => (
                <option key={session.id} value={session.id}>
                  {session.name}
                </option>
              ))}
            </select>
          </label>
          <label>
            Find event or reason
            <input value={search} onChange={(e) => setSearch(e.target.value)} />
          </label>
          <label>
            Minimum reference speed · km/h
            <input
              type="number"
              min={0}
              value={minimumSpeed}
              onChange={(e) => setMinimumSpeed(e.target.value)}
            />
          </label>
          <label>
            Maximum reference speed · km/h
            <input
              type="number"
              min={0}
              value={maximumSpeed}
              onChange={(e) => setMaximumSpeed(e.target.value)}
            />
          </label>
        </div>
        <p className="field-note">
          {rows.length} measurements displayed. Summary statistics above
          describe the evaluated cohort; filters apply to charts and details.
        </p>
      </section>
      <SpeedCharts rows={rows} />
      <SignedErrorDistribution rows={rows} />
      <section className="panel field-panel">
        <h2>Comparison groups</h2>
        <p className="panel-description">
          Groups require N ≥ {report.validation.options.minimum_group_samples}.
          Counts below that threshold remain visible without aggregate errors.
        </p>
        <div className="table-scroll">
          <table aria-label="Field evaluation comparison groups">
            <thead>
              <tr>
                <th>Dimension</th>
                <th>Group</th>
                <th>N</th>
                <th>MAE · km/h</th>
                <th>RMSE · km/h</th>
                <th>Signed error · km/h</th>
              </tr>
            </thead>
            <tbody>
              {report.group_sample_counts.map((group) => {
                const metrics = report.groups?.find(
                  (item) =>
                    item.dimension === group.dimension &&
                    item.value === group.value,
                )?.metrics;
                return (
                  <tr key={`${group.dimension}:${group.value}`}>
                    <td>{group.dimension.replaceAll("_", " ")}</td>
                    <td>{group.value}</td>
                    <td>{group.n}</td>
                    <td>{formatMetric(metrics?.mae_kmh)}</td>
                    <td>{formatMetric(metrics?.rmse_kmh)}</td>
                    <td>{formatMetric(metrics?.bias_kmh)}</td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        </div>
        {!report.group_sample_counts.length && (
          <p className="field-empty">No groups available.</p>
        )}
      </section>
      <section className="panel field-panel">
        <h2>Baseline and improved measurements</h2>
        <p className="panel-description">{report.pipeline_comparison.note}</p>
        {report.pipeline_comparison.paired_n ? (
          <div className="table-scroll">
            <table aria-label="Paired pipeline comparison">
              <thead>
                <tr>
                  <th>Variant</th>
                  <th>Matched pairs</th>
                  <th>MAE · km/h</th>
                  <th>RMSE · km/h</th>
                  <th>Signed error · km/h</th>
                </tr>
              </thead>
              <tbody>
                {(["baseline", "improved"] as const).map((variant) => (
                  <tr key={variant}>
                    <td>{variant}</td>
                    <td>{report.pipeline_comparison.paired_n}</td>
                    <td>
                      {formatMetric(
                        report.pipeline_comparison[variant].mae_kmh,
                      )}
                    </td>
                    <td>
                      {formatMetric(
                        report.pipeline_comparison[variant].rmse_kmh,
                      )}
                    </td>
                    <td>
                      {formatMetric(
                        report.pipeline_comparison[variant].bias_kmh,
                      )}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        ) : (
          <p className="field-empty">
            No saved baseline and improved measurements for the same reference
            events.
          </p>
        )}
      </section>
      <section className="panel field-panel">
        <h2>Tracking and timestamp evidence</h2>
        <p className="panel-description">
          Ground-truth identities stay separate from predicted IDs. Metrics are
          available only for annotated, matched observations.
        </p>
        <div className="field-evidence-grid">
          {report.tracking.map((item) => (
            <div key={item.session_id}>
              <h3>
                {report.sessions?.find((s) => s.id === item.session_id)?.name ||
                  item.session_id}
              </h3>
              <dl className="field-quality-grid">
                {Object.entries(item.metrics)
                  .filter(
                    ([, value]) => finite(value) || typeof value === "string",
                  )
                  .map(([key, value]) => (
                    <div key={key}>
                      <dt>{key.replaceAll("_", " ")}</dt>
                      <dd>
                        {finite(value) ? formatMetric(value) : String(value)}
                      </dd>
                    </div>
                  ))}
              </dl>
            </div>
          ))}
        </div>
        {!report.tracking.length && (
          <p className="field-empty">
            No annotated tracking metrics available.
          </p>
        )}
        {report.timing.map((item) => (
          <details key={item.session_id}>
            <summary>
              Timing evidence ·{" "}
              {report.sessions?.find((s) => s.id === item.session_id)?.name ||
                item.session_id}
            </summary>
            <p>{item.source_timebase || "Timebase not documented"}</p>
            <dl className="field-quality-grid">
              {qualityEntries(item.statistics).map(([key, value]) => (
                <div key={key}>
                  <dt>{key}</dt>
                  <dd>{finite(value) ? formatMetric(value) : String(value)}</dd>
                </div>
              ))}
            </dl>
            <p>
              Synchronization: {item.synchronization.status}; bound{" "}
              {formatMetric(item.synchronization.uncertainty_bound_s)} s.
            </p>
          </details>
        ))}
      </section>
      <section className="panel field-panel">
        <h2>Measurement details</h2>
        <div className="table-scroll">
          <table aria-label="Field validation measurements">
            <thead>
              <tr>
                <th>Session / event</th>
                <th>Estimate · km/h</th>
                <th>Reference · km/h</th>
                <th>Signed error · km/h</th>
                <th>Absolute error · km/h</th>
                <th>Status</th>
                <th>Reasons and evidence</th>
              </tr>
            </thead>
            <tbody>
              {rows.map((row) => {
                const meta =
                  report.row_metadata[report.validation.rows.indexOf(row)];
                return (
                  <tr
                    key={`${row.record.recording_id}:${row.record.measurement_id}`}
                  >
                    <td>
                      {meta?.session_name}
                      <small>{row.record.observation_id}</small>
                      <small>{row.record.measurement_id}</small>
                    </td>
                    <td>{formatMetric(row.record.estimated_speed_kmh)}</td>
                    <td>{formatMetric(row.record.reference_speed_kmh)}</td>
                    <td>{formatMetric(row.error_kmh, true)}</td>
                    <td>{formatMetric(row.absolute_error_kmh)}</td>
                    <td>
                      <span
                        className={`measurement-status ${row.record.status}`}
                      >
                        {row.record.status}
                      </span>
                    </td>
                    <td>
                      {row.exclusion_reasons.join("; ") ||
                        "Included comparison"}
                      {meta?.original_reasons.length > 0 && (
                        <small>{meta.original_reasons.join("; ")}</small>
                      )}
                      {meta?.measurement_diagnostics && (
                        <details>
                          <summary>Measurement quality evidence</summary>
                          <dl className="field-quality-grid">
                            {Object.entries(meta.measurement_diagnostics)
                              .filter(
                                ([, value]) =>
                                  finite(value) || typeof value === "string",
                              )
                              .map(([key, value]) => (
                                <div key={key}>
                                  <dt>{key.replaceAll("_", " ")}</dt>
                                  <dd>
                                    {finite(value)
                                      ? formatMetric(value)
                                      : String(value)}
                                  </dd>
                                </div>
                              ))}
                          </dl>
                        </details>
                      )}
                    </td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        </div>
        {!rows.length && (
          <p className="field-empty">
            No measurements match the current filters.
          </p>
        )}
      </section>
      <section className="panel field-panel">
        <h2>Exclusions and limits</h2>
        <dl className="field-quality-grid">
          {Object.entries(report.exclusions).map(([reason, count]) => (
            <div key={reason}>
              <dt>{reason.replaceAll("_", " ")}</dt>
              <dd>{count}</dd>
            </div>
          ))}
        </dl>
        {report.limitations?.map((item) => (
          <p key={item} className="field-note">
            {item}
          </p>
        ))}
        <p className="field-note">
          Offline evaluation cost:{" "}
          {formatMetric(report.performance.evaluation_ms)} ms for this request.
        </p>
      </section>
    </div>
  );
}
export default function FieldEvaluation({
  sessions,
  connected,
  onReport,
}: {
  sessions: FieldSession[];
  connected: boolean;
  onReport?: (report: Evaluation) => void;
}) {
  const [selected, setSelected] = useState<string[]>([]),
    [partition, setPartition] = useState<FieldPartition | "all">("held_out"),
    [variant, setVariant] =
      useState<FieldEvaluationRequest["variant"]>("original"),
    [minimum, setMinimum] = useState("3"),
    [description, setDescription] = useState("");
  const [report, setReport] = useState<Evaluation | null>(null),
    [evaluatedRequest, setEvaluatedRequest] =
      useState<FieldEvaluationRequest | null>(null),
    [busy, setBusy] = useState(false),
    [error, setError] = useState<string | null>(null);
  const request: FieldEvaluationRequest = {
    session_ids: selected.filter((id) =>
      sessions.some((session) => session.id === id),
    ),
    partition: partition === "all" ? null : partition,
    variant,
    options: {
      tolerance_bands_kmh: [3, 5],
      minimum_group_samples: Number(minimum),
    },
    description,
  };
  const valid =
    request.session_ids.length > 0 &&
    minimum !== "" &&
    Number.isInteger(Number(minimum)) &&
    Number(minimum) >= 3 &&
    Number(minimum) <= 10000;
  async function evaluate() {
    setBusy(true);
    setError(null);
    try {
      const value = await fieldApi.evaluate(request);
      setReport(value);
      setEvaluatedRequest(request);
      onReport?.(value);
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : "Evaluation failed.");
    } finally {
      setBusy(false);
    }
  }
  async function exportReport(format: "json" | "csv" | "html") {
    if (!evaluatedRequest) return;
    setBusy(true);
    setError(null);
    try {
      downloadResult(
        await fieldApi.exportEvaluation(evaluatedRequest, format),
        `roadlens-field-validation.${format}`,
      );
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : "Export failed.");
    } finally {
      setBusy(false);
    }
  }
  return (
    <div className="field-stack">
      <section className="panel field-panel">
        <h2>Held-out field evaluation</h2>
        <p className="panel-description">
          Select complete sessions with the same evidence provenance.
          Development and tuning sessions remain separate from held-out
          collection conditions.
        </p>
        {error && (
          <p className="inline-error" role="alert">
            {error}
          </p>
        )}
        <div
          className="field-session-checklist"
          role="group"
          aria-label="Evaluation sessions"
        >
          {sessions.map((session) => (
            <label className="field-check" key={session.id}>
              <input
                type="checkbox"
                checked={selected.includes(session.id)}
                disabled={busy}
                onChange={(e) =>
                  setSelected(
                    e.target.checked
                      ? [...selected, session.id]
                      : selected.filter((id) => id !== session.id),
                  )
                }
              />
              <span>
                {session.name}
                <small>
                  {session.partition.replaceAll("_", " ")} ·{" "}
                  {session.provenance.replaceAll("_", " ")}
                </small>
              </span>
            </label>
          ))}
          {!sessions.length && (
            <p className="field-empty">
              Create or import a field session before evaluation.
            </p>
          )}
        </div>
        <div className="field-form-grid">
          <label>
            Evaluation partition
            <select
              value={partition}
              disabled={busy}
              onChange={(e) => setPartition(e.target.value as typeof partition)}
            >
              <option value="held_out">Held-out evaluation</option>
              <option value="development">Development</option>
              <option value="calibration">Calibration / tuning</option>
              <option value="all">
                All selected partitions · descriptive only
              </option>
            </select>
          </label>
          <label>
            Measurement variant
            <select
              value={variant}
              disabled={busy}
              onChange={(e) => setVariant(e.target.value as typeof variant)}
            >
              <option value="original">Original</option>
              <option value="baseline">Baseline</option>
              <option value="improved">Improved</option>
            </select>
          </label>
          <label>
            Minimum subgroup sample size
            <input
              type="number"
              min={3}
              max={10000}
              step={1}
              disabled={busy}
              value={minimum}
              onChange={(e) => setMinimum(e.target.value)}
            />
          </label>
          <label>
            Evaluation description
            <input
              value={description}
              disabled={busy}
              onChange={(e) => setDescription(e.target.value)}
            />
          </label>
        </div>
        <p className="field-note">
          Tolerance analyses use ±3 and ±5 km/h. Whole recordings, overlapping
          segments, collection IDs, and declared near duplicates cannot leak
          across dataset partitions.
        </p>
        <div className="field-actions">
          <button
            className="button button-primary"
            disabled={!connected || busy || !valid}
            onClick={() => void evaluate()}
          >
            Evaluate field sessions
          </button>
          {(["json", "csv", "html"] as const).map((format) => (
            <button
              key={format}
              className="button button-secondary compact"
              disabled={!connected || busy || !evaluatedRequest}
              onClick={() => void exportReport(format)}
            >
              Export field report {format.toUpperCase()}
            </button>
          ))}
          {busy && <span role="status">Preparing field evaluation…</span>}
        </div>
      </section>
      {report ? (
        <FieldEvaluationResults
          key={JSON.stringify(evaluatedRequest)}
          report={report}
        />
      ) : (
        <div className="panel field-panel field-empty">
          <h2>No field evaluation yet</h2>
          <p>
            Import and align independent references, confirm event
            correspondence, and choose a partition. Synthetic examples exercise
            this workflow without providing real-road accuracy evidence.
          </p>
        </div>
      )}
    </div>
  );
}
