# Copyright (c) 2026 徐泽宇
"""统一 structlog 日志入口；旧代码可继续使用 logging.getLogger。

Authors:
    徐泽宇

Copyright:
    © 2026 徐泽宇
"""

from __future__ import annotations

import structlog


def get_logger(name: str | None = None) -> structlog.stdlib.BoundLogger:
    return structlog.get_logger(name)
