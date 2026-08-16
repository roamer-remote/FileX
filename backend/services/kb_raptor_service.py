# Copyright (c) 2026 徐泽宇
"""049 Phase A: RAPTOR hierarchical summary index + search drill-down."""

from __future__ import annotations

import json
import logging
import math
import time
from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

import numpy as np
from pydantic import ValidationError
from sqlalchemy import func, or_
from sqlalchemy.orm import Session

from config import KB_RAPTOR_USE_EMBED_CACHE
from services.ollama_config_service import get_ollama_runtime_config
from models.file import File as FileModel
from models.kb_chunk import KbChunk
from models.kb_enums import ContentKind
from services.kb_embed_cache_service import resolve_embedding_vectors
from services.kb_ollama_embed import OllamaEmbedError, embed_texts
from schemas.llm_outputs import RaptorSummaryOutput
from services.kb_post_llm_service import chat_json
from services.kb_post_llm_service import get_kb_post_llm_runtime_config
from services.gpu_model_lifecycle_service import (
    GpuExecutionContext,
    GpuModelSchedulerAdapter,
    ModelGroup,
)
from services.kb_search_service import _chunk_hit_dict, _merge_hits_by_file
from services.system_setting_service import get_kb_raptor_settings
from services.wiki_provenance_service import provenance_for_raptor_drilldown
from services.vector_index import VectorRecord, get_vector_index_backend

logger = logging.getLogger(__name__)


def _raptor_embed_vector(db: Session, summary_text: str) -> list[float]:
    if KB_RAPTOR_USE_EMBED_CACHE:
        return resolve_embedding_vectors(db, [summary_text])[0]
    return embed_texts([summary_text])[0]


RAPTOR_CONTENT_KIND = ContentKind.raptor_summary.value
_MAX_SUMMARY_INPUT_CHARS = 12000
_DEFAULT_DRILL_SCORE_FACTOR = 0.95
_OLLAMA_SUMMARIZE_MAX_ATTEMPTS = 2
_LARGE_DOC_MAX_SUMMARIES_CAP = 16
_CAP_AWARE_CLUSTER_FACTOR = 2


class RaptorBuildError(Exception):
    """RAPTOR tree build failed (may be fail-open)."""


@dataclass(frozen=True)
class _RaptorNode:
    chunk_id: int | None
    text: str
    embedding: list[float]
    char_start: int | None = None
    char_end: int | None = None


@dataclass
class _SummarySpec:
    text: str
    child_chunk_ids: list[int]
    level: int
    char_start: int | None
    char_end: int | None


def _dot(a: list[float], b: list[float]) -> float:
    return sum(x * y for x, y in zip(a, b))


def _norm(vec: list[float]) -> float:
    return math.sqrt(sum(x * x for x in vec)) or 1.0


def _cosine(a: list[float], b: list[float]) -> float:
    return _dot(a, b) / (_norm(a) * _norm(b))


def _normalize_embedding(vec: list[float]) -> np.ndarray:
    arr = np.asarray(vec, dtype=np.float64)
    norm = float(np.linalg.norm(arr))
    if norm <= 0.0:
        return arr
    return arr / norm


def _effective_target_clusters(
    node_count: int,
    target_clusters: int,
    max_summaries: int,
    *,
    factor: int = _CAP_AWARE_CLUSTER_FACTOR,
) -> int:
    """Cap-aware cluster target (120): shrink k when n >> max_summaries."""
    if max_summaries < 1 or node_count <= max_summaries * factor:
        return target_clusters
    cap_target = max(max_summaries * factor, max_summaries + 1)
    return min(target_clusters, cap_target)


def _cluster_by_embedding_reference(
    nodes: list[_RaptorNode], target_clusters: int
) -> list[list[_RaptorNode]]:
    """Pure-Python greedy clustering (reference for tests / regression)."""
    if not nodes:
        return []
    if len(nodes) <= target_clusters:
        return [[n] for n in nodes]

    cluster_size = max(2, min(8, math.ceil(len(nodes) / max(1, target_clusters))))
    remaining = list(nodes)
    clusters: list[list[_RaptorNode]] = []

    while remaining:
        seed = remaining.pop(0)
        cluster = [seed]
        if len(remaining) >= cluster_size - 1:
            scored = sorted(
                remaining,
                key=lambda n: _cosine(seed.embedding, n.embedding),
                reverse=True,
            )
            take = min(cluster_size - 1, len(scored))
            picked = scored[:take]
            cluster.extend(picked)
            picked_ids = {n.chunk_id for n in picked if n.chunk_id is not None}
            remaining = [n for n in remaining if n.chunk_id not in picked_ids]
        clusters.append(cluster)
    return clusters


def _cluster_by_embedding(nodes: list[_RaptorNode], target_clusters: int) -> list[list[_RaptorNode]]:
    if not nodes:
        return []
    if len(nodes) <= target_clusters:
        return [[n] for n in nodes]

    cluster_size = max(2, min(8, math.ceil(len(nodes) / max(1, target_clusters))))
    normalized = [_normalize_embedding(n.embedding) for n in nodes]
    remaining_indices: list[int] = list(range(len(nodes)))
    clusters: list[list[_RaptorNode]] = []

    while remaining_indices:
        seed_idx = remaining_indices.pop(0)
        cluster = [nodes[seed_idx]]
        if len(remaining_indices) >= cluster_size - 1:
            seed_vec = normalized[seed_idx]
            rem_matrix = np.stack([normalized[i] for i in remaining_indices], axis=0)
            scores = rem_matrix @ seed_vec
            order = np.argsort(-scores)
            take = min(cluster_size - 1, len(order))
            picked_indices = [remaining_indices[int(i)] for i in order[:take]]
            cluster.extend(nodes[i] for i in picked_indices)
            picked_set = set(picked_indices)
            remaining_indices = [i for i in remaining_indices if i not in picked_set]
        clusters.append(cluster)
    return clusters


def _parse_ollama_summary_content(content: str | None) -> tuple[str | None, str | None]:
    """Return (summary, error_reason). error_reason set when summary is None."""
    if not content or not str(content).strip():
        return None, "empty_content"
    try:
        parsed = json.loads(content)
    except json.JSONDecodeError:
        return None, "invalid_json"
    if not isinstance(parsed, dict):
        return None, "invalid_json"
    summary = str(parsed.get("summary") or "").strip()
    if not summary:
        return None, "empty_summary"
    return summary, None


def _ollama_summarize_once(
    text: str,
    *,
    timeout_sec: float,
    db: Session | None = None,
    gpu_scheduler: GpuModelSchedulerAdapter | None = None,
    gpu_context: GpuExecutionContext | None = None,
) -> tuple[str | None, str | None]:
    """Single KB post-processing LLM summarize attempt. Returns (summary, error_reason)."""
    body_text = text
    if len(body_text) > _MAX_SUMMARY_INPUT_CHARS:
        logger.debug(
            "kb_raptor summarize input truncated orig_chars=%s cap=%s",
            len(body_text),
            _MAX_SUMMARY_INPUT_CHARS,
        )
        body_text = body_text[:_MAX_SUMMARY_INPUT_CHARS]
    prompt = (
        "Summarize the following document excerpts into one concise paragraph. "
        'Return JSON only: {"summary":"..."}\n\n'
        f"{body_text}"
    )
    if gpu_scheduler is not None:
        if gpu_context is None:
            raise RaptorBuildError("gpu_context is required for scheduler-backed RAPTOR execution")
        gpu_scheduler.switch_to(ModelGroup.RAPTOR, gpu_context)
        gpu_scheduler.acquire_batch(ModelGroup.RAPTOR, [gpu_context.job_id], gpu_context)
        body = gpu_scheduler.execute(
            ModelGroup.RAPTOR,
            gpu_context,
            call=lambda: chat_json(
                prompt,
                db=db,
                purpose="raptor_summary",
                timeout_sec=max(5.0, float(timeout_sec)),
                fresh=True,
                gpu_context=gpu_context,
            ),
        )
    else:
        body = chat_json(
            prompt,
            db=db,
            purpose="raptor_summary",
            timeout_sec=max(5.0, float(timeout_sec)),
            fresh=True,
        )
    if body is None:
        logger.warning("kb_raptor post llm summarize failed")
        return None, "http_error"

    try:
        parsed = RaptorSummaryOutput.model_validate(body)
    except ValidationError:
        logger.warning("kb_raptor post llm summarize returned invalid schema")
        return None, "invalid_schema"
    summary = parsed.summary.strip()
    if not summary:
        return None, "empty_summary"
    return summary, None


def _ollama_summarize(
    text: str,
    *,
    timeout_sec: float,
    job_id: int | None = None,
    db: Session | None = None,
    gpu_scheduler: GpuModelSchedulerAdapter | None = None,
    gpu_context: GpuExecutionContext | None = None,
) -> str | None:
    input_chars = len(text)
    logger.info(
        "kb_raptor progress summarize_start job_id=%s input_chars=%s timeout_sec=%s",
        job_id,
        input_chars,
        timeout_sec,
    )
    t0 = time.perf_counter()
    last_reason: str | None = None
    for attempt in range(1, _OLLAMA_SUMMARIZE_MAX_ATTEMPTS + 1):
        summary, reason = _ollama_summarize_once(
            text,
            timeout_sec=timeout_sec,
            db=db,
            gpu_scheduler=gpu_scheduler,
            gpu_context=gpu_context,
        )
        if summary:
            logger.info(
                "kb_raptor progress summarize_done job_id=%s attempt=%s ms=%s out_chars=%s",
                job_id,
                attempt,
                int((time.perf_counter() - t0) * 1000),
                len(summary),
            )
            return summary
        last_reason = reason
        logger.warning(
            "kb_raptor summarize attempt=%s/%s reason=%s job_id=%s ms=%s",
            attempt,
            _OLLAMA_SUMMARIZE_MAX_ATTEMPTS,
            reason,
            job_id,
            int((time.perf_counter() - t0) * 1000),
        )
        if attempt < _OLLAMA_SUMMARIZE_MAX_ATTEMPTS:
            time.sleep(0.5)
    if last_reason:
        raise RaptorBuildError(f"ollama summary failed: {last_reason}")
    return None


def _char_range_for_nodes(nodes: list[_RaptorNode]) -> tuple[int | None, int | None]:
    starts = [n.char_start for n in nodes if n.char_start is not None]
    ends = [n.char_end for n in nodes if n.char_end is not None]
    if not starts or not ends:
        return None, None
    return min(starts), max(ends)


def _persist_summary_chunk(
    db: Session,
    f: FileModel,
    *,
    spec: _SummarySpec,
    vec: list[float],
    source: str,
    fts_config: str,
    chunk_index: int,
) -> KbChunk:
    meta: dict[str, Any] = {
        "level": spec.level,
        "child_chunk_ids": spec.child_chunk_ids,
    }
    if spec.char_start is not None and spec.char_end is not None:
        meta["source_char_range"] = [spec.char_start, spec.char_end]
    row = KbChunk(
        user_id=f.user_id,
        workspace_id=f.workspace_id,
        file_id=f.id,
        chunk_index=chunk_index,
        source=source,
        text=spec.text,
        heading_path=None,
        block_type="summary",
        content_kind=RAPTOR_CONTENT_KIND,
        content_meta=meta,
        text_search=func.to_tsvector(fts_config, spec.text),
        char_start=spec.char_start if spec.char_start is not None else 0,
        char_end=spec.char_end if spec.char_end is not None else 0,
    )
    db.add(row)
    db.flush()
    embed_model = get_ollama_runtime_config(db).embed_model
    get_vector_index_backend(db).upsert_many(
        [
            VectorRecord(
                chunk_id=int(row.id),
                file_id=f.id,
                workspace_id=f.workspace_id,
                user_id=f.user_id,
                content_kind=RAPTOR_CONTENT_KIND,
                embedding=vec,
                embedding_model=embed_model,
            )
        ]
    )
    return row


def _load_raptor_summary_chunks(db: Session, file_id: int) -> list[KbChunk]:
    return (
        db.query(KbChunk)
        .filter(KbChunk.file_id == file_id, KbChunk.content_kind == RAPTOR_CONTENT_KIND)
        .order_by(KbChunk.chunk_index)
        .all()
    )


def _can_resume_raptor_checkpoint(
    f: FileModel, *, md_char_count: int, summary_count: int
) -> bool:
    """True when partial checkpoint matches fingerprint and tree is not finalized.

    Partial 态：`raptor_built_chunk_count` = 已持久化 summary 数（≠ `chunk_count`）。
    完成态：`raptor_built_chunk_count == chunk_count` → 不 resume。
    """
    if summary_count <= 0:
        return False
    if f.raptor_built_md_chars != md_char_count:
        return False
    if f.raptor_built_chunk_count != summary_count:
        return False
    if f.raptor_built_chunk_count == (f.chunk_count or 0):
        return False
    return True


def clear_raptor_summaries_for_file(db: Session, file_id: int) -> None:
    """Delete raptor_summary chunks and vectors for a file (118)."""
    _clear_raptor_summaries(db, file_id)


def _clear_raptor_summaries(db: Session, file_id: int) -> None:
    rows = _load_raptor_summary_chunks(db, file_id)
    if not rows:
        return
    ids = [int(r.id) for r in rows]
    get_vector_index_backend(db).delete_by_chunk_ids(ids)
    db.query(KbChunk).filter(KbChunk.id.in_(ids)).delete(synchronize_session=False)
    db.flush()


def _commit_raptor_level_checkpoint(
    db: Session,
    f: FileModel,
    *,
    md_char_count: int,
    summary_count: int,
    level: int | None = None,
    max_summaries: int | None = None,
) -> None:
    f.raptor_built_md_chars = md_char_count
    f.raptor_built_chunk_count = summary_count
    db.commit()
    logger.info(
        "kb_raptor checkpoint file_id=%s level=%s summaries=%s max=%s md_chars=%s",
        f.id,
        level,
        summary_count,
        max_summaries,
        md_char_count,
    )


def _finalize_raptor_checkpoint(db: Session, f: FileModel, *, md_char_count: int) -> None:
    f.raptor_built_chunk_count = f.chunk_count
    f.raptor_built_md_chars = md_char_count
    db.commit()


def _nodes_from_summary_chunks(db: Session, chunks: list[KbChunk]) -> list[_RaptorNode]:
    if not chunks:
        return []
    vec_map = get_vector_index_backend(db).get_many([int(c.id) for c in chunks])
    nodes: list[_RaptorNode] = []
    for chunk in chunks:
        cid = int(chunk.id)
        if cid not in vec_map:
            continue
        nodes.append(
            _RaptorNode(
                chunk_id=cid,
                text=chunk.text or "",
                embedding=list(vec_map[cid][0]),
                char_start=chunk.char_start,
                char_end=chunk.char_end,
            )
        )
    return nodes


def _resume_build_state(
    db: Session,
    f: FileModel,
    base_chunks: list[KbChunk],
    *,
    md_char_count: int,
) -> tuple[list[_RaptorNode], int, int, int] | None:
    summaries = _load_raptor_summary_chunks(db, f.id)
    if not _can_resume_raptor_checkpoint(
        f, md_char_count=md_char_count, summary_count=len(summaries)
    ):
        return None

    levels: dict[int, list[KbChunk]] = {}
    for summary in summaries:
        meta = summary.content_meta if isinstance(summary.content_meta, dict) else {}
        lvl = int(meta.get("level", 0))
        levels.setdefault(lvl, []).append(summary)

    if not levels:
        return None

    completed_level = max(levels.keys())
    nodes = _nodes_from_summary_chunks(db, levels[completed_level])
    if not nodes:
        return None

    summary_count = len(summaries)
    next_level = completed_level - 1
    if next_level < 0 and summary_count > 0:
        logger.debug(
            "kb_raptor resume file_id=%s frontier level=%s next_level=%s "
            "(legacy/missing level meta may skip while loop)",
            f.id,
            completed_level,
            next_level,
        )
    all_indices = [int(c.chunk_index) for c in base_chunks] + [
        int(s.chunk_index) for s in summaries
    ]
    next_chunk_index = max(all_indices) + 1
    logger.info(
        "kb_raptor resume file_id=%s from_level=%s next_level=%s summaries=%s",
        f.id,
        completed_level,
        next_level,
        summary_count,
    )
    return nodes, next_level, summary_count, next_chunk_index


def _initial_raptor_nodes(
    db: Session, base_chunks: list[KbChunk], *, file_id: int | None = None
) -> tuple[list[_RaptorNode], int]:
    t0 = time.perf_counter()
    chunk_ids = [int(c.id) for c in base_chunks]
    vec_map = get_vector_index_backend(db).get_many(chunk_ids)
    nodes = [
        _RaptorNode(
            chunk_id=int(c.id),
            text=c.text or "",
            embedding=list(vec_map[int(c.id)][0]),
            char_start=c.char_start,
            char_end=c.char_end,
        )
        for c in base_chunks
        if int(c.id) in vec_map
    ]
    next_chunk_index = max(int(c.chunk_index) for c in base_chunks) + 1
    logger.info(
        "kb_raptor progress file_id=%s load_base_vectors base_chunks=%s loaded=%s ms=%s",
        file_id,
        len(base_chunks),
        len(nodes),
        int((time.perf_counter() - t0) * 1000),
    )
    return nodes, next_chunk_index


def _build_and_persist_tree(
    db: Session,
    f: FileModel,
    base_chunks: list[KbChunk],
    *,
    max_levels: int,
    max_summaries: int,
    timeout_sec: float,
    source: str,
    fts_config: str,
    md_char_count: int,
    job_id: int | None = None,
    checkpoint: bool = True,
    abort_check: Callable[[], None] | None = None,
    progress_summaries_hook: Callable[[int, int], None] | None = None,
    gpu_scheduler: GpuModelSchedulerAdapter | None = None,
    gpu_context: GpuExecutionContext | None = None,
) -> int:
    resume_state = _resume_build_state(db, f, base_chunks, md_char_count=md_char_count)
    if resume_state is not None:
        nodes, level, summary_count, next_chunk_index = resume_state
        logger.info(
            "kb_raptor progress file_id=%s job_id=%s resumed level=%s summaries=%s nodes=%s",
            f.id,
            job_id,
            level,
            summary_count,
            len(nodes),
        )
    else:
        existing = _load_raptor_summary_chunks(db, f.id)
        if existing:
            _clear_raptor_summaries(db, f.id)
            f.raptor_built_chunk_count = None
            f.raptor_built_md_chars = None
            db.flush()
        logger.info(
            "kb_raptor progress file_id=%s job_id=%s build_start base_chunks=%s max_levels=%s max_summaries=%s",
            f.id,
            job_id,
            len(base_chunks),
            max_levels,
            max_summaries,
        )
        nodes, next_chunk_index = _initial_raptor_nodes(db, base_chunks, file_id=f.id)
        level = max(0, max_levels - 1)
        summary_count = 0

    while len(nodes) > 1 and level >= 0 and summary_count < max_summaries:
        target_clusters = max(1, (len(nodes) + 1) // 2)
        effective_target = _effective_target_clusters(
            len(nodes), target_clusters, max_summaries
        )
        logger.info(
            "kb_raptor progress file_id=%s job_id=%s cluster_start level=%s nodes=%s "
            "target_clusters=%s effective_target=%s max_summaries=%s",
            f.id,
            job_id,
            level,
            len(nodes),
            target_clusters,
            effective_target,
            max_summaries,
        )
        cluster_t0 = time.perf_counter()
        clusters = _cluster_by_embedding(nodes, effective_target)
        logger.info(
            "kb_raptor progress file_id=%s job_id=%s cluster_done level=%s clusters=%s ms=%s",
            f.id,
            job_id,
            level,
            len(clusters),
            int((time.perf_counter() - cluster_t0) * 1000),
        )
        summarize_total = sum(
            1
            for cluster in clusters
            if len(cluster) > 1 and any(n.chunk_id is not None for n in cluster)
        )
        logger.info(
            "kb_raptor progress file_id=%s job_id=%s level=%s frontier_nodes=%s "
            "clusters=%s to_summarize=%s summaries=%s/%s",
            f.id,
            job_id,
            level,
            len(nodes),
            len(clusters),
            summarize_total,
            summary_count,
            max_summaries,
        )
        next_nodes: list[_RaptorNode] = []
        summarize_idx = 0
        for cluster in clusters:
            if summary_count >= max_summaries:
                break
            if len(cluster) == 1:
                next_nodes.append(cluster[0])
                continue
            child_ids = [int(n.chunk_id) for n in cluster if n.chunk_id is not None]
            if not child_ids:
                continue
            if summary_count >= max_summaries:
                break
            summarize_idx += 1
            combined = "\n\n".join(n.text for n in cluster if n.text)
            logger.info(
                "kb_raptor progress file_id=%s job_id=%s level=%s cluster=%s/%s "
                "summaries=%s/%s child_chunks=%s input_chars=%s",
                f.id,
                job_id,
                level,
                summarize_idx,
                summarize_total,
                summary_count,
                max_summaries,
                len(child_ids),
                len(combined),
            )
            summary_text = _ollama_summarize(
                combined,
                timeout_sec=timeout_sec,
                job_id=job_id,
                db=db,
                gpu_scheduler=gpu_scheduler,
                gpu_context=gpu_context,
            )
            char_start, char_end = _char_range_for_nodes(cluster)
            vec = _raptor_embed_vector(db, summary_text)
            spec = _SummarySpec(
                text=summary_text,
                child_chunk_ids=child_ids,
                level=level,
                char_start=char_start,
                char_end=char_end,
            )
            row = _persist_summary_chunk(
                db,
                f,
                spec=spec,
                vec=vec,
                source=source,
                fts_config=fts_config,
                chunk_index=next_chunk_index,
            )
            next_chunk_index += 1
            summary_count += 1
            if progress_summaries_hook is not None:
                progress_summaries_hook(summary_count, max_summaries)
            logger.info(
                "kb_raptor progress file_id=%s job_id=%s summary_persisted chunk_id=%s "
                "level=%s summaries=%s/%s",
                f.id,
                job_id,
                row.id,
                level,
                summary_count,
                max_summaries,
            )
            next_nodes.append(
                _RaptorNode(
                    chunk_id=int(row.id),
                    text=summary_text,
                    embedding=vec,
                    char_start=char_start,
                    char_end=char_end,
                )
            )
            if summary_count >= max_summaries:
                break
        nodes = next_nodes
        level -= 1
        if checkpoint:
            _commit_raptor_level_checkpoint(
                db,
                f,
                md_char_count=md_char_count,
                summary_count=summary_count,
                level=level + 1,
                max_summaries=max_summaries,
            )
        if abort_check:
            abort_check()

    if len(nodes) > 1 and summary_count < max_summaries:
        child_ids = [int(n.chunk_id) for n in nodes if n.chunk_id is not None]
        if child_ids:
            combined = "\n\n".join(n.text for n in nodes if n.text)
            logger.info(
                "kb_raptor progress file_id=%s job_id=%s root_merge nodes=%s "
                "summaries=%s/%s input_chars=%s",
                f.id,
                job_id,
                len(nodes),
                summary_count,
                max_summaries,
                len(combined),
            )
            summary_text = _ollama_summarize(
                combined,
                timeout_sec=timeout_sec,
                job_id=job_id,
                db=db,
                gpu_scheduler=gpu_scheduler,
                gpu_context=gpu_context,
            )
            char_start, char_end = _char_range_for_nodes(nodes)
            vec = _raptor_embed_vector(db, summary_text)
            spec = _SummarySpec(
                text=summary_text,
                child_chunk_ids=child_ids,
                level=0,
                char_start=char_start,
                char_end=char_end,
            )
            row = _persist_summary_chunk(
                db,
                f,
                spec=spec,
                vec=vec,
                source=source,
                fts_config=fts_config,
                chunk_index=next_chunk_index,
            )
            summary_count += 1
            if progress_summaries_hook is not None:
                progress_summaries_hook(summary_count, max_summaries)
            logger.info(
                "kb_raptor progress file_id=%s job_id=%s root_summary_persisted chunk_id=%s summaries=%s/%s",
                f.id,
                job_id,
                row.id,
                summary_count,
                max_summaries,
            )
    elif len(nodes) == 1 and summary_count > 0:
        top = db.get(KbChunk, nodes[0].chunk_id)
        if top is not None and isinstance(top.content_meta, dict):
            meta = dict(top.content_meta)
            meta["level"] = 0
            top.content_meta = meta

    if checkpoint and summary_count > 0:
        _finalize_raptor_checkpoint(db, f, md_char_count=md_char_count)

    logger.info(
        "kb_raptor progress file_id=%s job_id=%s build_done summaries=%s max=%s",
        f.id,
        job_id,
        summary_count,
        max_summaries,
    )

    return summary_count


def build_tree(
    db: Session,
    f: FileModel,
    *,
    md_char_count: int,
    source: str,
    fts_config: str,
    job_id: int | None = None,
    abort_check: Callable[[], None] | None = None,
    checkpoint: bool = True,
    force_settings: bool = False,
    progress_summaries_hook: Callable[[int, int], None] | None = None,
    gpu_scheduler: GpuModelSchedulerAdapter | None = None,
    gpu_context: GpuExecutionContext | None = None,
) -> tuple[int, str | None]:
    """Build RAPTOR summary chunks after base index. Returns (count, warning)."""
    settings = get_kb_raptor_settings(db)
    if not force_settings:
        if not settings.enabled:
            return 0, None
        if md_char_count < settings.min_chars:
            return 0, None

    max_summaries = settings.max_summaries_per_file
    from services.system_setting_service import get_kb_large_doc_settings

    large = get_kb_large_doc_settings(db)
    if (md_char_count or 0) > large["char_threshold"]:
        capped = min(max_summaries, _LARGE_DOC_MAX_SUMMARIES_CAP)
        if capped < max_summaries:
            logger.info(
                "kb_raptor large_doc_summary_cap file_id=%s md_chars=%s cap=%s orig=%s",
                f.id,
                md_char_count,
                capped,
                max_summaries,
            )
        max_summaries = capped

    base_chunks = (
        db.query(KbChunk)
        .filter(
            KbChunk.file_id == f.id,
            or_(
                KbChunk.content_kind.is_(None),
                KbChunk.content_kind != RAPTOR_CONTENT_KIND,
            ),
        )
        .order_by(KbChunk.chunk_index)
        .all()
    )
    if len(base_chunks) < 2:
        return 0, None

    logger.info(
        "kb_raptor progress file_id=%s job_id=%s tree_start base_chunks=%s md_chars=%s "
        "max_levels=%s max_summaries=%s force_settings=%s",
        f.id,
        job_id,
        len(base_chunks),
        md_char_count,
        settings.max_levels,
        max_summaries,
        force_settings,
    )

    try:
        count = _build_and_persist_tree(
            db,
            f,
            base_chunks,
            max_levels=settings.max_levels,
            max_summaries=max_summaries,
            timeout_sec=settings.ollama_timeout_sec,
            source=source,
            fts_config=fts_config,
            md_char_count=md_char_count,
            job_id=job_id,
            checkpoint=checkpoint,
            abort_check=abort_check,
            progress_summaries_hook=progress_summaries_hook,
            gpu_scheduler=gpu_scheduler,
            gpu_context=gpu_context,
        )
    except (RaptorBuildError, OllamaEmbedError) as exc:
        raise RaptorBuildError(str(exc)) from exc

    return count, None


def maybe_build_raptor_tree(
    db: Session,
    f: FileModel,
    *,
    md_char_count: int,
    source: str,
    fts_config: str,
    job=None,
    skip_if_unchanged: bool = False,
    abort_check: Callable[[], None] | None = None,
    force_settings: bool = False,
    emit_mq_progress: bool = False,
    gpu_scheduler: GpuModelSchedulerAdapter | None = None,
    gpu_context: GpuExecutionContext | None = None,
) -> None:
    """Index tail hook: fail_open writes warning to job log without failing index."""
    settings = get_kb_raptor_settings(db)
    if not force_settings and not settings.enabled:
        return

    post_llm = get_kb_post_llm_runtime_config(db, fresh=True)
    if post_llm.provider != "ollama":
        # OpenAI-compatible Chat 不使用 Ollama lifecycle；RAPTOR 的 Chat 请求
        # 直接由共享 post client 处理，避免预热错误的环境模型。
        gpu_scheduler = None
        gpu_context = None
    elif gpu_scheduler is None:
        from services.gpu_scheduler_runtime import scheduler_for_job

        gpu_scheduler, gpu_context = scheduler_for_job(
            int(getattr(job, "id", None) or f.id or 0),
            db=db,
        )

    if not force_settings:
        # 101: large doc skip RAPTOR unless kb_large_doc_raptor_enabled (applies to force=true)
        from services.system_setting_service import (
            get_kb_large_doc_settings,
            is_kb_large_doc_raptor_enabled,
        )

        large = get_kb_large_doc_settings(db)
        if (md_char_count or 0) > large["char_threshold"] and not is_kb_large_doc_raptor_enabled(db):
            logger.info(
                "kb_raptor large_doc_skip file_id=%s md_chars=%s force=%s",
                f.id,
                md_char_count,
                bool(getattr(job, "force", False)) if job is not None else False,
            )
            return

    if skip_if_unchanged and job is not None and not job.force:
        existing = (
            db.query(KbChunk)
            .filter(KbChunk.file_id == f.id, KbChunk.content_kind == RAPTOR_CONTENT_KIND)
            .count()
        )
        if (
            existing > 0
            and f.raptor_built_chunk_count == (f.chunk_count or 0)
            and f.raptor_built_md_chars == md_char_count
        ):
            logger.info("kb_raptor skip unchanged file_id=%s", f.id)
            return
    try:
        job_id = int(job.id) if job is not None else None
        progress_hook: Callable[[int, int], None] | None = None
        if emit_mq_progress:

            def _raptor_mq_progress(done: int, total: int) -> None:
                from messaging.mq_progress_notify import maybe_publish_post_progress

                pct = int(100 * done / total) if total else 0
                maybe_publish_post_progress(
                    user_id=int(f.user_id),
                    file_id=int(f.id),
                    progress_stage="RAPTOR",
                    progress_pct=pct,
                    progress_detail=f"{done}/{total}",
                )

            progress_hook = _raptor_mq_progress
        count, _ = build_tree(
            db,
            f,
            md_char_count=md_char_count,
            source=source,
            fts_config=fts_config,
            job_id=job_id,
            abort_check=abort_check,
            force_settings=force_settings,
            progress_summaries_hook=progress_hook,
            gpu_scheduler=gpu_scheduler,
            gpu_context=gpu_context,
        )
        if count:
            logger.info("kb_raptor built file_id=%s summaries=%s", f.id, count)
    except RaptorBuildError as exc:
        partial = (
            db.query(KbChunk)
            .filter(KbChunk.file_id == f.id, KbChunk.content_kind == RAPTOR_CONTENT_KIND)
            .count()
        )
        if partial > 0:
            msg = (
                f"raptor warning: partial tree persisted ({partial} summaries); "
                f"{str(exc)[:400]}"
            )
        else:
            msg = f"raptor warning: {str(exc)[:500]}"
        logger.warning("kb_raptor fail_open file_id=%s %s", f.id, msg)
        if settings.fail_open:
            if job is not None:
                prev = (job.last_error or "").strip()
                job.last_error = f"{prev}; {msg}" if prev else msg
            from services.kb_pipeline_log_service import (
                ACTION_KB_RAPTOR_WARN,
                format_kb_pipeline_detail,
                log_kb_pipeline_event,
                pipeline_reason,
            )

            log_kb_pipeline_event(
                db,
                f.user_id,
                ACTION_KB_RAPTOR_WARN,
                f.id,
                detail=format_kb_pipeline_detail(
                    partial_summaries=partial,
                    reason=pipeline_reason(str(exc)[:200]),
                ),
            )
            return
        raise


def expand_search_items_with_raptor(
    db: Session,
    primary_items: list[dict],
    *,
    allowed_file_ids: set[int] | None,
    drill_k: int,
    score_factor: float = _DEFAULT_DRILL_SCORE_FACTOR,
    top_k: int,
    group_by_file: bool,
) -> tuple[list[dict], dict[str, Any]]:
    """Drill-down from raptor_summary hits to child chunks."""
    meta: dict[str, Any] = {
        "raptor_expanded": False,
        "raptor_drilldown_ids": [],
        "raptor_added_hits": 0,
    }
    if not primary_items or drill_k <= 0:
        return primary_items, meta

    existing_chunk_ids: set[int] = set()
    seeds: list[tuple[int, float]] = []
    for row in primary_items:
        cid = row.get("chunk_id")
        if cid is not None:
            try:
                existing_chunk_ids.add(int(cid))
            except (TypeError, ValueError):
                # Multi-representation hits use virtual IDs such as repr:14470;
                # they are not kb_chunks and cannot seed RAPTOR drill-down.
                continue
        if row.get("content_kind") != RAPTOR_CONTENT_KIND:
            continue
        if cid is None:
            continue
        try:
            seed_id = int(cid)
        except (TypeError, ValueError):
            continue
        seeds.append((seed_id, float(row.get("score") or 0.0)))

    if not seeds:
        return primary_items, meta

    seed_ids = [sid for sid, _ in seeds[:drill_k]]
    rows = db.query(KbChunk).filter(KbChunk.id.in_(seed_ids)).all()
    by_id = {int(r.id): r for r in rows}

    child_scores: dict[int, float] = {}
    for sid, parent_score in seeds[:drill_k]:
        chunk = by_id.get(sid)
        if chunk is None:
            continue
        meta_obj = chunk.content_meta if isinstance(chunk.content_meta, dict) else {}
        raw_children = meta_obj.get("child_chunk_ids") or []
        for raw in raw_children:
            try:
                cid = int(raw)
            except (TypeError, ValueError):
                continue
            if cid in existing_chunk_ids:
                continue
            score = round(parent_score * score_factor, 4)
            if cid in child_scores:
                child_scores[cid] = max(child_scores[cid], score)
                continue
            if len(child_scores) >= drill_k:
                break
            child_scores[cid] = score
        if len(child_scores) >= drill_k:
            break

    child_ids = list(child_scores.keys())
    meta["raptor_drilldown_ids"] = child_ids
    if not child_ids:
        return primary_items, meta

    hit_rows = (
        db.query(KbChunk, FileModel)
        .join(FileModel, FileModel.id == KbChunk.file_id)
        .filter(KbChunk.id.in_(child_ids))
        .all()
    )
    by_child = {int(ch.id): (ch, fi) for ch, fi in hit_rows}
    graph_items: list[dict] = []
    for cid in child_ids:
        pair = by_child.get(cid)
        if pair is None:
            continue
        ch, fi = pair
        if allowed_file_ids is not None and int(fi.id) not in allowed_file_ids:
            continue
        hit = _chunk_hit_dict(ch, fi, child_scores.get(cid, 0.0), vector_score=None)
        hit.update(provenance_for_raptor_drilldown())
        graph_items.append(hit)

    if not graph_items:
        return primary_items, meta

    combined = list(primary_items) + graph_items
    combined.sort(key=lambda x: float(x.get("score") or 0.0), reverse=True)
    if group_by_file:
        merged = _merge_hits_by_file(combined)[:top_k]
    else:
        merged = combined[:top_k]

    meta["raptor_expanded"] = True
    meta["raptor_added_hits"] = len(graph_items)
    return merged, meta
