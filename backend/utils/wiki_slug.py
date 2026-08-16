# Copyright (c) 2026 徐泽宇
"""Wiki slug 规范化。

Authors:
    徐泽宇

Copyright:
    © 2026 徐泽宇
"""

from __future__ import annotations

import re
import unicodedata

_MULTI_HYPHEN = re.compile(r"-{2,}")
_WS_UNDERSCORE = re.compile(r"[\s_]+")


def normalize_wiki_slug(raw: str) -> str:
    s = unicodedata.normalize("NFKC", (raw or "").strip())
    if not s:
        return ""
    s = s.lower()
    s = _WS_UNDERSCORE.sub("-", s)
    s = "".join(c for c in s if c == "-" or c.isalnum())
    s = _MULTI_HYPHEN.sub("-", s).strip("-")
    return s[:128]
