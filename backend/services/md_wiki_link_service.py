# Copyright (c) 2026 徐泽宇
"""资料笔记 Wiki 互链：解析、存储、查询。

Authors:
    徐泽宇

Copyright:
    © 2026 徐泽宇
"""

from __future__ import annotations

import hashlib
import os
import uuid
from typing import Any

from sqlalchemy import and_, func, or_
from sqlalchemy.orm import Session

from models.file import File as FileModel, PAGE_KINDS
from models.file_wiki_link import FileWikiLink
from models.user import User
from services.acl_service import accessible_file_ids
from services.md_wiki_link_scan import scan_wiki_links_in_markdown
from services.md_paths import resolve_upload_path
from services.okf_note_service import read_okf_body_for_file
from utils.wiki_slug import normalize_wiki_slug

WIKI_PAGE_KINDS = {"entity", "concept", "synthesis"}




def _ensure_file_workspace(db: Session, file_record: FileModel) -> int:
    if file_record.workspace_id is not None:
        return int(file_record.workspace_id)
    from models.user import User
    from services.workspace_service import ensure_personal_workspace

    owner = db.query(User).filter(User.id == file_record.user_id).first()
    if not owner:
        raise ValueError("file owner missing")
    ws = ensure_personal_workspace(db, owner)
    file_record.workspace_id = ws.id
    return int(ws.id)

def delete_wiki_links_for_file(db: Session, file_id: int) -> None:
    db.query(FileWikiLink).filter(FileWikiLink.source_file_id == file_id).delete()


def _resolve_target_file(
    db: Session,
    actor: User,
    workspace_id: int | None,
    target_id: int,
) -> tuple[int | None, str | None]:
    target = db.query(FileModel).filter(FileModel.id == target_id).first()
    if not target:
        return None, "deleted"
    if workspace_id is not None and target.workspace_id != workspace_id:
        return None, "deleted"
    allowed = accessible_file_ids(db, actor, workspace_id or target.workspace_id)
    if target.id not in allowed and not actor.is_admin:
        return target.id, "acl"
    return target.id, None


def _resolve_wiki_slug(
    db: Session,
    actor: User,
    workspace_id: int | None,
    user_id: int,
    slug: str,
) -> tuple[int | None, str | None]:
    slug = normalize_wiki_slug(slug)
    if not slug:
        return None, "deleted"
    q = db.query(FileModel).filter(
        FileModel.wiki_slug == slug,
        FileModel.page_kind.in_(tuple(WIKI_PAGE_KINDS)),
    )
    if workspace_id is not None:
        q = q.filter(FileModel.workspace_id == workspace_id)
    else:
        q = q.filter(FileModel.user_id == user_id)
    candidates = q.order_by(FileModel.id).all()
    if not candidates:
        return None, "deleted"
    candidates.sort(key=lambda row: (0 if row.user_id == user_id else 1, row.id))
    ws_for_acl = workspace_id or candidates[0].workspace_id
    allowed = accessible_file_ids(db, actor, ws_for_acl)
    for target in candidates:
        if actor.is_admin or target.id in allowed:
            return target.id, None
    return candidates[0].id, "acl"


def _resolve_okf_path(
    db: Session,
    actor: User,
    workspace_id: int | None,
    user_id: int,
    source_concept_path: str | None,
    link_target: str,
) -> tuple[int | None, str | None]:
    if not source_concept_path:
        return None, "deleted"
    from services.okf.paths import resolve_relative_link

    concept_id = resolve_relative_link(source_concept_path, link_target)
    q = db.query(FileModel).filter(
        FileModel.okf_concept_path == concept_id,
        FileModel.page_kind.in_(tuple(WIKI_PAGE_KINDS)),
    )
    if workspace_id is not None:
        q = q.filter(FileModel.workspace_id == workspace_id)
    else:
        q = q.filter(FileModel.user_id == user_id, FileModel.workspace_id.is_(None))
    target = q.first()
    if not target:
        return None, "deleted"
    ws_for_acl = workspace_id or target.workspace_id
    allowed = accessible_file_ids(db, actor, ws_for_acl)
    if target.id not in allowed and not actor.is_admin:
        return target.id, "acl"
    return target.id, None


def rebuild_wiki_links_for_file(db: Session, actor: User, file_id: int) -> int:
    """删除并重扫 source 文件的 outlinks；返回 outlink 数。"""
    delete_wiki_links_for_file(db, file_id)
    source = db.query(FileModel).filter(FileModel.id == file_id).first()
    if not source or not source.has_md or not source.md_file_path:
        if source:
            source.wiki_outlink_count = 0
        return 0
    disk_path = resolve_upload_path(source.md_file_path) or source.md_file_path
    if not disk_path or not os.path.isfile(disk_path):
        source.wiki_outlink_count = 0
        return 0
    ws_id = _ensure_file_workspace(db, source)
    text = read_okf_body_for_file(source) or ""
    content_hash = _md_content_sha256(text)
    occs = scan_wiki_links_in_markdown(text)
    count = 0
    for occ_idx, occ in enumerate(occs, start=1):
        u = uuid.uuid4().hex[:12]
        anchor_id = f"fwl-{file_id}-{u}-{occ_idx}"
        target_file_id: int | None = None
        target_wiki_slug: str | None = None
        target_file_id_raw: int | None = None
        broken_reason: str | None = None
        if occ.link_kind == "file_id":
            try:
                raw_id = int(occ.raw_target)
            except ValueError:
                raw_id = 0
            target_file_id_raw = raw_id if raw_id > 0 else None
            target_file_id, broken_reason = _resolve_target_file(
                db, actor, ws_id, raw_id
            )
        elif occ.link_kind == "okf_path":
            target_file_id, broken_reason = _resolve_okf_path(
                db,
                actor,
                ws_id,
                source.user_id,
                source.okf_concept_path,
                occ.raw_target,
            )
        else:
            target_wiki_slug = occ.raw_target
            target_file_id, broken_reason = _resolve_wiki_slug(
                db,
                actor,
                ws_id,
                source.user_id,
                occ.raw_target,
            )
        db.add(
            FileWikiLink(
                source_file_id=file_id,
                target_file_id=target_file_id,
                target_wiki_slug=target_wiki_slug,
                target_file_id_raw=target_file_id_raw,
                link_kind=occ.link_kind,
                link_text=occ.link_text,
                occurrence_index=occ_idx,
                anchor_id=anchor_id,
                start_offset=occ.start,
                end_offset=occ.end,
                broken_reason=broken_reason,
                content_hash=content_hash,
            )
        )
        count += 1
    source.wiki_outlink_count = count
    return count


def heal_wiki_slug_links(db: Session, actor: User, workspace_id: int | None, wiki_slug: str) -> int:
    slug = normalize_wiki_slug(wiki_slug)
    rows = (
        db.query(FileWikiLink.source_file_id)
        .filter(
            FileWikiLink.link_kind == "wiki_slug",
            FileWikiLink.target_wiki_slug == slug,
            FileWikiLink.broken_reason == "deleted",
        )
        .distinct()
        .all()
    )
    healed = 0
    for (sid,) in rows:
        src = db.query(FileModel).filter(FileModel.id == sid).first()
        if not src:
            continue
        src_ws = src.workspace_id
        if src_ws is None:
            src_ws = _ensure_file_workspace(db, src)
        if workspace_id is not None and src_ws != workspace_id:
            continue
        rebuild_wiki_links_for_file(db, actor, sid)
        healed += 1
    return healed


def count_backlinks(db: Session, file_id: int) -> int:
    return (
        db.query(func.count(FileWikiLink.id))
        .filter(
            FileWikiLink.target_file_id == file_id,
            FileWikiLink.broken_reason.is_(None),
        )
        .scalar()
        or 0
    )


def _outlink_dedupe_key(row: dict[str, Any]) -> str:
    if row.get("target_file_id"):
        return f"file:{row['target_file_id']}"
    slug = row.get("target_wiki_slug")
    if slug:
        return f"wiki:{slug}"
    return f"anchor:{row['anchor_id']}"


def _dedupe_outlinks(outlinks: list[dict[str, Any]]) -> list[dict[str, Any]]:
    seen: dict[str, dict[str, Any]] = {}
    for row in outlinks:
        key = _outlink_dedupe_key(row)
        prev = seen.get(key)
        if prev is None or (prev.get("broken") and not row.get("broken")):
            seen[key] = row
    return list(seen.values())


def _dedupe_backlinks(backlinks: list[dict[str, Any]]) -> list[dict[str, Any]]:
    seen: dict[int, dict[str, Any]] = {}
    for row in backlinks:
        sid = int(row["source_file_id"])
        prev = seen.get(sid)
        if prev is None or (prev.get("broken") and not row.get("broken")):
            seen[sid] = row
    return list(seen.values())


def get_wiki_links_for_file(
    db: Session,
    actor: User,
    file_id: int,
    *,
    dedupe: bool = True,
    source_file_direct_only: bool = False,
) -> dict[str, Any]:
    source = db.query(FileModel).filter(FileModel.id == file_id).first()
    if not source:
        return {
            "file_id": file_id,
            "outlinks": [],
            "backlinks": [],
            "outlink_count": 0,
            "backlink_count": 0,
            "coref_files": [],
            "coref_count": 0,
        }
    ws_id = _ensure_file_workspace(db, source)
    allowed = accessible_file_ids(db, actor, ws_id)
    if not actor.is_admin and file_id not in allowed:
        return {
            "file_id": file_id,
            "outlinks": [],
            "backlinks": [],
            "outlink_count": 0,
            "backlink_count": 0,
            "coref_files": [],
            "coref_count": 0,
        }

    out_rows = (
        db.query(FileWikiLink)
        .filter(FileWikiLink.source_file_id == file_id)
        .order_by(FileWikiLink.occurrence_index)
        .all()
    )
    target_ids = {r.target_file_id for r in out_rows if r.target_file_id}
    target_names: dict[int, str] = {}
    target_page_kinds: dict[int, str] = {}
    if target_ids:
        for tf in db.query(FileModel).filter(FileModel.id.in_(target_ids)).all():
            target_names[tf.id] = tf.original_name
            target_page_kinds[tf.id] = tf.page_kind or "source"
    outlinks = []
    for r in out_rows:
        if r.broken_reason == "acl":
            continue
        if r.target_file_id and r.target_file_id not in allowed and not actor.is_admin:
            continue
        if source_file_direct_only:
            if r.link_kind != "file_id" or r.broken_reason is not None:
                continue
            if r.target_file_id is None:
                continue
            if target_page_kinds.get(r.target_file_id, "source") != "source":
                continue
        outlinks.append(
            {
                "target_file_id": r.target_file_id,
                "target_name": target_names.get(r.target_file_id) if r.target_file_id else None,
                "target_wiki_slug": r.target_wiki_slug,
                "link_kind": r.link_kind,
                "link_text": r.link_text,
                "anchor_id": r.anchor_id,
                "start_offset": r.start_offset,
                "end_offset": r.end_offset,
                "broken": r.broken_reason is not None,
                "broken_reason": r.broken_reason,
            }
        )

    backlink_match = and_(
        FileWikiLink.target_file_id == file_id,
        FileWikiLink.broken_reason.is_(None),
    )
    source_wiki_slug = normalize_wiki_slug(source.wiki_slug or "")
    if source_wiki_slug:
        backlink_match = or_(
            backlink_match,
            and_(
                FileWikiLink.link_kind == "wiki_slug",
                FileWikiLink.target_wiki_slug == source_wiki_slug,
                or_(
                    FileWikiLink.broken_reason.is_(None),
                    FileWikiLink.broken_reason == "deleted",
                ),
            ),
        )

    back_rows = (
        db.query(FileWikiLink, FileModel)
        .join(FileModel, FileModel.id == FileWikiLink.source_file_id)
        .filter(FileModel.workspace_id == ws_id, backlink_match)
        .order_by(FileModel.original_name, FileWikiLink.occurrence_index)
        .all()
    )
    backlinks = []
    for link, src in back_rows:
        src_allowed = accessible_file_ids(db, actor, src.workspace_id) if src.workspace_id else set()
        if not actor.is_admin and src.id not in src_allowed:
            continue
        if source_file_direct_only:
            if link.link_kind != "file_id":
                continue
            if (src.page_kind or "source") != "source":
                continue
        backlinks.append(
            {
                "source_file_id": src.id,
                "source_name": src.original_name,
                "link_text": link.link_text,
                "anchor_id": link.anchor_id,
                "broken": False,
            }
        )
    if dedupe:
        outlinks = _dedupe_outlinks(outlinks)
        backlinks = _dedupe_backlinks(backlinks)
    from services.wiki_link_edges_service import get_coref_peers_for_file

    coref_files = get_coref_peers_for_file(db, file_id, ws_id, allowed)
    from services.wiki_provenance_service import enrich_wiki_links_payload

    return enrich_wiki_links_payload(
        {
            "file_id": file_id,
            "outlinks": outlinks,
            "backlinks": backlinks,
            "outlink_count": len(outlinks),
            "backlink_count": len(backlinks),
            "coref_files": coref_files,
            "coref_count": len(coref_files),
        }
    )


def batch_rebuild_all_wiki_links(
    db: Session,
    actor: User,
    *,
    user_id: int | None = None,
    batch_size: int = 100,
) -> dict[str, int]:
    q = db.query(FileModel).filter(FileModel.has_md.is_(True))
    if user_id is not None:
        q = q.filter(FileModel.user_id == user_id)
    files = q.order_by(FileModel.id).all()
    rebuilt = 0
    for i, f in enumerate(files):
        rebuild_wiki_links_for_file(db, actor, f.id)
        rebuilt += 1
        if batch_size and (i + 1) % batch_size == 0:
            db.commit()
    db.commit()
    return {"rebuilt_count": rebuilt, "file_count": len(files)}


def _md_content_sha256(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def wiki_links_stale_for_file(db: Session, file_id: int) -> bool:
    """sidecar MD 哈希与 file_wiki_links.content_hash 不一致时为 stale。"""
    source = db.query(FileModel).filter(FileModel.id == file_id).first()
    if not source or not source.has_md or not source.md_file_path:
        return False
    if not os.path.isfile(source.md_file_path):
        return False
    current = _md_content_sha256(read_okf_body_for_file(source) or "")
    rows = (
        db.query(FileWikiLink.content_hash)
        .filter(FileWikiLink.source_file_id == file_id)
        .all()
    )
    if not rows:
        return False
    stored = next((r[0] for r in rows if r[0]), None)
    if not stored:
        # 迁移前或尚未 rebuild 的行 content_hash 为 NULL，不视为 stale
        return False
    return stored != current
