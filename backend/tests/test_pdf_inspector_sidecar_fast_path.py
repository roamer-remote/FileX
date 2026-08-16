# Copyright (c) 2026 徐泽宇
"""175: pdf-inspector fast path wired into sidecar (mineru/docling) routing."""

from __future__ import annotations

from unittest.mock import patch

import fitz

from models.file import File as FileModel
from services.extract.base import ExtractResult
from services.extract.ocr_stats import ExtractOcrStats


def _make_pdf(tmp_path, name: str, *, text: str | None = "native text") -> FileModel:
    pdf = tmp_path / name
    doc = fitz.open()
    page = doc.new_page()
    if text:
        page.insert_text((72, 72), text)
    doc.save(str(pdf))
    doc.close()
    return FileModel(
        id=7,
        user_id=1,
        filename=name,
        original_name=name,
        file_path=str(pdf),
        file_size=100,
        mime_type="application/pdf",
    )


def _inspector_result() -> ExtractResult:
    return ExtractResult(
        text="# fast\n",
        engine="pdf-inspector",
        ocr_stats=ExtractOcrStats(
            ocr_used=False,
            ocr_engine="none",
            pdf_class="text_layer",
            text_layer_page_count=1,
        ),
    )


def test_fast_path_gated_by_enabled(monkeypatch, tmp_path):
    monkeypatch.setattr("services.pdf_inspector_switch_service.get_pdf_inspector_enabled", lambda db=None: False)
    from services.extract.providers.pdf_inspector_provider import try_pdf_inspector_fast_path

    f = _make_pdf(tmp_path, "gate.pdf")
    assert try_pdf_inspector_fast_path(f) is None


def test_fast_path_skips_non_pdf(tmp_path, monkeypatch):
    monkeypatch.setattr("services.pdf_inspector_switch_service.get_pdf_inspector_enabled", lambda db=None: True)
    from services.extract.providers.pdf_inspector_provider import try_pdf_inspector_fast_path

    txt = tmp_path / "note.txt"
    txt.write_text("hello", encoding="utf-8")
    f = FileModel(
        id=8,
        user_id=1,
        filename="note.txt",
        original_name="note.txt",
        file_path=str(txt),
        file_size=10,
        mime_type="text/plain",
    )
    with patch(
        "services.extract.providers.pdf_inspector_provider.try_extract_pdf_with_inspector"
    ) as m:
        assert try_pdf_inspector_fast_path(f) is None
    m.assert_not_called()


def test_fast_path_returns_inspector_result(tmp_path, monkeypatch):
    monkeypatch.setattr("services.pdf_inspector_switch_service.get_pdf_inspector_enabled", lambda db=None: True)
    monkeypatch.setattr("config.KB_PDF_INSPECTOR_MODE", "extract")
    from services.extract.providers.pdf_inspector_provider import try_pdf_inspector_fast_path

    f = _make_pdf(tmp_path, "eligible.pdf")
    expected = _inspector_result()
    with patch(
        "services.extract.providers.pdf_inspector_provider.try_extract_pdf_with_inspector",
        return_value=expected,
    ) as m:
        assert try_pdf_inspector_fast_path(f) is expected
    m.assert_called_once()
    assert m.call_args.kwargs["mode"] == "extract"


def test_sidecar_routing_mineru_hits_fast_path(tmp_path, monkeypatch):
    monkeypatch.setattr("services.pdf_inspector_switch_service.get_pdf_inspector_enabled", lambda db=None: True)
    from services.extract.providers.registry import extract_with_provider

    f = _make_pdf(tmp_path, "mineru-eligible.pdf")
    expected = _inspector_result()
    with patch(
        "services.extract.providers.pdf_inspector_provider.try_pdf_inspector_fast_path",
        return_value=expected,
    ):
        with patch("services.extract.providers.mineru_provider.extract_mineru") as m:
            result = extract_with_provider(f, db=None, provider_override="mineru")
    m.assert_not_called()
    assert result.engine == "pdf-inspector"


def test_sidecar_routing_mineru_falls_through_to_sidecar(tmp_path, monkeypatch):
    monkeypatch.setattr("services.pdf_inspector_switch_service.get_pdf_inspector_enabled", lambda db=None: True)
    from services.extract.providers.registry import extract_with_provider

    f = _make_pdf(tmp_path, "mineru-ineligible.pdf")
    with patch(
        "services.extract.providers.pdf_inspector_provider.try_pdf_inspector_fast_path",
        return_value=None,
    ):
        with patch(
            "services.extract.providers.mineru_provider.extract_mineru",
            return_value=ExtractResult(text="# sidecar\n", engine="mineru"),
        ) as m:
            result = extract_with_provider(f, db=None, provider_override="mineru")
    m.assert_called_once()
    assert result.engine == "mineru"


def test_sidecar_routing_docling_hits_fast_path(tmp_path, monkeypatch):
    monkeypatch.setattr("services.pdf_inspector_switch_service.get_pdf_inspector_enabled", lambda db=None: True)
    from services.extract.providers.registry import extract_with_provider

    f = _make_pdf(tmp_path, "docling-eligible.pdf")
    expected = _inspector_result()
    with patch(
        "services.extract.providers.pdf_inspector_provider.try_pdf_inspector_fast_path",
        return_value=expected,
    ):
        with patch("services.extract.providers.docling_provider.extract_docling") as m:
            result = extract_with_provider(f, db=None, provider_override="docling")
    m.assert_not_called()
    assert result.engine == "pdf-inspector"


def test_legacy_path_does_not_run_registry_fast_path(tmp_path, monkeypatch):
    monkeypatch.setattr("services.pdf_inspector_switch_service.get_pdf_inspector_enabled", lambda db=None: True)
    from services.extract.providers.registry import extract_with_provider

    f = _make_pdf(tmp_path, "legacy.pdf")
    with patch(
        "services.extract.providers.pdf_inspector_provider.try_pdf_inspector_fast_path"
    ) as fast:
        with patch(
            "services.extract.providers.registry._legacy_extract",
            return_value=ExtractResult(text="# legacy\n", engine="pymupdf"),
        ) as legacy:
            result = extract_with_provider(f, db=None, provider_override="legacy")
    fast.assert_not_called()
    legacy.assert_called_once()
    assert result.engine == "pymupdf"


def test_run_extract_job_mineru_fast_path_logs_pdf_inspector(
    db_session, regular_user, tmp_path, monkeypatch
):
    """Full run_extract_job path: sidecar provider + fast path -> DONE engine=pdf-inspector."""
    from unittest.mock import patch

    from models.kb_extract_job import KbExtractJob
    from services.extract.ocr_stats import ExtractOcrStats
    from services.kb_extract_service import JOB_QUEUED, run_extract_job
    from services.kb_pipeline_log_service import ACTION_KB_EXTRACT_DONE

    monkeypatch.setattr("services.pdf_inspector_switch_service.get_pdf_inspector_enabled", lambda db=None: True)
    f = _make_pdf(tmp_path, "mineru-fast-job.pdf")
    f.user_id = regular_user.id
    db_session.add(f)
    db_session.flush()
    job = KbExtractJob(
        user_id=regular_user.id,
        file_id=f.id,
        status=JOB_QUEUED,
        provider="mineru",
        attempts=0,
    )
    db_session.add(job)
    db_session.commit()

    expected = ExtractResult(
        text="# note\n",
        engine="pdf-inspector",
        ocr_stats=ExtractOcrStats(
            ocr_used=False,
            ocr_engine="none",
            pdf_class="text_layer",
            text_layer_page_count=1,
        ),
    )
    with patch(
        "services.extract.providers.pdf_inspector_provider.try_pdf_inspector_fast_path",
        return_value=expected,
    ):
        with patch("services.kb_extract_service.persist_extract_result") as persist:
            from services.kb_extract_service import ExtractPersistTimings

            persist.return_value = ExtractPersistTimings(persist_ms=1, side_effects_ms=2)
            with patch("services.kb_index_service.enqueue_index_after_extract", return_value=None):
                run_extract_job(db_session, job)
    db_session.commit()

    from models.operation_log import OperationLog

    row = (
        db_session.query(OperationLog)
        .filter(
            OperationLog.target_id == f.id,
            OperationLog.action == ACTION_KB_EXTRACT_DONE,
        )
        .order_by(OperationLog.id.desc())
        .first()
    )
    assert row is not None
    assert "engine=pdf-inspector" in row.detail
    assert "ocr_used=false" in row.detail
