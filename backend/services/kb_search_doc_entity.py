# Copyright (c) 2026 徐泽宇
"""030 P3: document entity graph expand — neighbor chunk 二次扩召回。"""

from __future__ import annotations

from typing import Any

from sqlalchemy.orm import Session

from models.file import File as FileModel
from models.kb_chunk import KbChunk
from models.kb_doc_entity_edge import KbDocEntityEdge
from models.user import User
from services.kb_search_service import TAG_UNION_SCORE, _chunk_hit_dict, _merge_hits_by_file
from services.wiki_provenance_service import provenance_for_doc_entity_hit

DOC_ENTITY_MAX_SEEDS = 3
DOC_ENTITY_MAX_NEIGHBORS = 8
DOC_ENTITY_SCORE_FACTOR = 0.90
DOC_ENTITY_FALLBACK_SCORE = TAG_UNION_SCORE


def collect_doc_entity_neighbor_chunk_ids(
    db: Session,
    seed_chunk_ids: list[int],
    *,
    include_coref: bool = False,
    max_neighbors: int = DOC_ENTITY_MAX_NEIGHBORS,
    exclude_chunk_ids: set[int] | None = None,
) -> list[int]:
    """从种子 chunk 的实体边收集同文件邻居 chunk_id，保序去重。"""
    exclude = set(exclude_chunk_ids or ())
    seeds = [int(x) for x in seed_chunk_ids if x is not None][:DOC_ENTITY_MAX_SEEDS]
    if not seeds:
        return []

    seed_rows = db.query(KbChunk).filter(KbChunk.id.in_(seeds)).all()
    seed_file_ids = {int(c.file_id) for c in seed_rows}
    if not seed_file_ids:
        return []

    entity_names: set[str] = set()
    direct_edges = (
        db.query(KbDocEntityEdge)
        .filter(
            KbDocEntityEdge.file_id.in_(seed_file_ids),
            KbDocEntityEdge.source_chunk_id.in_(seeds),
        )
        .all()
    )
    for edge in direct_edges:
        if edge.entity_name:
            entity_names.add(edge.entity_name)
        if include_coref and edge.target_entity_name:
            entity_names.add(edge.target_entity_name)

    if include_coref and entity_names:
        coref_edges = (
            db.query(KbDocEntityEdge)
            .filter(
                KbDocEntityEdge.file_id.in_(seed_file_ids),
                KbDocEntityEdge.entity_name.in_(list(entity_names)),
            )
            .all()
        )
    else:
        coref_edges = direct_edges

    seen: set[int] = set(exclude)
    neighbors: list[int] = []
    for edge in coref_edges:
        cid = edge.source_chunk_id
        if cid is None:
            continue
        icid = int(cid)
        if icid in seen:
            continue
        seen.add(icid)
        neighbors.append(icid)
        if len(neighbors) >= max_neighbors:
            break
    return neighbors


def expand_search_items_with_doc_entities(
    db: Session,
    actor: User,
    primary_items: list[dict],
    *,
    allowed_file_ids: set[int] | None = None,
    include_coref: bool = False,
    top_k: int,
    group_by_file: bool,
) -> tuple[list[dict], dict[str, Any]]:
    """对文档实体邻居 chunk 扩召回并合并进 primary items。"""
    del actor
    meta: dict[str, Any] = {
        "doc_entity_expanded": False,
        "doc_entity_neighbor_ids": [],
        "doc_entity_added_hits": 0,
    }
    if not primary_items:
        return primary_items, meta

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
                # they are not kb_chunks and cannot seed entity expansion.
                continue
            existing_chunk_ids.add(icid)
            if icid not in seen_seed:
                seen_seed.add(icid)
                seed_chunk_ids.append(icid)
                if len(seed_chunk_ids) >= DOC_ENTITY_MAX_SEEDS:
                    break

    neighbor_ids = collect_doc_entity_neighbor_chunk_ids(
        db,
        seed_chunk_ids,
        include_coref=include_coref,
        exclude_chunk_ids=existing_chunk_ids,
    )
    if not neighbor_ids:
        return primary_items, meta

    rows = (
        db.query(KbChunk, FileModel)
        .join(FileModel, FileModel.id == KbChunk.file_id)
        .filter(KbChunk.id.in_(neighbor_ids))
        .all()
    )
    if allowed_file_ids is not None:
        rows = [(chunk, f) for chunk, f in rows if int(f.id) in allowed_file_ids]
    visible_neighbor_ids = {int(chunk.id) for chunk, _ in rows}
    meta["doc_entity_neighbor_ids"] = [cid for cid in neighbor_ids if cid in visible_neighbor_ids]
    by_id = {
        int(chunk.id): _chunk_hit_dict(chunk, f, DOC_ENTITY_FALLBACK_SCORE, vector_score=None)
        for chunk, f in rows
    }
    graph_items = [by_id[cid] for cid in neighbor_ids if cid in by_id]
    graph_items = [
        h for h in graph_items
        if h.get("chunk_id") is not None and int(h["chunk_id"]) not in existing_chunk_ids
    ]
    if not graph_items:
        meta["doc_entity_expanded"] = True
        return primary_items, meta

    for hit in graph_items:
        hit["score"] = round(float(hit["score"]) * DOC_ENTITY_SCORE_FACTOR, 4)
        hit.update(provenance_for_doc_entity_hit())

    combined = list(primary_items) + graph_items
    combined.sort(key=lambda x: float(x["score"]), reverse=True)
    if group_by_file:
        merged = _merge_hits_by_file(combined)[:top_k]
    else:
        merged = combined[:top_k]

    meta["doc_entity_expanded"] = True
    meta["doc_entity_added_hits"] = len(graph_items)
    return merged, meta
