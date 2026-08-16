# Copyright (c) 2026 徐泽宇
"""018: Wiki 图扩展 — RAG chunk 二次扩召回。

Authors:
    徐泽宇

Copyright:
    © 2026 徐泽宇
"""

from __future__ import annotations

from typing import Any

from sqlalchemy.orm import Session

from models.user import User
from services.kb_search_service import TAG_UNION_SCORE, _first_chunk_hit_for_file, _merge_hits_by_file, search_kb
from services.md_wiki_link_service import get_wiki_links_for_file
from services.wiki_provenance_service import provenance_for_wiki_graph_hit

WIKI_GRAPH_MAX_SEEDS = 3
WIKI_GRAPH_MAX_NEIGHBORS = 8
WIKI_GRAPH_SCORE_FACTOR = 0.92
WIKI_GRAPH_FALLBACK_SCORE = TAG_UNION_SCORE


def collect_wiki_graph_neighbor_ids(
    db: Session,
    actor: User,
    seed_file_ids: list[int],
    *,
    include_coref: bool = False,
    max_neighbors: int = WIKI_GRAPH_MAX_NEIGHBORS,
    exclude_file_ids: set[int] | None = None,
) -> list[int]:
    """从种子 wiki 出链（及可选 coref）收集邻居 file_id，保序去重。"""
    exclude = set(exclude_file_ids or ())
    seen: set[int] = set(exclude)
    neighbors: list[int] = []

    def _add(fid: int | None) -> bool:
        if fid is None or fid in seen:
            return False
        seen.add(fid)
        neighbors.append(fid)
        return len(neighbors) >= max_neighbors

    for seed_id in seed_file_ids[:WIKI_GRAPH_MAX_SEEDS]:
        payload = get_wiki_links_for_file(db, actor, seed_id)
        for out in payload.get("outlinks") or []:
            if out.get("broken"):
                continue
            if _add(out.get("target_file_id")):
                return neighbors
        if include_coref:
            for peer in payload.get("coref_files") or []:
                if _add(peer.get("file_id")):
                    return neighbors
    return neighbors


def expand_search_items_with_wiki_graph(
    db: Session,
    actor: User,
    query: str,
    primary_items: list[dict],
    *,
    user_id: int,
    search_kwargs: dict[str, Any],
    include_coref: bool = False,
    top_k: int,
    group_by_file: bool,
) -> tuple[list[dict], dict[str, Any]]:
    """对 wiki 邻居二次 search_kb，合并进 primary items。"""
    meta: dict[str, Any] = {
        "wiki_graph_expanded": False,
        "wiki_graph_neighbor_ids": [],
        "wiki_graph_added_hits": 0,
    }
    if not primary_items:
        return primary_items, meta

    seed_ids: list[int] = []
    seen_seed: set[int] = set()
    for row in primary_items:
        fid = int(row["file_id"])
        if fid in seen_seed:
            continue
        seen_seed.add(fid)
        seed_ids.append(fid)
        if len(seed_ids) >= WIKI_GRAPH_MAX_SEEDS:
            break

    primary_fids = {int(x["file_id"]) for x in primary_items}
    neighbor_ids = collect_wiki_graph_neighbor_ids(
        db,
        actor,
        seed_ids,
        include_coref=include_coref,
        exclude_file_ids=primary_fids,
    )
    meta["wiki_graph_neighbor_ids"] = neighbor_ids
    if not neighbor_ids:
        return primary_items, meta

    graph_top_k = min(len(neighbor_ids), top_k) if group_by_file else top_k
    graph_kwargs = {**search_kwargs, "hybrid": False}
    graph_items, _, _, _ = search_kb(
        db,
        user_id,
        query,
        file_ids=neighbor_ids,
        top_k=graph_top_k,
        group_by_file=group_by_file,
        **graph_kwargs,
    )
    if not graph_items:
        for nid in neighbor_ids:
            fallback = _first_chunk_hit_for_file(db, nid, WIKI_GRAPH_FALLBACK_SCORE)
            if fallback is not None:
                graph_items.append(fallback)
    if not graph_items:
        meta["wiki_graph_expanded"] = True
        return primary_items, meta

    for hit in graph_items:
        hit["score"] = round(float(hit["score"]) * WIKI_GRAPH_SCORE_FACTOR, 4)
        hit.update(provenance_for_wiki_graph_hit())

    combined = list(primary_items) + graph_items
    combined.sort(key=lambda x: float(x["score"]), reverse=True)
    graph_file_ids = {int(hit["file_id"]) for hit in graph_items}
    if group_by_file:
        merged = _merge_hits_by_file(combined)[:top_k]
    else:
        merged = combined[:top_k]
    for hit in merged:
        if int(hit["file_id"]) in graph_file_ids:
            hit.update(provenance_for_wiki_graph_hit())

    meta["wiki_graph_expanded"] = True
    meta["wiki_graph_added_hits"] = len(graph_items)
    return merged, meta
