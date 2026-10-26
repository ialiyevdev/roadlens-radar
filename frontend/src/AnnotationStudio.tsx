import { useEffect, useRef, useState } from "react";
import type { PointerEvent } from "react";
import { annotationApi } from "./annotationApi";
import type {
  AnnotatedFrame,
  AnnotationDocument,
  AnnotationFrameInfo,
  GroundTruthObject,
} from "./annotationApi";
import type { Category } from "./types";
import "./annotation.css";

type Point = [number, number];
type Drag = {
  start: Point;
  original?: GroundTruthObject["bbox"];
  identity?: string;
  resize?: boolean;
};
const emptyFrame = (
  index: number,
  timestamp: number | null,
): AnnotatedFrame => ({
  index,
  timestamp_s: timestamp,
  reviewed: false,
  objects: [],
  predictions: [],
});
const message = (error: unknown) =>
  error instanceof Error ? error.message : "The annotation request failed.";

export default function AnnotationStudio({
  fieldSessionId,
  connected,
  onSaved,
}: {
  fieldSessionId: string;
  connected: boolean;
  onSaved?: () => void;
}) {
  const [document, setDocument] = useState<AnnotationDocument | null>(null);
  const [frame, setFrame] = useState<AnnotationFrameInfo | null>(null);
  const [index, setIndex] = useState(1);
  const [indexDraft, setIndexDraft] = useState("1");
  const [timestampDraft, setTimestampDraft] = useState("");
  const [identity, setIdentity] = useState("vehicle-001");
  const [category, setCategory] = useState<Category>("car");
  const [selected, setSelected] = useState<string | null>(null);
  const [pendingBox, setPendingBox] = useState<GroundTruthObject["bbox"]>(null);
  const [tracker, setTracker] = useState("improved");
  const [busy, setBusy] = useState(false);
  const [dirty, setDirty] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [notice, setNotice] = useState<string | null>(null);
  const svg = useRef<SVGSVGElement>(null);
  const drag = useRef<Drag | null>(null);
  const sequence = useRef(0);
  const current =
    document?.frames.find((item) => item.index === index) ??
    emptyFrame(index, frame?.timestamp_s ?? null);
  const object = current.objects.find((item) => item.identity === selected);

  useEffect(() => {
    let active = true;
    setDocument(null);
    setFrame(null);
    setIndex(1);
    setIndexDraft("1");
    setDirty(false);
    setError(null);
    annotationApi
      .get(fieldSessionId)
      .then((value) => {
        if (active) setDocument(value);
      })
      .catch((cause) => {
        if (active) setError(message(cause));
      });
    return () => {
      active = false;
      sequence.current++;
    };
  }, [fieldSessionId]);
  useEffect(() => {
    const request = ++sequence.current;
    setFrame(null);
    setSelected(null);
    setPendingBox(null);
    annotationApi
      .frame(fieldSessionId, index)
      .then((value) => {
        if (sequence.current === request) setFrame(value);
      })
      .catch((cause) => {
        if (sequence.current === request) setError(message(cause));
      });
  }, [fieldSessionId, index]);

  function updateFrame(changes: Partial<AnnotatedFrame>) {
    setDocument((previous) =>
      previous
        ? {
            ...previous,
            frames: [
              ...previous.frames.filter((item) => item.index !== index),
              {
                ...current,
                timestamp_s: frame?.timestamp_s ?? current.timestamp_s,
                ...changes,
              },
            ].sort((a, b) => a.index - b.index),
          }
        : previous,
    );
    setDirty(true);
    setNotice(null);
  }
  function updateObject(changes: Partial<GroundTruthObject>) {
    if (!object) return;
    updateFrame({
      objects: current.objects.map((item) =>
        item.identity === object.identity ? { ...item, ...changes } : item,
      ),
    });
  }
  function point(event: PointerEvent<SVGSVGElement>): Point | null {
    const target = svg.current;
    const matrix = target?.getScreenCTM();
    if (!target || !matrix || !frame) return null;
    const location = target.createSVGPoint();
    location.x = event.clientX;
    location.y = event.clientY;
    const local = location.matrixTransform(matrix.inverse());
    return [
      Math.max(0, Math.min(frame.width, local.x)),
      Math.max(0, Math.min(frame.height, local.y)),
    ];
  }
  function down(event: PointerEvent<SVGSVGElement>) {
    if (busy || !document || !frame) return;
    const start = point(event);
    if (!start) return;
    const element = event.target as SVGElement;
    const id = element.getAttribute("data-identity");
    const found = current.objects.find((item) => item.identity === id);
    if (found?.bbox) {
      setSelected(found.identity);
      drag.current = {
        start,
        identity: found.identity,
        original: found.bbox,
        resize: element.getAttribute("data-resize") === "true",
      };
    } else {
      setSelected(null);
      drag.current = { start };
      setPendingBox([start[0], start[1], start[0], start[1]]);
    }
    event.currentTarget.setPointerCapture?.(event.pointerId);
  }
  function move(event: PointerEvent<SVGSVGElement>) {
    const active = drag.current;
    const end = point(event);
    if (!active || !end || !frame) return;
    if (!active.original)
      setPendingBox([
        Math.min(active.start[0], end[0]),
        Math.min(active.start[1], end[1]),
        Math.max(active.start[0], end[0]),
        Math.max(active.start[1], end[1]),
      ]);
    else {
      const original = active.original;
      let box: [number, number, number, number];
      if (active.resize)
        box = [
          original[0],
          original[1],
          Math.max(original[0] + 1, end[0]),
          Math.max(original[1] + 1, end[1]),
        ];
      else {
        const dx = Math.max(
          -original[0],
          Math.min(frame.width - original[2], end[0] - active.start[0]),
        );
        const dy = Math.max(
          -original[1],
          Math.min(frame.height - original[3], end[1] - active.start[1]),
        );
        box = [
          original[0] + dx,
          original[1] + dy,
          original[2] + dx,
          original[3] + dy,
        ];
      }
      updateFrame({
        objects: current.objects.map((item) =>
          item.identity === active.identity ? { ...item, bbox: box } : item,
        ),
      });
    }
  }
  function addObject(box: GroundTruthObject["bbox"], occluded = false) {
    const label = identity.trim();
    const existing = current.objects.find((item) => item.identity === label);
    if (!label || (existing && !(existing.occluded && box))) {
      setError("Enter a unique ground-truth identity for this frame.");
      return;
    }
    updateFrame({
      objects: [
        ...current.objects.filter((item) => item.identity !== label),
        {
          identity: label,
          category,
          bbox: box,
          occluded,
          partial_visibility: false,
          entry: false,
          exit: false,
        },
      ],
    });
    setSelected(label);
    setError(null);
  }
  function up() {
    if (
      drag.current &&
      !drag.current.original &&
      pendingBox &&
      pendingBox[2] - pendingBox[0] >= 2 &&
      pendingBox[3] - pendingBox[1] >= 2
    )
      addObject(pendingBox);
    drag.current = null;
    setPendingBox(null);
  }
  function navigate(next: number) {
    if (
      busy ||
      !Number.isInteger(next) ||
      next < 1 ||
      (frame && next > frame.total_frames)
    )
      return;
    setIndex(next);
    setIndexDraft(String(next));
    setError(null);
  }
  useEffect(() => {
    function key(event: KeyboardEvent) {
      if (
        !svg.current?.getClientRects().length ||
        /INPUT|TEXTAREA|SELECT/.test((event.target as HTMLElement)?.tagName) ||
        busy
      )
        return;
      if (event.key === "ArrowRight" || event.key === "ArrowLeft") {
        event.preventDefault();
        navigate(index + (event.key === "ArrowRight" ? 1 : -1));
      }
    }
    window.addEventListener("keydown", key);
    return () => window.removeEventListener("keydown", key);
  });
  async function action(
    operation: () => Promise<AnnotationDocument>,
    success: string,
  ) {
    setBusy(true);
    setError(null);
    setNotice(null);
    try {
      const value = await operation();
      setDocument(value);
      setDirty(false);
      setNotice(success);
      onSaved?.();
    } catch (cause) {
      setError(message(cause));
    } finally {
      setBusy(false);
    }
  }
  const exportBase = `/api/field-sessions/${encodeURIComponent(fieldSessionId)}/annotations/export`;
  return (
    <section
      className="panel annotation-studio"
      aria-label="Vehicle annotation studio"
    >
      <div className="panel-heading">
        <div>
          <h2>Vehicle annotation studio</h2>
          <p className="panel-description">
            Manual truth identities are independent of predicted tracking IDs.
            Review each frame before evaluating tracking.
          </p>
        </div>
        <span>
          {dirty ? "Unsaved changes" : `Revision ${document?.revision ?? 0}`}
        </span>
      </div>
      {error && (
        <div className="inline-error" role="alert">
          {error}
        </div>
      )}
      {notice && <p role="status">{notice}</p>}
      <div className="annotation-toolbar">
        <button
          className="button button-secondary compact"
          disabled={busy || index <= 1}
          onClick={() => navigate(index - 1)}
        >
          Previous frame
        </button>
        <label>
          Frame number
          <input
            type="number"
            min="1"
            max={frame?.total_frames}
            value={indexDraft}
            onChange={(event) => setIndexDraft(event.target.value)}
          />
        </label>
        <button
          className="button button-secondary compact"
          disabled={busy || !indexDraft.trim()}
          onClick={() => navigate(Number(indexDraft))}
        >
          Go to frame
        </button>
        <button
          className="button button-secondary compact"
          disabled={busy || !frame || index >= frame.total_frames}
          onClick={() => navigate(index + 1)}
        >
          Next frame
        </button>
        <label>
          Source timestamp · s
          <input
            type="number"
            step="any"
            value={timestampDraft}
            onChange={(event) => setTimestampDraft(event.target.value)}
          />
        </label>
        <button
          className="button button-secondary compact"
          disabled={
            busy ||
            !timestampDraft.trim() ||
            !Number.isFinite(Number(timestampDraft))
          }
          onClick={() => {
            setError(null);
            void annotationApi
              .frameAt(fieldSessionId, Number(timestampDraft))
              .then((value) => navigate(value.index))
              .catch((cause) => setError(message(cause)));
          }}
        >
          Go to timestamp
        </button>
        <span className="mono">
          {frame
            ? `${frame.index} / ${frame.total_frames} · source ${frame.timestamp_s?.toFixed(6) ?? "unavailable"} s · timebase ${frame.time_base ?? "unknown"}`
            : "Load an uploaded video to navigate frames."}
        </span>
      </div>
      {frame?.timing_warning && (
        <p className="studio-notice">{frame.timing_warning}</p>
      )}
      <div className="annotation-layout">
        <div>
          {frame ? (
            <svg
              ref={svg}
              className="annotation-canvas"
              viewBox={`0 0 ${frame.width} ${frame.height}`}
              role="img"
              aria-label={`Annotation frame ${index} in ${frame.coordinate_space} image pixels`}
              onPointerDown={down}
              onPointerMove={move}
              onPointerUp={up}
              onPointerCancel={() => {
                drag.current = null;
                setPendingBox(null);
              }}
            >
              <image
                href={frame.image_url}
                width={frame.width}
                height={frame.height}
              />
              {current.predictions.map((prediction, i) => (
                <g key={`prediction-${i}`} className="annotation-prediction">
                  <rect
                    x={prediction.bbox[0]}
                    y={prediction.bbox[1]}
                    width={prediction.bbox[2] - prediction.bbox[0]}
                    height={prediction.bbox[3] - prediction.bbox[1]}
                  />
                  <text
                    x={prediction.bbox[0]}
                    y={Math.max(15, prediction.bbox[1] - 5)}
                  >
                    predicted #{prediction.predicted_track_id}
                  </text>
                </g>
              ))}
              {current.objects
                .filter((item) => item.bbox)
                .map((item) => {
                  const box = item.bbox!;
                  return (
                    <g
                      key={item.identity}
                      className={`annotation-object ${selected === item.identity ? "selected" : ""}`}
                    >
                      <rect
                        data-identity={item.identity}
                        x={box[0]}
                        y={box[1]}
                        width={box[2] - box[0]}
                        height={box[3] - box[1]}
                      />
                      <text x={box[0]} y={Math.max(15, box[1] - 5)}>
                        {item.identity}
                      </text>
                      {selected === item.identity && (
                        <circle
                          data-identity={item.identity}
                          data-resize="true"
                          cx={box[2]}
                          cy={box[3]}
                          r={Math.max(4, frame.width / 100)}
                        />
                      )}
                    </g>
                  );
                })}
              {pendingBox && (
                <rect
                  className="annotation-draft"
                  x={pendingBox[0]}
                  y={pendingBox[1]}
                  width={pendingBox[2] - pendingBox[0]}
                  height={pendingBox[3] - pendingBox[1]}
                />
              )}
            </svg>
          ) : (
            <div className="table-empty">
              <strong>No navigable recording selected</strong>
              <p>
                Associate a local uploaded video with this field session.
                Synthetic metadata alone contains no footage.
              </p>
            </div>
          )}
          <p className="panel-description">
            Drag empty image space to draw; drag a box to move it, or its
            lower-right handle to resize. Arrow keys change frames outside form
            fields. Coordinates:{" "}
            {document?.geometry.coordinate_space ?? "source"} pixels,{" "}
            {document?.geometry.width ?? "—"} ×{" "}
            {document?.geometry.height ?? "—"}; intrinsic profile{" "}
            {document?.geometry.intrinsic_profile_id ?? "none"}.
          </p>
        </div>
        <fieldset className="annotation-editor" disabled={busy}>
          <legend className="visually-hidden">
            Ground-truth annotation editor
          </legend>
          <label>
            Ground-truth identity
            <input
              value={identity}
              maxLength={160}
              onChange={(event) => setIdentity(event.target.value)}
              placeholder="vehicle-001"
            />
          </label>
          <label>
            Vehicle category
            <select
              value={category}
              onChange={(event) => setCategory(event.target.value as Category)}
            >
              {["car", "truck", "bus", "motorcycle"].map((value) => (
                <option key={value}>{value}</option>
              ))}
            </select>
          </label>
          <button
            className="button button-secondary compact"
            disabled={!document || busy}
            onClick={() => addObject(null, true)}
          >
            Mark identity fully occluded
          </button>
          <button
            className="button button-secondary compact"
            disabled={
              busy ||
              !document?.frames.find((item) => item.index === index - 1)
                ?.objects.length ||
              current.objects.length > 0
            }
            onClick={() => {
              const previous = document?.frames.find(
                (item) => item.index === index - 1,
              );
              if (previous)
                updateFrame({
                  reviewed: false,
                  objects: previous.objects.map((item) => ({
                    ...item,
                    bbox: item.bbox ? [...item.bbox] : null,
                    entry: false,
                    exit: false,
                  })),
                });
            }}
          >
            Copy previous labels for review
          </button>
          <label>
            Selected annotation
            <select
              value={selected ?? ""}
              onChange={(event) => setSelected(event.target.value || null)}
            >
              <option value="">Select a truth identity</option>
              {current.objects.map((item) => (
                <option key={item.identity} value={item.identity}>
                  {item.identity}
                  {item.occluded ? " · occluded" : ""}
                </option>
              ))}
            </select>
          </label>
          {object && (
            <>
              <label>
                Edit identity
                <input
                  value={object.identity}
                  onChange={(event) => {
                    const next = event.target.value;
                    updateObject({ identity: next });
                    setSelected(next);
                  }}
                />
              </label>
              <button
                className="text-button"
                disabled={object.occluded}
                onClick={() =>
                  updateObject({
                    occluded: true,
                    bbox: null,
                    partial_visibility: false,
                  })
                }
              >
                Mark selected identity fully occluded
              </button>
              {object.bbox && (
                <div className="annotation-box-inputs">
                  {object.bbox.map((value, position) => (
                    <label key={position}>
                      {["Left x", "Top y", "Right x", "Bottom y"][position]}
                      <input
                        type="number"
                        value={value}
                        onChange={(event) => {
                          if (!event.target.value.trim()) return;
                          const box = [...object.bbox!] as [
                            number,
                            number,
                            number,
                            number,
                          ];
                          box[position] = Number(event.target.value);
                          updateObject({ bbox: box });
                        }}
                      />
                    </label>
                  ))}
                </div>
              )}
              {(["partial_visibility", "entry", "exit"] as const).map(
                (flag) => (
                  <label className="annotation-check" key={flag}>
                    <input
                      type="checkbox"
                      checked={object[flag]}
                      onChange={(event) =>
                        updateObject({ [flag]: event.target.checked })
                      }
                    />
                    {flag.replaceAll("_", " ")}
                  </label>
                ),
              )}
              <button
                className="text-button"
                onClick={() => {
                  updateFrame({
                    objects: current.objects.filter((item) => item !== object),
                  });
                  setSelected(null);
                }}
              >
                Remove annotation
              </button>
            </>
          )}
          <label className="annotation-check">
            <input
              type="checkbox"
              checked={current.reviewed}
              disabled={!document || busy}
              onChange={(event) =>
                updateFrame({ reviewed: event.target.checked })
              }
            />
            Frame reviewed, including empty frames
          </label>
        </fieldset>
      </div>
      {current.predictions.length > 0 && (
        <div className="annotation-proposals">
          <h3>Predicted proposals for review</h3>
          {current.predictions.map((prediction, i) => (
            <button
              key={i}
              className="button button-secondary compact"
              disabled={busy}
              onClick={() => addObject(prediction.bbox)}
            >
              Use predicted #{prediction.predicted_track_id} box with entered
              truth identity
            </button>
          ))}
        </div>
      )}
      <div className="annotation-toolbar">
        <button
          className="button button-primary"
          disabled={!document || !dirty || busy || !connected}
          onClick={() =>
            void action(
              () => annotationApi.save(fieldSessionId, document!),
              "Annotations saved incrementally.",
            )
          }
        >
          Save annotations
        </button>
        <label className="button button-secondary compact">
          Import annotations
          <input
            className="visually-hidden"
            type="file"
            accept=".json,.csv"
            aria-label="Import annotations"
            disabled={busy || !connected}
            onChange={(event) => {
              const file = event.target.files?.[0];
              event.target.value = "";
              if (file)
                void action(
                  () => annotationApi.import(fieldSessionId, file),
                  "Annotations imported.",
                );
            }}
          />
        </label>
        <a
          className="text-button"
          href={dirty || busy ? undefined : `${exportBase}?format=json`}
          aria-disabled={dirty || busy}
          download
        >
          Export annotations JSON
        </a>
        <a
          className="text-button"
          href={dirty || busy ? undefined : `${exportBase}?format=csv`}
          aria-disabled={dirty || busy}
          download
        >
          Export annotations CSV
        </a>
        {dirty && (
          <span className="muted">
            Save annotations before exporting the updated labels.
          </span>
        )}
        <label>
          Proposal tracker
          <select
            value={tracker}
            disabled={busy}
            onChange={(event) => setTracker(event.target.value)}
          >
            <option value="improved">Improved global assignment</option>
            <option value="baseline">Phase 2 baseline</option>
          </select>
        </label>
        <button
          className="button button-secondary compact"
          disabled={busy || dirty || !frame || !connected}
          onClick={() =>
            void action(
              () =>
                annotationApi.propose(
                  fieldSessionId,
                  index,
                  Math.min(frame!.total_frames, index + 24),
                  tracker,
                ),
              "Offline proposals saved. Review boxes and assign independent truth identities.",
            )
          }
        >
          Propose next 25 frames
        </button>
        {busy && <span role="status">Processing annotation request…</span>}
      </div>
      <p className="panel-description">
        Save edits before generating proposals. Proposals are detector/tracker
        hypotheses, never automatic ground truth. No face, plate or owner
        identification is performed.
      </p>
    </section>
  );
}
