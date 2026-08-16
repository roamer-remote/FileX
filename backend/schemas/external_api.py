# Copyright (c) 2026 徐泽宇
"""external_api 相关 API 数据模式模块。

Authors:
    徐泽宇
"""

from pydantic import BaseModel, Field


class ApiKeyStatusResponse(BaseModel):
    """GET /api/external/api-key-status 响应；HTTP 恒为 200，以 valid 为准。"""

    valid: bool
    reason: str | None = Field(
        default=None,
        description="invalid_api_key | api_key_inactive | user_inactive | not_api_key | missing_authorization",
    )
    username: str | None = None
    user_id: int | None = None
    hint: str | None = Field(
        default=None,
        description="valid=false 时的中文排查提示；valid=true 时为 null",
    )
