# Copyright (c) 2026 徐泽宇
"""Resolve plain text for KB indexing: material note first, then main markdown file.

Authors:
    徐泽宇

Copyright:
    © 2026 徐泽宇
"""

from __future__ import annotations

import logging
import os

from models.file import File as FileModel
from services.md_paths import resolve_upload_path
from services.okf.frontmatter import OkfParseError, split_frontmatter
from services.okf_note_service import read_okf_body_for_file
from utils.text_sanitize import strip_nul_bytes

logger = logging.getLogger(__name__)

SOURCE_SIDECAR = "sidecar_md"
SOURCE_MAIN = "main_md"


def _read_path(path: str) -> str | None:
    path = resolve_upload_path(path) or path
    if not path or not os.path.isfile(path):
        return None
    try:
        with open(path, "r", encoding="utf-8", errors="replace") as fh:
            raw = fh.read()
        if "\x00" in raw:
            logger.warning(
                "kb index text contained NUL bytes (stripped) path=%s count=%s",
                path,
                raw.count("\x00"),
            )
        text = strip_nul_bytes(raw)
        return text if text.strip() else None
    except OSError:
        return None


def _main_file_is_markdown(f: FileModel) -> bool:
    mime = (f.mime_type or "").lower()
    if mime in ("text/markdown", "text/x-markdown", "text/plain"):
        return True
    name = (f.original_name or f.filename or "").lower()
    return name.endswith(".md") or name.endswith(".markdown")


def _strip_frontmatter_safe(text: str) -> str:
    try:
        _meta, body = split_frontmatter(text)
    except OkfParseError:
        return text
    return body


def resolve_index_text(f: FileModel) -> tuple[str | None, str | None]:
    """Return (body-only text, source) or (None, None) if nothing indexable.

    sidecar 优先走 OKF body-only（frontmatter 不进入 chunk）；主文件 Markdown 仅在
    sidecar 缺失时回退，并剥离 frontmatter 以避免 YAML 泄漏到正文索引。
    """
    if f.has_md and f.md_file_path:
        body = read_okf_body_for_file(f)
        if body:
            text = strip_nul_bytes(body)
            if text.strip():
                return text, SOURCE_SIDECAR
    if _main_file_is_markdown(f):
        raw = _read_path(f.file_path)
        if raw:
            text = strip_nul_bytes(_strip_frontmatter_safe(raw))
            if text.strip():
                return text, SOURCE_MAIN
    return None, None
