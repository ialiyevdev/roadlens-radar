import { useEffect, useRef, useState } from "react";
import { fieldApi } from "./fieldApi";
import { trafficApi } from "./trafficApi";
import { qualityEntries } from "./fieldPresentation";
import type { FieldSession } from "./fieldTypes";
import type { TrafficSessionSummary } from "./trafficTypes";

interface EvaluationRow {
  outcome: string;
  truth: Record<string, unknown> | null;
  prediction: Record<string, unknown> | null;
  class_correct?: boolean;
  direction_correct?: boolean;
  time_error_s?: number;
}

export default function TrafficEvaluation({
  connected,
  sessions,
  visible = true,
}: {
  connected: boolean;
  sessions: TrafficSessionSummary[];
  visible?: boolean;
}) {
  const [fields, setFields] = useState<FieldSession[]>([]);
  const [traffic, setTraffic] = useState("");
  const [field, setField] = useState("");
  const [tolerance, setTolerance] = useState(0.5);
  const [partition, setPartition] = useState("held_out");
  const [report, setReport] = useState<Record<string, unknown> | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const generation = useRef(0);
  useEffect(() => {
    if (!connected || !visible) return;
    let active = true;
    generation.current++;
    setReport(null);
    fieldApi
      .list()
      .then((value) => {
        if (active) setFields(value.sessions);
      })
      .catch((e) => {
        if (active) setError(String(e));
      });
    return () => {
      active = false;
    };
  }, [connected, visible]);
  function invalidate() {
    generation.current++;
    setReport(null);
  }
  async function evaluate() {
    const request = ++generation.current;
    setBusy(true);
    setError("");
    try {
      const result = await trafficApi.evaluate({
        traffic_session_id: traffic,
        field_session_id: field,
        maximum_time_error_s: tolerance,
        partition,
      });
      if (generation.current === request) setReport(result);
    } catch (e) {
      if (generation.current === request)
        setError(e instanceof Error ? e.message : String(e));
    } finally {
      setBusy(false);
    }
  }
  const selected = fields.find((f) => f.id === field);
  const rows = Array.isArray(report?.rows)
    ? (report.rows as EvaluationRow[])
    : [];
  return (
    <section className="panel traffic-panel">
      <h2>Evaluate against manual vehicle annotations</h2>
      <p className="panel-description">
        Match an archived traffic observation to the same field recording.
        Reviewed annotation trajectories establish manual crossings; temporary
        predicted track IDs remain separate from ground truth.
      </p>
      <p className="traffic-warning">
        No independent real-world accuracy result is available until matching
        held-out footage, reviewed labels and independent references have been
        collected. Synthetic fixtures exercise the software only.
      </p>
      {error && (
        <p role="alert" className="inline-error">
          {error}
        </p>
      )}
      <div className="traffic-filter-grid">
        <label>
          Predicted traffic session
          <select
            value={traffic}
            disabled={busy}
            onChange={(e) => {
              setTraffic(e.target.value);
              invalidate();
            }}
          >
            <option value="">Choose archived observation</option>
            {sessions.map((s) => (
              <option key={s.id} value={s.id}>
                {s.name || s.session_id || s.id} ·{" "}
                {s.provenance || "recorded_unverified"}
              </option>
            ))}
          </select>
        </label>
        <label>
          Manual field annotations
          <select
            value={field}
            disabled={busy}
            onChange={(e) => {
              setField(e.target.value);
              invalidate();
            }}
          >
            <option value="">Choose matching field session</option>
            {fields.map((f) => (
              <option key={f.id} value={f.id}>
                {f.name} · {f.partition} · {f.provenance}
              </option>
            ))}
          </select>
        </label>
        <label>
          Evaluation partition
          <select
            value={partition}
            disabled={busy}
            onChange={(e) => {
              setPartition(e.target.value);
              invalidate();
            }}
          >
            <option value="held_out">Held out · final evaluation</option>
            <option value="development">Development · exploratory</option>
            <option value="calibration">Calibration / tuning</option>
          </select>
        </label>
        <label>
          Crossing alignment tolerance · s
          <input
            type="number"
            min="0.01"
            max="5"
            step=".05"
            value={tolerance}
            disabled={busy}
            onChange={(e) => {
              setTolerance(Number(e.target.value));
              invalidate();
            }}
          />
        </label>
      </div>
      {selected && (
        <p className="field-note">
          Evidence: {selected.provenance} · partition: {selected.partition}.
          Source identity and split leakage are checked by the backend.
        </p>
      )}
      <button
        className="button button-primary"
        disabled={!connected || !traffic || !field || busy}
        onClick={() => void evaluate()}
      >
        {busy ? "Evaluating…" : "Evaluate traffic predictions"}
      </button>
      {report && (
        <div className="traffic-evaluation-result">
          <h3>Traffic evaluation results</h3>
          <dl className="traffic-quality">
            {qualityEntries(report).map(([label, value]) => (
              <div key={label}>
                <dt>{label}</dt>
                <dd>
                  {typeof value === "number"
                    ? Number.isInteger(value)
                      ? value
                      : value.toFixed(4)
                    : value}
                </dd>
              </div>
            ))}
          </dl>
          {rows.length > 0 && (
            <div className="traffic-table-wrap">
              <table aria-label="Predicted versus manual crossings">
                <thead>
                  <tr>
                    {[
                      "Outcome",
                      "Manual identity",
                      "Predicted track",
                      "Line",
                      "Source time · s",
                      "Class correct",
                      "Direction correct",
                      "Time error · s",
                    ].map((label) => (
                      <th key={label}>{label}</th>
                    ))}
                  </tr>
                </thead>
                <tbody>
                  {rows.map((row, i) => (
                    <tr
                      key={i}
                      className={
                        row.outcome !== "matched" ||
                        row.class_correct === false ||
                        row.direction_correct === false
                          ? "traffic-evaluation-error"
                          : ""
                      }
                    >
                      <td>{row.outcome.replaceAll("_", " ")}</td>
                      <td>{String(row.truth?.identity ?? "—")}</td>
                      <td>{String(row.prediction?.track_id ?? "—")}</td>
                      <td>
                        {String(
                          row.truth?.line_id ??
                            row.prediction?.line_label ??
                            row.prediction?.line_id ??
                            "—",
                        )}
                      </td>
                      <td>
                        {String(
                          row.truth?.timestamp_s ??
                            row.prediction?.timestamp_s ??
                            "—",
                        )}
                      </td>
                      <td>
                        {row.class_correct === undefined
                          ? "—"
                          : row.class_correct
                            ? "yes"
                            : "no"}
                      </td>
                      <td>
                        {row.direction_correct === undefined
                          ? "—"
                          : row.direction_correct
                            ? "yes"
                            : "no"}
                      </td>
                      <td>
                        {typeof row.time_error_s === "number"
                          ? row.time_error_s.toFixed(3)
                          : "—"}
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
          {Array.isArray(report.confusion_matrix) &&
            report.confusion_matrix.length > 0 && (
              <div className="traffic-table-wrap">
                <table aria-label="Vehicle class confusion matrix">
                  <thead>
                    <tr>
                      <th>Manual class</th>
                      <th>Predicted class</th>
                      <th>Matched sample count</th>
                    </tr>
                  </thead>
                  <tbody>
                    {(
                      report.confusion_matrix as {
                        truth: string;
                        prediction: string;
                        count: number;
                      }[]
                    ).map((row, i) => (
                      <tr
                        key={i}
                        className={
                          row.truth !== row.prediction
                            ? "traffic-evaluation-error"
                            : ""
                        }
                      >
                        <td>{row.truth}</td>
                        <td>{row.prediction}</td>
                        <td>{row.count}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            )}
          {Object.entries(report)
            .filter(
              ([key, value]) =>
                Array.isArray(value) &&
                key !== "rows" &&
                key !== "confusion_matrix",
            )
            .map(([key, value]) => (
              <details key={key}>
                <summary>
                  {key.replaceAll("_", " ")} · {(value as unknown[]).length}
                </summary>
                <pre>{JSON.stringify(value, null, 2)}</pre>
              </details>
            ))}
        </div>
      )}
    </section>
  );
}
