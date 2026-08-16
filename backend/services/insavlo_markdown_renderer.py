# Copyright (c) 2026 徐泽宇
"""Insavlo webhook result -> Markdown renderer (044 FR-E).

Renders the Insavlo ``files[].result`` structure into a generic Markdown
resource note. The raw JSON is always appended so no information is lost.
"""

from __future__ import annotations

import json
from typing import Any

_CONFIDENCE_KEYS = frozenset({"$value", "$confidence_flag"})


def _is_confidence_struct(value: Any) -> bool:
    return isinstance(value, dict) and "$value" in value and set(value.keys()) <= _CONFIDENCE_KEYS


def _scalar_cell(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, bool):
        return "是" if value else "否"
    if _is_confidence_struct(value):
        val = value.get("$value", "")
        flag = value.get("$confidence_flag")
        text = "" if val is None else str(val)
        if flag is not None:
            text = f"{text} （置信: {flag}）"
        return text
    return str(value)


def _flatten_scalars(obj: Any, prefix: str = "") -> list[tuple[str, Any]]:
    """Yield (key, value) pairs for scalar/confidence leaves.

    Nested objects recurse as ``parent.child``; arrays are skipped here and
    rendered as independent sub-tables by the caller.
    """
    pairs: list[tuple[str, Any]] = []
    if not isinstance(obj, dict):
        return pairs
    for key, value in obj.items():
        full = f"{prefix}{key}"
        if isinstance(value, dict) and not _is_confidence_struct(value):
            pairs.extend(_flatten_scalars(value, f"{full}."))
        elif isinstance(value, list):
            continue
        else:
            pairs.append((full, value))
    return pairs


def _render_array_section(lines: list[str], key: str, values: list[Any]) -> None:
    if not values:
        return
    lines.append(f"## {key}")
    lines.append("")
    if all(isinstance(item, dict) for item in values):
        columns: list[str] = []
        seen: set[str] = set()
        for item in values:
            for col, _ in _flatten_scalars(item):
                if col not in seen:
                    seen.add(col)
                    columns.append(col)
        if not columns:
            columns = ["值"]
        lines.append("| " + " | ".join(columns) + " |")
        lines.append("|" + "|".join(["---"] * len(columns)) + "|")
        for item in values:
            flat = dict(_flatten_scalars(item))
            row = [_scalar_cell(flat.get(col)) for col in columns]
            lines.append("| " + " | ".join(row) + " |")
    else:
        lines.append("| # | 值 |")
        lines.append("|---|---|")
        for index, item in enumerate(values, 1):
            lines.append(f"| {index} | {_scalar_cell(item)} |")
    lines.append("")


def render_insavlo_markdown(
    *,
    original_name: str,
    transaction_id: str,
    file_id: str | None,
    skill_code: str | None,
    result: Any,
) -> str:
    """Render one Insavlo file result as Markdown per FR-E."""
    lines: list[str] = []
    lines.append(f"# {original_name}")
    lines.append("")
    lines.append("> 由 Insavlo 正文提取引擎生成。")
    lines.append("")
    lines.append("| 字段 | 值 |")
    lines.append("|---|---|")
    lines.append(f"| 原文件名 | {original_name} |")
    lines.append(f"| Insavlo Transaction ID | {transaction_id} |")
    lines.append(f"| Insavlo File ID | {file_id or ''} |")
    lines.append(f"| Skill Code | {skill_code or ''} |")
    lines.append("")

    if isinstance(result, dict) and result:
        scalar_pairs = _flatten_scalars(result)
        array_fields = [(k, v) for k, v in result.items() if isinstance(v, list)]
        if scalar_pairs:
            lines.append("## 字段")
            lines.append("")
            lines.append("| 字段 | 值 |")
            lines.append("|---|---|")
            for key, value in scalar_pairs:
                lines.append(f"| {key} | {_scalar_cell(value)} |")
            lines.append("")
        for key, values in array_fields:
            _render_array_section(lines, key, values)

    lines.append("## 原始结果（JSON）")
    lines.append("")
    lines.append("```json")
    lines.append(json.dumps(result, ensure_ascii=False, indent=2))
    lines.append("```")
    lines.append("")
    return "\n".join(lines)
