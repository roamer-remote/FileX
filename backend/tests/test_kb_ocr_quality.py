# Copyright (c) 2026 徐泽宇
"""103 P2: OCR quality heuristic and pipeline detail."""

from __future__ import annotations

from services.extract.ocr_quality import assess_ocr_quality
from services.extract.ocr_stats import ExtractOcrStats, attach_ocr_quality, finalize_ocr_stats


def test_assess_ocr_quality_good_text():
    text = "这是一段足够长的中文 OCR 识别结果，用于验证质量启发式不会误报低质量。"
    assert assess_ocr_quality(text) is None


def test_assess_ocr_quality_low_on_garbage():
    text = "@#$\n%^\n&*(\n"
    assert assess_ocr_quality(text) == "low"


def test_assess_ocr_quality_low_on_empty():
    assert assess_ocr_quality("") == "low"
    assert assess_ocr_quality("   \n\n  ") == "low"


def test_attach_ocr_quality_skips_when_no_ocr():
    stats = ExtractOcrStats(
        ocr_used=False,
        ocr_engine="none",
        pdf_class="text_layer",
        text_layer_page_count=1,
    )
    assert attach_ocr_quality(stats, "@#$ garbage") == stats


def test_attach_ocr_quality_sets_low_in_pipeline_fields():
    stats = ExtractOcrStats(
        ocr_used=True,
        ocr_engine="rapidocr",
        pdf_class="scan",
        ocr_page_count=1,
    )
    enriched = attach_ocr_quality(stats, "@#$\n%^\n&*(\n")
    assert enriched.ocr_quality == "low"
    assert enriched.pipeline_detail_fields()["ocr_quality"] == "low"


def test_finalize_ocr_stats_low_confidence_recommends_review(monkeypatch):
    monkeypatch.setattr("config.KB_OCR_REVIEW_CONFIDENCE_THRESHOLD", 0.75)
    stats = ExtractOcrStats(
        ocr_used=True,
        ocr_engine="rapidocr",
        pdf_class="scan",
        ocr_page_count=1,
    )
    good_text = "这是一段足够长的中文 OCR 识别结果，用于验证质量启发式不会误报低质量。"
    enriched = finalize_ocr_stats(stats, good_text, confidence_mean=0.5)
    assert enriched.ocr_confidence_mean == 0.5
    assert enriched.ocr_review_recommended is True
    fields = enriched.pipeline_detail_fields()
    assert fields["ocr_confidence_mean"] == 0.5
    assert fields["ocr_review_recommended"] is True


def test_finalize_ocr_stats_quality_low_recommends_review():
    stats = ExtractOcrStats(
        ocr_used=True,
        ocr_engine="rapidocr",
        pdf_class="scan",
        ocr_page_count=1,
    )
    enriched = finalize_ocr_stats(stats, "@#$\n%^\n&*(\n", confidence_mean=0.95)
    assert enriched.ocr_quality == "low"
    assert enriched.ocr_review_recommended is True
