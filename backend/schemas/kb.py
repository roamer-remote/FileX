# Copyright (c) 2026 徐泽宇
"""kb 相关 API 数据模式模块。

Authors:
    徐泽宇
"""

from typing import Any, ClassVar, Literal

from pydantic import BaseModel, Field, model_validator

from config import KB_SEARCH_TOP_K_MAX
from utils.agent_freshness import (
    AGENT_KB_SEARCH_NOTICE,
    AGENT_KB_SEARCH_WIKI_CONTEXT_APPENDIX,
)


class KbSearchRequest(BaseModel):
    """资料库检索请求 Pydantic 数据模式。

        Authors:
            徐泽宇

        Copyright:
            © 2026 徐泽宇

        Since:
            2026-05-22

        Attributes:
            query: query（str）。
            top_k: topk（int | None）。
            file_ids: 文件ids（list[int] | None）。
            tags: 标签（list[str] | None）。
            tag_mode: 标签mode（Literal['or', 'and']）。
            tag_combine: 标签combine（Literal['filter', 'union']）。
            include_not_ready: includenot就绪（bool）。
            include_drafts: includedrafts（bool）。
            group_by_file: groupby文件（bool）。
            context_chunks: 上下文chunks（int）。
            citation_format: 引用format（Literal['none', 'markdown', 'json']）。
            debug: 调试（bool）。
    """
    query: str = Field(..., min_length=1)
    top_k: int | None = Field(default=None, ge=1, le=KB_SEARCH_TOP_K_MAX)
    file_ids: list[int] | None = None
    tags: list[str] | None = None
    tag_mode: Literal["or", "and"] = "or"
    tag_combine: Literal["filter", "union"] = "filter"
    include_not_ready: bool = False
    include_drafts: bool = False
    group_by_file: bool = False
    context_chunks: int = Field(default=0, ge=0, le=3)
    citation_format: Literal["none", "markdown", "json"] = "none"
    debug: bool = False
    filename_boost: bool = False
    modality_boost: bool = False
    modality_boost_value: float | None = Field(default=None, ge=0.0, le=0.5)
    hybrid: bool | None = None
    query_expansion: bool = False
    expand_wiki_links: bool = False
    expand_wiki_coref: bool = False
    expand_wiki_graph: bool = False
    expand_tag_cooc: bool = False
    expand_doc_entities: bool = False
    expand_doc_entity_coref: bool = False
    expand_sag_events: bool = False
    sag_search_mode: Literal["fast", "standard"] = "fast"
    sag_max_hops: int | None = Field(default=None, ge=1, le=3)
    sag_max_events: int | None = Field(default=None, ge=1, le=200)
    return_search_trace: bool = False
    quality_job_id: int | None = Field(default=None, gt=0)
    wiki_context_depth: int | None = Field(default=None, ge=1, le=2)
    use_query_cache: bool = False
    evidence_mode: Literal["chunk", "monte_carlo"] = "chunk"
    evidence_sample_k: int | None = Field(default=None, ge=1, le=20)
    source_files_only: bool = False
    raptor_expand: bool = False
    raptor_drill_k: int | None = Field(default=None, ge=1, le=20)
    agent_thread_id: str | None = Field(
        default=None,
        max_length=128,
        description="109 会话 thread_id：同 ID 下 search/router 共用一条 agent_run",
    )
    agent_run_id: str | None = Field(
        default=None,
        max_length=36,
        description="109 可选：显式指定 running 的 agent_run UUID，优先于 thread 复用",
    )
    readonly_workflow_opt_in: bool = Field(
        default=False,
        description="187-P2：显式启用一次有预算的只读二次检索；默认关闭",
    )
    readonly_workflow_query: str | None = Field(
        default=None,
        min_length=1,
        max_length=512,
        description="187-P2：只读 workflow 的追加检索 query；仅 opt-in 时生效",
    )

    @model_validator(mode="after")
    def _tag_cooc_union_mutex(self):
        if self.expand_tag_cooc and self.tag_combine == "union":
            raise ValueError("expand_tag_cooc 与 tag_combine=union 互斥")
        if self.readonly_workflow_opt_in and not (self.readonly_workflow_query or "").strip():
            raise ValueError(
                "readonly_workflow_query 在 readonly_workflow_opt_in=true 时必填"
            )
        return self


class KbAssociationExploreRequest(BaseModel):
    """Bounded association discovery request; caller performs final verification."""

    query: str | None = Field(default=None, max_length=4000)
    anchors: list[str] = Field(default_factory=list, max_length=8)
    anchor_entities: list[str] = Field(default_factory=list, max_length=8)
    max_hops: int = Field(default=3, ge=1, le=3)
    max_paths: int = Field(default=50, ge=1, le=50)
    ppr_enabled: bool = False

    @model_validator(mode="after")
    def _require_query_or_anchors(self):
        if not self.query and not self.anchors and not self.anchor_entities:
            raise ValueError("query、anchors 或 anchor_entities 至少提供一项")
        return self


class KbAssociationAnchor(BaseModel):
    anchor: str
    status: Literal["resolved", "ambiguous", "unresolved"]
    visible_mention_count: int


class KbAssociationClaimEvidence(BaseModel):
    claim_id: int
    predicate: str
    file_id: int
    source_chunk_id: int | None = None
    source_locator: dict[str, Any] | None = None
    confidence: float | None = None
    qualifiers: dict[str, Any] | None = None


class KbAssociationPath(BaseModel):
    source_anchor: str
    target_anchor: str
    hops: int
    claims: list[KbAssociationClaimEvidence]
    conflict_claims: list[KbAssociationClaimEvidence] = Field(default_factory=list)
    level: Literal["direct", "composed", "adjacent_only", "conflicted", "insufficient"] = "composed"
    rules_applied: list[str] = Field(default_factory=list)
    rule_results: list[dict[str, Any]] = Field(default_factory=list)
    conflicts: list[dict[str, Any]] = Field(default_factory=list)
    score: float = Field(default=0.0, ge=0.0, le=1.0)
    coverage_status: Literal["complete", "incomplete"] = "complete"


class KbAssociationExploreResponse(BaseModel):
    anchors: list[KbAssociationAnchor]
    paths: list[KbAssociationPath]
    verification_file_ids: list[int]
    coverage: dict[str, Any]
    budgets: dict[str, int]
    truncation_reasons: list[str]
    truncated: bool = False
    meta: dict[str, Any] = Field(default_factory=dict)


# —— query-understand schemas (P0 LLM query understanding) ——

class KbQueryUnderstandRequest(BaseModel):
    question: str = Field(..., min_length=1, max_length=2000)


class KbQueryUnderstandEntity(BaseModel):
    name: str
    type: Literal["person", "org", "concept", "location"]


class KbQueryUnderstandConstraint(BaseModel):
    type: Literal["temporal", "colleague", "project", "status", "ownership"]
    detail: str


class KbQueryUnderstandResponse(BaseModel):
    intent: Literal["association", "fact", "compare", "procedure", "listing", "summary", "numeric", "visual"]
    entities: list[KbQueryUnderstandEntity] = Field(default_factory=list)
    constraints: list[KbQueryUnderstandConstraint] = Field(default_factory=list)
    sub_questions: list[str] = Field(default_factory=list)
    confidence: float = Field(default=0.0, ge=0.0, le=1.0)
    search_keywords: list[str] = Field(default_factory=list)
    rewritten_queries: list[str] = Field(default_factory=list)


class KbFulltextReasonRequest(BaseModel):
    """Full-text reasoning: backend reads files and runs LLM inference."""

    question: str = Field(..., min_length=1, max_length=4000)
    file_ids: list[int] = Field(default_factory=list, max_length=8)
    constraints: list[dict[str, str]] = Field(default_factory=list)
    sub_questions: list[str] = Field(default_factory=list)


class KbFulltextCitation(BaseModel):
    """A fulltext citation whose excerpt was found in the submitted source."""

    file_id: int
    excerpt: str
    context_excerpt: str
    source_sha256: str
    verified_in_source: bool = True


class KbFulltextVerificationStats(BaseModel):
    """Counts of candidate citations checked against this request's source."""

    accepted: int = Field(default=0, ge=0)
    rejected: int = Field(default=0, ge=0)


class KbFulltextReasonResponse(BaseModel):
    conclusion: str
    reasoning: str
    confidence: float = Field(default=0.0, ge=0.0, le=1.0)
    missing_evidence: list[str] = Field(default_factory=list)
    citations: list[KbFulltextCitation] = Field(default_factory=list)
    verification_stats: KbFulltextVerificationStats = Field(
        default_factory=KbFulltextVerificationStats,
    )
    truncated_file_ids: list[int] = Field(default_factory=list)
    omitted_file_ids: list[int] = Field(default_factory=list)


class KbRagasEvalContextInput(BaseModel):
    """One RAGAS context with provenance supplied by the Agent caller."""

    text: str = Field(..., min_length=1, max_length=8000)
    file_id: int | None = None
    chunk_id: int | None = None
    rank: int = Field(..., ge=0, le=49)


class KbRagasEvalSubmitRequest(BaseModel):
    """Completed RAG answer payload submitted by the Agent orchestrator."""

    MAX_CONTEXT_ITEM_CHARS: ClassVar[int] = 8000
    MAX_CONTEXT_TOTAL_CHARS: ClassVar[int] = 80000
    ALLOWED_SAMPLE_TYPES: ClassVar[set[str]] = {"answer", "recall_no_hit"}

    query: str = Field(..., min_length=1, max_length=4000)
    answer: str = Field(..., min_length=1, max_length=20000)
    contexts: list[str] = Field(..., min_length=1, max_length=50)
    context_items: list[KbRagasEvalContextInput] = Field(default_factory=list, max_length=50)
    context_file_ids: list[int] = Field(default_factory=list, max_length=50)
    context_chunk_ids: list[int] = Field(default_factory=list, max_length=100)
    agent_run_id: str | None = Field(default=None, max_length=36)
    search_trace_id: str | None = Field(default=None, max_length=64)
    sample_type: str | None = Field(default=None, max_length=32)

    @model_validator(mode="after")
    def _validate_context_lengths(self):
        for idx, ctx in enumerate(self.contexts):
            if len(ctx) > self.MAX_CONTEXT_ITEM_CHARS:
                raise ValueError(
                    f"contexts[{idx}] exceeds {self.MAX_CONTEXT_ITEM_CHARS} chars"
                )
        total = sum(len(c) for c in self.contexts)
        if total > self.MAX_CONTEXT_TOTAL_CHARS:
            raise ValueError(
                f"contexts total {total} chars exceeds {self.MAX_CONTEXT_TOTAL_CHARS}"
            )
        if self.context_items:
            if len(self.context_items) != len(self.contexts):
                raise ValueError("context_items must contain one item for each contexts entry")
            for idx, item in enumerate(self.context_items):
                if item.text != self.contexts[idx]:
                    raise ValueError(f"context_items[{idx}].text must equal contexts[{idx}]")
                if item.rank != idx:
                    raise ValueError(f"context_items[{idx}].rank must equal {idx}")
        return self

    @model_validator(mode="after")
    def _validate_sample_type(self):
        if self.sample_type is None:
            self.sample_type = "answer"
        elif self.sample_type not in self.ALLOWED_SAMPLE_TYPES:
            raise ValueError(
                f"sample_type must be one of {sorted(self.ALLOWED_SAMPLE_TYPES)}, "
                f"got {self.sample_type!r}"
            )
        return self


class KbRagasEvalSubmitResponse(BaseModel):
    accepted: bool


class KbChunkSnippet(BaseModel):
    """资料库分块snippet Pydantic 数据模式。

        Authors:
            徐泽宇

        Copyright:
            © 2026 徐泽宇

        Since:
            2026-05-18

        Attributes:
            chunk_index: 分块索引（int）。
            text: 文本（str）。
            score: score（float）。
            heading_path: heading路径（str | None）。
    """
    chunk_index: int | None = None
    text: str
    score: float
    heading_path: str | None = None
    citation_label: str | None = None


class KbChunkLocation(BaseModel):
    type: Literal["pdf_page", "slide", "sheet"]
    page: int | None = None
    slide: int | None = None
    sheet_index: int | None = None
    sheet_name: str | None = None


class KbChunkHit(BaseModel):
    """资料库分块hit Pydantic 数据模式。

        Authors:
            徐泽宇

        Copyright:
            © 2026 徐泽宇

        Since:
            2026-05-18

        Attributes:
            chunk_id: 分块ID（int | None）。
            file_id: 文件ID（int）。
            original_name: 原始名称（str）。
            has_md: 拥有Markdown（bool）。
            chunk_index: 分块索引（int）。
            source: 来源（str）。
            text: 文本（str）。
            score: score（float）。
            char_start: charstart（int）。
            char_end: charend（int）。
            matched_chunks: matchedchunks（int）。
            heading_path: heading路径（str | None）。
    """
    chunk_id: int | None = None
    file_id: int
    original_name: str
    has_md: bool
    chunk_index: int | None = None
    source: str | None = None
    text: str
    score: float
    char_start: int | None = None
    char_end: int | None = None
    matched_chunks: int = 1
    file_chunk_count: int | None = None
    heading_path: str | None = None
    block_type: str | None = None
    content_kind: str | None = None
    content_meta: dict[str, Any] | None = None
    figure_refs: dict[str, Any] | None = None
    context_text: str | None = None
    vector_score: float | None = None
    rerank_score: float | None = None
    boost_keywords: str | None = None
    keyword_boost: float | None = None
    filename_boost: float | None = None
    modality_boost: float | None = None
    base_score: float | None = None
    citation: str | dict[str, Any] | None = None
    citation_tier: Literal["paginated", "document_only"] = "document_only"
    citation_label: str | None = None
    location: KbChunkLocation | None = None
    snippets: list[KbChunkSnippet] | None = None
    provenance: Literal["extracted", "inferred", "ambiguous"] = "inferred"
    confidence: float = Field(default=0.85, ge=0.0, le=1.0)
    confidence_label: Literal["extracted", "inferred", "ambiguous"] = "inferred"
    source_kind: str | None = "search_hit"
    is_final: bool = True
    content_confidence: Literal["none", "partial", "final"] = "final"
    processing_stage: str | None = None
    processing_message: str | None = None
    expected_next_stage: str | None = None


class KbSearchDebugFunnel(BaseModel):
    vector_candidates: int = 0
    fts_candidates: int = 0
    merged_unique: int = 0
    after_acl_filter: int = 0
    after_min_score: int = 0
    after_rerank: int = 0
    after_mmr: int = 0
    filename_boost_applied: int = 0


class KbSearchMeta(BaseModel):
    """资料库检索元数据 Pydantic 数据模式。

        Authors:
            徐泽宇

        Copyright:
            © 2026 徐泽宇

        Since:
            2026-05-30

        Attributes:
            hybrid_enabled: 混合启用（bool）。
            rerank_enabled: 重排启用（bool）。
            rerank_applied: 重排applied（bool）。
            min_score: 最小score（float | None）。
            mmr_lambda: mmrlambda（float | None）。
            boost_keyword_bonus: 加权keywordbonus（float | None）。
            filename_boost_enabled: 文件名加权启用（bool | None）。
            filename_boost_value: 文件名加权value（float | None）。
            effective_hybrid: effective混合（bool | None）。
            query_expansion_enabled: query扩展启用（bool | None）。
            expanded_terms: expandedterms（list[str] | None）。
            effective_fts_config: effective全文检索配置（str | None）。
    """
    hybrid_enabled: bool = False
    rerank_enabled: bool = False
    rerank_applied: bool = False
    min_score: float | None = None
    mmr_lambda: float | None = None
    boost_keyword_bonus: float | None = None
    filename_boost_enabled: bool | None = None
    filename_boost_value: float | None = None
    modality_boost_enabled: bool | None = None
    modality_boost_value: float | None = None
    modality_intent: list[str] | None = None
    effective_hybrid: bool | None = None
    query_expansion_enabled: bool | None = None
    expanded_terms: list[str] | None = None
    effective_fts_config: str | None = None
    debug: bool | None = None
    wiki_graph_expanded: bool | None = None
    wiki_graph_neighbor_ids: list[int] | None = None
    wiki_graph_added_hits: int | None = None
    tag_cooc_expanded: bool | None = None
    tag_cooc_neighbor_tags: list[str] | None = None
    tag_cooc_added_hits: int | None = None
    doc_entity_expanded: bool | None = None
    doc_entity_neighbor_ids: list[int] | None = None
    doc_entity_added_hits: int | None = None
    sag_expanded: bool | None = None
    sag_added_hits: int | None = None
    sag_neighbor_event_ids: list[int] | None = None
    sag_mode_requested: Literal["fast", "standard"] | None = None
    sag_mode_effective: Literal["fast", "standard"] | None = None
    sag_mode_degraded: bool | None = None
    rewritten_queries: list[str] | None = None
    rewrite_llm_ms: int | None = None
    query_rewrite_skipped: bool | None = None
    iterative_rounds: int | None = None
    iterative_new_entities: list[str] | None = None
    iterative_new_file_ids: list[int] | None = None
    iterative_truncated: bool | None = None
    search_trace: dict[str, Any] | None = None
    readonly_workflow: dict[str, Any] | None = None
    cache_hit: bool | None = None
    cache_similarity: float | None = None
    cache_entry_id: int | None = None
    evidence_mode: Literal["chunk", "monte_carlo"] | None = None
    monte_carlo_sample_count: int | None = None
    raptor_expanded: bool | None = None
    raptor_drilldown_ids: list[int] | None = None
    raptor_added_hits: int | None = None
    debug_funnel: KbSearchDebugFunnel | None = None
    processing_hit_count: int = 0
    processing_file_ids: list[int] = Field(default_factory=list)
class WikiContextHint(BaseModel):
    """search 有命中时供智能体决定是否/如何展开 wiki-context。"""

    required: bool = Field(
        description="True 当至少一个 seed 有可读出链；此时须 wiki-context 后再作答",
    )
    seed_file_ids: list[int] = Field(
        default_factory=list,
        description="按 search 相关性排序的种子 file_id，最多 3 个",
    )
    expandable_seed_ids: list[int] = Field(
        default_factory=list,
        description="存在非 broken 出链的 seed；仅这些需要 wiki-context",
    )
    outlink_counts: dict[int, int] = Field(
        default_factory=dict,
        description="各 seed 的可展开出链数（不含 broken）",
    )
    recommended_parallel: int = Field(
        0,
        ge=0,
        le=3,
        description="主 Agent 同轮并行 curl wiki-context 次数：0=跳过，1=单次，2-3=并行",
    )
    depth: int = 1
    max_files: int = 8


class KbRetrievalHintsResponse(BaseModel):
    """072 P2：纯规则 RetrievalProfile 建议（GET /retrieval-hints）。"""

    query_type: str
    primary_path: Literal["search", "wiki-path", "wiki-explain"]
    struct_relation_mode: Literal["dual_entity", "single_entity"] | None = None
    search_params: dict[str, Any] = Field(default_factory=dict)
    use_query_cache_allowed: bool = True
    notes: list[str] = Field(default_factory=list)


class KbSearchResponse(BaseModel):
    """资料库检索响应 Pydantic 数据模式。

        Authors:
            徐泽宇

        Copyright:
            © 2026 徐泽宇

        Since:
            2026-05-25

        Attributes:
            items: 条目列表（list[KbChunkHit]）。
            embedding_model: embedding模型（str）。
            top_k: topk（int）。
            fetched_at: fetched时间（str）。
            agent_notice: 智能体notice（str）。
            wiki_context_hint: Wiki上下文hint（WikiContextHint | None）。
            wiki_context: Wiki上下文（dict | None）。
            meta: 元数据（KbSearchMeta | None）。
    """
    items: list[KbChunkHit]
    embedding_model: str
    top_k: int
    fetched_at: str = Field(
        ...,
        description="本响应检索快照的 UTC 时间（ISO 8601，Z 结尾）；智能体勿用早于该时刻的会话缓存替代重新 search",
    )
    agent_notice: str = Field(
        default=AGENT_KB_SEARCH_NOTICE,
        description="智能体必读：资料库可能已变更，须每轮重新检索；有命中时含 wiki-context 下一步",
    )
    wiki_context_hint: WikiContextHint | None = Field(
        default=None,
        description="有命中时非空：须对 seed_file_ids 调用 GET …/wiki-context 后再作答",
    )
    wiki_context: dict | None = Field(
        default=None,
        description="expand_wiki_links=true 且可展开时，批量 wiki-context 合并结果",
    )
    meta: KbSearchMeta | None = None
    agent_trace_view_url: str | None = Field(
        default=None,
        description="107：当请求含 agent_thread_id 时返回伴生页 URL",
    )


class KbReindexRequest(BaseModel):
    """资料库重索引请求（047 optional body）。"""
    force: bool = False


class KbReindexResponse(BaseModel):
    file_id: int
    index_status: str


class KbCorrectionOverlayCreateRequest(BaseModel):
    source_hash: str = Field(..., min_length=1, max_length=128)
    content: str = Field(..., min_length=1, max_length=2_000_000)
    reason: str = Field(..., min_length=1, max_length=4000)
    idempotency_key: str = Field(..., min_length=1, max_length=128)
    overlay_version: int = Field(default=1, ge=1)
    parent_version: int | None = Field(default=None, ge=1)


class KbCorrectionOverlayResponse(BaseModel):
    id: int
    source_file_id: int
    source_hash: str
    overlay_version: int
    state: str
    reindex_status: str
    content_hash: str


class KbCorrectionOverlayReindexRequest(BaseModel):
    strategy_id: str | None = Field(default=None, min_length=1, max_length=32)
    strategy_version: str = Field(..., min_length=1, max_length=64)


class KbCorrectionOverlayReindexResponse(BaseModel):
    overlay_id: int
    job_id: int
    status: str
    request_key: str


class KbForceRaptorResponse(BaseModel):
    file_id: int
    kb_post_status: str
    job_id: int


class KbReextractRequest(BaseModel):
    """资料库重提取请求 Pydantic 数据模式。"""
    force: bool = False
    provider: str | None = None


class KbReextractResponse(BaseModel):
    """资料库重提取响应 Pydantic 数据模式。

        Authors:
            徐泽宇

        Copyright:
            © 2026 徐泽宇

        Since:
            2026-05-22

        Attributes:
            file_id: 文件ID（int）。
            extract_status: 提取状态（str）。
    """
    file_id: int
    extract_status: str


class KbEmbeddingPreview(BaseModel):
    """资料库embedding预览 Pydantic 数据模式。

        Authors:
            徐泽宇

        Copyright:
            © 2026 徐泽宇

        Since:
            2026-05-22

        Attributes:
            dim: dim（int）。
            head: head（list[float]）。
            norm: norm（float）。
    """
    dim: int
    head: list[float]
    norm: float


class KbChunkDetail(BaseModel):
    """资料库分块详情 Pydantic 数据模式。

        Authors:
            徐泽宇

        Copyright:
            © 2026 徐泽宇

        Since:
            2026-05-22

        Attributes:
            id: ID（int）。
            chunk_index: 分块索引（int）。
            source: 来源（str）。
            text: 文本（str）。
            char_start: charstart（int）。
            char_end: charend（int）。
            embedding_model: embedding模型（str）。
            embedding_dim: embeddingdim（int）。
            embedding_preview: embedding预览（KbEmbeddingPreview）。
            created_at: 创建时间（str | None）。
            embedding: embedding（list[float] | None）。
            boost_keywords: 加权keywords（str | None）。
    """
    id: int
    chunk_index: int
    source: str
    text: str
    char_start: int
    char_end: int
    embedding_model: str
    embedding_dim: int
    embedding_preview: KbEmbeddingPreview
    created_at: str | None = None
    embedding: list[float] | None = None
    boost_keywords: str | None = None
    heading_path: str | None = None
    block_type: str | None = None
    content_kind: str | None = None
    content_meta: dict[str, Any] | None = None
    loc_label: str | None = None


class KbChunkPatchBody(BaseModel):
    """资料库分块补丁请求体 Pydantic 数据模式。

        Authors:
            徐泽宇

        Copyright:
            © 2026 徐泽宇

        Since:
            2026-05-25

        Attributes:
            text: 文本（str | None）。
            boost_keywords: 加权keywords（str | None）。
            reembed: reembed（bool）。
    """
    text: str | None = Field(default=None, min_length=1)
    boost_keywords: str | None = Field(default=None, max_length=2000)
    reembed: bool = True


class KbChunkPatchResponse(BaseModel):
    """资料库分块补丁响应 Pydantic 数据模式。

        Authors:
            徐泽宇

        Copyright:
            © 2026 徐泽宇

        Since:
            2026-05-22

        Attributes:
            chunk_id: 分块ID（int）。
            file_id: 文件ID（int）。
            chunk_index: 分块索引（int）。
            text: 文本（str）。
            boost_keywords: 加权keywords（str | None）。
            embedding_model: embedding模型（str）。
    """
    chunk_id: int
    file_id: int
    chunk_index: int
    text: str
    boost_keywords: str | None = None
    embedding_model: str


class KbChunkListResponse(BaseModel):
    """资料库分块列表响应 Pydantic 数据模式。

        Authors:
            徐泽宇

        Copyright:
            © 2026 徐泽宇

        Since:
            2026-05-22

        Attributes:
            file_id: 文件ID（int）。
            original_name: 原始名称（str）。
            index_status: 索引状态（str）。
            chunk_count: 分块数量（int）。
            kb_index_manual_override: 人工索引覆盖（bool）。
            embedding_dim: embeddingdim（int）。
            items: 条目列表（list[KbChunkDetail]）。
            total: 总计（int）。
            page: 页面（int）。
            page_size: 页面大小（int）。
    """
    file_id: int
    original_name: str
    index_status: str
    chunk_count: int
    kb_index_manual_override: bool = False
    embedding_dim: int
    items: list[KbChunkDetail]
    total: int
    page: int
    page_size: int


class KbSagEntityItem(BaseModel):
    entity_name: str
    entity_type: str


class KbSagEventItem(BaseModel):
    id: int
    chunk_id: int
    chunk_index: int | None = None
    title: str
    summary: str
    content: str
    extract_layer: str
    entities: list[KbSagEntityItem]
    created_at: str | None = None


class KbSagEventListResponse(BaseModel):
    file_id: int
    original_name: str
    items: list[KbSagEventItem]
    total: int
    page: int
    page_size: int
