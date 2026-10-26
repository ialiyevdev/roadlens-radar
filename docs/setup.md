# Windows setup

RoadLens runs locally on Windows 11. Install 64-bit **Python 3.12–3.13** and **Node.js 22.12 or newer with npm**, then reopen PowerShell. The release lock was exercised with Python 3.13.9 and Node.js 24.16.0; Python 3.12 has not been separately installed for this release. The pinned NumPy 2.5.4 requires Python 3.12 or newer. Docker, WSL, databases, credentials and a GPU are unnecessary.

From a downloaded or cloned source directory:

```powershell
Set-Location 'C:\work\RoadLens Radar'
.\scripts\setup.ps1
```

If Windows blocks local unsigned scripts, allow scripts for this PowerShell process only with `Set-ExecutionPolicy -Scope Process Bypass`, then rerun the command. No administrator shell is needed.

Setup finds Python through `py -3.13`, `py -3.12`, then `python.exe`. To choose an executable or a different environment directory:

```powershell
.\scripts\setup.ps1 -Python 'C:\Program Files\Python313\python.exe' -VenvPath '.venv-release'
```

`-CheckOnly` checks Python, Node and npm without installing anything. All relative environment paths resolve against the repository, including when a script is launched from another working directory. A pre-existing Python environment is reused; an existing directory that is not an environment causes an error and is preserved.

Setup installs **setuptools 84.1.0**, pinned consistently in `requirements-build.lock` and `pyproject.toml`, the exact runtime/test versions in `requirements-dev.lock`, and the local package with `--no-build-isolation --no-deps`. Frontend installation uses `npm ci` and the committed package lock. npm may replace an existing `node_modules` directory as part of its normal clean installation.

The model is downloaded from the pinned OpenCV Zoo revision into `models/vehicle_detector.onnx`. The downloader verifies its 9,744,418-byte size and SHA-256; a verified existing copy is reused. An existing mismatched file is rejected, rather than overwritten. Preserve it elsewhere before retrying. See [model provenance and license](model.md).

## Run the application

Use two PowerShell windows in the repository directory:

```powershell
# Window 1
.\scripts\start-backend.ps1
```

```powershell
# Window 2
.\scripts\start-frontend.ps1
```

Open **http://127.0.0.1:5173**. The backend listens at **http://127.0.0.1:8000**. Press Ctrl+C in each window to stop it. With a custom environment, pass the same `-VenvPath` to backend and test scripts. Frontend startup does not need Python environment activation.

The guided demonstration uses stored synthetic data and requires no camera. It does not start model inference. The full observation workflow accepts a camera or a user-supplied stationary-camera recording after an explicit source selection.

## Verify and build

```powershell
.\scripts\test.ps1
.\scripts\test.ps1 -BackendOnly
.\scripts\test.ps1 -FrontendOnly
.\scripts\build.ps1
.\scripts\build.ps1 -Showcase
```

Backend test runs also check portable release source, version consistency and local Markdown links with `scripts/check_release.py`. The standard build runs TypeScript checks and writes `frontend/dist`. The optional backend-free showcase writes `frontend/dist-showcase`; both directories are generated artifacts. A project hosting path can be supplied with `-Showcase -Base '/roadlens-radar/'`; the default `./` uses relative asset paths. Building does not publish anything.

Equivalent dependency checks:

```powershell
.\.venv\Scripts\python.exe -m pip check
Push-Location frontend
npm.cmd audit
Pop-Location
```

For independent source-copy installation, use [the reproducibility procedure](reproducibility.md). Model downloading and dependency installation require network access. The app itself uses local processing and storage.

## Troubleshooting

| Symptom | Action |
| --- | --- |
| Unsupported Python or Node version | Install a supported version, reopen PowerShell and rerun `setup.ps1 -CheckOnly`. |
| Python launcher chooses the wrong installation | Pass `-Python` with the full path to the desired executable. |
| Environment exists but is invalid | Choose a new `-VenvPath`; setup deliberately does not delete the existing directory. |
| Dependency download fails | Check connectivity and package-index/proxy policy, then rerun setup. The locks are retained unchanged. |
| Model verification fails | Preserve the mismatched file outside its expected path, then run setup again. Do not disable integrity checking. |
| Port 8000 or 5173 is in use | Stop the process already using that port, then retry. Vite refuses to silently choose another port. |
| Dashboard cannot reach the backend | Start the backend in the first window and confirm `http://127.0.0.1:8000/api/health` responds. |

The API binds to loopback and accepts local dashboard origins. These scripts do not configure a public inference server.
