# Copyright (c) 2026 徐泽宇
"""operation_log 相关 API 数据模式。"""

from pydantic import BaseModel, Field


class OperationLogDeleteRequest(BaseModel):
    ids: list[int] = Field(..., min_length=1, max_length=200)


class OperationLogDeleteResponse(BaseModel):
    deleted: int
