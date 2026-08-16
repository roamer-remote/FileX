# Copyright (c) 2026 徐泽宇
"""OKF YAML frontmatter split/merge."""

from __future__ import annotations

from typing import Any

import yaml

from services.okf.errors import OkfParseError

try:
    from yaml import CSafeLoader as _YamlLoader
except ImportError:  # pragma: no cover
    from yaml import SafeLoader as _YamlLoader  # type: ignore[assignment]


def split_frontmatter(text: str) -> tuple[dict[str, Any], str]:
    """Return (metadata, body). Missing frontmatter → ({}, text)."""
    raw = text or ""
    if not raw.startswith("---"):
        return {}, raw
    lines = raw.splitlines(keepends=True)
    if not lines:
        return {}, raw
    end_idx: int | None = None
    for i in range(1, len(lines)):
        if lines[i].strip() == "---":
            end_idx = i
            break
    if end_idx is None:
        return {}, raw
    yaml_block = "".join(lines[1:end_idx])
    body = "".join(lines[end_idx + 1 :])
    if not yaml_block.strip():
        return {}, body
    try:
        loaded = yaml.load(yaml_block, Loader=_YamlLoader)
    except yaml.YAMLError as exc:
        raise OkfParseError(f"YAML frontmatter 不可解析: {exc}") from exc
    if loaded is None:
        return {}, body
    if not isinstance(loaded, dict):
        raise OkfParseError("frontmatter 须为 YAML mapping")
    return dict(loaded), body


def normalize_metadata_for_storage(meta: dict[str, Any]) -> dict[str, Any]:
    """Strip `type`; normalize tags to list[str]."""
    out: dict[str, Any] = {}
    for key, value in meta.items():
        if key == "type":
            continue
        if key == "tags":
            if value is None:
                continue
            if isinstance(value, list):
                out["tags"] = [str(t) for t in value]
            else:
                out["tags"] = [str(value)]
            continue
        out[key] = value
    return out


def merge_frontmatter(meta: dict[str, Any], okf_type: str, body: str) -> str:
    """Emit SPEC-ordered markdown with frontmatter."""
    fm: dict[str, Any] = dict(meta or {})
    fm.pop("type", None)
    ordered: dict[str, Any] = {"type": okf_type}
    for key in ("title", "description", "resource", "tags", "timestamp", "okf_version"):
        if key in fm and fm[key] is not None and fm[key] != "":
            ordered[key] = fm[key]
    for key, value in fm.items():
        if key not in ordered:
            ordered[key] = value
    yaml_text = yaml.safe_dump(ordered, allow_unicode=True, sort_keys=False).strip()
    body_text = body or ""
    if body_text and not body_text.startswith("\n"):
        body_text = "\n" + body_text
    if body_text and not body_text.endswith("\n"):
        body_text += "\n"
    return f"---\n{yaml_text}\n---{body_text}"
