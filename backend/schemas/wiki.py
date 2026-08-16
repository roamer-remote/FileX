# Copyright (c) 2026 徐泽宇
"""wiki 相关 API 数据模式模块。

Authors:
    徐泽宇
"""

from typing import Literal

from pydantic import BaseModel, Field

ProvenanceKind = Literal["extracted", "inferred", "ambiguous"]


class ProvenanceFields(BaseModel):
    """溯源fields Pydantic 数据模式。

        Authors:
            徐泽宇

        Copyright:
            © 2026 徐泽宇

        Since:
            2026-06-09

        Attributes:
            provenance: 溯源（ProvenanceKind）。
            confidence: confidence（float）。
            confidence_label: confidencelabel（ProvenanceKind）。
            source_kind: 来源类型（str | None）。
    """
    provenance: ProvenanceKind = "inferred"
    confidence: float = Field(default=1.0, ge=0.0, le=1.0)
    confidence_label: ProvenanceKind = "inferred"
    source_kind: str | None = None


class WikiLinkOutItem(ProvenanceFields):
    """Wiki链接out条目 Pydantic 数据模式。

        Authors:
            徐泽宇

        Copyright:
            © 2026 徐泽宇

        Since:
            2026-06-02

        Attributes:
            target_file_id: 目标文件ID（int | None）。
            target_name: 目标名称（str | None）。
            target_wiki_slug: 目标WikiSlug（str | None）。
            link_kind: 链接类型（str）。
            link_text: 链接文本（str | None）。
            anchor_id: 锚点ID（str）。
            start_offset: startoffset（int）。
            end_offset: endoffset（int）。
            broken: broken（bool）。
            broken_reason: broken原因（str | None）。
    """
    target_file_id: int | None = None
    target_name: str | None = None
    target_wiki_slug: str | None = None
    link_kind: str
    link_text: str | None = None
    anchor_id: str
    start_offset: int
    end_offset: int
    broken: bool = False
    broken_reason: str | None = None


class WikiLinkBackItem(ProvenanceFields):
    """Wiki链接back条目 Pydantic 数据模式。

        Authors:
            徐泽宇

        Copyright:
            © 2026 徐泽宇

        Since:
            2026-06-01

        Attributes:
            source_file_id: 来源文件ID（int）。
            source_name: 来源名称（str）。
            link_text: 链接文本（str | None）。
            anchor_id: 锚点ID（str）。
            broken: broken（bool）。
    """
    source_file_id: int
    source_name: str
    link_text: str | None = None
    anchor_id: str
    broken: bool = False


class WikiCorefPeerItem(ProvenanceFields):
    """Wiki共引peer条目 Pydantic 数据模式。

        Authors:
            徐泽宇

        Copyright:
            © 2026 徐泽宇

        Since:
            2026-06-01

        Attributes:
            file_id: 文件ID（int）。
            source_name: 来源名称（str）。
            shared_wiki_slugs: 共享Wikislugs（list[str]）。
    """
    file_id: int
    source_name: str
    shared_wiki_slugs: list[str] = Field(default_factory=list)


class WikiLinksResponse(BaseModel):
    """Wikilinks响应 Pydantic 数据模式。

        Authors:
            徐泽宇

        Copyright:
            © 2026 徐泽宇

        Since:
            2026-06-02

        Attributes:
            file_id: 文件ID（int）。
            outlinks: outlinks（list[WikiLinkOutItem]）。
            backlinks: backlinks（list[WikiLinkBackItem]）。
            outlink_count: outlink数量（int）。
            backlink_count: backlink数量（int）。
            coref_files: 共引文件（list[WikiCorefPeerItem]）。
            coref_count: 共引数量（int）。
    """
    file_id: int
    outlinks: list[WikiLinkOutItem] = Field(default_factory=list)
    backlinks: list[WikiLinkBackItem] = Field(default_factory=list)
    outlink_count: int = 0
    backlink_count: int = 0
    coref_files: list[WikiCorefPeerItem] = Field(default_factory=list)
    coref_count: int = 0


class WikiPageCreateBody(BaseModel):
    """Wiki页面创建请求体 Pydantic 数据模式。

        Authors:
            徐泽宇

        Copyright:
            © 2026 徐泽宇

        Since:
            2026-06-01

        Attributes:
            title: title（str）。
            wiki_slug: WikiSlug（str）。
            page_kind: 页面类型（str）。
            markdown: Markdown（str）。
            workspace_id: 知识空间ID（int | None）。
    """
    title: str = Field(..., min_length=1, max_length=500)
    wiki_slug: str = Field(..., min_length=1, max_length=128)
    page_kind: str = Field(..., pattern="^(entity|concept|synthesis)$")
    markdown: str = Field(default="")
    workspace_id: int | None = None


class WikiPageSlugUpdateBody(BaseModel):
    """主题页 wiki_slug 修改请求。"""

    wiki_slug: str = Field(..., min_length=1, max_length=128)


class WikiPageListItem(BaseModel):
    """Wiki页面列表条目 Pydantic 数据模式。

        Authors:
            徐泽宇

        Copyright:
            © 2026 徐泽宇

        Since:
            2026-06-01

        Attributes:
            file_id: 文件ID（int）。
            title: title（str）。
            wiki_slug: WikiSlug（str）。
            page_kind: 页面类型（str）。
            has_md: 拥有Markdown（bool）。
            linked_source_count: linked来源数量（int）。
            workspace_id: 知识空间ID（int | None）。
    """
    file_id: int
    title: str
    wiki_slug: str
    page_kind: str
    has_md: bool
    linked_source_count: int = 0
    workspace_id: int | None = None


class WikiPageListResponse(BaseModel):
    """Wiki页面列表响应 Pydantic 数据模式。

        Authors:
            徐泽宇

        Copyright:
            © 2026 徐泽宇

        Since:
            2026-06-02

        Attributes:
            items: 条目列表（list[WikiPageListItem]）。
            total: 当前筛选下总条数。
            page: 当前页码（从 1 起）。
            page_size: 每页条数。
    """
    items: list[WikiPageListItem]
    total: int = 0
    page: int = 1
    page_size: int = 20


class WikiLinkedSourceItem(BaseModel):
    """Wikilinked来源条目 Pydantic 数据模式。

        Authors:
            徐泽宇

        Copyright:
            © 2026 徐泽宇

        Since:
            2026-06-02

        Attributes:
            file_id: 文件ID（int）。
            source_name: 来源名称（str）。
    """
    file_id: int
    source_name: str


class WikiLinkedSourcesResponse(BaseModel):
    """Wikilinkedsources响应 Pydantic 数据模式。

        Authors:
            徐泽宇

        Copyright:
            © 2026 徐泽宇

        Since:
            2026-06-01

        Attributes:
            wiki_slug: WikiSlug（str）。
            items: 条目列表（list[WikiLinkedSourceItem]）。
            total: 总计（int）。
    """
    wiki_slug: str
    items: list[WikiLinkedSourceItem] = Field(default_factory=list)
    total: int = 0


class WikiLinkGraphNode(BaseModel):
    """Wiki链接图node Pydantic 数据模式。

        Authors:
            徐泽宇

        Copyright:
            © 2026 徐泽宇

        Since:
            2026-06-01

        Attributes:
            id: ID（int）。
            name: 名称（str）。
            value: value（int）。
            page_kind: 页面类型（str）。
            wiki_slug: WikiSlug（str | None）。
    """
    id: int
    name: str
    value: int = 0
    page_kind: str = "source"
    wiki_slug: str | None = None


class WikiLinkGraphEdge(ProvenanceFields):
    """Wiki链接图edge Pydantic 数据模式。

        Authors:
            徐泽宇

        Copyright:
            © 2026 徐泽宇

        Since:
            2026-06-01

        Attributes:
            source: 来源（int）。
            target: 目标（int）。
            value: value（int）。
            edge_type: edge类型（Literal['file_direct', 'wiki_topic', 'wiki_coref', 'derived_from']）。
            wiki_slug: WikiSlug（str | None）。
    """
    source: int
    target: int
    value: int = 1
    edge_type: Literal["file_direct", "wiki_topic", "wiki_coref", "derived_from"] = "file_direct"
    wiki_slug: str | None = None


class WikiLinkGraphResponse(BaseModel):
    """Wiki链接图响应 Pydantic 数据模式。

        Authors:
            徐泽宇

        Copyright:
            © 2026 徐泽宇

        Since:
            2026-06-01

        Attributes:
            nodes: 节点（list[WikiLinkGraphNode]）。
            links: links（list[WikiLinkGraphEdge]）。
            truncated: truncated（bool）。
            total_files_with_links: 总计文件含links（int）。
    """
    nodes: list[WikiLinkGraphNode]
    links: list[WikiLinkGraphEdge]
    truncated: bool = False
    total_files_with_links: int = 0


class KbLogAppendBody(BaseModel):
    """资料库日志append请求体 Pydantic 数据模式。

        Authors:
            徐泽宇

        Copyright:
            © 2026 徐泽宇

        Since:
            2026-06-01

        Attributes:
            entry: 条目（str）。
            workspace_id: 知识空间ID（int | None）。
    """
    entry: str = Field(..., min_length=1, max_length=65536)
    workspace_id: int | None = None


class KbLogEntryItem(BaseModel):
    """资料库日志条目条目 Pydantic 数据模式。

        Authors:
            徐泽宇

        Copyright:
            © 2026 徐泽宇

        Since:
            2026-06-01

        Attributes:
            id: ID（int）。
            entry: 条目（str）。
            workspace_id: 知识空间ID（int | None）。
            created_at: 创建时间（str）。
    """
    id: int
    entry: str
    workspace_id: int | None = None
    created_at: str


class KbLogListResponse(BaseModel):
    """资料库日志列表响应 Pydantic 数据模式。

        Authors:
            徐泽宇

        Copyright:
            © 2026 徐泽宇

        Since:
            2026-06-02

        Attributes:
            items: 条目列表（list[KbLogEntryItem]）。
            total: 总计（int）。
            limit: limit（int）。
            offset: offset（int）。
    """
    items: list[KbLogEntryItem]
    total: int
    limit: int
    offset: int


class WikiCandidateItem(BaseModel):
    """Wiki候选条目 Pydantic 数据模式。

        Authors:
            徐泽宇

        Copyright:
            © 2026 徐泽宇

        Since:
            2026-06-02

        Attributes:
            wiki_slug: WikiSlug（str）。
            source_count: 来源数量（int）。
            sample_file_ids: sample文件ids（list[int]）。
    """
    wiki_slug: str
    source_count: int
    sample_file_ids: list[int] = Field(default_factory=list)


class WikiCandidatesResponse(BaseModel):
    """Wikicandidates响应 Pydantic 数据模式。

        Authors:
            徐泽宇

        Copyright:
            © 2026 徐泽宇

        Since:
            2026-06-02

        Attributes:
            items: 条目列表（list[WikiCandidateItem]）。
    """
    items: list[WikiCandidateItem] = Field(default_factory=list)


class WikiCompileQueueItem(BaseModel):
    """Wiki编译队列条目 Pydantic 数据模式。

        Authors:
            徐泽宇

        Copyright:
            © 2026 徐泽宇

        Since:
            2026-06-02

        Attributes:
            id: ID（int）。
            wiki_slug: WikiSlug（str）。
            source_count: 来源数量（int）。
            status: 状态（str）。
            workspace_id: 知识空间ID（int | None）。
            created_at: 创建时间（str）。
            updated_at: 更新时间（str）。
    """
    id: int
    wiki_slug: str
    source_count: int
    status: str
    workspace_id: int | None = None
    created_at: str
    updated_at: str


class WikiCompileQueueResponse(BaseModel):
    """Wiki编译队列响应 Pydantic 数据模式。

        Authors:
            徐泽宇

        Copyright:
            © 2026 徐泽宇

        Since:
            2026-06-02

        Attributes:
            items: 条目列表（list[WikiCompileQueueItem]）。
    """
    items: list[WikiCompileQueueItem] = Field(default_factory=list)


class WikiCompileQueuePatchBody(BaseModel):
    """Wiki编译队列补丁请求体 Pydantic 数据模式。

        Authors:
            徐泽宇

        Copyright:
            © 2026 徐泽宇

        Since:
            2026-06-01

        Attributes:
            status: 状态（str）。
    """
    status: str = Field(..., pattern="^(done|skipped|pending)$")


class WikiLintResponse(BaseModel):
    """Wiki体检响应 Pydantic 数据模式。

        Authors:
            徐泽宇

        Copyright:
            © 2026 徐泽宇

        Since:
            2026-06-01

        Attributes:
            broken_links: brokenlinks（list[dict]）。
            acl_broken_links: ACLbrokenlinks（list[dict]）。
            orphan_pages: orphanpages（list[dict]）。
            missing_slug: missingSlug（list[dict]）。
            pending_concepts: 待处理concepts（list[WikiCandidateItem]）。
            stale_wiki_index: 过期Wiki索引（bool）。
    """
    broken_links: list[dict] = Field(default_factory=list)
    acl_broken_links: list[dict] = Field(default_factory=list)
    orphan_pages: list[dict] = Field(default_factory=list)
    missing_slug: list[dict] = Field(default_factory=list)
    pending_concepts: list[WikiCandidateItem] = Field(default_factory=list)
    stale_wiki_index: bool = False


class AdminWikiRebuildBody(BaseModel):
    """管理Wiki重建请求体 Pydantic 数据模式。

        Authors:
            徐泽宇

        Copyright:
            © 2026 徐泽宇

        Since:
            2026-06-09

        Attributes:
            user_id: 用户ID（int | None）。
            batch_size: 批量大小（int）。
    """
    user_id: int | None = None
    batch_size: int = Field(default=100, ge=1, le=1000)


class AdminWikiLintBody(BaseModel):
    """管理Wiki体检请求体 Pydantic 数据模式。

        Authors:
            徐泽宇

        Copyright:
            © 2026 徐泽宇

        Since:
            2026-06-09

        Attributes:
            user_id: 用户ID（int | None）。
    """
    user_id: int | None = None


class WikiPathEdgeItem(ProvenanceFields):
    """Wiki路径edge条目 Pydantic 数据模式。

        Authors:
            徐泽宇

        Copyright:
            © 2026 徐泽宇

        Since:
            2026-06-09

        Attributes:
            edge_type: edge类型（Literal['file_direct', 'wiki_topic', 'wiki_coref', 'derived_from']）。
            via_slug: viaSlug（str | None）。
    """
    edge_type: Literal["file_direct", "wiki_topic", "wiki_coref", "derived_from"] = "file_direct"
    via_slug: str | None = None


class WikiPathResponse(BaseModel):
    """Wiki路径响应 Pydantic 数据模式。

        Authors:
            徐泽宇

        Copyright:
            © 2026 徐泽宇

        Since:
            2026-06-09

        Attributes:
            found: found（bool）。
            hops: hops（int）。
            truncated: truncated（bool）。
            path: 路径（list[dict]）。
    """
    found: bool = False
    hops: int = 0
    truncated: bool = False
    path: list[dict] = Field(default_factory=list)


class WikiExplainCenter(BaseModel):
    """Wiki解释center Pydantic 数据模式。

        Authors:
            徐泽宇

        Copyright:
            © 2026 徐泽宇

        Since:
            2026-06-09

        Attributes:
            file_id: 文件ID（int）。
            title: title（str）。
            page_kind: 页面类型（str）。
            wiki_slug: WikiSlug（str | None）。
            has_md: 拥有Markdown（bool）。
    """
    file_id: int
    title: str
    page_kind: str = "source"
    wiki_slug: str | None = None
    has_md: bool = False


class WikiExplainNeighbor(BaseModel):
    """Wiki解释邻居 Pydantic 数据模式。

        Authors:
            徐泽宇

        Copyright:
            © 2026 徐泽宇

        Since:
            2026-06-09

        Attributes:
            file_id: 文件ID（int）。
            title: title（str）。
            outlink_count: outlink数量（int）。
            backlink_count: backlink数量（int）。
    """
    file_id: int
    title: str
    outlink_count: int = 0
    backlink_count: int = 0


class WikiExplainTopicHub(BaseModel):
    """Wiki解释主题hub Pydantic 数据模式。

        Authors:
            徐泽宇

        Copyright:
            © 2026 徐泽宇

        Since:
            2026-06-09

        Attributes:
            slug: Slug（str）。
            target_file_id: 目标文件ID（int | None）。
            target_name: 目标名称（str | None）。
            broken: broken（bool）。
    """
    slug: str
    target_file_id: int | None = None
    target_name: str | None = None
    broken: bool = False


class WikiExplainResponse(BaseModel):
    """Wiki解释响应 Pydantic 数据模式。

        Authors:
            徐泽宇

        Copyright:
            © 2026 徐泽宇

        Since:
            2026-06-09

        Attributes:
            center: center（WikiExplainCenter）。
            outlinks: outlinks（list[WikiLinkOutItem]）。
            inlinks: inlinks（list[WikiLinkBackItem]）。
            coref_peers: 共引peers（list[WikiCorefPeerItem]）。
            topic_hubs: 主题hubs（list[WikiExplainTopicHub]）。
            neighbor_nodes: 邻居节点（list[WikiExplainNeighbor]）。
            edge_count: edge数量（int）。
            depth: 深度（int）。
            fetched_at: fetched时间（str）。
    """
    center: WikiExplainCenter
    outlinks: list[WikiLinkOutItem] = Field(default_factory=list)
    inlinks: list[WikiLinkBackItem] = Field(default_factory=list)
    coref_peers: list[WikiCorefPeerItem] = Field(default_factory=list)
    topic_hubs: list[WikiExplainTopicHub] = Field(default_factory=list)
    neighbor_nodes: list[WikiExplainNeighbor] = Field(default_factory=list)
    edge_count: int = 0
    depth: int = 1
    fetched_at: str = ""
