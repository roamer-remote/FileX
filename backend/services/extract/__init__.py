# Copyright (c) 2026 徐泽宇
"""Document text extraction for KB indexing (OCR, Office, no LLM).

Authors:
    徐泽宇

Copyright:
    © 2026 徐泽宇
"""

from __future__ import annotations

__all__ = ["extract_text_from_file"]


def extract_text_from_file(f, *, db=None):
    from services.extract.router import extract_text_from_file as _impl

    return _impl(f, db=db)
