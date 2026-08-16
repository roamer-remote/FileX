# Copyright (c) 2026 徐泽宇
"""086 Phase 1: read-only KB ingestion pipeline topology."""

from __future__ import annotations

from sqlalchemy.orm import Session

from schemas.kb_pipeline_visualization import (
    EffectivePipelineRoute,
    PipelineTopologyEdge,
    PipelineTopologyNode,
    PipelineTopologyResponse,
)
from services.kb_pipeline_service import get_pipeline_config
from services.system_setting_service import get_kb_extract_provider


def _static_topology() -> tuple[list[PipelineTopologyNode], list[PipelineTopologyEdge]]:
    nodes = [
        PipelineTopologyNode(
            id="upload",
            label="上传 / 入库",
            kind="stage",
            description="资料写入 uploads 并登记 files 行",
        ),
        PipelineTopologyNode(
            id="extract_enqueue",
            label="enqueue extract",
            kind="queue",
            description="kb.extract 主队列",
        ),
        PipelineTopologyNode(
            id="kb_extract",
            label="kb-extract",
            kind="worker",
            description="正文提取消费者；按 route 选择 provider",
        ),
        PipelineTopologyNode(
            id="mineru",
            label="filex-mineru",
            kind="sidecar",
            description="MinerU PDF 解析 RPC（kb.mineru）",
        ),
        PipelineTopologyNode(
            id="docling",
            label="filex-docling",
            kind="sidecar",
            description="Docling 解析 RPC（kb.docling）",
        ),
        PipelineTopologyNode(
            id="md_notes",
            label=".md_notes",
            kind="artifact",
            description="笔记 Markdown 落盘",
        ),
        PipelineTopologyNode(
            id="index_enqueue",
            label="enqueue index",
            kind="queue",
            description="kb.index 主队列",
        ),
        PipelineTopologyNode(
            id="kb_indexer",
            label="kb-indexer",
            kind="worker",
            description="分块、嵌入、写入 pgvector",
        ),
        PipelineTopologyNode(
            id="pgvector",
            label="pgvector",
            kind="store",
            description="向量索引存储",
        ),
        PipelineTopologyNode(
            id="search",
            label="search",
            kind="read_only",
            description="检索侧（不参与入库 job）",
        ),
        PipelineTopologyNode(
            id="rerank",
            label="rerank",
            kind="read_only",
            description="TEI rerank（不参与入库 job）",
        ),
    ]
    edges = [
        PipelineTopologyEdge(source="upload", target="extract_enqueue"),
        PipelineTopologyEdge(source="extract_enqueue", target="kb_extract"),
        PipelineTopologyEdge(source="kb_extract", target="mineru"),
        PipelineTopologyEdge(source="kb_extract", target="docling"),
        PipelineTopologyEdge(source="kb_extract", target="md_notes"),
        PipelineTopologyEdge(source="mineru", target="md_notes"),
        PipelineTopologyEdge(source="docling", target="md_notes"),
        PipelineTopologyEdge(source="md_notes", target="index_enqueue"),
        PipelineTopologyEdge(source="index_enqueue", target="kb_indexer"),
        PipelineTopologyEdge(source="kb_indexer", target="pgvector"),
        PipelineTopologyEdge(source="pgvector", target="search"),
        PipelineTopologyEdge(source="search", target="rerank"),
    ]
    return nodes, edges


def _route_match_label(match: dict[str, object]) -> str:
    if "mime_prefix" in match:
        return f"MIME 前缀 {match['mime_prefix']}"
    if "ext" in match:
        exts = match["ext"]
        if isinstance(exts, list):
            return "扩展名 " + ", ".join(str(x) for x in exts)
        return f"扩展名 {exts}"
    return "未知 match"


def _highlight_providers(effective_routes: list[EffectivePipelineRoute], global_default: str) -> set[str]:
    providers = {global_default.lower()}
    for route in effective_routes:
        providers.add(route.extract_provider.lower())
    highlighted: set[str] = set()
    if "mineru" in providers:
        highlighted.add("mineru")
    if "docling" in providers:
        highlighted.add("docling")
    highlighted.add("kb_extract")
    return highlighted


def build_pipeline_topology(db: Session) -> PipelineTopologyResponse:
    config = get_pipeline_config(db)
    global_default = get_kb_extract_provider(db)
    stages = dict(config.stages) if config else {"entity_extract": False, "wiki_lint_on_index": False}

    effective_routes: list[EffectivePipelineRoute] = []
    if config is not None:
        for idx, route in enumerate(config.routes):
            effective_routes.append(
                EffectivePipelineRoute(
                    route_index=idx,
                    match_label=_route_match_label(route.match),
                    extract_provider=route.extract_provider,
                )
            )

    nodes, edges = _static_topology()
    highlighted = _highlight_providers(effective_routes, global_default)
    nodes = [
        node.model_copy(update={"highlight": node.id in highlighted})
        for node in nodes
    ]

    return PipelineTopologyResponse(
        nodes=nodes,
        edges=edges,
        effective_routes=effective_routes,
        global_default_provider=global_default,
        stages=stages,
    )
