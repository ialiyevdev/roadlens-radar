# Synthetic tracking benchmark, suite 1.0

This comparison exercises association and lifecycle independently of model
inference. It contains **no real footage, camera recording, or independent
physical identity study**. It supports a software regression conclusion for the
specified boxes, not a real traffic accuracy claim.

## Baseline established before modification

`backend/roadlens/tracker_baseline.py` is the unchanged Phase 2 tracker copied
before modifying `tracker.py`. Its SHA-256 is
`715e26eea8fd7826d6b9dda290f30d832d231d26265d7a92cabf1cc30435d75e`.
The first baseline-only run is preserved in
[tracking_baseline_before_phase3.json](tracking_baseline_before_phase3.json),
timestamped **2026-10-23 18:01:44 UTC**. The subsequent comparison is
[tracking_phase3.json](tracking_phase3.json), timestamped **18:04:28 UTC**.
The baseline report remains available even though machine timings vary on rerun.

Both trackers use the same one-second expiry, three-hit confirmation, input
order, class labels, source timestamps and generated detections. The improved
tracker replaces greedy best-edge-first selection with global maximum-cardinality
assignment followed by maximum score. It retains the existing IoU/distance gates
and adds a small shape score and smoothed association velocity. It requires no
new runtime or trained model. Returned boxes and contact history remain raw
observations; association smoothing does not adjust speed measurements.

## Data and metric definitions

`benchmark_scenarios()` specifies all boxes, truth identities, omissions, jitter
and timestamps directly in Python, with no random state. Eleven scenarios cover
constant motion, parallel vehicles, crossing paths, short and long occlusion,
box jitter, different speeds, irregular timestamps, ambiguous overlap, entry/exit
and the original greedy assignment counterexample. There are **352 frames and
484 ground-truth object observations** in total. Each scenario owns fresh IDs.

For evaluation, currently observed tracker boxes are globally matched to
independently generated truth boxes at **IoU >= 0.5**, maximizing match count and
then IoU. Lost tracks are not observations. A truth identity changing tracker ID
from its last matched observation counts as an **ID switch**, including after
an observation gap. A previously matched truth object becoming unmatched then
matched again counts as a **fragment**. Thus detector omissions can produce a
fragment even when the tracker keeps the correct ID. A replacement ID after
expiry counts as a switch under this explicit definition. `created_tracks` is
the count of distinct emitted IDs; `confirmed_tracks` in benchmark reports is
the cumulative number that reached confirmation, including subsequently lost
or removed tracks. It differs from the live active-confirmed count.

These are explicitly defined metrics for this small suite; IDF1, MOTA and HOTA
are not implemented or claimed. Geometric matching near overlapping truth boxes
can itself be ambiguous. A stable assigned ID cannot prove physical identity.

## Actual recorded results

| Scenario | Baseline ID switches | Improved ID switches | Fragments, both |
| --- | ---: | ---: | ---: |
| Constant motion | 0 | 0 | 0 |
| Parallel vehicles | 0 | 0 | 0 |
| Crossing paths | 0 | 0 | 0 |
| Short occlusion | 0 | 0 | 1 |
| Long occlusion | 1 | 1 | 1 |
| Box jitter | 0 | 0 | 0 |
| Different speeds | 0 | 0 | 0 |
| Irregular timestamps | 0 | 0 | 0 |
| Ambiguous overlap | 2 | 0 | 1 |
| Entry/exit | 0 | 0 | 0 |
| Greedy counterexample | 2 | 0 | 0 |
| **Total** | **5** | **1** | **3** |

Both matched **466/484** truth observations and missed **18** observations. These
misses are deliberately omitted detections. Created IDs changed from **19 to
18**; confirmed IDs remained **16**. The remaining switch follows the deliberate
occlusion longer than the TTL: the tracker correctly starts a new hypothesis
instead of claiming appearance-based re-identification.

The improved live diagnostic reported **four potential-switch episodes** and
**one possible fragmentation after expiry**. These are heuristic suspicions,
not the ground-truth switch/fragment metrics above. The baseline has no such
monitor; its zero suspicion fields mean unavailable, not demonstrated certainty.

The comparison ran on Windows 11 build 26200, Python 3.13.9, Intel64 Family 6
Model 154 Stepping 3, 12 logical CPUs. After eight untimed warm-up updates, five
repetitions used identical scenario sequences. `perf_counter_ns` bracketed only
`update()`; detector inference, evaluation, rendering and HTTP were excluded.
P95 uses linear interpolation across pooled per-update timings.

| Update timing | Baseline | Improved |
| --- | ---: | ---: |
| Mean | 0.01560 ms | 0.03904 ms |
| P95 | 0.03130 ms | 0.09371 ms |

The improved tracker costs more CPU in this tiny one/two-vehicle workload.
No performance improvement or detection FPS claim follows from this comparison.
Baseline ran first; machine load, scheduler, timer resolution, allocations and
order effects remain. The earlier baseline-only mean was 0.00794 ms, illustrating
why individual local timing samples should not be interpreted as stable limits.

## Live lifecycle and diagnostic meanings

- New tracks are tentative; three observed detections confirm them. Short gaps
  produce a lost state. More than one source second without an observation
  removes the track; removed tracks disappear from the emitted list.
- `age_s` measures source time since first observation. `observation_gap_s`
  measures the interval between the latest two observations for a matched
  track, or time since the last observation while lost; a new track starts at 0.
- `association_ambiguous` means a competing feasible score was close to the
  selected score, or the globally selected score lost a stronger local choice.
  The margin is 0.12 in an uncalibrated ranking score, not a probability.
- `potential_id_switches` counts new ambiguous episodes per track, retaining an
  episode across missing observations. It neither verifies nor estimates the
  number of actual identity switches. Independent truth is needed for that.
- A nearby new ID after a recent expiry increments
  `fragmentation_suspicions`. This does not reconnect identities. Recent removed
  hypotheses are retained for at most one additional TTL, capped at 128.
- A box area decrease below 60% of the prior area exposes possible partial
  occlusion; a large increase exposes a size jump. Neither proves its cause.
- Live `active_tracks` includes observed tentative and confirmed tracks;
  `confirmed_tracks` counts currently observed confirmed tracks. `lost_tracks`
  counts retained missing hypotheses; `removed_tracks` is cumulative.

The gates remain IoU >= 0.15 or contact distance <= 0.65 predicted-box diagonals,
with same-category association. This deliberately small motion tracker can still
switch identities when vehicles overlap, accelerate, change apparent class or
disappear. Assignment maximizes feasible correspondence; it does not create
identity evidence. Appearance re-identification and learned confidence are absent.

## Reproduce

From the repository in Windows PowerShell:

```powershell
.\.venv\Scripts\python.exe scripts\benchmark_tracking.py --output data\tracking_benchmark.json
.\.venv\Scripts\python.exe -m pytest backend\tests\test_tracker.py backend\tests\test_assignment.py backend\tests\test_tracking_reliability.py backend\tests\test_tracking_benchmark.py -q
```

The endpoint/UI use the same bounded function. JSON includes every scenario,
source-time continuity series, definitions and measured hardware/timing fields.
The 45 focused tests include exhaustive small assignment optima, explicit
crossing/occlusion identities, timestamp rejection, ambiguity, raw-box retention,
lifecycle and a hand-calculated metric example. The test suite is synthetic;
physical-camera accuracy still needs independent labeled observations.
