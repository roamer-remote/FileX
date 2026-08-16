# Copyright (c) 2026 徐泽宇
"""103 P0: PDF OCR classification and extract pipeline log fields."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import patch

import fitz

from models.file import File as FileModel
from models.kb_extract_job import KbExtractJob
from services.extract.base import ExtractResult
from services.extract.ocr_stats import ExtractOcrStats, ocr_stats_for_image, ocr_stats_for_sidecar_provider
from services.extract.pdf import MIN_TEXT_CHARS_PER_PAGE, classify_pdf_pages, extract_pdf
from services.kb_extract_service import JOB_QUEUED, run_extract_job
from services.kb_pipeline_log_service import ACTION_KB_EXTRACT_DONE
from services.kb_pipeline_service import parse_pipeline_config


def _write_pdf(path: Path, page_texts: list[str | None]) -> None:
    doc = fitz.open()
    for text in page_texts:
        page = doc.new_page()
        if text:
            page.insert_text((72, 72), text)
    doc.save(str(path))
    doc.close()


def test_classify_pdf_pages_text_layer(tmp_path):
    pdf = tmp_path / "text.pdf"
    long_text = "x" * (MIN_TEXT_CHARS_PER_PAGE + 1)
    _write_pdf(pdf, [long_text, long_text])
    stats = classify_pdf_pages(str(pdf))
    assert stats.pdf_class == "text_layer"
    assert stats.ocr_used is False
    assert stats.ocr_engine == "none"
    assert stats.text_layer_page_count == 2
    assert stats.ocr_page_count is None


def test_classify_pdf_pages_scan(tmp_path):
    pdf = tmp_path / "scan.pdf"
    _write_pdf(pdf, [None])
    stats = classify_pdf_pages(str(pdf))
    assert stats.pdf_class == "scan"
    assert stats.ocr_used is True
    assert stats.ocr_page_count == 1
    assert stats.text_layer_page_count == 0


def test_classify_pdf_pages_mixed(tmp_path):
    pdf = tmp_path / "mixed.pdf"
    long_text = "y" * (MIN_TEXT_CHARS_PER_PAGE + 1)
    _write_pdf(pdf, [long_text, None])
    stats = classify_pdf_pages(str(pdf))
    assert stats.pdf_class == "mixed"
    assert stats.ocr_used is True
    assert stats.text_layer_page_count == 1
    assert stats.ocr_page_count == 1


def test_extract_pdf_attaches_ocr_stats_text_layer(tmp_path, monkeypatch):
    monkeypatch.setenv("KB_MARKITDOWN_ENABLED", "0")
    pdf = tmp_path / "body.pdf"
    long_text = "z" * (MIN_TEXT_CHARS_PER_PAGE + 1)
    _write_pdf(pdf, [long_text])
    with patch("services.extract.markitdown_extract.try_markitdown", return_value=None):
        with patch("services.extract.pdf.ocr_pil_image_with_confidence", return_value=("", None)):
            result = extract_pdf(str(pdf), file_id=99)
    assert result.ocr_stats is not None
    assert result.ocr_stats.pdf_class == "text_layer"
    assert result.ocr_stats.ocr_used is False
    assert result.engine == "pymupdf"


def test_extract_pdf_mixed_marks_ocr_used(tmp_path, monkeypatch):
    monkeypatch.setenv("KB_MARKITDOWN_ENABLED", "0")
    pdf = tmp_path / "mixed-body.pdf"
    long_text = "a" * (MIN_TEXT_CHARS_PER_PAGE + 1)
    _write_pdf(pdf, [long_text, None])
    with patch("services.extract.markitdown_extract.try_markitdown", return_value=None) as md_mock:
        with patch("services.extract.pdf.ocr_pil_image_with_confidence", return_value=("ocr line", 0.9)):
            result = extract_pdf(str(pdf), file_id=99)
    md_mock.assert_not_called()
    assert result.ocr_stats is not None
    assert result.ocr_stats.pdf_class == "mixed"
    assert result.ocr_stats.ocr_used is True
    assert result.ocr_stats.ocr_page_count == 1
    assert result.engine == "pymupdf+rapidocr"


def test_ocr_stats_for_image():
    stats = ocr_stats_for_image()
    assert stats.pdf_class == "n/a"
    assert stats.ocr_used is True
    assert stats.ocr_page_count == 1
    assert stats.text_layer_page_count is None


def test_ocr_stats_for_sidecar_provider_text_layer_pdf(tmp_path):
    """text_layer PDF: ocr_page_count is None — must not compare None > 0 (mineru/docling post-parse)."""
    pdf = tmp_path / "sidecar-text.pdf"
    long_text = "s" * (MIN_TEXT_CHARS_PER_PAGE + 1)
    _write_pdf(pdf, [long_text, long_text])
    f = FileModel(
        id=1,
        user_id=1,
        filename="sidecar-text.pdf",
        original_name="sidecar-text.pdf",
        file_path=str(pdf),
    )
    stats = ocr_stats_for_sidecar_provider(f, ocr_engine="mineru-paddle")
    assert stats.pdf_class == "text_layer"
    assert stats.ocr_used is False
    assert stats.ocr_engine == "none"
    assert stats.ocr_page_count is None
    assert stats.text_layer_page_count == 2


def test_ocr_stats_for_sidecar_provider_scan_pdf(tmp_path):
    pdf = tmp_path / "sidecar-scan.pdf"
    _write_pdf(pdf, [None])
    f = FileModel(
        id=2,
        user_id=1,
        filename="sidecar-scan.pdf",
        original_name="sidecar-scan.pdf",
        file_path=str(pdf),
    )
    stats = ocr_stats_for_sidecar_provider(f, ocr_engine="mineru-paddle")
    assert stats.pdf_class == "scan"
    assert stats.ocr_used is True
    assert stats.ocr_engine == "mineru-paddle"
    assert stats.ocr_page_count == 1


def test_seed_kb_ocr_pipeline_routes_json():
    repo_root = Path(__file__).resolve().parents[2]
    raw = (repo_root / "scripts" / "seed-kb-ocr-pipeline-routes.json").read_text(encoding="utf-8")
    cfg = parse_pipeline_config(raw)
    assert cfg is not None
    assert len(cfg.routes) == 1
    assert cfg.routes[0].extract_provider == "mineru"
    assert cfg.routes[0].match.get("mime_prefix") == "application/pdf"


def test_run_extract_job_done_includes_ocr_fields(db_session, regular_user, tmp_path):
    pdf = tmp_path / "job.pdf"
    long_text = "b" * (MIN_TEXT_CHARS_PER_PAGE + 1)
    _write_pdf(pdf, [long_text])
    f = FileModel(
        user_id=regular_user.id,
        filename="job.pdf",
        original_name="job.pdf",
        file_path=str(pdf),
        file_size=100,
        mime_type="application/pdf",
    )
    db_session.add(f)
    db_session.flush()
    job = KbExtractJob(
        user_id=regular_user.id,
        file_id=f.id,
        status=JOB_QUEUED,
        provider="legacy",
        attempts=0,
    )
    db_session.add(job)
    db_session.commit()

    ocr_stats = ExtractOcrStats(
        ocr_used=False,
        ocr_engine="none",
        pdf_class="text_layer",
        text_layer_page_count=1,
    )
    fake = ExtractResult(text="# note\n", engine="pymupdf", ocr_stats=ocr_stats)

    with patch("services.extract.providers.registry.extract_with_provider", return_value=fake):
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
    assert "ocr_used=false" in row.detail
    assert "ocr_engine=none" in row.detail
    assert "pdf_class=text_layer" in row.detail
    assert "text_layer_page_count=1" in row.detail


def _run_extract_job_with_ocr_stats(
    db_session,
    regular_user,
    tmp_path,
    *,
    pdf_name: str,
    page_texts: list[str | None],
    provider: str,
    ocr_stats: ExtractOcrStats,
    engine: str,
) -> str:
    pdf = tmp_path / pdf_name
    _write_pdf(pdf, page_texts)
    f = FileModel(
        user_id=regular_user.id,
        filename=pdf_name,
        original_name=pdf_name,
        file_path=str(pdf),
        file_size=100,
        mime_type="application/pdf",
    )
    db_session.add(f)
    db_session.flush()
    job = KbExtractJob(
        user_id=regular_user.id,
        file_id=f.id,
        status=JOB_QUEUED,
        provider=provider,
        attempts=0,
    )
    db_session.add(job)
    db_session.commit()

    fake = ExtractResult(text="# note\n", engine=engine, ocr_stats=ocr_stats)

    with patch("services.extract.providers.registry.extract_with_provider", return_value=fake):
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
    return row.detail


def test_run_extract_job_done_scan_includes_ocr_fields(db_session, regular_user, tmp_path):
    """SC-P0-002: scan PDF legacy path DONE detail includes ocr_used and page counts."""
    detail = _run_extract_job_with_ocr_stats(
        db_session,
        regular_user,
        tmp_path,
        pdf_name="scan-job.pdf",
        page_texts=[None],
        provider="legacy",
        ocr_stats=ExtractOcrStats(
            ocr_used=True,
            ocr_engine="rapidocr",
            pdf_class="scan",
            ocr_page_count=2,
            text_layer_page_count=0,
        ),
        engine="pymupdf+rapidocr",
    )
    assert "ocr_used=true" in detail
    assert "ocr_engine=rapidocr" in detail
    assert "pdf_class=scan" in detail
    assert "ocr_page_count=2" in detail
    assert "text_layer_page_count=0" in detail


def test_run_extract_job_done_pdf_inspector_includes_fast_path_ocr_fields(
    db_session, regular_user, tmp_path
):
    detail = _run_extract_job_with_ocr_stats(
        db_session,
        regular_user,
        tmp_path,
        pdf_name="pdf-inspector-job.pdf",
        page_texts=["native text"],
        provider="legacy",
        ocr_stats=ExtractOcrStats(
            ocr_used=False,
            ocr_engine="none",
            pdf_class="text_layer",
            text_layer_page_count=1,
        ),
        engine="pdf-inspector",
    )
    assert "ocr_used=false" in detail
    assert "ocr_engine=none" in detail
    assert "pdf_class=text_layer" in detail
    assert "text_layer_page_count=1" in detail


def test_run_extract_job_done_mineru_includes_ocr_engine(db_session, regular_user, tmp_path):
    detail = _run_extract_job_with_ocr_stats(
        db_session,
        regular_user,
        tmp_path,
        pdf_name="mineru-job.pdf",
        page_texts=[None],
        provider="mineru",
        ocr_stats=ExtractOcrStats(
            ocr_used=True,
            ocr_engine="mineru-paddle",
            pdf_class="scan",
            ocr_page_count=1,
            text_layer_page_count=0,
        ),
        engine="mineru",
    )
    assert "ocr_engine=mineru-paddle" in detail
    assert "ocr_used=true" in detail


def test_run_extract_job_done_docling_includes_ocr_engine(db_session, regular_user, tmp_path):
    detail = _run_extract_job_with_ocr_stats(
        db_session,
        regular_user,
        tmp_path,
        pdf_name="docling-job.pdf",
        page_texts=[None],
        provider="docling",
        ocr_stats=ExtractOcrStats(
            ocr_used=True,
            ocr_engine="docling",
            pdf_class="scan",
            ocr_page_count=1,
            text_layer_page_count=0,
        ),
        engine="docling",
    )
    assert "ocr_engine=docling" in detail
    assert "ocr_used=true" in detail


def test_run_extract_job_done_includes_ocr_quality_low(db_session, regular_user, tmp_path):
    """SC-P2-002 / P2 Minor #3: DONE detail includes ocr_quality=low when set on ocr_stats."""
    detail = _run_extract_job_with_ocr_stats(
        db_session,
        regular_user,
        tmp_path,
        pdf_name="low-quality-scan.pdf",
        page_texts=[None],
        provider="legacy",
        ocr_stats=ExtractOcrStats(
            ocr_used=True,
            ocr_engine="rapidocr",
            pdf_class="scan",
            ocr_page_count=1,
            text_layer_page_count=0,
            ocr_quality="low",
        ),
        engine="pymupdf+rapidocr",
    )
    assert "ocr_quality=low" in detail
    assert "ocr_used=true" in detail


def test_run_extract_job_done_includes_ocr_review_recommended(db_session, regular_user, tmp_path):
    """SC-P3-001: low confidence → ocr_review_recommended in DONE detail."""
    detail = _run_extract_job_with_ocr_stats(
        db_session,
        regular_user,
        tmp_path,
        pdf_name="review-scan.pdf",
        page_texts=[None],
        provider="legacy",
        ocr_stats=ExtractOcrStats(
            ocr_used=True,
            ocr_engine="rapidocr",
            pdf_class="scan",
            ocr_page_count=1,
            text_layer_page_count=0,
            ocr_confidence_mean=0.42,
            ocr_review_recommended=True,
        ),
        engine="pymupdf+rapidocr",
    )
    assert "ocr_confidence_mean=0.42" in detail
    assert "ocr_review_recommended=true" in detail
