# Calibration and speed measurement

RoadLens estimates average ground-plane displacement from a stationary monocular
camera. The camera must view a mostly planar road, and metric scale must come
from measured references. An elevated viewpoint or camera height alone provides
no usable scale. Estimates are not independently validated or enforcement grade.

## Prepare measured references

Choose an origin and two perpendicular axes on the road plane. Record the X/Y
coordinates, in meters, of identifiable road markings or surveyed ground points.
Use measurements collected from a safe, permitted location; do not enter traffic
to place markers or take measurements. Guessed lane widths and vehicle lengths
are unsuitable references.

Use at least four distinct points spread around the intended measurement area,
including its near and far ends. Avoid points concentrated on one lane marking
or a narrow strip. Measure additional points when possible, and reserve some as
independent checks rather than using all of them to fit the transformation.

## Configure a source and profile

1. Start a recorded road video or a stationary webcam from **Camera & video**.
   Pause after a usable frame appears while preparing the calibration. Freezing
   a reference frame does not itself pause the observation.
2. Open **Calibration & gates** and choose **Freeze frame**. This captures the raw image,
   without detection overlays. Click the reference locations, then enter each
   measured world X/Y coordinate and a profile name. Drag numbered points to
   adjust their image positions; remove and replace an incorrectly chosen point.
3. Set reserved references' **Role** to **Check**. They are projected for
   evaluation but do not influence the fitted homography.
4. Validate the references and inspect the coverage, grid, residuals, errors and
   warnings. Correct mistakes before choosing **Save profile**.
5. Confirm that the camera, zoom and image geometry match, then choose **Apply
   to this observation**. Applying is explicit for every new observation.

Coordinates stay in source pixels when the preview resizes; world positions use meters. The stored
profile includes the source identifier, width, height, rotation, mirroring and
crop metadata. Current capture uses unrotated, unmirrored, uncropped frames.
Recorded sources use a content hash; cameras use their selected device index.

A mismatched source or image geometry cannot activate a profile. A resolution
change during observation invalidates it. Resolution matching cannot detect a
moved camera, optical zoom or a different camera assigned the same index: use
**Camera moved / disable calibration**, collect a new frame and recalibrate.
Profiles are local JSON files in `data/calibrations`; no recording is needed.

## Understand geometry diagnostics

The backend fits an OpenCV image-to-world homography. More than four fitting
pairs use RANSAC with a **0.25 m** destination-space threshold; rejected fitting
pairs are reported. Projections and gates are restricted to the convex hull of
accepted fitting image points, avoiding unchecked extrapolation.

The fit residual describes agreement with points used to build the mapping.
Four points can fit exactly, so zero residual does not establish accuracy.
Independent check error is a root-mean-square world projection error for held-out
measured points. It evaluates those locations, not the entire road or vehicle
speed accuracy. Check error above 0.25 m produces a warning.

Validation rejects duplicate or nearly collinear references, nonfinite values,
negligible coverage, unstable mappings and a projective horizon in the region.
Coverage below 0.5% of the image is rejected; below 10% generates a warning.
The normalized geometry/transform condition diagnostic warns above 1,000 and
rejects above 1,000,000. These engineering thresholds are not accuracy bounds.

## Draw measurement gates

With the profile active and a compatible frozen frame visible, select **Draw
Gate A**, then click its two endpoints across the measured road. Repeat with
**Draw Gate B** farther along the intended travel direction. Drag endpoints or
edit their source-pixel coordinates, then choose **Save gates**. Both finite
segments must remain in the calibrated region and must not touch or intersect.
The arrow indicates A to B; **Also accept B to A** enables reverse traversal. **Reset gates** removes the saved configuration.

Resume observation and wait for a consistently tracked vehicle to cross both
segments. If a recorded clip ended during setup, start it again and explicitly
apply the saved profile, including its gates. The dashboard shows completed
measurements and rejection reasons; overlay toggles control clutter. Changing
the applied profile or gate configuration starts a fresh measurement history.

For each observed box, the engine projects its bottom-center as an approximation
of tire-to-road contact. It intersects consecutive world positions with each
gate and interpolates both crossing position and source timestamp. The estimate
is `distance_m / elapsed_seconds * 3.6`, rounded to one decimal km/h. Distance is
the straight-line displacement between crossing positions, not traveled path
length; curved roads can therefore be underestimated. Repeated touches do not
emit duplicate measurements. A point exactly on a gate waits for an observation
on the opposite side before the crossing is confirmed.

## Timing and measurement quality

Recorded videos use increasing presentation timestamps, `PTS * time_base`.
Missing or reversed timestamps switch decoding to a diagnostic nominal timeline;
that fallback cannot produce speeds. Cameras timestamp acquisition immediately
after `read()` using a monotonic clock. Driver buffering and exposure delay remain
unknown. Inference latency, browser polling and rendered FPS never supply the
measurement interval. Dropped live frames retain their own acquisition times.

Default `SpeedOptions` rules require at least three chronological observations.
Sampling gaps above **0.25 s** mark a result approximate; gaps above **1 s** break
continuity and reject an active measurement. The **250 km/h** displacement guard
rejects implausible jumps or speeds; it is configurable in code and is not a road
limit. Crossing both gates within one observation interval is rejected.

- **Valid:** observable timing, geometry and continuity checks passed. General
  cautions about stationary cameras or missing independent validation still
  apply; this label does not certify accuracy.
- **Approximate:** a numerical estimate exists with observed concerns, such as
  coarse sampling, repeated observations on a gate or poor calibration geometry.
- **Rejected:** no speed is reported because an essential requirement failed,
  including lost tracks, invalid positions/timing, unsupported direction or an
  incomplete traversal. Read the associated reasons.

Pause rejects unfinished traversals and clears pending crossing pairs for both
video and camera sources. Resume requires fresh consecutive observations;
paused wall-clock time cannot enter an estimate. Completed results remain visible
after pause/stop. New observations and reset clear session state. Invalidation
keeps historical results with their calibration identifiers but removes current
world projections and speed labels. History retains the most recent 1,000 results.

## Reproduce the synthetic validation

From the repository root in PowerShell:

```powershell
.\.venv\Scripts\python.exe scripts\validate_speed.py
```

The deterministic fixture is
[`backend/tests/fixtures/synthetic_trajectory.json`](../backend/tests/fixtures/synthetic_trajectory.json).
It supplies known image/world correspondences, gates and 0.24 s source samples.
Interpolated crossings occur at 0.3 s and 1.5 s, with 20 m displacement:
`20 / 1.2 * 3.6 = 60.0 km/h`. The script asserts the expected values and prints
the actual measurement. This verifies synthetic geometry and timing only; it
does not validate a physical camera, road measurements or detection accuracy.

Raw positions and timestamps are retained for inspection without smoothing.
Boundary-clipped boxes, occlusions and out-of-region projections cannot support
an active traversal. Lens distortion, road grade, imperfect reference measurements,
bounding-box jitter and temporary-ID switches remain material error sources.
Compare real recordings against independently measured positions and reference
speeds before drawing accuracy conclusions. Slow CPU inference may produce
approximate or rejected measurements; reduce detector input size if appropriate.

## Local API

Phase 3 adds [observable quality evidence](measurement_quality.md) and on-demand
measurement CSV/JSON exports at `/api/exports/measurements`. Full samples and
original calibration geometry are retained with each result; polling history
contains the smaller aggregate record. See [reference validation](../examples/validation/README.md)
and the [field protocol](real_world_validation.md) for independent comparisons.

See [interactive API documentation](http://127.0.0.1:8000/docs) for profile CRUD
and validation (`/api/calibrations`), freezing/invalidation (`/api/calibration`),
explicit profile activation, gates (`/api/gates`) and history (`/api/measurements`).
