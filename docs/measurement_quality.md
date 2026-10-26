# Observable measurement evidence

Phase 2's original estimate, crossing positions/timestamps, status, reasons,
calibration ID and source/session/track IDs remain intact. Phase 3 adds numerical
evidence, never a correction multiplier, learned confidence or empirical error
interval. `valid` means the configured engineering checks passed; it does not
mean independently accurate.

## Rules and quantities

| Observation | Default handling | Interpretation |
| --- | --- | --- |
| Ambiguous track assignment | Reject a pending traversal, break position continuity | A selected assignment is not reliable physical identity evidence |
| Missing observation / lost ID | Reject a pending traversal | The tracker may reconnect after a short gap; a speed measurement does not bridge lost identity |
| Current ambiguity, missing or invalid contact after completion | Hide current numeric overlay; preserve completed history | A past result must not label an uncertain current association |
| Frame-clipped contact or outside measured hull | Invalid position; reject active traversal | Do not extrapolate beyond measured support |
| Contact within 8 image pixels of hull | Approximate | Image proximity is observable; it is not a metric error bound |
| Box overlap ≥30% of smaller box | Approximate | Possible partial occlusion, not confirmed occlusion |
| Box area shrinks below 60% of previous | Approximate | Possible occlusion or detection instability |
| Constant-velocity contact residual >8 px | Approximate | Can also reflect acceleration or turning; inspect raw samples |
| Observation interval >0.25 s | Approximate | Crossing interpolation is coarse |
| Observation interval >1 s or invalid/fallback timing | Reject active traversal | Source-time continuity is unavailable |
| Movement >250 km/h plausibility guard | Reject | Investigate identity, timing and calibration; this is not a legal limit |
| Both gates in one interval | Reject | Insufficient temporal support |
| Observed calibration/gate warnings | Approximate | Held-out error, coverage, conditioning or gate proximity concern |

The 8 px proximity/residual, 1 m near-gate and sampling thresholds are configurable
`SpeedOptions` engineering settings. They need evaluation for each camera; they
do not specify measurement accuracy. Generic reminders about a stationary camera,
four fitted points or absent held-out checks remain visible without downgrading
every result automatically. No held-out error is displayed as zero when checks
are missing.

Contact residual compares a raw point with constant-velocity extrapolation of
the two previous valid points using their actual source intervals. Pixel and
projected-meter residual maxima are retained. No contact smoothing changes the
crossing timestamps or displacement.

## Retained evidence and exports

Every completed/rejected result retains calibration fit/check RMSE, image coverage,
minimum signed hull margin in pixels, maximum observation interval and motion
residuals, ambiguous/overlapping observation counts, track age and gate warnings.
Near-gate counts use the configured **1 m distance to each finite gate segment**;
these counts are diagnostic and do not themselves certify crossing support.
Each gate retains the source interval used for its crossing interpolation.

Constant-size counters/extrema cover the current continuous measurement attempt,
including earlier observations that have left the raw history. An invalid
pre-gate attempt resets when fresh valid continuity begins. Evidence stops at the
recorded completion/rejection. Up to **120** original boxes, detector scores,
image/world contacts, source times, gaps, residuals and reasons are copied with
the result; `position_history_truncated` and retained/total counts identify
incomplete raw history. Up to **1,000** results are retained.

Polling exposes aggregate records. **Measurement history → Export JSON/CSV**
includes the full retained samples and a snapshot of the original calibration
references, held-out points, diagnostics and gates. Later profile edits or
invalidation do not rewrite that evidence. Source labels/profile names and raw
frames are excluded. CSV uses JSON cells for sample/geometry arrays and flattened
`diagnostic_...` columns; JSON preserves nested structure.

Use these quantities with independent reference errors to investigate the
contributors in [the field guide](real_world_validation.md). A small residual
does not rule out lens distortion, planar-model bias, sensor timing errors or an
incorrect reference match. Software diagnostics cannot observe every cause.
