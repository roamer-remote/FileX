# Copyright (c) 2026 徐泽宇
"""Wiki 互链边类型：直连、主题引用、共引。

Authors:
    徐泽宇

Copyright:
    © 2026 徐泽宇
"""

from __future__ import annotations

from itertools import combinations
from typing import Any

from sqlalchemy.orm import Session

from models.file import File as FileModel
from models.file_wiki_link import FileWikiLink
from services.wiki_page_filters import WIKI_PAGE_KINDS
from utils.wiki_slug import normalize_wiki_slug

EDGE_FILE_DIRECT = "file_direct"
EDGE_WIKI_TOPIC = "wiki_topic"
EDGE_WIKI_COREF = "wiki_coref"
EDGE_TYPES = frozenset({EDGE_FILE_DIRECT, EDGE_WIKI_TOPIC, EDGE_WIKI_COREF})

MAX_SOURCES_PER_SLUG = 10


def collect_wiki_slug_sources(
    db: Session,
    workspace_id: int,
    allowed: set[int],
    *,
    source_files_only: bool = True,
) -> dict[str, set[int]]:
    """slug -> source file ids (page_kind=source when source_files_only, link_kind=wiki_slug). Includes broken slug links."""
    filters = [
        FileModel.workspace_id == workspace_id,
        FileWikiLink.link_kind == "wiki_slug",
        FileWikiLink.target_wiki_slug.isnot(None),
        FileWikiLink.source_file_id.in_(allowed),
    ]
    if source_files_only:
        filters.insert(1, FileModel.page_kind == "source")
    rows = (
        db.query(FileWikiLink.source_file_id, FileWikiLink.target_wiki_slug)
        .join(FileModel, FileModel.id == FileWikiLink.source_file_id)
        .filter(*filters)
        .all()
    )
    slug_map: dict[str, set[int]] = {}
    for sid, slug in rows:
        if not slug:
            continue
        slug_map.setdefault(slug, set()).add(int(sid))
    return slug_map


def merged_wiki_slug_source_map(
    db: Session,
    workspace_id: int,
    allowed: set[int],
    *,
    source_files_only: bool = True,
) -> dict[str, set[int]]:
    from utils.wiki_slug import normalize_wiki_slug

    slug_map = collect_wiki_slug_sources(db, workspace_id, allowed, source_files_only=source_files_only)
    merged: dict[str, set[int]] = {}
    for slug, sources in slug_map.items():
        key = normalize_wiki_slug(slug) or slug
        if not key:
            continue
        merged.setdefault(key, set()).update(sources)
    return merged


def wiki_slug_source_counts(
    db: Session,
    workspace_id: int,
    allowed: set[int],
    *,
    source_files_only: bool = True,
) -> dict[str, int]:
    """Normalized wiki slug -> distinct source file count ([[wiki:slug]] in notes)."""
    merged = merged_wiki_slug_source_map(db, workspace_id, allowed, source_files_only=source_files_only)
    return {k: len(v) for k, v in merged.items()}


def list_wiki_slug_linked_sources(
    db: Session,
    workspace_id: int,
    allowed: set[int],
    wiki_slug: str,
    *,
    source_files_only: bool = True,
) -> list[dict[str, Any]]:
    from utils.wiki_slug import normalize_wiki_slug

    key = normalize_wiki_slug(wiki_slug)
    if not key:
        return []
    source_ids = merged_wiki_slug_source_map(db, workspace_id, allowed, source_files_only=source_files_only).get(key, set())
    if not source_ids:
        return []
    rows = (
        db.query(FileModel.id, FileModel.original_name)
        .filter(FileModel.id.in_(source_ids))
        .order_by(FileModel.original_name.asc(), FileModel.id.asc())
        .all()
    )
    return [
        {"file_id": int(rid), "source_name": name or f"file-{rid}"}
        for rid, name in rows
    ]


def _top_source_ids_by_updated_at(
    db: Session,
    source_ids: set[int],
    limit: int,
) -> list[int]:
    if len(source_ids) <= limit:
        return sorted(source_ids)
    rows = (
        db.query(FileModel.id)
        .filter(FileModel.id.in_(source_ids))
        .order_by(FileModel.updated_at.desc(), FileModel.id.desc())
        .limit(limit)
        .all()
    )
    return [int(r[0]) for r in rows]


def build_coref_edges(
    db: Session,
    slug_map: dict[str, set[int]],
    allowed: set[int],
    *,
    scope_ids: set[int] | None = None,
    max_sources_per_slug: int = MAX_SOURCES_PER_SLUG,
) -> list[dict[str, Any]]:
    edges: list[dict[str, Any]] = []
    seen: set[tuple[int, int, str]] = set()
    for slug, sources in slug_map.items():
        if len(sources) < 2:
            continue
        picked = set(_top_source_ids_by_updated_at(db, sources, max_sources_per_slug))
        if scope_ids is not None:
            picked = {sid for sid in picked if sid in scope_ids}
        if len(picked) < 2:
            continue
        for a, b in combinations(sorted(picked), 2):
            if a not in allowed or b not in allowed:
                continue
            key = (a, b, slug)
            if key in seen:
                continue
            seen.add(key)
            edges.append(
                {
                    "source": a,
                    "target": b,
                    "value": 1,
                    "edge_type": EDGE_WIKI_COREF,
                    "wiki_slug": slug,
                }
            )
    return edges


def build_direct_and_topic_edges(
    link_rows: list[FileWikiLink],
    allowed: set[int],
    target_page_kind: dict[int, str | None],
    *,
    scope_ids: set[int] | None = None,
    wiki_slug_targets: dict[str, int] | None = None,
) -> list[dict[str, Any]]:
    edges: list[dict[str, Any]] = []
    seen_direct: set[tuple[int, int]] = set()
    seen_topic: set[tuple[int, int]] = set()
    wiki_slug_targets = wiki_slug_targets or {}

    for link in link_rows:
        sid = link.source_file_id
        if sid not in allowed:
            continue
        if scope_ids is not None and sid not in scope_ids:
            continue

        tid = link.target_file_id
        resolved_slug_target = False
        if link.link_kind == "wiki_slug" and tid is None:
            slug_key = normalize_wiki_slug(link.target_wiki_slug or "")
            if slug_key:
                tid = wiki_slug_targets.get(slug_key)
                resolved_slug_target = tid is not None

        if link.broken_reason is not None and not resolved_slug_target:
            continue
        if tid is None or tid not in allowed:
            continue

        if link.link_kind in ("file_id", "okf_path"):
            if scope_ids is not None and tid not in scope_ids:
                pk = target_page_kind.get(tid)
                if pk not in WIKI_PAGE_KINDS:
                    continue
            key = (sid, tid)
            if key in seen_direct:
                continue
            seen_direct.add(key)
            edges.append(
                {
                    "source": sid,
                    "target": tid,
                    "value": 1,
                    "edge_type": EDGE_FILE_DIRECT,
                    "wiki_slug": None,
                }
            )
        elif link.link_kind == "wiki_slug":
            pk = target_page_kind.get(tid)
            if pk not in WIKI_PAGE_KINDS:
                continue
            if scope_ids is not None and tid not in scope_ids:
                pass
            key = (sid, tid)
            if key in seen_topic:
                continue
            seen_topic.add(key)
            edges.append(
                {
                    "source": sid,
                    "target": tid,
                    "value": 1,
                    "edge_type": EDGE_WIKI_TOPIC,
                    "wiki_slug": link.target_wiki_slug,
                }
            )
    return edges


def get_coref_peers_for_file(
    db: Session,
    file_id: int,
    workspace_id: int,
    allowed: set[int],
) -> list[dict[str, Any]]:
    """Peers sharing at least one wiki slug with file_id (source files only)."""
    slug_map = collect_wiki_slug_sources(db, workspace_id, allowed)
    my_slugs: set[str] = set()
    for slug, sources in slug_map.items():
        if file_id in sources:
            my_slugs.add(slug)
    if not my_slugs:
        return []

    peer_slugs: dict[int, set[str]] = {}
    for slug in my_slugs:
        for sid in slug_map.get(slug, set()):
            if sid == file_id or sid not in allowed:
                continue
            peer_slugs.setdefault(sid, set()).add(slug)

    if not peer_slugs:
        return []

    names = {
        int(r.id): r.original_name
        for r in db.query(FileModel).filter(FileModel.id.in_(peer_slugs.keys())).all()
    }
    return [
        {
            "file_id": pid,
            "source_name": names.get(pid) or f"file-{pid}",
            "shared_wiki_slugs": sorted(peer_slugs[pid]),
        }
        for pid in sorted(peer_slugs.keys())
    ]
