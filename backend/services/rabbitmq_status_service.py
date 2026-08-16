# Copyright (c) 2026 徐泽宇
"""Read-only RabbitMQ connection and queue metrics for admin monitoring.

Authors:
    徐泽宇

Copyright:
    © 2026 徐泽宇
"""

from __future__ import annotations

import json
import logging
from typing import TYPE_CHECKING, Any
from urllib.parse import urlparse, urlunparse

import pika
from pika.exceptions import AMQPChannelError, AMQPConnectionError

from config import RABBITMQ_URL
from messaging.kb_extract_queues import (
    QUEUE_DLQ as EXTRACT_DLQ,
    QUEUE_MAIN as EXTRACT_MAIN,
    QUEUE_RETRY as EXTRACT_RETRY,
    declare_kb_extract_topology,
)
from messaging.kb_index_queues import (
    QUEUE_DLQ as INDEX_DLQ,
    QUEUE_MAIN as INDEX_MAIN,
    QUEUE_NOTIFY_API,
    QUEUE_RETRY as INDEX_RETRY,
    declare_kb_index_topology,
    open_blocking_connection,
)
from messaging.kb_mineru_queues import (
    QUEUE_MAIN as MINERU_MAIN,
    declare_kb_mineru_topology,
)
from messaging.gpu_queues import QUEUE_GPU_MINERU, QUEUE_GPU_RAPTOR
from messaging.kb_post_queues import (
    QUEUE_DLQ as POST_DLQ,
    QUEUE_MAIN as POST_MAIN,
    QUEUE_POST_NOTIFY_API,
    QUEUE_RETRY as POST_RETRY,
    declare_kb_post_topology,
)
from messaging.kb_docling_queues import (
    QUEUE_MAIN as DOCLING_MAIN,
    declare_kb_docling_topology,
)
from utils.timezone import beijing_now

logger = logging.getLogger(__name__)

if TYPE_CHECKING:
    from models.user import User
    from sqlalchemy.orm import Session


def mq_status_fingerprint(status: dict) -> str:
    queues = [
        (
            q.get("name"),
            q.get("label"),
            q.get("online"),
            q.get("message_count"),
            q.get("consumer_count"),
            q.get("consumer_busy"),
            q.get("jobs_pending"),
            q.get("backlog_total"),
        )
        for q in status.get("queues", [])
    ]
    payload = {
        "connected": status.get("connected"),
        "error": status.get("error"),
        "broker_display": status.get("broker_display"),
        "queues": queues,
        "active_tasks": status.get("active_tasks", []),
    }
    return json.dumps(payload, sort_keys=True, ensure_ascii=False)


def mq_status_global_fingerprint() -> str:
    return mq_status_fingerprint(get_mq_status(viewer=None))


def to_mq_status_event(status: dict) -> dict:
    return {"type": "mq_status_updated", **status}


# 顺序须与 frontend MqMonitor.tsx QUEUE_DISPLAY_ORDER 保持一致
MONITORED_QUEUES: tuple[tuple[str, str], ...] = (
    (INDEX_MAIN, "index_main"),
    (INDEX_RETRY, "index_retry"),
    (INDEX_DLQ, "index_dlq"),
    (POST_MAIN, "post_main"),
    (POST_RETRY, "post_retry"),
    (POST_DLQ, "post_dlq"),
    (QUEUE_NOTIFY_API, "index_notify"),
    (QUEUE_POST_NOTIFY_API, "post_notify"),
    (EXTRACT_MAIN, "extract_main"),
    (EXTRACT_RETRY, "extract_retry"),
    (EXTRACT_DLQ, "extract_dlq"),
    (MINERU_MAIN, "mineru_main"),
    (DOCLING_MAIN, "docling_main"),
    (QUEUE_GPU_MINERU, "gpu_mineru"),
    (QUEUE_GPU_RAPTOR, "gpu_raptor"),
)

LABEL_TO_TASK_KIND: dict[str, str] = {
    "index_main": "kb_index",
    "post_main": "kb_post",
    "extract_main": "kb_extract",
    "mineru_main": "kb_mineru",
    "docling_main": "kb_docling",
}

BACKLOG_LABELS: frozenset[str] = frozenset({"index_main", "post_main", "extract_main"})


def mask_broker_url(url: str) -> str:
    if not url:
        return ""
    try:
        parsed = urlparse(url)
    except Exception:
        return "amqp://****"
    user = parsed.username or ""
    host = parsed.hostname or ""
    port = f":{parsed.port}" if parsed.port else ""
    path = parsed.path or ""
    auth = f"{user}:****@" if user else ""
    netloc = f"{auth}{host}{port}"
    return urlunparse((parsed.scheme, netloc, path, "", "", ""))


def list_kb_index_queued_jobs(
    db: Session,
    *,
    limit: int = 50,
    owner_user_id: int | None = None,
) -> dict:
    """主队列：库内 status=queued、可能尚未投递 RabbitMQ 的索引任务。"""
    from models.file import File as FileModel
    from models.kb_index_job import KbIndexJob
    from models.user import User as UserModel
    from services.kb_index_service import JOB_QUEUED

    limit = min(max(1, limit), 100)
    q = db.query(KbIndexJob).filter(KbIndexJob.status == JOB_QUEUED)
    if owner_user_id is not None:
        q = q.join(FileModel, FileModel.id == KbIndexJob.file_id).filter(
            FileModel.user_id == owner_user_id
        )
    total = int(q.count())
    rows = (
        db.query(KbIndexJob, FileModel, UserModel.username)
        .join(FileModel, FileModel.id == KbIndexJob.file_id)
        .join(UserModel, UserModel.id == FileModel.user_id)
        .filter(KbIndexJob.status == JOB_QUEUED)
    )
    if owner_user_id is not None:
        rows = rows.filter(FileModel.user_id == owner_user_id)
    rows = rows.order_by(KbIndexJob.id).limit(limit).all()
    if owner_user_id is not None:
        items = [
            {
                "job_id": int(job.id),
                "file_id": int(file.id),
                "filename": file.filename,
                "updated_at": job.updated_at.isoformat() if job.updated_at else None,
            }
            for job, file, _username in rows
        ]
    else:
        items = [
            {
                "job_id": int(job.id),
                "file_id": int(file.id),
                "filename": file.filename,
                "username": username,
                "updated_at": job.updated_at.isoformat() if job.updated_at else None,
            }
            for job, file, username in rows
        ]
    return {"total": total, "items": items, "truncated": total > len(items)}


def _kb_index_jobs_pending() -> int:
    from database import SessionLocal

    db = SessionLocal()
    try:
        return _aggregate_kb_job_counts(db)["index_main"][0]
    finally:
        db.close()


def _kb_index_backlog_file_count() -> int:
    from database import SessionLocal

    db = SessionLocal()
    try:
        return _aggregate_kb_job_counts(db)["index_main"][1]
    finally:
        db.close()


def _kb_extract_jobs_pending() -> int:
    from database import SessionLocal

    db = SessionLocal()
    try:
        return _aggregate_kb_job_counts(db)["extract_main"][0]
    finally:
        db.close()


def _kb_extract_backlog_file_count() -> int:
    from database import SessionLocal

    db = SessionLocal()
    try:
        return _aggregate_kb_job_counts(db)["extract_main"][1]
    finally:
        db.close()


def _aggregate_kb_job_counts(db: Session) -> dict[str, tuple[int, int]]:
    from models.kb_extract_job import KbExtractJob
    from models.kb_index_job import KbIndexJob
    from services.kb_extract_service import JOB_QUEUED as EXTRACT_QUEUED
    from services.kb_extract_service import JOB_RUNNING as EXTRACT_RUNNING
    from services.kb_extract_service import JOB_WAITING_WEBHOOK as EXTRACT_WAITING_WEBHOOK
    from services.kb_post_service import JOB_QUEUED as POST_QUEUED, JOB_RUNNING as POST_RUNNING
    from services.kb_index_service import JOB_QUEUED as INDEX_QUEUED
    from services.kb_index_service import JOB_RUNNING as INDEX_RUNNING

    index_pending = int(db.query(KbIndexJob).filter(KbIndexJob.status == INDEX_QUEUED).count())
    index_backlog = int(
        db.query(KbIndexJob.file_id)
        .filter(KbIndexJob.status.in_((INDEX_QUEUED, INDEX_RUNNING)))
        .distinct()
        .count()
    )
    from models.kb_post_job import KbPostJob

    post_pending = int(db.query(KbPostJob).filter(KbPostJob.status == POST_QUEUED).count())
    post_backlog = int(
        db.query(KbPostJob.file_id)
        .filter(KbPostJob.status.in_((POST_QUEUED, POST_RUNNING)))
        .distinct()
        .count()
    )
    extract_pending = int(db.query(KbExtractJob).filter(KbExtractJob.status == EXTRACT_QUEUED).count())
    extract_backlog = int(
        db.query(KbExtractJob.file_id)
        .filter(KbExtractJob.status.in_((EXTRACT_QUEUED, EXTRACT_RUNNING, EXTRACT_WAITING_WEBHOOK)))
        .distinct()
        .count()
    )
    return {
        "index_main": (index_pending, index_backlog),
        "post_main": (post_pending, post_backlog),
        "extract_main": (extract_pending, extract_backlog),
    }


def _aggregate_kb_job_counts_for_user(db: Session, user_id: int) -> dict[str, tuple[int, int]]:
    from models.file import File as FileModel
    from models.kb_extract_job import KbExtractJob
    from models.kb_index_job import KbIndexJob
    from services.kb_extract_service import JOB_QUEUED as EXTRACT_QUEUED
    from services.kb_extract_service import JOB_RUNNING as EXTRACT_RUNNING
    from services.kb_extract_service import JOB_WAITING_WEBHOOK as EXTRACT_WAITING_WEBHOOK
    from services.kb_post_service import JOB_QUEUED as POST_QUEUED, JOB_RUNNING as POST_RUNNING
    from services.kb_index_service import JOB_QUEUED as INDEX_QUEUED
    from services.kb_index_service import JOB_RUNNING as INDEX_RUNNING

    uid = int(user_id)
    index_pending = int(
        db.query(KbIndexJob)
        .join(FileModel, FileModel.id == KbIndexJob.file_id)
        .filter(KbIndexJob.status == INDEX_QUEUED, FileModel.user_id == uid)
        .count()
    )
    index_backlog = int(
        db.query(KbIndexJob.file_id)
        .join(FileModel, FileModel.id == KbIndexJob.file_id)
        .filter(
            KbIndexJob.status.in_((INDEX_QUEUED, INDEX_RUNNING)),
            FileModel.user_id == uid,
        )
        .distinct()
        .count()
    )
    from models.kb_post_job import KbPostJob

    post_pending = int(
        db.query(KbPostJob)
        .join(FileModel, FileModel.id == KbPostJob.file_id)
        .filter(KbPostJob.status == POST_QUEUED, FileModel.user_id == uid)
        .count()
    )
    post_backlog = int(
        db.query(KbPostJob.file_id)
        .join(FileModel, FileModel.id == KbPostJob.file_id)
        .filter(
            KbPostJob.status.in_((POST_QUEUED, POST_RUNNING)),
            FileModel.user_id == uid,
        )
        .distinct()
        .count()
    )
    extract_pending = int(
        db.query(KbExtractJob)
        .join(FileModel, FileModel.id == KbExtractJob.file_id)
        .filter(KbExtractJob.status == EXTRACT_QUEUED, FileModel.user_id == uid)
        .count()
    )
    extract_backlog = int(
        db.query(KbExtractJob.file_id)
        .join(FileModel, FileModel.id == KbExtractJob.file_id)
        .filter(
            KbExtractJob.status.in_((EXTRACT_QUEUED, EXTRACT_RUNNING, EXTRACT_WAITING_WEBHOOK)),
            FileModel.user_id == uid,
        )
        .distinct()
        .count()
    )
    return {
        "index_main": (index_pending, index_backlog),
        "post_main": (post_pending, post_backlog),
        "extract_main": (extract_pending, extract_backlog),
    }


USER_MONITORED_QUEUES: tuple[tuple[str, str], ...] = (
    (INDEX_MAIN, "index_main"),
    (INDEX_RETRY, "index_retry"),
    (INDEX_DLQ, "index_dlq"),
    (POST_MAIN, "post_main"),
    (POST_RETRY, "post_retry"),
    (POST_DLQ, "post_dlq"),
    (EXTRACT_MAIN, "extract_main"),
    (EXTRACT_RETRY, "extract_retry"),
    (EXTRACT_DLQ, "extract_dlq"),
)


def list_kb_extract_queued_jobs(
    db: Session,
    *,
    limit: int = 50,
    owner_user_id: int | None = None,
) -> dict:
    from models.file import File as FileModel
    from models.kb_extract_job import KbExtractJob
    from models.user import User as UserModel
    from services.kb_extract_service import JOB_QUEUED

    limit = min(max(1, limit), 100)
    q = db.query(KbExtractJob).filter(KbExtractJob.status == JOB_QUEUED)
    if owner_user_id is not None:
        q = q.join(FileModel, FileModel.id == KbExtractJob.file_id).filter(
            FileModel.user_id == owner_user_id
        )
    total = int(q.count())
    rows = (
        db.query(KbExtractJob, FileModel, UserModel.username)
        .join(FileModel, FileModel.id == KbExtractJob.file_id)
        .join(UserModel, UserModel.id == FileModel.user_id)
        .filter(KbExtractJob.status == JOB_QUEUED)
    )
    if owner_user_id is not None:
        rows = rows.filter(FileModel.user_id == owner_user_id)
    rows = rows.order_by(KbExtractJob.id).limit(limit).all()
    if owner_user_id is not None:
        items = [
            {
                "job_id": int(job.id),
                "file_id": int(file.id),
                "filename": file.filename,
                "updated_at": job.updated_at.isoformat() if job.updated_at else None,
            }
            for job, file, _username in rows
        ]
    else:
        items = [
            {
                "job_id": int(job.id),
                "file_id": int(file.id),
                "filename": file.filename,
                "username": username,
                "updated_at": job.updated_at.isoformat() if job.updated_at else None,
            }
            for job, file, username in rows
        ]
    return {"total": total, "items": items, "truncated": total > len(items)}


def list_kb_post_queued_jobs(
    db: Session,
    *,
    limit: int = 50,
    owner_user_id: int | None = None,
) -> dict:
    """主队列：库内 status=queued、可能尚未投递 RabbitMQ 的后处理任务。"""
    from models.file import File as FileModel
    from models.kb_post_job import KbPostJob
    from models.user import User as UserModel
    from services.kb_post_service import JOB_QUEUED

    limit = min(max(1, limit), 100)
    q = db.query(KbPostJob).filter(KbPostJob.status == JOB_QUEUED)
    if owner_user_id is not None:
        q = q.join(FileModel, FileModel.id == KbPostJob.file_id).filter(
            FileModel.user_id == owner_user_id
        )
    total = int(q.count())
    rows = (
        db.query(KbPostJob, FileModel, UserModel.username)
        .join(FileModel, FileModel.id == KbPostJob.file_id)
        .join(UserModel, UserModel.id == FileModel.user_id)
        .filter(KbPostJob.status == JOB_QUEUED)
    )
    if owner_user_id is not None:
        rows = rows.filter(FileModel.user_id == owner_user_id)
    rows = rows.order_by(KbPostJob.id).limit(limit).all()
    if owner_user_id is not None:
        items = [
            {
                "job_id": int(job.id),
                "file_id": int(file.id),
                "filename": file.filename,
                "updated_at": job.updated_at.isoformat() if job.updated_at else None,
            }
            for job, file, _username in rows
        ]
    else:
        items = [
            {
                "job_id": int(job.id),
                "file_id": int(file.id),
                "filename": file.filename,
                "username": username,
                "updated_at": job.updated_at.isoformat() if job.updated_at else None,
            }
            for job, file, username in rows
        ]
    return {"total": total, "items": items, "truncated": total > len(items)}


def _task_key(kind: str, file_id: int) -> tuple[str, int]:
    return kind, file_id


def _dedupe_tasks(tasks: list[dict]) -> list[dict]:
    seen: set[tuple[str, int]] = set()
    out: list[dict] = []
    for task in tasks:
        file_id = int(task["file_id"])
        key = _task_key(str(task["kind"]), file_id)
        if key in seen:
            continue
        seen.add(key)
        out.append(task)
    return out


def _index_tasks_global(db: Session) -> list[dict]:
    from models.file import File as FileModel
    from models.kb_index_job import KbIndexJob
    from models.user import User as UserModel
    from services.kb_index_service import JOB_RUNNING, STATUS_INDEXING

    tasks: list[dict] = []
    rows = (
        db.query(FileModel, UserModel.username)
        .join(KbIndexJob, KbIndexJob.file_id == FileModel.id)
        .join(UserModel, UserModel.id == FileModel.user_id)
        .filter(KbIndexJob.status == JOB_RUNNING)
        .all()
    )
    for file, username in rows:
        tasks.append(
            {
                "kind": "kb_index",
                "username": username,
                "file_id": int(file.id),
                "filename": file.filename,
            }
        )

    rows2 = (
        db.query(FileModel, UserModel.username)
        .join(UserModel, UserModel.id == FileModel.user_id)
        .filter(FileModel.index_status == STATUS_INDEXING)
        .all()
    )
    for file, username in rows2:
        tasks.append(
            {
                "kind": "kb_index",
                "username": username,
                "file_id": int(file.id),
                "filename": file.filename,
            }
        )
    return _dedupe_tasks(tasks)


def _extract_tasks_global(db: Session) -> list[dict]:
    from models.file import File as FileModel
    from models.kb_extract_job import KbExtractJob
    from models.user import User as UserModel
    from services.kb_extract_service import JOB_RUNNING, JOB_WAITING_WEBHOOK, STATUS_EXTRACTING

    tasks: list[dict] = []
    rows = (
        db.query(FileModel, UserModel.username)
        .join(KbExtractJob, KbExtractJob.file_id == FileModel.id)
        .join(UserModel, UserModel.id == FileModel.user_id)
        .filter(KbExtractJob.status.in_((JOB_RUNNING, JOB_WAITING_WEBHOOK)))
        .all()
    )
    for file, username in rows:
        tasks.append(
            {
                "kind": "kb_extract",
                "username": username,
                "file_id": int(file.id),
                "filename": file.filename,
            }
        )

    rows2 = (
        db.query(FileModel, UserModel.username)
        .join(UserModel, UserModel.id == FileModel.user_id)
        .filter(FileModel.extract_status == STATUS_EXTRACTING)
        .all()
    )
    for file, username in rows2:
        tasks.append(
            {
                "kind": "kb_extract",
                "username": username,
                "file_id": int(file.id),
                "filename": file.filename,
            }
        )
    return _dedupe_tasks(tasks)




def _mineru_tasks_global(db: Session) -> list[dict]:
    from models.file import File as FileModel
    from models.user import User as UserModel
    from services.kb_mineru_inflight import list_mineru_inflight

    tasks: list[dict] = []
    entries = list_mineru_inflight()
    file_ids = [int(entry["file_id"]) for entry in entries]
    files = {
        int(f.id): f
        for f in db.query(FileModel).filter(FileModel.id.in_(file_ids)).all()
    } if file_ids else {}
    user_ids = {int(f.user_id) for f in files.values() if f.user_id is not None}
    users = {
        int(u.id): u.username
        for u in db.query(UserModel.id, UserModel.username).filter(UserModel.id.in_(user_ids)).all()
    } if user_ids else {}
    for entry in entries:
        file_id = int(entry["file_id"])
        username = (entry.get("username") or "").strip() or None
        file = files.get(file_id)
        if file is None:
            filename = entry.get("filename") or f"#{file_id}"
        else:
            filename = file.filename
            if not username:
                username = users.get(int(file.user_id))
        tasks.append(
            {
                "kind": "kb_mineru",
                "username": username or "?",
                "file_id": file_id,
                "filename": filename,
            }
        )
    return _dedupe_tasks(tasks)


def _docling_tasks_global(db: Session) -> list[dict]:
    from models.file import File as FileModel
    from models.user import User as UserModel
    from services.kb_docling_inflight import list_docling_inflight

    tasks: list[dict] = []
    entries = list_docling_inflight()
    file_ids = [int(entry["file_id"]) for entry in entries]
    files = {
        int(f.id): f
        for f in db.query(FileModel).filter(FileModel.id.in_(file_ids)).all()
    } if file_ids else {}
    user_ids = {int(f.user_id) for f in files.values() if f.user_id is not None}
    users = {
        int(u.id): u.username
        for u in db.query(UserModel.id, UserModel.username).filter(UserModel.id.in_(user_ids)).all()
    } if user_ids else {}
    for entry in entries:
        file_id = int(entry["file_id"])
        username = (entry.get("username") or "").strip() or None
        file = files.get(file_id)
        if file is None:
            filename = entry.get("filename") or f"#{file_id}"
        else:
            filename = file.filename
            if not username:
                username = users.get(int(file.user_id))
        tasks.append(
            {
                "kind": "kb_docling",
                "username": username or "?",
                "file_id": file_id,
                "filename": filename,
            }
        )
    return _dedupe_tasks(tasks)


def _post_tasks_global(db: Session) -> list[dict]:
    from models.file import File as FileModel
    from models.kb_post_job import KbPostJob
    from models.user import User as UserModel
    from services.kb_post_service import JOB_RUNNING, POST_STATUS_RUNNING

    tasks: list[dict] = []
    rows = (
        db.query(FileModel, UserModel.username)
        .join(KbPostJob, KbPostJob.file_id == FileModel.id)
        .join(UserModel, UserModel.id == FileModel.user_id)
        .filter(KbPostJob.status == JOB_RUNNING)
        .all()
    )
    for file, username in rows:
        tasks.append(
            {
                "kind": "kb_post",
                "username": username,
                "file_id": int(file.id),
                "filename": file.filename,
            }
        )

    rows2 = (
        db.query(FileModel, UserModel.username)
        .join(UserModel, UserModel.id == FileModel.user_id)
        .filter(FileModel.kb_post_status == POST_STATUS_RUNNING)
        .all()
    )
    for file, username in rows2:
        tasks.append(
            {
                "kind": "kb_post",
                "username": username,
                "file_id": int(file.id),
                "filename": file.filename,
            }
        )
    return _dedupe_tasks(tasks)


def _active_tasks_global(db: Session) -> list[dict]:
    from messaging.mq_task_progress import merge_task_progress_list, prune_stale_progress

    tasks = _index_tasks_global(db)
    tasks.extend(_post_tasks_global(db))
    tasks.extend(_extract_tasks_global(db))
    tasks.extend(_mineru_tasks_global(db))
    tasks.extend(_docling_tasks_global(db))
    deduped = _dedupe_tasks(tasks)
    active_file_ids = {int(t["file_id"]) for t in deduped if t.get("file_id") is not None}
    prune_stale_progress(active_file_ids)
    return attach_active_task_models(db, merge_task_progress_list(deduped))


def attach_active_task_models(db: Session, tasks: list[dict]) -> list[dict]:
    """Attach the effective model to each active task without exposing credentials."""
    if not tasks:
        return tasks

    post_model: str | None = None
    embed_model: str | None = None
    kinds = {str(task.get("kind")) for task in tasks}
    if "kb_post" in kinds:
        from services.kb_post_llm_service import get_kb_post_llm_runtime_config

        post_model = get_kb_post_llm_runtime_config(db, fresh=True).model.strip() or None
    if "kb_index" in kinds:
        from services.ollama_config_service import get_ollama_runtime_config

        embed_model = get_ollama_runtime_config(db, fresh=True).embed_model.strip() or None

    static_models = {
        "kb_extract": "提取引擎",
        "kb_mineru": "MinerU",
        "kb_docling": "Docling",
    }
    for task in tasks:
        kind = str(task.get("kind"))
        model = {
            "kb_post": post_model,
            "kb_index": embed_model,
        }.get(kind, static_models.get(kind))
        if model:
            task["model"] = model
    return tasks


def _active_tasks_for_viewer(db: Session, viewer: User) -> list[dict]:
    from services.acl_service import user_can_read_file

    from models.file import File as FileModel

    visible: list[dict] = []
    tasks = _active_tasks_global(db)
    file_ids = [int(task["file_id"]) for task in tasks]
    files = {
        int(f.id): f
        for f in db.query(FileModel).filter(FileModel.id.in_(file_ids)).all()
    } if file_ids else {}
    for task in tasks:
        file = files.get(int(task["file_id"]))
        if file and user_can_read_file(db, viewer, file):
            visible.append(task)
    return visible


def _active_tasks_for_owner(db: Session, owner: User) -> list[dict]:
    from models.file import File as FileModel

    owner_id = int(owner.id)
    tasks = _active_tasks_global(db)
    file_ids = [int(task["file_id"]) for task in tasks]
    files = {
        int(f.id): f
        for f in db.query(FileModel).filter(FileModel.id.in_(file_ids)).all()
    } if file_ids else {}
    visible: list[dict] = []
    for task in tasks:
        file = files.get(int(task["file_id"]))
        if file is None or int(file.user_id) != owner_id:
            continue
        visible.append(
            {
                "kind": str(task["kind"]),
                "file_id": int(task["file_id"]),
                "filename": task.get("filename"),
                **{
                    k: task[k]
                    for k in ("progress_pct", "progress_stage", "progress_detail")
                    if task.get(k) is not None
                },
                **({"model": task["model"]} if task.get("model") is not None else {}),
            }
        )
    return visible


def mq_status_to_user_payload(status: dict) -> dict:
    """Strip admin-only fields for user WS/REST (no username, masked broker depths)."""
    from services.rabbitmq_queue_user_service import USER_MQ_QUEUE_LABELS

    visible_labels = BACKLOG_LABELS | USER_MQ_QUEUE_LABELS
    queues: list[dict] = []
    for q in status.get("queues", []):
        label = q.get("label")
        if label not in visible_labels:
            continue
        queues.append(
            {
                "name": q.get("name"),
                "label": label,
                "online": bool(q.get("online")),
                "message_count": 0,
                "consumer_count": 0,
                "consumer_busy": bool(q.get("consumer_busy")),
                "jobs_pending": int(q.get("jobs_pending") or 0),
                "backlog_total": int(q.get("backlog_total") or 0),
            }
        )
    active_tasks = [
        {
            "kind": str(t.get("kind")),
            "file_id": t.get("file_id"),
            "filename": t.get("filename"),
            **{
                k: t[k]
                for k in ("progress_pct", "progress_stage", "progress_detail", "model")
                if t.get(k) is not None
            },
        }
        for t in status.get("active_tasks", [])
    ]
    return {
        "connected": status.get("connected"),
        "broker_display": "",
        "error": status.get("error"),
        "updated_at": status.get("updated_at"),
        "queues": queues,
        "active_tasks": active_tasks,
    }


def _queue_snapshot(channel: pika.channel.Channel, queue_name: str, label: str) -> tuple[dict, bool]:
    try:
        method = channel.queue_declare(queue=queue_name, passive=True)
        return {
            "name": queue_name,
            "label": label,
            "online": True,
            "message_count": int(method.method.message_count),
            "consumer_count": int(method.method.consumer_count),
            "consumer_busy": False,
            "jobs_pending": 0,
            "backlog_total": 0,
        }, False
    except AMQPChannelError:
        return {
            "name": queue_name,
            "label": label,
            "online": False,
            "message_count": 0,
            "consumer_count": 0,
            "consumer_busy": False,
            "jobs_pending": 0,
            "backlog_total": 0,
        }, True


def get_mq_status(*, viewer: User | None = None) -> dict:
    if viewer is not None and viewer.is_admin:
        viewer = None
    if viewer is None:
        return _get_mq_status_global()
    return _get_mq_status_user_scoped(viewer)


def _get_mq_status_global() -> dict:
    from database import SessionLocal

    now = beijing_now().isoformat()
    broker_display = mask_broker_url(RABBITMQ_URL)
    empty_queues = [
        {
            "name": name,
            "label": label,
            "online": False,
            "message_count": 0,
            "consumer_count": 0,
            "consumer_busy": False,
            "jobs_pending": 0,
            "backlog_total": 0,
        }
        for name, label in MONITORED_QUEUES
    ]

    db = SessionLocal()
    try:
        active_tasks = _active_tasks_global(db)
        backlog_map = _aggregate_kb_job_counts(db)
        gpu_observability = {
            "gpu_scheduler": _gpu_scheduler_state(db),
            "gpu_waiting": _gpu_waiting_summary(db),
        }
    finally:
        db.close()

    return _build_mq_status_payload(
        now=now,
        broker_display=broker_display,
        empty_queues=empty_queues,
        monitored=MONITORED_QUEUES,
        active_tasks=active_tasks,
        backlog_map=backlog_map,
        user_scoped=False,
        gpu_observability=gpu_observability,
    )


def _get_mq_status_user_scoped(viewer: User) -> dict:
    from database import SessionLocal

    now = beijing_now().isoformat()
    empty_queues = [
        {
            "name": name,
            "label": label,
            "online": False,
            "message_count": 0,
            "consumer_count": 0,
            "consumer_busy": False,
            "jobs_pending": 0,
            "backlog_total": 0,
        }
        for name, label in USER_MONITORED_QUEUES
    ]

    db = SessionLocal()
    try:
        active_tasks = _active_tasks_for_owner(db, viewer)
        backlog_map = _aggregate_kb_job_counts_for_user(db, int(viewer.id))
        from services.rabbitmq_queue_user_service import aggregate_user_mq_queue_counts

        backlog_map.update(aggregate_user_mq_queue_counts(db, int(viewer.id)))
    finally:
        db.close()

    raw = _build_mq_status_payload(
        now=now,
        broker_display="",
        empty_queues=empty_queues,
        monitored=USER_MONITORED_QUEUES,
        active_tasks=active_tasks,
        backlog_map=backlog_map,
        user_scoped=True,
    )
    return mq_status_to_user_payload(raw)


def _gpu_scheduler_state(db: Any) -> dict | None:
    """读取 gpu-scheduler worker 持久化的观测状态（164 §9）。"""
    from services.gpu_scheduler_state_store import GpuSchedulerStateStore

    return GpuSchedulerStateStore().read_state(db=db) or None


def _gpu_waiting_summary(db: Any) -> dict:
    """统计处于 waiting_gpu 的 extract/post 任务：数量、最久等待秒数与原因码。"""
    import re

    from models.kb_extract_job import KbExtractJob
    from models.kb_post_job import KbPostJob
    from utils.timezone import naive_db_now

    try:
        now = naive_db_now()
        rows = list(
            db.query(KbExtractJob.updated_at, KbExtractJob.last_error)
            .filter(KbExtractJob.status == "waiting_gpu")
            .all()
        )
        rows += list(
            db.query(KbPostJob.updated_at, KbPostJob.last_error)
            .filter(KbPostJob.status == "waiting_gpu")
            .all()
        )
        oldest_seconds: int | None = None
        reason_codes: set[str] = set()
        for updated_at, last_error in rows:
            if updated_at is not None:
                try:
                    seconds = int((now - updated_at).total_seconds())
                    if seconds >= 0:
                        oldest_seconds = (
                            seconds if oldest_seconds is None else max(oldest_seconds, seconds)
                        )
                except TypeError:
                    pass
            if last_error:
                match = re.match(r"\s*([a-z][a-z0-9_]*):", last_error)
                if match:
                    reason_codes.add(match.group(1))
        return {
            "count": len(rows),
            "oldest_wait_seconds": oldest_seconds,
            "reason_codes": sorted(reason_codes),
        }
    except Exception as exc:
        logger.warning("gpu_waiting summary skipped: %s", exc)
        return {"count": 0, "oldest_wait_seconds": None, "reason_codes": []}


def _build_mq_status_payload(
    *,
    now: str,
    broker_display: str,
    empty_queues: list[dict],
    monitored: tuple[tuple[str, str], ...],
    active_tasks: list[dict],
    backlog_map: dict[str, tuple[int, int]],
    user_scoped: bool,
    gpu_observability: dict | None = None,
) -> dict:
    from services.system_resource_service import collect_system_resources

    system_resources = None if user_scoped else collect_system_resources()
    if system_resources is not None and gpu_observability:
        system_resources = dict(system_resources)
        system_resources["gpu_scheduler"] = gpu_observability.get("gpu_scheduler")
        system_resources["gpu_waiting"] = gpu_observability.get("gpu_waiting")

    def _payload(**values: object) -> dict:
        payload = dict(values)
        if system_resources is not None:
            payload["system_resources"] = system_resources
        return payload

    def _consumer_busy(label: str) -> bool:
        kind = LABEL_TO_TASK_KIND.get(label)
        if not kind:
            return False
        return any(t.get("kind") == kind for t in active_tasks)

    def _apply_backlog(queues: list[dict]) -> None:
        for q in queues:
            label = q.get("label")
            if label in backlog_map:
                pending, backlog = backlog_map[label]
                q["jobs_pending"] = pending
                q["backlog_total"] = backlog
            q["consumer_busy"] = _consumer_busy(str(label))

    if not RABBITMQ_URL:
        _apply_backlog(empty_queues)
        return _payload(
            connected=False,
            broker_display=broker_display,
            error="RABBITMQ_URL 未配置",
            updated_at=now,
            queues=empty_queues,
            active_tasks=active_tasks,
        )

    try:
        conn = open_blocking_connection()
    except AMQPConnectionError as exc:
        _apply_backlog(empty_queues)
        return _payload(
            connected=False,
            broker_display=broker_display,
            error=str(exc),
            updated_at=now,
            queues=empty_queues,
            active_tasks=active_tasks,
        )
    except Exception as exc:
        return _payload(
            connected=False,
            broker_display=broker_display,
            error=str(exc),
            updated_at=now,
            queues=[],
            active_tasks=active_tasks,
        )

    queues: list[dict] = []
    try:
        ch = conn.channel()
        declare_kb_index_topology(ch)
        declare_kb_post_topology(ch)
        declare_kb_extract_topology(ch)
        if not user_scoped:
            declare_kb_mineru_topology(ch)
            declare_kb_docling_topology(ch)
        for queue_name, label in monitored:
            snap, channel_closed = _queue_snapshot(ch, queue_name, label)
            if channel_closed:
                # A passive lookup of a missing queue closes the channel; do not reuse it.
                try:
                    if ch.is_open:
                        ch.close()
                except Exception:
                    pass
                ch = conn.channel()
            if user_scoped:
                snap["message_count"] = 0
                snap["consumer_count"] = 0
            if label not in BACKLOG_LABELS:
                snap["jobs_pending"] = 0
                snap["backlog_total"] = 0
            snap["consumer_busy"] = _consumer_busy(label)
            queues.append(snap)
        _apply_backlog(queues)
    except Exception as exc:
        return _payload(
            connected=False,
            broker_display=broker_display,
            error=str(exc),
            updated_at=now,
            queues=queues,
            active_tasks=active_tasks,
        )
    finally:
        try:
            if conn.is_open:
                conn.close()
        except Exception:
            pass

    return _payload(
        connected=True,
        broker_display=broker_display,
        error=None,
        updated_at=now,
        queues=queues,
        active_tasks=active_tasks,
    )
