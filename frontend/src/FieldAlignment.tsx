import { useEffect, useState } from "react";
import { fieldApi } from "./fieldApi";
import type { EventMatch, FieldSession, SyncAnchor } from "./fieldTypes";
import { finite } from "./ValidationCharts";
import { formatMetric } from "./validationPresentation";

const errorText = (error: unknown) =>
  error instanceof Error ? error.message : "The alignment request failed.";
const nullableNumber = (value: string) => (value === "" ? null : Number(value));
export function AlignmentTimeline({ field }: { field: FieldSession }) {
  const measurements = field.measurements
    .filter(
      (item, i, all) =>
        all.findIndex((candidate) => candidate.event_id === item.event_id) ===
        i,
    )
    .filter((item) => finite(item.measurement.timestamp_s));
  const scale = field.sync_diagnostics.scale;
  const offset = field.sync_diagnostics.offset_s;
  const points = [
    ...measurements.map((item) => item.measurement.timestamp_s!),
    ...field.reference_events.map((item) => offset + scale * item.timestamp_s),
  ];
  const low = Math.min(0, ...points),
    high = Math.max(low + 1, ...points);
  const x = (time: number) => 90 + (760 * (time - low)) / (high - low);
  return (
    <section className="panel field-timeline">
      <h3>Measurement and reference timeline</h3>
      <p>
        Reference times mapped onto source seconds using the saved clock model.
        Select event matches explicitly below.
      </p>
      {points.length ? (
        <svg
          viewBox="0 0 900 180"
          role="img"
          aria-label="Recorded measurements and aligned reference event timeline"
        >
          <text x="8" y="47">
            RoadLens
          </text>
          <text x="8" y="114">
            Reference
          </text>
          <line x1="90" y1="42" x2="850" y2="42" className="chart-grid" />
          <line x1="90" y1="109" x2="850" y2="109" className="chart-grid" />
          {field.matches
            .filter((match) => match.reference_id)
            .map((match) => {
              const a = measurements.find(
                (item) => item.event_id === match.event_id,
              );
              const b = field.reference_events.find(
                (item) => item.id === match.reference_id,
              );
              return a && b ? (
                <line
                  key={match.event_id}
                  x1={x(a.measurement.timestamp_s!)}
                  y1="42"
                  x2={x(offset + scale * b.timestamp_s)}
                  y2="109"
                  className={`field-match-line ${match.association}`}
                >
                  <title>
                    {match.event_id} → {match.reference_id}: {match.association}
                  </title>
                </line>
              ) : null;
            })}
          {measurements.map((item) => (
            <circle
              key={item.event_id}
              cx={x(item.measurement.timestamp_s!)}
              cy="42"
              r="5"
              className="chart-point"
            >
              <title>
                {item.event_id}: source {item.measurement.timestamp_s} s
              </title>
            </circle>
          ))}
          {field.reference_events.map((item) => (
            <rect
              key={item.id}
              x={x(offset + scale * item.timestamp_s) - 4}
              y="105"
              width="8"
              height="8"
              className="chart-bar"
            >
              <title>
                {item.id}: reference {item.timestamp_s} s → source{" "}
                {(offset + scale * item.timestamp_s).toFixed(3)} s
              </title>
            </rect>
          ))}
          {[0, 1, 2, 3, 4].map((i) => {
            const time = low + ((high - low) * i) / 4;
            return (
              <text key={i} x={x(time)} y="145" textAnchor="middle">
                {time.toFixed(2)} s
              </text>
            );
          })}
          <text x="470" y="173" textAnchor="middle">
            Source time, seconds
          </text>
        </svg>
      ) : (
        <p className="field-empty">
          No timestamped measurements or reference events retained.
        </p>
      )}
    </section>
  );
}
export default function FieldAlignment({
  field,
  connected,
  onSaved,
}: {
  field: FieldSession;
  connected: boolean;
  onSaved: (field: FieldSession) => void;
}) {
  const [sync, setSync] = useState(field.sync);
  const [matches, setMatches] = useState<EventMatch[]>(field.matches);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [anchor, setAnchor] = useState({
    reference: "",
    source: "",
    uncertainty: "",
    independent: false,
    description: "",
  });
  useEffect(() => {
    setSync(field.sync);
    setMatches(field.matches);
  }, [field.sync, field.matches]);
  async function operation(action: () => Promise<FieldSession>) {
    setBusy(true);
    setError(null);
    try {
      onSaved(await action());
    } catch (cause) {
      setError(errorText(cause));
    } finally {
      setBusy(false);
    }
  }
  const events = field.measurements.filter(
    (item, index, all) =>
      all.findIndex((candidate) => candidate.event_id === item.event_id) ===
      index,
  );
  const disabled = busy || !connected;
  const canAdd =
    anchor.reference !== "" &&
    anchor.source !== "" &&
    finite(Number(anchor.reference)) &&
    finite(Number(anchor.source)) &&
    Number(anchor.source) >= 0 &&
    (anchor.uncertainty === "" ||
      (finite(Number(anchor.uncertainty)) && Number(anchor.uncertainty) >= 0));
  function changeMatch(eventId: string, change: Partial<EventMatch>) {
    const previous = matches.find((item) => item.event_id === eventId) || {
      event_id: eventId,
      reference_id: null,
      association: "unmatched",
      method: "",
      quality_notes: "",
      correspondence_confirmed: false,
    };
    setMatches([
      ...matches.filter((item) => item.event_id !== eventId),
      { ...previous, ...change },
    ]);
  }
  const validSync =
    finite(sync.offset_s) &&
    finite(sync.maximum_alignment_error_s) &&
    sync.maximum_alignment_error_s > 0 &&
    sync.maximum_alignment_error_s <= 60 &&
    (sync.uncertainty_s === null ||
      (finite(sync.uncertainty_s) && sync.uncertainty_s >= 0));
  return (
    <div className="field-stack">
      {error && (
        <p className="inline-error" role="alert">
          {error}
        </p>
      )}
      <section className="panel field-panel">
        <div className="panel-heading">
          <div>
            <h2>Independent reference events</h2>
            <p className="panel-description">
              Import device events with identifiers, timestamps, speed, units,
              method, provenance, and quality notes.
            </p>
          </div>
        </div>
        <label
          className={`button button-secondary field-upload ${disabled ? "disabled" : ""}`}
        >
          Import reference CSV / JSON
          <input
            type="file"
            accept=".csv,.json,text/csv,application/json"
            className="visually-hidden"
            aria-label="Import independent reference measurements"
            disabled={disabled}
            onChange={(e) => {
              const file = e.target.files?.[0];
              e.target.value = "";
              if (file)
                void operation(() => fieldApi.importReferences(field.id, file));
            }}
          />
        </label>
        <p className="field-note">
          {field.reference_events.length} imported references. Importing
          replaces the reference ledger and clears earlier matching decisions.
          GPS applications and ordinary speedometers do not establish reference
          precision by themselves.
        </p>
        {field.reference_events.length > 0 && (
          <div className="table-scroll">
            <table aria-label="Imported reference events">
              <thead>
                <tr>
                  <th>Reference ID</th>
                  <th>Reference time · s</th>
                  <th>Speed</th>
                  <th>Method</th>
                  <th>Evidence</th>
                  <th>Quality notes</th>
                </tr>
              </thead>
              <tbody>
                {field.reference_events.map((item) => (
                  <tr key={item.id}>
                    <td>{item.id}</td>
                    <td>{item.timestamp_s}</td>
                    <td>
                      {item.speed} {item.units}
                    </td>
                    <td>{item.method}</td>
                    <td>
                      {item.provenance.replaceAll("_", " ")} ·{" "}
                      {item.independent
                        ? "declared independent"
                        : "independence unconfirmed"}
                    </td>
                    <td>{item.quality_notes || "—"}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </section>
      <section className="panel field-panel">
        <div className="panel-heading">
          <div>
            <h2>Clock synchronization</h2>
            <p className="panel-description">
              Source time = offset + scale × reference time. A manual offset
              alone remains uncertain.
            </p>
          </div>
          <span className={`field-state ${field.sync_diagnostics.status}`}>
            {field.sync_diagnostics.status}
          </span>
        </div>
        <fieldset disabled={disabled}>
          <legend className="visually-hidden">
            Synchronization configuration
          </legend>
          <div className="field-form-grid">
            <label>
              Source clock metadata
              <input
                value={sync.source_clock}
                onChange={(e) =>
                  setSync({ ...sync, source_clock: e.target.value })
                }
              />
            </label>
            <label>
              Reference clock metadata
              <input
                value={sync.reference_clock}
                onChange={(e) =>
                  setSync({ ...sync, reference_clock: e.target.value })
                }
              />
            </label>
            <label>
              Manual source offset · seconds
              <input
                type="number"
                step="any"
                value={finite(sync.offset_s) ? sync.offset_s : ""}
                onChange={(e) =>
                  setSync({
                    ...sync,
                    offset_s:
                      e.target.value === "" ? NaN : Number(e.target.value),
                  })
                }
              />
            </label>
            <label>
              Offset uncertainty bound · seconds
              <input
                type="number"
                min={0}
                step="any"
                value={sync.uncertainty_s ?? ""}
                onChange={(e) =>
                  setSync({
                    ...sync,
                    uncertainty_s: nullableNumber(e.target.value),
                  })
                }
              />
            </label>
            <label>
              Maximum alignment error · seconds
              <input
                type="number"
                min={0.001}
                max={60}
                step="any"
                value={
                  finite(sync.maximum_alignment_error_s)
                    ? sync.maximum_alignment_error_s
                    : ""
                }
                onChange={(e) =>
                  setSync({
                    ...sync,
                    maximum_alignment_error_s:
                      e.target.value === "" ? NaN : Number(e.target.value),
                  })
                }
              />
            </label>
            <label className="field-check">
              <input
                type="checkbox"
                checked={sync.fit_drift}
                onChange={(e) =>
                  setSync({ ...sync, fit_drift: e.target.checked })
                }
              />
              Fit drift from independent anchors
            </label>
            <label className="field-wide">
              Synchronization notes
              <textarea
                value={sync.notes}
                onChange={(e) => setSync({ ...sync, notes: e.target.value })}
              />
            </label>
          </div>
          <h3>Synchronization anchors</h3>
          <p className="field-note">
            Use visible events observed by both clocks. Drift fitting requires
            at least two independent anchors. Enter an evidence-based
            uncertainty bound for each anchor.
          </p>
          {sync.anchors.length > 0 && (
            <div className="table-scroll">
              <table aria-label="Synchronization anchors">
                <thead>
                  <tr>
                    <th>Reference · s</th>
                    <th>Source · s</th>
                    <th>Bound · s</th>
                    <th>Independent</th>
                    <th>Description</th>
                    <th />
                  </tr>
                </thead>
                <tbody>
                  {sync.anchors.map((item, i) => (
                    <tr key={i}>
                      <td>{item.reference_timestamp_s}</td>
                      <td>{item.source_timestamp_s}</td>
                      <td>{item.uncertainty_s ?? "unknown"}</td>
                      <td>{item.independent ? "yes" : "no"}</td>
                      <td>{item.description || "—"}</td>
                      <td>
                        <button
                          className="text-button"
                          aria-label={`Remove synchronization anchor ${i + 1}`}
                          onClick={() =>
                            setSync({
                              ...sync,
                              anchors: sync.anchors.filter(
                                (_, index) => index !== i,
                              ),
                            })
                          }
                        >
                          Remove
                        </button>
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
          <div className="field-anchor-form">
            <label>
              Anchor reference time · s
              <input
                type="number"
                step="any"
                value={anchor.reference}
                onChange={(e) =>
                  setAnchor({ ...anchor, reference: e.target.value })
                }
              />
            </label>
            <label>
              Anchor source time · s
              <input
                type="number"
                min={0}
                step="any"
                value={anchor.source}
                onChange={(e) =>
                  setAnchor({ ...anchor, source: e.target.value })
                }
              />
            </label>
            <label>
              Anchor uncertainty · s
              <input
                type="number"
                min={0}
                step="any"
                value={anchor.uncertainty}
                onChange={(e) =>
                  setAnchor({ ...anchor, uncertainty: e.target.value })
                }
              />
            </label>
            <label>
              Description
              <input
                value={anchor.description}
                onChange={(e) =>
                  setAnchor({ ...anchor, description: e.target.value })
                }
              />
            </label>
            <label className="field-check">
              <input
                type="checkbox"
                checked={anchor.independent}
                onChange={(e) =>
                  setAnchor({ ...anchor, independent: e.target.checked })
                }
              />
              Independent clock evidence
            </label>
            <button
              className="button button-secondary compact"
              disabled={!canAdd}
              onClick={() => {
                const added: SyncAnchor = {
                  reference_timestamp_s: Number(anchor.reference),
                  source_timestamp_s: Number(anchor.source),
                  uncertainty_s: nullableNumber(anchor.uncertainty),
                  independent: anchor.independent,
                  description: anchor.description,
                };
                setSync({ ...sync, anchors: [...sync.anchors, added] });
                setAnchor({
                  reference: "",
                  source: "",
                  uncertainty: "",
                  independent: false,
                  description: "",
                });
              }}
            >
              Add synchronization anchor
            </button>
          </div>
          <div className="field-actions">
            <button
              className="button button-primary"
              disabled={!validSync}
              onClick={() =>
                void operation(() => fieldApi.sync(field.id, sync))
              }
            >
              Save synchronization
            </button>
          </div>
        </fieldset>
        <dl className="field-quality-grid">
          <div>
            <dt>Saved offset</dt>
            <dd>{formatMetric(field.sync_diagnostics.offset_s)} s</dd>
          </div>
          <div>
            <dt>Clock drift</dt>
            <dd>{formatMetric(field.sync_diagnostics.drift_ppm)} ppm</dd>
          </div>
          <div>
            <dt>Anchor count</dt>
            <dd>{field.sync_diagnostics.anchor_count}</dd>
          </div>
          <div>
            <dt>Maximum anchor residual</dt>
            <dd>{formatMetric(field.sync_diagnostics.maximum_residual_s)} s</dd>
          </div>
          <div>
            <dt>Synchronization bound</dt>
            <dd>
              {formatMetric(field.sync_diagnostics.uncertainty_bound_s)} s
            </dd>
          </div>
        </dl>
        {field.sync_diagnostics.warnings.map((warning) => (
          <p className="studio-notice" key={warning}>
            {warning}
          </p>
        ))}
      </section>
      <AlignmentTimeline field={field} />
      <section className="panel field-panel">
        <div className="panel-heading">
          <div>
            <h2>Explicit event correspondence</h2>
            <p className="panel-description">
              Match observed vehicles using independent evidence. No
              closest-event selection is made automatically.
            </p>
          </div>
        </div>
        {!events.length ? (
          <p className="field-empty">
            No retained RoadLens measurements. Capture a completed observation
            or import a field-session export containing measurements.
          </p>
        ) : (
          <>
            <div className="table-scroll">
              <table
                className="field-matches"
                aria-label="Event to reference matching"
              >
                <thead>
                  <tr>
                    <th>Vehicle event</th>
                    <th>Source time / estimate</th>
                    <th>Reference event</th>
                    <th>Association</th>
                    <th>Correspondence evidence</th>
                  </tr>
                </thead>
                <tbody>
                  {events.map((item) => {
                    const match = matches.find(
                      (candidate) => candidate.event_id === item.event_id,
                    );
                    return (
                      <tr key={item.event_id}>
                        <td>
                          {item.event_id}
                          <small>
                            {item.measurement.status} · predicted ID{" "}
                            {item.measurement.track_id}
                          </small>
                        </td>
                        <td>
                          {formatMetric(item.measurement.timestamp_s)} s
                          <small>
                            {formatMetric(item.measurement.estimated_speed_kmh)}{" "}
                            km/h
                          </small>
                        </td>
                        <td>
                          <select
                            aria-label={`Reference for ${item.event_id}`}
                            disabled={disabled}
                            value={match?.reference_id || ""}
                            onChange={(e) =>
                              changeMatch(item.event_id, {
                                reference_id: e.target.value || null,
                                association: e.target.value
                                  ? "matched"
                                  : "unmatched",
                                correspondence_confirmed: false,
                              })
                            }
                          >
                            <option value="">No reference selected</option>
                            {field.reference_events.map((ref) => (
                              <option key={ref.id} value={ref.id}>
                                {ref.id} · {ref.speed} {ref.units}
                              </option>
                            ))}
                          </select>
                        </td>
                        <td>
                          <select
                            aria-label={`Association for ${item.event_id}`}
                            disabled={disabled}
                            value={match?.association || "unmatched"}
                            onChange={(e) =>
                              changeMatch(item.event_id, {
                                association: e.target
                                  .value as EventMatch["association"],
                              })
                            }
                          >
                            <option value="unmatched">Unmatched</option>
                            <option value="ambiguous">Ambiguous</option>
                            <option value="matched">Matched</option>
                          </select>
                          <label className="field-check">
                            <input
                              type="checkbox"
                              aria-label={`Confirm correspondence for ${item.event_id}`}
                              disabled={disabled || !match?.reference_id}
                              checked={match?.correspondence_confirmed || false}
                              onChange={(e) =>
                                changeMatch(item.event_id, {
                                  correspondence_confirmed: e.target.checked,
                                })
                              }
                            />
                            Vehicle correspondence confirmed
                          </label>
                        </td>
                        <td>
                          <input
                            aria-label={`Matching evidence for ${item.event_id}`}
                            disabled={disabled}
                            placeholder="How the same vehicle was identified"
                            value={match?.method || ""}
                            onChange={(e) =>
                              changeMatch(item.event_id, {
                                method: e.target.value,
                              })
                            }
                          />
                          <input
                            aria-label={`Matching quality notes for ${item.event_id}`}
                            disabled={disabled}
                            placeholder="Quality notes or ambiguity"
                            value={match?.quality_notes || ""}
                            onChange={(e) =>
                              changeMatch(item.event_id, {
                                quality_notes: e.target.value,
                              })
                            }
                          />
                        </td>
                      </tr>
                    );
                  })}
                </tbody>
              </table>
            </div>
            <div className="field-actions">
              <button
                className="button button-primary"
                disabled={disabled}
                onClick={() =>
                  void operation(() => fieldApi.matches(field.id, matches))
                }
              >
                Save matching decisions
              </button>
            </div>
          </>
        )}
      </section>
    </div>
  );
}
