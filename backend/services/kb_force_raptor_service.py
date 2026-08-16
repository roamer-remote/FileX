"""118: per-file force RAPTOR (RAPTOR-only post, ignore settings gates)."""

from __future__ import annotations

import logging
from dataclasses import dataclass

from sqlalchemy import or_
from sqlalchemy.orm import Session

from config import GPU_SCHEDULER_ENABLED
from models.file import File as FileModel
from models.kb_chunk import KbChunk
from models.kb_post_job import KbPostJob
from models.user import User
from services.acl_service import get_readable_file
from services.kb_index_service import STATUS_READY
from services.kb_pipeline_log_service import (
    ACTION_KB_FORCE_RAPTOR_START,
    format_kb_pipeline_detail,
    log_kb_pipeline_event,
)
from services.kb_post_service import (
    JOB_QUEUED,
    JOB_RUNNING,
    POST_STATUS_QUEUED,
)
from services.kb_raptor_service import RAPTOR_CONTENT_KIND, clear_raptor_summaries_for_file
from services.kb_text_source import resolve_index_text
from services.workspace_access_service import file_action_capabilities, get_membership

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class ForceRaptorAccess:
    file: FileModel | None
    http_status: int | None = None
    detail: str | None = None


class ForceRaptorRejected(Exception):
    def __init__(self, status_code: int, detail: str):
        self.status_code = status_code
        self.detail = detail
        super().__init__(detail)


def _log_force_raptor(db: Session, user_id: int, file_id: int, action: str, **fields) -> None:
    log_kb_pipeline_event(
        db,
        user_id,
        action,
        file_id,
        detail=format_kb_pipeline_detail(force_settings=True, raptor_only=True, **fields),
    )


def resolve_force_raptor_access(db: Session, user: User, file_id: int) -> ForceRaptorAccess:
    """Return file when user has write access; otherwise status + detail for HTTP error."""
    f = get_readable_file(db, user, file_id)
    if f is None:
        return ForceRaptorAccess(None, 404, "资料不存在")
    if user.is_admin:
        return ForceRaptorAccess(f)
    ws_id = f.workspace_id
    if not ws_id:
        if f.user_id == user.id:
            return ForceRaptorAccess(f)
        return ForceRaptorAccess(None, 404, "资料不存在")
    member = get_membership(db, ws_id, user.id)
    if member is None:
        return ForceRaptorAccess(None, 404, "资料不存在")
    can_write, _ = file_action_capabilities(db, user, f, member=member)
    if not can_write:
        return ForceRaptorAccess(None, 403, "无权限")
    return ForceRaptorAccess(f)


def count_base_chunks(db: Session, file_id: int) -> int:
    return (
        db.query(KbChunk)
        .filter(
            KbChunk.file_id == file_id,
            or_(
                KbChunk.content_kind.is_(None),
                KbChunk.content_kind != RAPTOR_CONTENT_KIND,
            ),
        )
        .count()
    )


def has_active_post_job(db: Session, file_id: int) -> bool:
    return (
        db.query(KbPostJob.id)
        .filter(
            KbPostJob.file_id == file_id,
            KbPostJob.status.in_((JOB_QUEUED, JOB_RUNNING)),
        )
        .first()
        is not None
    )


def enqueue_force_raptor(db: Session, user: User, f: FileModel) -> tuple[int, str]:
    """Create raptor-only post job after lock + validation."""
    from services.system_setting_service import is_kb_post_async_enabled

    if is_kb_post_async_enabled(db) or GPU_SCHEDULER_ENABLED:
        post_job = KbPostJob(
            user_id=f.user_id,
            file_id=f.id,
            status=JOB_QUEUED,
            raptor_only=True,
            force_raptor_settings=True,
        )
        db.add(post_job)
        f.kb_post_status = POST_STATUS_QUEUED
        f.kb_post_error = None
        db.flush()
        _log_force_raptor(
            db,
            user.id,
            f.id,
            ACTION_KB_FORCE_RAPTOR_START,
            job_id=post_job.id,
            async_mode=True,
        )
        # 164 §6：force raptor 必须与普通 RAPTOR 一样建立 durable route；
        # GPU 调度模式下由 scheduler 取得 lease 后统一执行。
        from services.gpu_scheduler_persistence import enqueue_gpu_route

        enqueue_gpu_route(
            db,
            job_kind="raptor",
            job_id=post_job.id,
            file_id=f.id,
            idempotency_key=f"raptor:{post_job.id}:0",
            payload={
                "job_id": int(post_job.id),
                "job_kind": "raptor",
                "file_id": int(f.id),
                "attempt": 0,
                "idempotency_key": f"raptor:{post_job.id}:0",
                "handover_epoch": 0,
            },
        )
        return int(post_job.id), POST_STATUS_QUEUED

    from services.kb_post_service import run_sync_force_raptor

    return run_sync_force_raptor(db, user, f)


def try_force_raptor(db: Session, user: User, file_id: int) -> tuple[int, str]:
    """Lock file, validate, clear old summaries, enqueue. Raises ForceRaptorRejected on 4xx."""
    access = resolve_force_raptor_access(db, user, file_id)
    if access.file is None:
        raise ForceRaptorRejected(access.http_status or 404, access.detail or "资料不存在")

    f = db.query(FileModel).filter(FileModel.id == file_id).with_for_update().first()
    if f is None:
        raise ForceRaptorRejected(404, "资料不存在")

    if has_active_post_job(db, file_id):
        raise ForceRaptorRejected(409, "后处理进行中")

    text, source = resolve_index_text(f)
    if not text or not source:
        raise ForceRaptorRejected(409, "无笔记正文")
    if (f.index_status or "") != STATUS_READY:
        raise ForceRaptorRejected(409, "须先完成检索建立")
    if count_base_chunks(db, file_id) < 2:
        raise ForceRaptorRejected(409, "分块不足")

    clear_raptor_summaries_for_file(db, f.id)
    f.raptor_built_chunk_count = None
    f.raptor_built_md_chars = None
    db.flush()

    job_id, kb_post_status = enqueue_force_raptor(db, user, f)
    return job_id, kb_post_status
