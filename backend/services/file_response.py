# Copyright (c) 2026 徐泽宇
"""file_response 业务逻辑模块。

Authors:
    徐泽宇
"""

import os
import hashlib

from sqlalchemy.orm import Session

from models.file import File as FileModel
from models.file_tag_anchor import FileTagAnchor
from models.file_wiki_link import FileWikiLink
from models.user import User
from schemas.file import FileResponse as FileSchema
from schemas.file import FileTagAnchorItem
from services.file_service import existing_thumbnail_path, should_generate_thumbnail
from services.office_normalize_service import preview_mime_type
from services.md_paths import resolve_upload_path
from services.okf_note_service import read_okf_body_for_file
from services.tag_service import get_file_tag_names, get_tag_names_by_file_ids
from services.workspace_access_service import file_action_capabilities
from utils.timezone import to_beijing_time


def _md_path_has_content(path: str | None) -> bool:
    resolved = resolve_upload_path(path) if path else None
    if not resolved or not os.path.exists(resolved):
        return False
    try:
        with open(resolved, "r", encoding="utf-8") as fh:
            return bool(fh.read().strip())
    except OSError:
        return False


def _file_md_has_body_content(f: FileModel) -> bool:
    if not f.has_md:
        return False
    body = read_okf_body_for_file(f)
    if body is not None:
        return bool(body.strip())
    return _md_path_has_content(f.md_file_path)


def batch_file_tag_anchors(db: Session, file_ids: list[int]) -> dict[int, list[FileTagAnchorItem]]:
    if not file_ids:
        return {}
    rows = (
        db.query(FileTagAnchor)
        .filter(FileTagAnchor.file_id.in_(file_ids))
        .order_by(FileTagAnchor.file_id, FileTagAnchor.tag_name, FileTagAnchor.occurrence_index)
        .all()
    )
    out: dict[int, list[FileTagAnchorItem]] = {}
    for r in rows:
        out.setdefault(r.file_id, []).append(
            FileTagAnchorItem(
                anchor_id=r.anchor_id,
                tag=r.tag_name,
                occurrence_index=r.occurrence_index,
                start_offset=r.start_offset,
                end_offset=r.end_offset,
            )
        )
    return out


def file_to_schema(
    db: Session,
    f: FileModel,
    username: str | None,
    *,
    user: User | None = None,
    tags: list[str] | None = None,
    tag_anchors: list[FileTagAnchorItem] | None = None,
    deduplicated: bool = False,
    wiki_links_stale: bool | None = None,
    can_write: bool | None = None,
    can_manage: bool | None = None,
) -> FileSchema:
    if tags is None:
        tags = get_file_tag_names(db, f.id)
    if tag_anchors is None:
        tag_anchors = batch_file_tag_anchors(db, [f.id]).get(f.id, [])
    if can_write is None or can_manage is None:
        if user is not None:
            cw, cm = file_action_capabilities(db, user, f)
            if can_write is None:
                can_write = cw
            if can_manage is None:
                can_manage = cm
        else:
            if can_write is None:
                can_write = True
            if can_manage is None:
                can_manage = True
    disk_path = resolve_upload_path(f.file_path) or f.file_path if f.file_path else None
    has_thumb = bool(
        disk_path
        and should_generate_thumbnail(disk_path)
        and existing_thumbnail_path(disk_path) is not None
    )
    return FileSchema(
        id=f.id,
        filename=f.filename,
        original_name=f.original_name,
        file_size=f.file_size,
        mime_type=f.mime_type,
        folder_id=f.folder_id,
        workspace_id=f.workspace_id,
        publish_status=f.publish_status or "published",
        user_id=f.user_id,
        username=username,
        created_at=to_beijing_time(f.created_at).isoformat() if f.created_at else "",
        updated_at=to_beijing_time(f.updated_at).isoformat() if f.updated_at else None,
        md5_hash=f.md5_hash,
        has_md=f.has_md,
        md_has_content=_file_md_has_body_content(f),
        deduplicated=deduplicated,
        tags=tags,
        tag_anchors=tag_anchors,
        has_thumbnail=has_thumb,
        index_status=f.index_status or "skipped",
        indexed_at=to_beijing_time(f.indexed_at).isoformat() if f.indexed_at else None,
        chunk_count=f.chunk_count or 0,
        index_error=f.index_error,
        kb_post_status=getattr(f, "kb_post_status", None) or "pending",
        kb_post_error=getattr(f, "kb_post_error", None),
        kb_post_at=to_beijing_time(f.kb_post_at).isoformat() if getattr(f, "kb_post_at", None) else None,
        extract_status=f.extract_status or "not_needed",
        extracted_at=to_beijing_time(f.extracted_at).isoformat() if f.extracted_at else None,
        extract_error=f.extract_error,
        extract_engine=f.extract_engine,
        preview_mime_type=preview_mime_type(f),
        page_kind=getattr(f, "page_kind", None) or "source",
        wiki_slug=getattr(f, "wiki_slug", None),
        okf_concept_path=getattr(f, "okf_concept_path", None),
        okf_type=getattr(f, "okf_type", None),
        okf_metadata=getattr(f, "okf_metadata", None),
        wiki_links_stale=wiki_links_stale,
        can_write=can_write,
        can_manage=can_manage,
    )


def batch_file_tags(db: Session, file_ids: list[int]) -> dict[int, list[str]]:
    return get_tag_names_by_file_ids(db, file_ids)


def batch_uploader_names(db: Session, user_ids: list[int]) -> dict[int, str]:
    ids = sorted({int(uid) for uid in user_ids if uid is not None})
    if not ids:
        return {}
    rows = db.query(User.id, User.username).filter(User.id.in_(ids)).all()
    return {int(uid): username for uid, username in rows}


def _md_content_sha256(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def batch_wiki_links_stale(db: Session, file_ids: list[int]) -> dict[int, bool]:
    ids = sorted({int(fid) for fid in file_ids})
    if not ids:
        return {}

    out = {fid: False for fid in ids}
    files = (
        db.query(FileModel.id, FileModel.has_md, FileModel.md_file_path)
        .filter(FileModel.id.in_(ids))
        .all()
    )
    md_paths = {
        int(fid): path
        for fid, has_md, path in files
        if has_md and path and os.path.isfile(path)
    }
    if not md_paths:
        return out

    rows = (
        db.query(FileWikiLink.source_file_id, FileWikiLink.content_hash)
        .filter(FileWikiLink.source_file_id.in_(md_paths.keys()))
        .all()
    )
    stored_by_file: dict[int, str | None] = {}
    for fid, content_hash in rows:
        if content_hash and int(fid) not in stored_by_file:
            stored_by_file[int(fid)] = content_hash
        elif int(fid) not in stored_by_file:
            stored_by_file[int(fid)] = None

    for fid, stored in stored_by_file.items():
        if not stored:
            continue
        path = md_paths.get(fid)
        if not path:
            continue
        try:
            with open(path, "r", encoding="utf-8") as fh:
                current = _md_content_sha256(fh.read())
        except OSError:
            continue
        out[fid] = stored != current
    return out
