# Copyright (c) 2026 徐泽宇
"""077 P1: SAG event–entity multi-hop expand for KB search."""

from __future__ import annotations

import json
import logging
import time
from typing import Any, Literal

import httpx
from sqlalchemy import func
from sqlalchemy.orm import Session

from models.file import File as FileModel
from models.kb_chunk import KbChunk
from models.kb_event import KbEvent
from models.kb_event_entity import KbEventEntity
from models.user import User
from services.kb_entity_extract_service import _normalize_entity_name
from services.kb_fts_service import get_effective_fts_config
from services.kb_rerank_service import rerank_hits
from services.kb_search_service import TAG_UNION_SCORE, _chunk_hit_dict
from services.ollama_config_service import get_ollama_runtime_config
from services.system_setting_service import is_kb_sag_query_llm_enabled
from services.wiki_provenance_service import provenance_for_sag_event_hit

logger = logging.getLogger(__name__)

SAG_MAX_SEEDS = 3
SAG_DEFAULT_MAX_HOPS = 2
SAG_DEFAULT_MAX_EVENTS = 50
SAG_SCORE_FACTOR = 0.88
SAG_FALLBACK_SCORE = TAG_UNION_SCORE
SAG_MAX_QUERY_ENTITIES = 20


def resolve_sag_search_mode(
    db: Session,
    requested: Literal["fast", "standard"],
) -> tuple[Literal["fast", "standard"], Literal["fast", "standard"], bool]:
    """Return (effective_mode, requested_mode, degraded)."""
    if requested == "standard" and is_kb_sag_query_llm_enabled(db):
        return "standard", requested, False
    if requested == "standard":
        return "fast", requested, True
    return "fast", requested, False


def _ollama_query_entities_json(prompt: str) -> dict[str, Any] | None:
    cfg = get_ollama_runtime_config(fresh=True)
    payload = {
        "model": cfg.chat_model,
        "messages": [{"role": "user", "content": prompt}],
        "stream": False,
        "format": "json",
    }
    chat_url = f"{cfg.base_url}/api/chat"
    headers: dict[str, str] | None = None
    if cfg.chat_model.endswith(":cloud") and cfg.api_key:
        chat_url = "https://ollama.com/api/chat"
        headers = {"Authorization": f"Bearer {cfg.api_key}"}
    try:
        with httpx.Client(timeout=min(cfg.timeout_sec, 30.0)) as client:
            response = client.post(chat_url, headers=headers, json=payload)
            response.raise_for_status()
            body = response.json()
    except Exception as exc:
        logger.warning("kb_sag_search query llm failed: %s", exc)
        return None

    content = (body.get("message") or {}).get("content")
    if not content:
        return None
    try:
        parsed = json.loads(content)
    except json.JSONDecodeError:
        return None
    return parsed if isinstance(parsed, dict) else None


def _llm_query_entity_prompt(query: str) -> str:
    return (
        "Extract named entities from the user query for knowledge retrieval. "
        'Return JSON only: {"entities":[{"name":"..."}]}. '
        "Use concise canonical Chinese or English names.\n\n"
        f"Query: {query[:2000]}"
    )


def extract_query_entities_llm(query: str) -> list[str]:
    parsed = _ollama_query_entities_json(_llm_query_entity_prompt(query))
    if not parsed:
        return []
    names: list[str] = []
    seen: set[str] = set()
    for ent in parsed.get("entities") or []:
        if not isinstance(ent, dict):
            continue
        name = _normalize_entity_name(str(ent.get("name") or ""))
        if not name or name in seen:
            continue
        seen.add(name)
        names.append(name)
    return names[:SAG_MAX_QUERY_ENTITIES]


def collect_query_entities_fast(
    db: Session,
    query: str,
    *,
    allowed_file_ids: set[int] | None,
    fts_config: str,
) -> list[str]:
    if not query.strip():
        return []
    if allowed_file_ids is not None and not allowed_file_ids:
        return []
    q = db.query(KbEventEntity.entity_name).distinct()
    if allowed_file_ids is not None:
        q = q.filter(KbEventEntity.file_id.in_(allowed_file_ids))
    q = q.filter(
        func.to_tsvector(fts_config, KbEventEntity.entity_name).op("@@")(
            func.plainto_tsquery(fts_config, query)
        )
    )
    names: list[str] = []
    seen: set[str] = set()
    for (raw_name,) in q.limit(SAG_MAX_QUERY_ENTITIES).all():
        name = _normalize_entity_name(str(raw_name or ""))
        if not name or name in seen:
            continue
        seen.add(name)
        names.append(name)
    return names


def collect_query_entities(
    db: Session,
    query: str,
    *,
    mode: Literal["fast", "standard"],
    allowed_file_ids: set[int] | None,
    fts_config: str,
) -> list[str]:
    if mode == "standard":
        llm_names = extract_query_entities_llm(query)
        if llm_names:
            return llm_names
    return collect_query_entities_fast(
        db,
        query,
        allowed_file_ids=allowed_file_ids,
        fts_config=fts_config,
    )


def collect_seed_event_ids(
    db: Session,
    seed_chunk_ids: list[int],
    *,
    allowed_file_ids: set[int] | None,
) -> list[int]:
    seeds = [int(x) for x in seed_chunk_ids if x is not None][:SAG_MAX_SEEDS]
    if not seeds:
        return []
    q = db.query(KbEvent.id).filter(KbEvent.chunk_id.in_(seeds))
    if allowed_file_ids is not None:
        if not allowed_file_ids:
            return []
        q = q.filter(KbEvent.file_id.in_(allowed_file_ids))
    return [int(row[0]) for row in q.all()]


def _entities_for_events(
    db: Session,
    event_ids: list[int],
    *,
    allowed_file_ids: set[int] | None,
) -> set[str]:
    if not event_ids:
        return set()
    q = db.query(KbEventEntity.entity_name).filter(KbEventEntity.event_id.in_(event_ids))
    if allowed_file_ids is not None:
        q = q.filter(KbEventEntity.file_id.in_(allowed_file_ids))
    out: set[str] = set()
    for (raw_name,) in q.all():
        name = _normalize_entity_name(str(raw_name or ""))
        if name:
            out.add(name)
    return out


def multihop_expand_event_ids(
    db: Session,
    *,
    seed_event_ids: list[int],
    query_entities: list[str],
    allowed_file_ids: set[int] | None,
    max_hops: int,
    max_events: int,
) -> tuple[list[int], list[int]]:
    """BFS entity bridge expansion; returns (all_event_ids, hop_only_event_ids)."""
    max_hops = max(1, min(3, int(max_hops)))
    max_events = max(1, min(200, int(max_events)))

    seen_events: set[int] = {int(x) for x in seed_event_ids}
    hop_only: list[int] = []
    frontier_entities: set[str] = {_normalize_entity_name(x) or "" for x in query_entities}
    frontier_entities.discard("")
    frontier_entities |= _entities_for_events(db, list(seen_events), allowed_file_ids=allowed_file_ids)

    for _hop in range(max_hops):
        if len(seen_events) >= max_events or not frontier_entities:
            break
        q = db.query(KbEventEntity.event_id).filter(
            KbEventEntity.entity_name.in_(list(frontier_entities))
        )
        if allowed_file_ids is not None:
            if not allowed_file_ids:
                break
            q = q.filter(KbEventEntity.file_id.in_(allowed_file_ids))
        new_event_ids: list[int] = []
        for (event_id,) in q.distinct().all():
            eid = int(event_id)
            if eid in seen_events:
                continue
            if len(seen_events) >= max_events:
                break
            seen_events.add(eid)
            new_event_ids.append(eid)
            hop_only.append(eid)
        if not new_event_ids:
            break
        frontier_entities = _entities_for_events(db, new_event_ids, allowed_file_ids=allowed_file_ids)

    ordered = list(seed_event_ids)
    for eid in hop_only:
        if eid not in seed_event_ids:
            ordered.append(eid)
    return ordered[:max_events], hop_only


def _chunk_ids_for_events(
    db: Session,
    event_ids: list[int],
    *,
    allowed_file_ids: set[int] | None,
    exclude_chunk_ids: set[int],
) -> list[int]:
    if not event_ids:
        return []
    q = db.query(KbEvent.chunk_id).filter(KbEvent.id.in_(event_ids))
    if allowed_file_ids is not None:
        q = q.filter(KbEvent.file_id.in_(allowed_file_ids))
    out: list[int] = []
    seen: set[int] = set(exclude_chunk_ids)
    for (chunk_id,) in q.all():
        if chunk_id is None:
            continue
        icid = int(chunk_id)
        if icid in seen:
            continue
        seen.add(icid)
        out.append(icid)
    return out


def expand_search_items_with_sag_events(
    db: Session,
    actor: User,
    query: str,
    primary_items: list[dict],
    *,
    allowed_file_ids: set[int] | None,
    sag_search_mode: Literal["fast", "standard"] = "fast",
    max_hops: int | None = None,
    max_events: int | None = None,
    top_k: int,
    group_by_file: bool,
    return_search_trace: bool = False,
) -> tuple[list[dict], dict[str, Any]]:
    del actor, top_k, group_by_file
    effective_mode, requested_mode, degraded = resolve_sag_search_mode(db, sag_search_mode)
    meta: dict[str, Any] = {
        "sag_expanded": False,
        "sag_added_hits": 0,
        "sag_neighbor_event_ids": [],
        "sag_mode_requested": requested_mode,
        "sag_mode_effective": effective_mode,
    }
    if degraded:
        meta["sag_mode_degraded"] = True

    trace: dict[str, Any] | None = None
    timings: dict[str, float] = {}
    if return_search_trace:
        trace = {
            "query_entities": [],
            "seed_event_ids": [],
            "hop_expanded_event_ids": [],
            "reranked_event_ids": [],
            "timings_ms": timings,
        }
        meta["search_trace"] = trace

    if not primary_items:
        return primary_items, meta

    if allowed_file_ids is not None and not allowed_file_ids:
        return primary_items, meta

    t0 = time.perf_counter()
    fts_config = get_effective_fts_config(db)
    query_entities = collect_query_entities(
        db,
        query,
        mode=effective_mode,
        allowed_file_ids=allowed_file_ids,
        fts_config=fts_config,
    )
    timings["query_entities"] = round((time.perf_counter() - t0) * 1000, 2)
    if trace is not None:
        trace["query_entities"] = list(query_entities)

    existing_chunk_ids: set[int] = set()
    seed_chunk_ids: list[int] = []
    seen_seed: set[int] = set()
    for row in primary_items:
        cid = row.get("chunk_id")
        if cid is not None:
            try:
                icid = int(cid)
            except (TypeError, ValueError):
                # Multi-representation hits use virtual IDs such as repr:7541;
                # they are not kb_chunks and cannot seed SAG event expansion.
                continue
            existing_chunk_ids.add(icid)
            if icid not in seen_seed:
                seen_seed.add(icid)
                seed_chunk_ids.append(icid)
                if len(seed_chunk_ids) >= SAG_MAX_SEEDS:
                    break

    t1 = time.perf_counter()
    seed_event_ids = collect_seed_event_ids(
        db,
        seed_chunk_ids,
        allowed_file_ids=allowed_file_ids,
    )
    timings["seed_events"] = round((time.perf_counter() - t1) * 1000, 2)
    if trace is not None:
        trace["seed_event_ids"] = list(seed_event_ids)

    hop_limit = max_hops if max_hops is not None else SAG_DEFAULT_MAX_HOPS
    event_limit = max_events if max_events is not None else SAG_DEFAULT_MAX_EVENTS
    t2 = time.perf_counter()
    expanded_event_ids, hop_event_ids = multihop_expand_event_ids(
        db,
        seed_event_ids=seed_event_ids,
        query_entities=query_entities,
        allowed_file_ids=allowed_file_ids,
        max_hops=hop_limit,
        max_events=event_limit,
    )
    timings["multihop"] = round((time.perf_counter() - t2) * 1000, 2)
    if trace is not None:
        trace["hop_expanded_event_ids"] = list(hop_event_ids)

    neighbor_chunk_ids = _chunk_ids_for_events(
        db,
        expanded_event_ids,
        allowed_file_ids=allowed_file_ids,
        exclude_chunk_ids=existing_chunk_ids,
    )
    meta["sag_neighbor_event_ids"] = expanded_event_ids
    if not neighbor_chunk_ids:
        meta["sag_expanded"] = bool(seed_event_ids or query_entities)
        return primary_items, meta

    rows = (
        db.query(KbChunk, FileModel)
        .join(FileModel, FileModel.id == KbChunk.file_id)
        .filter(KbChunk.id.in_(neighbor_chunk_ids))
        .all()
    )
    by_id = {
        int(chunk.id): _chunk_hit_dict(chunk, f, SAG_FALLBACK_SCORE, vector_score=None)
        for chunk, f in rows
    }
    graph_items = [by_id[cid] for cid in neighbor_chunk_ids if cid in by_id]
    if not graph_items:
        meta["sag_expanded"] = True
        return primary_items, meta

    t3 = time.perf_counter()
    reranked, _applied = rerank_hits(query, graph_items, top_k=len(graph_items))
    timings["rerank"] = round((time.perf_counter() - t3) * 1000, 2)
    if trace is not None:
        trace["reranked_event_ids"] = list(expanded_event_ids)

    for hit in reranked:
        hit["score"] = round(float(hit["score"]) * SAG_SCORE_FACTOR, 4)
        hit.update(provenance_for_sag_event_hit())

    combined = list(primary_items) + reranked
    combined.sort(key=lambda x: float(x["score"]), reverse=True)

    meta["sag_expanded"] = True
    meta["sag_added_hits"] = len(reranked)
    return combined, meta
