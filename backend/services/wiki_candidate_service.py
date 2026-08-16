# Copyright (c) 2026 徐泽宇
"""待编译 Wiki 概念页（断链 slug 聚合）。

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
from services.wiki_page_service import WIKI_PAGE_KINDS
from utils.wiki_slug import normalize_wiki_slug

SAMPLE_FILE_IDS_LIMIT = 5


def _existing_concept_slugs(db: Session, workspace_id: int) -> set[str]:
    rows = (
        db.query(FileModel.wiki_slug)
        .filter(
            FileModel.workspace_id == workspace_id,
            FileModel.page_kind.in_(tuple(WIKI_PAGE_KINDS)),
            FileModel.wiki_slug.isnot(None),
        )
        .all()
    )
    out: set[str] = set()
    for (raw,) in rows:
        slug = normalize_wiki_slug(raw or "")
        if slug:
            out.add(slug)
    return out


def list_pending_concept_slugs(
    db: Session,
    user: User,
    workspace_id: int,
    *,
    min_sources: int = 2,
) -> list[dict[str, Any]]:
    """同 workspace 内断链 wiki_slug 按 distinct source 计数，排除已有概念页。"""
    min_sources = max(1, min(int(min_sources), 20))
    allowed = accessible_file_ids(db, user, workspace_id)
    existing = _existing_concept_slugs(db, workspace_id)

    rows = (
        db.query(FileWikiLink.target_wiki_slug, FileWikiLink.source_file_id)
        .join(FileModel, FileModel.id == FileWikiLink.source_file_id)
        .filter(
            FileWikiLink.link_kind == "wiki_slug",
            FileWikiLink.broken_reason == "deleted",
            FileModel.workspace_id == workspace_id,
            FileWikiLink.target_wiki_slug.isnot(None),
        )
        .all()
    )

    slug_sources: dict[str, set[int]] = {}
    for target_slug, source_id in rows:
        if not user.is_admin and source_id not in allowed:
            continue
        slug = normalize_wiki_slug(target_slug or "")
        if not slug or slug in existing:
            continue
        slug_sources.setdefault(slug, set()).add(int(source_id))

    items: list[dict[str, Any]] = []
    for slug in sorted(slug_sources.keys()):
        sources = slug_sources[slug]
        if len(sources) < min_sources:
            continue
        items.append(
            {
                "wiki_slug": slug,
                "source_count": len(sources),
                "sample_file_ids": sorted(sources)[:SAMPLE_FILE_IDS_LIMIT],
            }
        )
    return items
