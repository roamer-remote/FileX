# Copyright (c) 2026 徐泽宇
"""Wiki 概念页创建。

Authors:
    徐泽宇

Copyright:
    © 2026 徐泽宇
"""

from __future__ import annotations

import hashlib
import os
import uuid
from pathlib import Path

from sqlalchemy.orm import Session

from config import UPLOAD_DIR
from models.file import File as FileModel, PAGE_KINDS
from models.user import User
from services.file_service import get_mime_type
from services.md_note_service import save_md_note_for_file
from models.file_wiki_link import FileWikiLink
from services.md_wiki_link_service import heal_wiki_slug_links, rebuild_wiki_links_for_file
from services.md_note_service import read_md_note_text, save_md_note_for_file
from services.md_wiki_link_scan import replace_wiki_slug_in_markdown
from services.wiki_page_filters import WIKI_PAGE_KINDS
from utils.wiki_slug import normalize_wiki_slug


def _placeholder_path(user_id: int, name: str) -> str:
    month = "wiki-pages"
    uid = uuid.uuid4().hex[:12]
    rel = Path(str(user_id)) / month / f"{uid}_{name}"
    full = Path(UPLOAD_DIR) / rel
    full.parent.mkdir(parents=True, exist_ok=True)
    if not full.exists():
        full.write_bytes(b"")
    return str(full)


def create_wiki_page(
    db: Session,
    actor: User,
    *,
    title: str,
    wiki_slug: str,
    page_kind: str,
    markdown: str,
    workspace_id: int,
) -> FileModel:
    slug = normalize_wiki_slug(wiki_slug)
    if not slug:
        raise ValueError("wiki_slug 无效")
    if page_kind not in WIKI_PAGE_KINDS:
        raise ValueError("page_kind 须为 entity、concept 或 synthesis")
    dup = (
        db.query(FileModel)
        .filter(
            FileModel.user_id == actor.id,
            FileModel.workspace_id == workspace_id,
            FileModel.wiki_slug == slug,
        )
        .first()
    )
    if dup:
        raise FileExistsError("wiki_slug 冲突")

    safe_name = (title or slug).strip()[:200] or slug
    if not safe_name.lower().endswith(".md"):
        safe_name = f"{safe_name}.md"
    path = _placeholder_path(actor.id, safe_name)
    md5 = hashlib.md5(markdown.encode("utf-8")).hexdigest()
    f = FileModel(
        user_id=actor.id,
        workspace_id=workspace_id,
        filename=os.path.basename(path),
        original_name=safe_name,
        file_path=path,
        file_size=len(markdown.encode("utf-8")),
        mime_type=get_mime_type(safe_name) or "text/markdown",
        md5_hash=md5,
        has_md=False,
        page_kind=page_kind,
        wiki_slug=slug,
        index_status="pending",
    )
    db.add(f)
    db.flush()
    save_md_note_for_file(db, actor.id, f, markdown, enqueue_vector_index=True)
    heal_wiki_slug_links(db, actor, workspace_id, slug)
    return f


def wiki_pages_base_query(db: Session, workspace_id: int):
    return (
        db.query(FileModel)
        .filter(
            FileModel.workspace_id == workspace_id,
            FileModel.page_kind.in_(tuple(WIKI_PAGE_KINDS)),
        )
        .order_by(FileModel.wiki_slug, FileModel.id)
    )


def get_wiki_page_by_slug(
    db: Session,
    user: User,
    workspace_id: int,
    wiki_slug: str,
) -> FileModel | None:
    from services.acl_service import accessible_file_ids

    slug = normalize_wiki_slug(wiki_slug)
    if not slug:
        return None
    f = (
        db.query(FileModel)
        .filter(
            FileModel.workspace_id == workspace_id,
            FileModel.wiki_slug == slug,
            FileModel.page_kind.in_(tuple(WIKI_PAGE_KINDS)),
        )
        .first()
    )
    if not f:
        return None
    allowed = accessible_file_ids(db, user, workspace_id)
    if not user.is_admin and f.id not in allowed:
        return None
    return f

def rename_wiki_page_slug(
    db: Session,
    actor: User,
    file_id: int,
    *,
    new_wiki_slug: str,
    workspace_id: int,
) -> tuple[FileModel, int]:
    """修改主题页 wiki_slug，并同步更新关联笔记中的 [[wiki:…]] 引用。"""
    slug = normalize_wiki_slug(new_wiki_slug)
    if not slug:
        raise ValueError("wiki_slug 无效")

    f = db.query(FileModel).filter(FileModel.id == file_id).first()
    if not f or f.workspace_id != workspace_id:
        raise LookupError("概念页不存在")
    if (f.page_kind or "") not in WIKI_PAGE_KINDS:
        raise ValueError("非主题页资料")
    if actor.id != f.user_id and not actor.is_admin:
        raise PermissionError("无权修改此主题页")

    old_slug = normalize_wiki_slug(f.wiki_slug or "")
    if not old_slug:
        raise ValueError("当前主题页缺少 wiki_slug")
    if slug == old_slug:
        return f, 0

    dup = (
        db.query(FileModel)
        .filter(
            FileModel.workspace_id == workspace_id,
            FileModel.wiki_slug == slug,
            FileModel.page_kind.in_(tuple(WIKI_PAGE_KINDS)),
            FileModel.id != file_id,
        )
        .first()
    )
    if dup:
        raise FileExistsError("wiki_slug 冲突")

    source_ids = [
        sid
        for (sid,) in db.query(FileModel.id)
        .join(FileWikiLink, FileWikiLink.source_file_id == FileModel.id)
        .filter(
            FileModel.workspace_id == workspace_id,
            FileWikiLink.link_kind == "wiki_slug",
            FileWikiLink.target_wiki_slug == old_slug,
        )
        .distinct()
        .all()
    ]

    notes_updated = 0
    for sid in source_ids:
        src = db.query(FileModel).filter(FileModel.id == sid).first()
        if not src or not src.has_md:
            continue
        md_text = read_md_note_text(src)
        if md_text is None:
            continue
        new_text, count = replace_wiki_slug_in_markdown(md_text, old_slug, slug)
        if count <= 0:
            continue
        save_md_note_for_file(db, actor.id, src, new_text, enqueue_vector_index=True)
        rebuild_wiki_links_for_file(db, actor, sid)
        notes_updated += 1

    f.wiki_slug = slug
    db.flush()

    from models.wiki_compile_queue import WikiCompileQueue

    db.query(WikiCompileQueue).filter(
        WikiCompileQueue.workspace_id == workspace_id,
        WikiCompileQueue.wiki_slug == old_slug,
    ).update({WikiCompileQueue.wiki_slug: slug}, synchronize_session=False)

    heal_wiki_slug_links(db, actor, workspace_id, slug)
    rebuild_wiki_links_for_file(db, actor, file_id)
    return f, notes_updated

