# Portfolio demo guide

The full local application is the primary implementation. The guided tour and
optional static site explain it using **SYNTHETIC DEMONSTRATION** fixtures;
changing a step or source-frame slider does not run detection.

## Guided tour

1. Run setup and the two local servers as described in [setup](setup.md).
2. Open `http://127.0.0.1:5173/#showcase`, or choose **Guided showcase** in
   navigation / **Start guided demo** on the dashboard.
3. Use the numbered steps or **Previous** / **Next**. Keyboard users can tab to
   the controls; its step navigation group supports left/right arrows, Home and End.

| Step | What to inspect | Evidence boundary |
| --- | --- | --- |
| Vehicle detection | Boxes, source-frame scrubber, CPU model explanation | Known synthetic boxes; no active model |
| Multi-object tracking | Temporary IDs, trajectories and shared track table | Stored inputs; no physical identity study |
| Perspective calibration | Image/road coordinates and reference region | Known drawing geometry, separate from traffic fixture |
| Virtual speed gates | Two finite gates and interpolated source time | Synthetic geometry |
| Speed and diagnostics | Distance/time calculation and status meanings | 20 m / 1.2 s = 60 km/h is a software example |
| Directional counting | Finite counting line and direction | Stored generated trajectories |
| Vehicle classification | Shared chart and unknown class | Prescribed evidence, not class accuracy |
| Monitoring zones | Polygon, visible occupancy and observed dwell | Missing observations are not continuous occupancy |
| Traffic analytics | Native charts, six crossings, four scripted speeds | Stored synthetic exports |
| Validation and benchmarking | Separate historical workload reports | CPU still replay differs from scripted traffic timing |

**Open …** controls lead to real local workspace views; they do not automatically
start a source. Use those views to run inference, calibrate, edit counting regions
or evaluate a dataset. Stopping or resetting an observation does not delete saved
field or traffic archives.

## Interactive analytics without a recording

In **Traffic Intelligence**, choose **Load synthetic example**. Explore overview,
events, charts, comparison and exports. These application actions use the Python
API and the existing stored synthetic fixture. The guide does not label the
result as a physical observation or independent accuracy study.

For a generated-video counting workflow, stop the normal backend and run:

```powershell
.\.venv\Scripts\python.exe scripts\run_traffic_validation.py --port 8000
```

Keep the regular frontend running. Upload
`data/traffic_validation/SYNTHETIC_traffic_workflow.avi` through **Camera & video**.
This explicit harness substitutes a colored-marker detector; the normal backend
always uses YOLOX. Pause, draw a vertical counting line through x=320 across the
640×480 image, save, and resume. Two opposing scripted objects cross at about
4.833333 source seconds. It requires timely configuration before the crossings;
restart the generated recording if needed. This is a workflow exercise.

The separate 60 km/h gate harness and geometry procedure remain documented in
[calibration](calibration.md) and [testing](testing.md). Use the normal backend
again for actual model inference. No licensed moving-road demonstration clip is bundled.

## Static showcase

This optional build imports the same Showcase component, track table and native
traffic charts. Vite removes the normal application branch, so it needs no Python,
API, model weights, media upload, camera or file permissions. It does not emulate
live inference. Downloads are original bundled fixture/report files.

```powershell
Push-Location frontend
npm.cmd ci
npm.cmd run build:showcase -- --base=./
npm.cmd run preview:showcase
Pop-Location
```

Preview uses `http://127.0.0.1:4173`. Serve it over HTTP; opening `index.html`
directly with `file://` does not support module loading consistently.
Output: `frontend/dist-showcase`. The normal build remains `npm.cmd run build`
and outputs `frontend/dist`.

For a prospective GitHub Pages project site at `/roadlens-radar/`:

```powershell
Push-Location frontend
npm.cmd run build:showcase -- --base=/roadlens-radar/
npm.cmd run preview:showcase -- --base=/roadlens-radar/
Pop-Location
```

The prepared [GitHub Pages workflow](../.github/workflows/deploy-showcase.yml)
performs that build with Node 24.16.0 and `npm ci`, checks the static artifact, and
publishes **only** `frontend/dist-showcase` using the official Pages actions.
It runs on pushes to `main` and manual dispatch. The repository owner must first
select **GitHub Actions** in **Settings → Pages** and satisfy any `github-pages`
environment approvals. Follow the [publication guide](github_publication.md) for
review, source push, confirmed URLs, tag and release commands.

For that project-base build, open `http://127.0.0.1:4173/roadlens-radar/` when
previewing locally. The earlier relative build uses the preview server's root.

The build's packaging hook preserves three reviewed screenshots under
`screenshots/` and nine license/provenance files under `notices/`. For example,
append `screenshots/phase6-showcase.png` to the confirmed project-site URL;
`screenshots/phase6-showcase-mobile.png` and `screenshots/phase6-dashboard.png`
are included too. These are the original application captures, not live output.
The UI is unchanged. To run the same artifact check locally from the repository:

```powershell
node scripts/check_showcase.mjs --directory frontend/dist-showcase --base /roadlens-radar/
```

Static step navigation needs no SPA server rewrite. Relative base `./` also
supports nested static folders. Do not deploy the full local API, `data/`, model
cache, environment or uploaded recordings. The local preparation has not created
a repository, public hosting resource or external deployment.

## Presenting the engineering work

Start with the guided tour, then show the actual local workspace and
[case study](case_study.md). Explain source timestamps, geometry compatibility,
finite crossings and evidence exclusions. Keep the [performance workloads](performance.md)
separate. End with the outstanding need for independent field references,
representative held-out footage and physical camera/timing verification.

Asset rights and the process for adding permitted footage are in the
[demo manifest guide](../examples/demo/README.md).
