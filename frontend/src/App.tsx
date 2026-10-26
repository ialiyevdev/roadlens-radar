import { useState } from "react";
import Icon from "./Icon";
import type { IconName } from "./Icon";
import Preview, { elapsed, stateLabels } from "./Preview";
import SourceControls from "./SourceControls";
import Diagnostics from "./Diagnostics";
import TrackTable from "./TrackTable";
import Methodology from "./Methodology";
import CalibrationStudio from "./CalibrationStudio";
import SpeedPanel from "./SpeedPanel";
import OverlayControls from "./OverlayControls";
import ValidationBenchmarks from "./ValidationBenchmarks";
import FieldWorkspace from "./FieldWorkspace";
import TrafficWorkspace from "./TrafficWorkspace";
import Showcase from "./Showcase";
import type { ShowcaseView } from "./Showcase";
import { api } from "./api";
import type { Category } from "./types";
import { useSession } from "./useSession";

type Section =
  | "dashboard"
  | "sources"
  | "calibration"
  | "validation"
  | "fields"
  | "realValidation"
  | "traffic"
  | "showcase"
  | "methodology";
const categories: { key: Category; label: string; icon: IconName }[] = [
  { key: "car", label: "Cars", icon: "car" },
  { key: "truck", label: "Trucks", icon: "truck" },
  { key: "bus", label: "Buses", icon: "bus" },
  { key: "motorcycle", label: "Motorcycles", icon: "motorcycle" },
];
const titles = {
  showcase: [
    "Guided showcase",
    "Explore the pipeline with stored synthetic evidence, without a camera.",
  ],
  dashboard: [
    "Observation dashboard",
    "A live view of your source, detections, and tracking performance.",
  ],
  sources: [
    "Camera & video",
    "Choose your input and inspect the timing behind every frame.",
  ],
  calibration: [
    "Calibration & gates",
    "Connect measured road geometry to source-timestamped vehicle observations.",
  ],
  validation: [
    "Validation & benchmarks",
    "Inspect independent speed comparisons and reproducible tracking results.",
  ],
  fields: [
    "Field sessions",
    "Record camera geometry, annotate vehicles, and retain observation provenance.",
  ],
  realValidation: [
    "Real-world validation",
    "Align independent references and evaluate separate collection conditions.",
  ],
  traffic: [
    "Traffic Intelligence",
    "Count directional crossings and explore source-time traffic evidence.",
  ],
  methodology: [
    "Built to be measured.",
    "The methods, assumptions, and limits behind this observation workspace.",
  ],
};

function Metric({
  label,
  value,
  unit,
  note,
  icon,
}: {
  label: string;
  value: string;
  unit?: string;
  note: string;
  icon: IconName;
}) {
  return (
    <div className="metric-card">
      <div className="metric-label">
        <span>{label}</span>
        <Icon name={icon} size={17} />
      </div>
      <div className="metric-value">
        {value}
        <span>{unit}</span>
      </div>
      <p>{note}</p>
    </div>
  );
}

export default function App() {
  const [section, setSection] = useState<Section>(
    window.location.hash === "#showcase" ? "showcase" : "dashboard",
  );
  const [calibrationOpened, setCalibrationOpened] = useState(false);
  const [validationOpened, setValidationOpened] = useState(false);
  const [fieldOpened, setFieldOpened] = useState(false);
  const [trafficOpened, setTrafficOpened] = useState(false);
  const [fieldView, setFieldView] = useState<"sessions" | "validation">(
    "sessions",
  );
  const {
    session,
    health,
    connected,
    busy,
    actionError,
    setActionError,
    start,
    control,
    perform,
  } = useSession();
  function openCalibration() {
    setCalibrationOpened(true);
    setSection("calibration");
  }
  function openShowcaseView(view: ShowcaseView) {
    if (view === "calibration") openCalibration();
    else {
      if (view === "traffic") setTrafficOpened(true);
      if (view === "validation") setValidationOpened(true);
      setSection(view);
    }
  }
  const active = ["starting", "running", "paused"].includes(session.state);
  const hasFrames = session.frame_index > 0;
  const modelReady = health?.model.ready ?? false;
  const metrics = (value: number | null) =>
    hasFrames && value !== null && Number.isFinite(value)
      ? value.toFixed(1)
      : "—";

  return (
    <div className="app-shell">
      <a className="skip-link" href="#main">
        Skip to content
      </a>
      <aside className="sidebar">
        <a
          className="brand"
          href="#dashboard"
          onClick={(event) => {
            event.preventDefault();
            setSection("dashboard");
          }}
          aria-label="RoadLens Radar dashboard"
        >
          <span className="brand-mark">
            <Icon name="target" size={25} />
          </span>
          <span>
            roadlens<span className="brand-subtitle">RADAR</span>
          </span>
        </a>
        <span className="sidebar-label">WORKSPACE</span>
        <nav aria-label="Main navigation">
          {(
            [
              { id: "dashboard", icon: "dashboard", label: "Dashboard" },
              { id: "showcase", icon: "play", label: "Guided showcase" },
              { id: "sources", icon: "camera", label: "Camera & video" },
              { id: "traffic", icon: "pulse", label: "Traffic Intelligence" },
              {
                id: "calibration",
                icon: "target",
                label: "Calibration & gates",
              },
              {
                id: "validation",
                icon: "pulse",
                label: "Validation & benchmarks",
              },
              { id: "fields", icon: "book", label: "Field sessions" },
              {
                id: "realValidation",
                icon: "target",
                label: "Real-world validation",
              },
              { id: "methodology", icon: "book", label: "Methodology" },
            ] as const
          ).map((item) => (
            <button
              key={item.id}
              className={`nav-item ${section === item.id ? "active" : ""}`}
              aria-current={section === item.id ? "page" : undefined}
              onClick={() => {
                if (item.id === "calibration") openCalibration();
                else {
                  if (item.id === "validation") setValidationOpened(true);
                  if (item.id === "traffic") setTrafficOpened(true);
                  if (item.id === "fields" || item.id === "realValidation") {
                    setFieldOpened(true);
                    setFieldView(
                      item.id === "realValidation" ? "validation" : "sessions",
                    );
                  }
                  setSection(item.id);
                }
              }}
              title={item.label}
            >
              <Icon name={item.icon} size={18} />
              {item.label}
              {section === item.id && <span className="nav-active-dot" />}
            </button>
          ))}
        </nav>
        <div className="sidebar-bottom">
          <div className="local-box">
            <Icon name="chip" size={18} />
            <div>
              <strong>Local workspace</strong>
              <span>CPU · private by default</span>
            </div>
            <span className={`status-dot ${connected ? "green" : ""}`} />
          </div>
          <div className="sidebar-version">
            <span>PHASE 06</span>
            <span>v1.0.0</span>
          </div>
        </div>
      </aside>

      <div className="workspace">
        <header className="topbar">
          <div className="breadcrumb">
            Workspace
            <Icon name="chevron" size={13} />
            <span>
              {section === "showcase"
                ? "Guided showcase"
                : section === "traffic"
                  ? "Traffic Intelligence"
                  : section === "sources"
                    ? "Camera & video"
                    : section === "calibration"
                      ? "Calibration & gates"
                      : section === "validation"
                        ? "Validation & benchmarks"
                        : section === "fields"
                          ? "Field sessions"
                          : section === "realValidation"
                            ? "Real-world validation"
                            : section === "methodology"
                              ? "Methodology"
                              : "Dashboard"}
            </span>
          </div>
          <div className="topbar-status">
            <span className="local-tag">LOCAL</span>
            <span
              className={`status-dot ${connected ? "green" : connected === false ? "red" : ""}`}
            />
            <span>
              {connected === null
                ? "Connecting to backend"
                : connected
                  ? "Backend connected"
                  : "Backend disconnected"}
            </span>
          </div>
        </header>
        <main id="main">
          <div className="page-heading">
            <div>
              <div className="eyebrow">
                ROADLENS RADAR <span>/</span> VEHICLE OBSERVATION
              </div>
              <h1>{titles[section][0]}</h1>
              <p>{titles[section][1]}</p>
            </div>
            <div className="phase-badge">
              <span className="status-dot" />
              Measurement quality engineering
            </div>
          </div>

          {connected === false && section !== "showcase" && (
            <div className="alert error-alert" role="alert">
              <Icon name="info" size={19} />
              <div>
                <strong>The local backend is unavailable.</strong>
                <p>
                  Start the API on 127.0.0.1:8000. This workspace will reconnect
                  automatically.
                </p>
              </div>
            </div>
          )}
          {actionError && (
            <div className="alert error-alert" role="alert">
              <Icon name="info" size={19} />
              <div>
                <strong>Could not complete the request</strong>
                <p>{actionError}</p>
              </div>
              <button
                className="icon-button"
                aria-label="Dismiss request error"
                onClick={() => setActionError(null)}
              >
                <Icon name="close" size={18} />
              </button>
            </div>
          )}
          {session.error && (
            <div className="alert error-alert" role="alert">
              <Icon name="camera" size={19} />
              <div>
                <strong>Source error</strong>
                <p>{session.error}</p>
              </div>
            </div>
          )}
          {connected && health && !modelReady && (
            <div className="alert" role="status">
              <Icon name="info" size={19} />
              <div>
                <strong>Detector weights are not available.</strong>
                <p>
                  Run the model download command from the README, then start an
                  observation.
                </p>
              </div>
            </div>
          )}

          {section === "showcase" && <Showcase onOpenView={openShowcaseView} />}
          {section === "methodology" && <Methodology />}
          {trafficOpened && (
            <div hidden={section !== "traffic"}>
              <TrafficWorkspace
                session={session}
                connected={Boolean(connected)}
                visible={section === "traffic"}
                onSession={(updated) => {
                  void perform(async () => updated);
                }}
              />
            </div>
          )}
          {fieldOpened && (
            <div hidden={section !== "fields" && section !== "realValidation"}>
              <FieldWorkspace
                session={session}
                connected={Boolean(connected)}
                perform={perform}
                view={fieldView}
              />
            </div>
          )}
          {validationOpened && (
            <div hidden={section !== "validation"}>
              <ValidationBenchmarks connected={Boolean(connected)} />
            </div>
          )}
          {calibrationOpened && (
            <div hidden={section !== "calibration"}>
              <CalibrationStudio
                session={session}
                connected={Boolean(connected)}
                perform={perform}
              />
            </div>
          )}
          <div
            hidden={
              section === "methodology" ||
              section === "calibration" ||
              section === "validation" ||
              section === "fields" ||
              section === "realValidation" ||
              section === "traffic" ||
              section === "showcase"
            }
          >
            {section === "dashboard" && (
              <section className="panel showcase-dashboard-banner">
                <div>
                  <h2>Explore RoadLens without a camera</h2>
                  <p>
                    Follow ten guided steps using clearly labeled synthetic
                    fixtures and stored benchmark reports.
                  </p>
                </div>
                <button
                  className="button button-secondary"
                  onClick={() => setSection("showcase")}
                >
                  <Icon name="play" size={14} /> Start guided demo
                </button>
              </section>
            )}
            <div className="calibration-banner">
              <span className="calibration-icon">
                <Icon name="target" size={20} />
              </span>
              <div>
                <strong>
                  {session.calibration_status === "ready"
                    ? "Road-plane calibration active"
                    : "Calibration required"}
                </strong>
                <p>
                  {session.calibration_status === "ready"
                    ? "Estimated speeds require complete gate crossings and reliable source timing. Reapply after moving or zooming the camera."
                    : session.calibration_status === "incompatible"
                      ? "The calibration does not match this source geometry. Load a compatible profile before measuring speed."
                      : "Vehicle detection is available. Measure road-plane references, validate a profile, and configure two gates to estimate speed."}
                </p>
                {session.calibration_warnings?.map((warning) => (
                  <p key={warning}>{warning}</p>
                ))}
              </div>
              <button className="text-button" onClick={openCalibration}>
                Open calibration
                <Icon name="arrow" size={15} />
              </button>
            </div>

            <div className="metric-grid">
              <Metric
                label="Capture rate"
                value={metrics(session.capture_fps)}
                unit="fps"
                note="Measured at frame acquisition"
                icon="camera"
              />
              <Metric
                label="Processing rate"
                value={metrics(session.processing_fps)}
                unit="fps"
                note="Actual detection pipeline throughput"
                icon="pulse"
              />
              <Metric
                label="Processing latency"
                value={metrics(session.latency_ms)}
                unit="ms"
                note="Frame acquisition to processed result"
                icon="clock"
              />
              <Metric
                label="Confirmed tracks"
                value={
                  session.session_id
                    ? session.total_tracks.toLocaleString()
                    : "—"
                }
                note="Cumulative in this observation"
                icon="car"
              />
            </div>

            <div
              className={`observation-layout ${section === "sources" ? "source-view" : ""}`}
            >
              <div className="observation-main">
                <Preview session={session} />
                <OverlayControls
                  session={session}
                  disabled={!connected || busy}
                  onChange={(overlays) =>
                    void perform(() => api.overlays(overlays))
                  }
                />
                <div className="session-toolbar">
                  <div>
                    <span
                      className={`status-dot ${session.state === "running" ? "green" : ""}`}
                    />
                    <strong>{stateLabels[session.state]}</strong>
                    <span className="session-time mono">
                      {hasFrames ? elapsed(session.timestamp_s) : "00:00.0"}
                    </span>
                  </div>
                  <div className="toolbar-buttons">
                    <button
                      className="button button-secondary compact"
                      disabled={
                        busy ||
                        !connected ||
                        !["running", "paused"].includes(session.state)
                      }
                      onClick={() =>
                        void control(
                          session.state === "paused" ? "resume" : "pause",
                        )
                      }
                    >
                      <Icon
                        name={session.state === "paused" ? "play" : "pause"}
                        size={14}
                      />
                      {session.state === "paused" ? "Resume" : "Pause"}
                    </button>
                    <button
                      className="button button-secondary compact"
                      disabled={busy || !connected || !active}
                      onClick={() => void control("stop")}
                    >
                      <Icon name="stop" size={13} />
                      Stop
                    </button>
                    <button
                      className="icon-button reset-button"
                      aria-label="Reset session"
                      title="Reset session and clear tracks"
                      disabled={busy || !connected || session.state === "idle"}
                      onClick={() => void control("reset")}
                    >
                      <Icon name="reset" size={17} />
                    </button>
                  </div>
                </div>
                {section === "dashboard" ? (
                  <>
                    <SpeedPanel
                      session={session}
                      onClear={() =>
                        void perform(() => api.clearMeasurements())
                      }
                    />
                    <div className="section-heading">
                      <h2>Vehicles observed</h2>
                      <span>Confirmed tracks · current session</span>
                    </div>
                    <div className="category-grid">
                      {categories.map(({ key, label, icon }) => (
                        <div
                          className={`category-card category-${key}`}
                          key={key}
                        >
                          <span className="category-icon">
                            <Icon name={icon} size={21} />
                          </span>
                          <span>
                            <strong>
                              {session.session_id
                                ? session.counts[key].toLocaleString()
                                : "—"}
                            </strong>
                            <span>{label}</span>
                          </span>
                        </div>
                      ))}
                    </div>
                    <TrackTable session={session} />
                  </>
                ) : (
                  <section className="panel prose-panel source-explainer">
                    <h2>A reliable source comes first.</h2>
                    <p>
                      Use a stationary camera with a clear view, or select a
                      local video for reproducible runs. Start opens the device;
                      Stop releases camera access. Reset stops processing and
                      clears session tracks and statistics.
                    </p>
                    <p>
                      Camera resolution is a request to the device. Inspect the
                      actual dimensions and measured frame rate in source
                      diagnostics. Recorded video keeps its original source
                      timing where supported; processing may run slower than
                      playback.
                    </p>
                    <p>
                      Stop the current observation before changing input or
                      detection settings. Camera discovery briefly opens
                      candidate devices and is available while no observation is
                      running.
                    </p>
                  </section>
                )}
              </div>
              <div className="observation-side">
                <SourceControls
                  locked={active}
                  canStart={Boolean(connected && modelReady)}
                  busy={busy}
                  activeSource={{
                    type: session.source_type,
                    label: session.source_label,
                  }}
                  onStart={(options) => void start(options)}
                />
                <Diagnostics session={session} />
                <div className="detector-note">
                  <span className={`status-dot ${modelReady ? "green" : ""}`} />
                  <div>
                    <strong>{health?.model.name || "YOLOX-S · INT8"}</strong>
                    <p>
                      {modelReady
                        ? "Model available · OpenCV DNN · CPU"
                        : "Waiting for detector weights"}
                    </p>
                  </div>
                </div>
              </div>
            </div>
          </div>
          <footer className="workspace-footer">
            <span>
              RoadLens Radar <span>·</span> Computer vision engineering
              workspace
            </span>
            <span>
              <Icon name="shield" size={13} />
              No speed or accuracy claims without calibration and validation
            </span>
          </footer>
        </main>
      </div>
    </div>
  );
}
