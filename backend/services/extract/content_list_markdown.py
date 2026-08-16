# Copyright (c) 2026 徐泽宇
"""MinerU content_list → sidecar markdown (030)."""

from __future__ import annotations

from models.kb_enums import ContentKind
from services.extract.content_markers import format_content_marker
from services.extract.loc_markers import format_pdf_page_marker


def _page_marker(page_idx: int | None) -> str:
    if page_idx is None:
        return ""
    try:
        page = int(page_idx)
    except (TypeError, ValueError):
        return ""
    return format_pdf_page_marker(page + 1)


def _content_marker_page(page_idx: int | None) -> int | None:
    if page_idx is None:
        return None
    try:
        return int(page_idx) + 1
    except (TypeError, ValueError):
        return None


def _caption_text(caption_list: list | None) -> str | None:
    if not caption_list:
        return None
    parts = [str(x).strip() for x in caption_list if str(x).strip()]
    return " ".join(parts) if parts else None


def content_list_to_markdown(content_list: list[dict]) -> str:
    """Build human-readable MD with filex:loc / filex:content markers."""
    parts: list[str] = []
    for item in content_list:
        if not isinstance(item, dict):
            continue
        item_type = (item.get("type") or "").strip().lower()
        page_idx = item.get("page_idx")
        if item_type == "text":
            page_m = _page_marker(page_idx)
            if page_m:
                parts.append(page_m)
            text = (item.get("text") or "").strip()
            if text:
                parts.append(text)
                parts.append("")
            continue
        if item_type == "image":
            img_path = (item.get("img_path") or "").strip()
            if not img_path:
                continue
            page_m = _page_marker(page_idx)
            if page_m:
                parts.append(page_m)
            caption = _caption_text(item.get("image_caption"))
            asset_key = img_path.rsplit("/", 1)[-1]
            marker = format_content_marker(
                ContentKind.figure.value,
                page=_content_marker_page(page_idx),
                asset_key=asset_key,
                caption=caption,
            )
            alt = caption or asset_key
            parts.append(marker + f"![{alt}]({img_path})")
            parts.append("")
            continue
        if item_type == "table":
            body = (item.get("table_body") or "").strip()
            if not body:
                continue
            page_m = _page_marker(page_idx)
            if page_m:
                parts.append(page_m)
            caption = _caption_text(item.get("table_caption"))
            rotation_applied = item.get("rotation_applied")
            try:
                rotation_val = int(rotation_applied) if rotation_applied is not None else None
            except (TypeError, ValueError):
                rotation_val = None
            marker = format_content_marker(
                ContentKind.table.value,
                page=_content_marker_page(page_idx),
                caption=caption,
                rotation_applied=rotation_val,
            )
            parts.append(marker + body)
            parts.append("")
            continue
        if item_type == "equation":
            latex = (item.get("latex") or item.get("text") or "").strip()
            if not latex:
                continue
            page_m = _page_marker(page_idx)
            if page_m:
                parts.append(page_m)
            marker = format_content_marker(
                ContentKind.equation.value,
                page=_content_marker_page(page_idx),
            )
            parts.append(marker + f"```\n{latex}\n```")
            parts.append("")
    return "\n".join(parts).strip() + ("\n" if parts else "")
