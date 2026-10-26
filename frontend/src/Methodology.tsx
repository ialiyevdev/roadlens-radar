import Icon from "./Icon";

export default function Methodology() {
  return (
    <div className="methodology-grid">
      <section className="panel methodology-intro">
        <span className="eyebrow">
          PHASE 06 / LOCAL VISION & TRAFFIC WORKSPACE
        </span>
        <h2>
          Observe first.
          <br />
          Measure with evidence.
        </h2>
        <p>
          RoadLens Radar is a local computer vision workspace for vehicle
          detection, temporary multi-object tracking, and calibrated monocular
          video speed estimation. Measured geometry and source-frame timing make
          every estimate inspectable.
        </p>
        <div className="method-tags">
          <span>CPU inference</span>
          <span>Local processing</span>
          <span>Session-scoped tracking</span>
          <span>Measured road-plane references</span>
        </div>
      </section>
      <section className="panel prose-panel">
        <div className="panel-heading">
          <h2>Crossings, coverage & observed occupancy</h2>
          <Icon name="pulse" size={19} />
        </div>
        <p>
          Traffic Intelligence counts finite-line crossings independently of
          speed gates. Source-timed trajectories cross hysteresis boundaries,
          while bounded temporal and spatial suppression flags possible
          duplicate identities. Supported vehicle classes accumulate
          confidence-weighted votes; uncertain classifications remain unknown.
        </p>
        <p>
          Traffic rates divide observed crossings by covered source seconds.
          Pauses, missing timestamps, source gaps and configuration changes
          split coverage. A normalized hourly rate from a short recording is not
          a measured hour of traffic. Multiple lines and overlapping zones can
          observe the same vehicle more than once.
        </p>
        <p>
          Monitoring polygons are manually configured image regions or
          calibrated ground regions. Occupancy and pixel stationarity are
          camera-visible heuristics with configurable thresholds. Metric
          slow-speed indicators and speed distributions require valid calibrated
          measurements. Independently annotated held-out footage and matched
          references are required to evaluate physical counting, class and speed
          accuracy.
        </p>
      </section>
      <section className="panel prose-panel">
        <div className="panel-heading">
          <h2>Detection & tracking</h2>
          <Icon name="target" size={19} />
        </div>
        <p>
          YOLOX-S with INT8 weights runs through OpenCV DNN on the CPU. Select
          320, 416, or 640 pixel inference input; smaller inputs reduce
          computation but may miss small vehicles. Actual performance depends on
          the source and hardware. Cars, trucks, buses, and motorcycles are
          mapped from the model’s COCO classes.
        </p>
        <p>
          Global motion and IoU assignment links boxes across short gaps and
          confirms tracks after repeated observations. Smoothed association
          motion leaves measurement boxes unchanged. IDs belong to one session;
          ambiguity is flagged and expiry creates a new hypothesis. Live
          ID-switch suspicions require annotated truth to verify.
        </p>
        <p>
          Counts represent confirmed tracks observed during this session. They
          are not gate-crossing counts or independently verified traffic totals.
        </p>
      </section>
      <section className="panel prose-panel">
        <div className="panel-heading">
          <h2>Independent references and honest comparisons</h2>
          <Icon name="pulse" size={19} />
        </div>
        <p>
          Validation matches recording, event and measurement IDs against a
          separately declared reference method. Ambiguous associations,
          self-references and rejected estimates are excluded from speed-error
          statistics. MAE, RMSE, signed bias and tolerance analysis retain their
          eligible sample sizes; small groups withhold aggregate errors.
        </p>
        <p>
          No real-world reference data available. Bundled speed data and
          tracking identities are synthetic. Their results test software
          behavior and do not establish real-road accuracy. Exported evidence
          preserves calibration checks, source samples, gate interpolation
          intervals and contact-motion diagnostics for investigation. No
          empirical correction multiplier or speed-confidence percentage is
          used.
        </p>
      </section>
      <section className="panel prose-panel">
        <div className="panel-heading">
          <h2>Timing is part of the measurement</h2>
          <Icon name="clock" size={19} />
        </div>
        <p>
          Live camera timing uses a monotonic clock at frame acquisition. A
          bounded capture buffer favors recent frames when inference falls
          behind. Dropped frames remain visible in diagnostics.
        </p>
        <p>
          Recorded-video timing uses source timestamps when usable. A
          declared-frame-rate fallback is labeled in diagnostics. Inference
          completion time is never used as the original capture time.
        </p>
        <p>
          Capture FPS, processing FPS, inference time, and total processing
          latency are separate quantities. Values shown in the dashboard come
          from the running source.
        </p>
        <p>
          Pausing rejects incomplete gate traversals. Recorded source timestamps
          retain their original meaning; paused wall-clock time is never added
          to a vehicle measurement. Missing or non-monotonic timing cannot
          produce a valid speed.
        </p>
      </section>
      <section className="panel prose-panel">
        <div className="panel-heading">
          <h2>Reproducible field sessions</h2>
          <Icon name="target" size={19} />
        </div>
        <p>
          Save the source, camera settings, calibration, gates, original results
          and environment together. Draw reviewed vehicle boxes with persistent
          manual identities in Vehicle annotations. Predicted tracker IDs remain
          separate from ground truth.
        </p>
        <p>
          Import independent reference events, describe both clocks and
          establish independent synchronization anchors with documented
          uncertainty. Confirm each vehicle correspondence explicitly; uncertain
          alignment and ambiguous matches remain excluded. Keep complete
          recordings and collection groups in one development, calibration or
          held-out partition.
        </p>
        <p>
          Real-world validation compares eligible held-out events and exports
          JSON, CSV and HTML evidence with exclusions and timing diagnostics.
          Preserve the source recording, session and annotation exports beside
          the report. A synthetic example exercises this workflow without
          establishing roadway accuracy.
        </p>
      </section>
      <section className="panel prose-panel">
        <div className="panel-heading">
          <h2>Geometry before speed</h2>
          <Icon name="shield" size={19} />
        </div>
        <p>
          Pair at least four well-spread road-plane pixels with measured ground
          coordinates in meters. A homography maps those pixels to the road
          plane. Camera height, guessed lane widths, and guessed vehicle lengths
          do not establish metric scale.
        </p>
        <p>
          Optional checkerboard intrinsics correct lens distortion before
          detection. Corrected boxes, contacts, gates and road references share
          one pixel space. Applying or disabling correction requires a fresh
          road calibration; checkerboard residuals alone do not establish speed
          accuracy.
        </p>
        <p>
          Fit residuals check consistency. Independent check points test
          projection away from the fitted references; a zero four-point residual
          is not proof of accuracy. Profiles are tied to the source and image
          geometry and must be explicitly applied for each observation. Disable
          calibration after moving the camera or changing zoom; movement is not
          detected automatically.
        </p>
        <div className="methodology-warning">
          <span className="status-dot" />
          Not independently validated
        </div>
      </section>
      <section className="panel prose-panel">
        <div className="panel-heading">
          <h2>What a speed estimate means</h2>
          <Icon name="arrow" size={19} />
        </div>
        <p>
          The bottom-center of a vehicle box approximates its ground contact
          point. The system projects it into meters, intersects consecutive
          observations with each finite gate segment, and interpolates the
          crossing positions and source timestamps.
        </p>
        <p>
          Speed is straight-line ground displacement between the two crossing
          positions divided by elapsed source time, multiplied by 3.6 for km/h.
          Curved paths can be underestimated. Valid, approximate, and rejected
          results reflect observable geometry, timing, and continuity checks;
          they are not statistically calibrated confidence intervals.
        </p>
        <p>
          Lens distortion, road grade, occlusion, clipped boxes, box jitter,
          sparse sampling, and identity changes can affect results. This is a
          portfolio engineering system, not certified enforcement equipment.
          Controlled trajectories validate the calculation; real-road accuracy
          requires independent measured ground truth.
        </p>
      </section>
      <section className="panel prose-panel">
        <div className="panel-heading">
          <h2>Local by design</h2>
          <Icon name="chip" size={19} />
        </div>
        <p>
          The React interface communicates with the local FastAPI server. Frames
          are captured, detected, tracked, and annotated in Python. The preview
          is an MJPEG stream; diagnostics are polled separately.
        </p>
        <p>
          No audio, face recognition, number plate recognition, or cross-session
          identity matching is implemented. Camera footage is not recorded
          automatically. Uploaded recordings are copied to local data/uploads;
          stop the backend before removing those files.
        </p>
        <p>
          Use controlled tests and appropriately licensed video first.
          Public-road observation requires consideration of the applicable
          privacy and legal conditions.
        </p>
      </section>
    </div>
  );
}
