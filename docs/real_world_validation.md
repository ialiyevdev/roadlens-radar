# Field validation from an elevated window

**No real-world reference data available** describes the bundled project evidence.
The supplied tests, field example and benchmark videos are synthetic. No physical
webcam, roadway recording or independent reference-speed device was used to
establish field accuracy. Phase 4 provides the workflow for collecting that
evidence. A software `valid` status means consistency checks passed; it does not
certify that a speed is accurate.

The [field-session guide](field_sessions.md) documents exact schemas, routes,
synchronization and exports. Existing Phase 3 datasets remain supported in
**Validation & Benchmarks**.

## 1. Plan a safe elevated-camera observation

Work from a permitted indoor position. Use a firm mount on a stable surface,
secure the camera and cable, and keep equipment inside the window. Do not lean
outside, place equipment where it could fall, obstruct an exit or interact with
moving traffic. Record lawfully, minimize unnecessary views into homes and retain
only footage needed for the study. No plates, faces or owners are recognized.

Choose a mostly straight, planar road section with visible ground before Gate A
and after Gate B. An elevated view can reduce overlap but does not establish
measurement scale or guarantee visibility. Window glass can add reflections,
double images and optical errors. Reduce indoor reflections, avoid vibration and
document whether filming through glass; retain the same arrangement between runs.

Fix camera position, resolution, zoom and focus where possible. Assign a camera
configuration identifier and record lens, mount, glass, exposure/focus settings
where known, crop, rotation, mirroring and processing settings. A moved camera or
changed resolution, zoom, crop or lens arrangement needs a new configuration and
compatible calibration.

Before inspecting errors, decide collection periods, lanes/directions, reference
method, inclusion/exclusion rules and dataset partitions. Keep complete recording
sessions or collection conditions together. Randomly splitting adjacent frames
does not establish independent held-out evidence.

## 2. Establish safely measured road references

Use identifiable road-plane points with X/Y positions measured in metres or
obtained from documented survey information. Do not enter traffic to obtain
references. If the required geometry cannot be obtained safely from a permitted
location, use a suitable controlled site or postpone collection.

Spread fitting references across both sides and near/far ends of the usable
region. Reserve additional measured points as **Check** points, excluded from the
homography fit. Retain method, date, units and limitations. Guessed lane widths,
vehicle lengths and camera height do not establish scale.

Road slope, changing grade, camber and curved paths can violate the planar
straight-displacement model. Select a suitable segment and record limitations
instead of applying an arbitrary correction multiplier.

## 3. Choose the camera coordinate system

Lens calibration is optional; source-pixel road calibration remains supported.
If distortion appears relevant, follow [Optional camera intrinsics](camera_intrinsics.md):
collect sharp, diverse checkerboard images at the intended resolution/lens/zoom,
fit a profile, inspect diagnostics and compare original/corrected previews.

| Task | What it establishes |
| --- | --- |
| Camera intrinsics | A lens/camera model and checkerboard reprojection diagnostics. |
| Road-plane homography | A mapping from compatible image pixels to measured road-plane metres, with independent check errors. |
| Independent speed validation | Comparison of vehicle events with separately established reference observations. |

A small checkerboard residual proves neither the road model nor speed accuracy.
Undistortion does not necessarily improve the final result; compare it on the same
footage/references with separate compatible road calibrations.

Correction, when enabled, happens before detection. Boxes, contacts, trajectories,
gates, homography and overlays share the corrected pixel space. Image dimensions
stay unchanged; browser display pixels and road-plane metres remain separate.
Applying/disabling correction invalidates active road calibration. Never copy old
source-pixel points or gates onto the corrected image.

## 4. Calibrate the roadway and place gates

1. Start the selected source in **Camera & video**, wait for a frame and pause.
   Select the optional intrinsic profile before defining road references.
2. In **Calibration & gates**, freeze a fresh frame in that coordinate space.
   Enter measured fitting references and reserved **Check** points.
3. Validate and inspect grid alignment, coverage, residuals and independent check
   errors near both gates. A zero four-point fit residual is expected and supplies
   no independent accuracy evidence.
4. Save and explicitly apply the matching stationary-camera road profile.
5. Place finite Gate A/B inside the measured region, separated along travel, with
   visible ground contact around each. Avoid persistent occlusion/image clipping.
   Both gates in one retained observation interval cannot support normal crossing
   interpolation.
6. Record endpoints and direction settings. A moved gate or camera starts a new
   documented comparison configuration.

The [calibration guide](calibration.md) explains the geometry checks. A vehicle
box bottom-centre approximates ground contact; it is not a surveyed tyre location.

## 5. Record and archive a field session

Save source footage locally using an appropriate recording method. RoadLens live
camera observation does not itself archive a webcam video; arrange a separately
saved recording for manual annotation/replay. Avoid a second camera client that
interferes with capture.

After processing an observation, open **Real-world validation** and choose
**Capture current observation**. It creates an isolated field record containing
original measurements, timing summary, camera configuration and saved calibration
evidence. Alternatively choose **New field session**, select **Registered local
video** or **Attach local video**, enter metadata and save. A manually created
metadata-only session has no speeds until populated from an actual processed
observation or an imported field export.

Use `recorded_unverified` for footage without established independent references.
Use `independent_reference` only for a documented independent method; that label
alone cannot make an event eligible. Record start/end times with a timezone,
lighting, weather, traffic density, reflections, occlusion and unusual events.

Retain valid, approximate and rejected results. Keep an external ledger of eligible
crossings with no application result and enter the expected-event total. Do not
fabricate application IDs/statuses for no-result crossings. Source links are
relative to the upload directory; field exports do not copy videos. Preserve
recording hashes and collection/near-duplicate groups.

## 6. Review vehicles and timing

In **Vehicle annotations**, navigate frames or actual source timestamps, draw/
adjust boxes and assign persistent manual labels such as `manual-vehicle-001`.
Keep manual labels separate from predicted tracker IDs. Mark entry, exit, partial
visibility and occlusion; mark every inspected frame reviewed, including empty
frames, and save incrementally.

Model proposals are separate overlays and do not establish truth identities or
reference speeds. Preserve both exports when comparing trackers. See
[Vehicle annotations](annotations.md) for JSON/CSV interchange, revision protection
and metric definitions.

Recorded footage uses presentation timestamps; live capture uses monotonic frame
acquisition time. Decode completion, inference completion and browser display are
later events on different clocks. PTS do not automatically identify exposure or
verified wall-clock time. Never calculate vehicle elapsed time from UI refreshes.

Review missing/duplicate/backward timestamps, timebase changes, source/processing
gaps, skipped frames, maximum observation gap and latency distribution. Source
timing flags exclude confirmed field comparisons without changing original
measurement statuses. Missing counters produce an explicit caveat. Nominal-FPS
fallbacks cannot establish a speed clock. Pausing must not add the browser pause
duration to physical travel time.

## 7. Establish independent reference observations

Use a separately derived speed with a documented instrument or distance/timing
method, configuration, checks, resolution, synchronization and known limitations.
An independently measured distance/transit time is useful only when its measurement
performance is established. Record shared clock/distance dependencies. Do not
invent uncertainty bounds when the method cannot support them.

An ordinary speedometer, GPS app, manual stopwatch or another unvalidated camera
is a candidate reference, not automatically precise ground truth. Manually timing
the same video shares its clock errors. RoadLens speeds and assumed traffic speeds
are not independent references.

Compare the same quantity: RoadLens reports straight-line displacement between
gate crossing positions divided by source elapsed time. An instantaneous reading
elsewhere may differ when a vehicle accelerates or follows a curved path. Document
mismatches and exclude events unsuitable for the intended comparison.

## 8. Synchronize clocks and match each vehicle

In **Reference alignment**, import device events using **Import reference CSV /
JSON**. Preserve native IDs, times, speeds, units, method, provenance and quality
notes. Units are `km/h`, `m/s` or `mph`. Import replaces that session's reference
ledger and clears earlier matching decisions.

Describe both clocks. Obtain harmless observable synchronization events or
suitable shared triggers from a safe position, near collection start/end. Never
ask drivers to make special manoeuvres. Retain original readings and documented
uncertainty. The model is:

```text
source_seconds = offset_seconds + scale * reference_seconds
```

A manual offset remains uncertain alone. Confirmed alignment requires at least two
independent anchors spanning time, clock descriptions and uncertainty within the
chosen analysis tolerance. Fit drift only when supported by independent anchors,
not to minimize speed errors. Inspect residuals/clock-scale warnings. Events
outside the anchor span stay excluded; a perfect two-anchor fit is not proof of
precise timing.

Review timeline, direction, lane, order and anonymous vehicle appearance before
selecting each reference. Enter a matching method and confirm correspondence only
with evidence. Save **Ambiguous** when several vehicles could correspond and
**Unmatched** when evidence is missing. No closest-event association happens
automatically. Never choose a reference because it gives the smallest speed error.

## 9. Evaluate held-out observations and investigate errors

Keep development, calibration/tuning and held-out sessions distinct. The software
conservatively blocks a source recording, collection ID or declared near-duplicate
group across partitions, including disjoint crops of one recording. It cannot
detect undeclared duplicates or prove held-out data was not used for tuning.
Preserve the original split plan and change history.

In **Evaluation & reports**, select sessions with the same provenance, keep the
held-out partition selected, choose a measurement variant and evaluate. Synthetic,
recorded-unverified and independent-reference evidence are evaluated separately.

Report N beside MAE, RMSE, mean signed error, median and P90 absolute error.
Signed error is **estimate minus reference**: positive bias means higher RoadLens
estimates. The default subgroup minimum of three is a software guard, not
statistical confidence. Percentage errors omit zero reference speeds; +/-3 and
+/-5 km/h tolerances are analysis settings, not guarantees.

Rates use the expected-event ledger only when every selected session supplies one;
otherwise retained application events are the denominator and crossing recall is
unknown. Detail/chart filters do not recompute overall cohort summaries.

| Contributor | Evidence to inspect |
| --- | --- |
| Lens distortion | Comparable source/corrected road calibrations, spatial error patterns and target coverage. |
| Homography/scale | Units, point correspondences, region coverage and independent near/far check errors. |
| Slope/non-planarity | Road-plane and straight-path assumptions; use a suitable segment. |
| Gate placement | Endpoints, crossing positions, samples near gates and interpolation intervals. |
| Contact/occlusion | Raw bottom-centres, clipping, box jitter, overlap and retained position history. |
| Identity continuity | Manual labels and predictions around missing/competing observations. |
| Source time | Raw PTS/acquisition gaps, fallback flags, drops and timebase changes. |
| Reference alignment | Anchors, uncertainty, drift, event identity and segment comparability. |
| Resolution/settings | Archived camera configuration, detector settings and geometry compatibility. |

Retain outliers unless a predefined documented exclusion applies. Justify changes
on development/calibration data, preserve original measurements, and assess them
on untouched held-out observations. Do not tune correction multipliers or gates
against held-out errors.

## 10. Preserve a reproducible study bundle

Export field-session JSON, annotation JSON/CSV and field report JSON/CSV/HTML.
Keep the original independent-reference file, split plan, camera notes and
appropriate local recording with them. Reports omit raw source pixels. Session
reimport does not transfer video; restore/upload the matching recording separately.
Deleting a field session removes its metadata/annotations, not its uploaded video.

The [synthetic field example](../examples/field/README.md) has four eligible
comparisons with errors +2, -1, +3 and -2 km/h: MAE 2.0, RMSE 2.1213, bias +0.5
and P90 absolute error 2.7 km/h. These known values check software arithmetic,
not observations from a window, moving road traffic or a reference device.
Actual field evidence remains to be collected.

## Reusable collection checklist

- [ ] Safe permitted indoor mount/cable, lawful recording and appropriate privacy/retention.
- [ ] Camera/lens/glass arrangement, resolution, zoom/focus and configuration recorded.
- [ ] Safely measured road references and independent check points retained with units/limitations.
- [ ] Optional intrinsic model, fresh road calibration and gates use one compatible pixel space.
- [ ] Source hash, recording, collection group, environment and partition recorded before evaluation.
- [ ] Original statuses, timing evidence and external no-result ledger retained.
- [ ] Manual vehicle labels reviewed separately from predicted IDs; annotations saved/exported.
- [ ] Independent reference method and comparable speed quantity established without self-reference.
- [ ] Independent synchronization anchors span collection; uncertainty, residuals and timebase flags reviewed.
- [ ] Explicit matches saved; ambiguous/unmatched events retained without selecting by error size.
- [ ] Held-out split preserved; bias/outliers investigated without arbitrary corrections.
- [ ] Session, annotation, reference and report exports retained together with remaining limitations.
