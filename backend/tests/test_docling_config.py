# Copyright (c) 2026 徐泽宇
"""070: Docling config defaults."""

from __future__ import annotations

from config import (
    KB_EXTRACT_DOCLING_CACHE_MOUNT,
    KB_EXTRACT_DOCLING_HTTP_TIMEOUT_SEC,
    KB_EXTRACT_DOCLING_TIMEOUT_SEC,
    KB_EXTRACT_DOCLING_USE_MQ,
)


def test_docling_config_timeout_defaults():
    assert KB_EXTRACT_DOCLING_USE_MQ is False
    assert KB_EXTRACT_DOCLING_TIMEOUT_SEC == 600.0
    assert KB_EXTRACT_DOCLING_HTTP_TIMEOUT_SEC == 630.0
    assert KB_EXTRACT_DOCLING_CACHE_MOUNT == "/docling-cache"
