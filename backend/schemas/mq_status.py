# Copyright (c) 2026 徐泽宇
"""mq_status 相关 API 数据模式模块。

Authors:
    徐泽宇
"""

from typing import Any

from pydantic import BaseModel


class MqQueueStatus(BaseModel):
    """消息队列队列状态 Pydantic 数据模式。

        Authors:
            徐泽宇

        Copyright:
            © 2026 徐泽宇

        Since:
            2026-05-18

        Attributes:
            name: 名称（str）。
            label: label（str）。
            online: online（bool）。
            message_count: 消息数量（int）。
            consumer_count: 消费者数量（int）。
            consumer_busy: 消费者busy（bool）。
            jobs_pending: jobs待处理（int）。
            backlog_total: 积压总计（int）。
    """
    name: str
    label: str
    online: bool
    message_count: int
    consumer_count: int
    consumer_busy: bool = False
    jobs_pending: int = 0
    """库内 queued + 正在索引，按 file_id 去重（侧栏「待处理与执行中」）。"""
    backlog_total: int = 0


class MqActiveTask(BaseModel):
    """消息队列启用task Pydantic 数据模式。

        Authors:
            徐泽宇

        Copyright:
            © 2026 徐泽宇

        Since:
            2026-05-18

        Attributes:
            kind: 类型（str）。
            username: 用户名（str）。
            file_id: 文件ID（int | None）。
            filename: 文件名（str | None）。
    """
    kind: str
    username: str
    file_id: int | None = None
    filename: str | None = None
    progress_pct: int | None = None
    progress_stage: str | None = None
    progress_detail: str | None = None
    # 当前流程实际使用的模型名称，不包含 API Key 等凭证。
    model: str | None = None


class MqStatusResponse(BaseModel):
    """消息队列状态响应 Pydantic 数据模式。

        Authors:
            徐泽宇

        Copyright:
            © 2026 徐泽宇

        Since:
            2026-05-31

        Attributes:
            connected: connected（bool）。
            broker_display: brokerdisplay（str）。
            error: 错误（str | None）。
            updated_at: 更新时间（str）。
            queues: queues（list[MqQueueStatus]）。
            active_tasks: 启用tasks（list[MqActiveTask]）。
    """
    connected: bool
    broker_display: str
    error: str | None = None
    updated_at: str
    queues: list[MqQueueStatus]
    active_tasks: list[MqActiveTask] = []
    system_resources: dict[str, Any] | None = None


class MqQueuedJobItem(BaseModel):
    """消息队列queued任务条目 Pydantic 数据模式。

        Authors:
            徐泽宇

        Copyright:
            © 2026 徐泽宇

        Since:
            2026-05-31

        Attributes:
            job_id: 任务ID（int）。
            file_id: 文件ID（int）。
            filename: 文件名（str）。
            username: 用户名（str）。
            updated_at: 更新时间（str | None）。
    """
    job_id: int
    file_id: int
    filename: str
    username: str
    updated_at: str | None = None


class MqQueuedJobsResponse(BaseModel):
    """消息队列queuedjobs响应 Pydantic 数据模式。

        Authors:
            徐泽宇

        Copyright:
            © 2026 徐泽宇

        Attributes:
            total: 总计（int）。
            items: 条目列表（list[MqQueuedJobItem]）。
            truncated: truncated（bool）。
    """
    total: int
    items: list[MqQueuedJobItem]
    truncated: bool = False


class MqUserActiveTask(BaseModel):
    kind: str
    file_id: int | None = None
    filename: str | None = None
    progress_pct: int | None = None
    progress_stage: str | None = None
    progress_detail: str | None = None


class MqUserQueuedJobItem(BaseModel):
    job_id: int
    file_id: int
    filename: str
    updated_at: str | None = None


class MqUserQueuedJobsResponse(BaseModel):
    total: int
    items: list[MqUserQueuedJobItem]
    truncated: bool = False


class MqUserJobCancelResponse(BaseModel):
    job_id: int
    file_id: int
    kind: str
    mq_removed: int = 0
