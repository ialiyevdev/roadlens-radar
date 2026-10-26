# Performance and engineering evidence

These are actual local observations on **Windows 11 build 26200**, **Intel Core
i5-12450H / 12 logical CPUs**, Python **3.13.9**, OpenCV **4.14.0**. Host load and
short samples affect the results. No physical camera was opened, and none of
these measurements establishes real-time throughput on moving traffic.

## Evidence categories

| Category | Available evidence | What it does not establish |
| --- | --- | --- |
| Actual model inference | Repeated attributed CC0 still, real YOLOX/OpenCV CPU calls | Moving-road detection, tracking or speed accuracy |
| Generated video | Timing/control and marker-adapter workflow tests, FFV1 annotation navigation | Recorded roadway behavior or model accuracy |
| Scripted observations | Tracker comparison, counting scenarios, dense traffic timing | Detector recall, independent vehicle identities or field precision |
| Prescribed speed references | Synthetic matching and error-metric arithmetic | Physical instrument agreement |
| Independent field study | None supplied or performed | All real-world accuracy remains unverified |

Phase 6 regression passed **636 backend** and **151 frontend tests**. Both
TypeScript/production builds and local browser checks passed; these are quality
checks, not throughput measurements. The [verification record](testing.md) separates full regression, browser checks
and isolated installation. Phase 6 changes presentation and reproducibility;
the historical measurements below were not silently rerun or combined.

## Synthetic speed-validation arithmetic

The [Phase 3 stored report](../examples/validation/synthetic_report.json) has
18 rows, 14 matched references and 12 eligible pairs. MAE is **2.8333 km/h**,
RMSE **3.2660**, signed bias **+1.3333**, median absolute error **2.5** and P90
absolute error **4.9**. Estimates were deliberately perturbed from prescribed
mathematical reference values. These statistics test matching and arithmetic.

The separate [Phase 4 field fixture](../examples/field/synthetic_field_session.json)
has six original events and an eight-event external ledger. Its four eligible
pairs yield MAE **2.0 km/h**, RMSE **2.1213**, bias **+0.5**, median absolute
error **2.0** and P90 **2.7**. Four deliberately scripted baseline/improved
pairs give MAE **2.5 → 2.0**; this is a comparison-workflow check, not a measured
pipeline improvement. The source-time gate regression gives **20 m / 1.2 s =
60.0 km/h**. None used a physical reference instrument.

```powershell
.\.venv\Scripts\python.exe scripts\validate_dataset.py examples\validation\synthetic_reference_speeds.csv --output data\speed-validation.json
.\.venv\Scripts\python.exe scripts\validate_field.py --output data\field-validation
```

## Phase 5 traffic processing

The new engine adds CPU work after the existing tracker and speed estimator.
Its `profile` separates classification, finite-line crossing checks, event creation
and zone membership. Full snapshots, statistics and export serialization run on
explicit HTTP requests, rather than on every inference frame. The established
five-field `pipeline_profile` contract remains unchanged.

The [counting benchmark](benchmarks/phase5-counting.json), measured on 25 October
2026, supplies known trajectories directly to the real engine. All **14/14**
scenario expectations passed: **107 frames**, **17/17 expected crossings** and
**one expected duplicate suppression**. Thirty repetitions yielded 3,180 valid
timed update samples, averaging **0.0752 ms**, P95 **0.1799 ms**. These cases test
finite endpoints, multiple/bidirectional lines, jitter, occlusion, fragmented IDs,
uncertain classes, zones and invalid/gapped source time. They exclude detection,
tracker association, decode, HTTP and actual road footage.

[phase5-performance.json](benchmarks/phase5-performance.json) separately measures
32 scripted detections through the actual IoU tracker and traffic engine over
200 frames, one counting line and one image polygon. It also measures 30 trials
of statistics, snapshot serialization and exports. The small analytical artifact
contains six generated crossings and four scripted valid speeds. The dense
fixture has 32 tracks per frame, rather than 32 independently observed vehicles.

| Component | Mean ms | P95 ms |
| --- | ---: | ---: |
| Dense tracker update, 32 boxes | 3.2350 | 4.2106 |
| Additional dense traffic update | 0.8381 | 1.2480 |
| Classification within dense update | 0.0829 | 0.1330 |
| Crossing checks within dense update | 0.0343 | 0.0542 |
| Event creation within dense update | 0.00084 | 0.00170 |
| Zone processing within dense update | 0.6507 | 0.9984 |
| Small fixture statistics aggregation | 0.4472 | 0.7816 |
| Dense fixture statistics aggregation | 0.1157 | 0.1772 |
| Dense snapshot JSON serialization | 0.1899 | 0.1974 |
| Dense analytics JSON serialization | 0.1757 | 0.2011 |

The dense fixture produces few new events; its event-creation timing cannot
represent heavy crossing bursts. The scenario benchmark separately includes
actual crossing creation. Zone checks dominate the added dense cost. No
throughput improvement is claimed: traffic processing adds work to an otherwise
unchanged detector/tracker path. Statistics costs depend on retained events,
coverage and groups, not solely on the number of visible tracks.

```powershell
.\.venv\Scripts\python.exe scripts\benchmark_traffic.py --repetitions 30 --output data\profiling\traffic-counting.json
.\.venv\Scripts\python.exe scripts\profile_traffic.py --repetitions 30 --output data\profiling\traffic-performance.json
```

## Phase 5 actual detector workload: repeated CC0 still

[phase5-model-performance.json](benchmarks/phase5-model-performance.json) runs
the actual downloaded YOLOX-S INT8 model at input 640 on a repeated 640×360 CC0
traffic photograph. One warm-up and model loading are excluded. Twelve measured
frames each produced five detections and five tracks. Two synthetic counting
lines and one image polygon exercise traffic processing; a still image has zero
expected crossings and establishes no moving-vehicle accuracy.

| Component | Mean ms | P95 ms |
| --- | ---: | ---: |
| Detection, including preprocessing/postprocessing | 176.3776 | 181.1587 |
| Tracking | 0.1624 | 0.2139 |
| Additional traffic processing | 0.2124 | 0.3763 |
| Statistics aggregation | 0.5075 | 0.8209 |
| Combined snapshot/analytics JSON serialization | 0.1223 | 0.1693 |
| Measured processing total | 177.3821 | 182.0172 |

The raw report records each distribution, model/fixture hashes, CPU, versions
and exclusions. Source time advances independently by 0.1 seconds per frame.
This in-memory workload excludes decode, lens correction, road projection,
speed estimation, overlays/JPEG, HTTP and browser rendering. It is a component
measurement, not an end-to-end camera FPS claim. Its detection time differs from
the retained Phase 3 sample; the short runs and host load do not establish a
statistically significant performance change.

```powershell
.\.venv\Scripts\python.exe scripts\profile_traffic_pipeline.py --frames 12 --input-size 640 --output data\profiling\traffic-model.json
```

Histories have explicit caps: 10,000 crossing events, 10,000 zone events, 5,000
occupancy samples, 10,000 coverage segments, 128 configuration versions and
bounded identity/region state. Omission counters remain visible. Unfiltered
lifetime totals and retained filtered rows are separate; rates requiring missing
evidence are withheld. The browser paginates events at 100 rows and bounds chart
groups. Full retained exports and large HTTP snapshots can still cost materially
more than these small samples. Local archives are limited to 32 MiB per artifact;
archive failures are exposed without replacing the observation state.

## Pipeline instrumentation

The session snapshot reports latest-frame `inference_ms`, `pipeline_profile`
(`decode_ms`, `undistortion_ms`, `tracking_ms`, `projection_ms`, `gate_events_ms`), processing FPS, acquisition
FPS, end-to-end processing latency and overwritten live-buffer frames.

- Detection includes preprocessing, DNN forward and postprocessing.
- Decode brackets recorded-frame decoding and conversion to BGR. It is distinct
  from the source presentation timestamp and unknown live-device buffering.
- Optional undistortion brackets cached full-frame remapping before detection.
  Its initialization cost is separate; the disabled path reports zero.
- Tracking brackets `tracker.update()`.
- Projection sums homography projection calls for the frame. It excludes hull
  proximity checks, quality bookkeeping and retained-history serialization.
- Gate events bracket observing accepted positions, intersection processing,
  completion and associated result evidence. A frame without eligible positions
  can legitimately report zero.
- Processing latency includes work/waiting since acquisition and encoding. It
  excludes unknown device buffering, browser display and network transfer.
- Dropped frames count overwritten capacity-one live-buffer packets. The
  recorded-video path processes sequentially; its zero drops are by construction.

These use `perf_counter()` independently of original source timestamps. They do
not substitute inference completion time for source PTS. Homography, inverse,
region contour, grid and gate vectors are cached until configuration changes.
Raw contact positions remain unsmoothed.

## Phase 4 camera-model cost: synthetic pixels

[camera_phase4.json](benchmarks/camera_phase4.json) records generated BGR pixels
and exact projected checkerboard corners. The host identified itself as Intel64
Family 6 Model 154, twelve logical CPUs, Windows 11 build 26200, Python 3.13.9 and
OpenCV 4.14 with twelve OpenCV threads. No lens, physical target or camera was
measured. Ten untimed remaps preceded 200 timed cached calls at each resolution.
The map keeps the original dimensions and camera matrix with no crop.

| Component | Mean ms | Median ms | P95 ms |
| --- | ---: | ---: | ---: |
| Cached undistortion, 640 × 480 | 0.911 | 0.849 | 1.245 |
| Cached undistortion, 1280 × 720 | 2.069 | 1.925 | 3.181 |

One-off map initialization measured 8.639 ms and 2.661 ms respectively. Those
single initialization observations include startup/scheduling effects and do not
establish how initialization scales with resolution. They are excluded from the
cached-call distribution.

Fitting ten exact projected target views took 27.550 ms and returned a
0.0000101 px reprojection RMS, with maximum focal-parameter error 0.000282 px.
That fixture checks numerical geometry recovery. It excludes photograph corner
finding, target imperfections and lens/road effects; it establishes no physical
calibration or speed accuracy. The separate tests render target images and run
OpenCV's real corner finder without treating those images as field evidence.

```powershell
.\.venv\Scripts\python.exe scripts\benchmark_camera.py --repetitions 200 --output data\profiling\camera.json
```

## Phase 4 field-workflow cost: synthetic software data

[phase4-field-performance.json](benchmarks/phase4-field-performance.json) records
30 repetitions on the same reported Windows/Intel processor family with Python
3.13.9, OpenCV 4.14 and PyAV 16.1.0. Stateless operations had one warm-up call;
navigation used fresh decoders. P95 uses linear interpolation at `(n-1)*0.95`.
The field fixture has six original events, four eligible numerical comparisons,
four baseline/improved pairs and seven reference events.

| Component | Mean ms | P95 ms |
| --- | ---: | ---: |
| Import seven reference events | 0.117 | 0.245 |
| Diagnose one explicitly matched event | 0.020 | 0.027 |
| Evaluate complete field fixture | 1.484 | 1.695 |
| Serialize an already computed JSON report | 0.313 | 0.359 |
| Render an already computed CSV report | 0.721 | 0.870 |
| Render an already computed HTML report | 0.337 | 0.425 |
| Source-timestamp diagnostics, 1,000 packets | 4.225 | 4.615 |
| Processed-frame diagnostics, 1,000 packets | 0.514 | 0.523 |
| Timing snapshot with 240 retained latencies | 0.0069 | 0.0080 |

The timestamp batch means correspond to approximately 0.00423 ms per source
packet and 0.000514 ms per processed packet. These are normal synthetic packets;
the timings exclude actual acquisition, decode, inference and frame pixels.
Timing snapshots sort at most 240 latency values. Running interval moments and
the 120-interval gap window remain bounded over a long observation.

The navigation workload is a generated 120-frame FFV1 video, 320 × 240 at 25 fps.
Each trial opens a new decoder, but the operating-system file cache may already
contain the clip. Constructor/indexing costs are timed separately from image
requests; API, JPEG encoding and browser display are excluded.

| Navigation operation | Mean ms | P95 ms |
| --- | ---: | ---: |
| Build metadata index for 120 frames | 143.887 | 158.401 |
| Decode uncached forward to frame 120 | 64.079 | 147.756 |
| Sequential next frame | 1.513 | 2.327 |
| Previous frame present in pixel cache | 0.147 | 0.195 |
| Uncached backward request to frame 1 | 7.111 | 8.672 |

Annotation navigation retains at most three navigators, each with eight recent
frames and a 64 MiB pixel budget. Large sources and distant backward requests
can be materially slower. Metadata indexing decodes up to 100,000 frames once;
it does not keep all frame arrays. Optional model proposals use a separate
explicit request, pause the live observation and process at most 100 consecutive
frames. No proposal-inference throughput is inferred from navigation timings.

```powershell
.\.venv\Scripts\python.exe scripts\profile_field.py --iterations 30 --output data\profiling\field.json
```

Field report serialization excludes evaluation; evaluation excludes ML inference,
live capture, HTTP, browser rendering and annotation tracking unless explicitly
provided. The committed numbers describe the recorded small software workload,
not a live throughput guarantee. Hardware load and subsequent code revisions can
change a rerun. No comparable real-road footage with independent references was
supplied, so lens-correction or speed-accuracy improvements remain unmeasured.

## Retained Phase 3 detector workload

[pipeline_profile.json](benchmarks/pipeline_profile.json) records 12 measured
frames after one warm-up, actual YOLOX-S INT8 CPU inference at **640**, confidence
0.35, and the CC0 test still resized to **640 × 360**. Each frame produced five
vehicle detections. The replay is held in memory, with synthetic plane references
solely to exercise projection/gates. That geometry establishes no scale or true
vehicle speeds for the photograph. Model loading, source decode and HTTP are
excluded; drawing and JPEG encoding are included in the total.

| Stage | Mean ms | P95 ms |
| --- | ---: | ---: |
| Detection | 309.318 | 820.712 |
| Tracking | 0.4496 | 1.7015 |
| Projection, per frame | 0.687 | 2.472 |
| Gate processing, per frame | 0.089 | 0.260 |
| Drawing/JPEG | 3.188 | 10.458 |
| Total | 314.472 | 838.151 |

Effective processed throughput was **3.180 FPS**, with zero constructed replay
drops. This small development-host sample had substantial timing variation.
Stages do not sum exactly to total because quality checks, history management
and loop overhead are not individual timers. No speed-up claim follows.

```powershell
.\.venv\Scripts\python.exe scripts\profile_pipeline.py --frames 12 --input-size 640 --output data\profiling\pipeline.json
```

Changing input resolution changes detections as well as compute cost. This
fixture can yield zero detections at smaller inputs; zero projection/gate time
then means no observations, not a faster equivalent tracking workload.

## Tracker comparison

The independent [tracking comparison](benchmarks/tracking.md) uses identical
scripted boxes, one/two vehicles, and no inference. Its recorded mean update cost
is **0.01560 ms baseline / 0.03904 ms improved**, with P95 **0.03130 / 0.09371 ms**.
Global assignment improves specified identity outcomes and costs additional CPU.
This workload cannot predict scaling in a crowded scene or total detector FPS.

## Polling and retained evidence

Full position/calibration evidence is retained internally and serialized only
for explicit exports. `/api/session` and `/api/measurements` carry small result
records with diagnostic aggregates. Cached public records refresh when results
change; sample arrays are not deep-copied under the session lock on every poll.

[polling_profile.json](benchmarks/polling_profile.json) profiles the maximum
retained result count: **1,000 cloned synthetic records × 120 tiled samples**.
These are storage fixtures, not independent or chronological observations.
Construction and evidence exports are excluded. Three runs measured median
cached synchronization **1.42 ms**, snapshot copy **47.42 ms**, serialization
**7.87 ms**, and a **1.356 MiB** polling payload. Maximum history still has a
material polling/DOM cost; pagination is a future option. No real pipeline FPS
is inferred from this storage test.

```powershell
.\.venv\Scripts\python.exe scripts\profile_snapshot.py --output data\profiling\polling.json
```

## HTTP response setup

Every normal response exposes `X-RoadLens-Response-Ms`. `GET /api/performance`
reports per-route mean/P95/latest setup times over at most 120 responses, with
at most 64 route patterns retained. Setup timing ends at response headers and
does not measure streaming-body completion.

[http_profile.json](benchmarks/http_profile.json) records 20 sequential localhost
`GET /api/session` requests after three warm-ups, while idle. The payload was
900 bytes. Server setup mean/P95 was **1.021 / 2.020 ms**; client round-trip
mean/P95 was **4.834 / 14.478 ms**. Client timing also includes opening loopback
connections and reading the body. These idle values do not describe inference
load, full history, Vite proxy time or browser rendering.

With the normal backend running on localhost:

```powershell
.\.venv\Scripts\python.exe scripts\profile_http.py --output data\profiling\http.json
```
