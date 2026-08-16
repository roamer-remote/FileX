# Copyright (c) 2026 徐泽宇
"""LiteParse extract provider (in-process Python + RapidOCR HTTP bridge).

Authors:
    徐泽宇

Copyright:
    © 2026 徐泽宇
"""

from __future__ import annotations

import logging
import os

from models.file import File as FileModel
from services.extract.base import ExtractResult
from services.extract.policy import get_extension_from_file, needs_extract

logger = logging.getLogger(__name__)


def extract_liteparse(f: FileModel) -> ExtractResult:
    if not needs_extract(f):
        raise ValueError("文件类型不需要 liteparse 提取")
    path = f.file_path
    if not path or not os.path.isfile(path):
        raise FileNotFoundError(f"文件不存在: {path}")

    from config import (
        KB_EXTRACT_LITEPARSE_DPI,
        KB_EXTRACT_LITEPARSE_MAX_PAGES,
        KB_EXTRACT_LITEPARSE_NUM_WORKERS,
        KB_EXTRACT_LITEPARSE_OCR_LANG,
        KB_EXTRACT_LITEPARSE_OCR_URL,
    )
    from services.extract.liteparse_ocr_bridge import start_liteparse_ocr_bridge

    start_liteparse_ocr_bridge()

    try:
        from liteparse import LiteParse
    except ImportError as exc:
        raise RuntimeError("liteparse 未安装，请在 kb-extract 镜像中 pip install liteparse") from exc

    parser = LiteParse(
        ocr_enabled=True,
        ocr_server_url=KB_EXTRACT_LITEPARSE_OCR_URL,
        ocr_language=KB_EXTRACT_LITEPARSE_OCR_LANG,
        max_pages=KB_EXTRACT_LITEPARSE_MAX_PAGES,
        dpi=KB_EXTRACT_LITEPARSE_DPI,
        quiet=True,
        num_workers=KB_EXTRACT_LITEPARSE_NUM_WORKERS,
    )
    ext = get_extension_from_file(f)
    logger.info("liteparse parse file_id=%s ext=%s", f.id, ext)
    result = parser.parse(path)
    text = (result.text or "").strip()
    if not text:
        raise ValueError("liteparse 返回空正文")
    return ExtractResult(text=text, engine="liteparse+rapidocr")
