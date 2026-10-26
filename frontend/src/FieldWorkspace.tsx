import { useEffect, useRef, useState } from "react";
import { api } from "./api";
import { fieldApi } from "./fieldApi";
import { cameraApi } from "./cameraApi";
import { CameraIntrinsics } from "./CameraIntrinsics";
import type { CameraIntrinsicProfile } from "./cameraTypes";
import AnnotationStudio from "./AnnotationStudio";
import FieldMetadata, { emptyFieldSession } from "./FieldMetadata";
import FieldAlignment from "./FieldAlignment";
import FieldEvaluation from "./FieldEvaluation";
import { downloadResult } from "./validationApi";
import { finite } from "./ValidationCharts";
import { formatMetric } from "./validationPresentation";
import { qualityEntries } from "./fieldPresentation";
import type { CalibrationProfile, Session } from "./types";
import type {
  FieldEligibility,
  FieldSession,
  FieldSessionInput,
  FieldSourceOption,
} from "./fieldTypes";
import "./field.css";

type Tab = "session" | "camera" | "annotations" | "alignment" | "evaluation";
function inputOf(field: FieldSession): FieldSessionInput {
  const { id, created_at, updated_at, sync_diagnostics, ...input } = field;
  void id;
  void created_at;
  void updated_at;
  void sync_diagnostics;
  return input;
}
const message = (error: unknown) =>
  error instanceof Error ? error.message : "The field-session request failed.";
export default function FieldWorkspace({
  session,
  connected,
  perform,
  view = "sessions",
}: {
  session: Session;
  connected: boolean;
  perform: (operation: () => Promise<Session>) => Promise<void>;
  view?: "sessions" | "validation";
}) {
  const [sessions, setSessions] = useState<FieldSession[]>([]),
    [selectedId, setSelectedId] = useState("");
  const [draft, setDraft] = useState<FieldSessionInput>(emptyFieldSession),
    [dirty, setDirty] = useState(false);
  const selection = useRef({ id: selectedId, dirty });
  selection.current = { id: selectedId, dirty };
  const [sources, setSources] = useState<FieldSourceOption[]>([]),
    [profiles, setProfiles] = useState<CalibrationProfile[]>([]),
    [intrinsicProfiles, setIntrinsicProfiles] = useState<
      CameraIntrinsicProfile[]
    >([]);
  const [tab, setTab] = useState<Tab>(
      view === "validation" ? "evaluation" : "session",
    ),
    [cameraOpened, setCameraOpened] = useState(false),
    [annotationsOpened, setAnnotationsOpened] = useState(false);
  const [busy, setBusy] = useState(false),
    [error, setError] = useState<string | null>(null),
    [notice, setNotice] = useState<string | null>(null),
    [deleteReady, setDeleteReady] = useState(false),
    [eligibility, setEligibility] = useState<FieldEligibility | null>(null);
  const [annotationMetrics, setAnnotationMetrics] = useState<Record<
    string,
    unknown
  > | null>(null);
  const selected = sessions.find((item) => item.id === selectedId) || null;
  useEffect(() => {
    setTab(view === "validation" ? "evaluation" : "session");
  }, [view]);
  useEffect(() => {
    let active = true;
    setBusy(true);
    void Promise.allSettled([
      fieldApi.list(),
      fieldApi.sources(),
      api.calibrations(),
      cameraApi.profiles(),
    ]).then((results) => {
      if (!active) return;
      const [list, source, road, camera] = results;
      if (list.status === "fulfilled") {
        setSessions(list.value.sessions);
        const first = list.value.sessions[0];
        if (first) {
          setSelectedId(first.id);
          setDraft(inputOf(first));
        }
      }
      if (source.status === "fulfilled") setSources(source.value.sources);
      if (road.status === "fulfilled") setProfiles(road.value.profiles);
      if (camera.status === "fulfilled")
        setIntrinsicProfiles(camera.value.profiles);
      const failures = results
        .filter((result) => result.status === "rejected")
        .map((result) => message(result.reason));
      if (failures.length) setError([...new Set(failures)].join(" "));
      setBusy(false);
    });
    return () => {
      active = false;
    };
  }, []);
  useEffect(() => {
    let active = true;
    setEligibility(null);
    setAnnotationMetrics(null);
    if (selected)
      void fieldApi
        .eligibility(selected.id)
        .then((value) => {
          if (active) setEligibility(value);
        })
        .catch((cause) => {
          if (active) setError(message(cause));
        });
    if (selected)
      void fieldApi
        .annotationMetrics(selected.id)
        .then((value) => {
          if (active) setAnnotationMetrics(value);
        })
        .catch((cause) => {
          if (active) setError(message(cause));
        });
    return () => {
      active = false;
    };
  }, [selected]);
  function choose(field: FieldSession) {
    selection.current = { id: field.id, dirty: false };
    setSelectedId(field.id);
    setDraft(inputOf(field));
    setDirty(false);
    setDeleteReady(false);
    setNotice(null);
  }
  function saved(field: FieldSession) {
    setSessions((items) => [
      field,
      ...items.filter((item) => item.id !== field.id),
    ]);
    choose(field);
  }
  function childSaved(field: FieldSession) {
    setSessions((items) =>
      items.map((item) => (item.id === field.id ? field : item)),
    );
    if (selection.current.id === field.id && !selection.current.dirty)
      choose(field);
  }
  async function operation(action: () => Promise<void>) {
    setBusy(true);
    setError(null);
    setNotice(null);
    try {
      await action();
    } catch (cause) {
      setError(message(cause));
    } finally {
      setBusy(false);
    }
  }
  async function save() {
    await operation(async () => {
      const result = selected
        ? await fieldApi.update(selected.id, draft)
        : await fieldApi.create(draft);
      saved(result);
      setNotice("Field session saved locally.");
    });
  }
  function newSession() {
    selection.current = { id: "", dirty: false };
    setSelectedId("");
    setDraft(emptyFieldSession());
    setDirty(false);
    setDeleteReady(false);
    setTab("session");
    setNotice(null);
  }
  async function upload(file: File) {
    await operation(async () => {
      const uploaded = await api.upload(file);
      const catalog = await fieldApi.sources();
      setSources(catalog.sources);
      const found = catalog.sources.find(
        (item) => item.video_id === uploaded.video_id,
      );
      if (found) {
        selection.current.dirty = true;
        setDraft((value) => ({
          ...value,
          source: {
            ...value.source,
            source_id: found.source_id,
            video_id: found.video_id,
            relative_path: found.relative_path,
            content_sha256: found.source_id.startsWith("video:")
              ? found.source_id.slice(6)
              : null,
          },
          camera: {
            ...value.camera,
            geometry: {
              ...value.camera.geometry,
              width: found.width,
              height: found.height,
            },
          },
          source_timebase: found.time_base || "Video presentation timestamps",
        }));
        setDirty(true);
        setNotice(
          "Video registered once and linked to this draft. Save the field session to retain the association.",
        );
      }
    });
  }
  const validDraft =
    draft.name.trim().length > 0 &&
    draft.source.source_id.trim().length > 0 &&
    [draft.camera.geometry.width, draft.camera.geometry.height].every(
      (n) => Number.isInteger(n) && n >= 2 && n <= 16384,
    );
  const disabled = busy || !connected;
  const road =
    selected?.calibration_metadata?.road_plane ||
    profiles.find((profile) => profile.id === selected?.calibration_id);
  return (
    <div className="field-workspace">
      <div className="field-evidence-notice" role="status">
        <strong>
          {eligibility?.real_world_reference_available
            ? "Independent real-world reference events matched"
            : "No real-world reference data available"}
        </strong>
        <p>
          {selected?.provenance === "synthetic"
            ? "The selected session is synthetic. Its examples exercise the software workflow and provide no physical-road accuracy evidence."
            : "Reference provenance, timing alignment, and vehicle correspondence must be established before confirming comparisons."}
        </p>
      </div>
      <section className="panel field-panel">
        <div className="panel-heading">
          <div>
            <h2>Local field sessions</h2>
            <p className="panel-description">
              Persist source links, collection conditions, camera geometry,
              annotations, and independent-reference decisions.
            </p>
          </div>
          <span>{sessions.length} saved</span>
        </div>
        {error && (
          <p className="inline-error" role="alert">
            {error}
          </p>
        )}
        {notice && (
          <p className="studio-notice" role="status">
            {notice}
          </p>
        )}
        {selected?.configuration_warnings?.map((warning) => (
          <p className="studio-notice" role="status" key={warning}>
            {warning}
          </p>
        ))}
        <div className="field-session-picker">
          <label>
            Selected field session
            <select
              value={selectedId}
              disabled={disabled}
              onChange={(e) => {
                const field = sessions.find(
                  (item) => item.id === e.target.value,
                );
                if (field) choose(field);
              }}
            >
              <option value="">New unsaved session</option>
              {sessions.map((field) => (
                <option key={field.id} value={field.id}>
                  {field.name} · {field.partition.replaceAll("_", " ")} ·{" "}
                  {field.provenance.replaceAll("_", " ")}
                </option>
              ))}
            </select>
          </label>
          <button
            className="button button-secondary compact"
            disabled={disabled}
            onClick={newSession}
          >
            New field session
          </button>
          <button
            className="button button-secondary compact"
            disabled={disabled}
            onClick={() =>
              void operation(async () => {
                setDraft(await fieldApi.example());
                selection.current = { id: "", dirty: true };
                setSelectedId("");
                setDirty(true);
                setTab("session");
                setNotice("Synthetic example loaded as an unsaved draft.");
              })
            }
          >
            Load synthetic field example
          </button>
        </div>
        <div className="field-actions">
          <button
            className="button button-secondary compact"
            disabled={disabled || !session.source_id || !session.geometry}
            onClick={() =>
              void operation(async () => {
                saved(
                  await fieldApi.fromObservation({
                    name:
                      draft.name.trim() ||
                      session.source_label ||
                      "Field observation",
                    partition: draft.partition,
                    provenance: draft.provenance,
                    environment_notes: draft.environment_notes,
                    reference_description: draft.reference_description,
                  }),
                );
                setTab("session");
                setNotice(
                  "A separate field record was captured from the current observation.",
                );
              })
            }
          >
            Capture current observation
          </button>
          <label
            className={`button button-secondary compact field-upload ${disabled ? "disabled" : ""}`}
          >
            Import field session JSON
            <input
              type="file"
              accept=".json,application/json"
              className="visually-hidden"
              aria-label="Import field session"
              disabled={disabled}
              onChange={(e) => {
                const file = e.target.files?.[0];
                e.target.value = "";
                if (file)
                  void operation(async () => {
                    saved(await fieldApi.importSession(file));
                    setTab("session");
                  });
              }}
            />
          </label>
          <button
            className="button button-secondary compact"
            disabled={disabled || !selected}
            onClick={() =>
              selected &&
              void operation(async () =>
                downloadResult(
                  await fieldApi.exportSession(selected.id),
                  `roadlens-field-${selected.id}.json`,
                ),
              )
            }
          >
            Export field session JSON
          </button>
          {selected && (
            <button
              className="text-button danger-text"
              disabled={disabled}
              onClick={() => setDeleteReady(true)}
            >
              Delete field session
            </button>
          )}
        </div>
        {deleteReady && selected && (
          <div className="field-delete-prompt">
            <p>
              Delete the local metadata, reference matches, and annotations for
              “{selected.name}”? The source video remains registered.
            </p>
            <button
              className="button button-secondary compact"
              disabled={disabled}
              onClick={() =>
                void operation(async () => {
                  await fieldApi.delete(selected.id);
                  setSessions((items) =>
                    items.filter((item) => item.id !== selected.id),
                  );
                  newSession();
                  setNotice("Field session deleted.");
                })
              }
            >
              Confirm field session deletion
            </button>
            <button
              className="text-button"
              onClick={() => setDeleteReady(false)}
            >
              Keep session
            </button>
          </div>
        )}
        {selected && (
          <dl className="field-quality-grid field-overview">
            <div>
              <dt>Session identifier</dt>
              <dd className="mono">{selected.id}</dd>
            </div>
            <div>
              <dt>Collection status</dt>
              <dd>{selected.status}</dd>
            </div>
            <div>
              <dt>Vehicle events retained</dt>
              <dd>
                {
                  new Set(selected.measurements.map((item) => item.event_id))
                    .size
                }
              </dd>
            </div>
            <div>
              <dt>Annotated vehicles</dt>
              <dd>
                {annotationMetrics &&
                finite(annotationMetrics.annotated_vehicles)
                  ? annotationMetrics.annotated_vehicles
                  : "—"}
              </dd>
            </div>
            <div>
              <dt>Reference matches</dt>
              <dd>
                {Number(eligibility?.matched_event_count || 0)} /{" "}
                {selected.reference_events.length}
              </dd>
            </div>
            <div>
              <dt>Eligible events</dt>
              <dd>{Number(eligibility?.eligible_event_count || 0)}</dd>
            </div>
            <div>
              <dt>Camera configuration</dt>
              <dd>{selected.camera.configuration_id}</dd>
            </div>
          </dl>
        )}
      </section>
      <div className="field-tabs" role="tablist" aria-label="Field workflow">
        {(
          [
            { id: "session", label: "Session details" },
            { id: "camera", label: "Camera intrinsics" },
            { id: "annotations", label: "Vehicle annotations" },
            { id: "alignment", label: "Reference alignment" },
            { id: "evaluation", label: "Evaluation & reports" },
          ] as const
        ).map((item) => (
          <button
            role="tab"
            key={item.id}
            aria-selected={tab === item.id}
            aria-controls={`field-tab-${item.id}`}
            id={`field-tab-button-${item.id}`}
            onClick={() => {
              setTab(item.id);
              if (item.id === "camera") setCameraOpened(true);
              if (item.id === "annotations") setAnnotationsOpened(true);
            }}
          >
            {item.label}
          </button>
        ))}
      </div>
      <div
        role="tabpanel"
        id="field-tab-session"
        aria-labelledby="field-tab-button-session"
        hidden={tab !== "session"}
      >
        <section className="panel field-panel">
          <div className="panel-heading">
            <div>
              <h2>
                {selected ? "Edit field session" : "Create a field session"}
              </h2>
              <p className="panel-description">
                Use a new collection/configuration identifier after moving,
                zooming, or reconfiguring the camera. Source videos stay linked
                without copying footage.
              </p>
            </div>
            {dirty && (
              <span className="field-state uncertain">Unsaved changes</span>
            )}
          </div>
          <FieldMetadata
            value={draft}
            onChange={(value) => {
              selection.current.dirty = true;
              setDraft(value);
              setDirty(true);
            }}
            profiles={profiles}
            sources={sources}
            intrinsicProfiles={intrinsicProfiles}
            disabled={disabled}
            onUpload={(file) => void upload(file)}
          />
          <div className="field-actions">
            <button
              className="button button-primary"
              disabled={disabled || !validDraft}
              onClick={() => void save()}
            >
              {selected
                ? "Save field session changes"
                : "Save new field session"}
            </button>
            {busy && <span role="status">Updating local field session…</span>}
          </div>
        </section>
        {selected && (
          <section className="panel field-panel">
            <h2>Archived measurement quality</h2>
            <dl className="field-quality-grid">
              <div>
                <dt>Camera model</dt>
                <dd>
                  {selected.camera.intrinsic_profile_id ||
                    "Original source pixels; no undistortion"}
                </dd>
              </div>
              <div>
                <dt>Road-plane profile</dt>
                <dd>
                  {road?.name || selected.calibration_id || "Not associated"}
                </dd>
              </div>
              <div>
                <dt>Held-out check-point error</dt>
                <dd>{formatMetric(road?.diagnostics.check_error_m)} m</dd>
              </div>
              <div>
                <dt>Source timebase</dt>
                <dd>{selected.source_timebase || "Not documented"}</dd>
              </div>
              <div>
                <dt>Synchronization</dt>
                <dd>{selected.sync_diagnostics.status}</dd>
              </div>
              {qualityEntries(selected.timing_summary).map(([key, value]) => (
                <div key={key}>
                  <dt>{key}</dt>
                  <dd>{finite(value) ? formatMetric(value) : String(value)}</dd>
                </div>
              ))}
            </dl>
            {eligibility?.warnings?.map((warning) => (
              <p key={warning} className="field-note">
                {warning}
              </p>
            ))}
            {eligibility?.rows && eligibility.rows.length > 0 && (
              <details>
                <summary>Validation eligibility by vehicle event</summary>
                <div className="table-scroll">
                  <table aria-label="Field event eligibility">
                    <thead>
                      <tr>
                        <th>Vehicle event</th>
                        <th>Variant</th>
                        <th>Eligible</th>
                        <th>Exclusion reasons</th>
                      </tr>
                    </thead>
                    <tbody>
                      {eligibility.rows.map((row) => (
                        <tr key={`${row.event_id}:${row.variant}`}>
                          <td>{row.event_id}</td>
                          <td>{row.variant}</td>
                          <td>{row.eligible ? "yes" : "no"}</td>
                          <td>
                            {row.exclusion_reasons.join("; ") ||
                              "No current exclusions"}
                          </td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              </details>
            )}
          </section>
        )}
      </div>
      {cameraOpened && (
        <div
          role="tabpanel"
          id="field-tab-camera"
          aria-labelledby="field-tab-button-camera"
          hidden={tab !== "camera"}
        >
          <CameraIntrinsics
            session={session}
            connected={connected}
            perform={perform}
          />
          <button
            className="text-button"
            onClick={() =>
              void operation(async () => {
                setIntrinsicProfiles((await cameraApi.profiles()).profiles);
                setNotice(
                  "Camera intrinsic profiles refreshed for session metadata.",
                );
              })
            }
          >
            Refresh profiles in session details
          </button>
        </div>
      )}
      <div
        role="tabpanel"
        id="field-tab-annotations"
        aria-labelledby="field-tab-button-annotations"
        hidden={tab !== "annotations"}
      >
        {annotationsOpened &&
          (selected ? (
            <AnnotationStudio
              key={selected.id}
              fieldSessionId={selected.id}
              connected={connected}
              onSaved={() => {
                void fieldApi
                  .get(selected.id)
                  .then(childSaved)
                  .catch((cause) => {
                    if (selection.current.id === selected.id)
                      setError(message(cause));
                  });
              }}
            />
          ) : (
            <div className="panel field-panel field-empty">
              <h2>Save a field session before annotating</h2>
              <p>
                Attach a local video, save the session, then navigate individual
                source frames and assign ground-truth identities.
              </p>
            </div>
          ))}
      </div>
      <div
        role="tabpanel"
        id="field-tab-alignment"
        aria-labelledby="field-tab-button-alignment"
        hidden={tab !== "alignment"}
      >
        {selected ? (
          <FieldAlignment
            key={selected.id}
            field={selected}
            connected={connected}
            onSaved={childSaved}
          />
        ) : (
          <div className="panel field-panel field-empty">
            <h2>Save a field session before importing references</h2>
            <p>
              Reference events and matching decisions are persisted within the
              selected local session.
            </p>
          </div>
        )}
      </div>
      <div
        role="tabpanel"
        id="field-tab-evaluation"
        aria-labelledby="field-tab-button-evaluation"
        hidden={tab !== "evaluation"}
      >
        <FieldEvaluation sessions={sessions} connected={connected} />
      </div>
    </div>
  );
}
