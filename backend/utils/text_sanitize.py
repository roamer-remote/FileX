# Copyright (c) 2026 徐泽宇
"""Sanitize text before PostgreSQL string columns (reject NUL bytes).

Authors:
    徐泽宇

Copyright:
    © 2026 徐泽宇
"""

from __future__ import annotations


def strip_nul_bytes(text: str) -> str:
    """Remove U+0000; psycopg2 raises ValueError if NUL is present in bound strings."""
    if not text or "\x00" not in text:
        return text
    return text.replace("\x00", "")
