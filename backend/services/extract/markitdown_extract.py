# Copyright (c) 2026 徐泽宇
"""markitdown_extract 业务逻辑模块。

Authors:
    徐泽宇
"""

from __future__ import annotations

import logging

from config import KB_MARKITDOWN_ENABLED
from services.extract.base import ExtractResult

logger = logging.getLogger(__name__)

try:
    from markitdown import MarkItDown
except ImportError:
    MarkItDown = None


def _result_text(result: object) -> str:
    for attr in ("text_content", "markdown"):
        val = getattr(result, attr, None)
        if isinstance(val, str) and val.strip():
            return val.strip()
    return ""


def try_markitdown(path: str, ext: str, *, file_id: int | None = None) -> ExtractResult | None:
    """Try MarkItDown on a local file. Returns None on skip, empty output, or failure."""
    if not KB_MARKITDOWN_ENABLED:
        return None
    if MarkItDown is None:
        logger.warning("markitdown not installed file_id=%s ext=%s", file_id, ext)
        return None
    try:
        converter = MarkItDown(enable_plugins=False)
        result = converter.convert_local(path)
        text = _result_text(result)
        if not text:
            logger.info("markitdown empty file_id=%s ext=%s", file_id, ext)
            return None
        logger.info("markitdown ok file_id=%s ext=%s", file_id, ext)
        return ExtractResult(text=text, engine="markitdown")
    except Exception as exc:
        logger.warning("markitdown failed file_id=%s ext=%s: %s", file_id, ext, exc)
        return None
