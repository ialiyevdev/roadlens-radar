# Local observation and data handling

The Phase 6 static showcase contains only reviewed stored synthetic data and
historical numerical reports. It makes no API requests and requests no camera
or file permissions. The guided tour in the full application uses the same data;
the surrounding local workspace still polls its loopback API. The release's
demo manifest records asset sources, licenses and physical ground-truth limits.

RoadLens binds to loopback and uses no external inference service, audio input,
plate recognition, facial recognition, owner identification or cross-session
identity matching. The selected vehicle classes are the only detections sent to
the frontend. A browser session does not automatically open a camera.

Camera frames are processed in memory and are not recorded. JPEG previews are
sent only to the local interface. Session IDs, trajectories and counters are
temporary. Reset clears the current session. User-selected recorded inputs are
copied to `data/uploads` for analysis; that directory is ignored by Git and must
not be published. Stop the backend before manually deleting local uploaded files.
No browser-accessible public stream or hosting is configured.

Calibration reference coordinates, named profiles and gate configurations are
saved locally in `data/calibrations`. Frozen calibration frames remain in memory
only, with at most three per session; start/reset removes them. Profile deletion
removes its JSON file and disables it if active. Source hashes associate uploaded
content with geometry; they do not identify vehicles or people. The optional
synthetic harness keeps its generated video, profiles and uploads separately in
`data/validation`.

Phase 3 validation CSV/JSON files are parsed in memory and are not retained by the
server. The browser keeps selected datasets until reload. Explicit downloads
contain anonymous event/track IDs, speeds, declared reference methods and
numerical diagnostics. Measurement exports include bounded coordinate samples
and original calibration geometry, not image/video pixels or source filenames.
Review user-supplied dataset text before sharing it; the application cannot know
whether notes contain personal information. Bundled evidence uses generated
inputs or actual-model replay of an attributed CC0 still; none is a physical
roadway validation study.

Phase 4 field records persist locally in `data/field_sessions`, manual annotations
in `data/annotations`, intrinsic profiles in `data/camera_profiles`, and source
metadata in `data/uploads/.catalog.json`. Field records include timestamps,
environment/camera notes, relative recording links, hashes, independent-reference
events, explicit matches, synchronization anchors and archived measurement and
calibration evidence. Resetting the live observation does not delete these records.
Deleting a field session deletes its annotations and metadata, while keeping the
source video. Intrinsic calibration images are processed in memory; profile
diagnostics retain supplied image basenames/hashes and numerical fit results.

Annotation exports contain frame timestamps, boxes, manual truth labels and
predicted IDs, without source pixels. Field-session exports retain relative source
links and original study evidence; report exports omit those paths and pixels.
Notes, labels, timestamps, image names and coordinates may still disclose a
location or other information supplied by the author. Review exports before sharing.
CSV text is escaped for spreadsheets; annotation interchange records escaped
fields so reimport restores labels exactly. Local files and downloads are not
automatically encrypted, uploaded or removed by the application. Choose retention
appropriate to the study and stop the backend before manually removing recordings.

Phase 5 stores traffic observations in `data/traffic/sessions` and source/geometry
configurations in `data/traffic/configurations`. Completed observations archive
automatically; explicit archive requests save the current snapshot. Records
include temporary IDs, class evidence, counting lines/zones, event source times,
coverage, occupancy, timing diagnostics, camera/calibration metadata and existing
speed results. These are additional persistent local records: resetting the live
observation does not delete archives or counting definitions. No raw pixels or
automatically recorded webcam footage are included in traffic archives.

Traffic CSV/JSON exports include selected source/session identifiers, filters,
units and provenance. A hash associates an uploaded recording, not a person.
Anonymous labels, region coordinates, dates and author-supplied notes may still
disclose location or study details. Review them before publishing. The explicit
synthetic browser harness keeps its generated clip, uploads, field labels and
traffic records separately under ignored `data/traffic_validation`. Its marker
detector is never selected by the normal application entry point.

A fixed-camera public-road setup needs a privacy review before observing a
public road. Applicability depends on location, purpose, scope, storage and
whether identifiable personal data is processed. Operating from a private
residence does not by itself settle whether ongoing public-road monitoring is
permitted. This project makes no determination of the user's legal position.

Start with controlled tests and footage whose license permits the intended use.
Avoid exposing private property or identifiable people, plates and locations in
screenshots, repository files or demonstrations. Do not use the application to
issue fines or represent estimates as legally admissible speed evidence.
