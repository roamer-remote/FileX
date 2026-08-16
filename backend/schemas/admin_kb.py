# Copyright (c) 2026 徐泽宇
"""admin_kb 相关 API 数据模式模块。

Authors:
    徐泽宇
"""

from pydantic import BaseModel, Field


class AdminKbReindexAllRequest(BaseModel):
    """管理资料库重索引all请求 Pydantic 数据模式。

        Authors:
            徐泽宇

        Copyright:
            © 2026 徐泽宇

        Since:
            2026-05-30

        Attributes:
            user_id: 用户ID（int | None）。
            force: force（bool）。
    """
    user_id: int | None = Field(default=None, description="仅重索引指定用户；省略则全站")
    force: bool = Field(
        default=True,
        description="为 true 时清空 index_source_hash，确保重新嵌入向量",
    )


class AdminKbReindexAllResponse(BaseModel):
    """管理资料库重索引all响应 Pydantic 数据模式。

        Authors:
            徐泽宇

        Copyright:
            © 2026 徐泽宇

        Attributes:
            candidate_count: 候选数量（int）。
            enqueued_count: enqueued数量（int）。
            message: 消息（str）。
    """
    candidate_count: int
    enqueued_count: int
    message: str
