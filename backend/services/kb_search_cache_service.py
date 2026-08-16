# Copyright (c) 2026 徐泽宇
"""Semantic query-result cache for KB search (028 module A)."""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from models.kb_search_cache_entry import KbSearchCacheEntry


def _sorted_ids_fingerprint(ids: set[int] | list[int] | None) -> str:
    if ids is None:
        return "*"
    normalized = sorted({int(x) for x in ids})
    if not normalized:
        return ""
    return ",".join(str(x) for x in normalized)


def build_scope_hash(
    *,
    workspace_id: int | None,
    allowed_file_ids: set[int] | None,
    top_k: int,
    file_ids: list[int] | None,
    tags: list[str] | None,
    tag_mode: str,
    tag_combine: str,
    hybrid: bool | None,
    filename_boost: bool,
    modality_boost: bool,
    query_expansion: bool,
    include_not_ready: bool,
    include_drafts: bool,
    group_by_file: bool,
    context_chunks: int,
    cross_workspace: bool = False,
    source_files_only: bool = False,
) -> str:
    scope_dict = {
        "allowed_file_ids": _sorted_ids_fingerprint(allowed_file_ids),
        "context_chunks": context_chunks,
        "cross_workspace": cross_workspace,
        "file_ids": _sorted_ids_fingerprint(set(file_ids) if file_ids else None),
        "filename_boost": filename_boost,
        "modality_boost": modality_boost,
        "group_by_file": group_by_file,
        "hybrid": hybrid,
        "include_drafts": include_drafts,
        "include_not_ready": include_not_ready,
        "query_expansion": query_expansion,
        "source_files_only": source_files_only,
        "tag_combine": tag_combine,
        "tag_mode": tag_mode,
        "tags": sorted({t.strip() for t in (tags or []) if t and t.strip()}),
        "top_k": top_k,
        "workspace_id": workspace_id,
    }
    raw = json.dumps(scope_dict, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


@dataclass(frozen=True)
class CacheLookupResult:
    entry_id: int
    similarity: float
    items: list[dict]
    meta: dict
    embedding_model: str
    top_k: int


def _is_expired(entry: KbSearchCacheEntry, ttl_hours: float, now: datetime) -> bool:
    anchor = entry.last_hit_at or entry.updated_at or entry.created_at
    if anchor is None:
        return False
    if anchor.tzinfo is None:
        anchor = anchor.replace(tzinfo=timezone.utc)
    return now - anchor > timedelta(hours=ttl_hours)


def lookup_query_cache(
    db: Session,
    *,
    user_id: int,
    workspace_id: int,
    scope_hash: str,
    query_embedding: list[float],
    similarity_threshold: float,
    ttl_hours: float,
) -> CacheLookupResult | None:
    now = datetime.now(timezone.utc)
    dist_expr = KbSearchCacheEntry.query_embedding.cosine_distance(query_embedding).label("dist")
    stmt = (
        select(KbSearchCacheEntry, dist_expr)
        .where(
            KbSearchCacheEntry.user_id == user_id,
            KbSearchCacheEntry.workspace_id == workspace_id,
            KbSearchCacheEntry.scope_hash == scope_hash,
        )
        .order_by(dist_expr)
        .limit(1)
    )
    row = db.execute(stmt).first()
    if row is None:
        return None
    entry, dist = row
    if _is_expired(entry, ttl_hours, now):
        db.delete(entry)
        db.flush()
        return None
    similarity = max(0.0, 1.0 - float(dist if dist is not None else 1.0))
    if similarity < similarity_threshold:
        return None
    payload = entry.response_payload or {}
    entry.hit_count = int(entry.hit_count or 0) + 1
    entry.last_hit_at = now
    db.add(entry)
    db.flush()
    return CacheLookupResult(
        entry_id=int(entry.id),
        similarity=round(similarity, 4),
        items=list(payload.get("items") or []),
        meta=dict(payload.get("meta") or {}),
        embedding_model=str(payload.get("embedding_model") or ""),
        top_k=int(payload.get("top_k") or 8),
    )


def upsert_query_cache(
    db: Session,
    *,
    user_id: int,
    workspace_id: int,
    scope_hash: str,
    query_text: str,
    query_embedding: list[float],
    items: list[dict],
    meta: dict,
    embedding_model: str,
    top_k: int,
    max_entries_per_user: int,
) -> None:
    payload = {
        "items": items,
        "meta": meta,
        "embedding_model": embedding_model,
        "top_k": top_k,
    }
    now = datetime.now(timezone.utc)
    existing = (
        db.query(KbSearchCacheEntry)
        .filter(
            KbSearchCacheEntry.user_id == user_id,
            KbSearchCacheEntry.workspace_id == workspace_id,
            KbSearchCacheEntry.scope_hash == scope_hash,
            KbSearchCacheEntry.query_text == query_text,
        )
        .first()
    )
    if existing is not None:
        existing.response_payload = payload
        existing.query_embedding = query_embedding
        existing.updated_at = now
        db.add(existing)
    else:
        db.add(
            KbSearchCacheEntry(
                user_id=user_id,
                workspace_id=workspace_id,
                scope_hash=scope_hash,
                query_text=query_text,
                query_embedding=query_embedding,
                response_payload=payload,
                hit_count=0,
                last_hit_at=None,
            )
        )
    db.flush()
    _evict_lru_if_needed(db, user_id=user_id, max_entries=max_entries_per_user)


def _evict_lru_if_needed(db: Session, *, user_id: int, max_entries: int) -> None:
    if max_entries <= 0:
        return
    count = db.query(func.count(KbSearchCacheEntry.id)).filter(KbSearchCacheEntry.user_id == user_id).scalar()
    if count is None or count <= max_entries:
        return
    overflow = int(count) - max_entries
    stale = (
        db.query(KbSearchCacheEntry)
        .filter(KbSearchCacheEntry.user_id == user_id)
        .order_by(
            KbSearchCacheEntry.last_hit_at.asc().nullsfirst(),
            KbSearchCacheEntry.updated_at.asc(),
        )
        .limit(overflow)
        .all()
    )
    for entry in stale:
        db.delete(entry)


def apply_cache_meta(
    meta: dict,
    *,
    cache_hit: bool,
    cache_similarity: float | None,
    cache_entry_id: int | None,
) -> dict:
    out = dict(meta)
    out["cache_hit"] = cache_hit
    out["cache_similarity"] = cache_similarity
    out["cache_entry_id"] = cache_entry_id
    return out
