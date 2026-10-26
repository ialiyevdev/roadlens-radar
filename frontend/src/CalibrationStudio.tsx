import { useEffect, useRef, useState } from "react";
import type { PointerEvent as ReactPointerEvent } from "react";
import { api } from "./api";
import { errorMessage } from "./useSession";
import Icon from "./Icon";
import { gateErrors, imagePoint } from "./calibrationCoordinates";
import type { ReferenceRow, Mode, Drag } from "./calibrationCoordinates";
import CalibrationFrame from "./CalibrationFrame";
import ReferenceCoordinates from "./ReferenceCoordinates";
import type {
  CalibrationDiagnostics,
  CalibrationInput,
  CalibrationProfile,
  FrozenFrame,
  Point,
  Segment,
  Session,
} from "./types";

const number = (value: number | null | undefined, suffix = "") =>
  value != null && Number.isFinite(value)
    ? `${value.toFixed(3)}${suffix}`
    : "Unavailable";

export default function CalibrationStudio({
  session,
  connected,
  perform,
}: {
  session: Session;
  connected: boolean;
  perform: (operation: () => Promise<Session>) => Promise<void>;
}) {
  const [frame, setFrame] = useState<FrozenFrame | null>(null);
  const [rows, setRows] = useState<ReferenceRow[]>([]);
  const [name, setName] = useState("");
  const [profiles, setProfiles] = useState<CalibrationProfile[]>([]);
  const [profileId, setProfileId] = useState("");
  const [dirty, setDirty] = useState(false);
  const [diagnostics, setDiagnostics] = useState<CalibrationDiagnostics | null>(
    null,
  );
  const [showGrid, setShowGrid] = useState(true);
  const [stationary, setStationary] = useState(false);
  const [mode, setMode] = useState<Mode>("points");
  const [a, setA] = useState<Segment | null>(null);
  const [b, setB] = useState<Segment | null>(null);
  const [pending, setPending] = useState<Point | null>(null);
  const [reverse, setReverse] = useState(false);
  const [gateMessage, setGateMessage] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [notice, setNotice] = useState<string | null>(null);
  const svg = useRef<SVGSVGElement>(null);
  const nextId = useRef(1);
  const dragging = useRef<Drag | null>(null);
  const ignoreClick = useRef(false);
  const loadedSource = useRef<string | null>(null);
  const loadedGeometry = useRef<string | null>(null);

  useEffect(() => {
    if (connected)
      void api
        .calibrations()
        .then((result) => setProfiles(result.profiles))
        .catch((err) => setError(errorMessage(err)));
  }, [connected]);
  useEffect(() => {
    setStationary(false);
  }, [session.session_id]);
  useEffect(() => {
    if (session.calibration_id) {
      setA(session.gates?.gate_a ?? null);
      setB(session.gates?.gate_b ?? null);
      setReverse(session.gates?.allow_reverse ?? false);
    }
  }, [session.calibration_id, session.session_id]);
  const compatibleFrame = Boolean(
    frame &&
    frame.source_id === session.source_id &&
    JSON.stringify(frame.geometry) === JSON.stringify(session.geometry),
  );
  const ready = session.calibration_status === "ready" && compatibleFrame;
  const activeProfile = profiles.find(
    (profile) => profile.id === session.calibration_id,
  );

  async function action(operation: () => Promise<void>) {
    if (busy) return;
    setBusy(true);
    setError(null);
    setNotice(null);
    try {
      await operation();
    } catch (err) {
      setError(errorMessage(err));
    } finally {
      setBusy(false);
    }
  }
  async function freeze() {
    await action(async () => {
      const snapshot = await api.freeze();
      if (
        loadedSource.current &&
        (loadedSource.current !== snapshot.source_id ||
          loadedGeometry.current !== JSON.stringify(snapshot.geometry))
      ) {
        setRows([]);
        setDiagnostics(null);
        setProfileId("");
        setA(null);
        setB(null);
        setName("");
        setDirty(false);
      }
      loadedSource.current = snapshot.source_id;
      loadedGeometry.current = JSON.stringify(snapshot.geometry);
      setFrame(snapshot);
      setPending(null);
      setStationary(false);
      setNotice(
        `${snapshot.geometry.coordinate_space === "undistorted" ? "Undistorted" : "Source"} image frozen without overlays. Road references and gates use these exact pixels. The observation continues independently; pause it from Dashboard if needed.`,
      );
    });
  }
  function input(): CalibrationInput {
    if (!frame || !compatibleFrame)
      throw new Error(
        "Freeze a frame from the current source before validating or saving.",
      );
    if (!name.trim()) throw new Error("Enter a calibration profile name.");
    if (rows.filter((row) => !row.check).length < 4)
      throw new Error(
        "Add at least four fitting reference points on the road plane.",
      );
    if (rows.some((row) => !row.image.every(Number.isFinite)))
      throw new Error(
        "Enter finite source x/y coordinates for every reference point.",
      );
    if (
      rows.some(
        (row) =>
          !row.x.trim() ||
          !row.y.trim() ||
          !Number.isFinite(Number(row.x)) ||
          !Number.isFinite(Number(row.y)),
      )
    )
      throw new Error(
        "Enter a measured, finite world X and Y coordinate for every point.",
      );
    const correspondence = (row: ReferenceRow) => ({
      image: row.image,
      world: [Number(row.x), Number(row.y)] as Point,
    });
    return {
      name: name.trim(),
      source_id: frame.source_id,
      geometry: frame.geometry,
      points: rows.filter((row) => !row.check).map(correspondence),
      check_points: rows.filter((row) => row.check).map(correspondence),
    };
  }
  function changeRow(id: number, values: Partial<ReferenceRow>) {
    setRows((current) =>
      current.map((row) => (row.id === id ? { ...row, ...values } : row)),
    );
    setDiagnostics(null);
    setNotice(null);
    markDirty();
  }
  function markDirty() {
    setDirty(true);
    setStationary(false);
  }
  function loadProfile(id: string) {
    const profile = profiles.find((item) => item.id === id);
    setProfileId(id);
    setStationary(false);
    setError(null);
    setNotice(null);
    setDirty(false);
    if (!profile) {
      setRows([]);
      setName("");
      setDiagnostics(null);
      setA(null);
      setB(null);
      loadedSource.current = frame?.source_id ?? null;
      loadedGeometry.current = frame ? JSON.stringify(frame.geometry) : null;
      return;
    }
    loadedSource.current = profile.source_id;
    loadedGeometry.current = JSON.stringify(profile.geometry);
    setName(profile.name);
    setDiagnostics(profile.diagnostics);
    setRows(
      [
        ...profile.points.map((point) => ({ ...point, check: false })),
        ...profile.check_points.map((point) => ({ ...point, check: true })),
      ].map((point) => ({
        id: nextId.current++,
        image: point.image,
        x: String(point.world[0]),
        y: String(point.world[1]),
        check: point.check,
      })),
    );
    setA(profile.gates?.gate_a ?? null);
    setB(profile.gates?.gate_b ?? null);
    setReverse(profile.gates?.allow_reverse ?? false);
    if (
      frame &&
      (frame.source_id !== profile.source_id ||
        JSON.stringify(frame.geometry) !== JSON.stringify(profile.geometry))
    )
      setFrame(null);
    setNotice(
      "Saved profile loaded. Confirm the camera geometry before applying it to this observation.",
    );
  }
  function eventPoint(event: {
    clientX: number;
    clientY: number;
  }): Point | null {
    return frame && svg.current
      ? imagePoint(
          event.clientX,
          event.clientY,
          svg.current.getBoundingClientRect(),
          frame.geometry.width,
          frame.geometry.height,
        )
      : null;
  }
  function addPoint(event: React.MouseEvent<SVGSVGElement>) {
    if (ignoreClick.current) {
      ignoreClick.current = false;
      return;
    }
    if (!compatibleFrame) return;
    const point = eventPoint(event);
    if (!point) return;
    if (mode === "points") {
      setRows((current) => [
        ...current,
        { id: nextId.current++, image: point, x: "", y: "", check: false },
      ]);
      setDiagnostics(null);
      markDirty();
    } else if (pending) {
      (mode === "A" ? setA : setB)([pending, point]);
      setPending(null);
      setGateMessage("Draft gate changed. Save gates to apply.");
    } else setPending(point);
  }
  function startDrag(event: ReactPointerEvent<SVGCircleElement>, target: Drag) {
    event.stopPropagation();
    event.currentTarget.setPointerCapture(event.pointerId);
    dragging.current = target;
    ignoreClick.current = true;
  }
  function move(event: ReactPointerEvent<SVGSVGElement>) {
    const target = dragging.current;
    if (!target || !compatibleFrame) return;
    const point = eventPoint(event);
    if (!point) return;
    if ("row" in target) changeRow(target.row, { image: point });
    else {
      const setter = target.gate === "A" ? setA : setB;
      setter((current) =>
        current
          ? (current.map((value, index) =>
              index === target.endpoint ? point : value,
            ) as Segment)
          : null,
      );
      setGateMessage("Draft gate changed. Save gates to apply.");
    }
  }
  function gateFields(label: "A" | "B", segment: Segment | null) {
    if (!segment)
      return (
        <p className="field-note">
          Gate {label}: select Draw Gate {label}, then click two endpoints.
        </p>
      );
    return (
      <fieldset className="gate-coordinates">
        <legend>
          Gate {label} ·{" "}
          {frame?.geometry.coordinate_space === "undistorted"
            ? "undistorted"
            : "source"}{" "}
          pixels
        </legend>
        {segment.map((point, endpoint) => (
          <div key={endpoint}>
            {point.map((value, axis) => (
              <label key={axis}>
                {endpoint + 1}
                {axis ? " y" : " x"}
                <input
                  type="number"
                  step="0.1"
                  aria-label={`Gate ${label} endpoint ${endpoint + 1} ${axis ? "y" : "x"}`}
                  value={Number.isFinite(value) ? value : ""}
                  onChange={(event) => {
                    const setter = label === "A" ? setA : setB;
                    setter((current) =>
                      current
                        ? (current.map((p, i) =>
                            i === endpoint
                              ? (p.map((v, j) =>
                                  j === axis
                                    ? event.target.value === ""
                                      ? Number.NaN
                                      : Number(event.target.value)
                                    : v,
                                ) as Point)
                              : p,
                          ) as Segment)
                        : null,
                    );
                    setGateMessage("Draft gate changed. Save gates to apply.");
                  }}
                />
              </label>
            ))}
          </div>
        ))}
      </fieldset>
    );
  }
  const gateIssues = gateErrors(a, b);
  return (
    <div className="calibration-workflow">
      <div className="studio-status">
        <span
          className={`quality-badge ${session.calibration_status === "ready" ? "valid" : "approximate"}`}
        >
          {session.calibration_status === "ready"
            ? "Calibration active"
            : "Calibration required"}
        </span>
        <span>
          {session.measurement_status ||
            "Configure measured geometry and gates"}
        </span>
        {session.calibration_status === "ready" && (
          <button
            className="text-button danger-text"
            onClick={() => void perform(() => api.invalidateCalibration())}
          >
            Camera moved / disable calibration
          </button>
        )}
      </div>
      <section className="panel calibration-instructions">
        <div className="panel-heading">
          <h2>Measured references first</h2>
          <Icon name="target" size={19} />
        </div>
        <p>
          Use a stationary camera and a mostly planar road. Measure road
          markings or other ground-plane points from a safe, permitted location.
          Choose an origin and enter each point’s measured X/Y in meters. Spread
          at least four points around the measurement area.
        </p>
        <p>
          Camera height, guessed lane widths, and vehicle lengths do not
          establish scale. Add independent check points when available; four
          fitted points alone cannot verify accuracy. Keep the view, zoom, crop,
          rotation, and mirroring unchanged.
        </p>
      </section>
      {error && (
        <div role="alert" className="inline-error">
          {error}
        </div>
      )}
      {notice && (
        <div role="status" className="studio-notice">
          {notice}
        </div>
      )}
      {frame && !compatibleFrame && (
        <div role="alert" className="inline-error">
          Frozen frame is incompatible with the current source geometry. Freeze
          the current source and load a matching calibration.
        </div>
      )}
      <div className="calibration-layout">
        <div>
          <CalibrationFrame
            frame={frame}
            diagnostics={diagnostics}
            rows={rows}
            showGrid={showGrid}
            setShowGrid={setShowGrid}
            mode={mode}
            setMode={(value) => {
              setMode(value);
              setPending(null);
            }}
            a={a}
            b={b}
            pending={pending}
            ready={ready}
            canFreeze={connected && session.frame_index > 0}
            busy={busy}
            freeze={freeze}
            svg={svg}
            addPoint={addPoint}
            move={move}
            endDrag={() => {
              dragging.current = null;
            }}
            startDrag={startDrag}
          />
          <ReferenceCoordinates
            rows={rows}
            busy={busy}
            frame={frame}
            changeRow={changeRow}
            removeRow={(id) => {
              setRows((current) => current.filter((row) => row.id !== id));
              setDiagnostics(null);
              markDirty();
            }}
            clearRows={() => {
              setRows([]);
              setDiagnostics(null);
              markDirty();
            }}
            validate={() =>
              void action(async () => {
                setDiagnostics(await api.validateCalibration(input()));
              })
            }
          />
        </div>
        <div className="calibration-side">
          <section className="panel studio-panel">
            <div className="panel-heading">
              <h2>Calibration profile</h2>
              <Icon name="shield" size={17} />
            </div>
            <label className="studio-field">
              Saved profiles
              <select
                aria-label="Saved calibration profiles"
                value={profileId}
                onChange={(event) => loadProfile(event.target.value)}
              >
                <option value="">New profile</option>
                {profiles.map((profile) => (
                  <option key={profile.id} value={profile.id}>
                    {profile.name}
                  </option>
                ))}
              </select>
            </label>
            <label className="studio-field">
              Profile name
              <input
                aria-label="Calibration profile name"
                value={name}
                maxLength={100}
                placeholder="Stationary road camera"
                onChange={(event) => {
                  setName(event.target.value);
                  markDirty();
                }}
              />
            </label>
            <button
              className="button button-primary full-button"
              disabled={busy || !frame || !diagnostics?.valid}
              onClick={() =>
                void action(async () => {
                  const saved = await api.saveCalibration(
                    input(),
                    profileId || undefined,
                  );
                  setProfiles((await api.calibrations()).profiles);
                  setProfileId(saved.id);
                  setDiagnostics(saved.diagnostics);
                  setDirty(false);
                  setNotice(
                    "Calibration saved locally. Apply it explicitly to this observation.",
                  );
                })
              }
            >
              {profileId ? "Update profile" : "Save profile"}
            </button>
            {profileId && dirty && (
              <p className="diagnostic-warning" role="status">
                Unsaved references; validate and update profile before applying.
              </p>
            )}
            <label className="check-label stationary-check">
              <input
                type="checkbox"
                checked={stationary}
                disabled={dirty}
                onChange={(event) => setStationary(event.target.checked)}
              />
              I confirm the camera, zoom, and image geometry match this profile.
            </label>
            <button
              className="button button-secondary full-button"
              disabled={
                busy ||
                !connected ||
                !profileId ||
                dirty ||
                !stationary ||
                !session.session_id
              }
              onClick={() =>
                void perform(() => api.activateCalibration(profileId))
              }
            >
              Apply to this observation
            </button>
            <p className="field-note">
              Every new observation requires explicit application. Resolution
              matching cannot detect camera movement.
            </p>
            {profileId && (
              <button
                className="text-button danger-text"
                disabled={busy}
                onClick={() =>
                  void action(async () => {
                    await api.deleteCalibration(profileId);
                    setProfiles((await api.calibrations()).profiles);
                    loadProfile("");
                    setNotice("Calibration profile deleted.");
                  })
                }
              >
                Delete saved profile
              </button>
            )}
          </section>
          <section className="panel studio-panel geometry-diagnostics">
            <div className="panel-heading">
              <h2>Geometry diagnostics</h2>
              <span
                className={`quality-badge ${diagnostics?.valid ? "valid" : "approximate"}`}
              >
                {diagnostics
                  ? diagnostics.valid
                    ? "Geometry accepted"
                    : "Needs attention"
                  : "Not validated"}
              </span>
            </div>
            {diagnostics ? (
              <>
                <dl className="diagnostics-list">
                  <div>
                    <dt>Image coverage</dt>
                    <dd>{number(diagnostics.coverage * 100, "%")}</dd>
                  </div>
                  <div>
                    <dt>Fit residual</dt>
                    <dd>{number(diagnostics.fit_error_m, " m")}</dd>
                  </div>
                  <div>
                    <dt>Fit inliers</dt>
                    <dd>
                      {diagnostics.inliers.filter(Boolean).length} /{" "}
                      {diagnostics.inliers.length}
                    </dd>
                  </div>
                  <div>
                    <dt>Image residual</dt>
                    <dd>{number(diagnostics.fit_error_px, " px")}</dd>
                  </div>
                  <div>
                    <dt>Independent check error</dt>
                    <dd>{number(diagnostics.check_error_m, " m")}</dd>
                  </div>
                  <div>
                    <dt>Condition number</dt>
                    <dd>{number(diagnostics.condition_number)}</dd>
                  </div>
                </dl>
                {diagnostics.errors.map((message) => (
                  <p className="diagnostic-error" key={message}>
                    {message}
                  </p>
                ))}
                {diagnostics.warnings.map((message) => (
                  <p className="diagnostic-warning" key={message}>
                    {message}
                  </p>
                ))}
              </>
            ) : (
              <p className="panel-description">
                Validation checks geometry, coverage, conditioning, and
                independent points where provided. It does not establish
                real-world accuracy.
              </p>
            )}
            <p className="field-note">
              A zero residual from four fitted points is expected and is not
              independent validation.
            </p>
          </section>
          <section className="panel studio-panel">
            <div className="panel-heading">
              <h2>Virtual measurement gates</h2>
              <Icon name="arrow" size={18} />
            </div>
            <p className="panel-description">
              Apply a valid calibration, then draw two segments across the
              measured road area. The arrow shows A → B; gate endpoints remain
              in source pixels.
            </p>
            {!ready && (
              <p className="diagnostic-warning">
                Apply a compatible calibration and freeze the current source to
                edit gates.
              </p>
            )}
            {gateFields("A", a)}
            {gateFields("B", b)}
            <label className="check-label">
              <input
                type="checkbox"
                checked={reverse}
                onChange={(event) => {
                  setReverse(event.target.checked);
                  setGateMessage("Draft gate changed. Save gates to apply.");
                }}
              />
              Also accept B → A
            </label>
            <label className="check-label">
              <input
                type="checkbox"
                checked={session.overlays?.gates ?? true}
                disabled={!connected}
                onChange={(event) =>
                  void perform(() =>
                    api.overlays({
                      ...session.overlays,
                      gates: event.target.checked,
                    }),
                  )
                }
              />
              Show gates in observation feed
            </label>
            {gateMessage && (
              <p className="field-note" role="status">
                {gateMessage}
              </p>
            )}
            <div className="gate-actions">
              <button
                className="button button-primary compact"
                disabled={!ready || busy}
                onClick={() =>
                  void action(async () => {
                    if (gateIssues.length)
                      throw new Error(gateIssues.join(" "));
                    const result = await api.saveGates({
                      gate_a: a!,
                      gate_b: b!,
                      allow_reverse: reverse,
                    });
                    if (!result.valid) throw new Error(result.errors.join(" "));
                    setProfiles((await api.calibrations()).profiles);
                    setGateMessage(
                      result.warnings.length
                        ? `Gates saved. ${result.warnings.join(" ")}`
                        : "Gates saved to the active profile.",
                    );
                  })
                }
              >
                Save gates
              </button>
              <button
                className="button button-secondary compact"
                disabled={!ready || busy}
                onClick={() =>
                  void action(async () => {
                    await api.resetGates();
                    setProfiles((await api.calibrations()).profiles);
                    setA(null);
                    setB(null);
                    setPending(null);
                    setGateMessage("Gate configuration reset.");
                  })
                }
              >
                Reset gates
              </button>
            </div>
            {activeProfile && (
              <p className="field-note">Active profile: {activeProfile.name}</p>
            )}
            <p className="field-note">
              Average straight-line displacement between crossing positions;
              curved paths can be underestimated.
            </p>
          </section>
        </div>
      </div>
    </div>
  );
}
