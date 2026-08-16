# Copyright (c) 2026 徐泽宇
"""Heuristic OCR quality assessment for legacy extract paths (103 P2).

v1 signals: empty/short lines, garbled ratio, Latin alpha ratio.
Empty-page ratio deferred (needs per-page metadata from PDF path).
Quality thresholds are module constants; review threshold is env
``KB_OCR_REVIEW_CONFIDENCE_THRESHOLD`` (103 P3, via ``finalize_ocr_stats``).
"""

from __future__ import annotations

import re

_CJK_RE = re.compile(r"[\u4e00-\u9fff]")
_GARBLED_RE = re.compile(r"[^\w\s\u4e00-\u9fff]", re.UNICODE)

_MIN_AVG_LINE_LEN = 4
_MIN_TOTAL_CHARS = 20
_GARBLED_RATIO_THRESHOLD = 0.45


def assess_ocr_quality(text: str) -> str | None:
    """Return ``low`` when OCR output looks unreliable; otherwise ``None``."""
    stripped = (text or "").strip()
    if not stripped:
        return "low"
    lines = [ln.strip() for ln in stripped.splitlines() if ln.strip()]
    if not lines:
        return "low"
    content = "".join(lines)
    if len(content) < _MIN_TOTAL_CHARS:
        return "low"
    avg_len = sum(len(ln) for ln in lines) / len(lines)
    if avg_len < _MIN_AVG_LINE_LEN:
        return "low"
    garbled = len(_GARBLED_RE.findall(content))
    if garbled / len(content) > _GARBLED_RATIO_THRESHOLD:
        return "low"
    if _CJK_RE.search(content):
        return None
    alpha = sum(1 for c in content if c.isalpha())
    if alpha / len(content) < 0.3:
        return "low"
    return None
