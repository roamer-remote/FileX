# Copyright (c) 2026 徐泽宇
"""Markdown 中不可解析链接/标签的正文区间（fenced code 与行内代码）。

Authors:
    徐泽宇

Copyright:
    © 2026 徐泽宇
"""

from __future__ import annotations

import re
from typing import List, Tuple


def merge_ranges(ranges: List[Tuple[int, int]]) -> List[Tuple[int, int]]:
    if not ranges:
        return []
    sorted_r = sorted(ranges, key=lambda x: (x[0], x[1]))
    out: List[Tuple[int, int]] = [sorted_r[0]]
    for s, e in sorted_r[1:]:
        ps, pe = out[-1]
        if s <= pe:
            out[-1] = (ps, max(pe, e))
        else:
            out.append((s, e))
    return out


def fenced_code_ranges(text: str) -> List[Tuple[int, int]]:
    ranges: List[Tuple[int, int]] = []
    i = 0
    while True:
        j = text.find("```", i)
        if j < 0:
            break
        k = text.find("```", j + 3)
        if k < 0:
            break
        ranges.append((j, k + 3))
        i = k + 3
    return ranges


def inline_code_ranges(text: str) -> List[Tuple[int, int]]:
    ranges: List[Tuple[int, int]] = []
    for m in re.finditer(r"`([^`\n]*)`", text):
        ranges.append((m.start(), m.end()))
    return ranges


def md_forbidden_ranges(text: str) -> List[Tuple[int, int]]:
    return merge_ranges(fenced_code_ranges(text) + inline_code_ranges(text))


def offset_in_forbidden(offset: int, end: int, forbidden: List[Tuple[int, int]]) -> bool:
    for a, b in forbidden:
        if offset < b and end > a:
            return True
    return False
