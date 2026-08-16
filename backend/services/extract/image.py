# Copyright (c) 2026 徐泽宇
"""image 业务逻辑模块。

Authors:
    徐泽宇
"""

from __future__ import annotations

from services.extract.base import ExtractResult
from services.extract.ocr import _ocr_raw_with_confidence
from services.extract.ocr_stats import finalize_ocr_stats, legacy_ocr_engine_name, ocr_stats_for_image


def extract_image(path: str) -> ExtractResult:
    with open(path, "rb") as fh:
        data = fh.read()
    from services.extract.ocr_preprocess import maybe_preprocess_image_bytes

    processed = maybe_preprocess_image_bytes(data)
    text, confidence_mean = _ocr_raw_with_confidence(processed)
    engine = legacy_ocr_engine_name()
    ocr_stats = finalize_ocr_stats(
        ocr_stats_for_image(),
        text,
        confidence_mean=confidence_mean,
    )
    return ExtractResult(text=text, engine=engine, ocr_stats=ocr_stats)
