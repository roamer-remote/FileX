# Copyright (c) 2026 徐泽宇
"""filex:content markers for multimodal sidecar blocks (030)."""

from __future__ import annotations

import re
from dataclasses import dataclass

from services.extract.loc_markers import _parse_attrs

CONTENT_MARKER_PREFIX = "filex:content"
CONTENT_MARKER_RE = re.compile(r"<!--\s*filex:content\s+([^>]+?)\s*-->", re.IGNORECASE)


@dataclass(frozen=True)
class ContentMarkerSpan:
    char_start: int
    content_kind: str
    meta: dict[str, str]


def format_content_marker(
    kind: str,
    *,
    page: int | None = None,
    asset_key: str | None = None,
    caption: str | None = None,
    rotation_applied: int | None = None,
) -> str:
    parts = [f"kind={kind}"]
    if page is not None:
        parts.append(f"page={page}")
    if asset_key:
        parts.append(f"asset_key={asset_key}")
    if caption:
        safe = caption.replace('"', "'")[:200]
        parts.append(f'caption="{safe}"')
    if rotation_applied is not None:
        parts.append(f"rotation_applied={int(rotation_applied)}")
    return f"<!-- {CONTENT_MARKER_PREFIX} {' '.join(parts)} -->\n"


def parse_content_marker_line(line: str) -> tuple[str | None, dict[str, str]]:
    match = CONTENT_MARKER_RE.search(line.strip())
    if not match:
        return None, {}
    attrs = _parse_attrs(match.group(1))
    kind = (attrs.get("kind") or "").strip().lower()
    if not kind:
        return None, {}
    return kind, attrs


def find_content_marker_spans(body: str) -> list[ContentMarkerSpan]:
    spans: list[ContentMarkerSpan] = []
    for match in CONTENT_MARKER_RE.finditer(body or ""):
        kind, attrs = parse_content_marker_line(match.group(0))
        if not kind:
            continue
        spans.append(ContentMarkerSpan(char_start=match.start(), content_kind=kind, meta=attrs))
    return spans


def resolve_content_kind_for_char(
    spans: list[ContentMarkerSpan],
    char_start: int,
) -> tuple[str | None, dict[str, str] | None]:
    chosen: ContentMarkerSpan | None = None
    for span in spans:
        if span.char_start <= char_start:
            chosen = span
        else:
            break
    if chosen is None:
        return None, None
    return chosen.content_kind, dict(chosen.meta)


def content_meta_from_marker_attrs(attrs: dict[str, str], *, figure_path: str | None = None) -> dict:
    meta: dict[str, object] = {}
    if "page" in attrs:
        try:
            meta["page_idx"] = int(attrs["page"])
        except ValueError:
            pass
    if attrs.get("asset_key"):
        meta["asset_key"] = attrs["asset_key"]
    if attrs.get("caption"):
        meta["caption"] = attrs["caption"]
    if attrs.get("source_hash"):
        meta["source_hash"] = attrs["source_hash"].lower()
    if attrs.get("rotation_applied"):
        try:
            meta["rotation_applied"] = int(attrs["rotation_applied"])
        except ValueError:
            pass
    if figure_path:
        meta["figure_path"] = figure_path
    return meta
