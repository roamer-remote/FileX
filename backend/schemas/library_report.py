# Copyright (c) 2026 徐泽宇
"""library_report 相关 API 数据模式模块。

Authors:
    徐泽宇
"""

from typing import Any

from pydantic import BaseModel, Field


class LibraryReportPayload(BaseModel):
    """资料库报告载荷 Pydantic 数据模式。

        Authors:
            徐泽宇

        Copyright:
            © 2026 徐泽宇

        Since:
            2026-06-09

        Attributes:
            meta: 元数据（dict[str, Any]）。
            hub_files: hub文件（list[dict[str, Any]]）。
            hub_tags: hub标签（list[dict[str, Any]]）。
            hub_wiki_slugs: hubWikislugs（list[dict[str, Any]]）。
            surprising_links: surprisinglinks（list[dict[str, Any]]）。
            suggested_questions: suggestedquestions（list[dict[str, Any]]）。
            governance: governance（dict[str, Any]）。
    """
    meta: dict[str, Any]
    hub_files: list[dict[str, Any]] = Field(default_factory=list)
    hub_tags: list[dict[str, Any]] = Field(default_factory=list)
    hub_wiki_slugs: list[dict[str, Any]] = Field(default_factory=list)
    surprising_links: list[dict[str, Any]] = Field(default_factory=list)
    suggested_questions: list[dict[str, Any]] = Field(default_factory=list)
    governance: dict[str, Any] = Field(default_factory=dict)


class LibraryReportResponse(BaseModel):
    """资料库报告响应 Pydantic 数据模式。

        Authors:
            徐泽宇

        Copyright:
            © 2026 徐泽宇

        Since:
            2026-06-09

        Attributes:
            status: 状态（str）。
            generated_at: generated时间（str | None）。
            payload: 载荷（LibraryReportPayload | None）。
            message: 消息（str | None）。
            report_id: 报告ID（int | None）。
    """
    status: str
    generated_at: str | None = None
    payload: LibraryReportPayload | None = None
    message: str | None = None
    report_id: int | None = None


class LibraryReportRefreshResponse(BaseModel):
    """资料库报告刷新响应 Pydantic 数据模式。

        Authors:
            徐泽宇

        Copyright:
            © 2026 徐泽宇

        Attributes:
            status: 状态（str）。
            generated_at: generated时间（str | None）。
            payload: 载荷（LibraryReportPayload | None）。
            message: 消息（str | None）。
            report_id: 报告ID（int | None）。
    """
    status: str
    generated_at: str | None = None
    payload: LibraryReportPayload | None = None
    message: str | None = None
    report_id: int | None = None
