# Copyright (c) 2026 徐泽宇
"""016 P1：workspace 内 Wiki 互链最短路径（无权 BFS）。

Authors:
    徐泽宇

Copyright:
    © 2026 徐泽宇
"""

from __future__ import annotations

from collections import deque
from typing import Any

from sqlalchemy.orm import Session

from models.file import File as FileModel
from models.file_wiki_link import FileWikiLink
from models.user import User
from services.acl_service import accessible_file_ids
from services.wiki_link_edges_service import (
    EDGE_FILE_DIRECT,
    EDGE_TYPES,
    EDGE_WIKI_COREF,
    EDGE_WIKI_TOPIC,
    build_coref_edges,
    build_direct_and_topic_edges,
    collect_wiki_slug_sources,
)
from services.wiki_page_service import get_wiki_page_by_slug
from services.wiki_provenance_service import provenance_for_edge
from utils.wiki_slug import normalize_wiki_slug


class SlugNotFoundError(LookupError):
    """Slugnotfound错误异常类型。

        Authors:
            徐泽宇

        Copyright:
            © 2026 徐泽宇

        Since:
            2026-06-09
    """
    pass


class SlugWorkspaceMismatchError(ValueError):
    """Slug知识空间mismatch错误异常类型。

        Authors:
            徐泽宇

        Copyright:
            © 2026 徐泽宇

        Since:
            2026-06-09
    """
    pass


class EndpointNotFoundError(LookupError):
    """端点notfound错误异常类型。

        Authors:
            徐泽宇

        Copyright:
            © 2026 徐泽宇

        Since:
            2026-06-09
    """
    pass


def _build_workspace_edges(
    db: Session,
    user: User,
    workspace_id: int,
    *,
    edge_types: frozenset[str],
) -> list[dict[str, Any]]:
    allowed = accessible_file_ids(db, user, workspace_id)
    if not allowed:
        return []

    link_rows = (
        db.query(FileWikiLink)
        .join(FileModel, FileModel.id == FileWikiLink.source_file_id)
        .filter(
            FileModel.workspace_id == workspace_id,
            FileWikiLink.broken_reason.is_(None),
            FileWikiLink.target_file_id.isnot(None),
        )
        .all()
    )
    target_ids = {link.target_file_id for link in link_rows if link.target_file_id}
    target_page_kind: dict[int, str | None] = {}
    if target_ids:
        for row in (
            db.query(FileModel.id, FileModel.page_kind)
            .filter(FileModel.id.in_(target_ids))
            .all()
        ):
            target_page_kind[int(row.id)] = row.page_kind

    slug_map = collect_wiki_slug_sources(db, workspace_id, allowed)
    edges: list[dict[str, Any]] = []
    edges.extend(
        build_direct_and_topic_edges(link_rows, allowed, target_page_kind)
    )
    edges.extend(
        build_coref_edges(db, slug_map, allowed)
    )
    return [e for e in edges if str(e.get("edge_type")) in edge_types]


def _adjacency(
    edges: list[dict[str, Any]],
) -> dict[int, list[tuple[int, dict[str, Any]]]]:
    adj: dict[int, list[tuple[int, dict[str, Any]]]] = {}
    for e in edges:
        s, t = int(e["source"]), int(e["target"])
        adj.setdefault(s, []).append((t, e))
        adj.setdefault(t, []).append((s, e))
    return adj


def _slug_page_kinds(
    db: Session,
    workspace_id: int,
    slugs: set[str],
) -> dict[str, str]:
    if not slugs:
        return {}
    rows = (
        db.query(FileModel.wiki_slug, FileModel.page_kind)
        .filter(
            FileModel.workspace_id == workspace_id,
            FileModel.wiki_slug.in_(list(slugs)),
            FileModel.page_kind.isnot(None),
        )
        .all()
    )
    out: dict[str, str] = {}
    for slug, pk in rows:
        if slug:
            out[str(slug)] = pk or "concept"
    return out


def _file_node(file_id: int, title: str) -> dict[str, Any]:
    return {"node_type": "file", "file_id": file_id, "title": title or f"file-{file_id}"}


def _edge_node(edge: dict[str, Any]) -> dict[str, Any]:
    et = str(edge.get("edge_type") or EDGE_FILE_DIRECT)
    payload = provenance_for_edge(et)
    payload["edge_type"] = et
    slug = edge.get("wiki_slug")
    if slug:
        payload["via_slug"] = slug
    return {"edge": payload}


def _hub_node(slug: str, page_kind: str) -> dict[str, Any]:
    return {"node_type": "wiki_hub", "slug": slug, "page_kind": page_kind}


def _format_path(
    file_chain: list[int],
    edge_chain: list[dict[str, Any]],
    titles: dict[int, str],
    slug_page_kinds: dict[str, str],
) -> list[dict[str, Any]]:
    path: list[dict[str, Any]] = []
    for i, fid in enumerate(file_chain):
        path.append(_file_node(fid, titles.get(fid, "")))
        if i >= len(edge_chain):
            break
        edge = edge_chain[i]
        path.append(_edge_node(edge))
        et = str(edge.get("edge_type") or "")
        slug = edge.get("wiki_slug")
        if et in (EDGE_WIKI_COREF, EDGE_WIKI_TOPIC) and slug:
            path.append(_hub_node(str(slug), slug_page_kinds.get(str(slug), "concept")))
    return path


def resolve_path_endpoint_file(
    db: Session,
    user: User,
    workspace_id: int,
    *,
    file_id: int | None = None,
    slug: str | None = None,
) -> FileModel:
    if file_id is not None:
        f = db.query(FileModel).filter(FileModel.id == file_id).first()
        if not f or int(f.workspace_id or 0) != workspace_id:
            raise EndpointNotFoundError("file")
        allowed = accessible_file_ids(db, user, workspace_id)
        if not user.is_admin and f.id not in allowed:
            raise EndpointNotFoundError("file")
        return f

    if slug:
        norm = normalize_wiki_slug(slug)
        if not norm:
            raise SlugNotFoundError(slug)
        other_ws = (
            db.query(FileModel)
            .filter(
                FileModel.wiki_slug == norm,
                FileModel.page_kind.in_(("entity", "concept", "synthesis")),
            )
            .first()
        )
        if other_ws and int(other_ws.workspace_id or 0) != workspace_id:
            raise SlugWorkspaceMismatchError(norm)
        f = get_wiki_page_by_slug(db, user, workspace_id, norm)
        if not f:
            raise SlugNotFoundError(norm)
        return f

    raise ValueError("file_id or slug required")


def find_wiki_path(
    db: Session,
    user: User,
    workspace_id: int,
    *,
    from_file_id: int | None = None,
    from_slug: str | None = None,
    to_file_id: int | None = None,
    to_slug: str | None = None,
    max_hops: int = 4,
    edge_types: list[str] | None = None,
) -> dict[str, Any]:
    max_hops = min(max(1, int(max_hops)), 6)
    allowed_types = frozenset(edge_types) if edge_types else EDGE_TYPES
    allowed_types = allowed_types & EDGE_TYPES
    if not allowed_types:
        allowed_types = EDGE_TYPES

    start = resolve_path_endpoint_file(
        db, user, workspace_id, file_id=from_file_id, slug=from_slug
    )
    end = resolve_path_endpoint_file(
        db, user, workspace_id, file_id=to_file_id, slug=to_slug
    )

    if start.id == end.id:
        return {
            "found": True,
            "hops": 0,
            "truncated": False,
            "path": [_file_node(start.id, start.original_name or "")],
        }

    edges = _build_workspace_edges(db, user, workspace_id, edge_types=allowed_types)
    adj = _adjacency(edges)

    start_id, end_id = int(start.id), int(end.id)
    queue: deque[int] = deque([start_id])
    dist = {start_id: 0}
    parent: dict[int, tuple[int | None, dict[str, Any] | None]] = {start_id: (None, None)}

    found = False
    while queue:
        node = queue.popleft()
        d = dist[node]
        if d >= max_hops:
            continue
        for nbr, edge in adj.get(node, []):
            if nbr in dist:
                continue
            dist[nbr] = d + 1
            parent[nbr] = (node, edge)
            if nbr == end_id:
                found = True
                queue.clear()
                break
            queue.append(nbr)

    if not found:
        return {"found": False, "hops": 0, "truncated": False, "path": []}

    hops = dist[end_id]
    file_chain: list[int] = []
    edge_chain: list[dict[str, Any]] = []
    cur = end_id
    while cur != start_id:
        prev, edge = parent[cur]
        if prev is None or edge is None:
            break
        file_chain.append(cur)
        edge_chain.append(edge)
        cur = prev
    file_chain.append(start_id)
    file_chain.reverse()
    edge_chain.reverse()

    ids = set(file_chain)
    titles = {
        int(r.id): r.original_name or ""
        for r in db.query(FileModel).filter(FileModel.id.in_(ids)).all()
    }
    slugs = {str(e["wiki_slug"]) for e in edge_chain if e.get("wiki_slug")}
    slug_kinds = _slug_page_kinds(db, workspace_id, slugs)

    return {
        "found": True,
        "hops": hops,
        "truncated": False,
        "path": _format_path(file_chain, edge_chain, titles, slug_kinds),
    }
