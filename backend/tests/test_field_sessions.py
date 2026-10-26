"""Synthetic field metadata, persistence, explicit alignment and split protections."""

import json
from pathlib import Path

import pytest
from pydantic import ValidationError

from roadlens.field_alignment import eligibility, import_references, match_diagnostics, synchronization
from roadlens.field_models import FieldSessionInput, ReferenceEvent, SyncConfig
from roadlens.field_store import FieldStore, assert_partitions, session_input


EXAMPLES = Path(__file__).resolve().parents[2] / "examples" / "field"


@pytest.fixture
def data():
    return FieldSessionInput.model_validate_json((EXAMPLES / "synthetic_field_session.json").read_text(encoding="utf-8"))


@pytest.fixture
def store(tmp_path):
    return FieldStore(tmp_path / "sessions")


def test_atomic_round_trip_preserves_statuses_and_relative_references(store, data):
    data.source.relative_path = "uploads/anonymous-video.mp4"
    created = store.put(data)
    loaded = FieldStore(store.directory).get(created.id)
    assert loaded.model_dump() == created.model_dump()
    assert loaded.source.relative_path == "uploads/anonymous-video.mp4"
    assert [m.measurement.status for m in loaded.measurements] == [m.measurement.status for m in data.measurements]
    assert loaded.sync_diagnostics.status == "aligned"
    assert len(list(store.directory.glob("*.json"))) == 1
    assert not list(store.directory.glob("*.tmp"))
    assert not list(store.directory.glob("*.mp4"))


def test_update_delete_and_unknown_identifier(store, data):
    created = store.put(data)
    data.name = "Updated observation"
    updated = store.put(data, created.id)
    assert updated.id == created.id and updated.created_at == created.created_at
    assert updated.updated_at >= created.updated_at
    assert store.list()[0].name == "Updated observation"
    store.delete(created.id)
    assert store.list() == []
    with pytest.raises(KeyError):
        store.get(created.id)
    with pytest.raises(KeyError):
        store.get("../../secrets")


@pytest.mark.parametrize("change", ["source", "geometry", "intrinsic", "zoom"])
def test_camera_changes_invalidate_archived_geometry_without_rewriting_measurements(store, data, change):
    before = store.put(data)
    if change == "source":
        data.source.source_id = "new-source"
    elif change == "geometry":
        data.camera.geometry.width = 1280
    elif change == "intrinsic":
        data.camera.intrinsic_profile_id = "different-camera-model"
        data.camera.geometry.intrinsic_profile_id = "different-camera-model"
        data.camera.geometry.coordinate_space = "undistorted"
    else:
        data.camera.zoom = "2x"
    after = store.put(data, before.id)
    assert after.calibration_id is None and after.gates is None
    assert not after.calibration_compatible and after.configuration_warnings
    assert after.measurements == before.measurements
    assert not match_diagnostics(after, "event-001")["eligible"]


@pytest.mark.parametrize("path", ["../video.mp4", "uploads/../../video.mp4", "C:/private/video.mp4", "/tmp/video.mp4", "\\\\server\\share\\video.mp4"])
def test_source_paths_are_portable_and_contained(data, path):
    raw = data.model_dump()
    raw["source"]["relative_path"] = path
    with pytest.raises(ValidationError, match="relative"):
        FieldSessionInput.model_validate(raw)


@pytest.mark.parametrize("value", [float("nan"), float("inf"), float("-inf")])
def test_nonfinite_nested_timing_metadata_is_rejected(data, value):
    raw = data.model_dump()
    raw["timing_summary"] = {"latency": {"samples": [value]}}
    with pytest.raises(ValidationError, match="finite"):
        FieldSessionInput.model_validate(raw)


@pytest.mark.parametrize("field,value", [("started_at", "2026-10-24T09:00:00"), ("ended_at", "2026-10-23T09:00:00Z")])
def test_wallclock_metadata_needs_zone_and_order(data, field, value):
    raw = data.model_dump(mode="json")
    raw[field] = value
    with pytest.raises(ValidationError):
        FieldSessionInput.model_validate(raw)


def test_measurement_event_variant_and_reference_ids_are_unique(data):
    raw = data.model_dump()
    raw["measurements"].append(raw["measurements"][0])
    with pytest.raises(ValidationError, match="unique"):
        FieldSessionInput.model_validate(raw)
    raw = data.model_dump()
    raw["reference_events"].append(raw["reference_events"][0])
    with pytest.raises(ValidationError, match="unique"):
        FieldSessionInput.model_validate(raw)


def test_explicit_matching_rejects_foreign_events_and_double_assignment(data):
    raw = data.model_dump()
    raw["matches"][0]["event_id"] = "missing-event"
    with pytest.raises(ValidationError, match="retained measurement"):
        FieldSessionInput.model_validate(raw)
    raw = data.model_dump()
    raw["matches"][1]["reference_id"] = raw["matches"][0]["reference_id"]
    with pytest.raises(ValidationError, match="multiple vehicle"):
        FieldSessionInput.model_validate(raw)


@pytest.mark.parametrize("group", ["source_id", "content_sha256", "collection_id", "near_duplicate_group"])
def test_whole_recording_and_near_duplicate_groups_do_not_cross_partitions(store, data, group):
    if group == "near_duplicate_group":
        data.source.near_duplicate_group = "same-scene"
    first = store.put(data)
    second = data.model_copy(deep=True)
    second.source.source_id = "different-source"
    second.source.content_sha256 = "a" * 64
    second.source.collection_id = "different-collection"
    second.source.near_duplicate_group = "different-scene"
    setattr(second.source, group, getattr(data.source, group))
    second.partition = "development"
    # Even disjoint cropped segments remain grouped at recording level.
    second.source.segment_start_s, second.source.segment_end_s = 200, 300
    with pytest.raises(ValueError, match="split leakage"):
        store.put(second)
    assert len(store.list()) == 1
    assert store.get(first.id).partition == "held_out"


def test_same_partition_can_retain_variants_and_evaluation_rechecks_tampering(store, data):
    first = store.put(data)
    second = store.put(data)
    second.partition = "development"
    with pytest.raises(ValueError, match="split leakage"):
        assert_partitions([first, second])


def test_store_revalidates_unsafe_model_copy_updates(store, data):
    unsafe = data.model_copy(update={"expected_event_count": 1})
    with pytest.raises(ValidationError, match="Expected event count"):
        store.put(unsafe)


def test_import_reference_csv_and_json_convert_units_exactly():
    csv_data = b"id,timestamp_s,speed,units,method,provenance,independent\nr1,2,10,m/s,Checked radar,independent_reference,true\nr2,3,50,mph,Checked radar,independent_reference,true\n"
    refs = import_references(csv_data, "events.csv")
    assert refs[0].speed_kmh == 36
    assert refs[1].speed_kmh == pytest.approx(80.4672)
    imported = import_references(json.dumps({"reference_events": [r.model_dump() for r in refs]}).encode(), "events.json")
    assert imported == refs


@pytest.mark.parametrize("payload", [
    b"id,timestamp_s,speed,units,method,provenance,independent\nr,0,30,knots,radar,independent_reference,true\n",
    b"id,timestamp_s,speed,units,method,provenance,independent\nr,0,30,km/h,RoadLens estimate,independent_reference,true\n",
    b"id,timestamp_s,speed,units,method,provenance,independent\nr,0,nan,km/h,radar,independent_reference,true\n",
    b"id,timestamp_s,speed,units,method,provenance,independent\nr,0,30,km/h,radar,independent_reference,maybe\n",
    b"id,id,timestamp_s,speed,units,method,provenance,independent\nr,r,0,30,km/h,radar,independent_reference,true\n",
])
def test_invalid_reference_imports_fail_without_coercing_quality(payload):
    with pytest.raises(ValueError):
        import_references(payload, "events.csv")


def test_duplicate_and_oversized_reference_imports_fail():
    ref = {"id": "r", "timestamp_s": 0, "speed": 30, "units": "km/h", "method": "Checked radar"}
    with pytest.raises(ValueError, match="unique"):
        import_references(json.dumps([ref, ref]).encode(), "events.json")
    with pytest.raises(ValueError, match="8 MiB"):
        import_references(b" " * (8 * 1024 * 1024 + 1), "events.json")


def test_manual_uncertain_offset_does_not_become_confirmed(data):
    config = SyncConfig(source_clock="PTS seconds", reference_clock="Device clock", offset_s=-100, uncertainty_s=.01)
    diagnosis = synchronization(config)
    assert diagnosis.status == "uncertain" and diagnosis.scale == 1
    config.anchors = [data.sync.anchors[0]]
    assert synchronization(config).status == "uncertain"


def test_drift_fit_recovers_known_clock_relationship_with_residuals():
    config = SyncConfig(source_clock="PTS", reference_clock="Device", fit_drift=True, uncertainty_s=.001,
                        anchors=[{"reference_timestamp_s": 100, "source_timestamp_s": 10.01, "independent": True, "uncertainty_s": .001},
                                 {"reference_timestamp_s": 200, "source_timestamp_s": 110.02, "independent": True, "uncertainty_s": .001},
                                 {"reference_timestamp_s": 300, "source_timestamp_s": 210.03, "independent": True, "uncertainty_s": .001}])
    diagnosis = synchronization(config)
    assert diagnosis.scale == pytest.approx(1.0001)
    assert diagnosis.offset_s == pytest.approx(-90)
    assert diagnosis.drift_ppm == pytest.approx(100)
    assert diagnosis.maximum_residual_s < 1e-10
    assert diagnosis.status == "aligned"


def test_drift_fit_needs_multiple_distinct_independent_anchors(data):
    raw = data.sync.model_dump()
    raw["anchors"] = raw["anchors"][:1]
    with pytest.raises(ValidationError, match="at least two"):
        SyncConfig.model_validate(raw)
    raw = data.sync.model_dump()
    raw["anchors"][1]["independent"] = False
    with pytest.raises(ValidationError, match="independent"):
        SyncConfig.model_validate(raw)


@pytest.mark.parametrize("change", ["uncertainty", "missing_uncertainty", "drift", "clock"])
def test_suspicious_or_undocumented_alignment_is_not_eligible(data, change):
    config = data.sync.model_copy(deep=True)
    if change == "uncertainty":
        config.uncertainty_s = 1
    elif change == "missing_uncertainty":
        config.anchors[0].uncertainty_s = None
    elif change == "drift":
        config.anchors[1].source_timestamp_s = 150
    else:
        config.reference_clock = ""
    assert synchronization(config).status != "aligned"


def test_event_matching_is_explicit_and_ambiguous_events_stay_excluded(store, data):
    session = store.put(data)
    diagnosis = eligibility(session)
    assert diagnosis["eligible_event_count"] == 4
    assert diagnosis["independent_real_world_eligible_count"] == 0
    assert not diagnosis["real_world_reference_available"]
    ambiguous = match_diagnostics(session, "event-006")
    assert "reference_association_ambiguous" in ambiguous["exclusion_reasons"]
    assert not ambiguous["eligible"]
    session.matches = []
    unmatched = match_diagnostics(session, "event-001")
    assert unmatched["association"] == "unmatched" and unmatched["reference_id"] is None


def test_event_time_mismatch_and_anchor_extrapolation_are_excluded(store, data):
    session = store.put(data)
    session.reference_events[0].timestamp_s += 5
    assert "reference_event_time_mismatch" in match_diagnostics(session, "event-001")["exclusion_reasons"]
    session = store.put(data)
    session.measurements[0].measurement.gate_a_timestamp_s = 101
    session.measurements[0].measurement.gate_b_timestamp_s = 102
    assert "event_outside_synchronization_anchor_span" in match_diagnostics(session, "event-001")["exclusion_reasons"]


@pytest.mark.parametrize("edge", ["start", "end"])
def test_reference_interval_cannot_extrapolate_past_anchors_even_within_tolerance(store, data, edge):
    session = store.put(data)
    session.sync.fit_drift = False
    session.sync.offset_s = 0
    session.sync.anchors[0].reference_timestamp_s = 0
    session.sync.anchors[0].source_timestamp_s = 0
    session.sync.anchors[1].reference_timestamp_s = 100
    session.sync.anchors[1].source_timestamp_s = 100
    measurement = session.measurements[0].measurement
    reference = session.reference_events[0]
    if edge == "end":
        measurement.gate_a_timestamp_s, measurement.gate_b_timestamp_s = 99, 100
        reference.timestamp_s, reference.interval_end_s = 100.1, None
    else:
        measurement.gate_a_timestamp_s, measurement.gate_b_timestamp_s = 0, 1
        # An interval beginning before the anchor span still overlaps the event.
        session.sync.anchors[0].reference_timestamp_s = 10
        session.sync.anchors[0].source_timestamp_s = 10
        measurement.gate_a_timestamp_s, measurement.gate_b_timestamp_s = 10, 11
        reference.timestamp_s, reference.interval_end_s = 9.9, 10.5
    diagnosis = match_diagnostics(session, "event-001")
    assert not diagnosis["eligible"]
    assert "reference_outside_synchronization_anchor_span" in diagnosis["exclusion_reasons"]
    assert "event_outside_synchronization_anchor_span" not in diagnosis["exclusion_reasons"]
    assert "reference_event_time_mismatch" not in diagnosis["exclusion_reasons"]


def test_reference_identity_confirmation_never_uses_error_magnitude(store, data):
    session = store.put(data)
    session.matches[0].correspondence_confirmed = False
    session.reference_events[0].speed = session.measurements[0].measurement.estimated_speed_kmh
    result = match_diagnostics(session, "event-001")
    assert not result["eligible"]
    assert "event_correspondence_not_confirmed" in result["exclusion_reasons"]


def test_unverified_reference_and_session_provenance_are_retained_but_excluded(store, data):
    session = store.put(data)
    session.provenance = "recorded_unverified"
    session.reference_events[0].independent = False
    diagnosis = match_diagnostics(session, "event-001")
    assert {"reference_not_independent", "session_provenance_unverified"}.issubset(diagnosis["exclusion_reasons"])


@pytest.mark.parametrize("issue", ["missing_timestamp", "duplicate_timestamp", "backward_timestamp", "timebase_changed", "flagged_frames"])
def test_source_timestamp_integrity_flags_exclude_comparisons_without_rewriting_status(store, data, issue):
    session = store.put(data)
    session.timing_summary["issues"] = {issue: 1}
    before = session.measurements[0].measurement.model_dump()
    diagnosis = match_diagnostics(session, "event-001")
    assert not diagnosis["eligible"]
    assert "source_timing_quality_flagged" in diagnosis["exclusion_reasons"]
    assert session.measurements[0].measurement.model_dump() == before


def test_nominal_fallback_excludes_and_missing_timing_counters_only_warn(store, data):
    session = store.put(data)
    assert match_diagnostics(session, "event-001")["eligible"]
    assert any("not supplied" in warning for warning in eligibility(session)["warnings"])
    session.source_timebase = "nominal frame interval fallback"
    assert "source_timing_quality_flagged" in match_diagnostics(session, "event-001")["exclusion_reasons"]


def test_portable_session_input_drops_derived_store_fields(store, data):
    created = store.put(data)
    raw = session_input(created)
    assert "id" not in raw and "sync_diagnostics" not in raw
    assert FieldSessionInput.model_validate(raw) == data
