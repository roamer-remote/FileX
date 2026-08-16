# Copyright (c) 2026 徐泽宇
"""103 P1: OCR preprocess and effective OCR DPI."""

from __future__ import annotations

import importlib
import io
from pathlib import Path
from unittest.mock import patch

import fitz
import pytest
from PIL import Image, ImageDraw

from config import KB_EXTRACT_PDF_DPI, effective_ocr_pdf_dpi
from services.extract.pdf import build_pdf_marked_body


def _solid_png_bytes() -> bytes:
    img = Image.new("RGB", (120, 40), color="white")
    draw = ImageDraw.Draw(img)
    draw.text((8, 10), "OCR", fill="black")
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    return buf.getvalue()


def _reload_preprocess():
    import services.extract.ocr_preprocess as preprocess_mod

    importlib.reload(preprocess_mod)
    return preprocess_mod


def test_effective_ocr_pdf_dpi_defaults_to_extract_dpi(monkeypatch):
    monkeypatch.setattr("config.KB_OCR_PDF_DPI", None)
    monkeypatch.setattr("config.KB_OCR_PREPROCESS_ENABLED", False)
    assert effective_ocr_pdf_dpi() == KB_EXTRACT_PDF_DPI


def test_effective_ocr_pdf_dpi_explicit_300(monkeypatch):
    monkeypatch.setattr("config.KB_OCR_PDF_DPI", 300)
    monkeypatch.setattr("config.KB_OCR_PREPROCESS_ENABLED", False)
    assert effective_ocr_pdf_dpi() == 300


def test_effective_ocr_pdf_dpi_preprocess_fallback_300(monkeypatch):
    monkeypatch.setattr("config.KB_OCR_PDF_DPI", None)
    monkeypatch.setattr("config.KB_OCR_PREPROCESS_ENABLED", True)
    assert effective_ocr_pdf_dpi() == 300


def test_preprocess_disabled_is_identity(monkeypatch):
    monkeypatch.setattr("config.KB_OCR_PREPROCESS_ENABLED", False)
    preprocess_mod = _reload_preprocess()
    raw = _solid_png_bytes()
    assert preprocess_mod.maybe_preprocess_image_bytes(raw) == raw
    with Image.open(io.BytesIO(raw)) as img:
        same = preprocess_mod.preprocess_pil_image(img)
        assert same.tobytes() == img.convert("RGB").tobytes()


def test_preprocess_contrast_changes_pixels_when_enabled(monkeypatch):
    monkeypatch.setattr("config.KB_OCR_PREPROCESS_ENABLED", True)
    monkeypatch.setattr("config.KB_OCR_PREPROCESS_CONTRAST", True)
    monkeypatch.setattr("config.KB_OCR_PREPROCESS_ROTATE", False)
    monkeypatch.setattr("config.KB_OCR_PREPROCESS_DESKEW", False)
    preprocess_mod = _reload_preprocess()
    raw = _solid_png_bytes()
    with Image.open(io.BytesIO(raw)) as img:
        processed_img = preprocess_mod.preprocess_pil_image(img)
    assert processed_img.tobytes() != img.convert("RGB").tobytes()


def test_pdf_ocr_pixmap_size_scales_with_dpi(tmp_path, monkeypatch):
    monkeypatch.setenv("KB_MARKITDOWN_ENABLED", "0")
    monkeypatch.setattr("config.KB_OCR_PDF_DPI", 300)
    monkeypatch.setattr("config.KB_OCR_PREPROCESS_ENABLED", False)
    pdf = tmp_path / "dpi.pdf"
    doc = fitz.open()
    doc.new_page(width=72, height=72)
    doc.save(str(pdf))
    doc.close()

    seen: list[tuple[int, int]] = []

    def _capture(img):
        seen.append(img.size)
        return "text", None

    with patch("services.extract.pdf.ocr_pil_image_with_confidence", side_effect=_capture):
        build_pdf_marked_body(str(pdf))
    assert seen
    w, h = seen[0]
    assert w == pytest.approx(300, rel=0.02)
    assert h == pytest.approx(300, rel=0.02)


def test_legacy_paddle_engine_strings(monkeypatch):
    monkeypatch.setattr("services.extract.pdf.KB_OCR_ENGINE", "paddle")
    monkeypatch.setattr("services.extract.ocr_stats.KB_OCR_ENGINE", "paddle")
    from services.extract.ocr_stats import legacy_ocr_engine_name
    from services.extract.pdf import _legacy_pdf_engine

    assert legacy_ocr_engine_name() == "paddleocr"
    assert _legacy_pdf_engine(used_ocr=True) == "pymupdf+paddleocr"


FIXTURE_DIR = Path(__file__).resolve().parent / "fixtures" / "ocr_preprocess"
SAMPLE_PNG = FIXTURE_DIR / "sample.png"
# Stable mock OCR output for master-equivalent regression (SC-P1-001).
MASTER_EQUIVALENT_OCR_TEXT = "filex-ocr-baseline-fixture"


def test_fixture_sample_png_exists():
    assert SAMPLE_PNG.is_file()
    assert SAMPLE_PNG.stat().st_size > 0


def test_sc_p1_001_master_equivalent_image_ocr_path(monkeypatch):
    """SC-P1-001: preprocess off + no KB_OCR_PDF_DPI → fixture bytes unchanged → OCR baseline."""
    monkeypatch.setattr("config.KB_OCR_PREPROCESS_ENABLED", False)
    monkeypatch.setattr("config.KB_OCR_PDF_DPI", None)
    preprocess_mod = _reload_preprocess()
    fixture_bytes = SAMPLE_PNG.read_bytes()
    assert preprocess_mod.maybe_preprocess_image_bytes(fixture_bytes) == fixture_bytes

    with patch("services.extract.ocr._ocr_raw_image_bytes", return_value=MASTER_EQUIVALENT_OCR_TEXT) as raw_mock:
        from services.extract.ocr import ocr_image_bytes

        assert ocr_image_bytes(fixture_bytes) == MASTER_EQUIVALENT_OCR_TEXT
    raw_mock.assert_called_once_with(fixture_bytes)


def test_sc_p1_001_master_equivalent_pdf_ocr_render_dpi(tmp_path, monkeypatch):
    """SC-P1-001: default config → OCR pixmap at KB_EXTRACT_PDF_DPI (200), not preprocess fallback."""
    monkeypatch.setenv("KB_MARKITDOWN_ENABLED", "0")
    monkeypatch.setattr("config.KB_OCR_PDF_DPI", None)
    monkeypatch.setattr("config.KB_OCR_PREPROCESS_ENABLED", False)
    assert effective_ocr_pdf_dpi() == KB_EXTRACT_PDF_DPI

    pdf = tmp_path / "baseline-scan.pdf"
    doc = fitz.open()
    doc.new_page(width=72, height=72)
    doc.save(str(pdf))
    doc.close()

    seen: list[tuple[int, int]] = []

    def _capture(img):
        seen.append(img.size)
        return MASTER_EQUIVALENT_OCR_TEXT, None

    with patch("services.extract.pdf.ocr_pil_image_with_confidence", side_effect=_capture):
        body, used_ocr, _confidence_mean = build_pdf_marked_body(str(pdf))
    assert used_ocr is True
    assert MASTER_EQUIVALENT_OCR_TEXT in body
    assert seen
    w, h = seen[0]
    assert w == pytest.approx(KB_EXTRACT_PDF_DPI, rel=0.02)
    assert h == pytest.approx(KB_EXTRACT_PDF_DPI, rel=0.02)


def test_liteparse_rapid_path_applies_preprocess_when_enabled(monkeypatch):
    monkeypatch.setattr("config.KB_OCR_PREPROCESS_ENABLED", True)
    monkeypatch.setattr("config.KB_OCR_PREPROCESS_CONTRAST", True)
    monkeypatch.setattr("config.KB_OCR_PREPROCESS_ROTATE", False)
    monkeypatch.setattr("config.KB_OCR_PREPROCESS_DESKEW", False)
    monkeypatch.setattr("services.extract.ocr.KB_OCR_ENGINE", "rapid")
    _reload_preprocess()
    fixture_bytes = SAMPLE_PNG.read_bytes()

    with patch("services.extract.ocr._rapid_ocr") as rapid_factory:
        engine = rapid_factory.return_value
        engine.return_value = ([], None)
        from services.extract.ocr import ocr_image_bytes_for_liteparse

        ocr_image_bytes_for_liteparse(fixture_bytes)
        called_bytes = engine.call_args[0][0]
        assert called_bytes != fixture_bytes


def test_liteparse_paddle_path_preprocesses_once(monkeypatch):
    """P1 follow-up Minor #5: paddle liteparse must not double-preprocess."""
    monkeypatch.setattr("config.KB_OCR_PREPROCESS_ENABLED", True)
    monkeypatch.setattr("config.KB_OCR_PREPROCESS_CONTRAST", True)
    monkeypatch.setattr("config.KB_OCR_PREPROCESS_ROTATE", False)
    monkeypatch.setattr("config.KB_OCR_PREPROCESS_DESKEW", False)
    monkeypatch.setattr("services.extract.ocr.KB_OCR_ENGINE", "paddle")
    _reload_preprocess()
    fixture_bytes = SAMPLE_PNG.read_bytes()
    preprocess_calls: list[bytes] = []

    def _track_preprocess(raw: bytes) -> bytes:
        preprocess_calls.append(raw)
        return raw

    with patch("services.extract.ocr_preprocess.maybe_preprocess_image_bytes", side_effect=_track_preprocess):
        with patch("services.extract.ocr._ocr_raw_image_bytes", return_value="paddle text") as raw_mock:
            from services.extract.ocr import ocr_image_bytes_for_liteparse

            items = ocr_image_bytes_for_liteparse(fixture_bytes)
    assert len(preprocess_calls) == 1
    raw_mock.assert_called_once_with(fixture_bytes)
    assert items and items[0]["text"] == "paddle text"


def test_fixture_dir_exists():
    assert FIXTURE_DIR.is_dir()
    assert SAMPLE_PNG in FIXTURE_DIR.iterdir()
