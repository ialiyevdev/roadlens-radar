# RoadLens Radar v1.0.0

A local computer vision and traffic analytics workbench for Windows, with an
optional backend-free portfolio showcase. The full application runs CPU vehicle
detection, temporary tracking, calibrated gate-speed estimation, directional
counting, monitoring zones and evidence-based validation.

## Included

- FastAPI/OpenCV/YOLOX-S INT8 processing and a React/TypeScript workspace.
- Source-time measurement diagnostics, local study/traffic archives and exports.
- A ten-step guided tour with clearly labeled stored synthetic examples.
- A separate static showcase build and GitHub Pages Actions workflow that
  publishes only its generated files under `/roadlens-radar/`.
- Reproducible Windows setup, pinned dependency/build tooling, verified model
  download, source-only installation checks and attributed demonstration assets.
- Architecture, technical case study, benchmark methodology and release audit.

The final test/build/browser results are recorded in `docs/testing.md`.
`docs/performance.md` retains the separate historical benchmark workloads;
`docs/reproducibility.md` distinguishes local isolation from an external machine.

## Known limitations

- Real-world roadway speed and counting accuracy remain unverified. No physical
  camera, representative moving-road identity study or independent reference-speed
  device has been evaluated. This is not certified traffic enforcement equipment.
- CPU inference dominates processing cost. Short still-image replay timings do
  not establish end-to-end live throughput or field accuracy.
- Metric speed requires measured planar references, an unchanged camera/lens,
  approximate vehicle ground contact and reliable source time. Occlusion, ID
  changes, road grade and camera movement remain practical error sources.
- Intrinsics support pinhole models. There is no automatic camera-motion detection
  or appearance re-identification; long-video navigation and retained history
  have documented limits.
- The full API is intended for loopback use. Uploaded media and local archives
  are not automatically encrypted or removed.
- The static showcase performs no inference, uses stored examples and requires
  no Python API, webcam or local file permission. No redistributable moving-road
  demonstration clip is bundled; the photographic fixture is an attributed CC0 still.
- An external clean Windows installation and offline setup have not been tested.
  The Python suite retains an upstream Starlette/HTTPX deprecation warning.

First-party code retains MIT terms. Separately downloaded OpenCV Zoo weights
retain Apache-2.0 terms and notices. See `LICENSE`, `third_party/NOTICE.md` and
`examples/demo/manifest.json` before redistributing media or model assets.
