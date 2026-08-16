# Copyright (c) 2026 徐泽宇
"""在 Markdown 正文中查找标签词出现位置（排除 fenced code 与行内代码）。

Authors:
    徐泽宇

Copyright:
    © 2026 徐泽宇
"""

from __future__ import annotations

from typing import List, Tuple

from utils.md_forbidden_ranges import md_forbidden_ranges, offset_in_forbidden


def iter_tag_occurrences_in_markdown(text: str, tag: str) -> List[Tuple[int, int]]:
    """
    返回 (start, end) 列表，end 为 exclusive；索引为 Python str 字符偏移（与 JS 字符串索引一致）。
    tag 应为已规范化小写；匹配大小写不敏感。
    """
    if not tag:
        return []
    forbidden = md_forbidden_ranges(text)
    tl = text.lower()
    needle = tag.lower()
    n = len(needle)
    if n == 0:
        return []
    spans: List[Tuple[int, int]] = []
    start = 0
    while True:
        idx = tl.find(needle, start)
        if idx < 0:
            break
        end = idx + n
        if not offset_in_forbidden(idx, end, forbidden):
            spans.append((idx, end))
        start = idx + 1
    return spans
