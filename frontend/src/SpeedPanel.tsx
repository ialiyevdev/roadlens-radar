import Icon from "./Icon";
import { elapsed } from "./Preview";
import type { Session } from "./types";
import "./quality.css";

export function speedValue(value: number | null | undefined, ready: boolean) {
  return ready && value != null && Number.isFinite(value)
    ? value.toFixed(1)
    : "—";
}

export default function SpeedPanel({
  session,
  onClear,
}: {
  session: Session;
  onClear: () => void;
}) {
  const ready = session.calibration_status === "ready";
  const summary = session.measurement_summary;
  const measurements = session.measurements ?? [];
  const latestFirst = [...measurements].reverse();
  return (
    <section className="speed-workspace" aria-labelledby="speed-heading">
      <div className="section-heading speed-heading">
        <h2 id="speed-heading">Ground-plane speed estimates</h2>
        <span>{session.measurement_status || "Calibration required"}</span>
      </div>
      <div className="speed-grid">
        <div>
          <span>Active tracked vehicles</span>
          <strong className="mono">
            {session.tracks.filter((track) => track.missed === 0).length}
          </strong>
          <p>Currently observed temporary IDs</p>
        </div>
        <div>
          <span>Valid completed measurements</span>
          <strong className="mono">{summary?.valid_count ?? 0}</strong>
          <p>
            {summary?.approximate_count ?? 0} approximate ·{" "}
            {summary?.rejected_count ?? 0} rejected
          </p>
        </div>
        <div>
          <span>Latest estimate</span>
          <strong className="mono">
            {speedValue(summary?.latest_speed_kmh, ready)}
            <small>km/h</small>
          </strong>
          <p>
            {ready && summary?.latest_status ? (
              <span className={`quality-badge ${summary.latest_status}`}>
                {summary.latest_status}
              </span>
            ) : (
              "Completed A/B gate traversal"
            )}
          </p>
        </div>
        <div>
          <span>Average valid speed</span>
          <strong className="mono">
            {speedValue(summary?.average_speed_kmh, ready)}
            <small>km/h</small>
          </strong>
          <p>Valid estimates in this observation</p>
        </div>
      </div>
      <div className="panel measurement-panel">
        <div className="panel-heading">
          <h2>Measurement history</h2>
          {measurements.length > 0 && (
            <div className="measurement-export-actions">
              <a className="text-button" href="/api/exports/measurements?format=csv" download>Export CSV</a>
              <a className="text-button" href="/api/exports/measurements?format=json" download>Export JSON</a>
            </div>
          )}
          <button
            className="text-button"
            disabled={!measurements.length}
            onClick={onClear}
          >
            Clear history
          </button>
        </div>
        {measurements.length ? (
          <div className="table-scroll">
            <table aria-label="Speed measurement history">
              <thead>
                <tr>
                  <th>Vehicle ID</th>
                  <th>Speed · km/h</th>
                  <th>Direction</th>
                  <th>Gate time · s</th>
                  <th>Quality / diagnostics</th>
                  <th>Source time</th>
                </tr>
              </thead>
              <tbody>
                {latestFirst.map((measurement) => (
                  <tr
                    key={measurement.id}
                    className={`measurement-${measurement.status}`}
                  >
                    <td className="mono">
                      #{String(measurement.track_id).padStart(3, "0")}
                    </td>
                    <td className="mono">
                      {measurement.status === "rejected"
                        ? "—"
                        : speedValue(measurement.estimated_speed_kmh, ready)}
                      {measurement.status === "approximate" && (
                        <span className="approximate-label">approx.</span>
                      )}
                    </td>
                    <td>
                      {measurement.direction === "A_to_B"
                        ? "A → B"
                        : measurement.direction === "B_to_A"
                          ? "B → A"
                          : "Incomplete"}
                    </td>
                    <td className="mono">
                      {measurement.elapsed_seconds != null &&
                      Number.isFinite(measurement.elapsed_seconds)
                        ? measurement.elapsed_seconds.toFixed(3)
                        : "—"}
                    </td>
                    <td className="measurement-quality">
                      <span className={`quality-badge ${measurement.status}`}>
                        {measurement.status}
                      </span>
                      <span>
                        {measurement.sample_count} observations
                        {measurement.distance_m != null &&
                        Number.isFinite(measurement.distance_m)
                          ? ` · ${measurement.distance_m.toFixed(2)} m`
                          : ""}
                      </span>
                      {measurement.reasons.length > 0 && (
                        <ul>
                          {measurement.reasons.map((reason) => (
                            <li key={reason}>{reason}</li>
                          ))}
                        </ul>
                      )}
                      {measurement.diagnostics && (
                        <details className="measurement-evidence">
                          <summary>Measurement evidence</summary>
                          <dl>
                            {[
                              ["Calibration check RMSE · m", measurement.diagnostics.calibration_check_error_m?.toFixed(3) ?? "No independent checks"],
                              ["Minimum hull margin · px", measurement.diagnostics.minimum_region_margin_px?.toFixed(1) ?? "—"],
                              ["Maximum observation gap · s", measurement.diagnostics.maximum_observation_gap_s?.toFixed(3) ?? "—"],
                              ["Maximum motion residual · px", measurement.diagnostics.maximum_contact_prediction_residual_px?.toFixed(1) ?? "—"],
                              ["Gate A / B interpolation · s", `${measurement.diagnostics.gate_a_interpolation_interval_s?.toFixed(3) ?? "—"} / ${measurement.diagnostics.gate_b_interpolation_interval_s?.toFixed(3) ?? "—"}`],
                              [`Samples within ${measurement.diagnostics.near_gate_distance_m} m of A / B`, `${measurement.diagnostics.gate_a_near_samples} / ${measurement.diagnostics.gate_b_near_samples}`],
                              ["Ambiguous / overlapping observations", `${measurement.diagnostics.ambiguous_observations} / ${measurement.diagnostics.overlapping_box_observations}`],
                            ].map(([label, value]) => <div key={label}><dt>{label}</dt><dd className="mono">{value}</dd></div>)}
                          </dl>
                          <p>Motion residuals can reflect jitter or real acceleration. These observations are not an error bound. Export includes the retained source samples and original calibration geometry.</p>
                        </details>
                      )}
                    </td>
                    <td className="mono">{elapsed(measurement.timestamp_s)}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        ) : (
          <div className="table-empty">
            <Icon name="clock" size={23} />
            <strong>No completed measurements</strong>
            <p>
              Apply a measured calibration and configure gates. Tracked vehicles
              must cross both gates with reliable source timestamps.
            </p>
          </div>
        )}
        <div className="table-note">
          <Icon name="info" size={12} />
          <span>
            Estimated average straight-line ground displacement / source time.
            Valid means the configured checks passed; it is not an independent
            accuracy certification. Bounding-box contact points remain
            approximate.
          </span>
        </div>
      </div>
    </section>
  );
}
