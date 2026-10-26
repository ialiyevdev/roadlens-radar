# Changelog

## 1.0.0 — ready for publication, 26 October 2026

Final publication preparation, 26 October 2026:

- Added the official GitHub Pages Actions workflow for the standalone showcase,
  with locked installation, repository asset base and a static-only artifact check.
- Included reviewed screenshots and complete runtime licenses in static output.
- Added first-publication instructions, repository metadata suggestions and
  clearly pending public link locations. No public deployment was performed.

- Added a ten-step guided showcase using stored synthetic inputs and shared
  workspace charts/table, with accessible navigation and links to the actual tools.
- Added an optional backend-free static showcase with relative deployment paths.
- Added Windows setup/start/test/build and source-only isolated-install scripts,
  pinned build tooling, model integrity checks and release regression checks.
- Pinned setuptools 84.1.0 for packaging after the expanded build-tool advisory
  scan found two issues in the initial 80.9.0 selection; runtime locks are unchanged.
- Reworked the README, architecture and technical case study; added a demo asset
  manifest, release audit, reproducibility record, demo guide and publication checklist.
- Retained the Phase 1–5 measurement/traffic functionality and existing evidence.
- Removed the absolute model path from the health response; added software version.
- Corrected the historical Phase 3 tracker timing table against its original raw
  report (0.4496 ms mean / 1.7015 ms P95). No benchmark was retroactively changed.

This is a prepared local release candidate, not a published release. Real-world
speed/counting accuracy and physical camera behavior remain unverified.

## 0.5.0 — Phase 5

Directional counting, stable classes, monitoring zones, coverage-based analytics,
traffic archives/exports and reviewed-annotation counting evaluation.
[Implementation record](docs/phase5_changes.md)

## 0.4.0 — Phase 4

Field sessions, optional camera intrinsics, annotations, explicit independent
reference matching/alignment and held-out evaluation.
[Implementation record](docs/phase4_changes.md)

## 0.3.0 — Phase 3

Global association, separate tracker benchmarks, speed-reference evaluation,
diagnostics and numerical exports. [Implementation record](docs/phase3_changes.md)

## 0.2.0 — Phase 2

Measured road-plane calibration, finite virtual gates and source-time speed
estimation. [Methods](docs/calibration.md)

## 0.1.0 — Phase 1

Local camera/video acquisition, CPU vehicle detection, session-scoped tracking,
JPEG/MJPEG preview and runtime diagnostics.
