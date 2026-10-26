# v1.0.0 final publication verification

Verified locally on **26 October 2026 (Europe/Riga)**. RoadLens Radar v1.0.0 is
**ready for publication**. No commits, pushes, tags, GitHub repository, release
or external deployment were created. The remaining actions are the user's
publication review and GitHub setup, documented in [the publication guide](github_publication.md).

| Check | Actual final result |
| --- | --- |
| Full backend regression | **647 passed**, one upstream deprecation warning; 35.69 s |
| Full frontend regression | **151 passed** across 24 files; 24.12 s |
| Frontend dependency installation | Fresh `npm ci` succeeded without lockfile changes |
| TypeScript and normal production build | Passed; 77 modules; `frontend/dist` |
| TypeScript and Pages project build | Passed; 40 modules; `frontend/dist-showcase`, base `/roadlens-radar/` |
| Static artifact check | 23 files, 12 resolved asset references, three verified PNGs and nine notice files |
| Actions workflow validation | actionlint 1.7.12 passed; official action references pinned to verified upstream commits |
| Dependency checks | `pip check` clean; Python runtime/dev/build advisory audit: 28 packages, no known vulnerabilities; npm audit: zero vulnerabilities |
| Publication source review | Source/link/version scan passed; no tracked/staged files or remote; local snapshot trees inspected |

The eleven new Pages tests check both asset bases, paths containing spaces,
reviewed-image integrity, download/notice availability, unexpected private files,
backend access, hard links and workflow boundaries. The existing Windows source
copy test also verifies that `.github/workflows` survives isolated copying.
The normal application UI and measurement pipeline were unchanged.

The [final Chromium record](verification/v1-publication-browser.json) covers the
actual project build served under `/roadlens-radar/`, with the Python API and
full-app dev server stopped. All ten tour steps passed at **390, 768 and 1440 px**
(30 layout checks), with no page overflow or uncaught errors. Keyboard focus,
Previous/Next, native chart interaction, direct hash entry and actual page reload
passed. All **six downloads completed in Chromium and parsed as JSON**. All three
packaged screenshots decoded and matched manifest hashes; all nine notice URLs
responded. There were **zero backend requests, external requests or failed HTTP
responses**. The static artifact uses the same stored examples as before.

The artifact was built and served locally on Windows; the GitHub-hosted Ubuntu
workflow and live Pages URL have **not** been executed or verified. The workflow
has no Python install, model download or backend startup step. Its deployment job
is the only job granted Pages write/OIDC permissions; upload is limited to the
verified static output directory.

Historical Phase 6 isolated-install and benchmark evidence is retained below;
this final task does not claim another external clean-machine or field study.
Independent roadway speed/counting accuracy, physical camera behavior and an
independent reference-speed device remain unverified. No further product phase
is required to publish v1.0.0.

# Phase 6 release verification

Completed on **25 October 2026 (Europe/Riga)** on this Windows 11 computer using
Python 3.13.9, Node 24.16.0, npm 11.16.0, OpenCV 4.14.0 and PyAV 16.1.0.
These checks establish local software behavior, not physical roadway accuracy.

| Check | Actual result |
| --- | --- |
| Full backend suite | **636 passed** in 23.18 s; one existing Starlette/HTTPX deprecation warning |
| Full frontend suite | **151 passed** across 24 files; 24.86 s; HTTP mocked in JSDOM |
| TypeScript and normal production build | Passed; 77 modules; application output remains `frontend/dist` |
| TypeScript and static showcase build | Passed; 40 modules; separate `frontend/dist-showcase`, relative asset base |
| Python dependencies | `pip check`: no broken requirements; existing runtime/dev lock retained |
| Security checks | `npm audit`: zero vulnerabilities; pip-audit 2.9.0 against runtime/dev and build locks: 28 packages, no known vulnerabilities after the build-helper fix |
| Portable release source check | Local Markdown file links, version agreement and redacted sensitive-pattern scan passed |
| Demo manifest | Fifteen existing assets with byte hashes, source/license/redistribution and ground-truth status; four tests passed |
| Windows scripts | Seven PowerShell scripts parsed; setup prerequisite checks and three copy/path/privacy tests passed |
| Source-only installation | Fresh local copy with spaces, isolated Python/npm installs, new verified model download, actual API/model smoke and both production builds passed |

The expanded audit identified two advisories in the initial setuptools 80.9.0
build-helper selection. The final pin is 84.1.0 in both build manifests; editable
installation, dependency consistency, advisory scanning and a fresh complete
isolated smoke were repeated successfully. [Dependency audit scope](verification/phase6-dependencies.json).

Phase 6 adds **12 backend** tests (manifest, release/API and Windows copying) and
**10 frontend** tests (tour, source data, shared charts/table, keyboard behavior,
static rendering and dashboard entry). Earlier behavior assertions are preserved;
the intentional phase-label assertion now expects Phase 06. The original
60.0 km/h source-time fixture and actual downloaded-model tests remain in the
full backend run. Python support was corrected to 3.12–3.13 because the unchanged
NumPy 2.5.4 pin requires 3.12+. Only 3.13.9 was executed here.

## Chromium and API checks

The [browser record](verification/phase6-browser.json) covers all ten steps in
both the normal app and static build at **390, 768 and 1440 px**: **60 layout
checks**, no document overflow and no uncaught page errors. Four keyboard cases
(Home/End/left/right) passed in each build, including heading focus; Previous/Next
also passed. Four actual workspace links opened the corresponding views.
All six evidence downloads parsed in both builds (**12 checks**). Static rendering
made **zero API requests**. No camera scan or access was requested.

Actual video upload/start/pause through the normal UI exercised YOLOX-S INT8 on
a generated FFV1 replay of the attributed CC0 still: four source frames, five
tracks and **zero speed measurements without calibration**. This is actual model
execution on repeated static pixels, not recorded moving-road validation or a
new timing benchmark. The API used separate ignored QA storage.

The final static output was additionally served under **`/roadlens-radar/`** with
the Python API and full-app dev server stopped. A further **30 layout checks**,
six evidence downloads and the interactive count/rate chart toggle passed with
zero API requests or uncaught errors. The [subdirectory record](verification/phase6-static-subpath.json)
captures this separate check. It verifies the relative-base build; no hosting
resource or external deployment was created.

Actual new screenshots: [guided showcase](screenshots/phase6-showcase.png),
[mobile showcase](screenshots/phase6-showcase-mobile.png), and
[actual-model still-replay dashboard](screenshots/phase6-dashboard.png).
Historical feature screenshots below retain their original phase/version labels.

The [isolated installation record](reproducibility.md) explains what was installed,
what remained shared with the host, the initial OneDrive copy failure and its fix.
An external clean Windows machine, physical camera, independent reference-speed
device and representative held-out roadway recordings were **not** tested.

# Phase 5 verification

Final verification completed on **25 October 2026**, Windows 11, Python 3.13.9,
Node.js 24.16.0, npm 11.16.0, OpenCV 4.14.0 and PyAV 16.1.0. No runtime
dependency was added, and earlier successful assertions remain unchanged.

| Check | Actual result |
| --- | --- |
| Full backend suite | **624 passed**; one upstream Starlette/HTTPX deprecation warning |
| Full frontend suite | **141 passed** across 22 files; mocked HTTP/JSDOM |
| Production build | TypeScript and Vite passed; 57 modules |
| Python dependency consistency | `pip check`: no broken requirements |
| npm audit | Zero reported vulnerabilities at verification time |
| Counting benchmark | **14/14 scenarios**, 107 frames, **17/17 crossings**, one expected duplicate suppression |
| Actual-model CPU profile | Twelve measured CC0 still frames, five detections/tracks each; zero expected moving crossings |
| Local API + Chromium | Source upload/pause/resume, line/polygon drawing and numeric edits, counting, autoarchive, filters, annotations/evaluation, charts, session comparisons and all 14 table/format downloads passed |
| Responsive browser checks | Five Traffic Intelligence views × 390/768/1440 px; all 15 had document width equal to viewport, with no uncaught page errors |
| Final-region deletion | Deleted the only zone and last line through the UI, saved an empty configuration and retained historical events |

Phase 5 adds **146 backend** and **36 frontend** tests. Engine cases cover finite
and bidirectional crossings, multiple lines, jitter, short loss, identity
fragmentation/suppression, uncertain classes, image/ground zones, overlap, observed
dwell/stationarity, invalid time, isolation, bounded state and NumPy serialization.
Untimed frames retain instantaneous image observables without creating timed
events, dwell or coverage.

Analytical/API tests cover exposure and incomplete intervals, active-line
coverage, lifetime versus retained counts, filters/dates, valid-only speed
statistics, CSV/JSON metadata, local persistence, comparison compatibility and
annotation evaluation. Ten worker integration cases exercise uncalibrated
counting, pauses, restart/configuration reuse, geometry retirement, ground
calibration, overlays, timestamp failures, unique speed linkage, archive failures
and the first-frame encoding race. The original 60.0 km/h source-time fixture and
downloaded-model smoke/replay tests remain in the full suite.

Frontend tests cover coordinate editing/deletion, ground projection, source/pixel
compatibility, dirty drafts, stale responses, charts/focus, KPIs, filters/dates,
pagination, missing calibration, hidden-view refresh, navigation, exports and
evaluation. JSDOM does not establish layout; Chromium verifies real rendering
and horizontal table scrollers.

The browser harness uses generated FFV1 frames, an explicit colored-marker
detector and the actual tracker/engine/application routes. Two opposing scripted
vehicles crossed at **4.833333 source seconds**, with no metric speeds without
calibration. Matching scripted Phase 4 annotations gave two matches, no misses,
duplicates or false positives, and 2/2 class/direction matches. These are synthetic
software results. Per-frame tracking proposals and independent speed evidence
were unavailable and reported accordingly. A separate six-event/four-speed
fixture exercised charts, comparisons and all seven CSV/JSON export tables.

Actual screenshots:

- [Counting line and zone editor](screenshots/phase5-counting-editor.png)
- [Generated-video observation](screenshots/phase5-observed-overview.png)
- [Traffic overview](screenshots/phase5-traffic-overview.png)
- [Charts](screenshots/phase5-traffic-charts.png)
- [Traffic events](screenshots/phase5-traffic-events.png)
- [Scripted annotation evaluation](screenshots/phase5-counting-evaluation.png)
- [Session comparison](screenshots/phase5-session-comparison.png)
- [Mobile traffic view](screenshots/phase5-traffic-mobile.png)

Portable reproduction uses `scripts/benchmark_traffic.py`, `scripts/profile_traffic.py`,
`scripts/profile_traffic_pipeline.py` and `examples/traffic/`. Browser scripts and
downloads remain ignored under `data/`. To repeat the generated marker exercise,
start this explicit harness in place of the regular API:

```powershell
.\.venv\Scripts\python.exe scripts\run_traffic_validation.py --port 8000
```

Upload `data\traffic_validation\SYNTHETIC_traffic_workflow.avi`. The normal
`roadlens.api:app` entry point uses the actual model. No physical camera,
moving-roadway truth or independent reference device was evaluated. See
[performance](performance.md), [the traffic guide](traffic_intelligence.md)
and [the file map](phase5_changes.md) for workloads and evidence limits.

## Previous Phase 4 verification

Verified on **24 October 2026**, Windows 11, Python 3.13.9, Node.js 24.16.0,
npm 11.16.0, OpenCV 4.14.0 and PyAV 16.1.0. No runtime dependency was added.

| Check | Actual result |
| --- | --- |
| Full backend suite | **478 passed**; one upstream Starlette/HTTPX deprecation warning |
| Full frontend suite | **105 passed** across 16 files; mocked HTTP/JSDOM |
| Production build | TypeScript and Vite passed; 50 modules |
| Python dependency consistency | `pip check`: no broken requirements |
| npm audit | Zero reported vulnerabilities at verification time |
| Original source-time speed fixture | **60.0 km/h**, unchanged; 20 m / 1.2 source seconds |
| Synthetic field example | Four eligible comparisons; MAE 2.0, RMSE 2.1213, bias +0.5, median AE 2.0, P90 AE 2.7 km/h |
| Scripted annotation predictions | Four matches, one miss, one false positive, one ID switch, one fragment |
| Actual local API + Chromium | Field creation/upload, manual box editing/review/occlusion, frame/PTS navigation, JSON/CSV interchange, bounded actual YOLOX proposals, lens import/apply/disable, corrected preview/freeze, references/sync/matching, held-out evaluation/filtering and JSON/CSV/HTML downloads passed |
| Browser layout | 390/768/1440 px; document width matched each viewport and no uncaught page errors |

Backend additions cover camera schema/geometry, real corner extraction from
rendered checkerboards and synthetic point fits, raw timestamp/time-base issues,
persisted field sessions/source catalog, source deduplication, annotation schema
and spreadsheet-safe lossless interchange, optimistic revisions, exact video
navigation, bounded caches, archived intrinsic parameters, explicit matching,
offset/drift/uncertainty, interval anchor boundaries, source binding, split leakage,
metrics, reports and preservation of original statuses. Worker integration cases
exercise model changes during inference, JPEG publication and frozen-frame encoding.
Old API assertions now account for the deliberately added catalog and stage fields.

Frontend additions cover field CRUD, calibration selection, upload reuse, dirty
metadata surviving delayed child saves, annotations and pending-save protection,
timestamp navigation, dirty export protection, reference import and matching,
alignment warnings, evaluation filters, reports, empty states and errors. JSDOM
does not establish layout; the separate real Chromium checks do.

The actual downloaded-model tests ran in the backend suite. The browser used the
normal local backend and generated eight-frame FFV1 clip with actual CPU inference
and model proposals; the shape clip is not a detection-accuracy dataset. The lens
profile, manual boxes, matching/reference speeds and anchors were explicitly
synthetic. Removing anchors withheld eligibility; restoring them returned four
eligible comparisons. Download contents, including ledger rate denominators,
were checked. The existing Phase 3 validation view was also evaluated in this run.
The historical full Phase 2 calibration browser exercise was not repeated;
its API, source-time worker, frontend and 60.0 km/h regressions passed.

Actual screenshots:

- [Field session](screenshots/phase4-field-sessions.png)
- [Manual annotation](screenshots/phase4-annotations.png)
- [Original/corrected camera pixels](screenshots/phase4-camera-intrinsics.png)
- [Reference synchronization](screenshots/phase4-reference-alignment.png)
- [Held-out synthetic evaluation](screenshots/phase4-field-evaluation.png)
- [Mobile evaluation](screenshots/phase4-field-mobile.png)

The local QA script/results remain ignored under `data/phase4-browser-qa.mjs` and
`data/browser-phase4/`. Synthetic fixtures, scripts and workflow documentation
are the portable reproduction inputs. See [field sessions](field_sessions.md),
[camera intrinsics](camera_intrinsics.md), [annotations](annotations.md) and
[component performance](performance.md). No physical camera, moving-roadway truth
or independent speed-reference device was tested. Software consistency and
arithmetic results do not establish roadway accuracy.

## Previous Phase 3 verification

Final Phase 3 verification on **23 October 2026**:

| Check | Actual result |
| --- | --- |
| Full backend suite | **284 passed**, one existing upstream Starlette/HTTPX warning |
| Full frontend suite | **53 passed** across ten files, mocked HTTP/JSDOM |
| Production build | TypeScript and Vite passed; 37 modules |
| Python dependency consistency | `pip check`: no broken requirements |
| npm audit | Zero reported vulnerabilities at verification time |
| Original source-time speed fixture | 20 m / 1.2 s × 3.6 = **60.0 km/h**, unchanged |
| Independent-reference synthetic example | 18 rows / 14 reference matches / 12 comparisons; MAE 2.8333, RMSE 3.2660, bias +1.3333 km/h |
| Inference-free tracking suite | 11 scenarios / 352 frames / 484 truth observations; baseline 5 switches, improved 1; both 3 fragments and 18 misses |
| Actual local API + Chromium | Imports, evaluation, charts, filtering, both report formats, both benchmark formats, invalid/empty datasets and retained navigation state passed |
| Browser widths | 390, 768 and 1440 px; document width matched viewport, no horizontal page overflow or uncaught page errors |

The actual downloaded-model tests and recorded CC0-still replay ran in the full
backend suite. No physical camera, moving labeled roadway footage or independent
real-world speed reference was used. Phase 3 did not rerun the historical full
Phase 2 calibration browser workflow; its API/worker/frontend regressions passed.

New backend tests cover exhaustive small assignment optima, competing vehicles,
source-time gaps/expiry, occlusion, ambiguity episodes, invalid observations,
benchmark metric definitions, import/matching/duplicate/nonfinite errors, metric
arithmetic, percentile/tolerance math, empty and insufficient groups, rejected
results and reference mismatches. They also check on-demand evidence exports,
earlier gate evidence surviving history eviction, source-clock independence,
typed benchmark exports and suppression of a numeric label on a currently
uncertain identity. Full evidence stays outside polling records.

New frontend tests cover validation import/selection/settings, eligible chart
data, metrics/groups, filters, downloads, empty/errors, persistent navigation,
observable evidence and nullable timing/track diagnostics. JSDOM does not verify
layout; the real browser checks above establish the reported widths. Vitest uses
two workers to limit contention with CPU inference during development.

Browser checks used the normal localhost FastAPI service and Vite frontend,
with no source started. The backend supplied the synthetic evaluation and ran
both trackers; downloaded JSON/CSV contents were checked. Screenshots are actual
captures, not mockups:

- [Validation overview and charts](screenshots/phase3-validation.png)
- [Tracking comparison and continuity](screenshots/phase3-tracking.png)
- [Mobile validation](screenshots/phase3-validation-mobile.png)

Run `scripts/benchmark_tracking.py`, `scripts/validate_dataset.py` and
`scripts/validate_speed.py` for the distinct synthetic checks. Their definitions
are in [tracking results](benchmarks/tracking.md),
[reference examples](../examples/validation/README.md) and
[quality rules](measurement_quality.md). Actual CPU/HTTP/storage profiling and
reproduction commands are in [performance notes](performance.md).

## Previous Phase 2 verification

Verified on Windows on **23 October 2026**, with Python 3.13.9, Node.js 24.16.0,
npm 11.16.0 and the dependencies recorded in `requirements-dev.lock` and
`frontend/package-lock.json`.

| Check | Observed result |
| --- | --- |
| `python -m pytest -q` | 137 passed; one upstream Starlette/HTTPX deprecation warning |
| `npm.cmd test` in `frontend` | 29 passed across six test files |
| `npm.cmd run build` | TypeScript checks and Vite production build passed |
| `python -m pip check` | No broken requirements |
| `npm.cmd audit` | Zero reported vulnerabilities at verification time |
| Live local API and frontend HTTP checks | Both returned HTTP 200 |
| Chromium browser workflow | Upload, freeze, measured-reference form, fit/check validation, save/apply, gate editing, 60.0 km/h synthetic result, stop/reset |
| Mobile browser layout | Calibration and dashboard at 390 pixels; no horizontal page overflow |

The upstream test-client warning does not affect the tested runtime routes. No
warning was suppressed. Future dependency updates may change this output.

## What the tests establish

Backend tests cover detector preprocessing, COCO class filtering, NMS, tracking
interruptions and expiration, bounded trajectory history, invalid timestamps,
Windows capture-backend fallback, camera release and failed release ownership,
video presentation timestamps and flagged fallbacks, pause/resume, full recorded
decoding, restart, upload validation, session controls and JPEG/MJPEG responses.
Local host/origin restrictions are exercised without opening a physical device.

Phase 2 adds known perspective mappings, degeneracy/horizon/conditioning checks,
independent check errors, source-geometry mismatch, robust fitting, finite gate
intersections, interpolated crossing times, exact gate touches, duplicate
suppression, direction, missing/reversed timestamps, coarse/dropped sampling,
lost IDs, partial boxes, implausible jumps, pause/reset and bounded histories.
Twenty HTTP/worker integration cases exercise real session/tracker behavior with
controlled frame/detector adapters, including profile persistence and invalidation.
They include a video frame held during an in-flight pause and rejection of live
packets acquired before resume.

Five optional tests use the **actual downloaded CPU model**: a blank image,
positive vehicle detection at 320/416/640, and a five-frame recorded replay of the
CC0 traffic photograph. These ran successfully in this checkout. They skip when
the model is not downloaded. The other tests use generated source frames and
injected camera/detector implementations, making them independent of hardware.

Frontend tests check real control behavior against mocked HTTP responses:
discovery is explicit, video selection is required, source settings reach the
API, errors are visible, nullable diagnostics render safely, and session controls
reflect running/paused/stopped states. These are complemented by the browser
workflow against the actual local FastAPI service.

New frontend cases exercise scaled/letterboxed source coordinates, measured
input and independent-check roles, reference/gate editing, incomplete numeric
drafts, unsaved-profile protection, validation errors, quality/history display
and JPEG/MJPEG transport selection. Common form setup uses change events; the
specific clearing/retyping behaviors use simulated user input.

The Phase 2 browser check uses `scripts/run_validation.py`, a labeled synthetic
recorded-video harness with a color-marker adapter. It exercises the existing
decoder, tracker, API, calibration interface and speed engine. Clicks were checked
against source pixels, then refined numerically; fitted reference/check points
and gate endpoints were entered through the UI. The result uses source crossing
times **15.3 s and 16.5 s**, displacement **20 m**, elapsed **1.2 s**, and estimated
speed **60.0 km/h**, with `independently_validated: false`.

- [Calibration and configured gates](screenshots/phase2-calibration.png)
- [Completed synthetic speed measurement](screenshots/phase2-measurement.png)
- [Mobile calibration](screenshots/phase2-calibration-mobile.png)
- [Mobile measurement dashboard](screenshots/phase2-measurement-mobile.png)

Earlier Phase 1 browser verification used an AVI containing repeated frames of
the licensed still photograph and actual YOLOX inference at 416. Its screenshots
are retained as historical Phase 1 artifacts:

- [Empty dashboard](screenshots/phase1-empty.png)
- [Paused CC0 still-image replay](screenshots/phase1-dashboard.png)
- [Mobile layout](screenshots/phase1-mobile.png)

Observed FPS and latency values in screenshots describe that short run only.
The synthetic marker adapter does not benchmark YOLOX. These are not
representative performance benchmarks. Threshold changes,
resampling, compression and inference size change detector outputs.

## Repeat locally

From the repository root, with the environment installed:

```powershell
.\.venv\Scripts\python.exe scripts\download_model.py
.\.venv\Scripts\python.exe -m pytest -q
.\.venv\Scripts\python.exe scripts\validate_speed.py
.\.venv\Scripts\python.exe scripts\make_test_video.py
Push-Location frontend
npm.cmd test
npm.cmd run build
Pop-Location
```

For a manual browser check, start the two servers using the README. Select
**Video file**, upload `data/synthetic-timing.avi`, choose an inference size and
start. Inspect source PTS, frame index, preview and measured throughput. Pause,
resume, stop, restart and reset. The geometric timing fixture is expected to
produce no vehicle detections; it does not test object detection accuracy.
For the full calibration/gates browser exercise, follow
[the synthetic validation guide](validation.md).

## Validation still required

No physical camera was opened during implementation. Camera discovery,
connection/disconnection and ownership behavior were tested with mocks. Confirm
them with the actual Windows driver, including negotiated dimensions, device
busy errors and stop/restart. Stop can take several seconds while an inference
or driver read returns. A driver that cannot release requires a backend restart.

No real moving-traffic sequence with independently labeled identities has been
evaluated. The improved global tracker is compared against synthetic truth only;
it can still switch overlapping vehicles, fragment and double-count after expiry.
Its short coordinate history is a diagnostic, not appearance identity evidence.
Live buffering favors recent frames; in-flight pause/resume protections are
covered with controlled source/worker tests.

No physical reference coordinates, independently measured vehicle speeds or
physical elevated-camera results have been collected. There is no sensor-exposure
timestamp verification or independent benchmark comparison. PTS preservation
establishes a decoder timeline, not proof of the original sensor capture timing.
The implemented calibration and speed mathematics have synthetic/integration
coverage; physical-camera geometry and ground-truth speed accuracy still require
controlled validation before making empirical performance claims.
