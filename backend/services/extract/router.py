# Copyright (c) 2026 徐泽宇
"""router 业务逻辑模块。

Authors:
    徐泽宇
"""

from __future__ import annotations

import os
from collections.abc import Callable

from services.extract.base import ExtractResult
from services.extract.docx import extract_docx
from services.extract.image import extract_image
from services.extract.legacy import extract_legacy_doc, extract_legacy_ppt, extract_legacy_xls
from services.extract.pdf import extract_pdf
from services.extract.policy import (
    IMAGE_EXTENSIONS,
    MARKITDOWN_ELIGIBLE_EXTENSIONS,
    get_extension_from_file,
    is_eml_file,
)
from services.extract.pptx import extract_pptx
from services.extract.xlsx import extract_xlsx
from models.file import File as FileModel
from services.md_paths import resolve_upload_path


def _disk_path(path: str | None) -> str | None:
    return resolve_upload_path(path) or path


def _extract_preferred(
    f: FileModel,
    path: str,
    ext: str,
    *,
    legacy_fn: Callable[[], ExtractResult],
    via_libreoffice: bool = False,
) -> ExtractResult:
    from config import KB_MARKITDOWN_ENABLED
    from services.extract.markitdown_extract import try_markitdown

    def _with_lo_prefix(result: ExtractResult) -> ExtractResult:
        if via_libreoffice:
            return ExtractResult(
                text=result.text,
                engine=f"libreoffice+{result.engine}",
                content_list=result.content_list,
                mineru_assets_dir=result.mineru_assets_dir,
                fallback_from=result.fallback_from,
                fallback_reason=result.fallback_reason,
                ocr_stats=result.ocr_stats,
            )
        return result

    if not KB_MARKITDOWN_ENABLED or ext not in MARKITDOWN_ELIGIBLE_EXTENSIONS:
        return _with_lo_prefix(legacy_fn())
    md = try_markitdown(path, ext, file_id=f.id)
    if md is not None:
        return _with_lo_prefix(md)
    return _with_lo_prefix(legacy_fn())


def _extract_text_from_file_inner(f: FileModel, *, db=None) -> ExtractResult:
    path = _disk_path(f.file_path)
    if not path or not os.path.isfile(path):
        raise FileNotFoundError(f"文件不存在: {f.file_path}")
    if is_eml_file(f):
        from services.extract.eml_extract import extract_eml

        return extract_eml(path, file_id=f.id)
    ext = get_extension_from_file(f)
    if ext == "pdf":
        if db is None:
            return extract_pdf(path, file_id=f.id)
        return extract_pdf(path, file_id=f.id, db=db)
    if ext in IMAGE_EXTENSIONS:
        return extract_image(path)
    if ext == "docx":
        return _extract_preferred(f, path, ext, legacy_fn=lambda: extract_docx(path))
    if ext == "pptx":
        return _extract_preferred(f, path, ext, legacy_fn=lambda: extract_pptx(path))
    if ext == "xlsx":
        return _extract_preferred(f, path, ext, legacy_fn=lambda: extract_xlsx(path))
    if ext == "doc":
        norm_path = _disk_path(f.normalized_path)
        if norm_path and os.path.isfile(norm_path):
            norm_ext = "docx"
            return _extract_preferred(
                f,
                norm_path,
                norm_ext,
                legacy_fn=lambda: extract_docx(norm_path),
                via_libreoffice=True,
            )
        return extract_legacy_doc(path)
    if ext == "ppt":
        norm_path = _disk_path(f.normalized_path)
        if norm_path and os.path.isfile(norm_path):
            norm_ext = "pptx"
            return _extract_preferred(
                f,
                norm_path,
                norm_ext,
                legacy_fn=lambda: extract_pptx(norm_path),
                via_libreoffice=True,
            )
        return extract_legacy_ppt(path)
    if ext == "xls":
        norm_path = _disk_path(f.normalized_path)
        if norm_path and os.path.isfile(norm_path):
            norm_ext = "xlsx"
            return _extract_preferred(
                f,
                norm_path,
                norm_ext,
                legacy_fn=lambda: extract_xlsx(norm_path),
                via_libreoffice=True,
            )
        return extract_legacy_xls(path)
    raise ValueError(f"不支持的提取类型: {ext}")


def extract_text_from_file(f: FileModel, *, db=None) -> ExtractResult:
    result = _extract_text_from_file_inner(f, db=db)
    from services.extract.loc_inject import ensure_a_tier_loc_markers

    text = ensure_a_tier_loc_markers(f, result.text)
    if text != result.text:
        return ExtractResult(
            text=text,
            engine=result.engine,
            content_list=result.content_list,
            mineru_assets_dir=result.mineru_assets_dir,
            fallback_from=result.fallback_from,
            fallback_reason=result.fallback_reason,
            ocr_stats=result.ocr_stats,
        )
    return result
