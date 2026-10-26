import type { CalibrationProfile } from "./types";
import type { CameraIntrinsicProfile } from "./cameraTypes";
import type { FieldSessionInput, FieldSourceOption } from "./fieldTypes";

export function emptyFieldSession(): FieldSessionInput {
  return {
    name: "",
    description: "",
    source: {
      source_id: "unassigned",
      video_id: null,
      relative_path: null,
      content_sha256: null,
      segment_start_s: null,
      segment_end_s: null,
      collection_id: null,
      near_duplicate_group: null,
    },
    camera: {
      configuration_id: "unspecified",
      geometry: {
        width: 1280,
        height: 720,
        rotation: 0,
        mirrored: false,
        crop: null,
        coordinate_space: "source",
        intrinsic_profile_id: null,
      },
      intrinsic_profile_id: null,
      lens_model: null,
      zoom: null,
      notes: "",
      detector_input_size: null,
      detector_confidence: null,
      tracker: "global_motion",
    },
    calibration_id: null,
    gates: null,
    started_at: null,
    ended_at: null,
    source_timebase: "",
    timing_summary: {},
    environment_notes: "",
    environment_condition: "unspecified",
    reference_description: "",
    validation_dataset_id: null,
    provenance: "recorded_unverified",
    status: "draft",
    partition: "development",
    measurements: [],
    reference_events: [],
    sync: {
      source_clock: "",
      reference_clock: "",
      offset_s: 0,
      fit_drift: false,
      anchors: [],
      uncertainty_s: null,
      maximum_alignment_error_s: 0.25,
      notes: "",
    },
    matches: [],
    expected_event_count: null,
  };
}
const optionalText = (value: string) => value.trim() || null;
const optionalNumber = (value: string) =>
  value.trim() === "" ? null : Number(value);
export default function FieldMetadata({
  value,
  onChange,
  profiles,
  sources,
  intrinsicProfiles,
  disabled,
  onUpload,
}: {
  value: FieldSessionInput;
  onChange: (next: FieldSessionInput) => void;
  profiles: CalibrationProfile[];
  sources: FieldSourceOption[];
  intrinsicProfiles: CameraIntrinsicProfile[];
  disabled: boolean;
  onUpload: (file: File) => void;
}) {
  const patch = (key: keyof FieldSessionInput, item: unknown) =>
    onChange({ ...value, [key]: item });
  function source(key: keyof FieldSessionInput["source"], item: unknown) {
    patch("source", { ...value.source, [key]: item });
  }
  function camera(key: keyof FieldSessionInput["camera"], item: unknown) {
    patch("camera", { ...value.camera, [key]: item });
  }
  function geometry(
    key: keyof FieldSessionInput["camera"]["geometry"],
    item: unknown,
  ) {
    camera("geometry", { ...value.camera.geometry, [key]: item });
  }
  const road = profiles.find((profile) => profile.id === value.calibration_id);
  const intrinsic = intrinsicProfiles.find(
    (profile) => profile.id === value.camera.intrinsic_profile_id,
  );
  const incompatible =
    road &&
    (road.source_id !== value.source.source_id ||
      road.geometry.width !== value.camera.geometry.width ||
      road.geometry.height !== value.camera.geometry.height ||
      road.geometry.rotation !== value.camera.geometry.rotation ||
      road.geometry.mirrored !== value.camera.geometry.mirrored ||
      JSON.stringify(road.geometry.crop) !==
        JSON.stringify(value.camera.geometry.crop) ||
      (road.geometry.coordinate_space || "source") !==
        (value.camera.geometry.coordinate_space || "source") ||
      (road.geometry.intrinsic_profile_id || null) !==
        (value.camera.geometry.intrinsic_profile_id || null));
  return (
    <fieldset className="field-metadata" disabled={disabled}>
      <legend className="visually-hidden">Field session metadata</legend>
      <div className="field-form-grid">
        <label>
          Session name
          <input
            value={value.name}
            maxLength={160}
            required
            onChange={(e) => patch("name", e.target.value)}
          />
        </label>
        <label>
          Session status
          <select
            value={value.status}
            onChange={(e) => patch("status", e.target.value)}
          >
            {["draft", "collecting", "ready", "evaluated"].map((v) => (
              <option key={v}>{v}</option>
            ))}
          </select>
        </label>
        <label>
          Dataset partition
          <select
            value={value.partition}
            onChange={(e) => patch("partition", e.target.value)}
          >
            <option value="development">Development</option>
            <option value="calibration">Calibration / tuning</option>
            <option value="held_out">Held-out evaluation</option>
          </select>
        </label>
        <label>
          Evidence provenance
          <select
            value={value.provenance}
            onChange={(e) => patch("provenance", e.target.value)}
          >
            <option value="recorded_unverified">Recorded, unverified</option>
            <option value="synthetic">Synthetic</option>
            <option value="independent_reference">
              Independent reference collected
            </option>
          </select>
        </label>
        <label className="field-wide">
          Observation description
          <textarea
            value={value.description}
            maxLength={4000}
            onChange={(e) => patch("description", e.target.value)}
          />
        </label>
      </div>
      <h3>Observation source</h3>
      <div className="field-form-grid">
        <label>
          Registered local video
          <select
            value={
              sources.some((item) => item.video_id === value.source.video_id)
                ? value.source.video_id!
                : ""
            }
            onChange={(e) => {
              const selected = sources.find(
                (item) => item.video_id === e.target.value,
              );
              if (selected)
                onChange({
                  ...value,
                  source: {
                    ...value.source,
                    source_id: selected.source_id,
                    video_id: selected.video_id,
                    relative_path: selected.relative_path,
                    content_sha256: selected.source_id.startsWith("video:")
                      ? selected.source_id.slice(6)
                      : null,
                  },
                  camera: {
                    ...value.camera,
                    geometry: {
                      ...value.camera.geometry,
                      width: selected.width,
                      height: selected.height,
                    },
                  },
                  source_timebase:
                    selected.time_base ||
                    (selected.reported_fps
                      ? `Video PTS; reported ${selected.reported_fps} fps`
                      : "Video PTS; inspect timing diagnostics"),
                });
            }}
          >
            <option value="">Choose a registered source</option>
            {sources.map((item) => (
              <option key={item.video_id} value={item.video_id}>
                {item.name}
              </option>
            ))}
          </select>
        </label>
        <label className="field-upload button button-secondary">
          Attach local video
          <input
            type="file"
            className="visually-hidden"
            aria-label="Attach field video"
            accept="video/*,.avi,.mkv"
            onChange={(e) => {
              const file = e.target.files?.[0];
              e.target.value = "";
              if (file) onUpload(file);
            }}
          />
        </label>
        <label>
          Source identifier
          <input
            value={value.source.source_id}
            onChange={(e) => source("source_id", e.target.value)}
          />
        </label>
        <label>
          Relative source path
          <input
            value={value.source.relative_path || ""}
            placeholder="uploads/example.mp4"
            onChange={(e) =>
              source("relative_path", optionalText(e.target.value))
            }
          />
        </label>
        <label>
          Segment start · source seconds
          <input
            type="number"
            min={0}
            step="any"
            value={value.source.segment_start_s ?? ""}
            onChange={(e) =>
              source("segment_start_s", optionalNumber(e.target.value))
            }
          />
        </label>
        <label>
          Segment end · source seconds
          <input
            type="number"
            min={0}
            step="any"
            value={value.source.segment_end_s ?? ""}
            onChange={(e) =>
              source("segment_end_s", optionalNumber(e.target.value))
            }
          />
        </label>
        <label>
          Collection identifier
          <input
            value={value.source.collection_id || ""}
            onChange={(e) =>
              source("collection_id", optionalText(e.target.value))
            }
          />
        </label>
        <label>
          Near-duplicate group
          <input
            value={value.source.near_duplicate_group || ""}
            onChange={(e) =>
              source("near_duplicate_group", optionalText(e.target.value))
            }
          />
        </label>
        <label>
          Started at · ISO 8601 with timezone
          <input
            value={value.started_at || ""}
            placeholder="2026-10-24T14:00:00+03:00"
            onChange={(e) => patch("started_at", optionalText(e.target.value))}
          />
        </label>
        <label>
          Ended at · ISO 8601 with timezone
          <input
            value={value.ended_at || ""}
            placeholder="2026-10-24T14:05:00+03:00"
            onChange={(e) => patch("ended_at", optionalText(e.target.value))}
          />
        </label>
        <label className="field-wide">
          Source timebase description
          <input
            value={value.source_timebase}
            placeholder="Video presentation timestamps, not independently verified wall-clock time"
            onChange={(e) => patch("source_timebase", e.target.value)}
          />
        </label>
      </div>
      <h3>Camera and road geometry</h3>
      <div className="field-form-grid">
        <label>
          Camera configuration identifier
          <input
            value={value.camera.configuration_id}
            onChange={(e) => camera("configuration_id", e.target.value)}
          />
        </label>
        <label>
          Lens model
          <input
            value={value.camera.lens_model || ""}
            onChange={(e) => camera("lens_model", optionalText(e.target.value))}
          />
        </label>
        <label>
          Image width · pixels
          <input
            type="number"
            min={1}
            value={
              Number.isFinite(value.camera.geometry.width)
                ? value.camera.geometry.width
                : ""
            }
            onChange={(e) =>
              geometry(
                "width",
                e.target.value === "" ? NaN : Number(e.target.value),
              )
            }
          />
        </label>
        <label>
          Image height · pixels
          <input
            type="number"
            min={1}
            value={
              Number.isFinite(value.camera.geometry.height)
                ? value.camera.geometry.height
                : ""
            }
            onChange={(e) =>
              geometry(
                "height",
                e.target.value === "" ? NaN : Number(e.target.value),
              )
            }
          />
        </label>
        <label>
          Zoom / focus setting
          <input
            value={value.camera.zoom || ""}
            onChange={(e) => camera("zoom", optionalText(e.target.value))}
          />
        </label>
        <label>
          Image rotation
          <select
            value={value.camera.geometry.rotation}
            onChange={(e) => geometry("rotation", Number(e.target.value))}
          >
            {[0, 90, 180, 270].map((n) => (
              <option key={n} value={n}>
                {n}°
              </option>
            ))}
          </select>
        </label>
        <label>
          Camera intrinsic profile
          <select
            value={value.camera.intrinsic_profile_id || ""}
            onChange={(e) => {
              const id = optionalText(e.target.value);
              onChange({
                ...value,
                camera: {
                  ...value.camera,
                  intrinsic_profile_id: id,
                  geometry: {
                    ...value.camera.geometry,
                    intrinsic_profile_id: id,
                    coordinate_space: id ? "undistorted" : "source",
                  },
                },
                calibration_id: null,
                gates: null,
                calibration_metadata: {
                  ...value.calibration_metadata,
                  road_plane: null,
                  intrinsic: intrinsicProfiles.find(
                    (profile) => profile.id === id,
                  )
                    ? {
                        ...intrinsicProfiles.find(
                          (profile) => profile.id === id,
                        )!,
                      }
                    : null,
                },
              });
            }}
          >
            <option value="">None · original source pixels</option>
            {intrinsicProfiles.map((item) => (
              <option key={item.id} value={item.id}>
                {item.name} · {item.width} × {item.height}
              </option>
            ))}
            {value.camera.intrinsic_profile_id && !intrinsic && (
              <option value={value.camera.intrinsic_profile_id}>
                {value.camera.intrinsic_profile_id} · unavailable profile
              </option>
            )}
          </select>
        </label>
        <label>
          Road-plane calibration profile
          <select
            value={value.calibration_id || ""}
            onChange={(e) => {
              const id = optionalText(e.target.value);
              const profile = profiles.find((item) => item.id === id);
              onChange({
                ...value,
                calibration_id: id,
                gates: profile?.gates || null,
                calibration_metadata: {
                  ...value.calibration_metadata,
                  road_plane: profile || null,
                },
              });
            }}
          >
            <option value="">No road-plane profile</option>
            {profiles.map((item) => (
              <option key={item.id} value={item.id}>
                {item.name}
              </option>
            ))}
            {value.calibration_id && !road && (
              <option value={value.calibration_id}>
                {value.calibration_id} · unavailable profile
              </option>
            )}
          </select>
        </label>
        <label>
          Tracking implementation
          <input
            value={value.camera.tracker}
            onChange={(e) => camera("tracker", e.target.value)}
          />
        </label>
        <label>
          Expected vehicle events
          <input
            type="number"
            min={0}
            step={1}
            value={value.expected_event_count ?? ""}
            onChange={(e) =>
              patch("expected_event_count", optionalNumber(e.target.value))
            }
          />
        </label>
        <label className="field-wide">
          Camera placement and model notes
          <textarea
            value={value.camera.notes}
            onChange={(e) => camera("notes", e.target.value)}
          />
        </label>
      </div>
      <p className="field-note">
        Coordinates:{" "}
        {value.camera.geometry.coordinate_space === "undistorted"
          ? "undistorted image pixels"
          : "original source image pixels"}
        . Road-plane coordinates are metres. Changing this metadata does not
        apply a live calibration.
      </p>
      {incompatible && (
        <p className="studio-notice" role="status">
          The road-plane profile does not match this source and coordinate
          geometry. Select a compatible profile before using this field session
          for measurement.
        </p>
      )}
      {intrinsic &&
        (intrinsic.width !== value.camera.geometry.width ||
          intrinsic.height !== value.camera.geometry.height) && (
          <p className="studio-notice" role="status">
            The intrinsic profile resolution does not match this field camera
            geometry. Use the original calibration resolution or collect a
            compatible intrinsic profile.
          </p>
        )}
      <p className="field-note">
        {road
          ? `Independent check-point error: ${road.diagnostics.check_error_m === null ? "unavailable" : `${road.diagnostics.check_error_m.toFixed(3)} m`}. `
          : "No road-plane calibration is associated. "}
        {value.gates
          ? "Gate A and Gate B are retained from the selected profile."
          : "No virtual gates retained. Configure them in Calibration & gates before collecting measurements."}
      </p>
      <h3>Conditions and reference provenance</h3>
      <div className="field-form-grid">
        <label>
          Collection condition
          <input
            value={value.environment_condition}
            placeholder="dry daylight"
            onChange={(e) => patch("environment_condition", e.target.value)}
          />
        </label>
        <label>
          Validation dataset identifier
          <input
            value={value.validation_dataset_id || ""}
            onChange={(e) =>
              patch("validation_dataset_id", optionalText(e.target.value))
            }
          />
        </label>
        <label className="field-wide">
          Environment and observation notes
          <textarea
            value={value.environment_notes}
            onChange={(e) => patch("environment_notes", e.target.value)}
          />
        </label>
        <label className="field-wide">
          Independent reference method and provenance
          <textarea
            value={value.reference_description}
            onChange={(e) => patch("reference_description", e.target.value)}
            placeholder="Instrument, method, uncertainty evidence, synchronization, and limitations"
          />
        </label>
      </div>
    </fieldset>
  );
}
