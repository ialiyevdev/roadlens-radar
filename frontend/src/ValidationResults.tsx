import { useState } from "react";
import Icon from "./Icon";
import { SpeedCharts, finite } from "./ValidationCharts";
import { filterValidationRows, formatMetric } from "./validationPresentation";
import type { ValidationReport } from "./validationTypes";

function OverviewMetric({
  label,
  value,
  note,
  unit,
}: {
  label: string;
  value: string;
  note: string;
  unit?: string;
}) {
  return (
    <div className="metric-card">
      <div className="metric-label">{label}</div>
      <div className="metric-value">
        {value}
        <span>{unit}</span>
      </div>
      <p>{note}</p>
    </div>
  );
}
export default function ValidationResults({
  report,
}: {
  report: ValidationReport;
}) {
  const [status, setStatus] = useState("all");
  const [search, setSearch] = useState("");
  const rows = filterValidationRows(report.rows, status, search);
  return (
    <>
      <div className="validation-metrics">
        <OverviewMetric
          label="Measurements evaluated"
          value={String(report.total_records)}
          note={`${report.completed_count} completed · ${finite(report.completion_rate_percent) ? `${formatMetric(report.completion_rate_percent)}% completion` : "completion rate unavailable"}`}
        />
        <OverviewMetric
          label="Reference matched"
          value={String(report.reference_matched_count)}
          note={`${report.compared_count} eligible speed comparisons`}
        />
        <OverviewMetric
          label="Mean absolute error"
          value={formatMetric(report.summary.mae_kmh)}
          unit="km/h"
          note={`N = ${report.summary.n} eligible pairs`}
        />
        <OverviewMetric
          label="Root mean squared error"
          value={formatMetric(report.summary.rmse_kmh)}
          unit="km/h"
          note="Larger errors receive more weight"
        />
        <OverviewMetric
          label="Average signed error"
          value={formatMetric(report.summary.bias_kmh, true)}
          unit="km/h"
          note="Positive means an overestimate"
        />
        <OverviewMetric
          label="Rejection rate"
          value={formatMetric(report.rejection_rate_percent)}
          unit="%"
          note={`${report.rejected_count} rejected / ${report.total_records} records`}
        />
      </div>
      {!report.summary.sufficient_sample && (
        <p className="studio-notice" role="status">
          Insufficient comparisons for aggregate error statistics. N ={" "}
          {report.summary.n}; at least {report.options.minimum_group_samples}{" "}
          required by these analysis settings.
        </p>
      )}
      <SpeedCharts rows={report.rows} />
      <section
        className="panel validation-group-panel"
        aria-labelledby="group-heading"
      >
        <div className="panel-heading">
          <h2 id="group-heading">Error analysis by measurement group</h2>
          <span>
            Applied minimum N = {report.options.minimum_group_samples}
          </span>
        </div>
        <div className="table-scroll">
          <table aria-label="Validation group statistics">
            <thead>
              <tr>
                <th>Group</th>
                <th>N</th>
                <th>MAE · km/h</th>
                <th>RMSE · km/h</th>
                <th>Bias · km/h</th>
                <th>Median AE</th>
                <th>P90 AE</th>
                <th>MAPE</th>
                <th>Tolerance analysis</th>
              </tr>
            </thead>
            <tbody>
              {report.groups.map((group) => (
                <tr key={group.id}>
                  <td>
                    {group.label}
                    {!group.metrics.sufficient_sample && (
                      <small className="validation-cell-note">
                        Insufficient sample
                      </small>
                    )}
                  </td>
                  <td className="mono">{group.metrics.n}</td>
                  <td className="mono">
                    {formatMetric(group.metrics.mae_kmh)}
                  </td>
                  <td className="mono">
                    {formatMetric(group.metrics.rmse_kmh)}
                  </td>
                  <td className="mono">
                    {formatMetric(group.metrics.bias_kmh, true)}
                  </td>
                  <td className="mono">
                    {formatMetric(group.metrics.median_absolute_error_kmh)}
                  </td>
                  <td className="mono">
                    {formatMetric(group.metrics.p90_absolute_error_kmh)}
                  </td>
                  <td className="mono">
                    {formatMetric(group.metrics.mape_percent)}
                    {finite(group.metrics.mape_percent) ? "%" : ""}
                    <small className="validation-cell-note">
                      N = {group.metrics.percentage_sample_count}, reference
                      &gt; 0
                    </small>
                  </td>
                  <td>
                    {group.metrics.tolerance_bands.map((band) => (
                      <div key={band.tolerance_kmh}>
                        ±{band.tolerance_kmh} km/h:{" "}
                        {formatMetric(band.within_percent)}
                        {finite(band.within_percent) ? "%" : ""}{" "}
                        <span className="validation-muted">
                          ({band.within_count}/{group.metrics.n})
                        </span>
                      </div>
                    ))}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
        <div className="table-note">
          <Icon name="info" size={12} />
          <span>
            Thresholds describe this dataset. They do not certify accuracy.
            Speed-range and direction groups appear only when the minimum sample
            size is met.
          </span>
        </div>
      </section>
      <section
        className="panel validation-inspection"
        aria-labelledby="inspection-heading"
      >
        <div className="panel-heading">
          <div>
            <h2 id="inspection-heading">Measurement inspection</h2>
            <p className="panel-description">
              Each comparison retains its original status, reference method, and
              diagnostic fields.
            </p>
          </div>
          <span>
            {rows.length} / {report.rows.length} rows
          </span>
        </div>
        <div className="validation-filters">
          <label>
            Status filter
            <select
              value={status}
              onChange={(event) => setStatus(event.target.value)}
            >
              <option value="all">All measurements</option>
              <option value="valid">Valid</option>
              <option value="approximate">Approximate</option>
              <option value="rejected">Rejected</option>
              <option value="excluded">Excluded from comparison</option>
            </select>
          </label>
          <label>
            Search measurement or recording
            <input
              type="search"
              value={search}
              onChange={(event) => setSearch(event.target.value)}
              placeholder="Measurement, vehicle, or recording ID"
            />
          </label>
        </div>
        {rows.length ? (
          <div className="table-scroll">
            <table aria-label="Validation measurements">
              <thead>
                <tr>
                  <th>Measurement / vehicle</th>
                  <th>Estimate · km/h</th>
                  <th>Reference · km/h</th>
                  <th>Signed error</th>
                  <th>Absolute error</th>
                  <th>Status / event association</th>
                  <th>Diagnostics / reference</th>
                </tr>
              </thead>
              <tbody>
                {rows.map((row, i) => (
                  <tr
                    key={`${row.record.recording_id}-${row.record.observation_id}-${row.record.measurement_id}-${i}`}
                  >
                    <td className="mono">
                      {row.record.measurement_id}
                      <small className="validation-cell-note">
                        {row.record.vehicle_id || "No vehicle ID"}
                        <br />
                        {row.record.recording_id} / {row.record.observation_id}
                      </small>
                    </td>
                    <td className="mono">
                      {formatMetric(row.record.estimated_speed_kmh)}
                    </td>
                    <td className="mono">
                      {formatMetric(row.record.reference_speed_kmh)}
                    </td>
                    <td className="mono">
                      {formatMetric(row.error_kmh, true)}
                    </td>
                    <td className="mono">
                      {formatMetric(row.absolute_error_kmh)}
                    </td>
                    <td>
                      <span className={`quality-badge ${row.record.status}`}>
                        {row.record.status}
                      </span>
                      <small className="validation-cell-note">
                        {row.comparison_included
                          ? "Included comparison"
                          : "Excluded comparison"}
                        <br />
                        {row.reference_matched
                          ? "Reference event matched"
                          : "Reference event not matched"}
                      </small>
                    </td>
                    <td className="validation-reasons">
                      {row.exclusion_reasons.length > 0 && (
                        <ul>
                          {row.exclusion_reasons.map((reason, index) => (
                            <li key={index}>{reason}</li>
                          ))}
                        </ul>
                      )}
                      <span>
                        {row.record.reference_method || "No reference method"}
                      </span>
                      <small className="validation-cell-note">
                        Calibration:{" "}
                        {row.record.calibration_id || "Not supplied"}
                      </small>
                      <details>
                        <summary>Reference event details</summary>
                        <dl>
                          <div>
                            <dt>Recording / observation / measurement</dt>
                            <dd>
                              {row.record.reference_recording_id ||
                                "Not supplied"}{" "}
                              /{" "}
                              {row.record.reference_observation_id ||
                                "Not supplied"}{" "}
                              /{" "}
                              {row.record.reference_measurement_id ||
                                "Not supplied"}
                            </dd>
                          </div>
                          <div>
                            <dt>Independent reference declared</dt>
                            <dd>
                              {row.record.reference_independent ? "Yes" : "No"}
                            </dd>
                          </div>
                          <div>
                            <dt>Reference source timestamp · s</dt>
                            <dd>
                              {formatMetric(row.record.reference_timestamp_s)}
                            </dd>
                          </div>
                          <div>
                            <dt>Reference source interval · s</dt>
                            <dd>
                              {formatMetric(
                                row.record.reference_interval_start_s,
                              )}{" "}
                              to{" "}
                              {formatMetric(
                                row.record.reference_interval_end_s,
                              )}
                            </dd>
                          </div>
                        </dl>
                      </details>
                      {Object.keys(row.record.diagnostics || {}).length > 0 && (
                        <details>
                          <summary>Original diagnostic fields</summary>
                          <dl>
                            {Object.entries(row.record.diagnostics!).map(
                              ([key, value]) => (
                                <div key={key}>
                                  <dt>{key}</dt>
                                  <dd>
                                    {value == null
                                      ? "Not available"
                                      : String(value)}
                                  </dd>
                                </div>
                              ),
                            )}
                          </dl>
                        </details>
                      )}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        ) : (
          <div className="table-empty">
            <Icon name="target" size={23} />
            <strong>
              {report.rows.length
                ? "No measurements match these filters"
                : "This dataset contains no measurements"}
            </strong>
            <p>
              {report.rows.length
                ? "Change the status filter or search text to inspect other records."
                : "Import a dataset with reference events to begin comparing speeds."}
            </p>
          </div>
        )}
      </section>
      {report.limitations.length > 0 && (
        <details className="panel validation-limitations">
          <summary>Evaluation assumptions and limitations</summary>
          <ul>
            {report.limitations.map((limitation, i) => (
              <li key={i}>{limitation}</li>
            ))}
          </ul>
        </details>
      )}
    </>
  );
}
