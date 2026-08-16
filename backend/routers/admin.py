# Copyright (c) 2026 徐泽宇
"""admin HTTP 路由模块。

Authors:
    徐泽宇
"""

from typing import Literal

from fastapi import APIRouter, Depends, HTTPException, Response, status, Query
import httpx
from sqlalchemy import func as sa_func
from sqlalchemy.orm import Session

from database import get_db
from middleware.auth import get_admin_user
from models.user import User
from models.file import File as FileModel
from models.folder import Folder as FolderModel
from models.operation_log import OperationLog
from schemas.file import FileListResponse
from schemas.admin_kb import AdminKbReindexAllRequest, AdminKbReindexAllResponse
from schemas.wiki import AdminWikiLintBody, AdminWikiRebuildBody, WikiLintResponse
from schemas.system_setting import SystemSettingsResponse, SystemSettingsUpdate
from schemas.mq_status import MqStatusResponse, MqQueuedJobsResponse, MqQueuedJobsResponse
from schemas.mq_queue_messages import (
    MqQueueMessageDeleteRequest,
    MqQueueMessageDedupeResponse,
    MqQueueMessageDeleteResponse,
    MqQueueMessagesResponse,
)
from schemas.kb_ws_notify_metrics import KbWsNotifyMetricsResponse
from schemas.operation_log import OperationLogDeleteRequest, OperationLogDeleteResponse
from messaging.ws_manager import kb_index_ws_manager
from services.system_setting_service import get_public_settings_dict, update_settings
from services.system_setting_service import (
    KEY_KB_EXTRACT_INSAVLO_API_KEY,
    KEY_KB_EXTRACT_INSAVLO_WEBHOOK_SECRET,
    KEY_KB_POST_LLM_API_KEY,
    KEY_KB_RAGAS_LLM_API_KEY,
    KEY_OLLAMA_API_KEY,
    invalidate_all_settings_caches,
)
from models.system_setting import SystemSetting
from services.rabbitmq_status_service import (
    get_mq_status,
    list_kb_extract_queued_jobs,
    list_kb_index_queued_jobs,
    list_kb_post_queued_jobs,
)
from services.rabbitmq_queue_admin_service import (
    mq_queue_admin_unavailable_error,
    dedupe_queue_messages,
    mutate_queue_messages,
    peek_queue_messages,
)
from services.file_response import batch_file_tag_anchors, batch_file_tags, file_to_schema
from services.file_list_search import apply_file_search_filter
from services.log_service import delete_all_operation_logs, delete_operation_logs_by_ids, log_operation
from utils.timezone import to_beijing_time
from fastapi.responses import PlainTextResponse
from models.kb_search_audit_log import KbSearchAuditLog
from models.file_md_version import FileMdVersion
from schemas.workspace import FileMdVersionResponse, FilePublishStatusRequest, MdVersionRestoreRequest
from services.md_note_service import restore_md_note_version
from services.okf_note_service import read_okf_body_plaintext_or_raise
from utils.agent_freshness import apply_agent_no_cache_headers
from services.kb_reindex_all_service import enqueue_reindex_all_files

from . import (
    admin_departments,
    admin_enterprise_roles,
    admin_groups,
    admin_kb_eval,
    admin_kb_pipeline,
    admin_users,
)

router = APIRouter()
router.include_router(admin_users.router)
router.include_router(admin_departments.router, prefix="/departments", tags=["RBAC"])
router.include_router(admin_groups.router, prefix="/groups", tags=["RBAC"])
router.include_router(admin_enterprise_roles.router, prefix="/enterprise-roles", tags=["RBAC"])
router.include_router(admin_kb_pipeline.router)
router.include_router(admin_kb_eval.router)


def _settings_update_payload(body: SystemSettingsUpdate) -> dict[str, str]:
    out: dict[str, str] = {}
    for key, value in body.model_dump(exclude_none=True).items():
        if key in {
            "clear_insavlo_api_key",
            "clear_insavlo_webhook_secret",
            "clear_ollama_api_key",
            "clear_kb_post_llm_api_key",
            "clear_kb_ragas_llm_api_key",
        }:
            continue
        if isinstance(value, bool):
            out[key] = "true" if value else "false"
        else:
            out[key] = str(value)
    return out


def _clear_insavlo_secret_settings(db: Session, body: SystemSettingsUpdate) -> None:
    keys: list[str] = []
    if body.clear_insavlo_api_key:
        keys.append(KEY_KB_EXTRACT_INSAVLO_API_KEY)
    if body.clear_insavlo_webhook_secret:
        keys.append(KEY_KB_EXTRACT_INSAVLO_WEBHOOK_SECRET)
    if body.clear_ollama_api_key:
        keys.append(KEY_OLLAMA_API_KEY)
    if body.clear_kb_post_llm_api_key:
        keys.append(KEY_KB_POST_LLM_API_KEY)
    if body.clear_kb_ragas_llm_api_key:
        keys.append(KEY_KB_RAGAS_LLM_API_KEY)
    for key in keys:
        row = db.query(SystemSetting).filter(SystemSetting.setting_key == key).first()
        if row is None:
            db.add(SystemSetting(setting_key=key, value=""))
        else:
            row.value = ""


# ── Logs ────────────────────────────────────────────────────────


@router.get("/logs")
def list_logs(
    page: int = Query(1, ge=1),
    page_size: int = Query(50, ge=1, le=200),
    user_id: int | None = Query(None, description="按操作者用户筛选"),
    detail_contains: str | None = Query(None, description="detail 子串筛选（如 ocr_engine=rapidocr）"),
    db: Session = Depends(get_db),
    admin: User = Depends(get_admin_user),
):
    base = db.query(OperationLog)
    if user_id is not None:
        base = base.filter(OperationLog.user_id == user_id)
    if detail_contains:
        base = base.filter(OperationLog.detail.contains(detail_contains))
    total = base.count()
    row_query = (
        db.query(OperationLog, User.username)
        .outerjoin(User, OperationLog.user_id == User.id)
    )
    if user_id is not None:
        row_query = row_query.filter(OperationLog.user_id == user_id)
    if detail_contains:
        row_query = row_query.filter(OperationLog.detail.contains(detail_contains))
    rows = (
        row_query.order_by(OperationLog.id.desc())
        .offset((page - 1) * page_size)
        .limit(page_size)
        .all()
    )
    return {
        "total": total,
        "page": page,
        "page_size": page_size,
        "items": [
            {
                "id": log.id,
                "user_id": log.user_id,
                "username": username or "",
                "action": log.action,
                "target_type": log.target_type,
                "target_id": log.target_id,
                "detail": log.detail,
                "created_at": to_beijing_time(log.created_at).isoformat() if log.created_at else "",
            }
            for log, username in rows
        ],
    }


@router.delete("/logs/{log_id}", response_model=OperationLogDeleteResponse)
def delete_log(
    log_id: int,
    db: Session = Depends(get_db),
    admin: User = Depends(get_admin_user),
):
    row = db.query(OperationLog).filter(OperationLog.id == log_id).first()
    if not row:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="日志不存在")
    db.delete(row)
    db.commit()
    log_operation(db, admin.id, "删除操作日志", "operation_log", log_id, "单条删除")
    return OperationLogDeleteResponse(deleted=1)


@router.post("/logs/delete", response_model=OperationLogDeleteResponse)
def batch_delete_logs(
    body: OperationLogDeleteRequest,
    db: Session = Depends(get_db),
    admin: User = Depends(get_admin_user),
):
    unique_ids = list(dict.fromkeys(body.ids))
    deleted = delete_operation_logs_by_ids(db, unique_ids, commit=False)
    log_operation(
        db,
        admin.id,
        "删除操作日志",
        "operation_log",
        0,
        f"批量删除 {deleted} 条",
    )
    return OperationLogDeleteResponse(deleted=deleted)


@router.post("/logs/purge", response_model=OperationLogDeleteResponse)
def purge_logs(
    user_id: int | None = Query(None, description="仅清空指定用户的操作日志"),
    db: Session = Depends(get_db),
    admin: User = Depends(get_admin_user),
):
    if user_id is not None and db.query(User).filter(User.id == user_id).first() is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="用户不存在")
    deleted = delete_all_operation_logs(db, user_id=user_id, commit=False)
    if user_id is not None:
        actor = db.query(User).filter(User.id == user_id).first()
        detail = f"清空用户 {actor.username if actor else user_id} 的 {deleted} 条"
    else:
        detail = f"清空 {deleted} 条"
    log_operation(
        db,
        admin.id,
        "清空操作日志",
        "operation_log",
        user_id or 0,
        detail,
    )
    return OperationLogDeleteResponse(deleted=deleted)


# ── Files ───────────────────────────────────────────────────────


@router.get("/files", response_model=FileListResponse)
def admin_list_all_files(
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    user_id: int | None = Query(None, description="按上传用户筛选"),
    workspace_id: int | None = Query(None, description="按知识空间筛选"),
    folder_id: int | None = Query(None, description="0 表示未分类目录"),
    search: str | None = Query(
        None,
        description="按文件名模糊搜索；纯数字或 id: 前缀可按资料 ID 精确查找（id: 后须为有效资料 ID）",
    ),
    sort_time: Literal["desc", "asc"] = Query(
        "desc",
        description="按最后更新时间（无则回退创建时间）排序",
    ),
    db: Session = Depends(get_db),
    admin: User = Depends(get_admin_user),
):
    query = db.query(FileModel)
    if user_id is not None:
        query = query.filter(FileModel.user_id == user_id)
    if workspace_id is not None:
        query = query.filter(FileModel.workspace_id == workspace_id)
    if folder_id is not None:
        if folder_id == 0:
            query = query.filter(FileModel.folder_id.is_(None))
        else:
            query = query.filter(FileModel.folder_id == folder_id)
    if search:
        query = apply_file_search_filter(query, search)

    total = query.count()
    sort_key = sa_func.coalesce(FileModel.updated_at, FileModel.created_at)
    order_clause = sort_key.desc() if sort_time == "desc" else sort_key.asc()
    items = (
        query.order_by(order_clause)
        .offset((page - 1) * page_size)
        .limit(page_size)
        .all()
    )
    ids = [f.id for f in items]
    tag_map = batch_file_tags(db, ids)
    anchor_map = batch_file_tag_anchors(db, ids)
    result = []
    for f in items:
        uploader = db.query(User).filter(User.id == f.user_id).first()
        result.append(
            file_to_schema(
                db,
                f,
                uploader.username if uploader else None,
                tags=tag_map.get(f.id, []),
                tag_anchors=anchor_map.get(f.id, []),
            )
        )
    return FileListResponse(items=result, total=total, page=page, page_size=page_size)


# ── MQ ──────────────────────────────────────────────────────────


@router.get("/mq-status", response_model=MqStatusResponse)
def admin_get_mq_status(
    db: Session = Depends(get_db),
    admin: User = Depends(get_admin_user),
):
    return get_mq_status()


@router.get(
    "/kb-ws-notify-metrics",
    response_model=KbWsNotifyMetricsResponse,
    response_model_by_alias=True,
)
def admin_get_kb_ws_notify_metrics(
    admin: User = Depends(get_admin_user),
):
    return KbWsNotifyMetricsResponse(**kb_index_ws_manager.get_kb_ws_notify_metrics())


@router.get("/mq/queued-jobs", response_model=MqQueuedJobsResponse)
def admin_list_mq_queued_jobs(
    limit: int = Query(50, ge=1, le=100),
    db: Session = Depends(get_db),
    admin: User = Depends(get_admin_user),
):
    return list_kb_index_queued_jobs(db, limit=limit)


@router.get("/mq/extract-queued-jobs", response_model=MqQueuedJobsResponse)
def admin_list_mq_extract_queued_jobs(
    limit: int = Query(50, ge=1, le=100),
    db: Session = Depends(get_db),
    admin: User = Depends(get_admin_user),
):
    return list_kb_extract_queued_jobs(db, limit=limit)


@router.get("/mq/post-queued-jobs", response_model=MqQueuedJobsResponse)
def admin_list_mq_post_queued_jobs(
    limit: int = Query(50, ge=1, le=100),
    db: Session = Depends(get_db),
    admin: User = Depends(get_admin_user),
):
    return list_kb_post_queued_jobs(db, limit=limit)


@router.get("/mq/queues/{queue_name}/messages", response_model=MqQueueMessagesResponse)
def admin_peek_mq_queue_messages(
    queue_name: str,
    limit: int = Query(10, ge=1, le=100),
    db: Session = Depends(get_db),
    admin: User = Depends(get_admin_user),
):
    try:
        return peek_queue_messages(queue_name, limit=limit)
    except RuntimeError as exc:
        if "unavailable" in str(exc):
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail=str(exc),
            ) from exc
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc




@router.post("/mq/queues/{queue_name}/messages/dedupe", response_model=MqQueueMessageDedupeResponse)
def admin_dedupe_mq_queue_messages(
    queue_name: str,
    db: Session = Depends(get_db),
    admin: User = Depends(get_admin_user),
):
    try:
        return dedupe_queue_messages(queue_name)
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc
    except RuntimeError as exc:
        if "unavailable" in str(exc):
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail=str(exc),
            ) from exc
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc

@router.post("/mq/queues/{queue_name}/messages/delete", response_model=MqQueueMessageDeleteResponse)
def admin_delete_mq_queue_messages(
    queue_name: str,
    body: MqQueueMessageDeleteRequest,
    db: Session = Depends(get_db),
    admin: User = Depends(get_admin_user),
):
    try:
        return mutate_queue_messages(
            queue_name,
            purge=body.purge,
            job_id=body.job_id,
            index=body.index,
        )
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc
    except RuntimeError as exc:
        if "unavailable" in str(exc):
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail=str(exc),
            ) from exc
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc


# ── System Settings ─────────────────────────────────────────────


@router.get("/system-settings", response_model=SystemSettingsResponse)
def admin_get_system_settings(
    db: Session = Depends(get_db),
    admin: User = Depends(get_admin_user),
):
    from services.kb_pipeline_service import builtin_pipeline_routes

    return {**get_public_settings_dict(db), "builtin_routes": builtin_pipeline_routes()}


@router.put("/system-settings", response_model=SystemSettingsResponse)
def admin_put_system_settings(
    body: SystemSettingsUpdate,
    db: Session = Depends(get_db),
    admin: User = Depends(get_admin_user),
):
    from services.mineru_config_service import collect_mineru_settings_warnings

    try:
        with db.begin_nested():
            _clear_insavlo_secret_settings(db, body)
            update_settings(db, _settings_update_payload(body), commit=False)
        db.commit()
        invalidate_all_settings_caches(broadcast=True)
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc
    safe_body = body.model_dump(exclude_none=True)
    safe_body.pop("kb_extract_insavlo_api_key", None)
    safe_body.pop("kb_extract_insavlo_webhook_secret", None)
    safe_body.pop("ollama_api_key", None)
    safe_body.pop("clear_ollama_api_key", None)
    safe_body.pop("kb_post_llm_api_key", None)
    safe_body.pop("clear_kb_post_llm_api_key", None)
    safe_body.pop("kb_ragas_llm_api_key", None)
    safe_body.pop("clear_kb_ragas_llm_api_key", None)
    log_operation(db, admin.id, "更新系统设置", "settings", 0, str(safe_body))
    result = get_public_settings_dict(db)
    warnings = collect_mineru_settings_warnings(result)
    from services.kb_pipeline_service import builtin_pipeline_routes

    return {**result, "builtin_routes": builtin_pipeline_routes(), "warnings": warnings}


@router.post("/system-settings/test-insavlo")
def admin_test_insavlo_settings(
    db: Session = Depends(get_db),
    admin: User = Depends(get_admin_user),
):
    from services.insavlo_config_service import validate_insavlo_settings

    errors = validate_insavlo_settings(db)
    ready = not errors
    return {
        "ok": ready,
        "ready": ready,
        "errors": errors,
        "message": (
            "Insavlo 配置格式已通过，真实连通性将在首次提取任务中验证。"
            if ready
            else "Insavlo 配置未完整，无法作为正文提取引擎使用。"
        ),
    }


@router.post("/system-settings/test-ollama")
def admin_test_ollama_settings(
    db: Session = Depends(get_db),
    admin: User = Depends(get_admin_user),
):
    from services.ollama_config_service import get_ollama_runtime_config, probe_ollama

    cfg = get_ollama_runtime_config(db, fresh=True)
    result = probe_ollama(cfg)
    return result


@router.get("/mineru-version")
def admin_get_mineru_version(
    admin: User = Depends(get_admin_user),
):
    """返回 MinerU sidecar 当前报告的 mineru 库运行时版本（纯中继）。"""
    from config import KB_EXTRACT_MINERU_URL

    url = (KB_EXTRACT_MINERU_URL or "").strip().rstrip("/")
    if not url:
        return {"mineru_version": None, "sidecar_version": None, "error": "KB_EXTRACT_MINERU_URL 未配置"}

    health_url = f"{url}/health"
    try:
        # The sidecar URL is an internal Compose-network address.  Do not let
        # host proxy variables (HTTP_PROXY/HTTPS_PROXY) route it externally;
        # local development otherwise returns 502 before reaching filex-mineru.
        with httpx.Client(timeout=2.0, trust_env=False) as client:
            resp = client.get(health_url)
            if resp.status_code == 200:
                data = resp.json()
                # 只中继，不改写
                return {
                    "mineru_version": data.get("mineru_version"),
                    "sidecar_version": data.get("sidecar_version"),
                }
            else:
                return {
                    "mineru_version": None,
                    "sidecar_version": None,
                    "error": f"sidecar 返回 {resp.status_code}",
                }
    except Exception as exc:
        return {
            "mineru_version": None,
            "sidecar_version": None,
            "error": str(exc),
        }


# ── Audit / MD / KB ─────────────────────────────────────────────


@router.get("/audit/search-export")
def export_search_audit(
    workspace_id: int | None = Query(None),
    limit: int = Query(1000, ge=1, le=5000),
    db: Session = Depends(get_db),
    admin: User = Depends(get_admin_user),
):
    q = db.query(KbSearchAuditLog, User.username).join(User, User.id == KbSearchAuditLog.user_id)
    if workspace_id is not None:
        q = q.filter(KbSearchAuditLog.workspace_id == workspace_id)
    rows = q.order_by(KbSearchAuditLog.id.desc()).limit(limit).all()
    lines = ["id\tuser\tworkspace_id\tquery\thits\ttop_k\tcreated_at"]
    for log, uname in rows:
        q = (log.query or "").replace("\t", " ")
        hits = (log.hit_file_ids or "").replace("\t", " ")
        lines.append(f"{log.id}\t{uname}\t{log.workspace_id}\t{q}\t{hits}\t{log.top_k}\t{log.created_at}")
    return PlainTextResponse("\n".join(lines), media_type="text/plain; charset=utf-8")


@router.get(
    "/files/{file_id}/md",
    response_class=PlainTextResponse,
    summary="管理员读取任意资料的 Markdown 笔记",
    description="按 file_id 读取 sidecar 笔记，不依赖 workspace_id。须管理员权限（JWT 或 API Key）。",
)
def admin_get_file_md(
    file_id: int,
    response: Response,
    db: Session = Depends(get_db),
    admin: User = Depends(get_admin_user),
):
    apply_agent_no_cache_headers(response)
    f = db.query(FileModel).filter(FileModel.id == file_id).first()
    if not f:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="资料不存在")
    content = read_okf_body_plaintext_or_raise(f)
    log_operation(
        db,
        admin.id,
        "管理员查看 Markdown 笔记",
        "file",
        file_id,
        f"查看 {f.original_name} 的资料笔记",
    )
    return PlainTextResponse(content, media_type="text/markdown; charset=utf-8")


@router.get("/files/{file_id}/md/versions", response_model=list[FileMdVersionResponse])
def admin_list_md_versions(
    file_id: int,
    db: Session = Depends(get_db),
    _admin: User = Depends(get_admin_user),
):
    f = db.query(FileModel).filter(FileModel.id == file_id).first()
    if not f:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="资料不存在")
    rows = (
        db.query(FileMdVersion)
        .filter(FileMdVersion.file_id == file_id)
        .order_by(FileMdVersion.version.desc())
        .limit(50)
        .all()
    )
    return [
        FileMdVersionResponse(
            id=r.id,
            file_id=r.file_id,
            version=r.version,
            content=r.content,
            created_by_user_id=r.created_by_user_id,
            created_at=to_beijing_time(r.created_at).isoformat() if r.created_at else "",
        )
        for r in rows
    ]


@router.post("/files/{file_id}/md/restore-version")
def admin_restore_md_version(
    file_id: int,
    body: MdVersionRestoreRequest,
    db: Session = Depends(get_db),
    admin: User = Depends(get_admin_user),
):
    f = db.query(FileModel).filter(FileModel.id == file_id).first()
    if not f:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="资料不存在")
    ver = (
        db.query(FileMdVersion)
        .filter(FileMdVersion.id == body.version_id, FileMdVersion.file_id == file_id)
        .first()
    )
    if not ver:
        raise HTTPException(status_code=404, detail="版本不存在")
    restore_md_note_version(db, admin.id, f, ver.content, enqueue_vector_index=True)
    db.commit()
    log_operation(db, admin.id, "管理员恢复笔记版本", "file", file_id, f"v{ver.version}")
    return {"file_id": file_id, "restored_version": ver.version}


@router.post("/kb/reindex-all", response_model=AdminKbReindexAllResponse)
def admin_reindex_all_kb(
    body: AdminKbReindexAllRequest | None = None,
    db: Session = Depends(get_db),
    admin: User = Depends(get_admin_user),
):
    req = body or AdminKbReindexAllRequest()
    result = enqueue_reindex_all_files(db, user_id=req.user_id, force=req.force)
    log_operation(
        db,
        admin.id,
        "管理员批量重建向量索引",
        "kb_index",
        0,
        f"candidate={result['candidate_count']} enqueued={result['enqueued_count']} force={req.force}",
    )
    db.commit()
    try:
        from messaging.mq_status_watcher import request_refresh

        request_refresh()
    except Exception:
        pass
    msg = f"已入队 {result['enqueued_count']} 个文件（共 {result['candidate_count']} 个可索引）"
    return AdminKbReindexAllResponse(
        candidate_count=result["candidate_count"],
        enqueued_count=result["enqueued_count"],
        message=msg,
    )


@router.put("/files/{file_id}/publish-status")
def admin_set_publish_status(
    file_id: int,
    body: FilePublishStatusRequest,
    db: Session = Depends(get_db),
    admin: User = Depends(get_admin_user),
):
    f = db.query(FileModel).filter(FileModel.id == file_id).first()
    if not f:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="资料不存在")
    f.publish_status = body.publish_status
    db.commit()
    log_operation(db, admin.id, "管理员设置发布状态", "file", file_id, body.publish_status)
    return {"file_id": file_id, "publish_status": f.publish_status}

@router.post("/kb/wiki-lint")
def admin_wiki_lint(
    body: AdminWikiLintBody | None = None,
    db: Session = Depends(get_db),
    admin: User = Depends(get_admin_user),
):
    from models.user import User as UserModel
    from services.wiki_lint_service import lint_user_wiki

    req = body or AdminWikiLintBody()
    if req.user_id is not None:
        user = db.query(UserModel).filter(UserModel.id == req.user_id).first()
        if not user:
            raise HTTPException(status_code=404, detail="用户不存在")
        report = lint_user_wiki(db, user)
    else:
        from services.wiki_lint_service import lint_all_users_with_kb_index

        reports = lint_all_users_with_kb_index(db)
        log_operation(db, admin.id, "管理员 Wiki 体检", "kb_wiki", 0, f"users={len(reports)}")
        db.commit()
        return {"reports": reports}
    log_operation(db, admin.id, "管理员 Wiki 体检", "kb_wiki", req.user_id, "single user")
    db.commit()
    return WikiLintResponse(**report)


@router.post("/kb/rebuild-wiki-links")
def admin_rebuild_wiki_links(
    body: AdminWikiRebuildBody | None = None,
    db: Session = Depends(get_db),
    admin: User = Depends(get_admin_user),
):
    from models.file import File as FileModel
    from services.knowledge_base_index_service import auto_sync_kb_index
    from services.md_wiki_link_service import batch_rebuild_all_wiki_links

    req = body or AdminWikiRebuildBody()
    if req.user_id is None:
        sync_user_ids = [
            int(row[0])
            for row in db.query(FileModel.user_id)
            .filter(FileModel.has_md.is_(True))
            .distinct()
            .all()
        ]
    else:
        sync_user_ids = [int(req.user_id)]
    result = batch_rebuild_all_wiki_links(
        db, admin, user_id=req.user_id, batch_size=req.batch_size
    )
    for user_id in sync_user_ids:
        auto_sync_kb_index(db, user_id, sync_scope="wiki")
    log_operation(
        db,
        admin.id,
        "管理员重建 Wiki 链接",
        "kb_wiki",
        0,
        f"rebuilt={result['rebuilt_count']} files={result['file_count']}",
    )
    db.commit()
    return {"message": "Wiki 链接已重建", **result}
