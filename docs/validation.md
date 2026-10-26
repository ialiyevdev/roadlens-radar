# Reproduce Phase 2 validation

These exercises use known synthetic geometry and timestamps. They establish
mathematical and application behavior; they do not establish real-camera speed
accuracy or vehicle-detection performance.

## Deterministic geometry command

From the project root in PowerShell:

```powershell
.\.venv\Scripts\python.exe scripts\validate_speed.py
```

The command reads `backend/tests/fixtures/synthetic_trajectory.json`, fits a
homography and runs the actual speed engine. It asserts interpolated gate times
0.3 s and 1.5 s, displacement 20 m, elapsed time 1.2 s and **60.0 km/h**. Its
printed `independently_validated` flag remains false.

## Full browser exercise with recorded source timestamps

Stop the standard backend first, then start the optional test harness:

```powershell
.\.venv\Scripts\python.exe scripts\run_validation.py
```

It generates a lossless 800 × 600 AVI in `data/validation` and a matching
`configuration.json`. First-time generation can take several minutes; later
runs verify the video content hash and reuse it. In another terminal:

```powershell
Set-Location frontend
npm.cmd run dev
```

Open http://127.0.0.1:5173. The detector/source labels explicitly identify this as
**synthetic validation**. The harness uses the existing FastAPI app, session
manager, PyAV video decoder, tracker, calibration UI and speed engine. Only the
detector is replaced by a color-marker adapter with a fixed test score of 1.0.
It accepts only its generated fixture, never opens a camera, and stores uploads
and profiles separately under `data/validation`. This adapter is not used by
the normal `roadlens.api:app` entry point.

1. Select **Video file**, upload
   `data/validation/SYNTHETIC_60kmh_validation.avi`, and start observation.
2. Pause while the cyan rectangle is stationary. It waits for the first 15 source
   seconds, allowing setup before its traversal.
3. Open **Calibration & gates → Freeze frame**. Name the profile with a clear
   synthetic label. Click the four corner markers and enter the following
   known drawing coordinates. Source coordinates can also be corrected numerically.

| Point | Image x / y · pixels | World X / Y · meters | Role |
| --- | --- | --- | --- |
| 1 | 100 / 100 | 0 / 0 | Fit |
| 2 | 700 / 100 | 60 / 0 | Fit |
| 3 | 700 / 550 | 60 / 45 | Fit |
| 4 | 100 / 550 | 0 / 45 | Fit |
| 5, optional check | 450 / 350 | 35 / 25 | Check |

These coordinates come from the synthetic drawing. Never copy them as scale
references for an actual road.

4. Validate, inspect the grid, save the profile, confirm unchanged geometry and
   apply it to this observation. A zero fit/check error is expected for the
   drawing and makes no claim about real measurements.
5. Draw and save Gate A from **(200, 200) to (200, 450)** and Gate B from
   **(400, 200) to (400, 450)**. Keep reverse traversal disabled.
6. Return to Dashboard and resume. The marker crosses A at about source time
   **15.3 s** and B at **16.5 s**. The resulting straight-line displacement is
   **20 m**, with **1.2 s** elapsed and **60.0 km/h** estimated speed.
7. Inspect the valid result, source timestamps, sample count and diagnostics.
   Pause after completion to inspect overlays. Stop retains completed history;
   reset clears it. Start requires explicit calibration reapplication.

If setup runs past the movement, stop and start again, pause, then reload/apply
the saved synthetic profile with its gates. Pausing during an unfinished
measurement deliberately rejects it; resumed samples cannot complete that old
traversal.

Exit the harness with Ctrl+C. For genuine YOLOX inference on a webcam or video,
start the standard backend:

```powershell
.\.venv\Scripts\python.exe -m uvicorn roadlens.api:app --host 127.0.0.1 --port 8000
```

## What remains to validate

No physical camera or roadway was accessed during Phase 2 implementation.
Generated videos, controlled source/detector adapters and mathematical fixtures
exercise timing, tracking and application integration. Separate regression tests
also run the actual CPU detector on the attributed CC0 image and a recorded
still-image replay; those do not validate moving-traffic identities or speeds.

For real use, collect permitted measured references, check held-out points across
the intended region, and test a fixed camera under controlled conditions. Compare
estimates with independently established reference speeds before reporting an
accuracy metric. Include lens distortion, perspective, grade, window reflections,
contact-point error, occlusion, tracking switches and sensor timing uncertainty.
