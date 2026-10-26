"""Uploaded-file metadata persistence without retaining frames or copying recordings."""

import hashlib
import json
import os
import shutil
from uuid import uuid4

import cv2
import numpy as np
import pytest

from roadlens.video_catalog import VideoCatalog


def make_video(path, shade=40):
    writer = cv2.VideoWriter(str(path), cv2.VideoWriter_fourcc(*"FFV1"), 12, (96, 64))
    assert writer.isOpened()
    for index in range(5):
        writer.write(np.full((64, 96, 3), shade + index, np.uint8))
    writer.release()
    return path


def test_persistent_record_is_relative_and_records_real_metadata(tmp_path):
    uploads = tmp_path / "uploads"
    uploads.mkdir()
    video = make_video(uploads / "opaque.avi")
    source_id = "video:" + hashlib.sha256(video.read_bytes()).hexdigest()
    identifier = str(uuid4())
    catalog = VideoCatalog(uploads)
    record = catalog.register(video, "Traffic clip", source_id, identifier)
    assert record["video_id"] == identifier
    assert record["source_id"] == source_id
    assert record["relative_path"] == "opaque.avi"
    assert record["width"] == 96 and record["height"] == 64
    assert record["reported_fps"] == 12
    assert record["frame_count"] == 5
    assert "_size" not in record
    assert VideoCatalog(uploads).sources() == [record]
    assert catalog.existing(source_id) == record
    assert len(list(uploads.glob("*.avi"))) == 1


def test_rediscovery_is_lazy_and_does_not_rehash_current_metadata(tmp_path, monkeypatch):
    make_video(tmp_path / "original.avi")
    catalog = VideoCatalog(tmp_path)
    first = catalog.sources()
    assert len(first) == 1
    monkeypatch.setattr(catalog, "_describe", lambda *args: pytest.fail("Unchanged source metadata was re-read."))
    assert catalog.sources() == first


def test_duplicate_content_reuses_stable_id_without_deleting_either_file(tmp_path):
    original = make_video(tmp_path / "first.avi")
    duplicate = tmp_path / "second.avi"
    shutil.copyfile(original, duplicate)
    catalog = VideoCatalog(tmp_path)
    first = catalog.register(original, "Original")
    second = catalog.register(duplicate, "Duplicate")
    assert first == second
    assert len(catalog.sources()) == 1
    assert original.exists() and duplicate.exists()
    original.unlink()
    recovered = catalog.sources()
    assert len(recovered) == 1
    assert recovered[0]["source_id"] == first["source_id"]
    assert recovered[0]["relative_path"] == "second.avi"


def test_changed_file_is_fingerprinted_again_and_deleted_file_disappears(tmp_path):
    video = make_video(tmp_path / "video.avi")
    catalog = VideoCatalog(tmp_path)
    before = catalog.sources()[0]
    original_stat = video.stat()
    make_video(video, shade=80)
    # Windows may retain one timestamp during very rapid same-size rewrites.
    os.utime(video, ns=(original_stat.st_atime_ns, original_stat.st_mtime_ns + 1_000_000_000))
    after = catalog.sources()[0]
    assert after["source_id"] != before["source_id"]
    assert after["video_id"] != before["video_id"]
    assert catalog.existing(before["source_id"]) is None
    video.unlink()
    assert catalog.sources() == []


def test_outside_paths_stay_private_in_memory_only(tmp_path):
    uploads = tmp_path / "uploads"
    outside = make_video(tmp_path / "outside.avi")
    catalog = VideoCatalog(uploads)
    assert catalog.register(outside, "Private external fixture") is None
    assert not (uploads / ".catalog.json").exists()


def test_catalog_rejects_wrong_recording_fingerprint(tmp_path):
    video = make_video(tmp_path / "video.avi")
    with pytest.raises(ValueError, match="does not match"):
        VideoCatalog(tmp_path).register(video, "video", "video:" + "f" * 64)


def test_invalid_partial_uploads_are_not_listed(tmp_path):
    (tmp_path / "partial.mp4").write_bytes(b"incomplete")
    (tmp_path / "notes.txt").write_text("metadata only")
    assert VideoCatalog(tmp_path).sources() == []


def test_catalog_paths_cannot_escape_upload_root(tmp_path):
    uploads = tmp_path / "uploads"
    uploads.mkdir()
    outside = make_video(tmp_path / "private.avi")
    source = {"video_id": str(uuid4()), "source_id": "private", "relative_path": "../private.avi", "_size": outside.stat().st_size, "_mtime_ns": outside.stat().st_mtime_ns}
    (uploads / ".catalog.json").write_text(json.dumps({"version": 1, "videos": [source]}), encoding="utf-8")
    assert VideoCatalog(uploads).sources() == []
    assert outside.exists()


def test_catalog_label_retains_only_a_basename_and_plain_control_free_text(tmp_path):
    video = make_video(tmp_path / "opaque.avi")
    record = VideoCatalog(tmp_path).register(video, "C:\\private\\video\x00name.avi")
    assert record["name"] == "videoname.avi"
