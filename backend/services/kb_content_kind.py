# Copyright (c) 2026 徐泽宇
"""Assign content_kind / content_meta to text chunks from filex:content markers (030)."""

from __future__ import annotations

from services.extract.content_markers import (
    content_meta_from_marker_attrs,
    find_content_marker_spans,
    resolve_content_kind_for_char,
)
from services.kb_chunking import TextChunk


def enrich_chunks_with_content_metadata(body: str, pieces: list[TextChunk]) -> list[tuple[TextChunk, str | None, dict | None]]:
    spans = find_content_marker_spans(body)
    out: list[tuple[TextChunk, str | None, dict | None]] = []
    for piece in pieces:
        kind, attrs = resolve_content_kind_for_char(spans, piece.char_start)
        meta = None
        if kind and attrs:
            figure_path = None
            if kind == "figure" and attrs.get("asset_key"):
                figure_path = attrs.get("asset_key")
            meta = content_meta_from_marker_attrs(attrs, figure_path=figure_path)
            if not meta:
                meta = None
        out.append((piece, kind, meta))
    return out
