import Icon from "./Icon";
import type { Point } from "./types";
import type { ReferenceRow } from "./calibrationCoordinates";

interface Props {
  rows: ReferenceRow[];
  busy: boolean;
  frame: unknown;
  changeRow: (id: number, values: Partial<ReferenceRow>) => void;
  removeRow: (id: number) => void;
  clearRows: () => void;
  validate: () => void;
}
export default function ReferenceCoordinates({
  rows,
  busy,
  frame,
  changeRow,
  removeRow,
  clearRows,
  validate,
}: Props) {
  return (
    <section className="panel reference-panel">
      <div className="panel-heading">
        <h2>Reference coordinates</h2>
        <span className="count-badge">
          {rows.filter((row) => !row.check).length} fit ·{" "}
          {rows.filter((row) => row.check).length} check
        </span>
      </div>
      {rows.length ? (
        <div className="table-scroll">
          <table aria-label="Calibration reference coordinates">
            <thead>
              <tr>
                <th>Point</th>
                <th>Source x / y · px</th>
                <th>World X · m</th>
                <th>World Y · m</th>
                <th>Role</th>
                <th />
              </tr>
            </thead>
            <tbody>
              {rows.map((row, index) => (
                <tr key={row.id}>
                  <td className="mono">{index + 1}</td>
                  <td className="pixel-inputs">
                    {row.image.map((value, axis) => (
                      <input
                        key={axis}
                        type="number"
                        step="0.1"
                        aria-label={`Point ${index + 1} source ${axis ? "y" : "x"}`}
                        value={Number.isFinite(value) ? value : ""}
                        onChange={(event) =>
                          changeRow(row.id, {
                            image: row.image.map((v, j) =>
                              j === axis
                                ? event.target.value === ""
                                  ? Number.NaN
                                  : Number(event.target.value)
                                : v,
                            ) as Point,
                          })
                        }
                      />
                    ))}
                  </td>
                  <td>
                    <input
                      type="number"
                      step="any"
                      aria-label={`Point ${index + 1} world X meters`}
                      value={row.x}
                      placeholder="Measured X"
                      onChange={(event) =>
                        changeRow(row.id, { x: event.target.value })
                      }
                    />
                  </td>
                  <td>
                    <input
                      type="number"
                      step="any"
                      aria-label={`Point ${index + 1} world Y meters`}
                      value={row.y}
                      placeholder="Measured Y"
                      onChange={(event) =>
                        changeRow(row.id, { y: event.target.value })
                      }
                    />
                  </td>
                  <td>
                    <select
                      aria-label={`Point ${index + 1} role`}
                      value={row.check ? "check" : "fit"}
                      onChange={(event) =>
                        changeRow(row.id, {
                          check: event.target.value === "check",
                        })
                      }
                    >
                      <option value="fit">Fit</option>
                      <option value="check">Check</option>
                    </select>
                  </td>
                  <td>
                    <button
                      className="icon-button"
                      aria-label={`Remove point ${index + 1}`}
                      onClick={() => removeRow(row.id)}
                    >
                      <Icon name="close" size={13} />
                    </button>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      ) : (
        <div className="table-empty">
          <strong>No measured correspondences</strong>
          <p>
            Freeze a frame and click at least four ground-plane reference
            points.
          </p>
        </div>
      )}
      <div className="reference-actions">
        <button
          className="text-button"
          disabled={!rows.length || busy}
          onClick={clearRows}
        >
          Clear reference points
        </button>
        <button
          className="button button-secondary compact"
          disabled={busy || !frame}
          onClick={validate}
        >
          Validate calibration
        </button>
      </div>
    </section>
  );
}
