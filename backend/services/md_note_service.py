# Copyright (c) 2026 徐泽宇
"""资料 Markdown 笔记：写入磁盘与索引/锚点联动。

Authors:
    徐泽宇

Copyright:
    © 2026 徐泽宇
"""

from __future__ import annotations

import os

from fastapi import HTTPException, status
from sqlalchemy.orm import Session

from models.file import File as FileModel
from models.file_md_version import FileMdVersion
from services.file_service import get_extension, get_mime_type
from services.md_paths import is_legacy_flat_md_note_path, md_note_path, resolve_upload_path
from utils.text_sanitize import strip_nul_bytes


def is_markdown_upload(filename: str | None, mime_type: str | None = None) -> bool:
    """上传文件是否应同步写入资料笔记（Markdown 或纯文本 .txt）。"""
    mime = (mime_type or "").lower().split(";", 1)[0].strip()
    if mime in ("text/markdown", "text/x-markdown", "text/plain"):
        return True
    name = (filename or "").lower()
    ext = get_extension(name)
    if ext in ("md", "markdown", "txt"):
        return True
    if not mime or mime == "application/octet-stream":
        return get_mime_type(name) in ("text/markdown", "text/plain")
    return False


def decode_upload_markdown(content: bytes) -> str:
    return strip_nul_bytes(content.decode("utf-8", errors="replace"))


def _resolved_md_path(file_record: FileModel) -> str | None:
    if not file_record.md_file_path:
        return None
    return resolve_upload_path(file_record.md_file_path) or file_record.md_file_path


def read_md_note_text(file_record: FileModel) -> str | None:
    """读取资料 sidecar 笔记正文；无笔记或文件缺失时返回 None。"""
    if not file_record.has_md or not file_record.md_file_path:
        return None
    path = _resolved_md_path(file_record)
    if not path or not os.path.isfile(path):
        return None
    try:
        with open(path, encoding="utf-8") as fh:
            return fh.read()
    except OSError:
        return None


def read_file_md_plaintext_or_raise(file_record: FileModel) -> str:
    """读取 sidecar 笔记正文；缺失时抛出与 GET /files/{id}/md 一致的 HTTP 404。"""
    if not file_record.has_md or not file_record.md_file_path:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="该资料没有 Markdown 笔记",
        )
    path = _resolved_md_path(file_record)
    if not path or not os.path.isfile(path):
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Markdown 笔记已不存在",
        )
    try:
        with open(path, encoding="utf-8") as fh:
            return fh.read()
    except OSError:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Markdown 笔记已不存在",
        )


def _read_md_note_text(file_record: FileModel) -> str | None:
    return read_md_note_text(file_record)


def clear_manual_override_on_md_write(file_record: FileModel) -> None:
    """047: sidecar md 为 source of truth；写入时清除人工 chunk 覆盖标记。"""
    file_record.kb_index_manual_override = False


def legacy_md_note_write_allowed(file_record: FileModel) -> bool:
    """True when OKF concept_path is set but sidecar is still legacy flat `.md_notes/` file."""
    if not file_record.okf_concept_path:
        return True
    if not file_record.md_file_path:
        return False
    resolved = resolve_upload_path(file_record.md_file_path) or file_record.md_file_path
    return bool(resolved and is_legacy_flat_md_note_path(resolved) and os.path.isfile(resolved))


def save_md_note_for_file(
    db: Session,
    user_id: int,
    file_record: FileModel,
    content: str,
    *,
    enqueue_vector_index: bool = True,
) -> int | None:
    """写入资料笔记并执行与 PUT /files/{id}/md 相同的后处理（不 commit）。返回索引任务 id。"""
    if file_record.okf_concept_path and not legacy_md_note_write_allowed(file_record):
        raise ValueError(
            "OKF native concept sidecars must use okf_note_service.save_okf_body_for_file"
        )
    path = md_note_path(file_record.id)
    prev_text = _read_md_note_text(file_record)
    if prev_text is not None and prev_text == content:
        return None

    if prev_text is not None and prev_text != content:
        ver = int(file_record.md_content_rev or 0) + 1
        db.add(
            FileMdVersion(
                file_id=file_record.id,
                version=ver,
                content=prev_text,
                created_by_user_id=user_id,
            )
        )
        file_record.md_content_rev = ver
    clear_manual_override_on_md_write(file_record)

    with open(path, "w", encoding="utf-8") as fh:
        fh.write(content)

    file_record.has_md = True
    file_record.md_file_path = path

    from services.md_hash_service import touch_md_content_hash

    touch_md_content_hash(db, file_record, content=content)

    from services.md_tag_anchor_service import rebuild_anchors_for_file

    rebuild_anchors_for_file(db, user_id, file_record.id)
    rebuild_md_note_side_effects(db, user_id, file_record.id)

    if not enqueue_vector_index:
        return None
    from services.kb_index_service import enqueue_index

    return enqueue_index(db, user_id, file_record.id)


def restore_md_note_version(
    db: Session,
    user_id: int,
    file_record: FileModel,
    version_content: str,
    *,
    enqueue_vector_index: bool = True,
) -> int | None:
    """恢复资料笔记至给定历史内容（管理员版本恢复路径）。

    OKF native 笔记的版本内容为 body-only，走 ``save_okf_body_for_file`` 只替换
    body、保留 frontmatter，并在覆写前把当前 body 快照为新版本（保留版本链）。
    legacy sidecar 的版本内容为整段 raw，回退到 ``save_md_note_for_file`` 原地覆写。
    返回索引任务 id（无变更或不需要入队时为 None）。
    """
    from services.okf_note_service import read_okf_note, save_okf_body_for_file

    note = read_okf_note(file_record)
    if not note.is_legacy and file_record.has_md:
        prev_body = note.body or ""
        if prev_body == version_content:
            return None
        ver = int(file_record.md_content_rev or 0) + 1
        db.add(
            FileMdVersion(
                file_id=file_record.id,
                version=ver,
                content=prev_body,
                created_by_user_id=user_id,
            )
        )
        file_record.md_content_rev = ver
        clear_manual_override_on_md_write(file_record)
        save_okf_body_for_file(file_record, version_content)
        from services.md_tag_anchor_service import rebuild_anchors_for_file

        rebuild_anchors_for_file(db, user_id, file_record.id)
        rebuild_md_note_side_effects(db, user_id, file_record.id)
        if not enqueue_vector_index:
            return None
        from services.kb_index_service import enqueue_index

        return enqueue_index(db, user_id, file_record.id)

    return save_md_note_for_file(
        db, user_id, file_record, version_content, enqueue_vector_index=enqueue_vector_index
    )


def publish_md_note_index_job(db: Session, user_id: int, file_id: int, job_id: int | None) -> None:
    if job_id is None:
        return
    from services.kb_index_service import publish_index_job

    publish_index_job(db, user_id, file_id, job_id)


def maybe_attach_md_note_from_upload(
    db: Session,
    user_id: int,
    file_record: FileModel,
    content: bytes,
) -> tuple[bool, int | None]:
    """若上传为 Markdown 或 .txt，将正文写入资料笔记。返回 (是否写入, 索引任务 id)。"""
    if not is_markdown_upload(file_record.original_name, file_record.mime_type):
        return False, None
    text = decode_upload_markdown(content)
    job_id = save_md_note_for_file(db, user_id, file_record, text)
    return True, job_id


def sync_kb_index_after_md_note(db: Session, user_id: int) -> None:
    from services.knowledge_base_index_service import auto_sync_kb_index

    auto_sync_kb_index(db, user_id)


def rebuild_md_note_side_effects(db: Session, user_id: int, file_id: int) -> None:
    """标签锚点、Wiki 互链与编译队列（不写盘、不入队向量索引）。"""
    from models.user import User
    from services.md_wiki_link_service import rebuild_wiki_links_for_file

    actor = db.query(User).filter(User.id == user_id).first()
    if not actor:
        return
    rebuild_wiki_links_for_file(db, actor, file_id)
    f = db.query(FileModel).filter(FileModel.id == file_id).first()
    if f:
        from services.wiki_compile_queue_service import sync_compile_queue_after_md_save

        sync_compile_queue_after_md_save(db, actor, f.workspace_id)
