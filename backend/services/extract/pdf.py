# Copyright (c) 2026 徐泽宇
"""pdf 业务逻辑模块。

Authors:
    徐泽宇
"""

from __future__ import annotations

import logging

import fitz

from config import KB_EXTRACT_MAX_PAGES, KB_OCR_ENGINE, effective_ocr_pdf_dpi
from services.extract.base import ExtractResult
from services.extract.loc_markers import format_pdf_page_marker
from services.extract.ocr import ocr_pil_image_with_confidence
from services.extract.ocr_stats import ExtractOcrStats, finalize_ocr_stats, legacy_ocr_engine_name

logger = logging.getLogger(__name__)

MIN_TEXT_CHARS_PER_PAGE = 32
_MIN_TEXT_CHARS_PER_PAGE = MIN_TEXT_CHARS_PER_PAGE


def _page_text_char_count(page: fitz.Page) -> int:
    return len((page.get_text("text") or "").strip())


def classify_pdf_pages(path: str) -> ExtractOcrStats:
    """Per-page text-layer vs OCR classification (103 FR-P0-001)."""
    doc = fitz.open(path)
    try:
        page_count = min(doc.page_count, KB_EXTRACT_MAX_PAGES)
        text_layer_pages = 0
        ocr_pages = 0
        for i in range(page_count):
            page = doc.load_page(i)
            if _page_text_char_count(page) >= _MIN_TEXT_CHARS_PER_PAGE:
                text_layer_pages += 1
            else:
                ocr_pages += 1
    finally:
        doc.close()

    if ocr_pages == 0:
        pdf_class = "text_layer"
    elif text_layer_pages == 0:
        pdf_class = "scan"
    else:
        pdf_class = "mixed"

    ocr_used = ocr_pages > 0
    return ExtractOcrStats(
        ocr_used=ocr_used,
        ocr_engine=legacy_ocr_engine_name() if ocr_used else "none",
        pdf_class=pdf_class,
        ocr_page_count=ocr_pages if ocr_used else None,
        text_layer_page_count=text_layer_pages,
    )


def _pages_are_text_layer(doc: fitz.Document, page_count: int) -> bool:
    if page_count <= 0:
        return False
    for i in range(page_count):
        page = doc.load_page(i)
        if _page_text_char_count(page) < _MIN_TEXT_CHARS_PER_PAGE:
            return False
    return True


def build_pdf_marked_body(path: str, *, file_id: int | None = None) -> tuple[str, bool, float | None]:
    """Build sidecar text with per-page filex:loc markers (PyMuPDF path)."""
    doc = fitz.open(path)
    used_ocr = False
    page_confidences: list[float] = []
    try:
        page_count = min(doc.page_count, KB_EXTRACT_MAX_PAGES)
        parts: list[str] = []
        for i in range(page_count):
            page_num = i + 1
            page = doc.load_page(i)
            text = (page.get_text("text") or "").strip()
            if len(text) < _MIN_TEXT_CHARS_PER_PAGE:
                used_ocr = True
                dpi = effective_ocr_pdf_dpi()
                mat = fitz.Matrix(dpi / 72, dpi / 72)
                pix = page.get_pixmap(matrix=mat, alpha=False)
                from PIL import Image

                img = Image.frombytes("RGB", (pix.width, pix.height), pix.samples)
                text, conf = ocr_pil_image_with_confidence(img)
                text = (text or "").strip()
                if conf is not None:
                    page_confidences.append(conf)
            if not text:
                continue
            parts.append(format_pdf_page_marker(page_num) + text)
        confidence_mean = (
            round(sum(page_confidences) / len(page_confidences), 4) if page_confidences else None
        )
        return "\n\n".join(parts).strip(), used_ocr, confidence_mean
    finally:
        doc.close()


def _legacy_pdf_engine(*, used_ocr: bool) -> str:
    if not used_ocr:
        return "pymupdf"
    suffix = "paddleocr" if KB_OCR_ENGINE == "paddle" else "rapidocr"
    return f"pymupdf+{suffix}"


def extract_pdf(path: str, *, file_id: int | None = None, db=None) -> ExtractResult:
    from config import (
        KB_EXTRACT_MAX_PAGES,
        KB_PDF_INSPECTOR_MODE,
        KB_PDF_INSPECTOR_TIMEOUT_SEC,
    )
    from services.pdf_inspector_switch_service import get_pdf_inspector_enabled

    if get_pdf_inspector_enabled(db):
        from services.extract.providers.pdf_inspector_provider import inspect_pdf_with_fallback

        inspector_attempt = inspect_pdf_with_fallback(
            path,
            file_id=file_id,
            mode=KB_PDF_INSPECTOR_MODE,
            max_pages=KB_EXTRACT_MAX_PAGES,
            timeout_sec=KB_PDF_INSPECTOR_TIMEOUT_SEC,
        )
        if inspector_attempt.result is not None:
            return inspector_attempt.result
    else:
        inspector_attempt = None

    classification = classify_pdf_pages(path)
    doc = fitz.open(path)
    try:
        page_count = min(doc.page_count, KB_EXTRACT_MAX_PAGES)
        text_layer_only = _pages_are_text_layer(doc, page_count)
    finally:
        doc.close()

    markitdown_used = False
    if text_layer_only and file_id is not None:
        from services.extract.markitdown_extract import try_markitdown

        markitdown_used = try_markitdown(path, "pdf", file_id=file_id) is not None

    body, used_ocr, confidence_mean = build_pdf_marked_body(path, file_id=file_id)
    if markitdown_used:
        engine = "markitdown+pymupdf-loc"
        ocr_stats = ExtractOcrStats(
            ocr_used=False,
            ocr_engine="none",
            pdf_class=classification.pdf_class,
            ocr_page_count=None,
            text_layer_page_count=classification.text_layer_page_count,
        )
    else:
        engine = _legacy_pdf_engine(used_ocr=used_ocr)
        if used_ocr:
            ocr_stats = finalize_ocr_stats(
                ExtractOcrStats(
                    ocr_used=True,
                    ocr_engine=legacy_ocr_engine_name(),
                    pdf_class=classification.pdf_class,
                    ocr_page_count=classification.ocr_page_count,
                    text_layer_page_count=classification.text_layer_page_count,
                ),
                body,
                confidence_mean=confidence_mean,
            )
        else:
            ocr_stats = ExtractOcrStats(
                ocr_used=False,
                ocr_engine="none",
                pdf_class=classification.pdf_class,
                ocr_page_count=None,
                text_layer_page_count=classification.text_layer_page_count,
            )
    result = ExtractResult(text=body, engine=engine, ocr_stats=ocr_stats)
    if inspector_attempt is not None and inspector_attempt.fallback_reason:
        result.fallback_from = "pdf-inspector"
        result.fallback_reason = inspector_attempt.fallback_reason
    return result
