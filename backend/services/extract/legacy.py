# Copyright (c) 2026 徐泽宇
"""legacy 业务逻辑模块。

Authors:
    徐泽宇
"""

from __future__ import annotations

import os

from services.extract.base import ExtractResult
from services.extract.docx import extract_docx
from services.extract.libreoffice import convert_to_modern
from services.extract.pptx import extract_pptx
from services.extract.xlsx import extract_xlsx


def extract_legacy_doc(path: str) -> ExtractResult:
    converted = convert_to_modern(path, "docx")
    try:
        result = extract_docx(converted)
        return ExtractResult(text=result.text, engine=f"libreoffice+{result.engine}")
    finally:
        if os.path.isfile(converted):
            os.remove(converted)


def extract_legacy_ppt(path: str) -> ExtractResult:
    converted = convert_to_modern(path, "pptx")
    try:
        result = extract_pptx(converted)
        return ExtractResult(text=result.text, engine=f"libreoffice+{result.engine}")
    finally:
        if os.path.isfile(converted):
            os.remove(converted)


def extract_legacy_xls(path: str) -> ExtractResult:
    converted = convert_to_modern(path, "xlsx")
    try:
        result = extract_xlsx(converted)
        return ExtractResult(text=result.text, engine=f"libreoffice+{result.engine}")
    finally:
        if os.path.isfile(converted):
            os.remove(converted)
