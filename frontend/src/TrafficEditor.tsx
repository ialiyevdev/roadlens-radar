import { useEffect, useRef, useState } from "react";
import { api } from "./api";
import { imagePoint } from "./calibrationCoordinates";
import { trafficApi } from "./trafficApi";
import { newTrafficConfiguration } from "./trafficTypes";
import type { TrafficConfiguration, TrafficZone } from "./trafficTypes";
import type { CalibrationProfile, FrozenFrame, Point, Session } from "./types";

export function groundToImage(
  point: Point,
  homography: number[][],
): Point | null {
  const [a, b, c] = homography;
  if (!a || !b || !c) return null;
  const [x, y] = point;
  const det =
    a[0] * (b[1] * c[2] - b[2] * c[1]) -
    a[1] * (b[0] * c[2] - b[2] * c[0]) +
    a[2] * (b[0] * c[1] - b[1] * c[0]);
  if (!Number.isFinite(det) || Math.abs(det) < 1e-12) return null;
  const u =
    (b[1] * c[2] - b[2] * c[1]) * x +
    (a[2] * c[1] - a[1] * c[2]) * y +
    a[1] * b[2] -
    a[2] * b[1];
  const v =
    (b[2] * c[0] - b[0] * c[2]) * x +
    (a[0] * c[2] - a[2] * c[0]) * y +
    a[2] * b[0] -
    a[0] * b[2];
  const w =
    (b[0] * c[1] - b[1] * c[0]) * x +
    (a[1] * c[0] - a[0] * c[1]) * y +
    a[0] * b[1] -
    a[1] * b[0];
  return Number.isFinite(u + v + w) && Math.abs(w) > 1e-12
    ? [u / w, v / w]
    : null;
}
export function geometryMatches(
  config: TrafficConfiguration,
  frame: FrozenFrame,
) {
  const a = config.geometry,
    b = frame.geometry;
  return (
    config.source_id === frame.source_id &&
    a.width === b.width &&
    a.height === b.height &&
    a.rotation === b.rotation &&
    a.mirrored === b.mirrored &&
    JSON.stringify(a.crop) === JSON.stringify(b.crop) &&
    (a.coordinate_space ?? "source") === (b.coordinate_space ?? "source") &&
    (a.intrinsic_profile_id ?? null) === (b.intrinsic_profile_id ?? null)
  );
}
const settings: [keyof TrafficConfiguration, string, number][] = [
  ["max_gap_s", "Maximum accepted track gap · s", 0.1],
  ["min_track_hits", "Minimum track observations", 1],
  ["class_min_observations", "Minimum class observations", 1],
  ["class_min_confidence", "Minimum class confidence", 0.05],
  ["class_min_margin", "Minimum class vote margin", 0.05],
  ["identity_suppression_s", "Identity duplicate window · s", 0.05],
  ["identity_suppression_px", "Identity duplicate radius · px", 1],
  ["stationary_window_s", "Stationary observation window · s", 0.5],
  ["stationary_radius_px", "Stationary image radius · px", 1],
  ["slow_speed_kmh", "Calibrated slow-speed threshold · km/h", 1],
  ["occupancy_moderate", "Moderate occupancy · tracked vehicles", 1],
  ["occupancy_high", "High occupancy · tracked vehicles", 1],
];
export default function TrafficEditor({
  session,
  connected,
  configuration,
  onSaved,
}: {
  session: Session;
  connected: boolean;
  configuration: TrafficConfiguration | null;
  onSaved: (config: TrafficConfiguration) => void;
}) {
  const [draft, setDraft] = useState<TrafficConfiguration | null>(
    configuration,
  );
  const [frame, setFrame] = useState<FrozenFrame | null>(null);
  const [profiles, setProfiles] = useState<CalibrationProfile[]>([]);
  const [mode, setMode] = useState<"select" | "line" | "zone">("select");
  const [points, setPoints] = useState<Point[]>([]);
  const [selection, setSelection] = useState("");
  const [dirty, setDirty] = useState(false);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const [notice, setNotice] = useState("");
  const svg = useRef<SVGSVGElement>(null);
  const dirtyRef = useRef(dirty);
  dirtyRef.current = dirty;
  useEffect(() => {
    if (!dirtyRef.current) setDraft(configuration);
  }, [configuration]);
  const change = (next: TrafficConfiguration) => {
    setDraft(next);
    setDirty(true);
    setNotice("");
  };
  const incompatible = Boolean(
    draft && frame && !geometryMatches(draft, frame),
  );
  const frozenStale = Boolean(
    frame &&
    (frame.session_id !== session.session_id ||
      frame.source_id !== session.source_id ||
      (frame.geometry.intrinsic_profile_id ?? null) !==
        (session.geometry?.intrinsic_profile_id ?? null)),
  );
  const groundIncompatible = Boolean(
    draft?.zones.some((zone) => zone.coordinate_space === "ground") &&
    (session.calibration_status !== "ready" ||
      draft?.calibration_id !== session.calibration_id),
  );
  const selectedLine = draft?.lines.find(
    (line) => `line:${line.id}` === selection,
  );
  const selectedZone = draft?.zones.find(
    (zone) => `zone:${zone.id}` === selection,
  );
  async function freeze() {
    setBusy(true);
    setError("");
    try {
      const next = await api.freeze();
      setFrame(next);
      setPoints([]);
      setMode("select");
      if (!draft) {
        setDraft(newTrafficConfiguration(next.source_id, next.geometry));
        setDirty(true);
      }
      try {
        setProfiles((await api.calibrations()).profiles);
      } catch {
        setProfiles([]);
      }
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    } finally {
      setBusy(false);
    }
  }
  function add(point: Point) {
    if (!draft || incompatible || frozenStale || busy) return;
    if (mode === "line") {
      if (!points.length) {
        setPoints([point]);
        return;
      }
      const id = crypto.randomUUID();
      change({
        ...draft,
        lines: [
          ...draft.lines,
          {
            id,
            label: `Counting line ${draft.lines.length + 1}`,
            start: points[0],
            end: point,
            positive_label: "A → B",
            negative_label: "B → A",
            hysteresis_px: 3,
          },
        ],
      });
      setPoints([]);
      setMode("select");
      setSelection(`line:${id}`);
    } else if (mode === "zone") setPoints([...points, point]);
  }
  function finishZone() {
    if (!draft || points.length < 3) return;
    const id = crypto.randomUUID();
    change({
      ...draft,
      zones: [
        ...draft.zones,
        {
          id,
          label: `Monitoring zone ${draft.zones.length + 1}`,
          points,
          coordinate_space: "image",
          hysteresis: 3,
        },
      ],
    });
    setSelection(`zone:${id}`);
    setPoints([]);
    setMode("select");
  }
  function editPoints(value: Point[]) {
    if (!draft) return;
    if (selectedLine && value.length === 2)
      change({
        ...draft,
        lines: draft.lines.map((line) =>
          line.id === selectedLine.id
            ? { ...line, start: value[0], end: value[1] }
            : line,
        ),
      });
    if (selectedZone)
      change({
        ...draft,
        zones: draft.zones.map((zone) =>
          zone.id === selectedZone.id ? { ...zone, points: value } : zone,
        ),
      });
  }
  function zoneImage(zone: TrafficZone): Point[] {
    if (zone.coordinate_space === "image") return zone.points;
    if (groundIncompatible) return [];
    const h = profiles.find((p) => p.id === draft?.calibration_id)?.diagnostics
      .homography;
    return h
      ? zone.points
          .map((p) => groundToImage(p, h))
          .filter((p): p is Point => p !== null)
      : [];
  }
  async function save() {
    if (!draft || incompatible || frozenStale || groundIncompatible) return;
    setBusy(true);
    setError("");
    try {
      const saved = await trafficApi.configure(draft);
      setDraft(saved);
      setDirty(false);
      onSaved(saved);
      setNotice(
        "Counting configuration saved. Changes begin a separate coverage segment.",
      );
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    } finally {
      setBusy(false);
    }
  }
  return (
    <div className="traffic-editor">
      <section className="panel traffic-panel">
        <div className="traffic-heading">
          <div>
            <h2>Counting lines & monitoring zones</h2>
            <p className="panel-description">
              Manually configured regions · counting is independent of speed
              gates.
            </p>
          </div>
          <button
            className="button button-primary"
            disabled={!connected || session.frame_index < 1 || busy}
            onClick={() => void freeze()}
          >
            Freeze counting frame
          </button>
        </div>
        <p className="field-note">
          Pause the source for repeatable placement. Draw two endpoints for a
          finite line; click three or more vertices and finish a polygon. Image
          regions need no speed calibration.
        </p>
        {error && (
          <p className="inline-error" role="alert">
            {error}
          </p>
        )}
        {notice && (
          <p role="status" className="traffic-notice">
            {notice}
          </p>
        )}
        {(incompatible || frozenStale) && (
          <p role="alert" className="traffic-warning">
            The frozen frame or saved geometry differs from the active source.
            Freeze the current source, then start a new configuration.
            Coordinates are never scaled automatically.
          </p>
        )}
        {groundIncompatible && (
          <p className="traffic-warning" role="alert">
            Ground-zone calibration differs from the active valid road mapping.
            Choose the current calibration and recheck measured vertices, or use
            image-space zones.
          </p>
        )}
        <div className="traffic-editor-tools">
          <button
            className={`button button-secondary ${mode === "line" ? "selected" : ""}`}
            disabled={!frame || incompatible || frozenStale || busy}
            onClick={() => {
              setMode("line");
              setPoints([]);
            }}
          >
            Draw counting line
          </button>
          <button
            className="button button-secondary"
            disabled={!frame || incompatible || frozenStale || busy}
            onClick={() => {
              setMode("zone");
              setPoints([]);
            }}
          >
            Draw monitoring zone
          </button>
          <button
            className="button button-secondary"
            disabled={mode !== "zone" || points.length < 3 || busy}
            onClick={finishZone}
          >
            Finish polygon
          </button>
          <button
            className="text-button"
            disabled={!points.length}
            onClick={() => {
              setPoints([]);
              setMode("select");
            }}
          >
            Cancel drawing
          </button>
        </div>
        {frame ? (
          <>
            <p className="field-note">
              {frame.geometry.width} × {frame.geometry.height}{" "}
              {frame.geometry.coordinate_space ?? "source"} pixels
              {frame.geometry.intrinsic_profile_id
                ? ` · intrinsic ${frame.geometry.intrinsic_profile_id}`
                : ""}{" "}
              ·{" "}
              {mode === "select"
                ? "Select a shape or edit its coordinates below."
                : `${mode} drawing · ${points.length} points`}
            </p>
            <div className="traffic-canvas">
              <svg
                ref={svg}
                viewBox={`0 0 ${frame.geometry.width} ${frame.geometry.height}`}
                preserveAspectRatio="xMidYMid meet"
                role="img"
                aria-label="Traffic counting frame"
                onClick={(event) => {
                  if (!svg.current) return;
                  const point = imagePoint(
                    event.clientX,
                    event.clientY,
                    svg.current.getBoundingClientRect(),
                    frame.geometry.width,
                    frame.geometry.height,
                  );
                  if (point) add(point);
                }}
              >
                <image
                  href={frame.image_url}
                  width={frame.geometry.width}
                  height={frame.geometry.height}
                />
                {!incompatible &&
                  draft?.zones.map((zone) => (
                    <g
                      key={zone.id}
                      className={
                        selection === `zone:${zone.id}` ? "selected" : ""
                      }
                      onClick={(event) => {
                        if (mode !== "select") return;
                        event.stopPropagation();
                        setSelection(`zone:${zone.id}`);
                      }}
                    >
                      <polygon
                        points={zoneImage(zone)
                          .map((p) => p.join(","))
                          .join(" ")}
                        className="traffic-zone"
                      />
                      {zoneImage(zone)[0] && (
                        <text
                          x={zoneImage(zone)[0][0]}
                          y={zoneImage(zone)[0][1]}
                        >
                          {zone.label}
                        </text>
                      )}
                    </g>
                  ))}
                {!incompatible &&
                  draft?.lines.map((line) => (
                    <g
                      key={line.id}
                      className={
                        selection === `line:${line.id}` ? "selected" : ""
                      }
                      onClick={(event) => {
                        if (mode !== "select") return;
                        event.stopPropagation();
                        setSelection(`line:${line.id}`);
                      }}
                    >
                      <line
                        x1={line.start[0]}
                        y1={line.start[1]}
                        x2={line.end[0]}
                        y2={line.end[1]}
                        className="traffic-line"
                      />
                      <circle
                        cx={line.start[0]}
                        cy={line.start[1]}
                        r={Math.max(4, frame.geometry.width / 130)}
                      />
                      <text x={line.start[0] + 8} y={line.start[1] - 8}>
                        {line.label} · A
                      </text>
                      <text x={line.end[0] + 8} y={line.end[1] - 8}>
                        B
                      </text>
                    </g>
                  ))}
                {points.length > 0 && (
                  <polyline
                    className="traffic-pending"
                    points={points.map((p) => p.join(",")).join(" ")}
                  />
                )}
                {points.map((p, i) => (
                  <circle
                    key={i}
                    cx={p[0]}
                    cy={p[1]}
                    r={5}
                    className="traffic-point"
                  />
                ))}
              </svg>
            </div>
          </>
        ) : (
          <div className="traffic-empty">
            Start a recorded video in Camera & video, pause it, then freeze an
            unannotated counting frame.
          </div>
        )}
        {frame && (
          <button
            className="text-button"
            disabled={busy}
            onClick={() => {
              setDraft(
                newTrafficConfiguration(frame.source_id, frame.geometry),
              );
              setDirty(true);
              setSelection("");
              setPoints([]);
            }}
          >
            Start new configuration for this frame
          </button>
        )}
      </section>
      <section className="panel traffic-panel">
        <h2>Region settings</h2>
        {draft ? (
          <fieldset disabled={busy} className="traffic-fieldset">
            <label>
              Configuration name
              <input
                value={draft.name}
                onChange={(e) => change({ ...draft, name: e.target.value })}
              />
            </label>
            <label>
              Selected counting region
              <select
                value={selection}
                onChange={(e) => setSelection(e.target.value)}
              >
                <option value="">Choose line or zone</option>
                {draft.lines.map((line) => (
                  <option key={line.id} value={`line:${line.id}`}>
                    Line · {line.label}
                  </option>
                ))}
                {draft.zones.map((zone) => (
                  <option key={zone.id} value={`zone:${zone.id}`}>
                    Zone · {zone.label}
                  </option>
                ))}
              </select>
            </label>
            {selectedLine && (
              <>
                <label>
                  Counting line label
                  <input
                    value={selectedLine.label}
                    onChange={(e) =>
                      change({
                        ...draft,
                        lines: draft.lines.map((l) =>
                          l.id === selectedLine.id
                            ? { ...l, label: e.target.value }
                            : l,
                        ),
                      })
                    }
                  />
                </label>
                <label>
                  Positive crossing label
                  <input
                    value={selectedLine.positive_label}
                    onChange={(e) =>
                      change({
                        ...draft,
                        lines: draft.lines.map((l) =>
                          l.id === selectedLine.id
                            ? { ...l, positive_label: e.target.value }
                            : l,
                        ),
                      })
                    }
                  />
                </label>
                <label>
                  Negative crossing label
                  <input
                    value={selectedLine.negative_label}
                    onChange={(e) =>
                      change({
                        ...draft,
                        lines: draft.lines.map((l) =>
                          l.id === selectedLine.id
                            ? { ...l, negative_label: e.target.value }
                            : l,
                        ),
                      })
                    }
                  />
                </label>
                <p className="field-note">
                  Positive means the signed side increases through zero using
                  image x right and y down. For a horizontal A-left to B-right
                  line, positive travels from above to below. Labels describe
                  your observed directions.
                </p>
                <label>
                  Line hysteresis · px
                  <input
                    type="number"
                    min="0"
                    step=".5"
                    value={selectedLine.hysteresis_px}
                    onChange={(e) =>
                      change({
                        ...draft,
                        lines: draft.lines.map((l) =>
                          l.id === selectedLine.id
                            ? { ...l, hysteresis_px: Number(e.target.value) }
                            : l,
                        ),
                      })
                    }
                  />
                </label>
              </>
            )}
            {selectedZone && (
              <>
                <label>
                  Monitoring zone label
                  <input
                    value={selectedZone.label}
                    onChange={(e) =>
                      change({
                        ...draft,
                        zones: draft.zones.map((z) =>
                          z.id === selectedZone.id
                            ? { ...z, label: e.target.value }
                            : z,
                        ),
                      })
                    }
                  />
                </label>
                <label>
                  Zone coordinates
                  <select
                    value={selectedZone.coordinate_space}
                    onChange={(e) => {
                      const coordinate_space = e.target.value as
                        "image" | "ground";
                      change({
                        ...draft,
                        zones: draft.zones.map((z) =>
                          z.id === selectedZone.id
                            ? {
                                ...z,
                                coordinate_space,
                                points:
                                  coordinate_space === "ground"
                                    ? [
                                        [0, 0],
                                        [1, 0],
                                        [1, 1],
                                        [0, 1],
                                      ]
                                    : [],
                                hysteresis:
                                  coordinate_space === "ground" ? 0.1 : 3,
                              }
                            : z,
                        ),
                      });
                    }}
                  >
                    <option value="image">
                      Image pixels · no calibration needed
                    </option>
                    <option
                      value="ground"
                      disabled={session.calibration_status !== "ready"}
                    >
                      Ground plane · meters
                    </option>
                  </select>
                </label>
                {selectedZone.coordinate_space === "ground" && (
                  <>
                    <p className="traffic-warning">
                      Enter measured ground coordinates below. Switching
                      coordinate systems resets this polygon; pixel values are
                      never relabeled as meters.
                    </p>
                    <label>
                      Ground-zone calibration
                      <select
                        value={draft.calibration_id ?? ""}
                        onChange={(e) =>
                          change({
                            ...draft,
                            calibration_id: e.target.value || null,
                          })
                        }
                      >
                        <option value="">
                          Choose compatible active calibration
                        </option>
                        {profiles
                          .filter((p) => p.id === session.calibration_id)
                          .map((p) => (
                            <option key={p.id} value={p.id}>
                              {p.name}
                            </option>
                          ))}
                      </select>
                    </label>
                  </>
                )}
                <label>
                  Zone boundary hysteresis ·{" "}
                  {selectedZone.coordinate_space === "ground" ? "m" : "px"}
                  <input
                    type="number"
                    min="0"
                    step=".1"
                    value={selectedZone.hysteresis}
                    onChange={(e) =>
                      change({
                        ...draft,
                        zones: draft.zones.map((z) =>
                          z.id === selectedZone.id
                            ? { ...z, hysteresis: Number(e.target.value) }
                            : z,
                        ),
                      })
                    }
                  />
                </label>
              </>
            )}
            {(selectedLine || selectedZone) && (
              <>
                <div className="traffic-coordinates">
                  {(selectedLine
                    ? [selectedLine.start, selectedLine.end]
                    : selectedZone!.points
                  ).map((point, i) => (
                    <div key={i}>
                      {point.map((value, axis) => (
                        <label key={axis}>
                          {`${selectedLine ? "Endpoint" : "Vertex"} ${i + 1} ${axis === 0 ? "x" : "y"}`}
                          <input
                            type="number"
                            step=".1"
                            value={value}
                            onChange={(e) => {
                              const all = (
                                selectedLine
                                  ? [selectedLine.start, selectedLine.end]
                                  : selectedZone!.points
                              ).map((p) => [...p] as Point);
                              all[i][axis] = Number(e.target.value);
                              editPoints(all);
                            }}
                          />
                        </label>
                      ))}
                    </div>
                  ))}
                </div>
                {selectedZone && (
                  <button
                    className="text-button"
                    onClick={() => editPoints([...selectedZone.points, [0, 0]])}
                  >
                    Add polygon vertex
                  </button>
                )}
                <button
                  className="button button-secondary"
                  onClick={() => {
                    change({
                      ...draft,
                      lines: draft.lines.filter(
                        (l) => `line:${l.id}` !== selection,
                      ),
                      zones: draft.zones.filter(
                        (z) => `zone:${z.id}` !== selection,
                      ),
                    });
                    setSelection("");
                  }}
                >
                  Delete selected region
                </button>
              </>
            )}
            <details className="traffic-settings">
              <summary>
                Counting, class stability & occupancy heuristics
              </summary>
              <p className="field-note">
                Heuristic thresholds. Pixel stationarity and visible occupancy
                do not establish metric speed or network congestion. Duplicate
                suppression can also merge nearby vehicles; inspect suppressed
                events.
              </p>
              {settings.map(([key, label, step]) => (
                <label key={key}>
                  {label}
                  <input
                    type="number"
                    min="0"
                    step={step}
                    value={draft[key] as number}
                    onChange={(e) =>
                      change({ ...draft, [key]: Number(e.target.value) })
                    }
                  />
                </label>
              ))}
            </details>
            <button
              className="button button-primary"
              disabled={
                !connected ||
                !dirty ||
                mode !== "select" ||
                points.length > 0 ||
                incompatible ||
                frozenStale ||
                groundIncompatible ||
                ["running", "starting"].includes(session.state) ||
                busy
              }
              onClick={() => void save()}
            >
              Save traffic configuration
            </button>
            {dirty && <p className="field-note">Unsaved region changes</p>}
            {["running", "starting"].includes(session.state) && (
              <p className="field-note">
                Pause the source before applying counting-region changes.
              </p>
            )}
          </fieldset>
        ) : (
          <p className="traffic-empty">
            Freeze a source frame to begin. Counting lines and monitoring zones
            are stored independently of road-plane speed gates.
          </p>
        )}
      </section>
    </div>
  );
}
