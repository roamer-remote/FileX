# Copyright (c) 2026 徐泽宇
"""base 业务逻辑模块。

Authors:
    徐泽宇
"""

from __future__ import annotations

from dataclasses import dataclass

from services.extract.ocr_stats import ExtractOcrStats


@dataclass
class ExtractResult:
    """提取结果 业务服务。

        Authors:
            徐泽宇

        Copyright:
            © 2026 徐泽宇

        Attributes:
            text: 文本（str）。
            engine: engine（str）。
    """
    text: str
    engine: str
    content_list: list[dict] | None = None
    mineru_assets_dir: str | None = None
    fallback_from: str | None = None
    fallback_reason: str | None = None
    ocr_stats: ExtractOcrStats | None = None
    ocr_model_usage: list[dict[str, str]] | None = None
