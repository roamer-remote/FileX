# Copyright (c) 2026 徐泽宇
"""Tests for legacy Office normalization on disk.

Authors:
    徐泽宇

Copyright:
    © 2026 徐泽宇
"""

from __future__ import annotations

import os
from unittest.mock import patch

import pytest

from models.file import File as FileModel
from services.office_normalize_service import (
    ensure_office_normalized,
    preview_mime_type,
    preview_path_and_mime,
    remove_normalized_file,
)

PPTX_MIME = "application/vnd.openxmlformats-officedocument.presentationml.presentation"


@pytest.fixture
def legacy_doc_file(db_session, regular_user):
    from config import UPLOAD_DIR

    os.makedirs(UPLOAD_DIR, exist_ok=True)
    src = os.path.join(UPLOAD_DIR, "sample.doc")
    with open(src, "wb") as fh:
        fh.write(b"legacy-doc-bytes")
    f = FileModel(
        filename="uuid_sample.doc",
        original_name="sample.doc",
        file_path=src,
        file_size=16,
        mime_type="application/msword",
        user_id=regular_user.id,
        workspace_id=None,
    )
    db_session.add(f)
    db_session.commit()
    db_session.refresh(f)
    return f


def test_preview_mime_none_without_normalized(legacy_doc_file):
    assert preview_mime_type(legacy_doc_file) is None
    path, mime = preview_path_and_mime(legacy_doc_file)
    assert path == legacy_doc_file.file_path
    assert mime == "application/msword"


@patch("services.office_normalize_service.convert_to_modern")
def test_ensure_office_normalized_persists_copy(mock_convert, legacy_doc_file, tmp_path):
    converted = tmp_path / "converted.docx"
    converted.write_bytes(b"docx-bytes")
    mock_convert.return_value = str(converted)

    out = ensure_office_normalized(legacy_doc_file)

    assert out.endswith(f"{legacy_doc_file.id}.docx")
    assert os.path.isfile(out)
    assert legacy_doc_file.normalized_path == out
    assert preview_mime_type(legacy_doc_file) == (
        "application/vnd.openxmlformats-officedocument.wordprocessingml.document"
    )
    stream_path, mime = preview_path_and_mime(legacy_doc_file)
    assert stream_path == out
    assert "wordprocessingml" in mime


@patch("services.office_normalize_service.convert_to_modern")
def test_preview_legacy_doc_returns_modern_mime(mock_convert, client, jwt_token, legacy_doc_file, tmp_path):
    converted = tmp_path / "converted.docx"
    converted.write_bytes(b"PK\x03\x04")
    mock_convert.return_value = str(converted)

    r = client.get(
        f"/api/files/{legacy_doc_file.id}/preview",
        headers={"Authorization": f"Bearer {jwt_token}"},
    )
    assert r.status_code == 200
    assert "wordprocessingml" in (r.headers.get("content-type") or "")


def test_remove_normalized_file(legacy_doc_file, tmp_path):
    norm = tmp_path / "18.docx"
    norm.write_bytes(b"x")
    legacy_doc_file.normalized_path = str(norm)
    remove_normalized_file(legacy_doc_file)
    assert not os.path.isfile(norm)
    assert legacy_doc_file.normalized_path is None


@pytest.fixture
def pptx_file(db_session, regular_user, tmp_path):
    src = tmp_path / "brand-deck.pptx"
    src.write_bytes(b"pptx-bytes")
    f = FileModel(
        filename="brand-deck.pptx",
        original_name="brand-deck.pptx",
        file_path=str(src),
        file_size=src.stat().st_size,
        mime_type=PPTX_MIME,
        user_id=regular_user.id,
        workspace_id=None,
    )
    db_session.add(f)
    db_session.commit()
    db_session.refresh(f)
    return f


def test_preview_mime_type_reports_pdf_for_pptx_without_normalized_copy(pptx_file):
    assert preview_mime_type(pptx_file) == "application/pdf"
    assert pptx_file.normalized_path is None


def test_preview_path_and_mime_uses_independent_pdf_preview_cache(
    monkeypatch, tmp_path, pptx_file
):
    cached_pdf = tmp_path / f"{pptx_file.id}.pdf"
    cached_pdf.write_bytes(b"%PDF-1.4 preview")
    calls: list[int] = []

    def fake_ensure_preview_pdf(f):
        calls.append(f.id)
        return str(cached_pdf)

    monkeypatch.setattr("services.office_normalize_service.ensure_preview_pdf", fake_ensure_preview_pdf)

    path, mime = preview_path_and_mime(pptx_file)

    assert path == str(cached_pdf)
    assert mime == "application/pdf"
    assert calls == [pptx_file.id]
    assert pptx_file.normalized_path is None
