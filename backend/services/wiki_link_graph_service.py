# Copyright (c) 2026 徐泽宇
"""Workspace 内 Wiki 互链关系图。

Authors:
    徐泽宇

Copyright:
    © 2026 徐泽宇
"""

from __future__ import annotations

from typing import Any

from sqlalchemy import and_, or_
from sqlalchemy.orm import Session

from models.file import File as FileModel
from models.file_wiki_link import FileWikiLink
from models.user import User
from services.acl_service import accessible_file_ids
from services.wiki_link_edges_service import (
    build_coref_edges,
    build_direct_and_topic_edges,
    collect_wiki_slug_sources,
)
from services.workspace_access_service import get_folder_in_workspace
from utils.wiki_slug import normalize_wiki_slug

LINK_GRAPH_FILE_LIMIT = 200


def _scoped_file_ids_in_folder(
    db: Session,
    workspace_id: int,
    allowed: set[int],
    folder_id: int,
) -> set[int]:
    """与 GET /api/files 一致：folder_id=0 为未分类，否则为目录内文件（不含子目录）。"""
    if folder_id != 0:
        if get_folder_in_workspace(db, folder_id, workspace_id) is None:
            return set()
    q = db.query(FileModel.id).filter(
        FileModel.workspace_id == workspace_id,
        FileModel.id.in_(allowed),
    )
    if folder_id == 0:
        q = q.filter(FileModel.folder_id.is_(None))
    else:
        q = q.filter(FileModel.folder_id == folder_id)
    return {int(r[0]) for r in q.all()}


def build_wiki_link_graph(
    db: Session,
    user: User,
    workspace_id: int,
    *,
    folder_id: int | None = None,
    file_limit: int = LINK_GRAPH_FILE_LIMIT,
    include_derived: bool = False,
) -> dict[str, Any]:
    allowed = accessible_file_ids(db, user, workspace_id)
    if not allowed:
        return {
            "nodes": [],
            "links": [],
            "truncated": False,
            "total_files_with_links": 0,
        }

    scope_ids: set[int] | None = None
    if folder_id is not None:
        scope_ids = _scoped_file_ids_in_folder(db, workspace_id, allowed, folder_id)
        if not scope_ids:
            return {
                "nodes": [],
                "links": [],
                "truncated": False,
                "total_files_with_links": 0,
            }

    link_rows = (
        db.query(FileWikiLink)
        .join(FileModel, FileModel.id == FileWikiLink.source_file_id)
        .filter(
            FileModel.workspace_id == workspace_id,
            or_(
                and_(
                    FileWikiLink.broken_reason.is_(None),
                    FileWikiLink.target_file_id.isnot(None),
                ),
                and_(
                    FileWikiLink.link_kind == "wiki_slug",
                    FileWikiLink.target_wiki_slug.isnot(None),
                    or_(
                        FileWikiLink.broken_reason.is_(None),
                        FileWikiLink.broken_reason == "deleted",
                    ),
                ),
            ),
        )
        .all()
    )

    target_ids = {link.target_file_id for link in link_rows if link.target_file_id}
    wiki_slug_targets: dict[str, int] = {}
    target_wiki_slugs = {
        normalize_wiki_slug(link.target_wiki_slug or "")
        for link in link_rows
        if link.link_kind == "wiki_slug" and link.target_wiki_slug
    }
    target_wiki_slugs.discard("")
    if target_wiki_slugs:
        for row in (
            db.query(FileModel.id, FileModel.wiki_slug)
            .filter(
                FileModel.workspace_id == workspace_id,
                FileModel.wiki_slug.in_(target_wiki_slugs),
                FileModel.page_kind.in_(("entity", "concept", "synthesis")),
            )
            .all()
        ):
            slug_key = normalize_wiki_slug(row.wiki_slug or "")
            if slug_key and slug_key not in wiki_slug_targets:
                wiki_slug_targets[slug_key] = int(row.id)
                target_ids.add(int(row.id))

    target_page_kind: dict[int, str | None] = {}
    if target_ids:
        for row in (
            db.query(FileModel.id, FileModel.page_kind)
            .filter(FileModel.id.in_(target_ids))
            .all()
        ):
            target_page_kind[int(row.id)] = row.page_kind

    slug_map = collect_wiki_slug_sources(db, workspace_id, allowed)
    edges = build_direct_and_topic_edges(
        link_rows,
        allowed,
        target_page_kind,
        scope_ids=scope_ids,
        wiki_slug_targets=wiki_slug_targets,
    )
    edges.extend(
        build_coref_edges(
            db,
            slug_map,
            allowed,
            scope_ids=scope_ids,
        )
    )

    if include_derived:
        derived_rows = (
            db.query(FileModel.id)
            .filter(
                FileModel.workspace_id == workspace_id,
                FileModel.id.in_(allowed),
                FileModel.page_kind == "source",
                FileModel.has_md.is_(True),
                FileModel.extract_status != "not_needed",
            )
            .all()
        )
        for row in derived_rows:
            fid = int(row.id)
            edges.append(
                {
                    "source": fid,
                    "target": fid,
                    "value": 1,
                    "edge_type": "derived_from",
                    "wiki_slug": None,
                }
            )

    node_ids: set[int] = set()
    for e in edges:
        node_ids.add(int(e["source"]))
        node_ids.add(int(e["target"]))

    if not node_ids:
        return {
            "nodes": [],
            "links": [],
            "truncated": False,
            "total_files_with_links": 0,
        }

    files = (
        db.query(FileModel)
        .filter(FileModel.id.in_(node_ids))
        .order_by(FileModel.updated_at.desc(), FileModel.id.desc())
        .all()
    )
    total = len(files)
    truncated = total > file_limit
    if truncated:
        files = files[:file_limit]
        keep = {f.id for f in files}
        edges = [e for e in edges if e["source"] in keep and e["target"] in keep]
        node_ids = keep

    nodes = [
        {
            "id": f.id,
            "name": f.original_name or f"file-{f.id}",
            "value": f.wiki_outlink_count or 0,
            "page_kind": f.page_kind or "source",
            "wiki_slug": f.wiki_slug,
        }
        for f in files
        if f.id in node_ids
    ]
    from services.wiki_provenance_service import enrich_link_graph_payload

    return enrich_link_graph_payload(
        {
            "nodes": nodes,
            "links": edges,
            "truncated": truncated,
            "total_files_with_links": total,
        }
    )
