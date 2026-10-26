# Phase 3 file map

The project remains the existing FastAPI/React application. No runtime dependency
was added. Versions are 0.3.0; the Phase 2 tracker is preserved for comparison.

| Area | Added | Updated |
| --- | --- | --- |
| Tracking | `assignment.py`, `tracker_baseline.py`, `tracking_benchmark.py` | `tracker.py` |
| Measurement | `measurement_quality.py`, `profiling.py`, `phase3_api.py` | `measurement_models.py`, `speed.py`, `measurement_session.py`, `calibration.py`, `schemas.py`, `session.py`, `api.py` |
| Independent validation | `validation_models.py`, `validation.py`, `validation_api.py` | — |
| Backend tests | `test_assignment.py`, `test_tracking_reliability.py`, `test_tracking_benchmark.py`, `test_validation.py`, `test_validation_api.py`, `test_profiling.py`, `test_phase3_api.py` | `test_speed.py`, `test_phase2_api.py` |
| React validation | `ValidationBenchmarks.tsx`, `ValidationResults.tsx`, `TrackingBenchmarkResults.tsx`, `ValidationCharts.tsx`, `validationTypes.ts`, `validationApi.ts`, `validationPresentation.ts` | `App.tsx`, `styles.css` |
| Existing React diagnostics | `quality.css` | `SpeedPanel.tsx`, `Diagnostics.tsx`, `TrackTable.tsx`, `types.ts`, `Methodology.tsx` |
| Frontend tests/build | `ValidationBenchmarks.test.tsx`, `validationApi.test.ts`, `Diagnostics.test.tsx`, `TrackTable.test.tsx` | `App.test.tsx`, `SpeedPanel.test.tsx`, `vite.config.ts`, `package.json`, `package-lock.json` |
| Reproduction scripts | `benchmark_tracking.py`, `validate_dataset.py`, `profile_pipeline.py`, `profile_snapshot.py`, `profile_http.py` | — |
| Data/artifacts | `examples/validation/` (JSON/CSV synthetic input, actual example report, schema guide); `docs/benchmarks/` (baseline/comparison/performance reports); three Phase 3 screenshots | — |
| Documentation | `real_world_validation.md`, `measurement_quality.md`, `performance.md`, this file map | `README.md`, `architecture.md`, `testing.md`, `calibration.md`, `privacy.md`, `pyproject.toml` |

Backend names above are relative to `backend/roadlens/`, tests to
`backend/tests/`, React files to `frontend/src/`, scripts to `scripts/`, and
documentation to `docs/` unless a path is shown. `pyproject.toml` is at the root;
Vite and npm files are at `frontend/`.

[Actual verification](testing.md), [tracking results](benchmarks/tracking.md),
[synthetic validation results](../examples/validation/README.md) and
[Windows run/import/export instructions](../README.md) describe the final state.
No physical-camera or independent roadway accuracy result is claimed.
