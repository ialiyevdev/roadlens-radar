import type { Overlays, Session } from "./types";

const layers: [keyof Overlays, string][] = [
  ["boxes", "Vehicle boxes"],
  ["trajectories", "Trajectories"],
  ["contact_points", "Contact points"],
  ["gates", "Gates"],
  ["grid", "Ground grid"],
  ["speeds", "Completed valid speeds"],
];
export default function OverlayControls({
  session,
  disabled,
  onChange,
}: {
  session: Session;
  disabled: boolean;
  onChange: (overlays: Overlays) => void;
}) {
  const values = session.overlays ?? {
    boxes: true,
    trajectories: true,
    contact_points: false,
    gates: true,
    grid: false,
    speeds: true,
  };
  return (
    <details className="overlay-controls">
      <summary>Video overlay layers</summary>
      <div>
        {layers.map(([key, label]) => (
          <label className="check-label" key={key}>
            <input
              type="checkbox"
              checked={values[key]}
              disabled={disabled}
              onChange={(event) =>
                onChange({ ...values, [key]: event.target.checked })
              }
            />
            {label}
          </label>
        ))}
      </div>
      <p className="field-note">
        Tracking IDs, classes and traffic regions are independently controlled
        in Traffic Intelligence → Lines & zones.
      </p>
    </details>
  );
}
