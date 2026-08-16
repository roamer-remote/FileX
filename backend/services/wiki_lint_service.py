# Copyright (c) 2026 徐泽宇
"""Wiki 互链体检。

Authors:
    徐泽宇

Copyright:
    © 2026 徐泽宇
"""

from __future__ import annotations

from typing import Any

from sqlalchemy.orm import Session

from models.file import File as FileModel
from models.file_wiki_link import FileWikiLink
from models.user import User
from services.acl_service import accessible_file_ids
from services.knowledge_base_index_service import read_text, WIKI_ANCHOR_START



def _pending_workspace_id(db: Session, user: User, workspace_id: int | None) -> int:
    from services.workspace_access_service import resolve_workspace_id

    return resolve_workspace_id(db, user, workspace_id)


def _load_pending_concepts(db: Session, user: User, workspace_id: int | None) -> list[dict]:
    ws_pending = _pending_workspace_id(db, user, workspace_id)
    from services.system_setting_service import get_kb_wiki_compile_min_sources
    from services.wiki_candidate_service import list_pending_concept_slugs

    return list_pending_concept_slugs(
        db,
        user,
        ws_pending,
        min_sources=get_kb_wiki_compile_min_sources(db, user_id=user.id),
    )

WIKI_PAGE_KINDS = ("entity", "concept", "synthesis")


def lint_user_wiki(
    db: Session,
    user: User,
    workspace_id: int | None = None,
) -> dict[str, Any]:
    q_files = db.query(FileModel).filter(FileModel.user_id == user.id)
    if workspace_id is not None:
        q_files = q_files.filter(FileModel.workspace_id == workspace_id)
    file_ids = [f.id for f in q_files.all()]
    if not file_ids:
        report = _empty_report()
        report["pending_concepts"] = _load_pending_concepts(db, user, workspace_id)
        return report

    link_q = db.query(FileWikiLink).filter(FileWikiLink.source_file_id.in_(file_ids))
    links = link_q.all()

    broken_links = []
    acl_broken_links = []
    for link in links:
        if link.broken_reason == "deleted":
            broken_links.append(
                {
                    "source_file_id": link.source_file_id,
                    "link_kind": link.link_kind,
                    "target": link.target_wiki_slug or link.target_file_id_raw,
                    "broken_reason": "deleted",
                }
            )
        elif link.broken_reason == "acl":
            acl_broken_links.append(
                {
                    "source_file_id": link.source_file_id,
                    "target_file_id": link.target_file_id or link.target_file_id_raw,
                    "broken_reason": "acl",
                }
            )

    concept_q = db.query(FileModel).filter(
        FileModel.user_id == user.id,
        FileModel.page_kind.in_(WIKI_PAGE_KINDS),
    )
    if workspace_id is not None:
        concept_q = concept_q.filter(FileModel.workspace_id == workspace_id)
    concepts = concept_q.all()

    missing_slug = [
        {"file_id": f.id, "page_kind": f.page_kind}
        for f in concepts
        if not (f.wiki_slug or "").strip()
    ]

    orphan_pages = []
    for f in concepts:
        if not (f.wiki_slug or "").strip():
            continue
        bc = (
            db.query(FileWikiLink)
            .filter(
                FileWikiLink.target_file_id == f.id,
                FileWikiLink.broken_reason.is_(None),
            )
            .count()
        )
        if bc == 0 and (f.wiki_outlink_count or 0) == 0:
            orphan_pages.append({"file_id": f.id, "wiki_slug": f.wiki_slug})

    stale_wiki_index = False
    raw = read_text(user.id)
    if raw is not None and WIKI_ANCHOR_START not in raw:
        stale_wiki_index = True

    pending_concepts = _load_pending_concepts(db, user, workspace_id)

    return {
        "broken_links": broken_links,
        "acl_broken_links": acl_broken_links,
        "orphan_pages": orphan_pages,
        "missing_slug": missing_slug,
        "pending_concepts": pending_concepts,
        "stale_wiki_index": stale_wiki_index,
    }


def lint_all_users_with_kb_index(db: Session) -> list[dict[str, Any]]:
    from pathlib import Path
    from config import UPLOAD_DIR

    results = []
    base = Path(UPLOAD_DIR)
    if not base.is_dir():
        return results
    for user_dir in base.iterdir():
        if not user_dir.is_dir():
            continue
        idx = user_dir / "kb_index.md"
        if not idx.is_file():
            continue
        try:
            uid = int(user_dir.name)
        except ValueError:
            continue
        user = db.query(User).filter(User.id == uid).first()
        if not user or not user.is_active:
            continue
        report = lint_user_wiki(db, user)
        results.append({"user_id": uid, **report})
    return results


def _empty_report() -> dict[str, Any]:
    return {
        "broken_links": [],
        "acl_broken_links": [],
        "orphan_pages": [],
        "missing_slug": [],
        "pending_concepts": [],
        "stale_wiki_index": False,
    }
