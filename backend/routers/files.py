# Copyright (c) 2026 徐泽宇
"""files HTTP 路由模块。

Authors:
    徐泽宇
"""

import os
import shutil
import logging
from typing import Literal

from fastapi import APIRouter, Depends, HTTPException, UploadFile, File, Form, Query, Response, status
from fastapi.responses import FileResponse, PlainTextResponse
from pydantic import BaseModel
from sqlalchemy import func as sa_func, text
from sqlalchemy.exc import OperationalError
from sqlalchemy.orm import Session, aliased

from config import AGENT_ENUMERATE_MAX_FILES, AGENT_FILES_PAGE_SIZE_MAX, API_KEY_PREFIX, UPLOAD_DIR
from database import get_db
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from middleware.auth import get_current_user, get_file_stream_user, security
from models.user import User
from models.file import File as FileModel
from models.folder import Folder as FolderModel
from models.share_link import ShareLink
from models.tag import Tag, file_tags
from schemas.file import (
    FileResponse as FileSchema,
    FileUpdateRequest,
    FileListResponse,
    FileTagsUpdateRequest,
    FileStatsResponse,
)
from schemas.tag_graph import TagGraphResponse, TagHeatmapResponse
from services.system_setting_service import get_max_upload_bytes
from utils.agent_freshness import apply_agent_no_cache_headers
from services.file_service import (
    existing_thumbnail_path,
    get_extension,
    save_upload,
    thumbnail_media_type,
    validate_file,
    save_thumbnail,
)
from services.file_response import (
    batch_file_tag_anchors,
    batch_file_tags,
    batch_uploader_names,
    batch_wiki_links_stale,
    file_to_schema,
)
from services.log_service import log_operation
from services.tag_service import (
    build_user_tag_graph,
    build_user_tag_heatmap,
    get_file_tag_names,
    list_user_tag_names,
    normalize_tag_name,
    replace_file_tags,
)
from services.file_list_search import apply_file_search_filter
from services.file_stats_service import get_user_file_stats
from utils.timezone import to_beijing_time
from services.acl_service import (
    accessible_file_ids,
    apply_readable_files_filter,
    get_readable_file as acl_get_readable_file,
)
from constants.folder_errors import FOLDER_NOT_FOUND
from services.workspace_access_service import (
    batch_file_action_capabilities,
    can_write_file,
    get_file_in_workspace,
    require_workspace_member,
    resolve_workspace_id,
    uses_enterprise_rbac_for_workspace,
)
from services.workspace_service import ensure_personal_workspace

# ── Sub-routers (bridge pattern: main.py remains unchanged) ─────
from . import files_upload
from . import files_preview
from . import files_md
from . import files_okf
from . import files_pipeline_trace

logger = logging.getLogger(__name__)

router = APIRouter()
router.include_router(files_upload.router)
router.include_router(files_preview.router)
router.include_router(files_md.router)
router.include_router(files_okf.router)
router.include_router(files_pipeline_trace.router)
# ────────────────────────────────────────────────────────────────


def require_workspace_file(
    db: Session,
    file_id: int,
    user: User,
    workspace_id: int | None,
    *,
    ws_id: int | None = None,
    need_write: bool = False,
    need_manage: bool = False,
    write_forbidden_detail: str = "无权修改该资料",
    manage_forbidden_detail: str = "无权删除此资料",
) -> tuple[FileModel, int]:
    from models.enterprise_rbac import PERM_MANAGE, PERM_WRITE
    from services.permission_service import effective_file_permission, permission_at_least

    resolved_ws_id = ws_id if ws_id is not None else resolve_workspace_id(db, user, workspace_id)
    member = require_workspace_member(db, user, resolved_ws_id)
    allowed = accessible_file_ids(db, user, resolved_ws_id, member=member)
    f = get_file_in_workspace(db, file_id, resolved_ws_id)
    if not f or f.id not in allowed:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="资料不存在")
    if need_manage or need_write:
        if uses_enterprise_rbac_for_workspace(db, resolved_ws_id):
            minimum = PERM_MANAGE if need_manage else PERM_WRITE
            if not permission_at_least(effective_file_permission(db, user, f), minimum):
                detail = manage_forbidden_detail if need_manage else write_forbidden_detail
                raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=detail)
        elif need_write and not can_write_file(db, user, member, f):
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=write_forbidden_detail)
    return f, resolved_ws_id


def _get_owned_file(db: Session, file_id: int, user_id: int) -> FileModel | None:
    return db.query(FileModel).filter(FileModel.id == file_id, FileModel.user_id == user_id).first()


def _get_readable_file(db: Session, file_id: int, user: User) -> FileModel | None:
    """可读文件：本人、空间成员 ACL、或管理员。"""
    return acl_get_readable_file(db, user, file_id)


# ── Core File Routes (list / CRUD / tags / stats) ──────────────


@router.get("", response_model=FileListResponse)
def list_files(
    folder_id: int | None = Query(None),
    search: str | None = Query(
        None,
        description="按文件名模糊搜索；纯数字或 id: 前缀可按资料 ID 精确查找（id: 后须为有效资料 ID）",
    ),
    tag: str | None = Query(None, description="按标签筛选（精确匹配，忽略大小写）"),
    tag2: str | None = Query(
        None,
        description="与 tag 联用：仅返回同时带有 tag 与 tag2 的文件（AND）；须与 tag 同时传入",
    ),
    workspace_id: int | None = Query(None),
    sort_time: Literal["desc", "asc"] = Query(
        "desc",
        description="按最后更新时间（无则回退创建时间）排序：desc 新在前，asc 旧在前；sort_name 传入时被忽略",
    ),
    sort_name: Literal["desc", "asc"] | None = Query(
        None,
        description="按文件名（original_name，忽略大小写）排序：asc A→Z，desc Z→A；传入时优先于 sort_time",
    ),
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    enumerate: bool = Query(
        False,
        description="为 true 且 Bearer 为 API Key 时，单页返回当前筛选下全部资料（上限 AGENT_ENUMERATE_MAX_FILES）",
    ),
    include_wiki_stale: bool = Query(False),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
    credentials: HTTPAuthorizationCredentials = Depends(security),
):
    ws_id = resolve_workspace_id(db, current_user, workspace_id)
    token = (credentials.credentials or "").strip()
    is_api_key = token.startswith(API_KEY_PREFIX)
    if enumerate and not is_api_key:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="enumerate 仅支持 API Key（fb_ 前缀）鉴权",
        )
    page_size_cap = AGENT_FILES_PAGE_SIZE_MAX if is_api_key else 100
    if page_size > page_size_cap:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"page_size 不能超过 {page_size_cap}",
        )
    member = require_workspace_member(db, current_user, ws_id)
    query = db.query(FileModel).filter(FileModel.workspace_id == ws_id)
    query = apply_readable_files_filter(query, db, current_user, ws_id, member=member)
    if not db.query(query.exists()).scalar():
        return FileListResponse(items=[], total=0, page=page, page_size=page_size)

    from services.wiki_page_filters import source_files_only

    query = source_files_only(query)

    if folder_id is not None:
        if folder_id == 0:
            query = query.filter(FileModel.folder_id.is_(None))
        else:
            folder = (
                db.query(FolderModel)
                .filter(FolderModel.id == folder_id, FolderModel.workspace_id == ws_id)
                .first()
            )
            if not folder:
                raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=FOLDER_NOT_FOUND)
            query = query.filter(FileModel.folder_id == folder_id)
    if search:
        query = apply_file_search_filter(query, search)
    if tag2 is not None and not tag:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="使用 tag2 时必须同时提供 tag",
        )
    if tag:
        tn = normalize_tag_name(tag)
        if tn:
            if tag2 is not None:
                tn2 = normalize_tag_name(tag2)
                if not tn2:
                    return FileListResponse(items=[], total=0, page=page, page_size=page_size)
                trow1 = db.query(Tag).filter(Tag.workspace_id == ws_id, Tag.name == tn).first()
                trow2 = db.query(Tag).filter(Tag.workspace_id == ws_id, Tag.name == tn2).first()
                if not trow1 or not trow2:
                    return FileListResponse(items=[], total=0, page=page, page_size=page_size)
                if trow1.id == trow2.id:
                    query = query.join(file_tags, FileModel.id == file_tags.c.file_id).filter(
                        file_tags.c.tag_id == trow1.id
                    )
                else:
                    ft_a = aliased(file_tags)
                    ft_b = aliased(file_tags)
                    query = (
                        query.join(ft_a, FileModel.id == ft_a.c.file_id)
                        .filter(ft_a.c.tag_id == trow1.id)
                        .join(ft_b, (FileModel.id == ft_b.c.file_id) & (ft_b.c.tag_id == trow2.id))
                    )
            else:
                trow = db.query(Tag).filter(Tag.workspace_id == ws_id, Tag.name == tn).first()
                if not trow:
                    return FileListResponse(items=[], total=0, page=page, page_size=page_size)
                query = query.join(file_tags, FileModel.id == file_tags.c.file_id).filter(
                    file_tags.c.tag_id == trow.id
                )

    total = query.count()
    if sort_name is not None:
        name_key = sa_func.lower(FileModel.original_name)
        if sort_name == "desc":
            order_clause = (name_key.desc(), FileModel.id.desc())
        else:
            order_clause = (name_key.asc(), FileModel.id.asc())
    else:
        sort_key = sa_func.coalesce(FileModel.updated_at, FileModel.created_at)
        order_clause = (sort_key.desc() if sort_time == "desc" else sort_key.asc(),)
    enumerate_truncated = None
    effective_page = page
    effective_page_size = page_size
    if enumerate:
        effective_page = 1
        effective_page_size = min(total, AGENT_ENUMERATE_MAX_FILES) if total > 0 else page_size
        if total > AGENT_ENUMERATE_MAX_FILES:
            enumerate_truncated = True
    items = (
        query.order_by(*order_clause)
        .offset((effective_page - 1) * effective_page_size)
        .limit(effective_page_size)
        .all()
    )

    ids = [f.id for f in items]
    stale_map: dict[int, bool] = {}
    if include_wiki_stale and ids:
        stale_map = batch_wiki_links_stale(db, ids)

    tag_map = batch_file_tags(db, ids)
    anchor_map = batch_file_tag_anchors(db, ids)
    uploader_map = batch_uploader_names(db, [f.user_id for f in items])
    cap_map = batch_file_action_capabilities(
        db, current_user, items, workspace_id=ws_id, member=member
    )
    result = []
    for f in items:
        cw, cm = cap_map.get(f.id, (False, False))
        result.append(
            file_to_schema(
                db,
                f,
                uploader_map.get(f.user_id),
                user=current_user,
                tags=tag_map.get(f.id, []),
                tag_anchors=anchor_map.get(f.id, []),
                wiki_links_stale=stale_map.get(f.id) if include_wiki_stale else None,
                can_write=cw,
                can_manage=cm,
            )
        )

    return FileListResponse(
        items=result,
        total=total,
        page=effective_page,
        page_size=effective_page_size,
        enumerate_truncated=enumerate_truncated,
    )


@router.get("/tags", response_model=list[str])
def list_my_tag_names(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """当前用户已使用的全部标签名（去重排序），供筛选与编辑联想。"""
    return list_user_tag_names(db, current_user.id)


@router.get("/tags/graph", response_model=TagGraphResponse)
def get_my_tag_graph(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """标签关系网络。"""
    data = build_user_tag_graph(db, current_user.id)
    return TagGraphResponse(**data)


@router.get("/tags/heatmap", response_model=TagHeatmapResponse)
def get_my_tag_heatmap(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """标签共现矩阵（热力图）。"""
    data = build_user_tag_heatmap(db, current_user.id)
    return TagHeatmapResponse(**data)


@router.get("/stats", response_model=FileStatsResponse)
def file_stats(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    return get_user_file_stats(db, current_user.id)


@router.get("/{file_id}/tags", response_model=list[str])
def get_file_tags(
    file_id: int,
    workspace_id: int | None = Query(None),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """获取文件已有的标签列表。"""
    f, _ws = require_workspace_file(db, file_id, current_user, workspace_id)
    return get_file_tag_names(db, f.id)


@router.put("/{file_id}/tags", response_model=list[str])
def replace_tags(
    file_id: int,
    body: FileTagsUpdateRequest,
    workspace_id: int | None = Query(None),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """替换文件的全部标签（整表替换）。"""
    f, _ws = require_workspace_file(db, file_id, current_user, workspace_id, need_write=True)
    tags = replace_file_tags(db, current_user.id, f.id, body.tags)
    log_operation(db, current_user.id, "更新标签", "file", file_id, f"更新文件 {f.original_name} 的标签: {', '.join(body.tags)}")
    return tags


@router.get("/{file_id}", response_model=FileSchema)
def get_file(
    file_id: int,
    response: Response,
    workspace_id: int | None = Query(None),
    include_wiki_stale: bool = Query(False),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    apply_agent_no_cache_headers(response)
    ws_id = resolve_workspace_id(db, current_user, workspace_id)
    f = get_file_in_workspace(db, file_id, ws_id)
    if not f:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="资料不存在")
    member = require_workspace_member(db, current_user, ws_id)
    allowed = accessible_file_ids(db, current_user, ws_id, member=member)
    if f.id not in allowed:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="资料不存在")
    tags = get_file_tag_names(db, f.id)
    stale = None
    if include_wiki_stale:
        from services.md_wiki_link_service import wiki_links_stale_for_file

        stale = wiki_links_stale_for_file(db, f.id)
    return file_to_schema(
        db, f, current_user.username, user=current_user, tags=tags, wiki_links_stale=stale
    )


@router.put("/{file_id}")
def update_file(
    file_id: int,
    body: FileUpdateRequest,
    workspace_id: int | None = Query(None),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    f, _ws = require_workspace_file(db, file_id, current_user, workspace_id, need_write=True)
    rbac_on = uses_enterprise_rbac_for_workspace(db, _ws)

    if body.filename is not None:
        f.original_name = body.filename
    folder_id_changed = False
    if "folder_id" in body.model_dump(exclude_unset=True):
        from models.enterprise_rbac import PERM_WRITE
        from services.permission_service import effective_file_permission, effective_folder_permission, permission_at_least

        old_folder_id = f.folder_id
        if rbac_on:
            if not permission_at_least(effective_file_permission(db, current_user, f), PERM_WRITE):
                raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="无权移动该资料")
            if not permission_at_least(
                effective_folder_permission(db, current_user, _ws, body.folder_id),
                PERM_WRITE,
            ):
                raise HTTPException(
                    status_code=status.HTTP_403_FORBIDDEN,
                    detail="无权移动到目标目录",
                )
        elif f.user_id != current_user.id:
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="只能移动自己的资料")

        if body.folder_id is not None:
            folder = (
                db.query(FolderModel)
                .filter(FolderModel.id == body.folder_id, FolderModel.workspace_id == _ws)
                .first()
            )
            if not folder:
                raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=FOLDER_NOT_FOUND)
            f.folder_id = body.folder_id
        else:
            f.folder_id = None
        folder_id_changed = old_folder_id != f.folder_id

    if folder_id_changed:
        from services.okf_note_service import maybe_relocate_okf_sidecar_on_folder_change

        maybe_relocate_okf_sidecar_on_folder_change(
            db, f, new_folder_id=f.folder_id, previous_folder_id=old_folder_id
        )

    db.commit()
    db.refresh(f)
    log_operation(db, current_user.id, "更新文件", "file", file_id, f"更新文件 {f.original_name}")
    return file_to_schema(db, f, current_user.username, user=current_user)


def _terminate_association_connections(db: Session, worker_id: str) -> int:
    """Terminate all PG connections matching the given worker_id.

    Returns the number of backend processes terminated.
    """
    rows = db.execute(
        text(
            "SELECT pid FROM pg_stat_activity "
            "WHERE application_name LIKE :name AND pid <> pg_backend_pid()"
        ),
        {"name": f"%{worker_id}%"},
    ).fetchall()
    terminated = 0
    for (pid,) in rows:
        try:
            db.execute(text("SELECT pg_terminate_backend(:pid)"), {"pid": pid})
            terminated += 1
        except Exception:
            pass
    if terminated:
        logger.info("killed %d pg backends for association worker_id=%s", terminated, worker_id)
    return terminated


@router.delete("/{file_id}")
def delete_file(
    file_id: int,
    workspace_id: int | None = Query(None),
    defer_kb_index_sync: bool = Query(False),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    ws_id = resolve_workspace_id(db, current_user, workspace_id)
    rbac_on = uses_enterprise_rbac_for_workspace(db, ws_id)
    f, _ws = require_workspace_file(
        db,
        file_id,
        current_user,
        workspace_id,
        ws_id=ws_id,
        need_manage=rbac_on,
        need_write=not rbac_on,
    )
    if not rbac_on and current_user.id != f.user_id and not current_user.is_admin:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="无权删除此资料")

    from services.kb_index_service import (
        abort_kb_index_jobs_for_file_delete,
        delete_chunks_for_file,
        purge_kb_index_mq_for_jobs,
    )
    from services.kb_extract_service import (
        abort_kb_extract_jobs_for_file_delete,
        purge_gpu_route_mq_for_jobs,
        purge_kb_extract_mq_for_jobs,
    )
    from services.kb_post_service import abort_kb_post_jobs_for_file_delete, purge_kb_post_mq_for_jobs
    from services.kb_association_job_service import abort_kb_association_jobs_for_file_delete
    from models.kb_association_job import KbAssociationJob

    cancelled_index_ids = abort_kb_index_jobs_for_file_delete(db, file_id)
    cancelled_extract_ids = abort_kb_extract_jobs_for_file_delete(db, file_id)
    cancelled_post_ids = abort_kb_post_jobs_for_file_delete(db, file_id)

    # 在 abort 之前先获取 running 关联作业的 worker_id，
    # 以便 commit 后 terminate 其 PG 连接释放 FOR KEY SHARE 锁
    running_assoc_worker = (
        db.query(KbAssociationJob.worker_id)
        .filter(
            KbAssociationJob.file_id == file_id,
            KbAssociationJob.status == "running",
        )
        .scalar()
    )
    abort_kb_association_jobs_for_file_delete(db, file_id)
    db.commit()

    if running_assoc_worker:
        _terminate_association_connections(db, running_assoc_worker)

    purge_kb_index_mq_for_jobs(cancelled_index_ids)
    purge_kb_extract_mq_for_jobs(cancelled_extract_ids)
    purge_kb_post_mq_for_jobs(cancelled_post_ids)

    # GPU routes have no FK cascade; constrain cleanup by both file and task.
    from models.gpu_scheduler import GpuSchedulerOutbox

    purge_gpu_route_mq_for_jobs(
        file_id=file_id,
        mineru_job_ids=cancelled_extract_ids,
        raptor_job_ids=cancelled_post_ids,
    )
    if cancelled_extract_ids or cancelled_post_ids:
        gpu_routes = db.query(GpuSchedulerOutbox).filter(
            GpuSchedulerOutbox.file_id == file_id,
            (
                (GpuSchedulerOutbox.job_kind == "mineru")
                & GpuSchedulerOutbox.job_id.in_({str(job_id) for job_id in cancelled_extract_ids})
            )
            | (
                (GpuSchedulerOutbox.job_kind == "raptor")
                & GpuSchedulerOutbox.job_id.in_({str(job_id) for job_id in cancelled_post_ids})
            ),
        )
        gpu_routes.delete(synchronize_session=False)
        db.commit()

    from services.office_normalize_service import remove_normalized_file
    from services.office_preview_pdf_service import remove_preview_pdf

    remove_normalized_file(f)
    remove_preview_pdf(f)

    if f.file_path and os.path.exists(f.file_path):
        os.remove(f.file_path)
    tp = existing_thumbnail_path(f.file_path)
    if tp and os.path.isfile(tp):
        os.remove(tp)

    db.query(ShareLink).filter(ShareLink.file_id == file_id).delete()
    db.query(file_tags).filter(file_tags.c.file_id == file_id).delete()

    if f.has_md and f.md_file_path:
        from services.okf_note_service import remove_concept_sidecar_from_disk

        remove_concept_sidecar_from_disk(f)

    # 清理内容提取产生的资产目录（.extract_assets/{file_id} 下存放的图片/表格等资源）
    from services.extract.content_list_persist import extract_assets_dir_for_file
    assets_dir = extract_assets_dir_for_file(f)
    if os.path.isdir(assets_dir):
        shutil.rmtree(assets_dir, ignore_errors=True)

    # 清理 content_list sidecar（即使 .md 已删除，也应清理结构化数据）
    from services.md_paths import content_list_json_path
    cl_path = content_list_json_path(file_id)
    if os.path.isfile(cl_path):
        os.remove(cl_path)

    from services.md_tag_anchor_service import delete_anchors_for_file

    delete_anchors_for_file(db, file_id)

    try:
        db.execute(text("SET LOCAL lock_timeout = '20s'"))
        delete_chunks_for_file(db, file_id)
    except OperationalError as exc:
        msg = str(exc).lower()
        if "lock timeout" in msg or "canceling statement" in msg:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="资料正在被索引，请稍后重试",
            ) from exc
        raise

    from services.md_wiki_link_service import delete_wiki_links_for_file

    delete_wiki_links_for_file(db, file_id)
    owner_id = f.user_id
    db.delete(f)
    db.commit()
    from services.knowledge_base_index_service import auto_sync_kb_index

    if not defer_kb_index_sync:
        auto_sync_kb_index(db, owner_id)
    log_operation(db, current_user.id, "删除文件", "file", file_id, f"删除文件 {f.original_name}")
    return {"message": "资料已删除"}
