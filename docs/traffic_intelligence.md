# Traffic Intelligence

Phase 5 adds source-timed traffic crossings and monitoring regions to the existing local observation workflow. Open **Traffic Intelligence** in the sidebar. The observation dashboard still reports confirmed temporary tracks; this workspace separately reports finite-line crossing events. A physical vehicle can cross several lines or occupy overlapping zones, so adding those counts does not establish a unique vehicle total.

## Try the workflow

1. Open **Camera & video**, upload a local stationary-camera recording and start the observation. Pause at a clear frame.
2. Open **Traffic Intelligence → Lines & zones → Freeze counting frame**. This uses an unannotated frame in the active source or undistorted pixel space. The displayed dimensions, coordinate space and intrinsic profile identify the geometry being edited.
3. Choose **Draw counting line**, then click its start A and end B. The line is finite: passing its extension does not count. Select a line in **Selected counting region** to edit its label, direction meanings, endpoint coordinates and hysteresis. Counting lines do not alter speed gates.
4. Choose **Draw monitoring zone**, click at least three polygon vertices and select **Finish polygon**. Name the manually configured region, adjust numeric vertices and set boundary hysteresis. Multiple and overlapping polygons are supported. These are analyst-defined regions, not automatically recognized lanes.
5. Select **Save traffic configuration** while the observation is paused or completed. Resume through the observation controls. For a full recorded run, restart the same uploaded video; its matching source/geometry configuration is reused. Source, crop, rotation, mirroring or intrinsic-profile differences require an explicitly compatible configuration; the editor never silently scales points.
6. Use **Overview & trends** for KPIs and charts, **Traffic events** for individual decisions, and **Compare & export** for saved observations and datasets. Observations are archived at completion; **Archive traffic observation** saves the current retained evidence explicitly. **Refresh traffic sessions** reloads the list.

**Load synthetic traffic example** imports deterministic generated trajectories, counting events and scripted metric-speed records. Its banner identifies synthetic evidence. It does not represent detections on a real road, an independent device or demonstrated physical accuracy.

## Counting and class decisions

A confirmed track's bottom-center contact point must move between stable sides of a counting line. A hysteresis band avoids interpreting small boundary oscillations as repeated crossings. The event time is interpolated on the original source-time interval, and the crossing must lie on the finite segment. Missing timestamps, excessive gaps and interrupted tracks break continuity rather than inventing a timed crossing.

Each event retains its observation/source, temporary track, line, configuration, direction, interpolated time, category, status and diagnostic reasons. Suppressed duplicate candidates remain inspectable. Bounded temporal and spatial suppression helps flag a new identity crossing close to an earlier event, but it cannot prove physical identity and may suppress closely following vehicles. Tune these thresholds using reviewed footage and inspect both missed and suppressed events.

For direction labels, image x increases rightward and image y downward. A horizontal line drawn A-left to B-right has a positive crossing from above to below. Enter meaningful labels such as northbound and southbound after checking that orientation. Direction signs do not automatically identify a compass bearing.

The existing YOLOX-S COCO model supports **car, truck, bus and motorcycle**. The UI adds **unknown** for insufficient or conflicting class evidence. Confidence-weighted observations stabilize class votes; minimum observations, confidence and vote margin are configurable. Class scores describe model evidence and do not establish correctness. No extra classification model, plates or enforcement decisions are introduced.

## Coverage, rates and trends

Observed counts are crossing decisions. Normalized rates divide those counts by explicitly covered source seconds with counting lines active and scale to a minute or hour. Earlier unconfigured recording time cannot lower a traffic rate. Total source coverage remains separate for observation/zone metadata. A 20-second recording is not an observed hour of traffic. No browser polling, video processing throughput or pause duration is used as traffic exposure.

Choose 1, 5, 15, 30 or 60-minute aggregation. Flow intervals retain their coverage seconds, completeness, configuration, directional/class counts and cumulative count. Source-time gaps, pauses and configuration changes split coverage. Unknown timestamps cannot enter timed statistics. Empty or insufficient coverage withholds rates. Retention-limit warnings distinguish lifetime counters from retained rows and filtered subsets; exports and charts cannot reconstruct omitted historical events.

Filters select archived/current observations, class, crossing direction, counting line, event status and a source-time range in seconds. Observation start-date filters operate on recorded observation metadata, separately from the source clock. Time filters apply to each selected recording's own source seconds; equal source timestamps in two videos do not establish simultaneous wall-clock observations. Chart bars support pointer hover and keyboard focus for sample/coverage details.

## Monitoring regions and congestion heuristics

Image-space polygons require no road calibration. Entry, exit and completed dwell times use observed membership with boundary hysteresis. An interrupted visit remains interrupted; it does not receive an invented exit or complete dwell duration. The occupancy table separates completed visits, interruptions and current tracked occupancy.

Ground-plane polygons require the active valid calibration. Change **Zone coordinates** to ground meters, select **Ground-zone calibration**, then enter measured ground vertices. Switching coordinate systems resets the polygon to explicit editable defaults; it does not reinterpret pixel values as meters. A compatible homography projects ground vertices onto the frozen image. An invalidated or different calibration blocks applying the ground configuration while image-based analytics remain available.

Low/moderate/high **observed occupancy** uses configurable tracked-vehicle thresholds; defaults are moderate at 3 and high at 8. The default stationary heuristic looks for image contact positions staying within a 4-pixel radius for a 3-second source-time window. These quantities describe visible observations, not complete road density or network congestion. The configurable slow threshold defaults to 5 km/h and is available only with calibrated metric speed evidence. Pixel displacement is never converted into an uncalibrated real-world speed.

## Speed distributions

The default view includes only **valid** existing metric-speed measurements. It reports N, mean, median, minimum, maximum, population standard deviation and 85th percentile, plus distributions and grouped class/direction/source-time statistics. **Speed evidence → Approximate measurements separately** displays that status explicitly. Rejected records do not enter either aggregate.

These are summaries of the observed selected measurements, rather than new per-vehicle estimates. A crossing without a valid speed still contributes to unrelated counting analytics. Speed gates, measured geometry and timing-quality rules remain in **Calibration & gates**. Percentiles carry no regulatory or compliance determination.

## Comparing observations and exporting

Select saved observations above the views, then open **Compare & export**. Comparison rows retain source identifiers, observation start/end metadata, durations, normalized rates, configuration compatibility, speed N and warnings. Different geometry or counting definitions must not be treated as identical traffic streams. Short, interrupted and incomplete recordings stay explicit, and the application does not claim statistical significance for changes.

Choose one of seven export tables: crossing events, vehicle-class summaries, traffic-flow intervals, zone occupancy/dwell, speed summaries, session comparisons or data quality. **Export traffic CSV** and **Export traffic JSON** use the active selection and filters, explicit unit names, evidence metadata and schema version. Formula-like text is escaped in CSV for spreadsheets. JSON preserves structured values. Empty datasets contain no invented rows; CSV may retain a marked metadata row.

Use `scripts/analyze_traffic.py` for a small dependency-free exploratory analysis, or load an event CSV with pandas:

```python
import pandas as pd

events = pd.read_csv("roadlens-traffic-events.csv")
counted = events.loc[events["status"].eq("counted")]
print(counted.groupby(["category", "direction_label"]).size())
```

For Power BI, select **Get data → Text/CSV**, confirm the timestamp and speed columns are numeric, retain source/session/configuration identifiers, and filter event status to counted before making crossing charts. Source timestamps are elapsed seconds, not calendar datetimes. Keep coverage and quality tables beside rate comparisons. Review supplied text and local provenance metadata before sharing exports.

## Evaluate with manual evidence

1. Save the same recording as a Phase 4 field session, assign its dataset partition and provenance, then create consistent ground-truth identities in **Vehicle annotations**. Review consecutive visible frames around each crossing; occlusions, missing/unreviewed frames and gaps break manual trajectories.
2. Archive the predicted traffic observation with the matching source/geometry and counting definition. The manual and predicted identity namespaces remain separate.
3. Open **Evaluate predictions**, choose the predicted traffic session and matching manual field annotations, set the source-time alignment tolerance, and evaluate. Held-out is the default final-evaluation partition. Source, geometry, calibration and declared split leakage guards reject incompatible evidence.
4. Inspect truth/predicted/matched counts, misses, false positives, duplicates, signed count error, precision and recall. Sample counts accompany classification/direction accuracy and class precision/recall. The prediction-versus-manual table highlights incorrect classes/directions, misses and duplicate candidates; a confusion table shows matched class errors.
5. Review the existing annotation tracking continuity metrics and Phase 4 independent-reference speed report separately. Counting labels do not independently validate metric speed. A manual label, synchronization declaration or provenance flag is not automatically an authenticated physical reference.

Synthetic fixtures validate arithmetic, geometry and workflow. Recorded video without references supports exploratory observation. Reviewed manual trajectories support annotation-based counting/class/direction checks. Independently matched real-world measurements are required for independently validated metric speed. No physical camera, independent roadway reference device or real moving-roadway truth was supplied for Phase 5; final portfolio evidence still requires representative untouched held-out recordings, reviewed identities/classes/directions and synchronized independent speed references.
