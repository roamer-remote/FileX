# Copyright (c) 2026 徐泽宇
"""wiki_context 相关 API 数据模式模块。

Authors:
    徐泽宇
"""

from typing import Literal

from pydantic import BaseModel, Field, field_validator


WikiContextRole = Literal["seed", "outlink", "coref"]
WikiContextLinkKind = Literal["file_id", "wiki_slug"]


class WikiContextLinkFrom(BaseModel):
    """Wiki上下文链接from Pydantic 数据模式。

        Authors:
            徐泽宇

        Copyright:
            © 2026 徐泽宇

        Since:
            2026-06-05

        Attributes:
            file_id: 文件ID（int）。
            link_kind: 链接类型（WikiContextLinkKind）。
            wiki_slug: WikiSlug（str | None）。
    """
    file_id: int
    link_kind: WikiContextLinkKind
    wiki_slug: str | None = None


class WikiContextNode(BaseModel):
    """Wiki上下文node Pydantic 数据模式。

        Authors:
            徐泽宇

        Copyright:
            © 2026 徐泽宇

        Since:
            2026-06-05

        Attributes:
            file_id: 文件ID（int）。
            original_name: 原始名称（str）。
            page_kind: 页面类型（str）。
            wiki_slug: WikiSlug（str | None）。
            role: 角色（WikiContextRole）。
            link_from: 链接from（WikiContextLinkFrom | None）。
            markdown: Markdown（str）。
            has_md: 拥有Markdown（bool）。
            provenance: 溯源（Literal['extracted', 'inferred', 'ambiguous']）。
            confidence: confidence（float）。
            confidence_label: confidencelabel（Literal['extracted', 'inferred', 'ambiguous']）。
            source_kind: 来源类型（str | None）。
    """
    file_id: int
    original_name: str
    page_kind: str = Field(
        description="与 models.file.PAGE_KINDS 一致；库中 NULL 时服务端 fallback 为 source",
    )
    wiki_slug: str | None = None
    role: WikiContextRole
    link_from: WikiContextLinkFrom | None = None
    markdown: str = ""
    has_md: bool = False
    provenance: Literal["extracted", "inferred", "ambiguous"] = "extracted"
    confidence: float = Field(default=1.0, ge=0.0, le=1.0)
    confidence_label: Literal["extracted", "inferred", "ambiguous"] = "extracted"
    source_kind: str | None = "wiki_link"


class WikiContextSkipped(BaseModel):
    """Wiki上下文skipped Pydantic 数据模式。

        Authors:
            徐泽宇

        Copyright:
            © 2026 徐泽宇

        Since:
            2026-06-05

        Attributes:
            reason: 原因（str）。
            link_kind: 链接类型（WikiContextLinkKind | None）。
            wiki_slug: WikiSlug（str | None）。
            target_file_id: 目标文件ID（int | None）。
    """
    reason: str
    link_kind: WikiContextLinkKind | None = None
    wiki_slug: str | None = None
    target_file_id: int | None = None


class WikiContextResponse(BaseModel):
    """Wiki上下文响应 Pydantic 数据模式。

        Authors:
            徐泽宇

        Copyright:
            © 2026 徐泽宇

        Since:
            2026-06-05

        Attributes:
            seed_file_id: 种子文件ID（int）。
            depth: 深度（int）。
            max_files: 最大文件（int）。
            truncated: truncated（bool）。
            skipped: skipped（list[WikiContextSkipped]）。
            nodes: 节点（list[WikiContextNode]）。
            fetched_at: fetched时间（str）。
    """
    seed_file_id: int
    depth: int
    max_files: int
    truncated: bool = False
    skipped: list[WikiContextSkipped] = Field(default_factory=list)
    nodes: list[WikiContextNode] = Field(default_factory=list)
    fetched_at: str


class WikiContextBatchRequest(BaseModel):
    """Wiki上下文批量请求 Pydantic 数据模式。

        Authors:
            徐泽宇

        Copyright:
            © 2026 徐泽宇

        Since:
            2026-06-09

        Attributes:
            file_ids: 文件ids（list[int]）。
            depth: 深度（int）。
            max_files: 最大文件（int）。
            include_coref: include共引（bool）。
            workspace_id: 知识空间ID（int | None）。
    """
    file_ids: list[int] = Field(..., min_length=1, max_length=3)
    depth: int = Field(default=1, ge=1, le=2)
    max_files: int = Field(default=8, ge=1, le=20)
    include_coref: bool = False
    workspace_id: int | None = None

    @field_validator("file_ids")
    @classmethod
    def dedupe_file_ids(cls, value: list[int]) -> list[int]:
        return list(dict.fromkeys(value))


class WikiContextBatchResponse(BaseModel):
    """Wiki上下文批量响应 Pydantic 数据模式。

        Authors:
            徐泽宇

        Copyright:
            © 2026 徐泽宇

        Since:
            2026-06-09

        Attributes:
            seed_file_ids: 种子文件ids（list[int]）。
            depth: 深度（int）。
            max_files: 最大文件（int）。
            truncated: truncated（bool）。
            skipped: skipped（list[WikiContextSkipped]）。
            nodes: 节点（list[WikiContextNode]）。
            fetched_at: fetched时间（str）。
    """
    seed_file_ids: list[int]
    depth: int
    max_files: int
    truncated: bool = False
    skipped: list[WikiContextSkipped] = Field(default_factory=list)
    nodes: list[WikiContextNode] = Field(default_factory=list)
    fetched_at: str

