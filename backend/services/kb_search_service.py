# Copyright (c) 2026 徐泽宇
"""Semantic search over kb_chunks for current user.

Authors:
    徐泽宇

Copyright:
    © 2026 徐泽宇
"""

from __future__ import annotations

import logging
from collections import defaultdict
from dataclasses import dataclass
from typing import Literal

from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session

logger = logging.getLogger("filex.kb_search")

from config import (
    KB_SEARCH_KEYWORD_GUARD_MAX_LEN,
    KB_SEARCH_TOP_K_MAX,
)
from services.ollama_config_service import get_ollama_runtime_config
from services.kb_citation import attach_citation_fields_to_hit, attach_citations
from services.kb_rerank_service import rerank_enabled, rerank_hits

STATUS_READY = "ready"
RRF_K = 60
TAG_UNION_SCORE = 0.45
from models.file import File as FileModel
from models.kb_chunk import KbChunk
from models.kb_enums import ContentKind
from models.tag import Tag, file_tags
from services.kb_ollama_embed import OllamaEmbedError, embed_text
from services.vector_index import get_vector_index_backend
from services.kb_search_expansion import expand_query_terms, merge_rrf_rankings
from services.kb_figure_refs import build_figure_refs
from services.kb_search_modality import apply_modality_boost_scores, detect_modality_intent
from services.kb_search_rank import (
    apply_boost_keyword_scores,
    apply_filename_boost_scores,
    apply_mmr,
    build_or_tsquery_text,
    extract_query_terms,
)
from services.kb_fts_service import FTS_SIMPLE, get_effective_fts_config, should_use_plainto_for_query
from services.system_setting_service import (
    get_kb_search_default_top_k,
    get_kb_search_rank_settings,
    is_kb_raptor_enabled,
    is_kb_search_hybrid_enabled,
)
from services.user_setting_service import get_user_effective_dict
from services.wiki_provenance_service import provenance_for_search_hit

POST_PENDING_STATUSES = {"pending", "queued", "running"}
PROCESSING_NOTICE = (
    "本轮命中了处理中资料；source_kind=processing_placeholder 的条目仅表示文件状态，"
    "不可作为正式证据引用。source_kind=final_md_post_pending 的条目可基于当前 chunk 作答，"
    "但 RAPTOR/SAG/实体等高级后处理可能稍后更完整。"
)


def _passes_min_score(item: dict, *, min_score: float, fts_chunk_ids: set[int]) -> bool:
    if min_score <= 0:
        return True
    cid = item.get("chunk_id")
    if cid is not None and int(cid) in fts_chunk_ids:
        return True
    vs = item.get("vector_score")
    if vs is None:
        return True
    return float(vs) >= min_score

def _requires_keyword_in_hit(query: str) -> bool:
    q = query.strip()
    if not q or " " in q:
        return False
    return len(q) <= KB_SEARCH_KEYWORD_GUARD_MAX_LEN


def _hit_contains_query(query: str, *, chunk_text: str, original_name: str) -> bool:
    q = query.strip()
    if not q:
        return True
    haystack = f"{chunk_text}\n{original_name or ''}"
    return q in haystack


_SNIPPETS_PER_FILE = 3


def _snippet_from_hit(item: dict) -> dict:
    snip = {
        "chunk_id": item.get("chunk_id"),
        # Multi-representation hits are virtual results and do not map to a
        # concrete KbChunk, so their locator fields are intentionally absent.
        "chunk_index": item.get("chunk_index"),
        "source": item.get("source"),
        "text": item.get("text", ""),
        "score": item.get("score", 0.0),
        "char_start": item.get("char_start"),
        "char_end": item.get("char_end"),
        "heading_path": item.get("heading_path"),
        "block_type": item.get("block_type"),
        "content_kind": item.get("content_kind"),
        "loc_type": item.get("loc_type"),
        "loc_start": item.get("loc_start"),
        "loc_end": item.get("loc_end"),
        "loc_label": item.get("loc_label"),
        "citation_label": item.get("citation_label"),
    }
    return snip


def _merge_hits_by_file(items: list[dict]) -> list[dict]:
    """同一 file_id 合并为一条：主片段取最高 score，另附最多 _SNIPPETS_PER_FILE 条摘要。"""
    by_file: dict[int, dict] = {}
    for item in items:
        fid = int(item["file_id"])
        snip = _snippet_from_hit(item)
        prev = by_file.get(fid)
        if prev is None:
            by_file[fid] = {**item, "matched_chunks": 1, "snippets": [snip]}
            continue
        prev["matched_chunks"] = int(prev.get("matched_chunks", 1)) + 1
        snippets: list[dict] = prev.setdefault("snippets", [])
        snippets.append(snip)
        snippets.sort(key=lambda x: float(x["score"]), reverse=True)
        del snippets[_SNIPPETS_PER_FILE:]
        if float(item["score"]) > float(prev["score"]):
            prev.update(
                {
                    "chunk_index": item.get("chunk_index"),
                    "source": item.get("source"),
                    "text": item.get("text", ""),
                    "score": item.get("score", 0.0),
                    "char_start": item.get("char_start"),
                    "char_end": item.get("char_end"),
                    "heading_path": item.get("heading_path"),
                    "block_type": item.get("block_type"),
                    "loc_type": item.get("loc_type"),
                    "loc_start": item.get("loc_start"),
                    "loc_end": item.get("loc_end"),
                    "loc_label": item.get("loc_label"),
                    "citation_tier": item.get("citation_tier"),
                    "citation_label": item.get("citation_label"),
                    "location": item.get("location"),
                    "source_kind": item.get("source_kind"),
                    "is_final": item.get("is_final", True),
                    "content_confidence": item.get("content_confidence", "final"),
                    "processing_stage": item.get("processing_stage"),
                    "processing_message": item.get("processing_message"),
                    "expected_next_stage": item.get("expected_next_stage"),
                }
            )
    merged = list(by_file.values())
    merged.sort(key=lambda x: float(x["score"]), reverse=True)
    return merged


def _apply_searchable_chunk_filters(
    stmt,
    *,
    include_raptor_summaries: bool,
    raptor_enabled: bool,
):
    if not raptor_enabled and not include_raptor_summaries:
        stmt = stmt.where(
            or_(
                KbChunk.content_kind.is_(None),
                KbChunk.content_kind != ContentKind.raptor_summary.value,
            )
        )
    return stmt


def _attach_file_chunk_counts(
    db: Session,
    items: list[dict],
    *,
    include_raptor_summaries: bool = False,
    raptor_enabled: bool = False,
) -> None:
    file_ids = {
        int(item["file_id"])
        for item in items
        if item.get("file_id") is not None
        and item.get("source_kind") != "processing_placeholder"
    }
    if not file_ids:
        return

    stmt = (
        select(KbChunk.file_id, func.count(KbChunk.id))
        .where(KbChunk.file_id.in_(file_ids))
        .group_by(KbChunk.file_id)
    )
    stmt = _apply_searchable_chunk_filters(
        stmt,
        include_raptor_summaries=include_raptor_summaries,
        raptor_enabled=raptor_enabled,
    )
    rows = db.execute(stmt).all()
    counts = {int(fid): int(count) for fid, count in rows}
    for item in items:
        fid = item.get("file_id")
        if fid is None:
            continue
        count = counts.get(int(fid))
        if count is not None:
            item["file_chunk_count"] = count


def dedupe_search_items_by_chunk_id(items: list[dict]) -> list[dict]:
    """chunk_id 级去重，保留首次出现（含 wiki/doc 图扩展合并后）。

    调用方须在 expand 合并后已按 score 降序排列；本函数先按 score 降序再保留首次出现。
    """
    if not items:
        return []
    ranked = sorted(items, key=lambda x: float(x.get("score") or 0.0), reverse=True)
    seen: set[tuple[str, int | str]] = set()
    out: list[dict] = []
    for item in ranked:
        cid = item.get("chunk_id")
        if cid is not None:
            try:
                key = ("chunk", int(cid))
            except (TypeError, ValueError):
                # Multi-representation hits use virtual IDs such as repr:7541.
                key = ("virtual", str(cid))
            if key in seen:
                continue
            seen.add(key)
        out.append(item)
    return out


def limit_search_items_preserving_processing_placeholders(items: list[dict], top_k: int) -> list[dict]:
    if not items:
        return []
    limit = min(max(1, int(top_k)), KB_SEARCH_TOP_K_MAX)
    placeholders = [
        item
        for item in items
        if item.get("source_kind") == "processing_placeholder"
    ]
    if not placeholders:
        return items[:limit]
    non_placeholders = [
        item
        for item in items
        if item.get("source_kind") != "processing_placeholder"
    ]
    if len(placeholders) >= limit:
        return placeholders[:limit]
    return [*placeholders, *non_placeholders[: limit - len(placeholders)]]


def sync_processing_meta(meta: dict, items: list[dict]) -> dict:
    processing_items = [
        item
        for item in items
        if item.get("processing_stage") is not None
    ]
    meta["processing_hit_count"] = len(processing_items)
    meta["processing_file_ids"] = list(
        dict.fromkeys(int(item["file_id"]) for item in processing_items)
    )
    return meta


def _chunk_hit_dict(chunk, f, score: float, *, vector_score: float | None = None) -> dict:
    hit = {
        "chunk_id": int(chunk.id),
        "file_id": f.id,
        "original_name": f.original_name,
        "has_md": bool(f.has_md),
        "chunk_index": chunk.chunk_index,
        "source": chunk.source,
        "text": chunk.text,
        "score": round(float(score), 4),
        "char_start": chunk.char_start,
        "char_end": chunk.char_end,
        "heading_path": getattr(chunk, "heading_path", None),
        "block_type": getattr(chunk, "block_type", None),
        "content_kind": getattr(chunk, "content_kind", None),
        "content_meta": getattr(chunk, "content_meta", None),
        "boost_keywords": getattr(chunk, "boost_keywords", None),
        "loc_type": getattr(chunk, "loc_type", None),
        "loc_start": getattr(chunk, "loc_start", None),
        "loc_end": getattr(chunk, "loc_end", None),
        "loc_label": getattr(chunk, "loc_label", None),
        "matched_chunks": 1,
        "context_text": None,
    }
    if vector_score is not None:
        hit["vector_score"] = round(float(vector_score), 4)
    hit.update(provenance_for_search_hit(score=score))
    refs = build_figure_refs(f, hit.get("content_kind"), hit.get("content_meta"))
    if refs:
        hit["figure_refs"] = refs
    attach_citation_fields_to_hit(hit, original_name=f.original_name or f.filename or "")
    if hit.pop("_citation_degraded", False):
        logger.info(
            "citation degraded to document_only file_id=%s original_name=%s",
            f.id,
            f.original_name,
        )
    _attach_processing_status(hit, f)
    return hit


def _processing_stage_for_file(f: FileModel) -> tuple[str | None, str | None, str | None, bool, str]:
    extract_status = (getattr(f, "extract_status", None) or "").strip()
    index_status = (getattr(f, "index_status", None) or "").strip()
    post_status = (getattr(f, "kb_post_status", None) or "").strip()
    if index_status != STATUS_READY:
        if extract_status in {"pending", "processing", "queued", "running"}:
            return (
                f"extract_{extract_status}",
                "processing_placeholder",
                "等待文档解析生成正式笔记",
                False,
                "none",
            )
        if index_status in {"pending", "indexing", "queued", "running"}:
            return (
                f"index_{index_status}",
                "processing_placeholder",
                "等待基础索引完成",
                False,
                "none",
            )
        return (
            f"index_{index_status or 'pending'}",
            "processing_placeholder",
            "等待资料处理完成",
            False,
            "none",
        )
    if post_status in POST_PENDING_STATUSES:
        return (
            f"post_{post_status}",
            "final_md_post_pending",
            "等待 RAPTOR/SAG/实体等高级后处理完成",
            True,
            "partial",
        )
    if post_status == "failed":
        return (
            "post_failed",
            "final_md_post_failed",
            "高级后处理失败，基础笔记与 chunk 仍可使用",
            True,
            "partial",
        )
    return (None, None, None, True, "final")


def _attach_processing_status(hit: dict, f: FileModel) -> None:
    stage, source_kind, next_stage, is_final, confidence = _processing_stage_for_file(f)
    hit["is_final"] = is_final
    hit["content_confidence"] = confidence
    if stage is None:
        return
    hit["processing_stage"] = stage
    hit["source_kind"] = source_kind
    hit["expected_next_stage"] = next_stage
    if source_kind == "final_md_post_pending":
        hit["processing_message"] = "基础索引已可用，但后处理仍在进行；多跳、概念和递归摘要稍后可能更完整。"
    elif source_kind == "final_md_post_failed":
        detail = (getattr(f, "kb_post_error", None) or "").strip()
        suffix = f"：{detail}" if detail else ""
        hit["processing_message"] = f"高级后处理失败，基础笔记和 chunk 仍可作为证据{suffix}"


def _processing_placeholder_for_file(f: FileModel, score: float) -> dict:
    stage, source_kind, next_stage, is_final, confidence = _processing_stage_for_file(f)
    name = f.original_name or f.filename or f"file-{f.id}"
    return {
        "chunk_id": None,
        "file_id": int(f.id),
        "original_name": name,
        "has_md": bool(f.has_md),
        "chunk_index": -1,
        "source": "processing_status",
        "text": "",
        "score": round(float(score), 4),
        "char_start": 0,
        "char_end": 0,
        "matched_chunks": 0,
        "heading_path": None,
        "context_text": None,
        "citation_tier": "document_only",
        "citation_label": f"{name}（处理中）",
        "provenance": "inferred",
        "confidence": 0.0,
        "confidence_label": "ambiguous",
        "source_kind": source_kind or "processing_placeholder",
        "is_final": is_final,
        "content_confidence": confidence,
        "processing_stage": stage,
        "expected_next_stage": next_stage,
        "processing_message": "该资料已进入 FileX 后台处理，但尚无可引用的正式笔记或 chunk；不可作为正式证据引用。",
    }


def _append_processing_placeholders(
    db: Session,
    *,
    query: str,
    items: list[dict],
    user_id: int,
    workspace_id: int | None,
    allowed_file_ids: set[int] | None,
    readable_file_ids_query,
    file_ids: list[int] | None,
    include_not_ready: bool,
    include_drafts: bool,
    source_files_only: bool,
    limit: int,
) -> tuple[list[dict], list[int]]:
    if not include_not_ready:
        return items, []
    q = query.strip()
    if not q:
        return items, []
    seen_file_ids = {int(item["file_id"]) for item in items}
    rows = db.query(FileModel).filter(or_(FileModel.index_status != STATUS_READY, FileModel.index_status.is_(None)))
    if workspace_id is not None:
        rows = rows.filter(FileModel.workspace_id == workspace_id)
    elif allowed_file_ids is None and readable_file_ids_query is None:
        rows = rows.filter(FileModel.user_id == user_id)
    if allowed_file_ids is not None:
        if not allowed_file_ids:
            return items, []
        rows = rows.filter(FileModel.id.in_(allowed_file_ids))
    elif readable_file_ids_query is not None:
        rows = rows.filter(FileModel.id.in_(readable_file_ids_query))
    if file_ids:
        rows = rows.filter(FileModel.id.in_(file_ids))
    if not include_drafts:
        rows = rows.filter(FileModel.publish_status == "published")
    if source_files_only:
        rows = rows.filter(FileModel.page_kind == "source")
    rows = rows.filter(
        or_(
            FileModel.original_name.ilike(f"%{q}%"),
            FileModel.filename.ilike(f"%{q}%"),
        )
    )
    placeholders: list[dict] = []
    for f in rows.order_by(FileModel.updated_at.desc(), FileModel.id.desc()).limit(limit).all():
        if int(f.id) in seen_file_ids:
            continue
        placeholders.append(_processing_placeholder_for_file(f, 0.05))
        seen_file_ids.add(int(f.id))
    if not placeholders:
        return items, []
    return [*items, *placeholders], [int(x["file_id"]) for x in placeholders]


def _normalize_tag_names(tags: list[str] | None) -> list[str]:
    if not tags:
        return []
    return [t.strip() for t in tags if t and t.strip()]


def _file_ids_for_tags(
    db: Session,
    *,
    workspace_id: int | None,
    allowed_file_ids: set[int] | None,
    readable_file_ids_query=None,
    tags: list[str],
    tag_mode: Literal["or", "and"],
    include_not_ready: bool,
    include_drafts: bool,
    source_files_only: bool = False,
) -> set[int]:
    norm = _normalize_tag_names(tags)
    if not norm:
        return set()
    query = db.query(FileModel.id)
    if workspace_id is not None:
        query = query.filter(FileModel.workspace_id == workspace_id)
    if allowed_file_ids is not None:
        if not allowed_file_ids:
            return set()
        query = query.filter(FileModel.id.in_(allowed_file_ids))
    elif readable_file_ids_query is not None:
        query = query.filter(FileModel.id.in_(readable_file_ids_query))
    if not include_not_ready:
        query = query.filter(FileModel.index_status == STATUS_READY)
    if not include_drafts:
        query = query.filter(FileModel.publish_status == "published")
    if source_files_only:
        query = query.filter(FileModel.page_kind == "source")
    if tag_mode == "and":
        for tag_name in norm:
            sub = (
                select(file_tags.c.file_id)
                .join(Tag, Tag.id == file_tags.c.tag_id)
                .where(Tag.name == tag_name)
            )
            if allowed_file_ids is not None:
                sub = sub.where(file_tags.c.file_id.in_(allowed_file_ids))
            elif readable_file_ids_query is not None:
                sub = sub.where(file_tags.c.file_id.in_(readable_file_ids_query))
            query = query.filter(FileModel.id.in_(sub))
    else:
        query = query.join(file_tags, file_tags.c.file_id == FileModel.id).join(
            Tag, Tag.id == file_tags.c.tag_id
        )
        query = query.filter(Tag.name.in_(norm))
    return {int(r[0]) for r in query.all()}


def _first_chunk_hit_for_file(db: Session, file_id: int, score: float) -> dict | None:
    row = (
        db.query(KbChunk, FileModel)
        .join(FileModel, FileModel.id == KbChunk.file_id)
        .filter(KbChunk.file_id == file_id)
        .order_by(KbChunk.chunk_index)
        .first()
    )
    if not row:
        return None
    chunk, f = row
    hit = _chunk_hit_dict(chunk, f, score, vector_score=None)
    hit.update(provenance_for_search_hit(score=score, tag_union=True))
    return hit


def _apply_context_chunks(db: Session, user_id: int, items: list[dict], *, context_chunks: int) -> None:
    if context_chunks < 1 or not items:
        return
    file_ids = {int(item["file_id"]) for item in items}
    lo = min(int(item["chunk_index"]) for item in items) - context_chunks
    hi = max(int(item["chunk_index"]) for item in items) + context_chunks
    rows = (
        db.query(KbChunk)
        .filter(
            KbChunk.file_id.in_(file_ids),
            KbChunk.chunk_index >= lo,
            KbChunk.chunk_index <= hi,
        )
        .order_by(KbChunk.file_id, KbChunk.chunk_index)
        .all()
    )
    by_file: dict[int, list[KbChunk]] = defaultdict(list)
    for chunk in rows:
        by_file[int(chunk.file_id)].append(chunk)
    for item in items:
        fid = int(item["file_id"])
        idx = int(item["chunk_index"])
        neighbors = [
            c
            for c in by_file.get(fid, [])
            if idx - context_chunks <= c.chunk_index <= idx + context_chunks
        ]
        if neighbors:
            item["context_text"] = "\n\n".join(c.text for c in neighbors).strip() or None



@dataclass
class KbSearchDebugFunnel:
    vector_candidates: int = 0
    fts_candidates: int = 0
    merged_unique: int = 0
    after_acl_filter: int = 0
    after_min_score: int = 0
    after_rerank: int = 0
    after_mmr: int = 0
    filename_boost_applied: int = 0

    def as_dict(self) -> dict[str, int]:
        return {
            "vector_candidates": self.vector_candidates,
            "fts_candidates": self.fts_candidates,
            "merged_unique": self.merged_unique,
            "after_acl_filter": self.after_acl_filter,
            "after_min_score": self.after_min_score,
            "after_rerank": self.after_rerank,
            "after_mmr": self.after_mmr,
            "filename_boost_applied": self.filename_boost_applied,
        }


def _merge_funnel_partials(partials: list[KbSearchDebugFunnel | None]) -> KbSearchDebugFunnel | None:
    active = [p for p in partials if p is not None]
    if not active:
        return None
    out = KbSearchDebugFunnel()
    out.vector_candidates = max(p.vector_candidates for p in active)
    out.fts_candidates = max(p.fts_candidates for p in active)
    out.merged_unique = max(p.merged_unique for p in active)
    return out



def _fetch_search_candidates(
    db: Session,
    stmt,
    q_vec: list[float],
    q: str,
    *,
    hybrid_enabled: bool,
    fetch_limit: int,
    fts_config: str,
    collect_funnel: bool = False,
) -> tuple[list[tuple], set[int], KbSearchDebugFunnel | None]:
    fts_chunk_ids: set[int] = set()
    rows_scored: list[tuple] = []
    funnel = KbSearchDebugFunnel() if collect_funnel else None
    if hybrid_enabled and hasattr(KbChunk, "text_search"):
        vec_scored = get_vector_index_backend(db).search_scored_rows(
            stmt, q_vec, fetch_limit=fetch_limit
        )
        vec_scores: dict[int, float] = {}
        vec_ranked: list[tuple[int, float]] = []
        vec_rows = []
        for ch, fi, sim in vec_scored:
            cid = int(ch.id)
            vec_scores[cid] = sim
            vec_ranked.append((cid, sim))
            vec_rows.append((ch, fi, 1.0 - sim))
        fts_rows: list = []
        if should_use_plainto_for_query(q):
            ts_query = func.plainto_tsquery(fts_config, q)
            rank_expr = func.ts_rank_cd(KbChunk.text_search, ts_query).label("fts_rank")
            fts_stmt = (
                stmt.where(KbChunk.text_search.op("@@")(ts_query))
                .add_columns(rank_expr)
                .order_by(rank_expr.desc())
                .limit(fetch_limit)
            )
            try:
                fts_rows = db.execute(fts_stmt).all()
            except Exception:
                logger.warning("kb_search fts plainto degraded config=%s q_len=%s", fts_config, len(q), exc_info=True)
                fts_rows = []
        if len(fts_rows) < max(3, fetch_limit // 8):
            or_text = build_or_tsquery_text(extract_query_terms(q))
            if or_text:
                or_ts_query = func.to_tsquery(fts_config, or_text)
                or_rank_expr = func.ts_rank_cd(KbChunk.text_search, or_ts_query).label("fts_rank")
                or_fts_stmt = (
                    stmt.where(KbChunk.text_search.op("@@")(or_ts_query))
                    .add_columns(or_rank_expr)
                    .order_by(or_rank_expr.desc())
                    .limit(fetch_limit)
                )
                try:
                    or_rows = db.execute(or_fts_stmt).all()
                except Exception:
                    logger.warning("kb_search fts or_tsquery degraded config=%s", fts_config, exc_info=True)
                    or_rows = []
                seen_ids = {int(r[0].id) for r in fts_rows}
                fts_rows = list(fts_rows) + [r for r in or_rows if int(r[0].id) not in seen_ids]
        fts_ranked = [(int(r[0].id), float(r[2] or 0.0)) for r in fts_rows]
        fts_chunk_ids = {cid for cid, _ in fts_ranked}
        if funnel is not None:
            funnel.vector_candidates = len(vec_ranked)
            funnel.fts_candidates = len(fts_ranked)
        merged_scores: dict[int, float] = {}
        for ranked in (vec_ranked, fts_ranked):
            for rank, (cid, _) in enumerate(ranked):
                merged_scores[cid] = merged_scores.get(cid, 0.0) + 1.0 / (RRF_K + rank + 1)
        by_id: dict[int, tuple] = {}
        for r in vec_rows:
            cid = int(r[0].id)
            by_id[cid] = (r[0], r[1], vec_scores[cid])
        for r in fts_rows:
            cid = int(r[0].id)
            if cid not in by_id:
                by_id[cid] = (r[0], r[1], vec_scores.get(cid, 0.0))
        for cid, sc in sorted(merged_scores.items(), key=lambda x: x[1], reverse=True)[:fetch_limit]:
            if cid in by_id:
                ch, fi, vsc = by_id[cid]
                rows_scored.append((ch, fi, sc, vsc))
        if funnel is not None:
            funnel.merged_unique = len(merged_scores)
    else:
        raw = get_vector_index_backend(db).search_scored_rows(
            stmt, q_vec, fetch_limit=fetch_limit
        )
        for c, f, vsc in raw:
            rows_scored.append((c, f, vsc, vsc))
        if funnel is not None:
            funnel.vector_candidates = len(raw)
            funnel.merged_unique = len(rows_scored)
    return rows_scored, fts_chunk_ids, funnel


def _collect_rows_for_queries(
    db: Session,
    stmt,
    q: str,
    q_vec: list[float],
    search_terms: list[str],
    *,
    hybrid_enabled: bool,
    fetch_limit: int,
    fts_config: str,
    collect_funnel: bool = False,
) -> tuple[list[tuple], set[int], KbSearchDebugFunnel | None]:
    if len(search_terms) <= 1:
        return _fetch_search_candidates(
            db,
            stmt,
            q_vec,
            q,
            hybrid_enabled=hybrid_enabled,
            fetch_limit=fetch_limit,
            fts_config=fts_config,
            collect_funnel=collect_funnel,
        )
    term_rankings: list[list[int]] = []
    by_id: dict[int, tuple] = {}
    all_fts: set[int] = set()
    partials: list[KbSearchDebugFunnel | None] = []
    for term in search_terms:
        term_vec = q_vec if term == q else embed_text(term)
        rows, fts_ids, partial = _fetch_search_candidates(
            db,
            stmt,
            term_vec,
            term,
            hybrid_enabled=hybrid_enabled,
            fetch_limit=fetch_limit,
            fts_config=fts_config,
            collect_funnel=collect_funnel,
        )
        partials.append(partial)
        all_fts |= fts_ids
        ranked = [int(ch.id) for ch, _, _, _ in rows]
        if ranked:
            term_rankings.append(ranked)
        for ch, fi, _sc, vsc in rows:
            cid = int(ch.id)
            if cid not in by_id:
                by_id[cid] = (ch, fi, vsc)
    if not term_rankings:
        return [], all_fts, _merge_funnel_partials(partials)
    merged = merge_rrf_rankings(term_rankings, k=RRF_K)
    rows_scored: list[tuple] = []
    for cid, rrf_sc in sorted(merged.items(), key=lambda x: x[1], reverse=True)[:fetch_limit]:
        if cid in by_id:
            ch, fi, vsc = by_id[cid]
            rows_scored.append((ch, fi, rrf_sc, vsc))
    return rows_scored, all_fts, _merge_funnel_partials(partials)


def measure_recall_baseline(
    db: Session,
    user_id: int,
    test_queries: list[dict],
    *,
    workspace_id: int | None = None,
) -> dict:
    """146 P2: Measure recall baseline for a set of test queries.

    Each test query should have:
        - query: str
        - expected_file_ids: list[int] (ground truth relevant files)

    Returns:
        dict with recall@5, recall@10, recall@20 and per-query details.
    """
    if not test_queries:
        return {"recall_at_5": 0.0, "recall_at_10": 0.0, "recall_at_20": 0.0, "queries": []}

    results = []
    for tq in test_queries:
        query = tq.get("query", "")
        expected = set(tq.get("expected_file_ids") or [])
        if not query or not expected:
            continue

        try:
            items, _, _, _ = search_kb(
                db, user_id, query,
                workspace_id=workspace_id,
                top_k=20,
                hybrid=True,
            )
        except Exception:
            results.append({"query": query, "error": True})
            continue

        retrieved_ids = [item.get("file_id") for item in items if item.get("file_id")]

        def recall_at(k: int) -> float:
            if not expected:
                return 0.0
            hits = len(set(retrieved_ids[:k]) & expected)
            return hits / len(expected)

        results.append({
            "query": query,
            "expected_count": len(expected),
            "retrieved_count": len(retrieved_ids),
            "recall_at_5": round(recall_at(5), 4),
            "recall_at_10": round(recall_at(10), 4),
            "recall_at_20": round(recall_at(20), 4),
        })

    if not results:
        return {"recall_at_5": 0.0, "recall_at_10": 0.0, "recall_at_20": 0.0, "queries": []}

    avg_r5 = sum(r.get("recall_at_5", 0) for r in results) / len(results)
    avg_r10 = sum(r.get("recall_at_10", 0) for r in results) / len(results)
    avg_r20 = sum(r.get("recall_at_20", 0) for r in results) / len(results)

    return {
        "recall_at_5": round(avg_r5, 4),
        "recall_at_10": round(avg_r10, 4),
        "recall_at_20": round(avg_r20, 4),
        "query_count": len(results),
        "queries": results,
    }


def search_kb(
    db: Session,
    user_id: int,
    query: str,
    *,
    workspace_id: int | None = None,
    allowed_file_ids: set[int] | None = None,
    readable_file_ids_query=None,
    top_k: int | None = None,
    file_ids: list[int] | None = None,
    tags: list[str] | None = None,
    tag_mode: Literal["or", "and"] = "or",
    tag_combine: Literal["filter", "union"] = "filter",
    include_not_ready: bool = False,
    include_drafts: bool = False,
    source_files_only: bool = False,
    group_by_file: bool = False,
    context_chunks: int = 0,
    citation_format: Literal["none", "markdown", "json"] = "none",
    debug: bool = False,
    filename_boost: bool = False,
    modality_boost: bool = False,
    modality_boost_value: float | None = None,
    hybrid: bool | None = None,
    query_expansion: bool = False,
    include_raptor_summaries: bool = False,
    multi_repr_enabled: bool = False,
    multi_repr_types: list[str] | None = None,
    trace_id: str | None = None,
    request_scope: str | None = None,
) -> tuple[list[dict], str, int, dict]:
    # 187: the router-owned context is accepted by the primary and nested
    # search calls; the public envelope is finalized only at the router.
    trace_enabled = trace_id is not None
    del request_scope
    q = query.strip()
    if not q:
        raise ValueError("query required")

    effective = get_user_effective_dict(db, user_id)
    k = top_k if top_k is not None else get_kb_search_default_top_k(db, effective=effective)
    k = min(max(1, k), KB_SEARCH_TOP_K_MAX)

    rank_settings = get_kb_search_rank_settings(db, effective=effective)
    embed_model = get_ollama_runtime_config(db).embed_model

    try:
        q_vec = embed_text(q)
    except OllamaEmbedError as exc:
        raise exc

    fetch_limit = min(max(k * 12, k), 200)

    stmt = select(KbChunk, FileModel).join(FileModel, FileModel.id == KbChunk.file_id)
    if workspace_id is not None:
        stmt = stmt.where(FileModel.workspace_id == workspace_id)
    elif allowed_file_ids is None and readable_file_ids_query is None:
        stmt = stmt.where(KbChunk.user_id == user_id, FileModel.user_id == user_id)
    if allowed_file_ids is not None:
        if not allowed_file_ids:
            empty_acl_funnel = KbSearchDebugFunnel() if debug or trace_enabled else None
            if empty_acl_funnel is not None:
                empty_acl_funnel.after_acl_filter = 0
            return [], embed_model, k, _search_meta(
                hybrid_enabled=False,
                effective_hybrid=False,
                rerank_applied=False,
                rank_settings=rank_settings,
                filename_boost_enabled=False,
                filename_boost_value=0.0,
                modality_boost_enabled=False,
                modality_boost_value=0.0,
                modality_intent=[],
                query_expansion_enabled=False,
                expanded_terms=[],
                effective_fts_config=FTS_SIMPLE,
                debug=debug,
                debug_funnel=empty_acl_funnel.as_dict() if empty_acl_funnel is not None else None,
            )
        stmt = stmt.where(KbChunk.file_id.in_(allowed_file_ids))
    elif readable_file_ids_query is not None:
        stmt = stmt.where(KbChunk.file_id.in_(readable_file_ids_query))
    stmt = stmt.where(FileModel.index_status == STATUS_READY)
    if not include_drafts:
        stmt = stmt.where(FileModel.publish_status == "published")
    if source_files_only:
        stmt = stmt.where(FileModel.page_kind == "source")
    if file_ids:
        stmt = stmt.where(KbChunk.file_id.in_(file_ids))
    raptor_enabled = is_kb_raptor_enabled(db)
    stmt = _apply_searchable_chunk_filters(
        stmt,
        include_raptor_summaries=include_raptor_summaries,
        raptor_enabled=raptor_enabled,
    )
    norm_tags = _normalize_tag_names(tags)
    tag_union_ids: set[int] | None = None
    if norm_tags and tag_combine == "union":
        tag_union_ids = _file_ids_for_tags(
            db,
            workspace_id=workspace_id,
            allowed_file_ids=allowed_file_ids,
            readable_file_ids_query=readable_file_ids_query,
            tags=norm_tags,
            tag_mode=tag_mode,
            include_not_ready=False,
            include_drafts=include_drafts,
            source_files_only=source_files_only,
        )
    elif norm_tags:
        if tag_mode == "and":
            for tag_name in norm_tags:
                sub = (
                    select(file_tags.c.file_id)
                    .join(Tag, Tag.id == file_tags.c.tag_id)
                    .where(Tag.name == tag_name)
                )
                if allowed_file_ids is not None:
                    sub = sub.where(file_tags.c.file_id.in_(allowed_file_ids))
                stmt = stmt.where(KbChunk.file_id.in_(sub))
        else:
            stmt = stmt.join(file_tags, file_tags.c.file_id == KbChunk.file_id).join(
                Tag, Tag.id == file_tags.c.tag_id
            )
            stmt = stmt.where(Tag.name.in_(norm_tags))

    if hybrid is None:
        hybrid_enabled = is_kb_search_hybrid_enabled(db, effective=effective)
    else:
        hybrid_enabled = bool(hybrid)

    effective_fts_config = get_effective_fts_config(db, effective=effective)

    search_terms = [q]
    expanded_terms: list[str] = []
    if query_expansion:
        search_terms, expanded_terms = expand_query_terms(q)

    debug_funnel: KbSearchDebugFunnel | None = (
        KbSearchDebugFunnel() if debug or trace_enabled else None
    )
    rows_scored, fts_chunk_ids, fetch_funnel = _collect_rows_for_queries(
        db,
        stmt,
        q,
        q_vec,
        search_terms,
        hybrid_enabled=hybrid_enabled,
        fetch_limit=fetch_limit,
        fts_config=effective_fts_config,
        collect_funnel=debug or trace_enabled,
    )
    if debug_funnel is not None and fetch_funnel is not None:
        debug_funnel.vector_candidates = fetch_funnel.vector_candidates
        debug_funnel.fts_candidates = fetch_funnel.fts_candidates
        debug_funnel.merged_unique = fetch_funnel.merged_unique
        debug_funnel.after_acl_filter = len(rows_scored)

    keyword_guard = _requires_keyword_in_hit(q) and not hybrid_enabled
    min_score = rank_settings.min_score
    chunk_items: list[dict] = []
    for chunk, f, score, vector_score in rows_scored:
        if keyword_guard and not _hit_contains_query(
            q, chunk_text=chunk.text, original_name=f.original_name or ""
        ):
            continue
        chunk_items.append(_chunk_hit_dict(chunk, f, score, vector_score=vector_score))
    if min_score > 0:
        chunk_items = [
            it
            for it in chunk_items
            if _passes_min_score(it, min_score=min_score, fts_chunk_ids=fts_chunk_ids)
        ]
    if debug_funnel is not None:
        debug_funnel.after_min_score = len(chunk_items)

    if tag_union_ids:
        seen_file_ids = {int(item["file_id"]) for item in chunk_items}
        for fid in tag_union_ids:
            if fid in seen_file_ids:
                continue
            hit = _first_chunk_hit_for_file(db, fid, TAG_UNION_SCORE)
            if hit is not None:
                chunk_items.append(hit)
                seen_file_ids.add(fid)

    _attach_file_chunk_counts(
        db,
        chunk_items,
        include_raptor_summaries=include_raptor_summaries,
        raptor_enabled=raptor_enabled,
    )

    apply_boost_keyword_scores(chunk_items, q, bonus_per_hit=rank_settings.boost_keyword_bonus)
    filename_boost_enabled = bool(filename_boost)
    filename_boost_value = rank_settings.filename_boost if filename_boost_enabled else 0.0
    if filename_boost_enabled and filename_boost_value > 0:
        apply_filename_boost_scores(
            chunk_items,
            q,
            boost_value=filename_boost_value,
            debug=debug,
        )
        if debug_funnel is not None:
            debug_funnel.filename_boost_applied = sum(
                1 for it in chunk_items if it.get("filename_boost")
            )
    modality_boost_enabled = bool(modality_boost)
    modality_boost_value_eff = rank_settings.modality_boost if modality_boost_enabled else 0.0
    if modality_boost_enabled and modality_boost_value is not None:
        modality_boost_value_eff = max(0.0, min(0.5, float(modality_boost_value)))
    modality_intent = detect_modality_intent(q) if modality_boost_enabled else []
    if modality_boost_enabled and modality_boost_value_eff > 0 and modality_intent:
        apply_modality_boost_scores(
            chunk_items,
            modality_intent,
            boost_value=modality_boost_value_eff,
            debug=debug,
        )
    chunk_items.sort(key=lambda x: float(x["score"]), reverse=True)

    if group_by_file:
        reranked_chunks, rerank_applied = rerank_hits(q, chunk_items, top_k=max(k, min(len(chunk_items), k * 4)))
        items = _merge_hits_by_file(reranked_chunks)[:k]
        if debug_funnel is not None:
            debug_funnel.after_mmr = len(items)
    else:
        pool = chunk_items[: min(len(chunk_items), max(k * 4, fetch_limit // 2))]
        if rank_settings.mmr_lambda > 0 and len(pool) > k:
            items = apply_mmr(pool, top_k=k, lambda_mult=rank_settings.mmr_lambda)
            if debug_funnel is not None:
                debug_funnel.after_mmr = len(items)
        else:
            items = pool[:k]
            if debug_funnel is not None:
                debug_funnel.after_mmr = len(items)
        items, rerank_applied = rerank_hits(q, items, top_k=k)
    if debug_funnel is not None:
        debug_funnel.after_rerank = len(items)
    _apply_context_chunks(db, user_id, items, context_chunks=max(0, min(context_chunks, 3)))
    if citation_format in ("markdown", "json"):
        items = attach_citations(items, fmt=citation_format)
    items, _placeholder_file_ids = _append_processing_placeholders(
        db,
        query=q,
        items=items,
        user_id=user_id,
        workspace_id=workspace_id,
        allowed_file_ids=allowed_file_ids,
        readable_file_ids_query=readable_file_ids_query,
        file_ids=file_ids,
        include_not_ready=include_not_ready,
        include_drafts=include_drafts,
        source_files_only=source_files_only,
        limit=k,
    )
    items = limit_search_items_preserving_processing_placeholders(items, k)
    meta = _search_meta(
        hybrid_enabled=hybrid_enabled,
        effective_hybrid=hybrid_enabled,
        rerank_applied=rerank_applied,
        rank_settings=rank_settings,
        filename_boost_enabled=filename_boost_enabled,
        filename_boost_value=filename_boost_value if filename_boost_enabled else 0.0,
        modality_boost_enabled=modality_boost_enabled,
        modality_boost_value=modality_boost_value_eff if modality_boost_enabled else 0.0,
        modality_intent=modality_intent,
        query_expansion_enabled=bool(query_expansion),
        expanded_terms=expanded_terms,
        effective_fts_config=effective_fts_config,
        debug=debug,
        debug_funnel=debug_funnel.as_dict() if debug_funnel is not None else None,
    )
    sync_processing_meta(meta, items)
    if debug:
        for it in items:
            it.setdefault("debug", True)

    # 146 P2: multi-representation index search
    if multi_repr_enabled:
        try:
            from services.kb_multi_repr_service import search_repr

            repr_items = search_repr(
                db,
                q_vec,
                workspace_id=workspace_id,
                allowed_file_ids=allowed_file_ids,
                representation_types=multi_repr_types,
                top_k=k,
            )
            # Merge: dedup by file_id, keep highest score
            seen_files: dict[int, float] = {}
            for item in items:
                fid = item.get("file_id")
                if fid is not None:
                    seen_files[int(fid)] = max(
                        seen_files.get(int(fid), 0),
                        float(item.get("score") or 0),
                    )
            seen_chunk_ids = {
                int(item["chunk_id"])
                for item in items
                if isinstance(item.get("chunk_id"), int)
            }
            for ri in repr_items:
                fid = ri["file_id"]
                source_id = str(ri.get("source_id") or "")
                if (
                    ri.get("representation_type") == "section_context"
                    and source_id.startswith("chunk:")
                    and source_id.removeprefix("chunk:").isdigit()
                ):
                    chunk = db.get(KbChunk, int(source_id.removeprefix("chunk:")))
                    if chunk is not None and int(chunk.file_id) == int(fid):
                        file_row = db.get(FileModel, int(fid))
                        if file_row is not None:
                            hit = _chunk_hit_dict(chunk, file_row, float(ri["score"]))
                            hit["source_kind"] = "multi_repr:section_context"
                            if fid in seen_files and group_by_file:
                                existing = next(item for item in items if int(item["file_id"]) == int(fid))
                                snippets = existing.setdefault("snippets", [_snippet_from_hit(existing)])
                                if not any(snip.get("chunk_index") == hit["chunk_index"] for snip in snippets):
                                    snippets.append(_snippet_from_hit(hit))
                                    snippets.sort(key=lambda snip: float(snip["score"]), reverse=True)
                                    del snippets[_SNIPPETS_PER_FILE:]
                                    existing["matched_chunks"] = int(existing.get("matched_chunks") or 1) + 1
                                continue
                            if not group_by_file and int(hit["chunk_id"]) not in seen_chunk_ids:
                                items.append(hit)
                                seen_chunk_ids.add(int(hit["chunk_id"]))
                                seen_files[int(fid)] = float(ri["score"])
                            elif fid not in seen_files:
                                items.append(hit)
                                seen_chunk_ids.add(int(hit["chunk_id"]))
                                seen_files[int(fid)] = float(ri["score"])
                            continue
                if fid not in seen_files:
                    file_row = db.get(FileModel, int(fid))
                    items.append({
                        # A representation is document-level evidence, not a
                        # persisted KbChunk. Keep the public hit shape valid
                        # without fabricating a chunk id or locator.
                        "chunk_id": None,
                        "file_id": fid,
                        "original_name": file_row.original_name if file_row is not None else "",
                        "has_md": bool(file_row.has_md) if file_row is not None else False,
                        "chunk_index": None,
                        "source": None,
                        "text": ri["text"],
                        "score": ri["score"],
                        "char_start": None,
                        "char_end": None,
                        "citation_label": None,
                        "source_kind": f"multi_repr:{ri['representation_type']}",
                    })
            items.sort(key=lambda x: float(x.get("score") or 0), reverse=True)
            items = items[:k]
            meta["multi_repr_enabled"] = True
            meta["multi_repr_added_hits"] = len(repr_items)
        except Exception:
            meta["multi_repr_enabled"] = False

    return items, embed_model, k, meta


def _search_meta(
    *,
    hybrid_enabled: bool,
    effective_hybrid: bool,
    rerank_applied: bool,
    rank_settings,
    filename_boost_enabled: bool,
    filename_boost_value: float,
    modality_boost_enabled: bool,
    modality_boost_value: float,
    modality_intent: list[str],
    query_expansion_enabled: bool,
    expanded_terms: list[str],
    effective_fts_config: str,
    debug: bool,
    debug_funnel: dict[str, int] | None = None,
) -> dict:
    meta = {
        "hybrid_enabled": hybrid_enabled,
        "effective_hybrid": effective_hybrid,
        "rerank_enabled": rerank_enabled(),
        "rerank_applied": rerank_applied,
        "min_score": rank_settings.min_score,
        "mmr_lambda": rank_settings.mmr_lambda,
        "boost_keyword_bonus": rank_settings.boost_keyword_bonus,
        "filename_boost_enabled": filename_boost_enabled,
        "filename_boost_value": filename_boost_value,
        "modality_boost_enabled": modality_boost_enabled,
        "modality_boost_value": modality_boost_value,
        "modality_intent": modality_intent,
        "query_expansion_enabled": query_expansion_enabled,
        "expanded_terms": expanded_terms,
        "effective_fts_config": effective_fts_config,
    }
    if debug:
        meta["debug"] = True
    if debug_funnel is not None:
        meta["debug_funnel"] = debug_funnel
    return meta
