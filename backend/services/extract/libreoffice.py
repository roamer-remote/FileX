# Copyright (c) 2026 徐泽宇
"""libreoffice 业务逻辑模块。

Authors:
    徐泽宇
"""

from __future__ import annotations

import logging
import os
import shutil
import subprocess
import tempfile
from pathlib import Path

from config import KB_EXTRACT_LO_TIMEOUT_SEC

logger = logging.getLogger(__name__)

_LO_BIN = shutil.which("soffice") or shutil.which("libreoffice")


def libreoffice_available() -> bool:
    return bool(_LO_BIN)


def convert_to_modern(src_path: str, target_ext: str) -> str:
    """Convert legacy office file to docx/xlsx/pptx in a temp dir; return output path."""
    if not _LO_BIN:
        raise RuntimeError("LibreOffice (soffice) 未安装，无法转换旧版 Office 文档")
    target_ext = target_ext.lstrip(".")
    out_dir = tempfile.mkdtemp(prefix="filex-lo-")
    try:
        cmd = [
            _LO_BIN,
            "--headless",
            "--norestore",
            "--convert-to",
            target_ext,
            "--outdir",
            out_dir,
            src_path,
        ]
        proc = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=KB_EXTRACT_LO_TIMEOUT_SEC,
            check=False,
        )
        if proc.returncode != 0:
            err = (proc.stderr or proc.stdout or "")[:2000]
            raise RuntimeError(f"LibreOffice 转换失败: {err}")
        base = Path(src_path).stem
        out_path = os.path.join(out_dir, f"{base}.{target_ext}")
        if not os.path.isfile(out_path):
            candidates = list(Path(out_dir).glob(f"*.{target_ext}"))
            if not candidates:
                raise RuntimeError("LibreOffice 未生成预期输出文件")
            out_path = str(candidates[0])
        # Copy to another temp file so caller can delete out_dir
        fd, stable = tempfile.mkstemp(suffix=f".{target_ext}")
        os.close(fd)
        shutil.copy2(out_path, stable)
        return stable
    finally:
        shutil.rmtree(out_dir, ignore_errors=True)


def convert_to_pdf(src_path: str) -> str:
    """Convert an Office document to PDF in a temp dir; return output path."""
    return convert_to_modern(src_path, "pdf")
