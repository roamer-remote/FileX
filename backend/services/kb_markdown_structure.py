# Copyright (c) 2026 徐泽宇
"""Markdown structure parsing for KB chunking.

Authors:
    徐泽宇

Copyright:
    © 2026 徐泽宇
"""

from __future__ import annotations

import re
from dataclasses import dataclass

from services.kb_heading_path import is_valid_markdown_heading_title

_HEADING_RE = re.compile(r"^(#{1,6})\s+(.+)$")
_FENCE_RE = re.compile(r"^```[\w-]*\s*$")


@dataclass(frozen=True)
class MdBlock:
    """Markdownblock 业务服务。

        Authors:
            徐泽宇

        Copyright:
            © 2026 徐泽宇

        Since:
            2026-05-22

        Attributes:
            text: 文本（str）。
            char_start: charstart（int）。
            char_end: charend（int）。
            block_type: block类型（str）。
            heading_path: heading路径（str | None）。
    """
    text: str
    char_start: int
    char_end: int
    block_type: str
    heading_path: str | None


def _block_type_for_text(text: str) -> str:
    lines = [ln.strip() for ln in text.strip().splitlines() if ln.strip()]
    if not lines:
        return "paragraph"
    if all(ln.startswith("|") and "|" in ln[1:] for ln in lines[: min(3, len(lines))]):
        return "table"
    if lines[0].startswith("```") or lines[-1].startswith("```"):
        return "code"
    hm = _HEADING_RE.match(lines[0])
    if hm and is_valid_markdown_heading_title(hm.group(2).strip()):
        return "heading"
    return "paragraph"


def split_markdown_blocks(body: str) -> list[MdBlock]:
    if not body.strip():
        return []

    lines = body.splitlines(keepends=True)
    heading_stack: list[tuple[int, str]] = []
    blocks: list[MdBlock] = []
    buf: list[str] = []
    buf_start = 0
    pos = 0
    in_fence = False

    def current_heading_path() -> str | None:
        if not heading_stack:
            return None
        return " > ".join(h for _, h in heading_stack)

    def flush(end_pos: int) -> None:
        nonlocal buf, buf_start
        raw = "".join(buf)
        if not raw.strip():
            buf = []
            return
        text = raw.strip()
        blocks.append(
            MdBlock(
                text=text,
                char_start=buf_start,
                char_end=end_pos,
                block_type=_block_type_for_text(text),
                heading_path=current_heading_path(),
            )
        )
        buf = []

    for line in lines:
        line_start = pos
        pos += len(line)
        stripped = line.strip()

        if _FENCE_RE.match(stripped):
            in_fence = not in_fence
            buf.append(line)
            continue

        if not in_fence:
            m = _HEADING_RE.match(stripped)
            if m:
                title = m.group(2).strip()
                if not is_valid_markdown_heading_title(title):
                    if not buf:
                        buf_start = line_start
                    buf.append(line)
                    continue
                flush(line_start)
                level = len(m.group(1))
                while heading_stack and heading_stack[-1][0] >= level:
                    heading_stack.pop()
                heading_stack.append((level, title))
                buf_start = line_start
                buf = [line]
                flush(pos)
                continue

            if not stripped and buf:
                flush(pos)
                buf_start = pos
                continue

        if not buf:
            buf_start = line_start
        buf.append(line)

    if buf:
        flush(pos)

    return blocks
