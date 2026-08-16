# Copyright (c) 2026 徐泽宇
"""Minimal Notion block tree → Markdown (049 T-6 MVP)."""

from __future__ import annotations

from typing import Any


def _rich_text(parts: list[dict[str, Any]] | None) -> str:
    if not parts:
        return ""
    return "".join(p.get("plain_text", "") for p in parts)


def block_to_markdown(block: dict[str, Any], *, depth: int = 0) -> str:
    btype = block.get("type") or ""
    data = block.get(btype) or {}
    text = _rich_text(data.get("rich_text"))
    lines: list[str] = []

    if btype == "paragraph":
        lines.append(text or "")
    elif btype == "heading_1":
        lines.append(f"# {text}".rstrip())
    elif btype == "heading_2":
        lines.append(f"## {text}".rstrip())
    elif btype == "heading_3":
        lines.append(f"### {text}".rstrip())
    elif btype == "bulleted_list_item":
        lines.append(f"{'  ' * depth}- {text}".rstrip())
    elif btype == "numbered_list_item":
        lines.append(f"{'  ' * depth}1. {text}".rstrip())
    elif btype == "to_do":
        checked = data.get("checked", False)
        mark = "x" if checked else " "
        lines.append(f"- [{mark}] {text}".rstrip())
    elif btype == "quote":
        lines.append(f"> {text}".rstrip())
    elif btype == "code":
        lang = (data.get("language") or "").strip()
        body = text or ""
        lines.append(f"```{lang}\n{body}\n```")
    elif btype == "divider":
        lines.append("---")
    elif btype == "child_page":
        title = data.get("title") or text or "child page"
        lines.append(f"## {title}")
    else:
        if text:
            lines.append(text)

    children = block.get("children") or []
    for child in children:
        child_md = block_to_markdown(child, depth=depth + (1 if btype.endswith("_list_item") else 0))
        if child_md:
            lines.append(child_md)

    return "\n".join(line for line in lines if line is not None)


def blocks_to_markdown(blocks: list[dict[str, Any]]) -> str:
    parts = [block_to_markdown(b) for b in blocks]
    body = "\n\n".join(p for p in parts if p.strip())
    return body.strip() + "\n" if body.strip() else ""
