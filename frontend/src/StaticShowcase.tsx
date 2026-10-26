import Icon from "./Icon";
import Showcase from "./Showcase";

export default function StaticShowcase() {
  return (
    <div className="static-showcase-shell">
      <a className="skip-link" href="#main">
        Skip to content
      </a>
      <header className="static-showcase-header">
        <a className="brand" href="#main" aria-label="RoadLens Radar showcase">
          <span className="brand-mark">
            <Icon name="target" size={25} />
          </span>
          <span>
            roadlens<span className="brand-subtitle">RADAR</span>
          </span>
        </a>
        <span className="local-tag">STATIC PORTFOLIO PREVIEW</span>
      </header>
      <main id="main">
        <div className="page-heading">
          <div>
            <div className="eyebrow">
              COMPUTER VISION / MEASUREMENT ENGINEERING
            </div>
            <h1>RoadLens Radar</h1>
            <p>
              A local CPU vision workspace for detection, tracking and
              inspectable traffic measurement.
            </p>
          </div>
        </div>
        <Showcase />
        <footer className="workspace-footer">
          <span>Read-only portfolio build · no backend connection</span>
          <span>Real-world roadway accuracy remains unverified.</span>
        </footer>
      </main>
    </div>
  );
}
