# Copyright (c) 2026 徐泽宇
"""external_uploads HTTP 路由模块。

Authors:
    徐泽宇
"""

import hashlib
import os

from fastapi import APIRouter, Depends, File, Form, Header, HTTPException, Query, UploadFile, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from fastapi.responses import Response
from pydantic import BaseModel
from sqlalchemy.orm import Session

from database import get_db
from middleware.auth import api_key_status_hint, build_api_key_status, get_api_key_user
from models.user import User
from models.file import File as FileModel
from models.folder import Folder as FolderModel
from schemas.external_api import ApiKeyStatusResponse
from schemas.file import (
    ExternalUploadWithMdResponse,
    FileResponse as FileSchema,
    FileTagsUpdateRequest,
)
from services.file_response import file_to_schema
from services.file_service import save_upload, save_thumbnail, validate_file
from services.okf_note_service import initialize_okf_note_for_upload
from services.system_setting_service import get_max_upload_bytes
from services.tag_service import get_file_tag_names, list_user_tag_names, merge_file_tags
from services.log_service import log_operation
from services.external_share_gate import validate_optional_share_context
from services.external_md import (
    persist_external_markdown_for_file,
    resolve_accessible_file_by_md5,
    upsert_md_note_for_api,
)
from services.awaiting_ai_files_md import render_awaiting_ai_files_markdown
from services.workspace_layout_md import render_workspace_layout_markdown
from services.workspace_access_service import require_workspace_member, resolve_workspace_id

router = APIRouter()


async def _external_upload_core(
    db: Session,
    file: UploadFile,
    current_user: User,
    x_filex_share_token: str | None,
    *,
    x_filex_share_password: str | None = None,
    workspace_id: int | None = None,
    folder_id: int | None = None,
) -> tuple[FileModel, bool]:
    """保存外部上传文件；返回 (记录, 是否为同用户 MD5 去重)。"""
    try:
        validate_file(file)
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))

    content = await file.read()
    max_bytes = get_max_upload_bytes(db)
    if len(content) > max_bytes:
        mb = max_bytes // (1024 * 1024)
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"文件大小超过限制（最大 {mb}MB）",
        )
    file_md5 = hashlib.md5(content).hexdigest()

    validate_optional_share_context(
        db,
        x_filex_share_token,
        current_user,
        file_md5,
        share_password=x_filex_share_password,
    )

    ws_id = resolve_workspace_id(db, current_user, workspace_id)
    require_workspace_member(db, current_user, ws_id, minimum="contributor")
    if folder_id is not None:
        folder = (
            db.query(FolderModel)
            .filter(FolderModel.id == folder_id, FolderModel.workspace_id == ws_id)
            .first()
        )
        if not folder:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="文件夹不存在")

    existing = db.query(FileModel).filter(
        FileModel.md5_hash == file_md5,
        FileModel.user_id == current_user.id,
        FileModel.workspace_id == ws_id,
    ).first()
    if existing:
        uploader = db.query(User).filter(User.id == existing.user_id).first()
        return existing, True

    file_record = save_upload(file, current_user.id, content)
    file_record.workspace_id = ws_id
    file_record.folder_id = folder_id
    file_record.md5_hash = file_md5
    db.add(file_record)
    db.flush()
    body_attached = initialize_okf_note_for_upload(db, file_record, content)
    db.commit()
    db.refresh(file_record)
    if body_attached:
        from services.kb_index_service import enqueue_index, publish_index_job
        from services.md_note_service import sync_kb_index_after_md_note

        index_job_id = enqueue_index(db, current_user.id, file_record.id)
        db.commit()
        if index_job_id is not None:
            publish_index_job(db, current_user.id, file_record.id, index_job_id)
        sync_kb_index_after_md_note(db, current_user.id)

    save_thumbnail(file_record.file_path)

    log_operation(
        db, current_user.id, "文件上传（API）", "file",
        file_record.id, f"通过 API 上传文件 {file_record.original_name}",
    )

    return file_record, False


@router.get("/api-key-status", response_model=ApiKeyStatusResponse)
def api_key_status(
    db: Session = Depends(get_db),
    creds: HTTPAuthorizationCredentials | None = Depends(HTTPBearer(auto_error=False)),
):
    """智能体前置探测：API Key 是否可用、所属用户是否启用。**不**更新 `ApiKey.last_used_at`。"""
    if creds is None:
        reason = "missing_authorization"
        return ApiKeyStatusResponse(
            valid=False,
            reason=reason,
            hint=api_key_status_hint(reason),
            username=None,
            user_id=None,
        )
    return ApiKeyStatusResponse(**build_api_key_status(creds.credentials, db))


# ── 智能体：待 AI 处理文件列表（Markdown）────────────────────────

@router.get("/files-awaiting-ai")
def list_files_awaiting_ai_markdown(
    workspace_id: int | None = Query(None, description="限定知识空间；未传时默认为个人空间"),
    cross_workspace: bool = Query(
        False,
        description="为 true 时汇总各可访问空间内的待处理文件（与 workspace_id 互斥，优先 cross_workspace）",
    ),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_api_key_user),
):
    """
    返回当前 API Key 所属用户下：**无标签**且 **无 Markdown 笔记**（`has_md` 为假）的文件列表，
    正文为 Markdown 表格（`Content-Type: text/markdown; charset=utf-8`），**无分页**。
    """
    if cross_workspace and workspace_id is not None:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="cross_workspace 与 workspace_id 不能同时指定",
        )
    body = render_awaiting_ai_files_markdown(
        db,
        current_user,
        workspace_id=workspace_id,
        cross_workspace=cross_workspace,
    )
    return Response(
        content=body,
        media_type="text/markdown; charset=utf-8",
    )


@router.get("/workspace-layout")
def workspace_layout_markdown(
    workspace_id: int | None = Query(None, description="知识空间 id；未传时默认为个人空间"),
    folder_id: int | None = Query(
        None,
        description="仅导出该目录内资料；0 表示未分类；不传则导出空间内全部可见 source 资料",
    ),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_api_key_user),
):
    """单知识空间文件夹树 + 资料清单（Markdown，无分页；资料行数上限见 AGENT_LAYOUT_MAX_FILES）。"""
    body = render_workspace_layout_markdown(
        db,
        current_user,
        workspace_id=workspace_id,
        folder_id=folder_id,
    )
    return Response(
        content=body,
        media_type="text/markdown; charset=utf-8",
    )


# ── 2.1 文件上传 ─────────────────────────────────────────────

@router.post("/files", response_model=FileSchema)
async def upload_file_external(
    file: UploadFile = File(...),
    workspace_id: int | None = Form(None),
    folder_id: int | None = Form(None),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_api_key_user),
    x_filex_share_token: str | None = Header(None, alias="X-FileX-Share-Token"),
    x_filex_share_password: str | None = Header(None, alias="X-FileX-Share-Password"),
):
    """上传文件，保存到磁盘和数据库，返回 MD5 摘要。"""
    file_record, dedup = await _external_upload_core(
        db,
        file,
        current_user,
        x_filex_share_token,
        x_filex_share_password=x_filex_share_password,
        workspace_id=workspace_id,
        folder_id=folder_id,
    )
    if dedup:
        uploader = db.query(User).filter(User.id == file_record.user_id).first()
        return file_to_schema(
            db, file_record, uploader.username if uploader else None, deduplicated=True,
        )
    from services.extract.policy import needs_extract
    from services.kb_extract_service import enqueue_extract, publish_extract_job

    if needs_extract(file_record):
        job_id = enqueue_extract(db, current_user.id, file_record.id)
        db.commit()
        if job_id is not None:
            publish_extract_job(db, current_user.id, file_record.id, job_id)
        db.refresh(file_record)

    from services.knowledge_base_index_service import auto_sync_kb_index

    auto_sync_kb_index(db, current_user.id)

    return file_to_schema(db, file_record, current_user.username, tags=[])


@router.post("/files-with-md", response_model=ExternalUploadWithMdResponse)
async def upload_file_external_with_markdown(
    file: UploadFile = File(...),
    markdown: str | None = Form(None),
    content_list: str | None = Form(None, description="JSON: wrapper or array"),
    workspace_id: int | None = Form(None),
    folder_id: int | None = Form(None),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_api_key_user),
    x_filex_share_token: str | None = Header(None, alias="X-FileX-Share-Token"),
    x_filex_share_password: str | None = Header(None, alias="X-FileX-Share-Password"),
):
    """
    单次请求上传原文（multipart `file`）并可附带生成的 Markdown（form 字段 `markdown`）。
    适用于第三方下载链接：不传 `X-FileX-Share-Token`，仅用 API Key 归属用户入库；
    若来源于本站分享链接，仍应带头做所有者校验。
    `markdown` 为空或仅空白则等价于仅调用 `POST /api/external/files`。
    """
    file_record, dedup = await _external_upload_core(
        db,
        file,
        current_user,
        x_filex_share_token,
        x_filex_share_password=x_filex_share_password,
        workspace_id=workspace_id,
        folder_id=folder_id,
    )


    content_list_saved = False
    if content_list is not None and content_list.strip():
        from services.extract.content_list_markdown import content_list_to_markdown
        from services.extract.content_list_persist import (
            parse_content_list_form_json,
            persist_external_content_list,
        )

        try:
            items = parse_content_list_form_json(content_list.strip())
        except ValueError as exc:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc
        persist_external_content_list(file_record.id, items)
        content_list_saved = True
        if markdown is None or not markdown.strip():
            markdown = content_list_to_markdown(items)

    markdown_saved = False
    if markdown is not None and markdown.strip():
        persist_external_markdown_for_file(
            db,
            file_record,
            markdown.strip(),
            current_user,
            file.filename,
            allow_existing=not dedup,
        )
        markdown_saved = True
        from services.kb_index_service import enqueue_index, publish_index_job

        job_id = enqueue_index(db, current_user.id, file_record.id)
        db.commit()
        if job_id is not None:
            publish_index_job(db, current_user.id, file_record.id, job_id)

    username = current_user.username
    if dedup:
        uploader = db.query(User).filter(User.id == file_record.user_id).first()
        username = uploader.username if uploader else username

    if not markdown_saved:
        from services.extract.policy import needs_extract
        from services.kb_extract_service import enqueue_extract, publish_extract_job

        if needs_extract(file_record):
            job_id = enqueue_extract(db, current_user.id, file_record.id)
            db.commit()
            if job_id is not None:
                publish_extract_job(db, current_user.id, file_record.id, job_id)
            db.refresh(file_record)

    from services.knowledge_base_index_service import auto_sync_kb_index

    auto_sync_kb_index(db, current_user.id)

    return ExternalUploadWithMdResponse(
        file=file_to_schema(db, file_record, username, deduplicated=dedup, tags=[]),
        markdown_saved=markdown_saved,
    )


# ── 标签（API Key）────────────────────────────────────────────


@router.get("/tags", response_model=list[str])
def external_list_tags(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_api_key_user),
):
    """列出当前密钥所属用户的全部标签名。"""
    return list_user_tag_names(db, current_user.id)


@router.get("/files/{file_id}/tags", response_model=list[str])
def external_get_file_tags(
    file_id: int,
    workspace_id: int | None = Query(None),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_api_key_user),
):
    from routers.files import require_workspace_file

    f, _ws = require_workspace_file(db, file_id, current_user, workspace_id, need_write=False)
    return get_file_tag_names(db, f.id)


@router.put("/files/{file_id}/tags", response_model=list[str])
def external_merge_file_tags(
    file_id: int,
    body: FileTagsUpdateRequest,
    workspace_id: int | None = Query(None),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_api_key_user),
):
    """合并标签：在已有标签上追加请求中的标签（规范化、去重），不会移除已有标签。"""
    from routers.files import require_workspace_file

    f, _ws = require_workspace_file(db, file_id, current_user, workspace_id, need_write=True)
    tags = merge_file_tags(db, current_user.id, f.id, body.tags)
    db.commit()
    log_operation(
        db,
        current_user.id,
        "合并文件标签（API）",
        "file",
        file_id,
        f"文件 {f.original_name} 标签 API 合并",
    )
    return tags


# ── 请求体 Schema ────────────────────────────────────────────

class MdContentUploadRequest(BaseModel):
    """Markdown内容上传请求 API 路由辅助类型。

        Authors:
            徐泽宇

        Copyright:
            © 2026 徐泽宇

        Since:
            2026-06-03

        Attributes:
            md5_hash: MD5哈希（str）。
            content: 内容（str）。
            original_name: 原始名称（str | None）。
    """
    md5_hash: str
    content: str
    original_name: str | None = None


class MdContentPutByFileIdRequest(BaseModel):
    """Markdown内容putby文件ID请求 API 路由辅助类型。

        Authors:
            徐泽宇

        Copyright:
            © 2026 徐泽宇

        Since:
            2026-05-02

        Attributes:
            content: 内容（str）。
    """
    content: str


# ── 2.2 上传 Markdown 内容 ───────────────────────────────────

@router.post("/md-content")
def upload_md_content(
    body: MdContentUploadRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_api_key_user),
    x_filex_share_token: str | None = Header(None, alias="X-FileX-Share-Token"),
    x_filex_share_password: str | None = Header(None, alias="X-FileX-Share-Password"),
):
    """
    根据 MD5 摘要上传 Markdown 内容。
    更新数据库记录打上标记，保存 Markdown 文件到磁盘。
    保存笔记后会自动更新资料库索引 kb_index.md；亦可手动 POST /api/knowledge-base/rebuild。
    """
    validate_optional_share_context(
        db,
        x_filex_share_token,
        current_user,
        body.md5_hash,
        share_password=x_filex_share_password,
    )

    file_record = resolve_accessible_file_by_md5(
        db, current_user, body.md5_hash, need_write=True,
    )

    persist_external_markdown_for_file(
        db,
        file_record,
        body.content,
        current_user,
        body.original_name,
    )

    return {
        "message": "Markdown 内容保存成功",
        "md5_hash": body.md5_hash,
        "file_id": file_record.id,
    }


@router.put("/md-content")
def upsert_md_content(
    body: MdContentUploadRequest,
    workspace_id: int | None = Query(None),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_api_key_user),
    x_filex_share_token: str | None = Header(None, alias="X-FileX-Share-Token"),
    x_filex_share_password: str | None = Header(None, alias="X-FileX-Share-Password"),
):
    """
    根据 MD5 新建或更新 Markdown 笔记（Agent 润色后写回）。
    保存后会入队向量索引并同步 kb_index.md。
    """
    validate_optional_share_context(
        db,
        x_filex_share_token,
        current_user,
        body.md5_hash,
        share_password=x_filex_share_password,
    )

    file_record = resolve_accessible_file_by_md5(
        db,
        current_user,
        body.md5_hash,
        workspace_id=workspace_id,
        need_write=True,
    )
    return upsert_md_note_for_api(
        db,
        current_user,
        file_record,
        body.content,
        log_action="更新 Markdown 内容（API）",
    )


@router.put("/files/{file_id}/md")
def upsert_file_md_external(
    file_id: int,
    body: MdContentPutByFileIdRequest,
    workspace_id: int | None = Query(None),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_api_key_user),
):
    """按 file_id 新建或更新 Markdown 笔记（仅 API Key）。"""
    from routers.files import require_workspace_file

    f, _ws = require_workspace_file(
        db, file_id, current_user, workspace_id, need_write=True,
    )
    return upsert_md_note_for_api(
        db,
        current_user,
        f,
        body.content,
        log_action="更新 Markdown 笔记（API）",
    )


# ── 2.3 获取 Markdown 内容 ──────────────────────────────────

@router.get("/md-content/{md5_hash}")
def get_md_content(
    md5_hash: str,
    workspace_id: int | None = Query(None),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_api_key_user),
):
    """
    根据 MD5 摘要获取 Markdown 文件内容。
    """
    file_record = resolve_accessible_file_by_md5(
        db, current_user, md5_hash, workspace_id=workspace_id, need_write=False,
    )

    if not file_record.has_md or not file_record.md_file_path:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="该资料没有关联的 Markdown 内容")

    if not os.path.exists(file_record.md_file_path):
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Markdown 笔记已不存在")

    from services.okf_note_service import read_okf_body_for_file

    content = read_okf_body_for_file(file_record) or ""

    safe_filename = f"{md5_hash}.md"
    return Response(
        content=content,
        media_type="text/markdown; charset=utf-8",
        headers={"Content-Disposition": f'inline; filename="{safe_filename}"'},
    )
