# Copyright (c) 2026 徐泽宇
"""Generate OKF index.md (SPEC §6)."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class IndexChild:
    title: str
    rel_path: str
    description: str = ""


def generate_index_md(section_title: str, children: list[IndexChild]) -> str:
    lines = [f"# {section_title}", ""]
    for child in sorted(children, key=lambda c: c.title.lower()):
        desc = f" - {child.description}" if child.description else ""
        lines.append(f"* [{child.title}]({child.rel_path}){desc}")
    lines.append("")
    return "\n".join(lines)


def generate_root_index_md(children: list[IndexChild], *, okf_version: str = "0.1") -> str:
    """Bundle 根 index.md：SPEC §11 允许 frontmatter 仅含 okf_version。"""
    body = generate_index_md("Bundle Index", children)
    return f'---\nokf_version: "{okf_version}"\n---\n{body}'


def ensure_root_index_okf_version(content: str, *, okf_version: str = "0.1") -> str:
    """Passthrough 根 index 若无 okf_version 则补上 frontmatter。"""
    if "okf_version:" in content:
        return content
    if content.startswith("---"):
        return content
    return f'---\nokf_version: "{okf_version}"\n---\n{content}'
