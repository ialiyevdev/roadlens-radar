import type { RefObject, MouseEvent, PointerEvent } from "react";
import Icon from "./Icon";
import type {
  CalibrationDiagnostics,
  FrozenFrame,
  Point,
  Segment,
} from "./types";
import type { ReferenceRow, Mode, Drag } from "./calibrationCoordinates";

interface Props {
  frame: FrozenFrame | null;
  diagnostics: CalibrationDiagnostics | null;
  rows: ReferenceRow[];
  showGrid: boolean;
  setShowGrid: (show: boolean) => void;
  mode: Mode;
  setMode: (mode: Mode) => void;
  a: Segment | null;
  b: Segment | null;
  pending: Point | null;
  ready: boolean;
  canFreeze: boolean;
  busy: boolean;
  freeze: () => Promise<void>;
  svg: RefObject<SVGSVGElement | null>;
  addPoint: (event: MouseEvent<SVGSVGElement>) => void;
  move: (event: PointerEvent<SVGSVGElement>) => void;
  endDrag: () => void;
  startDrag: (event: PointerEvent<SVGCircleElement>, target: Drag) => void;
}
export default function CalibrationFrame({
  frame,
  diagnostics,
  rows,
  showGrid,
  setShowGrid,
  mode,
  setMode,
  a,
  b,
  pending,
  ready,
  canFreeze,
  busy,
  freeze,
  svg,
  addPoint,
  move,
  endDrag,
  startDrag,
}: Props) {
  const size = frame ? Math.max(frame.geometry.width / 90, 5) : 7;
  return (
    <section className="panel calibration-canvas-panel">
      <div className="preview-heading">
        <div>
          <h2>Road-plane reference frame</h2>
          <p className="field-note">
            {frame
              ? `${frame.geometry.width} × ${frame.geometry.height} ${frame.geometry.coordinate_space === "undistorted" ? "undistorted" : "source"} pixels · unannotated snapshot`
              : "Start a source in Camera & video, then freeze a frame."}
          </p>
        </div>
        <button
          className="button button-primary compact"
          disabled={!canFreeze || busy}
          onClick={() => void freeze()}
        >
          <Icon name="camera" size={14} />
          Freeze frame
        </button>
      </div>
      {frame ? (
        <>
          <div
            className="calibration-canvas"
            style={{
              aspectRatio: `${frame.geometry.width} / ${frame.geometry.height}`,
            }}
          >
            <svg
              ref={svg}
              viewBox={`0 0 ${frame.geometry.width} ${frame.geometry.height}`}
              preserveAspectRatio="xMidYMid meet"
              aria-label="Frozen road frame: click to add reference points or gate endpoints"
              role="img"
              onClick={addPoint}
              onPointerMove={move}
              onPointerUp={endDrag}
              onPointerCancel={endDrag}
            >
              <defs>
                <marker
                  id="direction-arrow"
                  markerWidth="8"
                  markerHeight="8"
                  refX="7"
                  refY="4"
                  orient="auto"
                >
                  <path d="M0 0 8 4 0 8" fill="#e7d49c" />
                </marker>
              </defs>
              <image
                href={frame.image_url}
                width={frame.geometry.width}
                height={frame.geometry.height}
              />
              {diagnostics?.valid && (
                <polygon
                  className="calibration-region"
                  points={diagnostics.region_image
                    .map((point) => point.join(","))
                    .join(" ")}
                />
              )}
              {showGrid &&
                diagnostics?.valid &&
                diagnostics.grid_image.map((line, i) => (
                  <polyline
                    key={i}
                    className="calibration-grid-line"
                    points={line.map((point) => point.join(",")).join(" ")}
                  />
                ))}
              {(
                [
                  ["A", a],
                  ["B", b],
                ] as const
              ).map(
                ([label, segment]) =>
                  segment &&
                  segment.flat().every(Number.isFinite) && (
                    <g key={label} className={`gate-drawing gate-${label}`}>
                      <line
                        x1={segment[0][0]}
                        y1={segment[0][1]}
                        x2={segment[1][0]}
                        y2={segment[1][1]}
                        strokeWidth={size / 2}
                      />
                      <text
                        x={(segment[0][0] + segment[1][0]) / 2}
                        y={(segment[0][1] + segment[1][1]) / 2 - size}
                        fontSize={size * 2}
                      >
                        Gate {label}
                      </text>
                      {segment.map((p, i) => (
                        <circle
                          key={i}
                          cx={p[0]}
                          cy={p[1]}
                          r={size}
                          onPointerDown={(event) =>
                            startDrag(event, { gate: label, endpoint: i })
                          }
                        />
                      ))}
                    </g>
                  ),
              )}
              {a &&
                b &&
                a.flat().every(Number.isFinite) &&
                b.flat().every(Number.isFinite) && (
                  <line
                    className="gate-direction"
                    x1={(a[0][0] + a[1][0]) / 2}
                    y1={(a[0][1] + a[1][1]) / 2}
                    x2={(b[0][0] + b[1][0]) / 2}
                    y2={(b[0][1] + b[1][1]) / 2}
                    strokeWidth={size / 3}
                    markerEnd="url(#direction-arrow)"
                  />
                )}
              {rows.map(
                (row, index) =>
                  row.image.every(Number.isFinite) && (
                    <g
                      key={row.id}
                      className={
                        row.check
                          ? "reference-point check-point"
                          : "reference-point"
                      }
                    >
                      <circle
                        cx={row.image[0]}
                        cy={row.image[1]}
                        r={size * 1.3}
                        onPointerDown={(event) =>
                          startDrag(event, { row: row.id })
                        }
                      />
                      <text
                        x={row.image[0]}
                        y={row.image[1] + size * 0.55}
                        textAnchor="middle"
                        fontSize={size * 1.65}
                      >
                        {index + 1}
                      </text>
                    </g>
                  ),
              )}
              {pending && (
                <circle
                  cx={pending[0]}
                  cy={pending[1]}
                  r={size}
                  fill="#e7d49c"
                />
              )}
            </svg>
          </div>
          <div className="canvas-tools">
            <div className="segmented" aria-label="Frame editing mode">
              {(
                [
                  ["points", "Add references"],
                  ["A", "Draw Gate A"],
                  ["B", "Draw Gate B"],
                ] as const
              ).map(([value, label]) => (
                <button
                  key={value}
                  aria-pressed={mode === value}
                  onClick={() => {
                    setMode(value);
                  }}
                  disabled={value !== "points" && !ready}
                >
                  {label}
                </button>
              ))}
            </div>
            <label className="check-label">
              <input
                type="checkbox"
                checked={showGrid}
                onChange={(event) => setShowGrid(event.target.checked)}
              />
              Ground-plane grid
            </label>
          </div>
          <p className="canvas-help">
            {mode === "points"
              ? "Click to add a reference. Drag a numbered marker to adjust it; enter measured coordinates below."
              : `Click ${pending ? "the second" : "the first"} endpoint of Gate ${mode}. Drag endpoints or edit their source pixels below.`}
          </p>
        </>
      ) : (
        <div className="calibration-placeholder">
          <Icon name="target" size={36} />
          <h3>No frozen reference frame</h3>
          <p>
            Calibration uses your actual source. No example scale is applied.
          </p>
        </div>
      )}
    </section>
  );
}
