# Copyright (c) 2026 徐泽宇
"""OCR telemetry for extract pipeline logs (103 P0)."""

from __future__ import annotations

from dataclasses import dataclass, replace
from typing import Any

from config import KB_OCR_ENGINE


@dataclass(frozen=True)
class ExtractOcrStats:
    ocr_used: bool
    ocr_engine: str
    pdf_class: str
    ocr_page_count: int | None = None
    text_layer_page_count: int | None = None
    ocr_quality: str | None = None
    ocr_confidence_mean: float | None = None
    ocr_review_recommended: bool | None = None

    def pipeline_detail_fields(self) -> dict[str, Any]:
        fields: dict[str, Any] = {
            "ocr_used": self.ocr_used,
            "ocr_engine": self.ocr_engine,
            "pdf_class": self.pdf_class,
        }
        if self.ocr_page_count is not None:
            fields["ocr_page_count"] = self.ocr_page_count
        if self.text_layer_page_count is not None:
            fields["text_layer_page_count"] = self.text_layer_page_count
        if self.ocr_quality is not None:
            fields["ocr_quality"] = self.ocr_quality
        if self.ocr_confidence_mean is not None:
            fields["ocr_confidence_mean"] = self.ocr_confidence_mean
        if self.ocr_review_recommended:
            fields["ocr_review_recommended"] = True
        return fields


def attach_ocr_quality(stats: ExtractOcrStats, text: str) -> ExtractOcrStats:
    if not stats.ocr_used:
        return stats
    from services.extract.ocr_quality import assess_ocr_quality

    quality = assess_ocr_quality(text)
    if quality is None:
        return stats
    return replace(stats, ocr_quality=quality)


def finalize_ocr_stats(
    stats: ExtractOcrStats,
    text: str,
    *,
    confidence_mean: float | None = None,
) -> ExtractOcrStats:
    """Apply quality heuristic + confidence review flag (103 P3)."""
    from config import KB_OCR_REVIEW_CONFIDENCE_THRESHOLD

    stats = attach_ocr_quality(stats, text)
    review = stats.ocr_quality == "low"
    if not review and confidence_mean is not None:
        review = confidence_mean < KB_OCR_REVIEW_CONFIDENCE_THRESHOLD
    return replace(
        stats,
        ocr_confidence_mean=confidence_mean,
        ocr_review_recommended=True if review else None,
    )


def legacy_ocr_engine_name() -> str:
    return "paddleocr" if KB_OCR_ENGINE == "paddle" else "rapidocr"


def ocr_stats_none() -> ExtractOcrStats:
    return ExtractOcrStats(ocr_used=False, ocr_engine="none", pdf_class="n/a")


def ocr_stats_for_image() -> ExtractOcrStats:
    return ExtractOcrStats(
        ocr_used=True,
        ocr_engine=legacy_ocr_engine_name(),
        pdf_class="n/a",
        ocr_page_count=1,
    )


def ocr_stats_for_sidecar_provider(
    f,
    *,
    ocr_engine: str,
) -> ExtractOcrStats:
    from services.extract.pdf import classify_pdf_pages
    from services.extract.policy import get_extension_from_file

    path = getattr(f, "file_path", None)
    if get_extension_from_file(f) == "pdf" and path:
        try:
            cls = classify_pdf_pages(path)
        except Exception:
            # Extraction already succeeded in the sidecar; telemetry must not turn
            # a malformed or unavailable local PDF into an extraction failure.
            return ExtractOcrStats(
                ocr_used=True,
                ocr_engine=ocr_engine,
                pdf_class="unknown",
            )
        return ExtractOcrStats(
            ocr_used=cls.ocr_used,
            ocr_engine=ocr_engine if cls.ocr_used else "none",
            pdf_class=cls.pdf_class,
            ocr_page_count=cls.ocr_page_count,
            text_layer_page_count=cls.text_layer_page_count,
        )
    return ExtractOcrStats(
        ocr_used=True,
        ocr_engine=ocr_engine,
        pdf_class="n/a",
        ocr_page_count=1,
    )
