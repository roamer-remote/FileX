# Copyright (c) 2026 徐泽宇
"""072: 标签共现扩召回 — RAG chunk 二次检索。

Authors:
    徐泽宇

Copyright:
    © 2026 徐泽宇
"""

from __future__ import annotations

from collections import Counter, defaultdict
from typing import Any

from sqlalchemy.orm import Session

from models.file import File as FileModel
from models.tag import Tag, file_tags
from models.user import User
from services.kb_search_service import (
    STATUS_READY,
    _file_ids_for_tags,
    _merge_hits_by_file,
    search_kb,
)
from services.system_setting_service import get_kb_search_tag_cooc_settings
from services.wiki_provenance_service import provenance_for_tag_cooc_expand_hit

TAG_COOC_MAX_SEEDS = 3
TAG_COOC_MAX_TAGS = 5
TAG_COOC_SCORE_FACTOR = 0.90
TAG_COOC_MAX_CANDIDATE_FILES = 128


def _apply_file_scope(
    query,
    *,
    workspace_id: int | None,
    allowed_file_ids: set[int] | None,
    readable_file_ids_query=None,
):
    if workspace_id is not None:
        query = query.filter(FileModel.workspace_id == workspace_id)
    if allowed_file_ids is not None:
        if not allowed_file_ids:
            return None
        query = query.filter(FileModel.id.in_(allowed_file_ids))
    elif readable_file_ids_query is not None:
        query = query.filter(FileModel.id.in_(readable_file_ids_query))
    return (
        query.filter(FileModel.index_status == STATUS_READY)
        .filter(FileModel.publish_status == "published")
    )


def _compute_tag_cooccurrence(
    db: Session,
    actor: User,
    seed_file_ids: list[int],
    *,
    min_edge: int,
    max_tags: int,
    workspace_id: int | None,
    cross_workspace: bool,
    allowed_file_ids: set[int] | None,
    readable_file_ids_query=None,
) -> list[str]:
    """种子文件标签的共现邻居标签（按共现文件数降序，上限 max_tags）。

    直接查询 file_tags；禁止调用 build_user_tag_graph（无 40 文件截断）。
    """
    _ = actor  # ACL 由 allowed_file_ids / readable 子查询保证
    _ = cross_workspace  # scope 由 workspace_id + ACL 参数表达
    seeds = list(dict.fromkeys(int(x) for x in seed_file_ids))[:TAG_COOC_MAX_SEEDS]
    if not seeds:
        return []

    seed_tag_rows = (
        db.query(Tag.name)
        .join(file_tags, Tag.id == file_tags.c.tag_id)
        .filter(file_tags.c.file_id.in_(seeds))
        .distinct()
        .all()
    )
    seed_tags = {r[0] for r in seed_tag_rows}
    if not seed_tags:
        return []

    candidate_q = (
        db.query(file_tags.c.file_id)
        .join(FileModel, FileModel.id == file_tags.c.file_id)
        .join(Tag, Tag.id == file_tags.c.tag_id)
        .filter(Tag.name.in_(seed_tags))
    )
    candidate_q = _apply_file_scope(
        candidate_q,
        workspace_id=workspace_id,
        allowed_file_ids=allowed_file_ids,
        readable_file_ids_query=readable_file_ids_query,
    )
    if candidate_q is None:
        return []
    candidate_ids = {int(r[0]) for r in candidate_q.distinct().all()}
    if not candidate_ids:
        return []

    tag_rows = (
        db.query(file_tags.c.file_id, Tag.name)
        .join(Tag, Tag.id == file_tags.c.tag_id)
        .filter(file_tags.c.file_id.in_(candidate_ids))
        .all()
    )
    by_file: dict[int, set[str]] = defaultdict(set)
    for fid, name in tag_rows:
        by_file[int(fid)].add(str(name))

    pair_counts: Counter[tuple[str, str]] = Counter()
    for tags in by_file.values():
        on_file_seed = tags & seed_tags
        for a in on_file_seed:
            for b in tags:
                if a == b:
                    continue
                pair_counts[(a, b)] += 1

    tag_best: dict[str, int] = {}
    for (a, b), cnt in pair_counts.items():
        if cnt >= min_edge:
            tag_best[b] = max(tag_best.get(b, 0), cnt)

    ranked = sorted(tag_best.keys(), key=lambda t: (-tag_best[t], t))
    return ranked[:max_tags]


def _collect_cooc_candidate_file_ids(
    db: Session,
    *,
    neighbor_tags: list[str],
    workspace_id: int | None,
    allowed_file_ids: set[int] | None,
    readable_file_ids_query=None,
    exclude_file_ids: set[int],
    source_files_only: bool = False,
) -> list[int]:
    if not neighbor_tags:
        return []
    fids = _file_ids_for_tags(
        db,
        workspace_id=workspace_id,
        allowed_file_ids=allowed_file_ids,
        readable_file_ids_query=readable_file_ids_query,
        tags=neighbor_tags,
        tag_mode="or",
        include_not_ready=False,
        include_drafts=False,
        source_files_only=source_files_only,
    )
    ordered = sorted(fids - exclude_file_ids)
    return ordered[:TAG_COOC_MAX_CANDIDATE_FILES]


def expand_search_items_with_tag_cooc(
    db: Session,
    actor: User,
    query: str,
    primary_items: list[dict],
    *,
    user_id: int,
    search_kwargs: dict[str, Any],
    workspace_id: int | None,
    cross_workspace: bool,
    allowed_file_ids: set[int] | None,
    readable_file_ids_query=None,
    top_k: int,
    group_by_file: bool,
    min_edge: int | None = None,
    max_cooc_tags: int = TAG_COOC_MAX_TAGS,
) -> tuple[list[dict], dict[str, Any]]:
    """对标签共现邻居文件二次 search_kb，合并进 primary items。"""
    settings = get_kb_search_tag_cooc_settings(db)
    edge = min_edge if min_edge is not None else settings.min_edge
    meta: dict[str, Any] = {
        "tag_cooc_expanded": False,
        "tag_cooc_neighbor_tags": [],
        "tag_cooc_added_hits": 0,
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
        if len(seed_ids) >= TAG_COOC_MAX_SEEDS:
            break

    neighbor_tags = _compute_tag_cooccurrence(
        db,
        actor,
        seed_ids,
        min_edge=edge,
        max_tags=max_cooc_tags,
        workspace_id=workspace_id,
        cross_workspace=cross_workspace,
        allowed_file_ids=allowed_file_ids,
        readable_file_ids_query=readable_file_ids_query,
    )
    meta["tag_cooc_neighbor_tags"] = neighbor_tags
    if not neighbor_tags:
        return primary_items, meta

    primary_fids = {int(x["file_id"]) for x in primary_items}
    source_files_only = bool(search_kwargs.get("source_files_only"))
    candidate_ids = _collect_cooc_candidate_file_ids(
        db,
        neighbor_tags=neighbor_tags,
        workspace_id=workspace_id,
        allowed_file_ids=allowed_file_ids,
        readable_file_ids_query=readable_file_ids_query,
        exclude_file_ids=primary_fids,
        source_files_only=source_files_only,
    )
    if not candidate_ids:
        return primary_items, meta

    cooc_top_k = min(len(candidate_ids), top_k) if group_by_file else top_k
    cooc_kwargs = {
        k: v
        for k, v in search_kwargs.items()
        if k not in ("tags", "tag_mode", "tag_combine")
    }
    cooc_items, _, _, _ = search_kb(
        db,
        user_id,
        query,
        workspace_id=workspace_id,
        allowed_file_ids=allowed_file_ids,
        readable_file_ids_query=readable_file_ids_query,
        file_ids=candidate_ids,
        top_k=cooc_top_k,
        group_by_file=group_by_file,
        **cooc_kwargs,
    )
    if not cooc_items:
        meta["tag_cooc_expanded"] = True
        meta["tag_cooc_added_hits"] = 0
        return primary_items, meta

    for hit in cooc_items:
        hit["score"] = round(float(hit["score"]) * TAG_COOC_SCORE_FACTOR, 4)
        hit.update(provenance_for_tag_cooc_expand_hit())

    combined = list(primary_items) + cooc_items
    combined.sort(key=lambda x: float(x["score"]), reverse=True)
    cooc_file_ids = {int(hit["file_id"]) for hit in cooc_items}
    if group_by_file:
        merged = _merge_hits_by_file(combined)[:top_k]
    else:
        merged = combined[:top_k]
    for hit in merged:
        if int(hit["file_id"]) in cooc_file_ids:
            hit.update(provenance_for_tag_cooc_expand_hit())

    meta["tag_cooc_expanded"] = True
    meta["tag_cooc_added_hits"] = len(cooc_items)
    return merged, meta
