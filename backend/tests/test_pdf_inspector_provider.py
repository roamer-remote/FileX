import builtins
from dataclasses import dataclass
from unittest.mock import patch

import pytest

from services.extract.base import ExtractResult
from services.extract.loc_markers import format_pdf_page_marker
from services.extract.ocr_stats import ExtractOcrStats
from services.extract.providers.pdf_inspector_provider import (
    PdfInspectorAttempt,
    build_pdf_marked_body,
    inspect_pdf_with_fallback,
    _run_native_call,
    try_extract_pdf_with_inspector,
)


@dataclass
class FakePage:
    markdown: str


@dataclass
class FakeInspection:
    classification: str = "text_based"
    confidence: float = 0.98
    page_count: int = 2
    pages_needing_ocr: list[int] | None = None
    has_encoding_issues: bool = False
    is_complex_layout: bool = False
    pages_with_tables: list[int] | None = None
    pages_with_columns: list[int] | None = None
    pages_with_images: list[int] | None = None
    supplementary_pages_with_columns: list[int] | None = None


def _hanging_worker(operation: str, path: str, conn) -> None:
    import time

    time.sleep(30)


def test_build_pdf_marked_body_keeps_empty_pages_and_uses_one_based_markers():
    body = build_pdf_marked_body(
        [FakePage("第一页"), FakePage(""), FakePage("第三页")],
        page_count=3,
    )

    assert body == "\n\n".join(
        [
            format_pdf_page_marker(1).rstrip("\n") + "\n第一页",
            format_pdf_page_marker(2).rstrip("\n"),
            format_pdf_page_marker(3).rstrip("\n") + "\n第三页",
        ]
    ).strip()


def test_inspector_high_confidence_text_pdf_returns_markdown():
    with patch(
        "services.extract.providers.pdf_inspector_provider._inspect_pdf",
        return_value=FakeInspection(),
    ), patch(
        "services.extract.providers.pdf_inspector_provider._extract_pages_markdown",
        return_value=[FakePage("第一页"), FakePage("第二页")],
    ):
        result = try_extract_pdf_with_inspector("/tmp/a.pdf", file_id=7, mode="extract")

    assert isinstance(result, ExtractResult)
    assert result.engine == "pdf-inspector"
    assert result.ocr_stats is not None
    assert result.ocr_stats.ocr_used is False
    assert result.ocr_stats.pdf_class == "text_layer"
    from services.kb_extract_service import _ocr_detail_fields

    assert _ocr_detail_fields(result) == {
        "ocr_used": False,
        "ocr_engine": "none",
        "pdf_class": "text_layer",
        "text_layer_page_count": 2,
    }
    assert result.text.count("type=pdf_page") == 2
    assert "page=1" in result.text and "page=2" in result.text


def test_inspector_scanned_pdf_falls_back_without_extracting_pages():
    with patch(
        "services.extract.providers.pdf_inspector_provider._inspect_pdf",
        return_value=FakeInspection(classification="scanned", confidence=0.99),
    ), patch(
        "services.extract.providers.pdf_inspector_provider._extract_pages_markdown",
    ) as extract_pages:
        result = try_extract_pdf_with_inspector("/tmp/a.pdf", file_id=7, mode="extract")

    assert result is None
    extract_pages.assert_not_called()


def test_inspector_fallback_exposes_structured_classification_reason():
    with patch(
        "services.extract.providers.pdf_inspector_provider._inspect_pdf",
        return_value=FakeInspection(classification="scanned", confidence=0.99),
    ):
        attempt = inspect_pdf_with_fallback("/tmp/a.pdf", file_id=7, mode="extract")

    assert isinstance(attempt, PdfInspectorAttempt)
    assert attempt.result is None
    assert attempt.fallback_reason == "classification=scanned"


def test_detect_only_is_observation_not_failure_fallback():
    with patch(
        "services.extract.providers.pdf_inspector_provider._inspect_pdf",
        return_value=FakeInspection(),
    ):
        attempt = inspect_pdf_with_fallback("/tmp/a.pdf", file_id=7, mode="detect-only")

    assert attempt.result is None
    assert attempt.fallback_reason is None


def test_detect_only_scanned_pdf_is_observation_not_failure_fallback():
    with patch(
        "services.extract.providers.pdf_inspector_provider._inspect_pdf",
        return_value=FakeInspection(classification="scanned", confidence=0.99),
    ):
        attempt = inspect_pdf_with_fallback("/tmp/a.pdf", file_id=7, mode="detect-only")

    assert attempt.result is None
    assert attempt.fallback_reason is None


def test_inspector_page_completeness_failure_falls_back():
    with patch(
        "services.extract.providers.pdf_inspector_provider._inspect_pdf",
        return_value=FakeInspection(page_count=2),
    ), patch(
        "services.extract.providers.pdf_inspector_provider._extract_pages_markdown",
        return_value=[FakePage("only page")],
    ):
        result = try_extract_pdf_with_inspector("/tmp/a.pdf", file_id=7, mode="extract")

    assert result is None


def test_inspector_page_order_mismatch_falls_back():
    with patch(
        "services.extract.providers.pdf_inspector_provider._inspect_pdf",
        return_value=FakeInspection(),
    ), patch(
        "services.extract.providers.pdf_inspector_provider._extract_pages_markdown",
        return_value=[FakePage("first"), FakePage("second")],
    ), patch(
        "services.extract.providers.pdf_inspector_provider._page_number",
        side_effect=[1, 1],
    ):
        result = try_extract_pdf_with_inspector("/tmp/a.pdf", file_id=7, mode="extract")

    assert result is None


def test_inspector_complex_layout_exposes_structured_fallback_reason():
    with patch(
        "services.extract.providers.pdf_inspector_provider._inspect_pdf",
        return_value=FakeInspection(is_complex_layout=True),
    ):
        attempt = inspect_pdf_with_fallback("/tmp/a.pdf", file_id=7, mode="extract")

    assert attempt.result is None
    assert attempt.fallback_reason == "complex_layout"


def test_inspector_rejects_page_count_mismatch(tmp_path):
    import fitz

    p = tmp_path / "one-page.pdf"
    doc = fitz.open()
    doc.new_page()
    doc.save(str(p))
    doc.close()
    with patch(
        "services.extract.providers.pdf_inspector_provider._inspect_pdf",
        return_value=FakeInspection(page_count=2),
    ):
        attempt = inspect_pdf_with_fallback(str(p), file_id=7, mode="extract")

    assert attempt.result is None
    assert attempt.fallback_reason == "page_count_mismatch"


def test_real_pdf_inspector_subprocess_preserves_page_markers(tmp_path):
    import fitz

    p = tmp_path / "real-native.pdf"
    doc = fitz.open()
    for _ in range(2):
        page = doc.new_page()
        page.insert_textbox(
            (50, 50, 550, 750),
            "Native text content for the pdf-inspector subprocess smoke test. " * 20,
        )
    doc.save(str(p))
    doc.close()

    result = try_extract_pdf_with_inspector(str(p), file_id=7, mode="extract")

    assert result is not None
    assert result.engine == "pdf-inspector"
    assert result.text.count("type=pdf_page") == 2
    assert "page=1" in result.text and "page=2" in result.text


def test_native_inspector_call_is_terminated_at_deadline():
    # Process startup + native import cannot complete within this deliberately
    # tiny deadline; the parent must terminate the child rather than wait.
    with pytest.raises(TimeoutError):
        _run_native_call("detect", "/tmp/a.pdf", timeout_sec=0.001)


def test_native_inspector_call_terminates_a_hung_worker():
    with pytest.raises(TimeoutError):
        _run_native_call(
            "detect",
            "/tmp/a.pdf",
            timeout_sec=0.05,
            worker=_hanging_worker,
        )


def test_native_timeout_becomes_bounded_fallback_reason():
    with patch(
        "services.extract.providers.pdf_inspector_provider._inspect_pdf",
        side_effect=TimeoutError("deadline exceeded"),
    ):
        attempt = inspect_pdf_with_fallback("/tmp/a.pdf", file_id=7, mode="extract")

    assert attempt.result is None
    assert attempt.fallback_reason == "error=TimeoutError"


def test_inspector_is_not_called_when_mode_is_off():
    with patch(
        "services.extract.providers.pdf_inspector_provider._inspect_pdf",
    ) as inspect_pdf:
        result = try_extract_pdf_with_inspector("/tmp/a.pdf", file_id=7, mode="off")

    assert result is None
    inspect_pdf.assert_not_called()


def test_disabled_pdf_inspector_path_does_not_import_adapter(tmp_path):
    import fitz

    p = tmp_path / "legacy.pdf"
    doc = fitz.open()
    doc.new_page()
    doc.save(str(p))
    doc.close()

    real_import = builtins.__import__

    def guarded_import(name, *args, **kwargs):
        if name == "services.extract.providers.pdf_inspector_provider":
            raise AssertionError("pdf-inspector adapter imported while disabled")
        return real_import(name, *args, **kwargs)

    with patch("services.pdf_inspector_switch_service.get_pdf_inspector_enabled", lambda db=None: False), patch(
        "builtins.__import__", side_effect=guarded_import
    ), patch("services.extract.markitdown_extract.try_markitdown", return_value=None):
        from services.extract.pdf import extract_pdf

        result = extract_pdf(str(p), file_id=7)

    assert result.engine.startswith("pymupdf")


def test_legacy_pdf_router_returns_inspector_result_when_enabled(tmp_path):
    import fitz

    p = tmp_path / "text.pdf"
    doc = fitz.open()
    doc.new_page()
    doc.save(str(p))
    doc.close()

    inspected = ExtractResult(
        text=format_pdf_page_marker(1) + "native text",
        engine="pdf-inspector",
        ocr_stats=ExtractOcrStats(
            ocr_used=False,
            ocr_engine="none",
            pdf_class="text_layer",
            text_layer_page_count=1,
        ),
    )
    with patch("services.pdf_inspector_switch_service.get_pdf_inspector_enabled", lambda db=None: True), patch(
        "config.KB_PDF_INSPECTOR_MODE", "extract"
    ), patch(
        "services.extract.providers.pdf_inspector_provider.inspect_pdf_with_fallback",
        return_value=PdfInspectorAttempt(inspected, None),
    ) as fast_path:
        from services.extract.pdf import extract_pdf

        result = extract_pdf(str(p), file_id=7)

    from config import KB_EXTRACT_MAX_PAGES

    fast_path.assert_called_once_with(
        str(p),
        file_id=7,
        mode="extract",
        max_pages=KB_EXTRACT_MAX_PAGES,
        timeout_sec=120.0,
    )
    assert result.engine == "pdf-inspector"


def test_legacy_pdf_router_records_inspector_fallback_reason(tmp_path):
    import fitz

    p = tmp_path / "text.pdf"
    doc = fitz.open()
    doc.new_page()
    doc.save(str(p))
    doc.close()

    with patch("services.pdf_inspector_switch_service.get_pdf_inspector_enabled", lambda db=None: True), patch(
        "config.KB_PDF_INSPECTOR_MODE", "extract"
    ), patch(
        "services.extract.providers.pdf_inspector_provider.inspect_pdf_with_fallback",
        return_value=PdfInspectorAttempt(None, "classification=scanned"),
    ), patch(
        "services.extract.pdf.classify_pdf_pages",
        return_value=ExtractOcrStats(
            ocr_used=False,
            ocr_engine="none",
            pdf_class="text_layer",
            text_layer_page_count=1,
        ),
    ), patch("services.extract.pdf._pages_are_text_layer", return_value=True), patch(
        "services.extract.pdf.build_pdf_marked_body",
        return_value=("<!-- filex:loc type=pdf_page page=1 -->\nlegacy", False, None),
    ), patch("services.extract.pdf.KB_MARKITDOWN_ENABLED", False, create=True):
        from services.extract.pdf import extract_pdf

        result = extract_pdf(str(p), file_id=7)

    assert result.fallback_from == "pdf-inspector"
    assert result.fallback_reason == "classification=scanned"
