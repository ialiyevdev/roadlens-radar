# Reproducibility

Three scopes of evidence must remain separate:

| Scope | Meaning |
| --- | --- |
| Existing environment | Regression tests/builds in the developer checkout and its previously installed dependencies. |
| Isolated local source copy | A new source-only directory and virtual environment on this same Windows computer. Python/Node installations, package caches, network and operating system remain shared. |
| External clean machine | A separate Windows installation prepared from publicly available source and prerequisites. This has not been performed for Phase 6. |

## Isolated local smoke test

Run from the repository:

```powershell
.\scripts\smoke-install.ps1
```

The script creates a new timestamped directory under ignored `data/release-smoke/`. The directory name deliberately contains spaces. It copies the release source folders (`.github`, `backend`, `frontend`, `scripts`, `docs`, `examples`, `third_party`) and named root release files. It excludes existing environments, `node_modules`, generated builds, Python caches, environment files, logs, model weights and private runtime `data`. Symbolic links and junctions are skipped; ordinary OneDrive source files remain eligible. Git metadata is not copied.

The new directory must not already exist. The script never deletes the source checkout, an environment, or an earlier smoke result. A custom destination is supported:

```powershell
.\scripts\smoke-install.ps1 -DestinationDirectory 'C:\work\RoadLens smoke with spaces'
```

The default complete procedure:

1. Creates a fresh `.venv` and installs both pinned Python lock files and the editable project.
2. Runs `npm ci` from the copied package lock.
3. Downloads and verifies the pinned model; developer model weights are not copied.
4. Verifies that `roadlens` imports from the isolated copy and executes actual YOLOX inference on the attributed CC0 traffic **still image**.
5. Starts an actual Uvicorn server on a temporary loopback port, checks `/api/health`, imports the explicitly synthetic traffic example, and checks its six crossings/four scripted speeds (mean 28.5 km/h).
6. Stops only the Uvicorn process it started, then runs both full-application and static-showcase production builds.
7. Retains the isolated directory and `data/release-smoke.json`/`.log` inside it for inspection.

No camera, personal recording or independent roadway reference is involved. The actual model check confirms model execution on the known still; it is not a video throughput or roadway accuracy experiment.

`-PrepareOnly` makes the sanitized source copy without installation or checks. `-InstallOnly` installs and runs the API/model/example smoke while skipping both builds. These are partial checks and must be reported as such.

## External Windows checklist

For a separate computer, follow [setup](setup.md) using only the release source and ordinary public prerequisites:

- Confirm no `.venv`, `node_modules`, model weights, uploaded recordings or private settings were supplied.
- Run `setup.ps1 -CheckOnly`, then `setup.ps1` and retain install output.
- Run `test.ps1`, `build.ps1`, and `build.ps1 -Showcase`.
- Start both services, open the guided demo and navigate all ten stages without camera/file permissions.
- Load the synthetic traffic example and verify its explicit provenance label, six crossings and four scripted speed records.
- Serve the static showcase over HTTP with the Python backend stopped; check navigation, charts and asset paths.
- Record OS/interpreter/Node versions and actual failures. Do not reinterpret this procedure as field validation.

## Release verification record

The complete isolated smoke passed on **25 October 2026 (Europe/Riga)** using Python **3.13.9**, Node.js **24.16.0**, npm **11.16.0** and the corrected **setuptools 84.1.0** build pin. A new source directory containing spaces received fresh `.venv` and `node_modules` directories. Python wheels could use the computer's existing pip cache; no developer packages, runtime data or model file were copied. The model was downloaded anew and passed the pinned integrity check.

| Isolated check | Actual result |
| --- | --- |
| Pinned Python/build dependencies and editable project | Installed; `pip check` clean |
| Build helper | setuptools 84.1.0 installed; same exact pin in the lock and build-system metadata |
| Frontend lock installation | `npm ci` succeeded; audit reported zero vulnerabilities |
| Import location | Confirmed inside the new source copy |
| Actual detector on the original CC0 still | Executed; nine vehicle detections, without an accuracy claim |
| Actual Uvicorn startup and loopback health | Passed; model ready; owned server stopped afterward |
| Stored synthetic example through HTTP | Six crossings, four scripted speed records, mean 28.5 km/h |
| Full application TypeScript/production build | Passed, 77 transformed modules |
| Static showcase TypeScript/production build | Passed, 40 transformed modules, relative asset base |
| Portable source check inside the isolated copy | Passed, 300 candidate files, zero reported issues |
| External clean Windows machine | Not performed |

The retained final run is under `data/release-smoke/20261024-221454-215 isolated checkout`; the directory timestamp is UTC. Its API/model report is `data/release-smoke.json` inside that copy. This fresh installation supersedes the earlier successful run with the initial build-helper pin. The first copy attempt exposed OneDrive's reparse-point marking on ordinary source files; the copier was corrected to skip actual symbolic links/junctions, then installation was repeated successfully. Earlier attempts were preserved outside release source.

Full regression and browser verification are recorded separately in [testing](testing.md) and [release audit](release_audit.md). The isolated smoke does not claim to rerun the full test suite or establish an externally administered clean-machine result.
