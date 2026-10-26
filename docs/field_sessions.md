# Field sessions and independent-reference evaluation

Open **Real-world validation** for the Phase 4 workflow. **Validation & Benchmarks**
continues to support the separate Phase 3 dataset/benchmark workflow. Field records
and offline evaluations do not activate a camera or change the live observation.

The interface displays **No real-world reference data available** until independent
reference events have been imported and successfully matched with eligible timing
and correspondence. Provenance and instrument independence are author declarations;
RoadLens cannot authenticate a reference device or certify its accuracy. Bundled
examples are synthetic. Actual roadway footage and independently established
reference observations remain to be collected.

## Create an observation record

1. Process a camera or uploaded video using the existing dashboard. If measuring
   speed, apply a compatible road calibration and gates first. Lens correction is
   optional; see [Camera intrinsics](camera_intrinsics.md).
2. After collecting the desired results, open **Real-world validation** and choose
   **Capture current observation**. It saves a separate field record containing
   the original results/statuses, source link, camera geometry, processing settings,
   timing summary and road/intrinsic calibration metadata. Capture is a snapshot;
   later live results do not append to it automatically.
3. Complete **Session details**: configuration/collection identifiers, timebase,
   start/end times, environmental notes, reference method, partition and provenance.
   Enter the external expected-event count only when a separate crossing ledger
   establishes it. Save changes.
4. Alternatively choose **New field session** and select **Registered local video**
   or **Attach local video**. Save before annotating or importing references.
   A manually created metadata-only record contains no speed estimates. Populate
   a measurement-bearing record through observation capture or a field JSON import;
   do not manufacture estimates for missed crossings.

The upload catalog persists metadata and hashes, rediscovers existing uploads and
reuses the same registered source for identical content. Uploaded files are not
copied into field-session folders. `source.relative_path` is relative to the upload
directory: normally an opaque filename such as `a1b2c3.mp4`, **not**
`uploads/a1b2c3.mp4`. Absolute paths and parent traversal are rejected. A session
without a local recorded source can retain measurements but cannot navigate
annotation frames. Live observation does not automatically record a webcam video.

Deleting a field session also removes its local annotations and saved reference
decisions. Its uploaded video remains registered. Changing source, geometry,
intrinsic model, lens or zoom invalidates archived calibration/gates, adds a warning
and excludes that changed configuration from comparisons. Original measurement
IDs, statuses, reasons and evidence remain intact; make a new session/configuration
for a new capture arrangement. Runtime road calibration retains its existing
invalidation rules independently.

## Stored schema

Default storage is `data/field_sessions/{uuid}.json`. Writes are atomic. Source
videos stay in `data/uploads/`; the catalog is `data/uploads/.catalog.json`.
Annotations and camera profiles have their own stores. The complete contracts are
in [field_models.py](../backend/roadlens/field_models.py).

| Field | Meaning |
| --- | --- |
| `id`, `created_at`, `updated_at` | Server-assigned identity and UTC save timestamps. |
| `name`, `description`, `status` | Study description and `draft`, `collecting`, `ready` or `evaluated` bookkeeping. Status alone does not establish eligibility. |
| `source` | Stable source ID, optional video ID/relative path, recording SHA-256, segment bounds, collection ID and near-duplicate group. Both segment endpoints are required together. |
| `camera` | Configuration ID, image geometry, applied intrinsic-profile ID, lens/zoom notes, detector input/confidence and tracker. |
| `calibration_id`, `gates`, `calibration_metadata` | Road profile, finite gate coordinates and archived road/intrinsic profile evidence, including fitting references and independent check diagnostics where available. |
| `calibration_compatible`, `configuration_warnings` | Configuration-change guards; they do not rewrite original measurement results. |
| `started_at`, `ended_at` | Observation wall-clock metadata with an explicit timezone. End cannot precede start. |
| `source_timebase`, `timing_summary` | Clock description and available source/processing integrity counters and latency evidence. |
| `environment_notes`, `environment_condition` | Observed conditions, recorded rather than inferred. |
| `reference_description`, `validation_dataset_id` | Documented reference method and optional associated dataset identifier. |
| `provenance`, `partition` | Evidence category and development/calibration/held-out designation. |
| `measurements` | `{event_id, variant, measurement}` wrappers around original Phase 3 measurement results. Variants are `original`, `baseline`, `improved`. |
| `reference_events`, `sync`, `matches` | Independent event ledger, clock configuration and explicit correspondence decisions. |
| `expected_event_count` | External crossing-ledger total, at least the number of retained vehicle events. Missing means total crossing recall is unknown. |
| `sync_diagnostics` | Derived offset/scale, drift, anchor residuals, declared bound, warnings and alignment state. |

Image geometry declares `coordinate_space=source` or `undistorted`; undistorted
geometry requires the exact intrinsic profile ID, matching `camera.intrinsic_profile_id`.
Rendered preview coordinates and road-plane metres are separate. Camera profile
selection does not automatically transform existing points or measurements.

Measurements have unique IDs; `(event_id, variant)` is unique within a session.
An event ID denotes one anonymous crossing, independent of a predicted track ID.
One event can retain baseline/improved results for comparison without replacing
its original. This schema stores the original polling result and observable
diagnostics. Export detailed position-sample history from the existing measurement
history when that additional evidence is needed.

## Annotate recorded vehicles

Open **Vehicle annotations** for the saved field session. Navigate 1-based frame
ordinals or actual source timestamps, draw/adjust boxes and assign persistent
manual identities. Mark occlusion, partial visibility, entry/exit and reviewed
frames; save incrementally. Human labels and predicted tracker IDs remain separate.

Import/export JSON for complete annotation interchange or CSV for analysis. An
annotation import must match field-session ID, source, geometry and current
revision. Field-session import creates a new UUID; it does not silently reassign
an old annotation document. See [Vehicle annotations](annotations.md) for the
document schema, deliberate transfer procedure, keyboard controls and metrics.

Proposals do not create manual truth or reference speeds. Preserve exports from
both tracker runs and score the same reviewed frames/coordinate geometry. Available
counts are identity switches, fragments, misses, false positives and matched
observations under the documented matching rule; IDF1 is not implemented.

## Import reference events

Use **Reference alignment -> Import reference CSV / JSON**. Import replaces the
reference ledger and clears previous matching decisions, preventing reassignment
to a replacement device ledger without review. The original measurement results
remain unchanged. UTF-8 JSON/CSV imports are capped at 8 MiB and 10,000 events.

The required CSV columns are:

```csv
id,timestamp_s,speed,units,method,provenance,independent
```

Optional columns are `interval_end_s`, `instrument_id`, `uncertainty_kmh` and
`quality_notes`. Headers/IDs must be unique and booleans are `true`/`false`
(`1`/`0` are also accepted). Blank optional values mean unavailable. JSON accepts
an event list or `{"reference_events": [...]}`. For example, this is a **schema
illustration**, not supplied field evidence:

```json
[
  {
    "id": "device-event-001",
    "timestamp_s": 103.25,
    "interval_end_s": 104.0,
    "speed": 13.8889,
    "units": "m/s",
    "method": "Replace with the documented independent measurement method",
    "provenance": "recorded_unverified",
    "independent": false,
    "instrument_id": null,
    "uncertainty_kmh": null,
    "quality_notes": "Reference performance and timing have not been established."
  }
]
```

Supported units are exactly `km/h`, `m/s` and `mph`. Conversion uses 3.6 km/h per
m/s and 1.609344 km/h per mph. Finite nonnegative speeds are required. A reference
interval ends after its timestamp; a missing interval end represents a point event.
Native timestamps remain in the reference clock's seconds until alignment.

Reference provenance is `synthetic`, `recorded_unverified` or `independent_reference`.
Unverified/non-independent records are retained but excluded from confirmed numeric
comparisons. RoadLens-derived reference methods are rejected. Ordinary speedometers,
GPS apps and other unvalidated cameras do not establish reference precision by
themselves. Describe instrument checks, relevant dependencies and limitations.
An optional speed uncertainty is retained evidence; it does not create a calculated
confidence interval or automatically validate an instrument.

## Synchronize clocks

Describe source and reference clocks and add observed synchronization anchors.
Each anchor retains `reference_timestamp_s`, `source_timestamp_s`, an independence
declaration, uncertainty in source-equivalent seconds and a description. Source
time is PTS/acquisition time, never browser refresh or inference completion.
Video PTS are not independently verified wall-clock/exposure timestamps.

```text
source_seconds = offset_seconds + scale * reference_seconds
```

With **Fit drift from independent anchors** disabled, `scale=1` and the entered
manual offset is checked against anchors. With it enabled, least squares fits
offset and scale using at least two independent, distinct reference timestamps.
The fitted values replace the manual offset for alignment; residuals remain visible.
Do not use RoadLens speed agreement to construct synchronization anchors.

**Save synchronization** retains uncertain configurations for investigation.
Confirmed alignment requires at least two independent anchors spanning time, both
clock descriptions, and declared uncertainty within the analysis tolerance.
The conservative bound is entered offset uncertainty plus the largest anchor
uncertainty plus the largest absolute fitting residual. Missing uncertainty stays
unknown. This is a declared bound, not a statistical confidence interval.

The default maximum alignment error is 0.25 s, an analysis setting. A scale change
above 1,000 ppm triggers investigation and prevents confirmed alignment. Events
outside the source-time anchor span are excluded. Do not increase tolerance merely
to force inclusion. A single uncertain offset or perfect two-anchor fit does not
establish precise timing.

## Save explicit event correspondence

The timeline maps reference times into source seconds. For each retained vehicle
event, explicitly choose a reference ID and `matched`, `ambiguous` or `unmatched`.
Record the matching method/quality notes and check **Vehicle correspondence
confirmed** only with supporting direction, lane, order and visual evidence.
Choose **Save matching decisions**. No reference is selected automatically by time
or speed error. A reference cannot be assigned to several matched vehicle events.

An eligible comparison needs a supported independent reference, matching session/
reference provenance, confirmed correspondence, aligned clocks, source timing
without integrity flags, compatible archived camera geometry and a non-rejected
numeric estimate. Reference/source event intervals must be within the analysis
tolerance and the vehicle interval inside the synchronization-anchor span. Ambiguous,
unmatched, rejected, missing and time-mismatched events remain in reports with
reasons. Negative aligned times are retained as diagnostic evidence and excluded.

Source `missing_timestamp`, `duplicate_timestamp`, `backward_timestamp`,
`timebase_changed` or `flagged_frames` counters and nominal timing fallback exclude
confirmed comparisons. Missing counters add a caveat rather than invented failures.
Application `valid`/`approximate`/`rejected` statuses are preserved through import,
matching and evaluation.

## Keep held-out data separate

Partitions are `development`, `calibration` and `held_out`. Assign them before
inspecting evaluation errors. Prefer complete sessions or independent collection
conditions rather than adjacent frames. Matching source IDs/SHA-256 recordings,
collection IDs or declared near-duplicate groups cannot span partitions. The
guard deliberately also blocks disjoint segments of the same recording. Reimported
copies retain source grouping and cannot evade this guard merely by receiving a
new field-session UUID.

Record edited/re-encoded copies using the same near-duplicate/collection group;
different bytes alone do not make them independent. Metadata cannot discover all
undeclared duplicates or prove that held-out results were never used for tuning.
Keep the split plan and change history with the study.

## Evaluate and export

In **Evaluation & reports**, select sessions of one provenance, leave **Held-out
evaluation** selected for the primary study, select a variant and choose
**Evaluate field sessions**. Other partitions support descriptive investigations.
Mixed synthetic/unverified/independent evidence is not pooled.

Reports calculate MAE, RMSE, mean signed error (estimate minus reference), median
and P90 absolute error, applicable percentage errors, tolerance counts and sample
sizes. P90 uses linear interpolation at `(n-1)*0.90`; percentage errors omit zero
reference speeds. Group metrics require at least three eligible comparisons by
default; the minimum is configurable and does not establish statistical confidence.
Groups cover session, camera configuration, calibration, direction, speed interval,
environment, tracker and status when enough comparisons exist.

Valid/rejection/non-completion rates use the expected-event ledger only when
every selected session supplies a total. Otherwise they use retained events and
cannot establish all-vehicle recall. Non-completion includes any event without a
non-rejected numeric result, including rejected attempts. Reports show missing
application events, unmatched references and per-reason exclusions. Baseline/
improved metrics pair only explicitly retained results for the same event/reference;
they never overwrite originals or apply correction multipliers.

Status/direction/session/search/speed filters change charts and detail rows. Overall
summary statistics continue to describe the evaluated cohort. Change the evaluated
session/partition/variant selection to produce a different report. Export regenerates
from the saved sessions; reevaluate after changing metadata or reference decisions.

Use **Export field report JSON / CSV / HTML**. JSON preserves structure and original
measurement evidence; CSV includes a summary metadata row and measurement rows;
HTML is escaped, scriptless and self-contained. Reports include calibration
methodology, timing, provenance, partitions, exclusions, limitations and reproduction
settings. They omit source paths and pixels. **Export field session JSON** retains
its relative source link, original references, anchors and matching decisions for
reimport. Preserve that input snapshot and annotations beside each report. Restore
the matching video separately when moving the study.

## Reproduce the synthetic exercise

Choose **Load synthetic field example**, save it, then evaluate its held-out
original measurements. Or import `examples/field/synthetic_field_session.json`.
The separate synthetic reference CSV/JSON can exercise import, which clears the
example's matching decisions; review/resave them before evaluating again.

```powershell
.\.venv\Scripts\python.exe scripts\validate_field.py --output data\field-validation
.\.venv\Scripts\python.exe scripts\profile_field.py --iterations 30 --output data\phase4-field-performance.json
```

The original example has six retained vehicle events and an eight-event external
ledger: three valid, one approximate, two rejected. Four comparisons are eligible:
MAE **2.0 km/h**, RMSE **2.1213**, mean signed error **+0.5**, median AE **2.0**,
P90 AE **2.7**. Ledger rates are **37.5% valid**, **25% rejected**, **50%
non-completed**. Four explicitly paired synthetic baseline/improved events have
MAE **2.5 -> 2.0 km/h**. These are deliberately generated arithmetic inputs, not
evidence that a physical pipeline became more accurate.

The [measured software-cost report](benchmarks/phase4-field-performance.json)
separately times matching, evaluation, report generation, timestamp diagnostics
and navigation of generated FFV1 frames. It records hardware, versions, repetitions
and limits; it excludes live capture, ML inference, HTTP and browser rendering.
See [examples/field](../examples/field/README.md) and the practical
[elevated-camera field procedure](real_world_validation.md).

## API map

All routes use the local application's normal host/origin checks.

| Route | Operation |
| --- | --- |
| `GET /api/field-sources` | Registered uploaded video metadata. |
| `GET/POST /api/field-sessions` | List/create sessions. |
| `GET /api/field-sessions/example` | Unsaved synthetic example input. |
| `POST /api/field-sessions/from-observation` | Snapshot the current observation with supplied study metadata. |
| `POST /api/field-sessions/import` | Multipart JSON field-session import; assigns a new UUID. |
| `GET/PUT/DELETE /api/field-sessions/{id}` | Read/update/delete a local session. |
| `GET /api/field-sessions/{id}/export` | Complete session JSON. |
| `POST /api/field-sessions/{id}/references/import` | Multipart reference CSV/JSON import. |
| `PUT /api/field-sessions/{id}/sync` | Save synchronization configuration. |
| `PUT /api/field-sessions/{id}/matches` | Save `{matches: [...]}` explicit decisions. |
| `GET /api/field-sessions/{id}/eligibility` | Per-event exclusions, counts and synchronization diagnostics. |
| `POST /api/field-evaluation` | Evaluate selected session IDs; held-out/original defaults. |
| `POST /api/field-evaluation/export?format=json\|csv\|html` | Regenerate/download a report. |

Evaluation input is `{session_ids, partition, variant, options, description}`.
`partition: null` requests all selected partitions for descriptive analysis.
`options` uses the Phase 3 `minimum_group_samples` and `tolerance_bands_kmh` fields.
Camera and annotation routes are documented in their linked guides.
