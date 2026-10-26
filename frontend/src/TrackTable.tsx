import Icon from "./Icon";
import type { Session } from "./types";

export default function TrackTable({
  session,
}: {
  session: Pick<Session, "tracks" | "calibration_status">;
}) {
  return (
    <section className="panel tracks-panel">
      <div className="panel-heading">
        <div className="heading-group">
          <h2>Current tracks</h2>
          <span className="count-badge">{session.tracks.length}</span>
        </div>
        <span className="subtle-caption">Session-scoped IDs</span>
      </div>
      <div className="table-scroll">
        <table>
          <thead>
            <tr>
              <th>Track ID</th>
              <th>Vehicle</th>
              <th>Detection confidence</th>
              <th>State</th>
              <th>Observations</th>
              <th>Age / observation gap · s</th>
              <th>Road position · m</th>
              <th>Gate state</th>
            </tr>
          </thead>
          <tbody>
            {session.tracks.length ? (
              session.tracks.map((track) => (
                <tr key={track.id}>
                  <td className="mono">#{String(track.id).padStart(3, "0")}</td>
                  <td className="vehicle-cell">
                    <Icon name={track.category} size={17} />
                    <span>{track.category}</span>
                  </td>
                  <td>
                    <div className="confidence-cell">
                      <span className="confidence-track">
                        <span
                          style={{
                            width: `${Math.round(track.confidence * 100)}%`,
                          }}
                        />
                      </span>
                      <span className="mono">
                        {(track.confidence * 100).toFixed(0)}%
                      </span>
                    </div>
                  </td>
                  <td>
                    <span
                      className={`track-state ${track.state === "confirmed" ? "confirmed" : ""}`}
                    >
                      {track.state}
                    </span>
                    {track.missed > 0 && (
                      <span className="missed-note">
                        {" "}
                        · {track.missed} missed
                      </span>
                    )}
                  </td>
                  <td className="mono">{track.hits}</td>
                  <td className="mono">
                    {track.age_s?.toFixed(2) ?? "—"} /{" "}
                    {track.observation_gap_s?.toFixed(3) ?? "—"}
                    {track.association_ambiguous && (
                      <span className="missed-note"> · identity uncertain</span>
                    )}
                  </td>
                  <td className="mono">
                    {session.calibration_status === "ready" &&
                    track.world_position?.every(Number.isFinite)
                      ? track.world_position
                          .map((value) => value.toFixed(2))
                          .join(", ")
                      : "—"}
                  </td>
                  <td className="track-measurement-state">
                    <span>
                      {track.measurement_state?.replaceAll("_", " ") ||
                        "Uncalibrated"}
                    </span>
                    {track.position_diagnostics?.length ? (
                      <details>
                        <summary>Position diagnostics</summary>
                        <ul>
                          {track.position_diagnostics.map((reason) => (
                            <li key={reason}>{reason}</li>
                          ))}
                        </ul>
                      </details>
                    ) : null}
                  </td>
                </tr>
              ))
            ) : (
              <tr>
                <td colSpan={8}>
                  <div className="table-empty">
                    <Icon name="target" size={25} />
                    <strong>No tracks to inspect yet</strong>
                    <p>
                      Detected vehicles will appear here with temporary IDs and
                      detection confidence.
                    </p>
                  </div>
                </td>
              </tr>
            )}
          </tbody>
        </table>
      </div>
      <div className="table-note">
        <Icon name="info" size={13} />
        Detection confidence describes the model prediction. It does not measure
        speed accuracy.
      </div>
    </section>
  );
}
