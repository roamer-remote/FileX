# Copyright (c) 2026 徐泽宇
"""Ensure paginated extract types carry filex:loc markers when missing."""

from __future__ import annotations

import logging
import os

from models.file import File as FileModel
from services.extract.policy import A_TIER_EXTENSIONS, get_extension_from_file
from services.extract.loc_markers import body_has_loc_markers

logger = logging.getLogger(__name__)


def ensure_a_tier_loc_markers(f: FileModel, text: str) -> str:
    ext = get_extension_from_file(f)
    if ext not in A_TIER_EXTENSIONS:
        return text
    if body_has_loc_markers(text):
        return text
    path = f.file_path
    if not path or not os.path.isfile(path):
        return text
    if ext == "pdf":
        from services.extract.pdf import build_pdf_marked_body

        try:
            return build_pdf_marked_body(path, file_id=f.id)[0]
        except Exception:
            logger.warning(
                "ensure_a_tier_loc_markers pdf failed file_id=%s path=%s",
                f.id,
                path,
                exc_info=True,
            )
            return text
    if ext in ("ppt", "pptx"):
        from services.extract.pptx import build_pptx_marked_body

        pptx_path = f.normalized_path if ext == "ppt" and f.normalized_path else path
        if not os.path.isfile(pptx_path):
            pptx_path = path
        try:
            return build_pptx_marked_body(pptx_path)
        except Exception:
            logger.warning(
                "ensure_a_tier_loc_markers ppt failed file_id=%s path=%s",
                f.id,
                pptx_path,
                exc_info=True,
            )
            return text
    if ext in ("xls", "xlsx"):
        from services.extract.xlsx import build_xlsx_marked_body

        xlsx_path = f.normalized_path if ext == "xls" and f.normalized_path else path
        if not os.path.isfile(xlsx_path):
            xlsx_path = path
        try:
            return build_xlsx_marked_body(xlsx_path)
        except Exception:
            logger.warning(
                "ensure_a_tier_loc_markers xlsx failed file_id=%s path=%s",
                f.id,
                xlsx_path,
                exc_info=True,
            )
            return text
    return text
