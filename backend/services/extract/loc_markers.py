# Copyright (c) 2026 徐泽宇
"""Sidecar location markers for paginated extract types (025).

Authors:
    徐泽宇

Copyright:
    © 2026 徐泽宇
"""

from __future__ import annotations

import re
from dataclasses import dataclass

LOC_MARKER_PREFIX = "filex:loc"
LOC_MARKER_RE = re.compile(r"<!--\s*filex:loc\s+([^>]+?)\s*-->", re.IGNORECASE)
_ATTR_RE = re.compile(
    r'(\w+)=("(?:\\.|[^"\\])*"|[^\s]+)',
)

@dataclass(frozen=True)
class ChunkLocation:
    loc_type: str | None = None
    loc_start: int | None = None
    loc_end: int | None = None
    loc_label: str | None = None


def _escape_sheet_name(name: str) -> str:
    return name.replace("\\", "\\\\").replace('"', '\\"')


def format_pdf_page_marker(page: int) -> str:
    return f"<!-- {LOC_MARKER_PREFIX} type=pdf_page page={page} -->\n"


def format_slide_marker(slide: int) -> str:
    return f"<!-- {LOC_MARKER_PREFIX} type=slide slide={slide} -->\n"


def format_sheet_marker(sheet_index: int, sheet_name: str) -> str:
    safe_name = _escape_sheet_name(sheet_name or "")
    return f'<!-- {LOC_MARKER_PREFIX} type=sheet sheet_index={sheet_index} sheet_name="{safe_name}" -->\n'


def _parse_attrs(raw: str) -> dict[str, str]:
    out: dict[str, str] = {}
    for match in _ATTR_RE.finditer(raw.strip()):
        key = match.group(1)
        val = match.group(2)
        if val.startswith('"') and val.endswith('"'):
            val = val[1:-1].replace('\\"', '"').replace("\\\\", "\\")
        out[key] = val
    return out


def location_from_marker_attrs(attrs: dict[str, str]) -> ChunkLocation | None:
    loc_type = attrs.get("type")
    if loc_type == "pdf_page":
        page = int(attrs["page"])
        return ChunkLocation(loc_type="pdf_page", loc_start=page, loc_end=page)
    if loc_type == "slide":
        slide = int(attrs["slide"])
        return ChunkLocation(loc_type="slide", loc_start=slide, loc_end=slide)
    if loc_type == "sheet":
        idx = int(attrs["sheet_index"])
        name = attrs.get("sheet_name") or ""
        return ChunkLocation(loc_type="sheet", loc_start=idx, loc_end=idx, loc_label=name)
    return None


def parse_loc_marker_line(line: str) -> ChunkLocation | None:
    match = LOC_MARKER_RE.search(line.strip())
    if not match:
        return None
    return location_from_marker_attrs(_parse_attrs(match.group(1)))


def body_has_loc_markers(text: str) -> bool:
    return LOC_MARKER_PREFIX in (text or "")


def split_body_by_loc_markers(body: str) -> list[tuple[ChunkLocation | None, str]]:
    """Split markdown body into segments; each segment inherits preceding marker loc."""
    if not body:
        return []

    parts: list[tuple[ChunkLocation | None, str]] = []
    current_loc: ChunkLocation | None = None
    buf: list[str] = []
    pos = 0
    while pos < len(body):
        if body.startswith("<!--", pos):
            end = body.find("-->", pos)
            if end == -1:
                buf.append(body[pos:])
                break
            line = body[pos : end + 3]
            loc = parse_loc_marker_line(line)
            if loc is not None:
                if buf:
                    segment = "".join(buf)
                    if segment.strip():
                        parts.append((current_loc, segment))
                    buf = []
                current_loc = loc
                pos = end + 3
                continue
        buf.append(body[pos])
        pos += 1

    if buf:
        segment = "".join(buf)
        if segment.strip():
            parts.append((current_loc, segment))
    if not parts and body.strip():
        parts.append((None, body))
    return parts


def strip_loc_marker_lines(text: str) -> str:
    lines = []
    for line in text.splitlines(keepends=True):
        if parse_loc_marker_line(line) is not None:
            continue
        lines.append(line)
    return "".join(lines)
