# Small-dataset vehicle annotations

The annotation studio labels vehicles in an uploaded video with human-assigned identities. These identities are stored separately from the tracker's predicted IDs. A manually drawn box is an observation, not an independent reference-speed measurement. No plate, face or vehicle-owner identification is performed.

## Workflow

1. Upload a video in **Camera & video** and create a field session referencing that source in **Real-world validation**. Keep the complete recording/collection in one dataset partition. Select **Annotations** for that field session.
2. Navigate by the 1-based source-frame index, previous/next buttons, arrow keys outside text inputs, or an actual source timestamp. Timestamp navigation selects the nearest decoded presentation timestamp and displays the selected frame's actual timestamp. It does not establish a reference-event match or wall-clock synchronization.
3. Draw a vehicle box, enter a persistent manual identity such as `manual-vehicle-001`, and keep that label through subsequent visible frames. Drag a box to adjust its position and use its corner handle to resize it. Correct the identity label when an association was mistaken. Keep one category for each manual identity.
4. Mark temporary occlusion, partial visibility, entry and exit as appropriate. A fully occluded vehicle may retain its identity without a box. Mark every inspected frame **reviewed**, including an empty frame with no vehicles. Unreviewed frames remain outside the tracking evaluation.
5. Save incrementally. The revision number protects edits: if another tab saved first, the older save/import receives a conflict and leaves existing labels intact. Reload and compare edits before submitting a new revision. A field session whose source or coordinate geometry changes cannot silently reuse an earlier annotation document.
6. Optionally run offline model proposals for up to 100 consecutive frames using the baseline or improved tracker. Pause an active observation first. Predictions are separate overlays; they never create manual truth identities or mark frames reviewed. Running proposals again replaces the previous prediction run, retaining all manual objects and review flags. Export a snapshot before changing tracker/settings if a comparison must be preserved.
7. Export JSON for complete interchange or CSV for spreadsheet/Python analysis. Reimport expects the same field-session ID, stable source ID, coordinate geometry and current revision. To move labels deliberately to a newly created session for the identical source, export a blank document from the target and review the identity/geometry metadata before transferring frame records.

Offline navigation indexes at most 100,000 decoded frames and preserves actual PTS/time-base values without substituting a nominal FPS clock. An exact older frame can require decoding again from the beginning. At most three video navigators are cached. Images and model proposals are computed on request; no additional server or background service is started. Imported labels can be retained if their referenced video is unavailable; image navigation and source-timestamp verification then remain unavailable. When the local video is present, saves verify each ordinal frame and timestamp against that recording.

## Coordinate and identity contract

`geometry.coordinate_space` is either `source` or `undistorted`. Undistorted documents require the exact `intrinsic_profile_id`. Offline frames use the same full-frame OpenCV correction as live processing, with unchanged dimensions and `K_new = K`. Boxes are measured in those image pixels and must stay within the image. Rendered browser coordinates and road-plane metres are separate spaces. Gates and roadway profiles are never inferred from annotation boxes.

An annotation document has this structure:

```json
{
  "schema_version": 1,
  "field_session_id": "00000000-0000-4000-8000-000000000004",
  "source_id": "video:SHA256_OF_THE_RECORDING",
  "geometry": {"width": 640, "height": 480, "rotation": 0, "mirrored": false, "crop": null, "coordinate_space": "source", "intrinsic_profile_id": null},
  "revision": 0,
  "provenance": "synthetic",
  "frames": [{
    "index": 1,
    "timestamp_s": 0.0,
    "reviewed": true,
    "objects": [{"identity": "manual-vehicle-001", "category": "car", "bbox": [100, 100, 180, 180], "occluded": false, "partial_visibility": false, "entry": true, "exit": false}],
    "predictions": [{"predicted_track_id": 1, "category": "car", "bbox": [100, 100, 180, 180], "confidence": 0.8}]
  }],
  "proposal_metadata": null
}
```

Frame indices are unique. Manual identity strings and predicted integer IDs each must be unique within a frame. Boxes use `[x1, y1, x2, y2]` with positive area. `bbox: null` requires `occluded: true`. Timestamps may be null when the decoder genuinely provides none; invalid source timing remains visible and prevents automatic tracker proposals rather than creating a replacement clock. A proposal document records the inference settings, tracker, frame interval and elapsed component time in `proposal_metadata`.

The CSV header is fixed and includes `geometry_json` and `proposal_metadata_json` along with document metadata. Each frame has an explicit `record_type=frame` row, then zero or more `object` and `prediction` rows. This retains reviewed empty frames, fully occluded objects and all predictions. An empty document has a single `document` row. Boolean values are `true` and `false`. Formula-like text cells receive an apostrophe guard for spreadsheet safety; `escaped_text_fields_json` records exactly which cells were guarded so reimport restores them without altering legitimate apostrophe-prefixed labels. Import rejects inconsistent metadata, unknown record types, partial boxes and duplicate identities. JSON and CSV imports are limited to 8 MiB; documents to 10,000 frame records and 100,000 combined object/prediction observations.

When the field session includes an archived intrinsic profile, offline navigation validates and uses that exact archive. Deleting or replacing a currently saved lens profile cannot change the archive's image coordinates. A matching profile in the active store is required only when the field session contains no intrinsic archive.

## Tracking counts

Only reviewed frames are scored. When a proposal run is recorded, scoring is restricted to its frame interval; unprocessed frames cannot become invented misses. Visible manual boxes and same-category predictions are assigned globally using IoU greater than 0.5. Unmatched visible boxes are misses; unmatched predictions are false positives. An ID switch is a changed matched prediction ID for the same manual identity. A fragment is a matched identity that is visibly missed and then matched again. A full occlusion with no box does not create a miss or a fragment.

These counts depend on the correctness and completeness of manual review. They do not implement IDF1. IoU cannot disambiguate visually indistinguishable overlapping boxes, and sparsely reviewed frames cannot establish all errors in intervening footage. Retain the same reviewed frames and source geometry for a baseline/improved comparison and preserve both exports. Tracking counts establish no speed accuracy.

## Synthetic exercise

```powershell
.\.venv\Scripts\python.exe scripts/make_annotation_fixture.py
```

Upload `data\annotation_fixture\synthetic_annotations.avi`, create a matching field session and copy its UUID. Before adding labels to that session, regenerate only its annotation metadata:

```powershell
.\.venv\Scripts\python.exe scripts/make_annotation_fixture.py --field-session-id YOUR_FIELD_SESSION_UUID
```

Import `data\annotation_fixture\annotations.json` or `annotations.csv` in the annotation studio. The existing generated video is reused. The eight-frame exercise has scripted prediction IDs and deliberately includes a visible miss, false positive, ID switch, full occlusion, partial visibility and an unreviewed final frame. Its metric file reports four matched observations, one miss, one false positive, one ID switch and one fragment. These are deterministic synthetic examples, not actual detector output or field measurements. If the target session already has saved labels, compare its current export/revision first; import will not overwrite a newer revision silently.

API endpoints under `/api/field-sessions/{id}` are `GET/PUT /annotations`, `POST /annotations/import`, `GET /annotations/export?format=json|csv`, `GET /annotations/metrics`, `GET /frames?index=1`, `GET /frames?timestamp_s=0.3`, `GET /frames/image?index=1` and `POST /proposals`.
