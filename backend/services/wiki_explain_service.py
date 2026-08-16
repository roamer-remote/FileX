# Copyright (c) 2026 徐泽宇
"""016 P1：单点 Wiki 邻域结构化解释（无 Markdown）。

Authors:
    徐泽宇

Copyright:
    © 2026 徐泽宇
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from sqlalchemy.orm import Session

from models.file import File as FileModel
from models.user import User
from services.md_wiki_link_service import get_wiki_links_for_file
from services.wiki_path_service import (
    EndpointNotFoundError,
    SlugNotFoundError,
    SlugWorkspaceMismatchError,
    resolve_path_endpoint_file,
)


def _center_node(f: FileModel) -> dict[str, Any]:
    return {
        "file_id": f.id,
        "title": f.original_name or f"file-{f.id}",
        "page_kind": f.page_kind or "source",
        "wiki_slug": f.wiki_slug,
        "has_md": bool(f.has_md),
    }


def _topic_hubs_from_outlinks(outlinks: list[dict[str, Any]]) -> list[dict[str, Any]]:
    hubs: list[dict[str, Any]] = []
    seen: set[str] = set()
    for o in outlinks:
        if o.get("link_kind") != "wiki_slug":
            continue
        slug = o.get("target_wiki_slug")
        if not slug or slug in seen:
            continue
        seen.add(slug)
        hubs.append(
            {
                "slug": slug,
                "target_file_id": o.get("target_file_id"),
                "target_name": o.get("target_name"),
                "broken": bool(o.get("broken")),
            }
        )
    return hubs


def explain_wiki_file(
    db: Session,
    user: User,
    workspace_id: int,
    *,
    file_id: int | None = None,
    slug: str | None = None,
    depth: int = 1,
) -> dict[str, Any]:
    depth = min(max(1, int(depth)), 2)
    center_file = resolve_path_endpoint_file(
        db, user, workspace_id, file_id=file_id, slug=slug
    )

    links = get_wiki_links_for_file(db, user, center_file.id, dedupe=True)
    outlinks = links.get("outlinks") or []
    inlinks = links.get("backlinks") or []
    coref_peers = links.get("coref_files") or []
    topic_hubs = _topic_hubs_from_outlinks(outlinks)

    edge_count = len(outlinks) + len(inlinks) + len(coref_peers)
    neighbor_nodes: list[dict[str, Any]] = []

    if depth >= 2:
        seen_neighbors: set[int] = {center_file.id}
        for o in outlinks:
            tid = o.get("target_file_id")
            if not tid or tid in seen_neighbors or o.get("broken"):
                continue
            seen_neighbors.add(int(tid))
            nlinks = get_wiki_links_for_file(db, user, int(tid), dedupe=True)
            neighbor_nodes.append(
                {
                    "file_id": int(tid),
                    "title": o.get("target_name") or f"file-{tid}",
                    "outlink_count": nlinks.get("outlink_count", 0),
                    "backlink_count": nlinks.get("backlink_count", 0),
                }
            )
            edge_count += int(nlinks.get("outlink_count") or 0)
            edge_count += int(nlinks.get("backlink_count") or 0)

    return {
        "center": _center_node(center_file),
        "outlinks": outlinks,
        "inlinks": inlinks,
        "coref_peers": coref_peers,
        "topic_hubs": topic_hubs,
        "neighbor_nodes": neighbor_nodes,
        "edge_count": edge_count,
        "depth": depth,
        "fetched_at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
    }
