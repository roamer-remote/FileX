# Copyright (c) 2026 徐泽宇
"""files_md HTTP 路由模块。

Authors:
    徐泽宇
"""

import os

from fastapi import APIRouter, Depends, HTTPException, Query, Response, status
from fastapi.responses import PlainTextResponse
from pydantic import BaseModel
from sqlalchemy.orm import Session

from config import UPLOAD_DIR
from database import get_db
from middleware.auth import get_current_user
from models.user import User
from schemas.tag_graph import TagGraphResponse, TagHeatmapResponse
from utils.agent_freshness import apply_agent_no_cache_headers
from services.log_service import log_operation
from services.workspace_access_service import require_workspace_member, resolve_workspace_id
from services.acl_service import accessible_file_ids

# Reuse helper from files.py — import at runtime to avoid circular deps
from . import files as _files_mod

router = APIRouter()


class FilePublishBody(BaseModel):
    """文件发布请求体 API 路由辅助类型。

        Authors:
            徐泽宇

        Copyright:
            © 2026 徐泽宇

        Since:
            2026-05-30

        Attributes:
            publish_status: 发布状态（str）。
    """
    publish_status: str


@router.put("/{file_id}/publish-status")
def set_publish_status(
    file_id: int,
    body: FilePublishBody,
    workspace_id: int | None = Query(None),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    if body.publish_status not in ("draft", "published"):
        raise HTTPException(status_code=400, detail="publish_status 须为 draft 或 published")
    f, _ws = _files_mod.require_workspace_file(db, file_id, current_user, workspace_id, need_write=True)
    f.publish_status = body.publish_status
    db.commit()
    return {"file_id": file_id, "publish_status": f.publish_status}


@router.get("/{file_id}/md/versions", response_model=list)
def list_md_versions(
    file_id: int,
    workspace_id: int | None = Query(None),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    from models.file_md_version import FileMdVersion
    f, _ws = _files_mod.require_workspace_file(db, file_id, current_user, workspace_id)
    rows = (
        db.query(FileMdVersion)
        .filter(FileMdVersion.file_id == file_id)
        .order_by(FileMdVersion.version.desc())
        .limit(50)
        .all()
    )
    return [
        {
            "id": r.id,
            "file_id": r.file_id,
            "version": r.version,
            "created_by_user_id": r.created_by_user_id,
            "created_at": r.created_at.isoformat() if r.created_at else "",
        }
        for r in rows
    ]


class MdContentRequest(BaseModel):
    """Markdown内容请求 API 路由辅助类型。

        Authors:
            徐泽宇

        Copyright:
            © 2026 徐泽宇

        Since:
            2026-05-30

        Attributes:
            content: 内容（str）。
    """
    content: str


@router.put("/{file_id}/md")
def upload_file_md(
    file_id: int,
    body: MdContentRequest,
    workspace_id: int | None = Query(None),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """上传或更新文件的 Markdown 笔记内容。"""
    f, _ws = _files_mod.require_workspace_file(db, file_id, current_user, workspace_id, need_write=True)

    from services.external_md import upsert_md_note_for_api

    return upsert_md_note_for_api(db, current_user, f, body.content)


@router.get("/{file_id}/md")
def get_file_md(
    file_id: int,
    response: Response,
    workspace_id: int | None = Query(None),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """获取文件的 Markdown 笔记内容。"""
    apply_agent_no_cache_headers(response)
    f, _ws = _files_mod.require_workspace_file(db, file_id, current_user, workspace_id)
    from services.okf_note_service import read_okf_body_plaintext_or_raise

    content = read_okf_body_plaintext_or_raise(f)
    return PlainTextResponse(content, media_type="text/markdown; charset=utf-8")


@router.delete("/{file_id}/md")
def delete_file_md(
    file_id: int,
    workspace_id: int | None = Query(None),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """删除文件的 Markdown 笔记。"""
    f, _ws = _files_mod.require_workspace_file(db, file_id, current_user, workspace_id, need_write=True)
    if not f.has_md or not f.md_file_path:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="该资料没有 Markdown 笔记")

    if os.path.exists(f.md_file_path):
        os.remove(f.md_file_path)

    # 同时清理 content_list sidecar（结构化提取数据）
    from services.md_paths import content_list_json_path
    cl_path = content_list_json_path(file_id)
    if os.path.isfile(cl_path):
        os.remove(cl_path)

    f.has_md = False
    f.md_file_path = None
    f.extracted_at = None
    f.extract_engine = None
    f.md_content_hash = None

    from services.md_tag_anchor_service import delete_anchors_for_file

    delete_anchors_for_file(db, file_id)
    from services.md_wiki_link_service import delete_wiki_links_for_file

    delete_wiki_links_for_file(db, file_id)
    f.wiki_outlink_count = 0
    from services.kb_index_service import delete_chunks_for_file

    delete_chunks_for_file(db, file_id)
    from services.kb_text_source import resolve_index_text
    from services.kb_index_service import enqueue_index, publish_index_job

    text, _src = resolve_index_text(f)
    if text:
        job_id = enqueue_index(db, current_user.id, file_id)
        db.commit()
        if job_id is not None:
            publish_index_job(db, current_user.id, file_id, job_id)
    else:
        f.index_status = "skipped"
        f.chunk_count = 0
        f.indexed_at = None
        f.index_error = None
        db.commit()

    from services.knowledge_base_index_service import auto_sync_kb_index

    auto_sync_kb_index(db, current_user.id)

    log_operation(
        db, current_user.id, "删除 Markdown 笔记", "file",
        file_id, f"删除文件 {f.original_name} 的 Markdown 笔记",
    )

    from messaging.kb_extract_publisher import publish_file_extract_notify

    db.refresh(f)
    try:
        publish_file_extract_notify(f)
    except Exception:
        pass

    return {"message": "Markdown 笔记已删除"}


@router.get("/{file_id}/wiki-links")
def get_file_wiki_links(
    file_id: int,
    workspace_id: int | None = Query(None),
    dedupe: bool = Query(True),
    source_file_direct_only: bool = Query(False),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    f, _ws = _files_mod.require_workspace_file(db, file_id, current_user, workspace_id)
    from services.md_wiki_link_service import get_wiki_links_for_file

    return get_wiki_links_for_file(
        db,
        current_user,
        f.id,
        dedupe=dedupe,
        source_file_direct_only=source_file_direct_only,
    )

@router.get("/{file_id}/wiki-context")
def get_file_wiki_context(
    file_id: int,
    response: Response,
    depth: int = Query(1, ge=1, le=2),
    max_files: int = Query(8, ge=1, le=20),
    include_coref: bool = Query(False),
    workspace_id: int | None = Query(None),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """展开种子资料的 Wiki 出链/共引邻居 MD（BFS，无 LLM）。"""
    apply_agent_no_cache_headers(response)
    f, _ws = _files_mod.require_workspace_file(db, file_id, current_user, workspace_id)
    from services.wiki_context_service import expand_wiki_context
    from schemas.wiki_context import WikiContextResponse

    payload = expand_wiki_context(
        db,
        current_user,
        f.id,
        depth=depth,
        max_files=max_files,
        include_coref=include_coref,
    )
    return WikiContextResponse(**payload)

