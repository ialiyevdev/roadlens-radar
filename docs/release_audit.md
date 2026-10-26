# Release audit

Audit date: **26 October 2026**; Phase 6 audit retained below. Scope: current candidate source, dependency
manifests, bundled examples/screenshots and local API behavior. This checkout
has no commits on `main`, no tracked/staged files and no configured remote.
Two local Codex tree references were also inspected: zero reachable commits and
302 snapshot blobs, with no prohibited asset names or credential/home-path
patterns found. These tool snapshots are separate from the publication branch;
the proposed commands push only `main` and `v1.0.0`. No Git history was rewritten.
No source, recording, site or release was published.

## Final publication review

The official [GitHub Pages workflow](../.github/workflows/deploy-showcase.yml)
uses a locked frontend installation and the existing standalone build with
base `/roadlens-radar/`. Only `frontend/dist-showcase` is uploaded. The live
frontend and Python API retain their local configuration. Action references
are pinned to upstream commit IDs and deployment permissions are scoped to
the deploy job. Pages must be selected manually in GitHub settings.

The existing static build omitted the full React, React DOM and scheduler MIT
license texts. Release packaging now copies their installed upstream notices,
the RoadLens MIT terms, existing model/CC0 notices and only three manifest-reviewed
screenshots into the artifact. The checker rejects the full-app bundle, backend
calls, unexpected artifact paths, symbolic/hard links and missing or altered screenshots.
No product features or UI design changed.

The candidate source excludes environment files, caches, model weights and
recordings. The 27 existing PNG screenshots contained no text/EXIF chunks; the
CC0 JPEG had only JFIF metadata, with no EXIF/XMP or GPS fields. The public
photographer attribution is retained for provenance. Git author identity is
a manual publication choice; configured identity values were not copied into
reports or changed by this task.

Current test/build/browser results are in [testing](testing.md). Repository and
live-site links remain explicitly pending in the README until real URLs exist.
The [publication guide](github_publication.md) supplies the description, topics,
Git commands, Pages settings and final approval checklist. The source is ready
for the user's publication action; GitHub-hosted execution remains unperformed.

## Findings and resolutions

| Finding | Resolution / evidence |
| --- | --- |
| README assumed an existing developer environment and accumulated five phases of instructions | Replaced with a concise landing page; linked method/workflow guides and added setup/demo/release guides |
| No camera-free introduction or static build | Added shared ten-step Guided showcase; stored synthetic fixtures and actual historical reports, no simulated inference |
| Absolute model path in local health payload | Health now exposes the model basename and software version; regression test checks relocation and no source opening |
| One historical Phase 3 timing row contained Phase 5 tracker numbers | Restored **0.4496 / 1.7015 ms mean/P95** from unchanged `pipeline_profile.json`; retained distinct Phase 5 timings |
| Setup/build helper selection was partly unpinned | Added pinned build tooling, checked Python/Node versions, `npm ci`, explicit command failures and checksum-verified model setup |
| Expanded advisory scan found two issues in the initial setuptools 80.9.0 build pin | Raised only the build helper to 84.1.0 and repeated advisory/install verification; runtime/dev lock retained |
| The old Python 3.11 claim conflicted with pinned NumPy 2.5.4 metadata | Setup/project support now states Python 3.12–3.13; existing tested lock retained without an unverified downgrade |
| Source-only smoke copy initially skipped hydrated OneDrive files | Filter now excludes actual symbolic links/junctions rather than all reparse points; fresh isolated installation passed |
| Byte-hashed JSON fixtures could change with Git line endings | Added `.gitattributes`; manifest JSON inputs use LF without changing numerical data or raw timestamps |
| New static output and environment variants needed ignore coverage | Extended `.gitignore` for `dist-showcase`, environment variants, environment files and common cache outputs |
| No consolidated media rights inventory | Added [hashed demo manifest](../examples/demo/manifest.json) and [addition process](../examples/demo/README.md) |
| Large local QA/media files exist | Preserved under ignored `data/`; they are not release source. No unclear asset was deleted |
| No eligible redistributable moving-road clip | Kept generated examples and attributed CC0 still; did not download unrelated footage |
| Historical guides retained a personal window/floor setup description | Generalized to an elevated fixed-camera procedure while retaining technical guidance |

The initial source inventory contained **266 candidate files / 5,603,358 bytes**,
including **24 screenshots / 3,238,994 bytes**. The largest candidate was a 514 KB
application screenshot; no video or model binary was a Git candidate. The ignored
development `data/` directory then held about **85 MB** of fixtures/QA artifacts;
later isolated-install/tool environments add ignored local files. No mass cleanup
was needed for a source release. Historical screenshots/reports are linked by
phase guides and retained as reproducibility evidence.

The baseline tracker is deliberately retained for comparison; test adapters,
fixture generators and benchmark modules have explicit reproduction uses. The
dependency set remains the existing FastAPI/OpenCV/NumPy/PyAV/React stack. No new
runtime library or external service was added. Optional audit tooling was installed
in an ignored separate environment, not the application environment.

## Security and privacy review

- Candidate text scanning found **no developer home paths, private-key markers or
  obvious credential assignments**. No root `.env` file was present. Pattern scans
  are limited; review the staged diff before publication. No secret values are
  copied into reports or scan output.
- The API binds to loopback in launch scripts and validates Host/Origin and
  cross-site browser access. It is not an authenticated public inference service.
  The full API must not be exposed by static hosting.
- Uploads accept a bounded set of video extensions, cap content at 256 MB,
  verify actual decoding, use generated storage names and remove failed files.
  The original filename is reduced to a printable basename. Local video IDs are
  opaque; catalog/field paths are constrained to relative contained paths.
- Local errors are displayed as text by React. Production responses do not expose
  debug tracebacks. Source-related diagnostic text and user-entered study notes
  can still contain identifying context; review exports before sharing.
- Camera frames are processed in memory, not automatically recorded. Uploaded
  files, calibration profiles, annotations, study metadata and traffic archives
  persist under ignored `data/`; reset does not delete saved archives. No plate,
  face, owner identification or new collection feature was added.
- The static showcase bundles only reviewed stored JSON inputs/reports. It needs
  no API, model, camera or local user file. Build output is separate from local
  study data and is ignored until explicitly chosen for hosting.

`npm audit` reported **0 vulnerabilities**. `pip check` reported **no broken
requirements**. The first **pip-audit 2.9.0** run found no advisories in the
runtime/dev lock. Extending it to the build lock found two advisories in the
initial setuptools 80.9.0 pin: [Windows legacy wheel path handling](https://github.com/pypa/setuptools/security/advisories/GHSA-xmj3-9gf7-h52w)
and [macOS Unicode exclusion handling](https://github.com/pypa/setuptools/security/advisories/GHSA-h35f-9h28-mq5c).
The build helper and build-system requirement were deliberately pinned to
**84.1.0**, followed by another combined advisory scan and isolated installation.
The final combined scan checked **28 packages** with **zero known vulnerabilities**,
using the PyPI advisory service (`--no-deps --disable-pip`); the
[dependency record](verification/phase6-dependencies.json) retains the scope.
The lock is
fully version-pinned but not wheel-hashed; this audit does not replace artifact
integrity review or cover undisclosed vulnerabilities. Model bytes have their
own exact SHA-256 and size check. Application runtime/dev dependencies were not
upgraded; the build-helper change addresses the observed audit findings.

## Licensing

Existing first-party [MIT terms](../LICENSE) are preserved. The pinned OpenCV Zoo
model directory explicitly applies **Apache-2.0** to all its files. Its upstream
license content was compared with the included copy after normalizing line
endings and matched. Retain the [license and notices](../third_party/NOTICE.md)
when distributing weights; setup downloads them separately.

The one photographic inference fixture is an attributed CC0 image. Generated
examples have known software truth, not independently collected physical truth.
No rights are asserted over unrelated media or third-party dependencies. The
manifest separates source, author, redistribution status and ground-truth status.

## Repeatable checks and remaining review

```powershell
.\.venv\Scripts\python.exe scripts\check_release.py
.\.venv\Scripts\python.exe -m pytest backend\tests\test_demo_manifest.py backend\tests\test_release.py backend\tests\test_windows_release_scripts.py
Push-Location frontend
npm.cmd audit
Pop-Location
```

The source check resolves local Markdown file links inside the release, checks
version agreement and reports sensitive-pattern categories without matching
values. It does not crawl external URLs or validate every Markdown heading anchor.
The manifest tests verify reviewed asset hashes/rights metadata; full checks and
browser evidence are recorded in [testing](testing.md).

Publication still requires the user's choice of account/repository/visibility,
review of ownership and staged public content, and explicit authorization for
push/tag/release/hosting. Independent field validation and external clean-machine
verification remain separate future work. See the [release checklist](release_notes.md).
