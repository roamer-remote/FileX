# Copyright (c) 2026 徐泽宇
"""Legacy Office (.doc/.ppt/.xls) → modern format on disk for in-browser preview.

Authors:
    徐泽宇

Copyright:
    © 2026 徐泽宇
"""

from __future__ import annotations

import logging
import os
import shutil

from config import UPLOAD_DIR
from models.file import File as FileModel
from services.extract.libreoffice import convert_to_modern
from services.extract.policy import LEGACY_OFFICE, get_extension_from_file
from services.file_service import get_mime_type
from services.md_paths import resolve_upload_path
from services.office_preview_pdf_service import (
    PREVIEW_PDF_MIME,
    ensure_preview_pdf,
    preview_pdf_mime_type,
    should_preview_as_pdf,
)

logger = logging.getLogger(__name__)

LEGACY_TO_MODERN = {"doc": "docx", "ppt": "pptx", "xls": "xlsx"}

NORMALIZED_DIR = os.path.join(UPLOAD_DIR, ".normalized")


def is_legacy_office_file(f: FileModel) -> bool:
    return get_extension_from_file(f) in LEGACY_OFFICE


def normalized_disk_path(file_id: int, modern_ext: str) -> str:
    os.makedirs(NORMALIZED_DIR, exist_ok=True)
    ext = modern_ext.lstrip(".")
    return os.path.join(NORMALIZED_DIR, f"{file_id}.{ext}")


def normalized_file_exists(f: FileModel) -> bool:
    path = resolve_upload_path(f.normalized_path) if f.normalized_path else None
    return bool(path and os.path.isfile(path))


def preview_mime_type(f: FileModel) -> str | None:
    pdf_mime = preview_pdf_mime_type(f)
    if pdf_mime:
        return pdf_mime
    if not normalized_file_exists(f):
        return None
    ext = os.path.splitext(f.normalized_path)[1].lstrip(".")
    if not ext:
        return None
    return get_mime_type(f"file.{ext}")


def ensure_office_normalized(f: FileModel) -> str:
    """Convert legacy office to a persisted modern copy; update f.normalized_path."""
    ext = get_extension_from_file(f)
    if ext not in LEGACY_OFFICE:
        raise ValueError(f"非旧版 Office 文件: .{ext}")
    if not f.file_path:
        raise FileNotFoundError("原件不存在")
    src_path = resolve_upload_path(f.file_path) or f.file_path
    if not os.path.isfile(src_path):
        raise FileNotFoundError(f"原件不存在: {f.file_path}")

    modern_ext = LEGACY_TO_MODERN[ext]
    dest = normalized_disk_path(f.id, modern_ext)

    if f.normalized_path and normalized_file_exists(f):
        norm = resolve_upload_path(f.normalized_path) or f.normalized_path
        return norm

    if os.path.isfile(dest):
        f.normalized_path = dest
        return dest

    converted = convert_to_modern(src_path, modern_ext)
    try:
        os.makedirs(NORMALIZED_DIR, exist_ok=True)
        shutil.copy2(converted, dest)
        f.normalized_path = dest
        logger.info("normalized legacy office file_id=%s -> %s", f.id, dest)
        return dest
    finally:
        if os.path.isfile(converted):
            try:
                os.remove(converted)
            except OSError:
                pass


def preview_path_and_mime(f: FileModel) -> tuple[str, str]:
    """Return disk path + media type for GET /preview (normalized copy when available)."""
    if should_preview_as_pdf(f):
        return ensure_preview_pdf(f), PREVIEW_PDF_MIME
    if normalized_file_exists(f):
        mime = preview_mime_type(f)
        norm = resolve_upload_path(f.normalized_path) if f.normalized_path else None
        if mime and norm:
            return norm, mime
    src = resolve_upload_path(f.file_path) if f.file_path else None
    return (src or f.file_path), f.mime_type


def remove_normalized_file(f: FileModel) -> None:
    path = f.normalized_path
    if path and os.path.isfile(path):
        try:
            os.remove(path)
        except OSError:
            logger.warning("failed to remove normalized file %s", path, exc_info=True)
    f.normalized_path = None
