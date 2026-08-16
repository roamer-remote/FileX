# Copyright (c) 2026 徐泽宇
"""Tests for Office document PDF preview cache generation."""

from __future__ import annotations

import os
import threading
from concurrent.futures import ThreadPoolExecutor

import pytest

from models.file import File as FileModel


PPTX_MIME = "application/vnd.openxmlformats-officedocument.presentationml.presentation"


def ppt_file(src: str, *, file_id: int = 633, mime_type: str = PPTX_MIME) -> FileModel:
    return FileModel(
        id=file_id,
        filename=os.path.basename(src),
        original_name=os.path.basename(src),
        file_path=src,
        file_size=os.path.getsize(src),
        mime_type=mime_type,
        user_id=1,
    )


@pytest.fixture
def pptx_source(tmp_path):
    src = tmp_path / "deck.pptx"
    src.write_bytes(b"pptx-bytes")
    return src


def test_preview_pdf_helpers_identify_ppt_and_cache_path(monkeypatch, tmp_path, pptx_source):
    monkeypatch.setattr("services.office_preview_pdf_service.UPLOAD_DIR", str(tmp_path / "uploads"))

    from services.office_preview_pdf_service import (
        PREVIEW_PDF_MIME,
        preview_pdf_disk_path,
        preview_pdf_mime_type,
        should_preview_as_pdf,
    )

    f = ppt_file(str(pptx_source), file_id=633)

    assert should_preview_as_pdf(f) is True
    assert preview_pdf_mime_type(f) == PREVIEW_PDF_MIME
    assert preview_pdf_disk_path(f).endswith(os.path.join(".preview_pdf", "633.pdf"))

    pdf_src = tmp_path / "plain.pdf"
    pdf_src.write_bytes(b"%PDF-1.4")
    pdf = ppt_file(str(pdf_src), file_id=634, mime_type="application/pdf")
    pdf.original_name = "plain.pdf"
    assert should_preview_as_pdf(pdf) is False
    assert preview_pdf_mime_type(pdf) is None


def test_ensure_preview_pdf_generates_and_reuses_cache_without_normalized_path(
    monkeypatch, tmp_path, pptx_source
):
    upload = tmp_path / "uploads"
    converted = tmp_path / "converted.pdf"
    converted.write_bytes(b"%PDF-1.4 converted")
    calls: list[str] = []

    def fake_convert_to_pdf(src_path: str) -> str:
        calls.append(src_path)
        return str(converted)

    monkeypatch.setattr("services.office_preview_pdf_service.UPLOAD_DIR", str(upload))
    monkeypatch.setattr("services.office_preview_pdf_service.convert_to_pdf", fake_convert_to_pdf)

    from services.office_preview_pdf_service import ensure_preview_pdf

    f = ppt_file(str(pptx_source), file_id=701)

    first = ensure_preview_pdf(f)
    second = ensure_preview_pdf(f)

    assert first == second
    assert os.path.isfile(first)
    assert open(first, "rb").read() == b"%PDF-1.4 converted"
    assert calls == [str(pptx_source)]
    assert f.normalized_path is None


def test_ensure_preview_pdf_cleans_partial_file_on_failed_conversion(
    monkeypatch, tmp_path, pptx_source
):
    upload = tmp_path / "uploads"

    def fake_convert_to_pdf(src_path: str) -> str:
        raise RuntimeError("libreoffice failed")

    monkeypatch.setattr("services.office_preview_pdf_service.UPLOAD_DIR", str(upload))
    monkeypatch.setattr("services.office_preview_pdf_service.convert_to_pdf", fake_convert_to_pdf)

    from services.office_preview_pdf_service import ensure_preview_pdf, preview_pdf_disk_path

    f = ppt_file(str(pptx_source), file_id=702)

    with pytest.raises(RuntimeError):
        ensure_preview_pdf(f)

    assert not os.path.exists(preview_pdf_disk_path(f))
    assert not list((upload / ".preview_pdf").glob("702.pdf.tmp.*"))


def test_ensure_preview_pdf_serializes_concurrent_generation(monkeypatch, tmp_path, pptx_source):
    upload = tmp_path / "uploads"
    started = threading.Event()
    release = threading.Event()
    calls: list[str] = []

    def fake_convert_to_pdf(src_path: str) -> str:
        calls.append(src_path)
        started.set()
        assert release.wait(2)
        converted = tmp_path / f"converted-{len(calls)}.pdf"
        converted.write_bytes(b"%PDF-1.4 concurrent")
        return str(converted)

    monkeypatch.setattr("services.office_preview_pdf_service.UPLOAD_DIR", str(upload))
    monkeypatch.setattr("services.office_preview_pdf_service.convert_to_pdf", fake_convert_to_pdf)

    from services.office_preview_pdf_service import ensure_preview_pdf

    f = ppt_file(str(pptx_source), file_id=703)

    with ThreadPoolExecutor(max_workers=2) as pool:
        future_a = pool.submit(ensure_preview_pdf, f)
        assert started.wait(2)
        future_b = pool.submit(ensure_preview_pdf, f)
        release.set()
        path_a = future_a.result(timeout=2)
        path_b = future_b.result(timeout=2)

    assert path_a == path_b
    assert open(path_a, "rb").read() == b"%PDF-1.4 concurrent"
    assert len(calls) == 1
