# Copyright (c) 2026 徐泽宇
"""policy 业务逻辑模块。

Authors:
    徐泽宇
"""

from __future__ import annotations

import os

from models.file import File as FileModel
from services.file_service import get_extension

MARKDOWN_EXTENSIONS = frozenset({"md", "markdown"})
TEXT_PLAIN_EXTENSIONS = frozenset({"txt"})
TEXT_COPY_EXTENSIONS = MARKDOWN_EXTENSIONS | TEXT_PLAIN_EXTENSIONS

EXTRACT_EXTENSIONS = frozenset({
    "pdf",
    "doc", "docx",
    "ppt", "pptx",
    "xls", "xlsx",
    "jpg", "jpeg", "png", "gif", "bmp", "webp",
    "eml",
})

IMAGE_EXTENSIONS = frozenset({"jpg", "jpeg", "png", "gif", "bmp", "webp"})
MODERN_OFFICE = frozenset({"docx", "pptx", "xlsx"})
LEGACY_OFFICE = frozenset({"doc", "ppt", "xls"})
# MarkItDown 可处理的原生扩展（.xls 须先 LO 归一化为 .xlsx，不对原件直接调用）
MARKITDOWN_ELIGIBLE_EXTENSIONS = frozenset({"pdf", "docx", "pptx", "xlsx"})
A_TIER_EXTENSIONS = frozenset({"pdf", "ppt", "pptx", "xls", "xlsx"})


def get_extension_from_file(f: FileModel) -> str:
    return get_extension(f.original_name or f.filename or "")


def is_eml_file(f: FileModel) -> bool:
    """Return the persisted EML type; a display rename must not change it."""
    mime_type = (f.mime_type or "").lower().split(";", 1)[0].strip()
    return mime_type == "message/rfc822"


def is_markdown_source_file(f: FileModel) -> bool:
    return get_extension_from_file(f) in TEXT_COPY_EXTENSIONS


def supports_reextract(f: FileModel) -> bool:
    if is_eml_file(f):
        return bool(f.file_path and os.path.isfile(f.file_path))
    ext = get_extension_from_file(f)
    if ext == "eml":
        return False
    if ext in TEXT_COPY_EXTENSIONS:
        path = f.file_path
        return bool(path and os.path.isfile(path))
    return ext in EXTRACT_EXTENSIONS


def needs_extract(f: FileModel) -> bool:
    if f.has_md and f.md_file_path and os.path.isfile(f.md_file_path):
        try:
            from services.okf_note_service import read_okf_body_for_file

            body = read_okf_body_for_file(f)
            if body is not None and body.strip():
                return False
        except OSError:
            pass
    if is_eml_file(f):
        return True
    ext = get_extension_from_file(f)
    if ext == "eml":
        return False
    return ext in EXTRACT_EXTENSIONS
