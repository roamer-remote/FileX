# Copyright (c) 2026 徐泽宇
"""Office document PDF preview cache service."""

from __future__ import annotations

import logging
import os
import shutil
import threading
from glob import glob

from config import UPLOAD_DIR
from models.file import File as FileModel
from services.extract.libreoffice import convert_to_pdf
from services.extract.policy import get_extension_from_file
from services.md_paths import resolve_upload_path

logger = logging.getLogger(__name__)

PREVIEW_PDF_MIME = "application/pdf"
_PPT_MIME_TYPES = {
    "application/vnd.ms-powerpoint",
    "application/vnd.openxmlformats-officedocument.presentationml.presentation",
}

_locks_guard = threading.Lock()
_locks: dict[int, threading.Lock] = {}


def should_preview_as_pdf(f: FileModel) -> bool:
    ext = get_extension_from_file(f)
    mime = (f.mime_type or "").lower()
    return ext in {"ppt", "pptx"} or mime in _PPT_MIME_TYPES


def preview_pdf_mime_type(f: FileModel) -> str | None:
    return PREVIEW_PDF_MIME if should_preview_as_pdf(f) else None


def preview_pdf_dir() -> str:
    return os.path.join(UPLOAD_DIR, ".preview_pdf")


def preview_pdf_disk_path(f: FileModel) -> str:
    os.makedirs(preview_pdf_dir(), exist_ok=True)
    return os.path.join(preview_pdf_dir(), f"{f.id}.pdf")


def remove_preview_pdf(f: FileModel) -> None:
    """Remove the file-scoped PPT/PPTX preview cache and temp files."""
    path = os.path.join(preview_pdf_dir(), f"{f.id}.pdf")
    for candidate in (path, *glob(f"{path}.tmp.*")):
        try:
            if os.path.isfile(candidate):
                os.remove(candidate)
        except OSError:
            logger.warning("failed to remove preview PDF %s", candidate, exc_info=True)


def _valid_pdf(path: str | None) -> bool:
    return bool(path and os.path.isfile(path) and os.path.getsize(path) > 0)


def _lock_for(file_id: int) -> threading.Lock:
    with _locks_guard:
        lock = _locks.get(file_id)
        if lock is None:
            lock = threading.Lock()
            _locks[file_id] = lock
        return lock


def ensure_preview_pdf(f: FileModel) -> str:
    if not should_preview_as_pdf(f):
        raise ValueError("非 PPT/PPTX 文件，不需要 PDF 预览")
    if not f.file_path:
        raise FileNotFoundError("原件不存在")

    src_path = resolve_upload_path(f.file_path) or f.file_path
    if not os.path.isfile(src_path):
        raise FileNotFoundError(f"原件不存在: {f.file_path}")

    final_path = preview_pdf_disk_path(f)
    if _valid_pdf(final_path):
        return final_path

    converted: str | None = None
    tmp_final = f"{final_path}.tmp.{os.getpid()}.{threading.get_ident()}"

    lock = _lock_for(int(f.id))
    with lock:
        if _valid_pdf(final_path):
            return final_path
        try:
            converted = convert_to_pdf(src_path)
            if not _valid_pdf(converted):
                raise RuntimeError("LibreOffice 未生成有效 PDF 预览文件")
            shutil.copy2(converted, tmp_final)
            if not _valid_pdf(tmp_final):
                raise RuntimeError("PDF 预览缓存写入失败")
            os.replace(tmp_final, final_path)
            logger.info("generated office pdf preview file_id=%s -> %s", f.id, final_path)
            return final_path
        except Exception:
            logger.warning("failed to generate office pdf preview file_id=%s", f.id, exc_info=True)
            raise
        finally:
            for path in (tmp_final, converted):
                if path and path != final_path and os.path.isfile(path):
                    try:
                        os.remove(path)
                    except OSError:
                        logger.warning("failed to remove temp office pdf preview %s", path, exc_info=True)
