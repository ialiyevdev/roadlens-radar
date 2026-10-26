import { useEffect, useRef, useState } from "react";
import { api } from "./api";
import Icon from "./Icon";
import type { Camera, SourceType, StartOptions, Video } from "./types";
import { errorMessage } from "./useSession";

interface Props {
  locked: boolean;
  canStart: boolean;
  busy: boolean;
  activeSource: { type: SourceType | null; label: string | null };
  onStart: (options: StartOptions) => void;
}

export default function SourceControls({
  locked,
  canStart,
  busy,
  activeSource,
  onStart,
}: Props) {
  const [sourceType, setSourceType] = useState<SourceType>("camera");
  const [cameras, setCameras] = useState<Camera[]>([]);
  const [cameraIndex, setCameraIndex] = useState(0);
  const [manualCamera, setManualCamera] = useState(false);
  const [scanning, setScanning] = useState(false);
  const [scanDone, setScanDone] = useState(false);
  const [video, setVideo] = useState<Video | null>(null);
  const [uploading, setUploading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [confidence, setConfidence] = useState(0.35);
  const [inputSize, setInputSize] = useState(640);
  const [resolution, setResolution] = useState("1280x720");
  const inputRef = useRef<HTMLInputElement>(null);
  const mounted = useRef(true);

  useEffect(() => {
    mounted.current = true;
    return () => {
      mounted.current = false;
    };
  }, []);

  useEffect(() => {
    if (locked && activeSource.type) setSourceType(activeSource.type);
  }, [locked, activeSource.type]);

  async function scan() {
    setScanning(true);
    setError(null);
    try {
      const result = await api.cameras();
      if (!mounted.current) return;
      setCameras(result.cameras);
      setScanDone(true);
      if (result.cameras.length) {
        setCameraIndex(result.cameras[0].index);
        setManualCamera(false);
      }
    } catch (err) {
      if (mounted.current) setError(errorMessage(err));
    } finally {
      if (mounted.current) setScanning(false);
    }
  }

  async function upload(file: File) {
    setUploading(true);
    setError(null);
    setVideo(null);
    try {
      const result = await api.upload(file);
      if (mounted.current) setVideo(result);
    } catch (err) {
      if (mounted.current) setError(errorMessage(err));
    } finally {
      if (mounted.current) setUploading(false);
    }
  }

  function start() {
    const [width, height] = resolution.split("x").map(Number);
    onStart({
      source_type: sourceType,
      camera_index: cameraIndex,
      video_id: video?.video_id,
      confidence,
      input_size: inputSize,
      width,
      height,
    });
  }

  const unavailable = locked || busy;
  const ready = sourceType === "camera" ? true : Boolean(video);

  return (
    <section className="panel source-panel" aria-labelledby="source-heading">
      <div className="panel-heading">
        <h2 id="source-heading">Observation source</h2>
        <Icon name="camera" size={18} />
      </div>
      <p className="panel-description">
        Connect a camera or analyze a local recording.
      </p>
      <div className="segmented" role="group" aria-label="Source type">
        <button
          aria-pressed={sourceType === "camera"}
          disabled={unavailable || uploading}
          onClick={() => setSourceType("camera")}
        >
          <Icon name="camera" size={16} />
          Live camera
        </button>
        <button
          aria-pressed={sourceType === "video"}
          disabled={unavailable || scanning}
          onClick={() => setSourceType("video")}
        >
          <Icon name="video" size={16} />
          Video file
        </button>
      </div>

      {sourceType === "camera" ? (
        <div className="source-fields">
          <div className="label-row">
            <label htmlFor="camera-source">Camera device</label>
            <button
              className="text-button"
              onClick={() => void scan()}
              disabled={unavailable || scanning}
            >
              <Icon name="refresh" size={12} />
              {scanning ? "Scanning…" : "Scan cameras"}
            </button>
          </div>
          {manualCamera || !cameras.length ? (
            <div className="camera-index-field">
              <span>Device index</span>
              <input
                id="camera-source"
                aria-label="Camera device index"
                type="number"
                min="0"
                max="20"
                value={cameraIndex}
                disabled={unavailable}
                onChange={(event) =>
                  setCameraIndex(
                    Math.min(20, Math.max(0, Number(event.target.value))),
                  )
                }
              />
            </div>
          ) : (
            <select
              id="camera-source"
              value={cameraIndex}
              disabled={unavailable}
              onChange={(event) => setCameraIndex(Number(event.target.value))}
            >
              {cameras.map((camera) => (
                <option key={camera.index} value={camera.index}>
                  {camera.name} · {camera.index}
                </option>
              ))}
            </select>
          )}
          <div className="field-note">
            {scanning ? (
              "Checking connected devices. This may take a moment."
            ) : scanDone && !cameras.length ? (
              "No camera found. Check the connection or try a device index."
            ) : cameras.length ? (
              <button
                className="text-button"
                disabled={unavailable}
                onClick={() => setManualCamera(!manualCamera)}
              >
                {manualCamera
                  ? "Choose a discovered camera"
                  : "Enter a device index manually"}
              </button>
            ) : (
              "Use device 0 for your default camera, or scan for devices."
            )}
          </div>
          <label htmlFor="capture-resolution">
            Requested capture resolution
          </label>
          <select
            id="capture-resolution"
            value={resolution}
            disabled={unavailable}
            onChange={(event) => setResolution(event.target.value)}
          >
            <option value="1280x720">1280 × 720</option>
            <option value="640x480">640 × 480</option>
          </select>
          <p className="field-note">
            The camera may negotiate a different resolution.
          </p>
        </div>
      ) : (
        <div className="source-fields">
          <input
            ref={inputRef}
            className="visually-hidden"
            aria-label="Choose video file"
            type="file"
            accept="video/*,.mp4,.avi,.mov,.mkv,.webm"
            disabled={unavailable || uploading}
            onChange={(event) => {
              const file = event.target.files?.[0];
              if (file) void upload(file);
              event.target.value = "";
            }}
          />
          <button
            className={`upload-zone ${video ? "has-file" : ""}`}
            disabled={unavailable || uploading}
            onClick={() => inputRef.current?.click()}
          >
            <span className="upload-icon">
              <Icon name={video ? "video" : "upload"} size={23} />
            </span>
            <strong>
              {uploading
                ? "Uploading video…"
                : locked && activeSource.type === "video"
                  ? activeSource.label
                  : video
                    ? video.name
                    : "Choose a video file"}
            </strong>
            <span>
              {locked
                ? "Current observation source"
                : video
                  ? "Click to choose another recording"
                  : "MP4, AVI, MOV · stays on this computer"}
            </span>
          </button>
          <p className="field-note">
            Maximum 256 MB. Video decoding uses PyAV / FFmpeg. Source timestamps
            are retained where available.
          </p>
        </div>
      )}

      <div className="settings-divider" />
      <div className="label-row">
        <label htmlFor="confidence">Detection confidence</label>
        <output htmlFor="confidence" className="mono">
          {confidence.toFixed(2)}
        </output>
      </div>
      <input
        id="confidence"
        type="range"
        min="0.05"
        max="0.95"
        step="0.05"
        value={confidence}
        disabled={unavailable}
        onChange={(event) => setConfidence(Number(event.target.value))}
      />
      <div className="range-labels">
        <span>More detections</span>
        <span>Higher confidence</span>
      </div>
      <div className="model-setting">
        <label htmlFor="inference-input">Inference input</label>
        <select
          id="inference-input"
          value={inputSize}
          disabled={unavailable}
          onChange={(event) => setInputSize(Number(event.target.value))}
        >
          <option value="320">320 × 320</option>
          <option value="416">416 × 416</option>
          <option value="640">640 × 640</option>
        </select>
      </div>
      {error && (
        <p role="alert" className="inline-error">
          {error}
        </p>
      )}
      <button
        className="button button-primary start-button"
        disabled={!canStart || unavailable || !ready || uploading || scanning}
        onClick={start}
      >
        <Icon name="play" size={17} />
        {busy
          ? "Please wait…"
          : locked
            ? "Session in progress"
            : "Start observation"}
        <Icon name="arrow" size={17} />
      </button>
      <p className="local-note">
        <Icon name="shield" size={13} />
        Local processing. No audio capture.
      </p>
    </section>
  );
}
