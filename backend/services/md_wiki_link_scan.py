# Copyright (c) 2026 徐泽宇
"""解析资料 Markdown 中的 Wiki 互链语法。

Authors:
    徐泽宇

Copyright:
    © 2026 徐泽宇
"""

from __future__ import annotations

import re
from dataclasses import dataclass

from utils.md_forbidden_ranges import md_forbidden_ranges, offset_in_forbidden
from utils.wiki_slug import normalize_wiki_slug

# [[123]] | [[file:123]] | [[wiki:slug]] | [[text|123]] | [[text|wiki:slug]]
_WIKI_LINK_RE = re.compile(
    r"\[\[(?:([^\]|]+)\|)?(\d+)\]\]"
    r"|\[\[(?:([^\]|]+)\|)?file:(\d+)\]\]"
    r"|\[\[(?:([^\]|]+)\|)?wiki:([^\]\|]+)\]\]",
    re.IGNORECASE,
)

# OKF bundle 内部 Markdown 链接（P1 双语法，与 okf/links.py 对齐）
_OKF_ABS_MD_LINK_RE = re.compile(r"\[([^\]]*)\]\((/[a-zA-Z0-9_./\-]+\.md)\)")
_OKF_REL_MD_LINK_RE = re.compile(
    r"\[([^\]]*)\]\((\./[a-zA-Z0-9_./\-]+\.md|\.\./[a-zA-Z0-9_./\-]+\.md|[a-zA-Z0-9_./\-]+\.md)\)"
)


@dataclass(frozen=True)
class WikiLinkOccurrence:
    """Wiki链接occurrence 业务服务。

        Authors:
            徐泽宇

        Copyright:
            © 2026 徐泽宇

        Since:
            2026-06-01

        Attributes:
            link_kind: 链接类型（str）。
            link_text: 链接文本（str | None）。
            raw_target: raw目标（str）。
            start: start（int）。
            end: end（int）。
    """
    link_kind: str  # file_id | wiki_slug | okf_path
    link_text: str | None
    raw_target: str
    start: int
    end: int


def _span_overlaps_existing(start: int, end: int, spans: list[tuple[int, int]]) -> bool:
    for s, e in spans:
        if start < e and end > s:
            return True
    return False


def _scan_wiki_bracket_links(text: str, forbidden: list[tuple[int, int]]) -> list[WikiLinkOccurrence]:
    out: list[WikiLinkOccurrence] = []
    for m in _WIKI_LINK_RE.finditer(text):
        if offset_in_forbidden(m.start(), m.end(), forbidden):
            continue
        groups = m.groups()
        if groups[1] is not None:
            out.append(
                WikiLinkOccurrence(
                    link_kind="file_id",
                    link_text=groups[0],
                    raw_target=groups[1],
                    start=m.start(),
                    end=m.end(),
                )
            )
        elif groups[3] is not None:
            out.append(
                WikiLinkOccurrence(
                    link_kind="file_id",
                    link_text=groups[2],
                    raw_target=groups[3],
                    start=m.start(),
                    end=m.end(),
                )
            )
        elif groups[5] is not None:
            slug = normalize_wiki_slug(groups[5])
            if not slug:
                continue
            out.append(
                WikiLinkOccurrence(
                    link_kind="wiki_slug",
                    link_text=groups[4],
                    raw_target=slug,
                    start=m.start(),
                    end=m.end(),
                )
            )
    return out


def _scan_okf_md_links(text: str, forbidden: list[tuple[int, int]]) -> list[WikiLinkOccurrence]:
    out: list[WikiLinkOccurrence] = []
    seen_spans: list[tuple[int, int]] = []
    for regex in (_OKF_ABS_MD_LINK_RE, _OKF_REL_MD_LINK_RE):
        for m in regex.finditer(text):
            start, end = m.start(), m.end()
            if offset_in_forbidden(start, end, forbidden):
                continue
            if (start, end) in seen_spans:
                continue
            link_text = m.group(1)
            out.append(
                WikiLinkOccurrence(
                    link_kind="okf_path",
                    link_text=link_text if link_text else None,
                    raw_target=m.group(2),
                    start=start,
                    end=end,
                )
            )
            seen_spans.append((start, end))
    return out


def scan_wiki_links_in_markdown(text: str) -> list[WikiLinkOccurrence]:
    forbidden = md_forbidden_ranges(text)
    wiki = _scan_wiki_bracket_links(text, forbidden)
    occupied = [(o.start, o.end) for o in wiki]
    okf = [
        o
        for o in _scan_okf_md_links(text, forbidden)
        if not _span_overlaps_existing(o.start, o.end, occupied)
    ]
    merged = wiki + okf
    merged.sort(key=lambda o: o.start)
    return merged

def replace_wiki_slug_in_markdown(text: str, old_slug: str, new_slug: str) -> tuple[str, int]:
    """将笔记中的 [[wiki:old]] 替换为 [[wiki:new]]，保留可选显示文本。"""
    old_n = normalize_wiki_slug(old_slug)
    new_n = normalize_wiki_slug(new_slug)
    if not old_n or not new_n or old_n == new_n:
        return text, 0

    forbidden = md_forbidden_ranges(text)
    parts: list[str] = []
    last = 0
    replaced = 0
    for occ in scan_wiki_links_in_markdown(text):
        if occ.link_kind != "wiki_slug" or occ.raw_target != old_n:
            continue
        if offset_in_forbidden(occ.start, occ.end, forbidden):
            continue
        parts.append(text[last:occ.start])
        if occ.link_text:
            parts.append(f"[[{occ.link_text}|wiki:{new_n}]]")
        else:
            parts.append(f"[[wiki:{new_n}]]")
        last = occ.end
        replaced += 1
    parts.append(text[last:])
    return "".join(parts), replaced

