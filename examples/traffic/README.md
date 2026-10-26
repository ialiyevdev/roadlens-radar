# Synthetic traffic examples

Every dataset in this directory is generated software evidence. It contains no physical traffic, independent speed instrument readings or measured roadway accuracy.

`synthetic_traffic_session.json` is the complete persisted artifact: six crossing events from 120 generated trajectory frames, 59.5 covered source seconds, a counting line and an image zone. Four scripted valid speeds have a mean of 28.5 km/h; one approximate and one rejected value remain outside that aggregate. These numbers test arithmetic and status separation. They do not estimate model or camera accuracy.

`synthetic_trajectories.json` contains the input boxes and source timestamps. The event, class, flow, zone, speed, comparison and quality JSON/CSV files are exports from the actual analytics code. The dashboard's **Load synthetic traffic example** action imports a new local copy of this artifact.

From the repository root in PowerShell:

```powershell
.\.venv\Scripts\python.exe scripts\make_traffic_fixture.py --video data\traffic_fixture\synthetic_traffic.avi
.\.venv\Scripts\python.exe scripts\benchmark_traffic.py --repetitions 30 --output docs\benchmarks\phase5-counting.json
.\.venv\Scripts\python.exe scripts\profile_traffic.py --repetitions 30 --output docs\benchmarks\phase5-performance.json
.\.venv\Scripts\python.exe scripts\profile_traffic_pipeline.py --frames 12 --input-size 640 --output docs\benchmarks\phase5-model-performance.json
.\.venv\Scripts\python.exe scripts\analyze_traffic.py examples\traffic\synthetic_events.csv
```

The optional FFV1 clip contains labeled moving shapes. The fixture generator supplies known boxes directly to the counting engine; it does not imply that YOLOX detects those shapes as vehicles. The model profile separately runs the existing YOLOX model on the existing CC0 still image. Static-image replay measures software cost, not moving-traffic counting accuracy.

`scripts/analyze_traffic.py` loads a JSON or CSV event export using Python's standard library and summarizes class/direction counts and attached valid speeds. No analysis dependency is required to run the application. An optional pandas exploration is equally small:

```python
import pandas as pd

events = pd.read_csv("roadlens-traffic-events.csv")
counted = events.loc[events["status"].eq("counted")]
print(counted.groupby(["line_id", "direction", "category"]).size())

flow = pd.read_csv("roadlens-traffic-flow.csv")
print(flow[["session_id", "start_s", "coverage_seconds", "count"]])
```

Power BI can import the same UTF-8 CSVs through **Get data → Text/CSV**. Use `session_id` plus `configuration_id` to keep observations/configuration versions separate. Treat source timestamps as elapsed seconds, speeds as km/h and coverage as seconds. Inspect `complete_window`, quality exports and the repeated `filters_json`/`units_json` metadata before comparing rates. Empty exports contain one `export_row_type=metadata` row; exclude it from fact tables. Nested columns contain JSON text.

Normalized crossings/hour is `observed crossings × 3600 / covered seconds`. A one-minute or interrupted recording does not establish a reliable hourly traffic volume. Summing multiple lines counts crossings at each line, and can count one physical vehicle several times. Replaying the same recording produces another software observation, not another independent traffic sample.
