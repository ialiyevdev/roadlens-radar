import { useEffect, useState } from "react";
import Icon from "./Icon";
import { finite } from "./ValidationCharts";
import ValidationResults from "./ValidationResults";
import TrackingBenchmarkResults from "./TrackingBenchmarkResults";
import { downloadResult, validationApi } from "./validationApi";
import type {
  TrackingReport,
  ValidationDataset,
  ValidationOptions,
  ValidationReport,
} from "./validationTypes";

function errorMessage(error: unknown) {
  return error instanceof Error
    ? error.message
    : "The local request could not be completed.";
}
function ExportButtons({
  disabled,
  onExport,
  label,
}: {
  disabled: boolean;
  onExport: (format: "csv" | "json") => void;
  label: string;
}) {
  return (
    <div className="validation-export-buttons">
      <button
        className="button button-secondary compact"
        disabled={disabled}
        onClick={() => onExport("csv")}
        aria-label={`Export ${label} CSV`}
      >
        Export CSV
      </button>
      <button
        className="button button-secondary compact"
        disabled={disabled}
        onClick={() => onExport("json")}
        aria-label={`Export ${label} JSON`}
      >
        Export JSON
      </button>
    </div>
  );
}
export default function ValidationBenchmarks({
  connected,
}: {
  connected: boolean;
}) {
  const [datasets, setDatasets] = useState<ValidationDataset[]>([]);
  const [selected, setSelected] = useState("0");
  const [report, setReport] = useState<ValidationReport | null>(null);
  const [bands, setBands] = useState(["3", "5"]);
  const [minimumSamples, setMinimumSamples] = useState("3");
  const [busy, setBusy] = useState<string | null>("Loading example dataset");
  const [error, setError] = useState<string | null>(null);
  const [benchmark, setBenchmark] = useState<TrackingReport | null>(null);
  const [benchmarkBusy, setBenchmarkBusy] = useState<string | null>(null);
  const [benchmarkError, setBenchmarkError] = useState<string | null>(null);
  const dataset = datasets[Number(selected)];
  const options: ValidationOptions = {
    tolerance_bands_kmh: bands.map(Number),
    minimum_group_samples: Number(minimumSamples),
  };
  const validOptions =
    bands.every(
      (value) =>
        value.trim() !== "" &&
        finite(Number(value)) &&
        Number(value) >= 0 &&
        Number(value) <= 1000,
    ) &&
    Number(bands[0]) !== Number(bands[1]) &&
    minimumSamples.trim() !== "" &&
    Number.isInteger(Number(minimumSamples)) &&
    Number(minimumSamples) >= 3 &&
    Number(minimumSamples) <= 10000;
  useEffect(() => {
    let active = true;
    validationApi
      .example()
      .then((example) => {
        if (active) setDatasets([example]);
      })
      .catch((cause: unknown) => {
        if (active) setError(errorMessage(cause));
      })
      .finally(() => {
        if (active) setBusy(null);
      });
    return () => {
      active = false;
    };
  }, []);
  async function importDataset(file: File) {
    setBusy("Importing validation dataset");
    setError(null);
    try {
      const imported = await validationApi.import(file);
      setSelected(String(datasets.length));
      setDatasets([...datasets, imported]);
      setReport(null);
    } catch (cause) {
      setError(errorMessage(cause));
    } finally {
      setBusy(null);
    }
  }
  async function evaluate() {
    if (!dataset || !validOptions) return;
    setBusy("Evaluating independent reference pairs");
    setError(null);
    try {
      setReport(await validationApi.evaluate(dataset, options));
    } catch (cause) {
      setError(errorMessage(cause));
    } finally {
      setBusy(null);
    }
  }
  async function exportValidation(format: "csv" | "json") {
    if (!dataset || !report) return;
    setBusy("Preparing validation export");
    setError(null);
    try {
      downloadResult(
        await validationApi.export(dataset, report.options, format),
        `roadlens-validation.${format}`,
      );
    } catch (cause) {
      setError(errorMessage(cause));
    } finally {
      setBusy(null);
    }
  }
  async function runBenchmark() {
    setBenchmarkBusy("Running baseline and improved trackers");
    setBenchmarkError(null);
    try {
      setBenchmark(await validationApi.benchmark());
    } catch (cause) {
      setBenchmarkError(errorMessage(cause));
    } finally {
      setBenchmarkBusy(null);
    }
  }
  async function exportBenchmark(format: "csv" | "json") {
    if (!benchmark) return;
    setBenchmarkBusy("Preparing benchmark export");
    setBenchmarkError(null);
    try {
      downloadResult(
        await validationApi.exportBenchmark(benchmark, format),
        `roadlens-tracking-benchmark.${format}`,
      );
    } catch (cause) {
      setBenchmarkError(errorMessage(cause));
    } finally {
      setBenchmarkBusy(null);
    }
  }
  return (
    <div className="validation-workspace">
      <section
        className="panel validation-controls"
        aria-labelledby="validation-data-heading"
      >
        <div className="panel-heading">
          <div>
            <h2 id="validation-data-heading">Independent speed validation</h2>
            <p className="panel-description">
              Compare estimates with independently measured references for the
              same vehicle and event.
            </p>
          </div>
          <Icon name="target" size={20} />
        </div>
        {error && (
          <div className="inline-error" role="alert">
            {error}
          </div>
        )}
        <div className="validation-control-grid">
          <div>
            <label className="validation-field">
              Comparison dataset
              <select
                value={selected}
                disabled={!!busy || !datasets.length}
                onChange={(event) => {
                  setSelected(event.target.value);
                  setReport(null);
                }}
              >
                {!datasets.length && (
                  <option value="0">No dataset loaded</option>
                )}
                {datasets.map((item, i) => (
                  <option value={i} key={i}>
                    {item.name} (
                    {item.provenance === "synthetic"
                      ? "synthetic"
                      : "real-world"}
                    )
                  </option>
                ))}
              </select>
            </label>
            <div className="validation-import">
              <label
                className={`button button-secondary ${busy || !connected ? "disabled" : ""}`}
              >
                <Icon name="upload" size={14} />
                Import CSV / JSON
                <input
                  className="visually-hidden"
                  type="file"
                  accept=".csv,.json,text/csv,application/json"
                  aria-label="Import validation dataset"
                  disabled={!!busy || !connected}
                  onChange={(event) => {
                    const file = event.target.files?.[0];
                    event.target.value = "";
                    if (file) void importDataset(file);
                  }}
                />
              </label>
              <span>Local analysis only · no footage required</span>
            </div>
            <p className="panel-description">
              Include explicit recording, observation, and measurement reference
              IDs, an independent reference method, and event association.
              Ambiguous matches are excluded.
            </p>
            {!datasets.length && !busy && (
              <button
                className="text-button"
                disabled={!connected}
                onClick={() => {
                  setBusy("Loading example dataset");
                  setError(null);
                  void validationApi
                    .example()
                    .then((example) => setDatasets([example]))
                    .catch((cause: unknown) => setError(errorMessage(cause)))
                    .finally(() => setBusy(null));
                }}
              >
                Load synthetic example
              </button>
            )}
          </div>
          <div className="validation-options">
            <fieldset>
              <legend>Analysis settings</legend>
              <div className="validation-tolerance-inputs">
                {bands.map((band, i) => (
                  <label key={i}>
                    Tolerance band {i + 1} · km/h
                    <input
                      type="number"
                      min="0"
                      max="1000"
                      step="0.5"
                      value={band}
                      disabled={!!busy}
                      onChange={(event) => {
                        setBands(
                          bands.map((value, index) =>
                            index === i ? event.target.value : value,
                          ),
                        );
                        setReport(null);
                      }}
                    />
                  </label>
                ))}
              </div>
              <label>
                Minimum group samples
                <input
                  type="number"
                  min="3"
                  max="10000"
                  step="1"
                  value={minimumSamples}
                  disabled={!!busy}
                  onChange={(event) => {
                    setMinimumSamples(event.target.value);
                    setReport(null);
                  }}
                />
              </label>
              <p className="field-note">
                Tolerance bands are analysis thresholds. Small groups retain
                counts but omit aggregate error statistics.
              </p>
              {!validOptions && (
                <p className="danger-text">
                  Enter two different bands from 0 to 1000 km/h and a
                  whole-number minimum from 3 to 10000.
                </p>
              )}
            </fieldset>
          </div>
        </div>
        {dataset && (
          <div className={`validation-provenance-banner ${dataset.provenance}`}>
            <span className="validation-provenance">
              {dataset.provenance === "synthetic"
                ? "SYNTHETIC DATASET"
                : "REAL-WORLD DATASET"}
            </span>
            <div>
              <strong>
                {dataset.provenance === "synthetic"
                  ? "Software validation, not measured road accuracy"
                  : "Reference quality must be established independently"}
              </strong>
              <p>{dataset.description || "No dataset description supplied."}</p>
              <p>
                {dataset.records.length} records ·{" "}
                {dataset.provenance === "synthetic"
                  ? "Generated references do not establish real-world accuracy."
                  : "An independent declaration alone does not certify reference precision."}
              </p>
            </div>
          </div>
        )}
        <div className="validation-actions">
          <button
            className="button button-primary"
            disabled={!connected || !!busy || !dataset || !validOptions}
            onClick={() => void evaluate()}
          >
            <Icon name="play" size={14} />
            Evaluate speed references
          </button>
          <ExportButtons
            label="validation"
            disabled={!!busy || !report || !connected}
            onExport={(format) => void exportValidation(format)}
          />
          {busy && <span role="status">{busy}…</span>}
        </div>
      </section>
      {report ? (
        <ValidationResults
          key={`${selected}-${report.dataset_name}`}
          report={report}
        />
      ) : (
        <div className="panel validation-empty">
          <Icon name="pulse" size={25} />
          <h2>No speed evaluation yet</h2>
          <p>
            Select the synthetic example or import a CSV / JSON dataset, then
            evaluate its reference pairs. Error statistics remain unavailable
            until enough unambiguous comparisons exist.
          </p>
        </div>
      )}
      <section
        className="panel validation-benchmark"
        aria-labelledby="tracking-benchmark-heading"
      >
        <div className="panel-heading">
          <div>
            <h2 id="tracking-benchmark-heading">Tracking benchmark</h2>
            <p className="panel-description">
              Reproducible synthetic identities, gaps, jitter, ambiguity, and
              source-time intervals.
            </p>
          </div>
          <Icon name="chip" size={19} />
        </div>
        {benchmarkError && (
          <div className="inline-error" role="alert">
            {benchmarkError}
          </div>
        )}
        <div className="validation-actions">
          <button
            className="button button-secondary"
            disabled={!connected || !!benchmarkBusy}
            onClick={() => void runBenchmark()}
          >
            <Icon name="play" size={14} />
            Run tracking benchmark
          </button>
          <ExportButtons
            label="tracking benchmark"
            disabled={!benchmark || !!benchmarkBusy || !connected}
            onExport={(format) => void exportBenchmark(format)}
          />
          {benchmarkBusy && <span role="status">{benchmarkBusy}…</span>}
        </div>
        {benchmark ? (
          <TrackingBenchmarkResults
            key={benchmark.generated_at_utc}
            report={benchmark}
          />
        ) : (
          <div className="validation-benchmark-empty">
            <p>
              Run both trackers on identical annotated trajectories to inspect
              identity switches, fragmentation, and measured tracking cost.
            </p>
            <span>
              Tracking benchmark results are separate from detector quality and
              real-world speed accuracy.
            </span>
          </div>
        )}
      </section>
    </div>
  );
}
