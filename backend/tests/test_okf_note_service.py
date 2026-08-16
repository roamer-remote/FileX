# Copyright (c) 2026 徐泽宇
"""OKF native note service tests."""

from __future__ import annotations

import os
from datetime import datetime, timezone
from unittest.mock import patch

from models.file import File as FileModel
from models.folder import Folder
from services.md_hash_service import compute_md_content_hash
from services.md_paths import okf_sidecar_path
from services.okf.frontmatter import split_frontmatter
from services.okf_note_service import (
    build_upload_okf_metadata,
    create_okf_note_shell,
    initialize_okf_note_for_upload,
    read_okf_body_for_file,
    read_okf_note,
    read_okf_raw_for_file,
    save_okf_body_for_file,
    sync_file_okf_fields_from_frontmatter,
    touch_body_content_hash,
    update_okf_frontmatter_for_file,
)


def _file(tmp_path, *, note_text: str | None = None, file_id: int = 123) -> FileModel:
    note_path = tmp_path / f"{file_id}.md"
    has_md = note_text is not None
    if note_text is not None:
        note_path.write_text(note_text, encoding="utf-8")
    return FileModel(
        id=file_id,
        user_id=9,
        workspace_id=7,
        folder_id=20,
        filename="Quarterly Report.pdf",
        original_name="Quarterly Report.pdf",
        file_path=str(tmp_path / "Quarterly Report.pdf"),
        file_size=4096,
        mime_type="application/pdf",
        md5_hash="0123456789abcdef0123456789abcdef",
        has_md=has_md,
        md_file_path=str(note_path) if has_md else None,
        page_kind="source",
        extract_status="pending",
        extract_engine=None,
    )


def test_read_okf_note_splits_valid_frontmatter(tmp_path):
    raw = (
        "---\n"
        "type: FileX Source\n"
        "title: Quarterly Report\n"
        "tags: [finance]\n"
        "okf_version: '0.1'\n"
        "---\n"
        "# Body\n"
    )
    f = _file(tmp_path, note_text=raw)

    note = read_okf_note(f)

    assert note.frontmatter["type"] == "FileX Source"
    assert note.frontmatter["title"] == "Quarterly Report"
    assert note.body == "# Body\n"
    assert note.raw == raw
    assert note.is_legacy is False
    assert read_okf_body_for_file(f) == "# Body\n"
    assert read_okf_raw_for_file(f) == raw


def test_read_okf_note_treats_missing_or_invalid_frontmatter_as_legacy(tmp_path):
    legacy = _file(tmp_path, note_text="# Legacy note\n")
    invalid = _file(tmp_path, note_text="---\ntype: [\n---\nBody", file_id=124)

    legacy_note = read_okf_note(legacy)
    invalid_note = read_okf_note(invalid)

    assert legacy_note.frontmatter == {}
    assert legacy_note.body == "# Legacy note\n"
    assert legacy_note.is_legacy is True
    assert invalid_note.frontmatter == {}
    assert invalid_note.body == "---\ntype: [\n---\nBody"
    assert invalid_note.is_legacy is True


def test_read_okf_note_logs_invalid_frontmatter_warning(tmp_path):
    invalid = _file(tmp_path, note_text="---\ntype: [\n---\nBody", file_id=124)

    with patch("services.okf_note_service.logger.warning") as mock_warning:
        note = read_okf_note(invalid)

    assert note.is_legacy is True
    mock_warning.assert_called_once()
    assert "invalid_okf_frontmatter" in mock_warning.call_args.args[0]
    assert mock_warning.call_args.args[1] == 124


def test_save_okf_body_preserves_frontmatter_and_updates_body_hash(tmp_path):
    raw = (
        "---\n"
        "type: FileX Source\n"
        "title: Original\n"
        "description: ''\n"
        "okf_version: '0.1'\n"
        "---\n"
        "Old body\n"
    )
    f = _file(tmp_path, note_text=raw)

    save_okf_body_for_file(f, "New body\n")

    saved = read_okf_raw_for_file(f)
    meta, body = split_frontmatter(saved)
    assert meta["type"] == "FileX Source"
    assert meta["title"] == "Original"
    assert "description" not in meta
    assert meta["okf_version"] == "0.1"
    assert body == "New body\n"
    assert f.md_content_hash == compute_md_content_hash("New body\n")


def test_save_okf_body_bumps_timestamp(tmp_path):
    raw = (
        "---\n"
        "type: FileX Source\n"
        "title: Original\n"
        "timestamp: 2020-01-01T00:00:00Z\n"
        "okf_version: '0.1'\n"
        "---\n"
        "Old body\n"
    )
    f = _file(tmp_path, note_text=raw)

    save_okf_body_for_file(
        f,
        "New body\n",
        timestamp=datetime(2026, 7, 3, 9, 10, 11, tzinfo=timezone.utc),
    )

    meta, body = split_frontmatter(read_okf_raw_for_file(f))
    assert meta["timestamp"] == "2026-07-03T09:10:11Z"
    assert body == "New body\n"


def test_save_okf_body_writes_with_atomic_replace(tmp_path):
    f = _file(tmp_path, note_text="Legacy body\n")

    with patch("services.okf_note_service.os.replace", wraps=os.replace) as mock_replace:
        save_okf_body_for_file(f, "Replacement\n")

    mock_replace.assert_called_once()
    replaced_source, replaced_target = mock_replace.call_args.args
    assert replaced_target == f.md_file_path
    assert replaced_source != replaced_target


def test_save_okf_body_wraps_legacy_note_with_defaults(tmp_path):
    f = _file(tmp_path, note_text="Legacy body\n")

    save_okf_body_for_file(f, "Replacement\n")

    meta, body = split_frontmatter(read_okf_raw_for_file(f))
    assert meta["type"] == "FileX Source"
    assert meta["okf_version"] == "0.1"
    assert meta["title"] == "Quarterly Report"
    assert body == "Replacement\n"


def test_create_okf_note_shell_writes_supplied_frontmatter_with_empty_body(tmp_path):
    f = _file(tmp_path)
    frontmatter = {
        "type": "Custom Source",
        "title": "Shell Title",
        "resource": "filex://files/123",
        "tags": ["api"],
        "timestamp": "2026-07-03T04:05:06Z",
        "okf_version": "0.1",
    }

    create_okf_note_shell(f, frontmatter, concept_path="sources/api/shell-title")

    sidecar = okf_sidecar_path(f.workspace_id, "sources/api/shell-title")
    assert f.md_file_path == sidecar
    meta, body = split_frontmatter(read_okf_raw_for_file(f))
    assert meta["type"] == "Custom Source"
    assert meta["title"] == "Shell Title"
    assert meta["tags"] == ["api"]
    assert body == ""
    assert f.okf_concept_path == "sources/api/shell-title"
    assert f.okf_type == "Custom Source"
    assert f.okf_metadata["title"] == "Shell Title"


def test_build_upload_metadata_and_sync_file_fields(tmp_path):
    f = _file(tmp_path)
    uploaded_at = datetime(2026, 7, 3, 4, 5, 6, tzinfo=timezone.utc)

    metadata = build_upload_okf_metadata(
        f,
        okf_title="",
        okf_type="",
        okf_description="",
        okf_tags=["finance", "quarterly"],
        okf_concept_path="sources/reports/quarterly",
        timestamp=uploaded_at,
    )

    assert metadata["type"] == "FileX Source"
    assert metadata["title"] == "Quarterly Report"
    assert metadata["tags"] == ["finance", "quarterly"]
    assert metadata["timestamp"] == "2026-07-03T04:05:06Z"
    assert metadata["okf_version"] == "0.1"
    assert "description" not in metadata
    assert metadata["resource"] == "filex://files/123"
    assert metadata["filex"]["file_id"] == 123
    assert metadata["filex"]["workspace_id"] == 7
    assert metadata["filex"]["folder_id"] == 20
    assert metadata["filex"]["source_mime"] == "application/pdf"
    assert metadata["filex"]["source_md5"] == "0123456789abcdef0123456789abcdef"
    assert metadata["filex"]["source_size"] == 4096
    assert metadata["filex"]["original_name"] == "Quarterly Report.pdf"
    assert metadata["filex"]["extract_status"] == "pending"

    sync_file_okf_fields_from_frontmatter(f, metadata, concept_path="sources/reports/quarterly")

    assert f.okf_concept_path == "sources/reports/quarterly"
    assert f.okf_type == "FileX Source"
    assert f.okf_metadata["title"] == "Quarterly Report"
    assert "type" not in f.okf_metadata
    assert f.okf_reserved_role is None
    assert f.page_kind == "source"
    assert f.wiki_slug is None


def test_initialize_upload_uses_folder_relative_concept_path(db_session, tmp_path):
    root = Folder(id=2001, name="Reports 2026", parent_id=None, workspace_id=7, user_id=9)
    child = Folder(id=2002, name="Q1/Raw", parent_id=2001, workspace_id=7, user_id=9)
    db_session.add_all([root, child])
    db_session.flush()
    f = _file(tmp_path, file_id=901)
    f.folder_id = child.id

    initialize_okf_note_for_upload(db_session, f, b"")

    expected = okf_sidecar_path(f.workspace_id, f.okf_concept_path)
    assert os.path.isfile(expected)
    assert f.md_file_path == expected
    assert f.okf_concept_path == "sources/Reports-2026/Q1-Raw/Quarterly-Report"


def test_update_frontmatter_bumps_timestamp_without_changing_body_hash(tmp_path, db_session):
    raw = (
        "---\n"
        "type: FileX Source\n"
        "title: Original\n"
        "timestamp: 2026-07-03T04:05:06Z\n"
        "okf_version: '0.1'\n"
        "---\n"
        "Body\n"
    )
    f = _file(tmp_path, note_text=raw)
    f.md_content_hash = compute_md_content_hash("Body\n")

    update_okf_frontmatter_for_file(
        f,
        {
            "type": "FileX Source",
            "title": "Updated",
            "timestamp": "2020-01-01T00:00:00Z",
            "okf_version": "0.1",
        },
        concept_path="sources/updated/path",
        timestamp=datetime(2026, 7, 3, 8, 9, 10, tzinfo=timezone.utc),
        db=db_session,
    )

    sidecar = okf_sidecar_path(f.workspace_id, "sources/updated/path")
    assert f.md_file_path == sidecar

    meta, body = split_frontmatter(read_okf_raw_for_file(f))
    assert meta["title"] == "Updated"
    assert meta["timestamp"] == "2026-07-03T08:09:10Z"
    assert body == "Body\n"
    assert f.okf_concept_path == "sources/updated/path"
    assert f.md_content_hash == compute_md_content_hash("Body\n")


def test_touch_body_content_hash_hashes_body_only(tmp_path):
    raw = "---\ntype: FileX Source\n---\nBody only\n"
    f = _file(tmp_path, note_text=raw)

    digest = touch_body_content_hash(f)

    assert digest == compute_md_content_hash("Body only\n")
    assert f.md_content_hash == digest
