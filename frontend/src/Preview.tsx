import { useEffect, useState } from "react";
import Icon from "./Icon";
import type { Session } from "./types";

export const stateLabels = {
  idle: "No active source",
  starting: "Opening source",
  running: "Observing",
  paused: "Paused",
  stopped: "Stopped",
  completed: "Video complete",
  error: "Source error",
};

export function elapsed(seconds: number | null) {
  if (seconds === null || !Number.isFinite(seconds) || seconds < 0) return "—";
  const minutes = Math.floor(seconds / 60);
  return `${minutes.toString().padStart(2, "0")}:${(seconds % 60).toFixed(1).padStart(4, "0")}`;
}

export default function Preview({ session }: { session: Session }) {
  const [failed, setFailed] = useState(false);
  const [retry, setRetry] = useState(0);
  const hasFrame = session.frame_index > 0 && Boolean(session.session_id);
  const staticFrame = ["paused", "completed", "stopped", "error"].includes(
    session.state,
  );
  const sessionQuery = encodeURIComponent(session.session_id || "");
  const imageUrl = staticFrame
    ? `/api/frame?session=${sessionQuery}&revision=${session.preview_revision ?? session.frame_index}&retry=${retry}`
    : `/api/stream?session=${sessionQuery}&retry=${retry}`;
  useEffect(() => {
    setFailed(false);
    setRetry(0);
  }, [session.session_id]);

  return (
    <section className="panel preview-panel" aria-labelledby="preview-heading">
      <div className="preview-heading">
        <div className="heading-group">
          <h2 id="preview-heading">Observation feed</h2>
          <span
            className={`status-pill ${session.state === "running" ? "green" : ""}`}
          >
            <span className="status-dot" />
            {stateLabels[session.state]}
          </span>
        </div>
        <span className="preview-source">
          {session.source_label || "Awaiting connection"}
        </span>
      </div>
      <div className={`preview-surface ${hasFrame ? "with-feed" : ""}`}>
        {hasFrame && (
          <img
            className="stream-image"
            src={imageUrl}
            alt="Processed source with vehicle detections, temporary tracking IDs, and image trajectories"
            onError={() => setFailed(true)}
            onLoad={() => setFailed(false)}
          />
        )}
        {(!hasFrame || failed) && (
          <div className="preview-empty">
            <div className="viewfinder">
              <span />
              <span />
              <span />
              <span />
              <div className="viewfinder-camera">
                <Icon name="camera" size={32} />
              </div>
              <div className="viewfinder-cross" />
            </div>
            <h3>
              {failed
                ? "Preview connection interrupted"
                : session.state === "starting"
                  ? "Opening your source"
                  : session.state === "error"
                    ? "Source could not be opened"
                    : "A clearer view starts here."}
            </h3>
            <p>
              {failed
                ? "Your session diagnostics remain available. Reconnect the preview to continue viewing."
                : session.state === "starting"
                  ? "Loading the detector and waiting for the first frame."
                  : "Select a camera or recorded video, then start an observation to see vehicle detections and tracks."}
            </p>
            {failed ? (
              <button
                className="button button-secondary"
                onClick={() => {
                  setFailed(false);
                  setRetry((value) => value + 1);
                }}
              >
                <Icon name="refresh" size={15} />
                Reconnect preview
              </button>
            ) : (
              <span className="preview-empty-label">
                <span className="status-dot" />
                {session.state === "starting"
                  ? "Waiting for frames"
                  : "No video source connected"}
              </span>
            )}
          </div>
        )}
        <div className="feed-corner top-left" />
        <div className="feed-corner top-right" />
        <div className="feed-corner bottom-left" />
        <div className="feed-corner bottom-right" />
        {hasFrame && (
          <div className="feed-caption">
            <span>
              {session.width} × {session.height}
            </span>
            <span>FRAME {session.frame_index.toLocaleString()}</span>
            <span>{elapsed(session.timestamp_s)}</span>
          </div>
        )}
      </div>
      <div className="preview-footer">
        <span>
          <span className="legend-dot detection" />
          Vehicle detection
        </span>
        <span>
          <span className="legend-dot trajectory" />
          Track trajectory
        </span>
        <span className="preview-privacy">
          <Icon name="shield" size={13} />
          Camera footage is not recorded
        </span>
      </div>
    </section>
  );
}
