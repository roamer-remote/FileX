# Copyright (c) 2026 徐泽宇
"""mq_queue_messages 相关 API 数据模式模块。

Authors:
    徐泽宇
"""

from pydantic import BaseModel, Field


class MqQueueMessageItem(BaseModel):
    """消息队列队列消息条目 Pydantic 数据模式。

        Authors:
            徐泽宇

        Copyright:
            © 2026 徐泽宇

        Since:
            2026-05-30

        Attributes:
            index: 索引（int）。
            job_id: 任务ID（int | None）。
            last_error: last错误（str | None）。
            body_preview: 请求体预览（str）。
            raw_body: raw请求体（str）。
            redelivered: redelivered（bool）。
    """
    index: int = Field(..., ge=0, description="本次预览列表中的序号（从 0 起）")
    job_id: int | None = None
    last_error: str | None = None
    body_preview: str
    raw_body: str
    redelivered: bool = False
    duplicate_count: int = Field(default=1, ge=1, description="同一 job_id 在队列中的重复条数（展示用）")


class MqQueueMessagesResponse(BaseModel):
    """消息队列队列messages响应 Pydantic 数据模式。

        Authors:
            徐泽宇

        Copyright:
            © 2026 徐泽宇

        Since:
            2026-05-30

        Attributes:
            queue_name: 队列名称（str）。
            message_count: 消息数量（int）。
            items: 条目列表（list[MqQueueMessageItem]）。
            truncated: truncated（bool）。
    """
    queue_name: str
    message_count: int
    """RabbitMQ 队列当前深度（peek 结束后再读，可能与 items 不一致）。"""
    peek_count: int = 0
    """去重后预览条目数，与 items 长度一致。"""
    raw_peek_count: int = 0
    """去重前实际拉取条数。"""
    items: list[MqQueueMessageItem]
    truncated: bool = False


class MqQueueMessageDeleteRequest(BaseModel):
    """消息队列队列消息删除请求 Pydantic 数据模式。

        Authors:
            徐泽宇

        Copyright:
            © 2026 徐泽宇

        Since:
            2026-05-30

        Attributes:
            purge: purge（bool）。
            job_id: 任务ID（int | None）。
            index: 索引（int | None）。
    """
    purge: bool = False
    job_id: int | None = Field(default=None, ge=1)
    index: int | None = Field(default=None, ge=0)


class MqQueueMessageDeleteResponse(BaseModel):
    """消息队列队列消息删除响应 Pydantic 数据模式。

        Authors:
            徐泽宇

        Copyright:
            © 2026 徐泽宇

        Attributes:
            queue_name: 队列名称（str）。
            removed: removed（int）。
            message_count: 消息数量（int）。
    """
    queue_name: str
    removed: int
    message_count: int


class MqQueueMessageDedupeResponse(BaseModel):
    """MQ 队列按 job_id 去重响应。"""

    queue_name: str
    removed: int
    message_count: int


class MqUserQueueMessageItem(BaseModel):
    index: int = Field(..., ge=0)
    job_id: int | None = None
    last_error: str | None = None
    body_preview: str
    duplicate_count: int = Field(default=1, ge=1)


class MqUserQueueMessagesResponse(BaseModel):
    queue_label: str
    total: int
    peek_count: int
    items: list[MqUserQueueMessageItem]
    truncated: bool = False


class MqUserQueueMessageRemoveRequest(BaseModel):
    queue_label: str
    job_id: int = Field(..., ge=1)


class MqUserQueueMessageRemoveResponse(BaseModel):
    queue_label: str
    removed: int
