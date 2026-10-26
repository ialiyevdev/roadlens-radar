import { useEffect, useRef, useState } from "react";
import Preview from "./Preview";
import { api } from "./api";
import { trafficApi } from "./trafficApi";
import { downloadResult } from "./validationApi";
import { qualityEntries } from "./fieldPresentation";
import TrafficEditor from "./TrafficEditor";
import TrafficCharts from "./TrafficCharts";
import TrafficEvaluation from "./TrafficEvaluation";
import type { Session } from "./types";
import type {
  TrafficAnalysis,
  TrafficArtifact,
  TrafficConfiguration,
  TrafficOverlays,
  TrafficRequest,
  TrafficSessionSummary,
  TrafficTable,
} from "./trafficTypes";
import "./traffic.css";

const tabs = [
  "Overview & trends",
  "Lines & zones",
  "Traffic events",
  "Compare & export",
  "Evaluate predictions",
] as const;
const tables: { value: TrafficTable; label: string }[] = [
  { value: "events", label: "Vehicle crossing events" },
  { value: "classes", label: "Vehicle-class summaries" },
  { value: "flow", label: "Traffic-flow intervals" },
  { value: "zones", label: "Zone occupancy & dwell" },
  { value: "speeds", label: "Speed summaries" },
  { value: "comparisons", label: "Session comparisons" },
  { value: "quality", label: "Data quality indicators" },
];
const overlayLabels: [keyof TrafficOverlays, string][] = [
  ["track_ids", "Tracking IDs"],
  ["vehicle_classes", "Vehicle classes"],
  ["traffic_lines", "Counting lines"],
  ["traffic_zones", "Monitoring zones"],
  ["direction_indicators", "Direction indicators"],
  ["zone_occupancy", "Zone occupancy indicators"],
];
export function metric(value: unknown, digits = 1) {
  return typeof value === "number" && Number.isFinite(value)
    ? Number.isInteger(value)
      ? String(value)
      : value.toFixed(digits)
    : "—";
}
export function observationDate(value: string): string | undefined {
  if (!value) return undefined;
  const date = new Date(value);
  return Number.isFinite(date.getTime()) ? date.toISOString() : undefined;
}
export function uniqueEventOptions(
  events: TrafficAnalysis["events"],
  key: "category" | "direction" | "line_id" | "status",
) {
  return [...new Set(events.map((event) => event[key]))].sort();
}
function RecordsTable({
  title,
  rows,
}: {
  title: string;
  rows: Record<string, unknown>[];
}) {
  const keys = [...new Set(rows.flatMap((row) => Object.keys(row)))].filter(
    (key) =>
      rows.some(
        (row) =>
          row[key] !== null &&
          (typeof row[key] !== "object" || Array.isArray(row[key])),
      ),
  );
  return rows.length ? (
    <div className="traffic-table-wrap">
      <table aria-label={title}>
        <thead>
          <tr>
            {keys.map((key) => (
              <th key={key}>{key.replaceAll("_", " ")}</th>
            ))}
          </tr>
        </thead>
        <tbody>
          {rows.map((row, i) => (
            <tr key={i}>
              {keys.map((key) => (
                <td key={key}>
                  {typeof row[key] === "number"
                    ? metric(row[key], 3)
                    : typeof row[key] === "boolean"
                      ? row[key]
                        ? "yes"
                        : "no"
                      : Array.isArray(row[key])
                        ? (row[key] as unknown[]).join(" · ") || "—"
                        : String(row[key] ?? "—")}
                </td>
              ))}
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  ) : (
    <p className="traffic-empty">No {title.toLowerCase()} available.</p>
  );
}
export default function TrafficWorkspace({
  session,
  connected,
  visible,
  onSession,
}: {
  session: Session;
  connected: boolean;
  visible: boolean;
  onSession?: (session: Session) => void;
}) {
  const [tab, setTab] = useState<(typeof tabs)[number]>(tabs[0]);
  const [current, setCurrent] = useState<TrafficArtifact | null>(null);
  const [configuration, setConfiguration] =
    useState<TrafficConfiguration | null>(null);
  const [sessions, setSessions] = useState<TrafficSessionSummary[]>([]);
  const [selected, setSelected] = useState<string[]>([]);
  const [includeCurrent, setIncludeCurrent] = useState(true);
  const [interval, setIntervalMinutes] = useState(1);
  const [category, setCategory] = useState("");
  const [direction, setDirection] = useState("");
  const [line, setLine] = useState("");
  const [status, setStatus] = useState("");
  const [start, setStart] = useState("");
  const [end, setEnd] = useState("");
  const [startedAfter, setStartedAfter] = useState("");
  const [startedBefore, setStartedBefore] = useState("");
  const [speedStatus, setSpeedStatus] = useState<"valid" | "approximate">(
    "valid",
  );
  const [analysis, setAnalysis] = useState<TrafficAnalysis | null>(null);
  const [unfiltered, setUnfiltered] = useState<TrafficAnalysis | null>(null);
  const [overlays, setOverlays] = useState<TrafficOverlays | null>(null);
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);
  const [loading, setLoading] = useState(false);
  const [notice, setNotice] = useState("");
  const [tick, setTick] = useState(0);
  const [exportTable, setExportTable] = useState<TrafficTable>("events");
  const [eventPage, setEventPage] = useState(0);
  const requestSerial = useRef(0);
  const request: TrafficRequest = {
    session_ids: selected,
    include_current: includeCurrent,
    interval_minutes: interval,
    speed_status: speedStatus,
    ...(category ? { category } : {}),
    ...(direction ? { direction } : {}),
    ...(line ? { line_id: line } : {}),
    ...(status ? { status } : {}),
    ...(start !== "" ? { start_s: Number(start) } : {}),
    ...(end !== "" ? { end_s: Number(end) } : {}),
    ...(observationDate(startedAfter)
      ? { observation_started_after: observationDate(startedAfter) }
      : {}),
    ...(observationDate(startedBefore)
      ? { observation_started_before: observationDate(startedBefore) }
      : {}),
  };
  const requestKey = JSON.stringify(request);
  useEffect(() => setEventPage(0), [requestKey]);
  async function list() {
    setSessions((await trafficApi.list()).sessions);
  }
  useEffect(() => {
    if (!connected || !visible) return;
    let active = true;
    Promise.all([
      trafficApi.list(),
      trafficApi.overlays(),
      trafficApi.configuration(),
    ])
      .then(([value, layers, config]) => {
        if (active) {
          setSessions(value.sessions);
          setOverlays(layers);
          setConfiguration(config);
        }
      })
      .catch((e) => {
        if (active) setError(e instanceof Error ? e.message : String(e));
      });
    return () => {
      active = false;
    };
  }, [connected, visible, session.state, session.session_id]);
  useEffect(() => {
    if (!connected || !visible) return;
    let active = true;
    let polling = false;
    const poll = async () => {
      if (polling) return;
      polling = true;
      try {
        const value = await trafficApi.current();
        if (active) {
          setCurrent(value.snapshot);
          if (value.snapshot) setConfiguration(value.snapshot.configuration);
          setUnfiltered(value.analytics);
          setTick((t) => t + 1);
        }
      } catch (e) {
        if (active) setError(e instanceof Error ? e.message : String(e));
      } finally {
        polling = false;
      }
    };
    void poll();
    const timer = window.setInterval(() => void poll(), 1500);
    return () => {
      active = false;
      window.clearInterval(timer);
    };
  }, [connected, visible]);
  useEffect(() => {
    if (!connected || !visible) return;
    const serial = ++requestSerial.current;
    let active = true;
    const value = JSON.parse(requestKey) as TrafficRequest;
    if (
      value.start_s !== undefined &&
      value.end_s !== undefined &&
      value.end_s <= value.start_s
    ) {
      setError("End source time must be after start source time.");
      setAnalysis(null);
      return;
    }
    if (
      value.observation_started_after &&
      value.observation_started_before &&
      value.observation_started_before <= value.observation_started_after
    ) {
      setError("Observation date end must follow its start.");
      setAnalysis(null);
      setLoading(false);
      return;
    }
    setLoading(true);
    trafficApi
      .analyze(value)
      .then((result) => {
        if (active && serial === requestSerial.current) {
          setAnalysis(result);
          setError("");
        }
      })
      .catch((e) => {
        if (active && serial === requestSerial.current)
          setError(e instanceof Error ? e.message : String(e));
      })
      .finally(() => {
        if (active && serial === requestSerial.current) setLoading(false);
      });
    return () => {
      active = false;
    };
  }, [connected, visible, requestKey, tick]);
  async function action(task: () => Promise<void>) {
    setBusy(true);
    setError("");
    setNotice("");
    try {
      await task();
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    } finally {
      setBusy(false);
    }
  }
  async function loadExample() {
    const artifact = await trafficApi.example();
    await list();
    const id = artifact.id || artifact.session_id;
    if (id) {
      setSelected([id]);
      setIncludeCurrent(false);
      setCategory("");
      setDirection("");
      setLine("");
      setStatus("");
      setStart("");
      setEnd("");
      setStartedAfter("");
      setStartedBefore("");
    }
    setNotice(
      "Synthetic traffic fixture loaded. These trajectories and speeds demonstrate software behavior; they are not roadway evidence.",
    );
    setTab(tabs[0]);
    setTick((t) => t + 1);
  }
  async function archive() {
    await trafficApi.archive();
    await list();
    setNotice(
      "Current traffic observation archived with its source coverage and configuration history.",
    );
  }
  async function exportData(format: "json" | "csv") {
    const blob = await trafficApi.export(request, exportTable, format);
    downloadResult(blob, `roadlens-traffic-${exportTable}.${format}`);
    setNotice(`Exported ${exportTable} as ${format.toUpperCase()}.`);
  }
  const summary = analysis?.summary;
  const eventPageCount = Math.max(
    1,
    Math.ceil((analysis?.events.length ?? 0) / 100),
  );
  const displayPage = Math.min(eventPage, eventPageCount - 1);
  const opts = [...(unfiltered?.events ?? []), ...(analysis?.events ?? [])];
  const provenance = [
    ...new Set(
      selected
        .map((id) => sessions.find((s) => s.id === id)?.provenance)
        .filter(Boolean),
    ),
  ];
  return (
    <div className="traffic-workspace">
      {analysis?.summary.incomplete_retained_data && (
        <p className="traffic-warning" role="status">
          This observation exceeded retained-history limits. Counts cover{" "}
          {analysis.summary.count_scope ?? "retained"} data; filtered events,
          charts and exports contain a retained subset. Incomplete filtered
          rates are withheld.
        </p>
      )}
      <section className="panel traffic-panel traffic-intro">
        <div className="traffic-heading">
          <div>
            <div className="eyebrow">
              TRAFFIC INTELLIGENCE <span>/</span> SOURCE-TIME ANALYTICS
            </div>
            <h2>Understand the traffic you observed.</h2>
            <p className="panel-description">
              Directional crossings, stable vehicle classes and manually
              configured monitoring regions. One temporary track ID does not
              establish one unique physical vehicle.
            </p>
          </div>
          <div className="traffic-actions">
            <button
              className="button button-secondary"
              disabled={!connected || busy}
              onClick={() => void action(loadExample)}
            >
              Load synthetic traffic example
            </button>
            <button
              className="button button-primary"
              disabled={!connected || busy || !current?.session_id}
              onClick={() => void action(archive)}
            >
              Archive traffic observation
            </button>
          </div>
        </div>
        {notice && (
          <p role="status" className="traffic-notice">
            {notice}
          </p>
        )}
        {error && (
          <p role="alert" className="inline-error">
            {error}
          </p>
        )}
        <p className="traffic-evidence">
          {provenance.includes("synthetic")
            ? "SYNTHETIC EVIDENCE · deterministic generated trajectories and speed records"
            : provenance.length
              ? `Evidence: ${provenance.join(", ")}`
              : "Recorded observations have no independent reference accuracy until validated."}
        </p>
      </section>
      <div
        role="tablist"
        aria-label="Traffic Intelligence views"
        className="traffic-tabs"
      >
        {tabs.map((name) => (
          <button
            key={name}
            role="tab"
            aria-selected={tab === name}
            onClick={() => setTab(name)}
          >
            {name}
          </button>
        ))}
      </div>
      <section className="panel traffic-panel traffic-filters">
        <div className="traffic-heading">
          <h2>Observation selection</h2>
          <button
            className="text-button"
            disabled={!connected || busy}
            onClick={() => void action(list)}
          >
            Refresh traffic sessions
          </button>
          <span className="field-note">
            {loading
              ? "Updating source-time statistics…"
              : "Statistics use covered source time"}
          </span>
        </div>
        <fieldset className="traffic-session-choice">
          <legend>Traffic observation sessions</legend>
          <label className="check-label">
            <input
              type="checkbox"
              checked={includeCurrent}
              onChange={(e) => setIncludeCurrent(e.target.checked)}
            />
            Current observation
            {current?.session_id
              ? ` · ${current.session_id.slice(0, 8)}`
              : " · no source started"}
          </label>
          {sessions.map((s) => (
            <label key={s.id} className="check-label">
              <input
                type="checkbox"
                checked={selected.includes(s.id)}
                onChange={(e) =>
                  setSelected(
                    e.target.checked
                      ? [...selected, s.id]
                      : selected.filter((id) => id !== s.id),
                  )
                }
              />
              {s.name || s.session_id || s.id}
              <span className="field-note">
                {s.provenance || "recorded_unverified"}
              </span>
            </label>
          ))}
          {!sessions.length && (
            <span className="field-note">
              No archived traffic observations.
            </span>
          )}
        </fieldset>
        <div className="traffic-filter-grid">
          <label>
            Aggregation interval
            <select
              value={interval}
              onChange={(e) => setIntervalMinutes(Number(e.target.value))}
            >
              {[1, 5, 15, 30, 60].map((n) => (
                <option key={n} value={n}>
                  {n} minute{n === 1 ? "" : "s"}
                </option>
              ))}
            </select>
          </label>
          <label>
            Vehicle class filter
            <select
              value={category}
              onChange={(e) => setCategory(e.target.value)}
            >
              <option value="">All supported vehicle classes</option>
              {["car", "truck", "bus", "motorcycle", "unknown"].map((c) => (
                <option value={c} key={c}>
                  {c}
                </option>
              ))}
            </select>
          </label>
          <label>
            Direction filter
            <select
              value={direction}
              onChange={(e) => setDirection(e.target.value)}
            >
              <option value="">All directions</option>
              {["positive", "negative"].map((d) => (
                <option key={d} value={d}>
                  {d}
                </option>
              ))}
            </select>
          </label>
          <label>
            Counting line filter
            <select value={line} onChange={(e) => setLine(e.target.value)}>
              <option value="">All counting lines</option>
              {line && !opts.some((event) => event.line_id === line) && (
                <option value={line}>{line}</option>
              )}
              {uniqueEventOptions(opts, "line_id").map((id) => (
                <option key={id} value={id}>
                  {opts.find((e) => e.line_id === id)?.line_label || id}
                </option>
              ))}
            </select>
          </label>
          <label>
            Event status filter
            <select value={status} onChange={(e) => setStatus(e.target.value)}>
              <option value="">All event statuses</option>
              <option value="counted">Counted</option>
              <option value="suppressed">Suppressed duplicate candidate</option>
            </select>
          </label>
          <label>
            Start source time · s
            <input
              type="number"
              min="0"
              step=".1"
              value={start}
              onChange={(e) => setStart(e.target.value)}
            />
          </label>
          <label>
            End source time · s
            <input
              type="number"
              min="0"
              step=".1"
              value={end}
              onChange={(e) => setEnd(e.target.value)}
            />
          </label>
          <label>
            Speed evidence
            <select
              value={speedStatus}
              onChange={(e) =>
                setSpeedStatus(e.target.value as typeof speedStatus)
              }
            >
              <option value="valid">Valid metric measurements only</option>
              <option value="approximate">
                Approximate measurements separately
              </option>
            </select>
          </label>
          <label>
            Observation start after
            <input
              type="datetime-local"
              value={startedAfter}
              onChange={(e) => setStartedAfter(e.target.value)}
            />
          </label>
          <label>
            Observation start before
            <input
              type="datetime-local"
              value={startedBefore}
              onChange={(e) => setStartedBefore(e.target.value)}
            />
          </label>
        </div>
        <p className="field-note">
          Time filters are seconds on each recording's source clock. Observation
          dates and source identifiers appear in session comparison metadata.
          Browser polling and inference time never define traffic volume. Date
          inputs use your browser's local timezone (
          {Intl.DateTimeFormat().resolvedOptions().timeZone}); requests retain
          an explicit UTC offset.
        </p>
      </section>
      {analysis?.warnings.length ? (
        <div className="traffic-warning" role="status">
          {analysis.warnings.map((warning, i) => (
            <p key={i}>{warning}</p>
          ))}
        </div>
      ) : null}
      <div hidden={tab !== tabs[0]}>
        <div className="traffic-kpis">
          {[
            {
              label: "Observed crossings",
              value: summary?.total_crossings,
              note: "Counted crossings across selected lines; a vehicle may cross multiple lines.",
            },
            {
              label: "Normalized observed rate",
              value: summary?.normalized_crossings_per_minute,
              unit: "/ min",
              note: `${metric(summary?.coverage_seconds)} s of covered source time; incomplete recordings are not hourly forecasts.`,
            },
            {
              label: "Most common class",
              value: summary?.most_common_category,
              note: "Stable votes from supported YOLOX-S vehicle categories.",
            },
            {
              label:
                speedStatus === "valid"
                  ? "Valid average speed"
                  : "Approximate average speed",
              value: summary?.mean_speed_kmh,
              unit: "km/h",
              note: `N=${metric(analysis?.speeds.n)} ${speedStatus} metric measurements; road calibration required.`,
            },
            {
              label: "Current zone occupancy",
              value: summary?.current_zone_occupancy,
              note: "Visible tracked vehicles across manually configured zones; overlaps may count a vehicle twice.",
            },
            {
              label: "Suppressed candidates",
              value: summary?.suppressed_events,
              note: "Retained for review; temporal/spatial duplicate heuristics do not prove identity.",
            },
          ].map((item) => (
            <div className="metric-card" key={item.label}>
              <div className="metric-label">{item.label}</div>
              <div className="metric-value">
                {typeof item.value === "string"
                  ? item.value
                  : metric(item.value)}
                <span>{item.unit}</span>
              </div>
              <p>{item.note}</p>
            </div>
          ))}
        </div>
        {analysis && (
          <>
            <div className="traffic-direction-summary">
              {analysis.directions.map((d) => (
                <span key={`${d.direction}-${d.direction_label}`}>
                  {d.direction_label || d.direction} <strong>{d.count}</strong>
                </span>
              ))}
            </div>
            <TrafficCharts analysis={analysis} />
            <section className="panel traffic-panel">
              <h2>
                {speedStatus === "valid"
                  ? "Valid metric speed statistics"
                  : "Approximate metric speed statistics"}
              </h2>
              <p className="panel-description">
                N={analysis.speeds.n} · only the selected status is aggregated.
                Percentiles describe observed samples and carry no regulatory
                determination.
              </p>
              <div className="traffic-speed-metrics">
                {[
                  ["Mean", analysis.speeds.mean_kmh],
                  ["Median", analysis.speeds.median_kmh],
                  ["Minimum", analysis.speeds.minimum_kmh],
                  ["Maximum", analysis.speeds.maximum_kmh],
                  ["85th percentile", analysis.speeds.p85_kmh],
                  [
                    "Standard deviation",
                    analysis.speeds.standard_deviation_kmh,
                  ],
                ].map(([label, value]) => (
                  <div key={String(label)}>
                    <span>{label}</span>
                    <strong>
                      {metric(value)} <small>km/h</small>
                    </strong>
                  </div>
                ))}
              </div>
              {!analysis.speeds.n && (
                <p className="traffic-empty">
                  No {speedStatus} calibrated speed measurements in this
                  selection. Image-based counts and occupancy remain available.
                </p>
              )}
              <details>
                <summary>
                  Speed statistics by class, direction and source-time interval
                </summary>
                <RecordsTable
                  title="Speeds by class"
                  rows={analysis.speeds.by_class}
                />
                <RecordsTable
                  title="Speeds by direction"
                  rows={analysis.speeds.by_direction}
                />
                <RecordsTable
                  title="Speeds by source interval"
                  rows={analysis.speeds.by_interval}
                />
              </details>
            </section>
            <section className="panel traffic-panel">
              <h2>Monitoring-zone activity</h2>
              <p className="panel-description">
                Occupancy is a camera-visible proxy. Dwell time uses observed
                entry and exit; interrupted visits stay explicit.
              </p>
              <dl className="traffic-quality">
                {analysis.occupancy
                  .slice(-1)
                  .flatMap((row) =>
                    qualityEntries(
                      Object.fromEntries(
                        Object.entries(row).filter(([key]) =>
                          [
                            "visible_tracks",
                            "stationary_tracks",
                            "slow_tracks",
                            "occupancy_level",
                            "zone_occupancy_proxy",
                          ].includes(key),
                        ),
                      ),
                    ),
                  )
                  .map(([label, value]) => (
                    <div key={label}>
                      <dt>{label}</dt>
                      <dd>{value}</dd>
                    </div>
                  ))}
              </dl>
              <p className="field-note">
                Low / moderate / high observed occupancy uses the saved
                configurable vehicle-count thresholds. Stationarity is an
                image-motion heuristic; slow-speed indicators require calibrated
                measurements.
              </p>
              <RecordsTable
                title="Zone occupancy and dwell"
                rows={analysis.zones}
              />
            </section>
            <section className="panel traffic-panel">
              <h2>Counting & measurement quality</h2>
              <RecordsTable
                title="Traffic data quality"
                rows={analysis.quality}
              />
            </section>
          </>
        )}
        {!analysis && (
          <p className="traffic-empty">
            Choose a source observation or load the explicitly synthetic example
            to explore traffic analytics.
          </p>
        )}
      </div>
      <div hidden={tab !== tabs[1]}>
        <TrafficEditor
          session={session}
          connected={connected}
          configuration={configuration}
          onSaved={(value) => {
            setConfiguration(value);
            setTick((t) => t + 1);
          }}
        />
        <section className="panel traffic-panel">
          <h2>Observation preview & overlay layers</h2>
          <Preview session={session} />
          <fieldset
            disabled={!connected || busy}
            className="traffic-overlay-options"
          >
            <legend>Independent traffic overlays</legend>
            {overlays &&
              overlayLabels.map(([key, label]) => (
                <label className="check-label" key={key}>
                  <input
                    type="checkbox"
                    checked={overlays[key]}
                    onChange={(e) => {
                      const next = { ...overlays, [key]: e.target.checked };
                      void action(async () =>
                        setOverlays(await trafficApi.setOverlays(next)),
                      );
                    }}
                  />
                  {label}
                </label>
              ))}
            {(
              [
                ["boxes", "Vehicle bounding boxes"],
                ["speeds", "Completed valid speed labels"],
              ] as const
            ).map(([key, label]) => (
              <label className="check-label" key={key}>
                <input
                  type="checkbox"
                  checked={session.overlays[key]}
                  onChange={(e) => {
                    const next = {
                      ...session.overlays,
                      [key]: e.target.checked,
                    };
                    void action(async () => {
                      const updated = await api.overlays(next);
                      onSession?.(updated);
                    });
                  }}
                />
                {label}
              </label>
            ))}
          </fieldset>
        </section>
      </div>
      <div hidden={tab !== tabs[2]}>
        <section className="panel traffic-panel">
          <div className="traffic-heading">
            <h2>Source-timestamped crossing events</h2>
            <span>{analysis?.events.length ?? 0} retained rows</span>
          </div>
          <p className="panel-description">
            Temporary IDs may fragment or transfer between vehicles. Inspect
            status and reasons before treating counts as unique physical
            vehicles.
          </p>
          <div className="traffic-table-wrap">
            <table aria-label="Traffic crossing events">
              <thead>
                <tr>
                  {[
                    "Source time · s",
                    "Observation",
                    "Class / score",
                    "Direction",
                    "Counting line",
                    "Track ID",
                    "Speed · km/h",
                    "Status",
                    "Diagnostic reasons",
                  ].map((h) => (
                    <th key={h}>{h}</th>
                  ))}
                </tr>
              </thead>
              <tbody>
                {analysis?.events
                  .slice(displayPage * 100, (displayPage + 1) * 100)
                  .map((event) => (
                    <tr key={event.id}>
                      <td className="mono">{metric(event.timestamp_s, 3)}</td>
                      <td title={event.session_id}>
                        {event.session_id.slice(0, 8)}
                      </td>
                      <td>
                        {event.category} ·{" "}
                        {typeof event.class_score === "number"
                          ? `${(event.class_score * 100).toFixed(0)}%`
                          : "—"}
                      </td>
                      <td>{event.direction_label || event.direction}</td>
                      <td>{event.line_label || event.line_id}</td>
                      <td className="mono">#{event.track_id}</td>
                      <td>
                        {metric(event.measured_speed_kmh ?? event.speed_kmh)}
                      </td>
                      <td>
                        <span className={`traffic-status ${event.status}`}>
                          {event.status}
                        </span>
                      </td>
                      <td title={event.diagnostic_reasons.join(" · ")}>
                        {event.diagnostic_reasons.join(" · ") ||
                          "No additional flags"}
                      </td>
                    </tr>
                  ))}
              </tbody>
            </table>
          </div>
          {eventPageCount > 1 && (
            <div className="traffic-actions">
              <button
                className="button button-secondary"
                disabled={displayPage === 0}
                onClick={() => setEventPage(displayPage - 1)}
              >
                Previous event page
              </button>
              <span className="field-note">
                Page {displayPage + 1} of {eventPageCount} · 100 rows per page ·
                exports include all filtered retained rows
              </span>
              <button
                className="button button-secondary"
                disabled={displayPage >= eventPageCount - 1}
                onClick={() => setEventPage(displayPage + 1)}
              >
                Next event page
              </button>
            </div>
          )}
          {!analysis?.events.length && (
            <p className="traffic-empty">
              No traffic events match this selection. Configure a line and
              observe a crossing, or explore the synthetic example.
            </p>
          )}
        </section>
      </div>
      <div hidden={tab !== tabs[3]}>
        <section className="panel traffic-panel">
          <h2>Compare recorded observations</h2>
          <p className="panel-description">
            Select two or more archived observations above. Different durations,
            incomplete coverage and changed counting configurations remain
            explicit; normalized rates require coverage and do not establish
            statistically significant traffic changes.
          </p>
          {analysis && (
            <RecordsTable
              title="Traffic session comparisons"
              rows={analysis.comparisons}
            />
          )}
          <p className="traffic-warning">
            Matching labels alone do not establish compatible traffic streams.
            Inspect source, camera geometry and configuration identifiers before
            comparing zones or lines.
          </p>
        </section>
        <section className="panel traffic-panel">
          <h2>Export analysis tables</h2>
          <p className="panel-description">
            CSV and JSON use explicit units and preserve selected sessions,
            source-time filters and quality metadata. Suitable for pandas,
            PostgreSQL and Power BI.
          </p>
          <label>
            Traffic export table
            <select
              value={exportTable}
              onChange={(e) => setExportTable(e.target.value as TrafficTable)}
            >
              {tables.map((t) => (
                <option key={t.value} value={t.value}>
                  {t.label}
                </option>
              ))}
            </select>
          </label>
          <div className="traffic-actions">
            <button
              className="button button-primary"
              disabled={!connected || busy || loading || !analysis}
              onClick={() => void action(() => exportData("csv"))}
            >
              Export traffic CSV
            </button>
            <button
              className="button button-secondary"
              disabled={!connected || busy || loading || !analysis}
              onClick={() => void action(() => exportData("json"))}
            >
              Export traffic JSON
            </button>
          </div>
        </section>
        <details className="panel traffic-panel">
          <summary>Current observation diagnostics</summary>
          <dl className="traffic-quality">
            {qualityEntries(current?.diagnostics ?? {}).map(([key, value]) => (
              <div key={key}>
                <dt>{key}</dt>
                <dd>{value}</dd>
              </div>
            ))}
          </dl>
        </details>
      </div>
      <div hidden={tab !== tabs[4]}>
        <TrafficEvaluation
          connected={connected}
          sessions={sessions}
          visible={visible && tab === tabs[4]}
        />
      </div>
    </div>
  );
}
