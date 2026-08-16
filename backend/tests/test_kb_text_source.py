# Copyright (c) 2026 徐泽宇
"""KB index text resolution (sidecar md paths)."""

from __future__ import annotations

from models.file import File as FileModel
from services.kb_text_source import resolve_index_text
from services.md_paths import resolve_upload_path


def test_resolve_upload_path_rebases_host_absolute_to_container_upload_dir(
    tmp_path, monkeypatch
):
    container_upload = tmp_path / "container_uploads"
    container_upload.mkdir()
    note = container_upload / ".md_notes" / "15.md"
    note.parent.mkdir(parents=True)
    note.write_text("hello note", encoding="utf-8")

    host_path = "/Users/dev/project/backend/uploads/.md_notes/15.md"
    monkeypatch.setattr("services.md_paths.UPLOAD_DIR", str(container_upload))

    assert resolve_upload_path(host_path) == str(note)


def test_resolve_index_text_reads_sidecar_via_rebased_path(tmp_path, monkeypatch):
    upload = tmp_path / "uploads"
    upload.mkdir()
    note = upload / ".md_notes" / "9.md"
    note.parent.mkdir(parents=True)
    note.write_text("# Title\n\nBody for index.", encoding="utf-8")

    monkeypatch.setattr("services.md_paths.UPLOAD_DIR", str(upload))

    f = FileModel(
        id=9,
        user_id=1,
        original_name="doc.pdf",
        filename="doc.pdf",
        file_path="/Users/host/FileX/backend/uploads/1/doc.pdf",
        mime_type="application/pdf",
        has_md=True,
        md_file_path="/Users/host/FileX/backend/uploads/.md_notes/9.md",
    )
    text, source = resolve_index_text(f)
    assert source == "sidecar_md"
    assert "Body for index" in (text or "")


def test_resolve_upload_path_rebases_app_uploads_to_host_upload_dir(tmp_path, monkeypatch):
    upload = tmp_path / "uploads"
    ws_dir = upload / "1" / "2026-06"
    ws_dir.mkdir(parents=True)
    pdf = ws_dir / "doc.pdf"
    pdf.write_bytes(b"%PDF-1.4")

    monkeypatch.setattr("services.md_paths.UPLOAD_DIR", str(upload))

    assert resolve_upload_path("/app/uploads/1/2026-06/doc.pdf") == str(pdf)


def test_extract_router_resolves_container_file_path(tmp_path, monkeypatch):
    from unittest.mock import patch

    from models.file import File as FileModel
    from services.extract.base import ExtractResult
    from services.extract.router import extract_text_from_file

    upload = tmp_path / "uploads"
    ws_dir = upload / "1" / "2026-06"
    ws_dir.mkdir(parents=True)
    pdf = ws_dir / "annual.pdf"
    pdf.write_bytes(b"%PDF-1.4 minimal")

    monkeypatch.setattr("services.md_paths.UPLOAD_DIR", str(upload))

    f = FileModel(
        id=137,
        user_id=1,
        original_name="annual.pdf",
        filename="annual.pdf",
        file_path="/app/uploads/1/2026-06/annual.pdf",
        mime_type="application/pdf",
    )
    with patch("services.extract.router.extract_pdf") as mock_pdf:
        mock_pdf.return_value = ExtractResult(text="# ok", engine="test")
        result = extract_text_from_file(f)
    assert result.text == "# ok"
    mock_pdf.assert_called_once_with(str(pdf), file_id=137)


def test_read_file_md_plaintext_or_raise_rebases_host_md_path(tmp_path, monkeypatch):
    from fastapi import HTTPException

    from services.md_note_service import read_file_md_plaintext_or_raise

    upload = tmp_path / "uploads"
    note = upload / ".md_notes" / "106.md"
    note.parent.mkdir(parents=True)
    note.write_text("note in container", encoding="utf-8")
    monkeypatch.setattr("services.md_paths.UPLOAD_DIR", str(upload))

    f = FileModel(
        filename="x",
        original_name="x.md",
        file_path=str(upload / "x.bin"),
        file_size=1,
        mime_type="text/markdown",
        user_id=1,
        has_md=True,
        md_file_path="/Users/host/FileX/backend/uploads/.md_notes/106.md",
    )
    assert read_file_md_plaintext_or_raise(f) == "note in container"

    f.md_file_path = "/no/such/note.md"
    try:
        read_file_md_plaintext_or_raise(f)
        raise AssertionError("expected 404")
    except HTTPException as exc:
        assert exc.status_code == 404
