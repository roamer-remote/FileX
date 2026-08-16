# Copyright (c) 2026 徐泽宇
"""Citation formatting for search hits (agent / MCP).

Authors:
    徐泽宇

Copyright:
    © 2026 徐泽宇
"""

from __future__ import annotations

from typing import Any, Literal

from services.extract.policy import A_TIER_EXTENSIONS
from services.file_service import get_extension


def _anchor_for_hit(hit: dict) -> str:
    chunk_id = hit.get("chunk_id")
    if chunk_id is not None:
        return f"chunk:{chunk_id}"
    return f"chunk_index:{hit.get('chunk_index', 0)}"


def _wrap_name(original_name: str) -> str:
    name = (original_name or "资料").strip() or "资料"
    return f"《{name}》"


def is_a_tier_original_name(original_name: str | None) -> bool:
    return get_extension(original_name or "") in A_TIER_EXTENSIONS


def build_citation_label(
    original_name: str,
    *,
    loc_type: str | None = None,
    loc_start: int | None = None,
    loc_end: int | None = None,
    loc_label: str | None = None,
) -> tuple[str, str, dict[str, Any] | None]:
    """Return (citation_tier, citation_label, location dict)."""
    wrapped = _wrap_name(original_name)

    if loc_type == "pdf_page" and loc_start is not None:
        page = int(loc_start)
        return (
            "paginated",
            f"{wrapped}第 {page} 页",
            {"type": "pdf_page", "page": page},
        )
    if loc_type == "slide" and loc_start is not None:
        slide = int(loc_start)
        return (
            "paginated",
            f"{wrapped}第 {slide} 张",
            {"type": "slide", "slide": slide},
        )
    if loc_type == "sheet" and loc_start is not None:
        idx = int(loc_start)
        sheet_name = (loc_label or "").strip()
        if sheet_name:
            label = f"{wrapped}第 {idx} 个工作表「{sheet_name}」"
        else:
            label = f"{wrapped}第 {idx} 个工作表"
        location: dict[str, Any] = {"type": "sheet", "sheet_index": idx}
        if sheet_name:
            location["sheet_name"] = sheet_name
        return ("paginated", label, location)

    return ("document_only", wrapped, None)


def attach_citation_fields_to_hit(hit: dict, *, original_name: str) -> dict:
    tier, label, location = build_citation_label(
        original_name,
        loc_type=hit.get("loc_type"),
        loc_start=hit.get("loc_start"),
        loc_end=hit.get("loc_end"),
        loc_label=hit.get("loc_label"),
    )
    if tier == "document_only" and is_a_tier_original_name(original_name) and not hit.get("loc_type"):
        hit.setdefault("_citation_degraded", True)
    hit["citation_tier"] = tier
    hit["citation_label"] = label
    hit["location"] = location
    return hit


def format_hit_citation(hit: dict, *, fmt: Literal["markdown", "json"]) -> str | dict:
    base = {
        "file_id": hit["file_id"],
        "chunk_id": hit.get("chunk_id"),
        "chunk_index": hit.get("chunk_index"),
        "original_name": hit.get("original_name"),
        "heading_path": hit.get("heading_path"),
        "score": hit.get("score"),
        "anchor": _anchor_for_hit(hit),
        "text_preview": (hit.get("text") or "")[:500],
        "citation_label": hit.get("citation_label"),
    }
    if fmt == "json":
        return base
    heading = hit.get("heading_path") or hit.get("original_name") or f"file:{hit['file_id']}"
    preview = (hit.get("text") or "").replace("\n", " ").strip()[:240]
    return f"- [{heading}](filex://file/{hit['file_id']}#{base['anchor']}) score={hit.get('score')}: {preview}"


def attach_citations(items: list[dict], fmt: Literal["markdown", "json"]) -> list[dict]:
    out: list[dict] = []
    for hit in items:
        row = dict(hit)
        row["citation"] = format_hit_citation(hit, fmt=fmt)
        out.append(row)
    return out
