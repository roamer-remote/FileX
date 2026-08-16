# Copyright (c) 2026 徐泽宇
"""Docling sidecar content_list → 030 MinerU-compatible blocks (050)."""

from __future__ import annotations

import logging
from typing import Any

logger = logging.getLogger(__name__)

_TEXT_TYPES = frozenset({"text", "paragraph", "title", "heading", "list_item", "caption"})
_IMAGE_TYPES = frozenset({"picture", "figure", "image", "fig"})
_TABLE_TYPES = frozenset({"table"})
_EQUATION_TYPES = frozenset({"formula", "equation", "math"})


def _norm_type(raw: Any) -> str:
    return str(raw or "").strip().lower()


def _page_idx(item: dict) -> int | None:
    for key in ("page_idx", "page", "page_no", "page_number"):
        if key not in item:
            continue
        try:
            val = int(item[key])
        except (TypeError, ValueError):
            continue
        if key in ("page", "page_no", "page_number") and val >= 1:
            return val - 1
        return val
    prov = item.get("prov")
    if isinstance(prov, list) and prov:
        first = prov[0]
        if isinstance(first, dict) and "page_no" in first:
            try:
                page = int(first["page_no"])
                return page - 1 if page >= 1 else page
            except (TypeError, ValueError):
                pass
    return None


def _caption_list(item: dict, *keys: str) -> list[str] | None:
    for key in keys:
        val = item.get(key)
        if val is None:
            continue
        if isinstance(val, list):
            parts = [str(x).strip() for x in val if str(x).strip()]
            return parts or None
        text = str(val).strip()
        if text:
            return [text]
    return None


def adapt_docling_block(raw: dict) -> dict | None:
    if not isinstance(raw, dict):
        return None
    item_type = _norm_type(raw.get("type") or raw.get("label") or raw.get("kind"))
    page_idx = _page_idx(raw)

    if item_type in _TEXT_TYPES:
        text = (raw.get("text") or raw.get("content") or raw.get("markdown") or "").strip()
        if not text:
            return None
        out: dict[str, Any] = {"type": "text", "text": text}
        if page_idx is not None:
            out["page_idx"] = page_idx
        return out

    if item_type in _IMAGE_TYPES:
        img_path = (raw.get("img_path") or raw.get("image_path") or raw.get("uri") or raw.get("path") or "").strip()
        if not img_path:
            logger.warning("skip docling image block missing img_path type=%s", item_type)
            return None
        out = {"type": "image", "img_path": img_path}
        if page_idx is not None:
            out["page_idx"] = page_idx
        caption = _caption_list(raw, "caption", "captions", "image_caption")
        if caption:
            out["image_caption"] = caption
        return out

    if item_type in _TABLE_TYPES:
        body = (
            raw.get("table_body")
            or raw.get("markdown")
            or raw.get("text")
            or raw.get("content")
            or ""
        )
        body = str(body).strip()
        if not body:
            return None
        out = {"type": "table", "table_body": body}
        if page_idx is not None:
            out["page_idx"] = page_idx
        caption = _caption_list(raw, "table_caption", "caption", "captions")
        if caption:
            out["table_caption"] = caption
        rotation = raw.get("rotation_applied")
        if rotation is not None:
            try:
                out["rotation_applied"] = int(rotation)
            except (TypeError, ValueError):
                pass
        return out

    if item_type in _EQUATION_TYPES:
        latex = (raw.get("latex") or raw.get("text") or raw.get("content") or "").strip()
        if not latex:
            return None
        out = {"type": "equation", "latex": latex}
        if page_idx is not None:
            out["page_idx"] = page_idx
        return out

    text = (raw.get("text") or raw.get("content") or "").strip()
    if text:
        out = {"type": "text", "text": text}
        if page_idx is not None:
            out["page_idx"] = page_idx
        return out
    return None


def adapt_docling_content_list(raw_list: list[dict] | None) -> list[dict]:
    if not raw_list:
        return []
    out: list[dict] = []
    for raw in raw_list:
        if not isinstance(raw, dict):
            continue
        adapted = adapt_docling_block(raw)
        if adapted is not None:
            out.append(adapted)
    return out
