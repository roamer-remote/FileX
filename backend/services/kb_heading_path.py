# Copyright (c) 2026 徐泽宇
"""Heading path normalization for KB chunk indexing (038).

Authors:
    徐泽宇
"""

from __future__ import annotations

import re

KB_HEADING_TITLE_MAX_LEN = 200
KB_HEADING_CODE_HEURISTIC_MIN_LEN = 80
KB_HEADING_PATH_MAX_LEN = 512
KB_HEADING_DEBUG_PREFIX_LEN = 80

_RE_DEF = re.compile(r"\bdef\s+")
_RE_CLASS = re.compile(r"\bclass\s+")
_RE_IMPORT = re.compile(r"(^|\s)(import|from)\s+")
_RE_DECORATOR = re.compile(r"@(app|router)\.")
_RE_ARROW = re.compile(r"->")
_RE_FAT_ARROW = re.compile(r"=>")
_RE_OCR_EQ = re.compile(r"\s=\$=\s")
_RE_MULTI_EQ = re.compile(r"={2,}")
_RE_DOLLAR_PAREN = re.compile(r"\$\(")


def cap_heading_path(value: str | None, *, max_len: int = KB_HEADING_PATH_MAX_LEN) -> str | None:
    """Truncate heading_path to DB limit (character-level, UTF-8 safe for str slice)."""
    if value is None:
        return None
    s = value.strip()
    if not s:
        return None
    if len(s) <= max_len:
        return s
    return s[:max_len]


def looks_like_code_heading(title: str) -> bool:
    """True when title looks like OCR/code line masquerading as a Markdown heading (FR-A-102)."""
    t = title.strip()
    n = len(t)
    if n <= KB_HEADING_CODE_HEURISTIC_MIN_LEN or n > KB_HEADING_TITLE_MAX_LEN:
        return False
    if _RE_DEF.search(t):
        return True
    if _RE_CLASS.search(t):
        return True
    if _RE_IMPORT.search(t):
        return True
    if _RE_DECORATOR.search(t):
        return True
    if "include_in_schema" in t:
        return True
    if _RE_ARROW.search(t):
        return True
    if _RE_FAT_ARROW.search(t):
        return True
    if _RE_OCR_EQ.search(t):
        return True
    if _RE_MULTI_EQ.search(t):
        return True
    if _RE_DOLLAR_PAREN.search(t):
        return True
    rs = t.rstrip()
    if (rs.endswith(");") or rs.endswith("})")) and t.count("(") >= 2:
        return True
    return False


def is_valid_markdown_heading_title(title: str) -> bool:
    """FR-A-101 + FR-A-102: whether a `#` line title should enter heading_stack."""
    t = title.strip()
    if not t:
        return False
    if len(t) > KB_HEADING_TITLE_MAX_LEN:
        return False
    return not looks_like_code_heading(t)
