import { useRef, useState } from "react";
import type { KeyboardEvent } from "react";
import Icon from "./Icon";
import TrackTable from "./TrackTable";
import TrafficCharts, { TrafficBarChart } from "./TrafficCharts";
import {
  showcaseAnalysis,
  showcaseArtifact,
  showcaseBenchmarks,
  showcaseDownloads,
  showcaseGeometry,
  showcaseTracks,
  showcaseTrajectories,
} from "./showcaseData";
import "./traffic.css";
import "./showcase.css";

export type ShowcaseView = "sources" | "calibration" | "traffic" | "validation";
export const showcaseSteps: {
  title: string;
  detail: string;
  view: ShowcaseView;
  viewLabel: string;
}[] = [
  {
    title: "Vehicle detection",
    detail:
      "The full application runs YOLOX-S INT8 on CPU through OpenCV DNN. This scene uses known synthetic boxes, so exploring it runs no model inference.",
    view: "sources",
    viewLabel: "Camera & video",
  },
  {
    title: "Multi-object tracking",
    detail:
      "Temporary IDs connect observations using global association, category checks and motion estimates. Trails below connect the stored fixture positions; they do not demonstrate real occlusion recovery.",
    view: "sources",
    viewLabel: "Camera & video",
  },
  {
    title: "Perspective calibration",
    detail:
      "Measured image-to-road correspondences define a planar homography. Held-out check points and geometry compatibility determine whether positions can be used for measurement.",
    view: "calibration",
    viewLabel: "Calibration & gates",
  },
  {
    title: "Virtual speed gates",
    detail:
      "Two finite gate segments delimit a measurement. Observed contacts are mapped to the road plane; finite gate crossings are interpolated using source timestamps.",
    view: "calibration",
    viewLabel: "Calibration & gates",
  },
  {
    title: "Speed & diagnostics",
    detail:
      "Distance divided by source-time elapsed gives speed. Valid, approximate and rejected measurements stay distinct; a valid software status does not establish real-world accuracy.",
    view: "calibration",
    viewLabel: "Calibration & gates",
  },
  {
    title: "Directional vehicle counting",
    detail:
      "Counting lines are independent of speed gates. Stable sides outside a hysteresis band and a finite-segment intersection produce a source-timed crossing event.",
    view: "traffic",
    viewLabel: "Traffic Intelligence",
  },
  {
    title: "Vehicle classification",
    detail:
      "Confidence-weighted class evidence is retained per temporary track. Low evidence remains unknown. These class counts come from the stored synthetic export, with no learned prediction here.",
    view: "traffic",
    viewLabel: "Traffic Intelligence",
  },
  {
    title: "Monitoring zones",
    detail:
      "Polygon zones record visible occupancy, entries, exits and observed dwell. Missing observations interrupt dwell; image occupancy and stationary heuristics do not measure physical queue length.",
    view: "traffic",
    viewLabel: "Traffic Intelligence",
  },
  {
    title: "Traffic analytics",
    detail:
      "The same native SVG charts used in the live workspace display stored exports. Coverage controls normalized rates; short observations cannot establish hourly traffic volume.",
    view: "traffic",
    viewLabel: "Traffic Intelligence",
  },
  {
    title: "Validation & benchmarking",
    detail:
      "Reviewed trajectories, independent references and held-out evaluation address different questions. The reports below measure software behavior and cost. Physical roadway accuracy remains unverified.",
    view: "validation",
    viewLabel: "Validation & benchmarks",
  },
];

function TrajectoryScene({ step }: { step: number }) {
  const [frameIndex, setFrameIndex] = useState(8);
  const frame = showcaseTrajectories.frames[frameIndex];
  const config = showcaseArtifact.configuration!;
  const showLine = step === 5;
  const showZone = step === 7;
  const showTrails = step !== 0;
  const tracks = showcaseTracks(frameIndex);
  return (
    <section
      className="panel showcase-scene"
      aria-labelledby="fixture-scene-title"
    >
      <div className="panel-heading">
        <h3 id="fixture-scene-title">Stored trajectory explorer</h3>
        <span className="showcase-stored-tag">KNOWN BOXES · NO INFERENCE</span>
      </div>
      <svg
        viewBox="0 0 200 120"
        role="img"
        aria-label={`Synthetic fixture frame ${frame.index}, source time ${frame.timestamp_s.toFixed(1)} seconds`}
      >
        <rect width="200" height="120" className="showcase-canvas" />
        {[40, 80, 120, 160].map((x) => (
          <line
            key={x}
            x1={x}
            x2={x}
            y1="0"
            y2="120"
            className="showcase-grid-line"
          />
        ))}
        {[30, 60, 90].map((y) => (
          <line
            key={y}
            y1={y}
            y2={y}
            x1="0"
            x2="200"
            className="showcase-grid-line"
          />
        ))}
        {showZone &&
          config.zones.map((zone) => (
            <polygon
              key={zone.id}
              points={zone.points.map((point) => point.join(",")).join(" ")}
              className="showcase-zone"
            />
          ))}
        {showLine &&
          config.lines.map((line) => (
            <g key={line.id}>
              <line
                x1={line.start[0]}
                y1={line.start[1]}
                x2={line.end[0]}
                y2={line.end[1]}
                className="showcase-count-line"
              />
              <text x="114" y="55" className="showcase-scene-label">
                Count line · down image ↓
              </text>
            </g>
          ))}
        {frame.tracks.map((track) => {
          const [x1, y1, x2, y2] = track.bbox;
          const history = tracks.find((item) => item.id === track.id)?.history;
          return (
            <g key={track.id}>
              {showTrails && history && (
                <polyline
                  points={history.map((point) => point.join(",")).join(" ")}
                  className="showcase-trail"
                />
              )}
              <rect
                x={x1}
                y={y1}
                width={x2 - x1}
                height={y2 - y1}
                className="showcase-box"
              />
              <circle
                cx={(x1 + x2) / 2}
                cy={y2}
                r="1.4"
                className="showcase-contact"
              />
              <text
                x={Math.min(x1, 150)}
                y={y1 < 12 ? y2 + 7 : y1 - 4}
                className="showcase-scene-label"
              >
                {showTrails ? `#${track.id} · ` : ""}
                {track.category} · known input
              </text>
            </g>
          );
        })}
      </svg>
      <label className="showcase-scrubber">
        Explore stored source frames
        <input
          type="range"
          min="0"
          max={showcaseTrajectories.frames.length - 1}
          value={frameIndex}
          onChange={(event) => setFrameIndex(Number(event.target.value))}
        />
      </label>
      <p className="field-note">
        Frame {frame.index} / {showcaseTrajectories.frames.length} ·{" "}
        {frame.timestamp_s.toFixed(1)} source seconds · 200 × 120 fixture
        coordinates. Scrubbing selects stored inputs; no video or camera is
        running.
      </p>
      {step === 1 && (
        <>
          <p className="field-note">
            Shared live-workspace track table, populated with scripted fixture
            observations. Confidence values are supplied inputs. The live table
            shows supported vehicle categories; unsupported raw fixture inputs
            remain visible in the scene and become unknown in traffic summaries.
          </p>
          <TrackTable session={{ tracks, calibration_status: "required" }} />
        </>
      )}
    </section>
  );
}

function GeometryScene({ gates }: { gates: boolean }) {
  return (
    <section className="panel showcase-scene">
      <h3>Known drawing geometry · separate speed fixture</h3>
      <svg
        viewBox="0 0 800 600"
        role="img"
        aria-label={
          gates
            ? "Synthetic speed fixture with two gates twenty metres apart"
            : "Synthetic image-to-road correspondences, sixty by forty-five metres"
        }
      >
        <rect width="800" height="600" className="showcase-canvas" />
        <polygon
          points={showcaseGeometry.points
            .map((point) => point.join(","))
            .join(" ")}
          className="showcase-zone"
        />
        {[200, 300, 400, 500, 600].map((x) => (
          <line
            key={x}
            x1={x}
            x2={x}
            y1="100"
            y2="550"
            className="showcase-grid-line"
          />
        ))}
        {[200, 300, 400, 500].map((y) => (
          <line
            key={y}
            y1={y}
            y2={y}
            x1="100"
            x2="700"
            className="showcase-grid-line"
          />
        ))}
        {showcaseGeometry.points.map(([x, y], i) => (
          <g key={i}>
            <circle cx={x} cy={y} r="6" className="showcase-contact" />
            <text x={x + 10} y={y - 12} className="showcase-geometry-label">
              P{i + 1} ·{" "}
              {[
                [0, 0],
                [60, 0],
                [60, 45],
                [0, 45],
              ][i].join(", ")}{" "}
              m
            </text>
          </g>
        ))}
        {gates && (
          <>
            {[showcaseGeometry.gateA, showcaseGeometry.gateB].map(
              (gate, index) => (
                <g key={index}>
                  <line
                    x1={gate[0][0]}
                    y1={gate[0][1]}
                    x2={gate[1][0]}
                    y2={gate[1][1]}
                    className="showcase-gate"
                  />
                  <text
                    x={gate[0][0] - 26}
                    y="180"
                    className="showcase-geometry-label"
                  >
                    Gate {index === 0 ? "A" : "B"}
                  </text>
                </g>
              ),
            )}
            <line
              x1="200"
              y1="330"
              x2="400"
              y2="330"
              className="showcase-trail"
            />
            <text x="260" y="310" className="showcase-geometry-label">
              20 m
            </text>
          </>
        )}
      </svg>
      <p className="field-note">
        Coordinates reproduce the generated drawing in
        scripts/run_validation.py. The 0.1 m/pixel mapping is deliberately
        simple; this illustration does not validate a physical perspective
        calibration.
      </p>
    </section>
  );
}

function SpeedExample() {
  const { distance_m, elapsed_seconds } = showcaseGeometry;
  return (
    <section className="panel showcase-speed">
      <span className="eyebrow">KNOWN GEOMETRY · SCRIPTED TIMING</span>
      <h3>Inspect the arithmetic</h3>
      <div className="showcase-formula mono">
        {distance_m} m ÷ {elapsed_seconds.toFixed(1)} s × 3.6 ={" "}
        <strong>
          {((distance_m / elapsed_seconds) * 3.6).toFixed(1)} km/h
        </strong>
      </div>
      <p>
        This separate generated speed fixture checks unit conversion and
        source-time handling. It has no independent road measurement.
      </p>
      <dl className="showcase-diagnostics">
        <div>
          <dt>Valid</dt>
          <dd>
            Both gates crossed with compatible calibration and acceptable
            timing/position diagnostics.
          </dd>
        </div>
        <div>
          <dt>Approximate</dt>
          <dd>An estimate exists with warnings that need inspection.</dd>
        </div>
        <div>
          <dt>Rejected</dt>
          <dd>Measurement prerequisites or diagnostic checks fail.</dd>
        </div>
      </dl>
    </section>
  );
}

function BenchmarkEvidence() {
  const { counting, model, traffic } = showcaseBenchmarks;
  return (
    <section className="panel showcase-benchmarks">
      <h3>Stored reports · three separate workloads</h3>
      <div className="table-scroll">
        <table>
          <thead>
            <tr>
              <th>Evidence</th>
              <th>Result</th>
              <th>Scope</th>
            </tr>
          </thead>
          <tbody>
            <tr>
              <td>Synthetic counting engine</td>
              <td>
                {counting.expectations_met}/{counting.scenario_count} scenarios;{" "}
                {counting.actual_crossings}/{counting.expected_crossings}{" "}
                crossings
              </td>
              <td>
                Known trajectory inputs. Includes {counting.actual_suppressed}{" "}
                expected identity suppression; excludes detector and tracker.
              </td>
            </tr>
            <tr>
              <td>Actual YOLOX still replay</td>
              <td>
                {model.timings.detection_ms.mean_ms.toFixed(3)} ms/frame
                detection
              </td>
              <td>
                {model.frames} measured frames, input {model.input_size}; CC0
                still image replay on {model.hardware.cpu}. Objects do not move.
              </td>
            </tr>
            <tr>
              <td>Synthetic dense traffic</td>
              <td>
                {traffic.dense_traffic_per_frame.mean_ms.toFixed(3)} ms/frame
                traffic processing
              </td>
              <td>
                {traffic.workload.dense_tracks_per_frame} scripted tracks/frame
                over {traffic.workload.dense_frames} frames. Excludes model
                inference, decoding and browser.
              </td>
            </tr>
          </tbody>
        </table>
      </div>
      <p className="field-note">
        These results cannot be added into an end-to-end throughput claim. There
        is no independently verified real-field speed or counting accuracy
        result.
      </p>
    </section>
  );
}

export default function Showcase({
  onOpenView,
}: {
  onOpenView?: (view: ShowcaseView) => void;
}) {
  const [step, setStep] = useState(0);
  const heading = useRef<HTMLHeadingElement>(null);
  const current = showcaseSteps[step];
  function goTo(index: number) {
    setStep(Math.max(0, Math.min(showcaseSteps.length - 1, index)));
    requestAnimationFrame(() => heading.current?.focus());
  }
  function stepKeys(event: KeyboardEvent<HTMLDivElement>) {
    if (event.target !== event.currentTarget) return;
    if (event.key === "ArrowRight") {
      event.preventDefault();
      goTo(step + 1);
    }
    if (event.key === "ArrowLeft") {
      event.preventDefault();
      goTo(step - 1);
    }
    if (event.key === "Home") {
      event.preventDefault();
      goTo(0);
    }
    if (event.key === "End") {
      event.preventDefault();
      goTo(showcaseSteps.length - 1);
    }
  }
  return (
    <div className="showcase-workspace">
      <section className="panel showcase-intro">
        <span className="showcase-synthetic-label">
          <Icon name="info" size={16} /> SYNTHETIC DEMONSTRATION
        </span>
        <div className="showcase-intro-heading">
          <div>
            <h2>A guided look inside RoadLens</h2>
            <p>
              Ten steps through the measurement pipeline, with stored fixtures
              and shared workspace components.
            </p>
          </div>
          <span className="showcase-stored-tag">
            STORED OUTPUTS · NO ACTIVE INFERENCE
          </span>
        </div>
        <p className="showcase-evidence-note">
          No webcam, road video or model download is needed for this tour.
          Synthetic observations test software behavior. The benchmark step
          separately identifies actual-model still-image replay.
        </p>
      </section>
      <div className="showcase-layout">
        <nav className="panel showcase-steps" aria-label="Guided demo steps">
          <ol>
            {showcaseSteps.map((item, index) => (
              <li key={item.title}>
                <button
                  aria-label={`${String(index + 1).padStart(2, "0")} ${item.title}`}
                  aria-current={step === index ? "step" : undefined}
                  onClick={() => goTo(index)}
                >
                  <span className="mono">
                    {String(index + 1).padStart(2, "0")}
                  </span>
                  <span>{item.title}</span>
                  {step === index && <Icon name="chevron" size={14} />}
                </button>
              </li>
            ))}
          </ol>
        </nav>
        <div className="showcase-content">
          <section className="panel showcase-step-description">
            <p className="eyebrow" aria-live="polite">
              STEP {String(step + 1).padStart(2, "0")} / 10
            </p>
            <h2 tabIndex={-1} ref={heading}>
              {current.title}
            </h2>
            <p>{current.detail}</p>
            {onOpenView ? (
              <button
                className="text-button"
                onClick={() => onOpenView(current.view)}
              >
                Open {current.viewLabel}
                <Icon name="arrow" size={15} />
              </button>
            ) : (
              <p className="showcase-local-view">
                Explore {current.viewLabel} in the local full-stack application.
                Setup instructions are in the repository README.
              </p>
            )}
          </section>
          {[0, 1, 5, 7].includes(step) && <TrajectoryScene step={step} />}
          {[2, 3].includes(step) && <GeometryScene gates={step === 3} />}
          {step === 4 && <SpeedExample />}
          {step === 5 && (
            <section className="panel showcase-summary">
              <h3>Actual stored crossing export</h3>
              <p>
                <strong>
                  {showcaseAnalysis.summary.total_crossings} crossings
                </strong>{" "}
                over {showcaseAnalysis.summary.coverage_seconds} covered source
                seconds. All six scripted trajectories cross “Down image”.
              </p>
              <p className="field-note">
                This counting fixture has no road-plane calibration. Its
                attached speed values are separately scripted to test filtering
                and summaries.
              </p>
            </section>
          )}
          {step === 6 && (
            <TrafficBarChart
              title="Vehicle-class distribution"
              rows={showcaseAnalysis.classes.map((row) => ({
                label: row.category,
                value: row.count,
                note: `${(row.fraction * 100).toFixed(1)}% of the six synthetic crossings`,
              }))}
              unit="crossings"
            />
          )}
          {step === 7 && (
            <section className="panel showcase-summary">
              <h3>Stored zone observations</h3>
              {showcaseAnalysis.zones.map((zone) => (
                <p key={zone.zone_id}>
                  {zone.entries} entries · {zone.exits} exits ·{" "}
                  {zone.mean_dwell_s?.toFixed(1)} s mean observed dwell in “
                  {zone.zone_label}”.
                </p>
              ))}
              <p className="field-note">
                Generated image-coordinate observations only; occupancy is a
                count of tracked objects in a polygon.
              </p>
            </section>
          )}
          {step === 8 && (
            <>
              <section className="panel showcase-summary">
                <h3>Synthetic traffic example</h3>
                <p>
                  {showcaseAnalysis.summary.total_crossings} crossings ·{" "}
                  {showcaseAnalysis.summary.coverage_seconds} covered seconds ·{" "}
                  {showcaseAnalysis.speeds.n} scripted valid speeds, mean{" "}
                  {showcaseAnalysis.speeds.mean_kmh} km/h.
                </p>
                <p className="field-note">
                  The 60-second interval has 59.5 seconds of coverage and is
                  partial. Attached speeds test aggregation; they were not
                  measured by this counting fixture.
                </p>
              </section>
              <TrafficCharts analysis={showcaseAnalysis} />
            </>
          )}
          {step === 9 && <BenchmarkEvidence />}
          <div
            className="showcase-navigation"
            role="group"
            aria-label="Step navigation"
            tabIndex={0}
            onKeyDown={stepKeys}
          >
            <button
              className="button button-secondary"
              disabled={step === 0}
              onClick={() => goTo(step - 1)}
            >
              Previous step
            </button>
            <span className="mono">
              {step + 1} of {showcaseSteps.length}
            </span>
            <button
              className="button button-primary"
              disabled={step === showcaseSteps.length - 1}
              onClick={() => goTo(step + 1)}
            >
              Next step
              <Icon name="arrow" size={15} />
            </button>
          </div>
          <p className="showcase-keyboard-hint">
            Tab to the step navigation group and use ← / →, Home or End. Every
            step is also available in the numbered navigation.
          </p>
        </div>
      </div>
      <section className="panel showcase-downloads">
        <h2>Inspect the evidence</h2>
        <p>
          Original repository JSON files, bundled with this build. Synthetic
          files contain no independent ground truth.
        </p>
        <div>
          {showcaseDownloads.map((asset) => (
            <a key={asset.label} href={asset.url} download>
              {asset.label}
              <Icon name="arrow" size={13} />
            </a>
          ))}
        </div>
      </section>
    </div>
  );
}
