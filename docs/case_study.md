# RoadLens Radar: a technical case study

## Problem

A stationary camera supplies image positions, not road distances or vehicle identities. Perspective makes identical pixel displacements correspond to different distances. Lens distortion, uncertain vehicle contact points, occlusion and missing detections add error. Processing intervals can also differ from recording intervals. Counting visible objects is therefore a different problem from measuring a repeatable crossing event or a defensible metric speed.

## Objective

RoadLens is a local engineering workbench for vehicle detection, temporary tracking, calibrated gate-speed estimation and directional traffic activity. It records the configuration, source time, diagnostic status and provenance behind each result. A visitor can inspect stored synthetic examples without a camera; an operator can use the full application for a local source and an explicit validation workflow. It is not certified traffic enforcement equipment.

## Technical approach

The backend uses OpenCV DNN with a pinned OpenCV Zoo YOLOX-S INT8 model on CPU. It keeps car, motorcycle, bus and truck predictions. Global motion/IoU association produces tentative, confirmed and lost tracks without a second neural model. This keeps installation local and avoids a GPU/PyTorch requirement, at the cost of limited identity evidence during occlusion.

The operator supplies measured road references to fit a homography. The observed box bottom center approximates contact with that plane. Optional intrinsic correction happens before detection and geometry; all coordinates bind to a specific full-image geometry and profile. Gate intersections are interpolated between observed road positions, then speed is displacement divided by elapsed source time. The implementation retains raw contacts and does not smooth or rescale a speed to make it look more stable.

Recorded video uses PyAV presentation timestamps. Live capture timestamps acquisition with a monotonic clock. Inference, decode and browser timing are measured separately. A capacity-one live frame buffer favors recent observations over a growing queue; recorded video processes sequentially. Missing/backward times, long gaps, pause and configuration changes interrupt measurement continuity instead of inventing elapsed time.

An incremental traffic engine consumes the existing tracks. It combines finite-line crossings, direction, accumulated category evidence and zone visits. Boundary hysteresis limits oscillation. Aggregate rates use accepted source coverage and configuration history; speed statistics separate valid, approximate and rejected cohorts. Atomic JSON artifacts retain results without duplicating source footage, and native SVG charts display the same analytics used by JSON/CSV exports.

Validation has two distinct inputs. Manual frame annotations can evaluate detection/tracking continuity and counting events. Metric speed additionally needs independently obtained reference values, explicit event correspondence and justified clock alignment. Recording-level partitions prevent declared duplicates from appearing in both development and held-out evaluation.

## Engineering challenges and decisions

| Challenge | Implemented choice | Remaining tradeoff |
| --- | --- | --- |
| Perspective and lens effects | Source-bound road homography; optional full-image intrinsic correction before detection | A single planar model cannot represent arbitrary road grade or a moved camera |
| Ground contact approximation | Preserve the observed bottom-center point and expose region/contact diagnostics | A bounding box is not a measured tire contact, particularly during occlusion |
| Ambiguous association | Global assignment with motion, IoU and shape evidence; preserve a greedy baseline | More CPU work; no appearance re-identification or guaranteed physical identity |
| Uneven frame intervals | Use source timestamps and explicit continuity/status guards | Sparse observations cannot recover an unseen motion path |
| CPU inference cost | Configurable verified 320/416/640 inputs, bounded live buffering, separate stage profiles | No guaranteed real-time rate; input-size accuracy requires representative footage |
| Repeated crossings and fragmented IDs | Per-ID/line/direction/version counting plus a narrow, explainable duplicate heuristic | Separate fragments can still count twice; close vehicles can remain ambiguous |
| Incomplete observation coverage | Versioned intervals, retained omission diagnostics and withheld unsupported rates | A short observed rate does not establish hourly volume or complete density |
| Evidence interpretation | Label scripted, still-replay and independent-reference workloads separately | Synthetic correctness cannot establish physical roadway accuracy |

The detector choice is supported by the pinned upstream directory's explicit Apache-2.0 terms and the existing CPU implementation. The source retains attribution, verifies downloaded model bytes and does not bundle the weights. The choice does not establish superiority over other detectors. See [model provenance](model.md) and [architecture](architecture.md) for contracts and source links.

## Measured results

These are recorded software experiments with different workloads. They must not be combined into an end-to-end throughput or accuracy figure. The [performance report](performance.md) contains reproduction commands and the full context.

| Experiment | Recorded result | What was measured |
| --- | --- | --- |
| Actual-model still replay | Mean detection **176.378 ms**, tracking **0.162 ms**, traffic **0.212 ms** per measured frame | Actual YOLOX-S INT8, one repeated CC0 still resized to 640×360, 640-square model input, one warm-up plus 12 measured iterations; five detected tracks, two synthetic lines and one image zone |
| Synthetic 32-track load | Mean tracker **3.235 ms**, traffic **0.838 ms** per update | 200 generated 32-box frames through the real tracker and traffic engine, one line and one zone; excludes inference, decode, HTTP and browser work |
| Synthetic counting regression | **14/14 scenarios**, **17/17 expected crossings**, one expected duplicate suppression | 107 scripted input frames, direct traffic-engine observations; no detector or physical vehicles |
| Synthetic tracker comparison | **5 → 1 ID switches**; mean update **0.01560 → 0.03904 ms** | Same 11 scenarios, 352 frames and 484 generated truth observations; both trackers retain three fragments and 18 omitted observations |
| Scripted speed-error arithmetic | Eligible **N=12**, MAE **2.833 km/h**, RMSE **3.266 km/h** | Synthetic imported measurements/references exercise filtering and error formulas; no physical instrument |

The Phase 5 model replay and 32-track profile ran on an Intel Core i5-12450H host with 12 logical CPUs, Windows 11 build 26200, Python 3.13.9 and OpenCV 4.14.0. The model replay used 12 OpenCV threads. Its source-time increments are scripted; the same still cannot test moving traffic or gate speed. Reported model-stage timings exclude decode, lens correction, road projection, speed estimation, overlays, JPEG, HTTP and browser rendering.

Evidence files: [model replay](benchmarks/phase5-model-performance.json), [32-track profile](benchmarks/phase5-performance.json), [counting suite](benchmarks/phase5-counting.json) and [tracker methodology](benchmarks/tracking.md). Final release regression counts are maintained in [testing](testing.md), so historical benchmark evidence remains separate from current test runs.

## Validation limitations

There is no independently measured roadway speed/counting dataset in the release. The bundled licensed real image is a still without ground-truth labels; other demo observations and known speeds are generated. Passing those tests demonstrates selected code paths, geometry arithmetic, filtering and export behavior. It does not quantify detection accuracy, physical contact error, timing error, speed uncertainty or field counting reliability.

Manual category/identity annotations can be wrong, clock anchors can be uncertain and instrument readings may not be independent. The application preserves declarations, exclusions and unmatched events, but cannot certify them. Occlusion, distant small vehicles, darkness, camera vibration, slope and changing camera settings remain practical failure modes. The [field procedure](real_world_validation.md) describes how independent evidence can be collected and separated from development data.

## Future work

The next useful evidence is a permissioned, representative held-out recording set with reviewed vehicle identities, line crossings and independently matched speed references. Multiple camera views, traffic densities, lighting conditions and repeated calibration checks would reveal failure patterns. Candidate detector resolutions, association methods and calibration/contact models should then be compared on the same recordings, with cost, misses, duplicate counts and excluded speed measurements reported together. No such field improvement is claimed by this release.
