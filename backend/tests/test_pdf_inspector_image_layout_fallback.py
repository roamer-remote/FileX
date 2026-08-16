# Copyright (c) 2026 徐泽宇
"""179: pdf-inspector fast-path eligibility tightened for images / multi-column."""

from __future__ import annotations

from unittest.mock import patch

import fitz

from services.extract.providers.pdf_inspector_provider import (
    PdfInspection,
    _supplementary_fallback_reason,
    _supplementary_layout_scan,
    _page_has_columns,
    inspect_pdf_with_fallback,
    PDF_INSPECTOR_MIN_IMAGE_PAGES,
)


def _inspection(**overrides) -> PdfInspection:
    base = dict(
        classification="text_based",
        confidence=0.98,
        page_count=4,
        pages_needing_ocr=(),
        has_encoding_issues=False,
        is_complex_layout=False,
        pages_with_tables=(),
        pages_with_columns=(),
        pages_with_images=(),
        supplementary_pages_with_columns=(),
    )
    base.update(overrides)
    return PdfInspection(**base)


def test_image_threshold_two_pages_triggers_images_detected():
    reason = _supplementary_fallback_reason(
        _inspection(pages_with_images=(1, 3))
    )
    assert reason == "images_detected"


def test_single_image_page_does_not_trigger_fallback():
    assert _supplementary_fallback_reason(_inspection(pages_with_images=(1,))) is None


def test_no_images_does_not_trigger_fallback():
    assert _supplementary_fallback_reason(_inspection()) is None


def test_majority_column_pages_triggers_columns_detected():
    reason = _supplementary_fallback_reason(
        _inspection(page_count=8, supplementary_pages_with_columns=(1, 2, 3, 4, 5))
    )
    assert reason == "columns_detected"


def test_few_column_pages_does_not_trigger_fallback():
    # 报告类单栏文档偶发一页近似分栏，不应误伤。
    assert (
        _supplementary_fallback_reason(
            _inspection(page_count=14, supplementary_pages_with_columns=(1, 2))
        )
        is None
    )


def test_image_fallback_takes_precedence_over_columns():
    assert (
        _supplementary_fallback_reason(
            _inspection(
                page_count=14,
                pages_with_images=(1, 2),
                supplementary_pages_with_columns=(1, 2),
            )
        )
        == "images_detected"
    )


def _pdf_with_images(path, pages_with_images, image_size=(200, 200)):
    doc = fitz.open()
    for idx in range(4):
        page = doc.new_page()
        if idx + 1 in pages_with_images:
            pix = fitz.Pixmap(fitz.csRGB, fitz.IRect(0, 0, image_size[0], image_size[1]))
            pix.set_rect(pix.irect, (180, 30, 30))
            page.insert_image(page.rect, pixmap=pix)
        else:
            page.insert_text((60, 60), "plain single column text line")
    doc.save(str(path))
    doc.close()


def test_supplementary_scan_detects_content_images(tmp_path):
    p = tmp_path / "img.pdf"
    _pdf_with_images(p, pages_with_images={1, 3})
    images, _columns = _supplementary_layout_scan(str(p))
    assert images == (1, 3)


def test_supplementary_scan_ignores_small_decorative_image(tmp_path):
    p = tmp_path / "logo.pdf"
    _pdf_with_images(p, pages_with_images={1}, image_size=(40, 40))
    images, _columns = _supplementary_layout_scan(str(p))
    assert images == ()


def _pdf_two_column(path):
    import textwrap

    doc = fitz.open()
    page = doc.new_page(width=595, height=842)
    body = (
        "The quick brown fox jumps over the lazy dog and continues with more words "
        "to form a real paragraph block inside each column region of this page. "
    )
    y = 70
    for _ in range(12):
        for x0 in (50, 320):
            for line in textwrap.wrap(body, width=28):
                page.insert_text((x0, y), line)
                y += 13
        y += 12
    doc.save(str(path))
    doc.close()


def test_page_has_columns_detects_two_column_layout(tmp_path):
    p = tmp_path / "two.pdf"
    _pdf_two_column(str(p))
    doc = fitz.open(str(p))
    try:
        assert _page_has_columns(doc[0]) is True
    finally:
        doc.close()


def test_supplementary_scan_detects_majority_column_document(tmp_path):
    p = tmp_path / "two.pdf"
    _pdf_two_column(str(p))
    _images, columns = _supplementary_layout_scan(str(p))
    assert columns, "two-column synthetic page should be flagged"


def test_scan_fails_open_when_path_missing(tmp_path):
    assert _supplementary_layout_scan(str(tmp_path / "nope.pdf")) == ((), ())


def test_eligible_inspection_with_images_falls_back(tmp_path):
    import os

    p = tmp_path / "empty.pdf"
    with fitz.open() as doc:
        doc.new_page()
        doc.new_page()
        doc.save(str(p))
    with patch(
        "services.extract.providers.pdf_inspector_provider._inspect_pdf",
        return_value=_inspection(pages_with_images=(1, 2), page_count=2),
    ), patch(
        "services.extract.providers.pdf_inspector_provider._extract_pages_markdown"
    ) as extract_pages:
        attempt = inspect_pdf_with_fallback(str(p), file_id=7, mode="extract")
    assert attempt.result is None
    assert attempt.fallback_reason == "images_detected"
    extract_pages.assert_not_called()
    os.remove(str(p))


def _pdf_with_logo_and_content(path, *, logo_pages, content_pages, total_pages=5):
    """Build a PDF where the same logo xref repeats on many pages plus distinct
    content images on specific pages."""
    doc = fitz.open()
    logo_pix = fitz.Pixmap(fitz.csRGB, fitz.IRect(0, 0, 150, 150))
    logo_pix.set_rect(logo_pix.irect, (200, 200, 200))
    content_pix = fitz.Pixmap(fitz.csRGB, fitz.IRect(0, 0, 300, 300))
    content_pix.set_rect(content_pix.irect, (30, 30, 180))
    for idx in range(total_pages):
        page = doc.new_page()
        if idx + 1 in logo_pages:
            page.insert_image(fitz.Rect(50, 50, 200, 200), pixmap=logo_pix)
        if idx + 1 in content_pages:
            page.insert_image(fitz.Rect(50, 50, 350, 350), pixmap=content_pix)
    doc.save(str(path))
    doc.close()


def test_repeated_logo_is_not_counted_as_content_image(tmp_path):
    # 同一 logo 出现在 5 页（>=3 页），仅 1 页有独立内容图。
    p = tmp_path / "logo.pdf"
    _pdf_with_logo_and_content(str(p), logo_pages={1, 2, 3, 4, 5}, content_pages={1})
    images, _columns = _supplementary_layout_scan(str(p))
    assert images == (1,), f"repeated logo should be excluded, got {images}"


def test_two_distinct_content_images_trigger_fallback(tmp_path):
    # 2 页各有独立内容图（不同 xref），应判为带图文档。
    p = tmp_path / "content.pdf"
    _pdf_with_logo_and_content(str(p), logo_pages=set(), content_pages={1, 2})
    images, _columns = _supplementary_layout_scan(str(p))
    assert images == (1, 2)
