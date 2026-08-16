# Copyright (c) 2026 徐泽宇
"""外部 API：Markdown 笔记解析、首次挂载与 upsert 更新。

Authors:
    徐泽宇

Copyright:
    © 2026 徐泽宇
"""

from __future__ import annotations

from fastapi import HTTPException, status
from sqlalchemy.orm import Session

from models.file import File as FileModel
from models.file_md_version import FileMdVersion
from models.user import User
from services.log_service import log_operation
from services.okf_note_service import read_okf_body_for_file, save_okf_body_for_file

MAX_EXTERNAL_MD_BYTES = 5 * 1024 * 1024  # 5 MiB


def validate_md_content_size(md_content: str) -> None:
    if len(md_content.encode("utf-8")) > MAX_EXTERNAL_MD_BYTES:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Markdown 内容过大（上限 {MAX_EXTERNAL_MD_BYTES // (1024 * 1024)} MiB）",
        )


from services.acl_service import accessible_file_ids
from services.workspace_access_service import (
    ROLE_VIEWER,
    can_write_file,
    require_workspace_member,
)


def resolve_accessible_file_by_md5(
    db: Session,
    user: User,
    md5_hash: str,
    *,
    workspace_id: int | None = None,
    need_write: bool = False,
) -> FileModel:
    """按 MD5 定位当前用户 ACL 可访问的资料；多匹配时须带 workspace_id 消歧。"""
    normalized = (md5_hash or "").strip().lower()
    if len(normalized) != 32:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="md5_hash 须为 32 位十六进制",
        )

    q = db.query(FileModel).filter(FileModel.md5_hash == normalized)
    if workspace_id is not None:
        q = q.filter(FileModel.workspace_id == workspace_id)

    candidates = q.all()
    if not candidates:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="未找到对应资料")

    accessible: list[FileModel] = []
    for f in candidates:
        try:
            member = require_workspace_member(db, user, f.workspace_id, minimum=ROLE_VIEWER)
            allowed = accessible_file_ids(db, user, f.workspace_id, member=member)
            if f.id not in allowed:
                continue
            if need_write and not can_write_file(db, user, member, f):
                continue
            accessible.append(f)
        except HTTPException:
            continue

    if not accessible:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="未找到对应资料")
    if len(accessible) > 1:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="同 MD5 存在多条资料，请通过查询参数 workspace_id 指定知识空间",
        )
    return accessible[0]


def resolve_file_by_md5(
    db: Session,
    user_id: int,
    md5_hash: str,
    *,
    workspace_id: int | None = None,
) -> FileModel:
    """按 MD5 定位当前用户下的资料；多匹配时须带 workspace_id 消歧。"""
    normalized = (md5_hash or "").strip().lower()
    if len(normalized) != 32:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="md5_hash 须为 32 位十六进制",
        )

    q = db.query(FileModel).filter(
        FileModel.user_id == user_id,
        FileModel.md5_hash == normalized,
    )
    if workspace_id is not None:
        q = q.filter(FileModel.workspace_id == workspace_id)

    rows = q.all()
    if not rows:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="未找到对应资料")
    if len(rows) > 1:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="同 MD5 存在多条资料，请通过查询参数 workspace_id 指定知识空间",
        )
    return rows[0]


def upsert_md_note_for_api(
    db: Session,
    current_user: User,
    file_record: FileModel,
    content: str,
    *,
    log_action: str = "上传 Markdown 笔记",
    log_detail: str | None = None,
) -> dict:
    """新建或更新资料笔记（与 PUT /api/files/{id}/md 一致的后处理）。调用方须已校验访问权限。"""
    validate_md_content_size(content)

    if not file_record.md5_hash:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="文件缺少 MD5，无法关联 Markdown",
        )

    from services.kb_index_service import enqueue_index, publish_index_job
    from services.md_note_service import rebuild_md_note_side_effects, sync_kb_index_after_md_note
    from services.md_tag_anchor_service import rebuild_anchors_for_file
    file_id = file_record.id
    prev_body = read_okf_body_for_file(file_record)
    if prev_body is not None and prev_body == content:
        db.commit()
        return {
            "message": "Markdown 笔记无变更",
            "file_id": file_id,
            "md5_hash": file_record.md5_hash,
            "unchanged": True,
            "index_status": file_record.index_status or "skipped",
        }

    if prev_body is not None and prev_body != content:
        ver = int(file_record.md_content_rev or 0) + 1
        db.add(
            FileMdVersion(
                file_id=file_id,
                version=ver,
                content=prev_body,
                created_by_user_id=current_user.id,
            )
        )
        file_record.md_content_rev = ver

    save_okf_body_for_file(file_record, content)
    rebuild_anchors_for_file(db, current_user.id, file_id)
    rebuild_md_note_side_effects(db, current_user.id, file_id)
    job_id = enqueue_index(db, current_user.id, file_id)
    db.commit()
    if job_id is not None:
        publish_index_job(db, current_user.id, file_id, job_id)
    sync_kb_index_after_md_note(db, current_user.id)

    detail = log_detail or f"为文件 {file_record.original_name} 更新 Markdown 笔记"
    log_operation(db, current_user.id, log_action, "file", file_id, detail)

    return {
        "message": "Markdown 笔记保存成功",
        "file_id": file_id,
        "md5_hash": file_record.md5_hash,
        "unchanged": False,
        "index_status": file_record.index_status or "pending",
    }


def persist_external_markdown_for_file(
    db: Session,
    file_record: FileModel,
    md_content: str,
    current_user: User,
    original_name_hint: str | None,
    *,
    allow_existing: bool = False,
) -> None:
    """首次挂载 Markdown；已有笔记时 409，除非是同请求上传生成的初始正文。"""
    if not allow_existing and file_record.has_md and (read_okf_body_for_file(file_record) or "").strip():
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="该资料已有关联的 Markdown 内容",
        )

    upsert_md_note_for_api(
        db,
        current_user,
        file_record,
        md_content,
        log_action="上传 Markdown 内容",
        log_detail=f"为文件 {original_name_hint or file_record.original_name} 上传 Markdown 内容",
    )
