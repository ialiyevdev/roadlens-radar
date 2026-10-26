# Demonstration asset manifest

[`manifest.json`](manifest.json) identifies the small inputs used by the guided/static showcase, the separate positive-inference fixture and three actual release screenshots. Every path is relative to the repository root; SHA-256 and byte length identify the reviewed bytes. JSON assets use LF line endings, enforced by `.gitattributes`, so checksums survive a fresh Git checkout. No camera, personal recording or redistributable moving real-traffic video is bundled.

The showcase imports the existing generated trajectories, persisted traffic artifact and analytics exports at build time. Its observations are labeled **SYNTHETIC DEMONSTRATION** and are stored outputs, not active detector inference. Four scripted valid speeds average 28.5 km/h; they exercise status filtering and arithmetic. They are not independently measured speeds. The three benchmark reports have different workloads: scripted counting, scripted 32-track processing, and actual model inference on a repeated licensed still with synthetic counting regions. None provides physical speed or counting ground truth.

The CC0 photograph is retained for the real detector's smoke/profile checks. It is a recorded still, not video. It has no independent vehicle labels and is not required to run the static showcase. The pinned model is downloaded separately under the terms documented in [model provenance](../../docs/model.md) and [third-party notices](../../third_party/NOTICE.md); it is not a bundled demo asset.

The two Phase 6 showcase screenshots display synthetic stored data. The Phase 6 dashboard screenshot displays actual detector predictions on a replayed CC0 still. Its interface retains the first-party MIT terms and its photograph retains CC0 terms; the screenshot is not a moving-road accuracy result.

## Reproduce or review

From the repository root after setup:

```powershell
.\.venv\Scripts\python.exe scripts\make_traffic_fixture.py
.\.venv\Scripts\python.exe scripts\benchmark_traffic.py --repetitions 30 --output docs\benchmarks\phase5-counting.json
.\.venv\Scripts\python.exe scripts\profile_traffic.py --repetitions 30 --output docs\benchmarks\phase5-performance.json
.\.venv\Scripts\python.exe scripts\profile_traffic_pipeline.py --frames 12 --input-size 640 --output docs\benchmarks\phase5-model-performance.json
.\.venv\Scripts\python.exe -m pytest backend\tests\test_demo_manifest.py
```

Regenerating reports changes timestamps and local timing samples; it does not reproduce the original timings byte for byte. Review the new evidence, then deliberately update each affected manifest entry's `bytes` and `sha256` using `Get-Item` and `Get-FileHash -Algorithm SHA256`. Keep original evidence when a comparison matters. Tests reject missing/changed assets and unsafe or absolute paths. The complete traffic example includes companion CSV exports described in [its README](../traffic/README.md); the manifest lists the JSON inputs actually used by the showcase.

## Adding real footage later

1. Obtain an original source and an explicit license/permission that covers redistribution. Record the provider, exact source, license version, required credit and any restrictions. Online availability alone is insufficient.
2. Review visible people, plates, location, recording metadata and any audio. Obtain appropriate consent/rights and minimize identifying material before considering publication. Keep unreviewed originals in ignored local storage.
3. Add only a small reviewed clip, retain its license/notice and record its hash, size and recording provenance in the manifest. Mark independent ground truth unavailable unless a separate documented reference was actually collected.
4. Keep the recording and any declared near-duplicates in one evaluation partition. Document frame timing, calibration, manual review and reference alignment separately. Update the showcase label and tests to match the evidence; a recorded clip alone is not a validated metric-speed dataset.

Do not add generated video as recorded roadway evidence. The optional clips from `make_traffic_fixture.py` and the explicit validation harnesses contain generated shapes; YOLOX detection of those shapes is not implied.
