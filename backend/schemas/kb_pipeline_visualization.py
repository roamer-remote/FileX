# Copyright (c) 2026 徐泽宇
"""086 KB pipeline visualization read DTOs."""

from __future__ import annotations

from pydantic import BaseModel, Field

from schemas.kb_quality_manifest import ExtractionManifest


class PipelineTopologyNode(BaseModel):
    id: str
    label: str
    kind: str
    description: str | None = None
    highlight: bool = False


class PipelineTopologyEdge(BaseModel):
    source: str
    target: str


class EffectivePipelineRoute(BaseModel):
    route_index: int
    match_label: str
    extract_provider: str


class PipelineTopologyResponse(BaseModel):
    nodes: list[PipelineTopologyNode]
    edges: list[PipelineTopologyEdge]
    effective_routes: list[EffectivePipelineRoute]
    global_default_provider: str
    stages: dict[str, bool] = Field(default_factory=dict)


class PipelineTraceStep(BaseModel):
    key: str
    title: str
    status: str
    detail: str | None = None
    error_message: str | None = None
    log_deep_link: str | None = None
    occurred_at: str | None = None
    # 向量索引阶段效率指标（用于监控大文件如 id=340 的建立检索耗时）
    embed_ms: int | None = None
    persist_ms: int | None = None
    post_index_ms: int | None = None
    post_entity_ms: int | None = None
    post_sag_ms: int | None = None
    post_raptor_ms: int | None = None
    large_pdf: bool | None = None
    post_skip_reason: str | None = None


class FilePipelineTraceResponse(BaseModel):
    file_id: int
    filename: str
    trace_provider: str | None = None
    global_default_provider: str
    chunk_count: int
    has_md_notes: bool
    steps: list[PipelineTraceStep]
    extraction_manifest: ExtractionManifest | None = None
    extraction_manifest_error: str | None = None


class PipelineQueueMetric(BaseModel):
    name: str
    label: str
    message_count: int
    warning: bool = False
    deep_link: str = "/admin/mq"


class PipelineKpiMetric(BaseModel):
    key: str
    value: int
    warning: bool = False
    deep_link: str | None = None


class ProviderFailureStat(BaseModel):
    provider: str
    failure_count: int
    success_count: int
    failure_rate: float


class PipelineStageAvgMs(BaseModel):
    extract_provider_ms: float | None = None
    extract_persist_ms: float | None = None
    index_embed_ms: float | None = None
    index_persist_ms: float | None = None
    index_post_ms: float | None = None


class PipelineRecentEvent(BaseModel):
    id: int
    action: str
    user_id: int
    username: str
    target_id: int | None = None
    detail: str | None = None
    created_at: str
    log_deep_link: str


class PipelineOcrAggStat(BaseModel):
    key: str
    count: int


class PipelineMetricsResponse(BaseModel):
    window: str
    generated_at: str
    cached: bool = False
    queues: list[PipelineQueueMetric]
    kpis: list[PipelineKpiMetric]
    provider_failures: list[ProviderFailureStat]
    ocr_telemetry: list[PipelineOcrAggStat] = Field(default_factory=list)
    avg_stage_ms: PipelineStageAvgMs
    recent_events: list[PipelineRecentEvent]
    warnings: list[str] = Field(default_factory=list)
