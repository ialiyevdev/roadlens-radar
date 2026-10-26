# Field-session interchange

All bundled files are **synthetic**, including camera configuration, references,
clock anchors and measurements. No physical camera, road or reference instrument
was observed. Do not relabel these files as real evidence.

`synthetic_field_session.json` is a complete importable field session. It contains
six original vehicle events (three valid, one approximate and two rejected),
explicit decisions for seven reference events, a separately declared eight-event
ledger, and four baseline/improved pairs. The references also appear as CSV and
JSON imports. Importing references replaces that session's reference ledger and
clears matching decisions; review and save those decisions again.

The schema is `backend/roadlens/field_models.py`. A field session contains:

- `source`: stable anonymous `source_id`, optional uploaded `video_id` and safe
  `relative_path`, recording SHA-256, segment endpoints, collection and near-duplicate
  group. Paths cannot be absolute or traverse parent directories. Videos are
  referenced, never copied into session exports.
- `camera`, `calibration_id`, `gates`: resolution/configuration and intrinsic profile,
  road-plane calibration and finite gate coordinates. Wall-clock metadata must
  include its timezone; it does not establish verified acquisition timing.
- `partition`: `development`, `calibration` or `held_out`. Entire source recordings,
  collection IDs and declared near-duplicate groups stay in one partition. This
  intentionally also blocks nonoverlapping crops of the same recording.
- `provenance`: `synthetic`, `recorded_unverified` or `independent_reference`.
  Independence is an author's documented declaration, not certification.
- `measurements`: `{event_id, variant, measurement}`. Variant is `original`,
  `baseline` or `improved`; `measurement` preserves the original Phase 3 result,
  status, reasons and diagnostic quantities. Event labels identify anonymous
  crossings and are separate from predicted track IDs. No-result crossings belong
  in the external expected-event ledger, rather than fabricated application IDs.
- `reference_events`: `id,timestamp_s,interval_end_s?,speed,units,method,provenance,
  independent,instrument_id?,uncertainty_kmh?,quality_notes`. Units are exactly
  `km/h`, `m/s` or `mph` (1 mph = 1.609344 km/h). Reference clocks may have their
  own finite origin. RoadLens-derived references are rejected.
- `sync`: source/reference clock descriptions, manual `offset_s`, optional
  `fit_drift`, independent synchronization anchors and documented uncertainty.
  The model is **source seconds = offset + scale × reference seconds**. Drift fitting
  requires at least two independent, distinct anchors. Confirmed alignment requires
  two anchors spanning time, declared uncertainty within the analysis tolerance,
  and no suspicious clock-scale change. Events outside the anchor span remain
  excluded. Residuals and declared bounds are not confidence intervals.
- `matches`: one decision per `event_id`, with an explicit `reference_id`,
  `association` (`matched`, `ambiguous`, `unmatched`), method, notes and
  `correspondence_confirmed`. Reference IDs cannot be assigned to multiple vehicle
  events. There is no nearest-event automatic matching.

Reference CSV requires `id,timestamp_s,speed,units,method,provenance,independent`;
all other reference fields are optional. Use UTF-8, one event per row, unique
headers and `true`/`false` for independence. JSON accepts a reference list or
`{"reference_events": [...]}`. Imports are capped at 8 MiB/10,000 records.

Run the unchanged fixture through the actual evaluator and report renderers:

```powershell
.\.venv\Scripts\python.exe scripts\validate_field.py --output data\field-validation
```

Four original comparisons are eligible. Their signed errors are +2, -1, +3 and
-2 km/h: MAE 2.0, RMSE √4.5, bias +0.5, median absolute error 2.0 and P90 absolute
error 2.7 km/h. These are arithmetic checks, not empirical accuracy results.
Reports keep rejected and ambiguous events and original statuses. Aggregate and
subgroup errors require at least three eligible comparisons; that threshold
does not establish statistical confidence. Default evaluation selects held-out
sessions. Synthetic, unverified and independent evidence are evaluated separately.

JSON preserves report structure, CSV includes a metadata/summary row plus each
measurement, and standalone HTML escapes all supplied text and runs no scripts.
Reports omit source paths and pixels. Session export retains its relative source
link for local reimport; move/upload recordings separately when required.
