# Copyright (c) 2026 徐泽宇
"""Wiki 互链 BFS 展开：种子资料笔记及其出链/共引邻居 MD。

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
from models.user import User
from services.acl_service import accessible_file_ids
from services.okf_note_service import read_okf_body_for_file
from services.md_wiki_link_service import _ensure_file_workspace, get_wiki_links_for_file
from services.wiki_provenance_service import provenance_for_wiki_context_role
from utils.agent_freshness import utc_now_iso_z


def expand_wiki_context_batch(
    db: Session,
    actor: User,
    seed_file_ids: list[int],
    *,
    depth: int = 1,
    max_files: int = 8,
    include_coref: bool = False,
) -> dict[str, Any]:
    """多种子 wiki-context：逐种子 BFS 后按 file_id 去重，全局 max_files 截断。"""
    seed_file_ids = list(dict.fromkeys(seed_file_ids))
    merged_nodes: list[dict[str, Any]] = []
    merged_skipped: list[dict[str, Any]] = []
    seen_node_ids: set[int] = set()
    truncated = False

    for seed_id in seed_file_ids:
        partial = expand_wiki_context(
            db,
            actor,
            seed_id,
            depth=depth,
            max_files=max_files,
            include_coref=include_coref,
        )
        merged_skipped.extend(partial.get("skipped") or [])
        if partial.get("truncated"):
            truncated = True
        for node in partial.get("nodes") or []:
            fid = int(node["file_id"])
            if fid in seen_node_ids:
                continue
            seen_node_ids.add(fid)
            merged_nodes.append(node)
            if len(merged_nodes) >= max_files:
                truncated = True
                break
        if len(merged_nodes) >= max_files:
            break

    return {
        "seed_file_ids": seed_file_ids,
        "depth": depth,
        "max_files": max_files,
        "truncated": truncated,
        "skipped": merged_skipped,
        "nodes": merged_nodes,
        "fetched_at": utc_now_iso_z(),
    }


def _actor_can_read_file(db: Session, actor: User, file_row: FileModel) -> bool:
    if actor.is_admin:
        return True
    ws_id = _ensure_file_workspace(db, file_row)
    return file_row.id in accessible_file_ids(db, actor, ws_id)


def expand_wiki_context(
    db: Session,
    actor: User,
    seed_file_id: int,
    *,
    depth: int = 1,
    max_files: int = 8,
    include_coref: bool = False,
) -> dict[str, Any]:
    """BFS 展开 Wiki 邻居；不 commit。种子 ACL 由路由 `require_workspace_file` 校验。"""
    visited: set[int] = set()
    nodes: list[dict[str, Any]] = []
    skipped: list[dict[str, Any]] = []
    truncated = False

    queue: deque[tuple[int, int, dict[str, Any] | None, str]] = deque()
    queue.append((seed_file_id, depth, None, "seed"))

    while queue:
        if len(nodes) >= max_files:
            if queue:
                truncated = True
            break

        fid, d_rem, link_from, role_hint = queue.popleft()
        if fid in visited:
            continue

        file_row = db.query(FileModel).filter(FileModel.id == fid).first()
        if not file_row:
            continue

        if not _actor_can_read_file(db, actor, file_row):
            continue

        links_payload = get_wiki_links_for_file(db, actor, fid)

        md_text = read_okf_body_for_file(file_row)
        if fid == seed_file_id:
            role = "seed"
        elif role_hint == "coref":
            role = "coref"
        else:
            role = "outlink"

        visited.add(fid)
        node: dict[str, Any] = {
            "file_id": file_row.id,
            "original_name": file_row.original_name,
            "page_kind": file_row.page_kind or "source",
            "wiki_slug": file_row.wiki_slug,
            "role": role,
            "link_from": link_from,
            "markdown": md_text or "",
            "has_md": bool(md_text),
        }
        node.update(provenance_for_wiki_context_role(role))
        nodes.append(node)

        if d_rem <= 0 or len(nodes) >= max_files:
            continue

        for out in links_payload.get("outlinks") or []:
            if out.get("broken"):
                skipped.append(
                    {
                        "reason": out.get("broken_reason") or "broken",
                        "link_kind": out.get("link_kind"),
                        "wiki_slug": out.get("target_wiki_slug"),
                        "target_file_id": out.get("target_file_id"),
                    }
                )
                continue
            target_id = out.get("target_file_id")
            if not target_id or target_id in visited:
                continue
            link_from_meta: dict[str, Any] = {
                "file_id": fid,
                "link_kind": out.get("link_kind") or "file_id",
            }
            if out.get("target_wiki_slug"):
                link_from_meta["wiki_slug"] = out["target_wiki_slug"]
            queue.append((target_id, d_rem - 1, link_from_meta, "outlink"))

        if include_coref:
            for peer in links_payload.get("coref_files") or []:
                peer_id = peer.get("file_id")
                if not peer_id or peer_id in visited:
                    continue
                slug = (peer.get("shared_wiki_slugs") or [None])[0]
                link_from_meta = {
                    "file_id": fid,
                    "link_kind": "wiki_slug",
                    "wiki_slug": slug,
                }
                queue.append((peer_id, d_rem, link_from_meta, "coref"))

    return {
        "seed_file_id": seed_file_id,
        "depth": depth,
        "max_files": max_files,
        "truncated": truncated,
        "skipped": skipped,
        "nodes": nodes,
        "fetched_at": utc_now_iso_z(),
    }
