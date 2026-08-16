# Copyright (c) 2026 徐泽宇
"""User-scoped peek/count for KB retry/DLQ RabbitMQ queues (owner via File.user_id)."""

from __future__ import annotations

import logging
from typing import Any

from sqlalchemy.orm import Session

from messaging.kb_extract_queues import QUEUE_DLQ as EXTRACT_DLQ
from messaging.kb_extract_queues import QUEUE_RETRY as EXTRACT_RETRY
from messaging.kb_index_queues import QUEUE_DLQ as INDEX_DLQ
from messaging.kb_index_queues import QUEUE_RETRY as INDEX_RETRY
from models.file import File as FileModel
from models.kb_extract_job import KbExtractJob
from models.kb_index_job import KbIndexJob
from models.kb_post_job import KbPostJob
from services.rabbitmq_queue_admin_service import (
    PEEK_LIMIT_DEFAULT,
    PEEK_LIMIT_MAX,
    _collapse_duplicate_job_items,
    _parse_message_body,
)
from services.rabbitmq_retry_dlq_snapshot_service import (
    USER_MQ_LABEL_TO_PIPELINE,
    USER_MQ_LABEL_TO_QUEUE,
    USER_MQ_QUEUE_LABELS,
    PipelineKind,
    count_owned_messages,
    get_retry_dlq_snapshot,
    invalidate_retry_dlq_snapshot,
    owned_messages_for_queue,
)

logger = logging.getLogger(__name__)


def invalidate_user_mq_count_cache(owner_user_id: int | None = None) -> None:
    """Invalidate shared retry/DLQ snapshot (owner_user_id kept for API compat)."""
    del owner_user_id
    invalidate_retry_dlq_snapshot()


def assert_user_mq_queue_label(label: str) -> tuple[str, PipelineKind]:
    if label not in USER_MQ_QUEUE_LABELS:
        raise ValueError(f"不允许的用户 MQ 队列: {label}")
    return USER_MQ_LABEL_TO_QUEUE[label], USER_MQ_LABEL_TO_PIPELINE[label]


def _job_owner_user_id(db: Session, job_id: int, pipeline: PipelineKind) -> int | None:
    if pipeline == "index":
        row = (
            db.query(FileModel.user_id)
            .join(KbIndexJob, KbIndexJob.file_id == FileModel.id)
            .filter(KbIndexJob.id == job_id)
            .first()
        )
    elif pipeline == "post":
        row = db.query(KbPostJob.user_id).filter(KbPostJob.id == job_id).first()
    else:
        row = (
            db.query(FileModel.user_id)
            .join(KbExtractJob, KbExtractJob.file_id == FileModel.id)
            .filter(KbExtractJob.id == job_id)
            .first()
        )
    if row is None:
        return None
    return int(row[0])


def aggregate_user_mq_queue_counts(db: Session, owner_user_id: int) -> dict[str, tuple[int, int]]:
    """Per-label (pending, backlog) for user retry/DLQ; both equal owned MQ depth."""
    try:
        snapshot = get_retry_dlq_snapshot(db)
    except Exception as exc:
        logger.warning("user mq snapshot failed: %s", exc)
        return {label: (0, 0) for label in sorted(USER_MQ_QUEUE_LABELS)}

    out: dict[str, tuple[int, int]] = {}
    for label in sorted(USER_MQ_QUEUE_LABELS):
        try:
            count = count_owned_messages(
                snapshot,
                owner_user_id=owner_user_id,
                queue_label=label,
            )
        except Exception as exc:
            logger.warning("user mq count failed label=%s: %s", label, exc)
            count = 0
        out[label] = (count, count)
    return out


def peek_queue_messages_for_owner(
    db: Session,
    *,
    owner_user_id: int,
    queue_label: str,
    limit: int = PEEK_LIMIT_DEFAULT,
) -> dict[str, Any]:
    queue_name, _pipeline = assert_user_mq_queue_label(queue_label)
    limit = min(max(1, limit), PEEK_LIMIT_MAX)
    try:
        snapshot = get_retry_dlq_snapshot(db)
    except Exception as exc:
        logger.warning("user mq peek snapshot failed: %s", exc)
        return {
            "queue_label": queue_label,
            "queue_name": queue_name,
            "total": 0,
            "peek_count": 0,
            "items": [],
            "truncated": False,
        }
    owned_msgs = owned_messages_for_queue(
        snapshot,
        owner_user_id=owner_user_id,
        queue_label=queue_label,
    )
    owned_rows: list[dict[str, Any]] = []
    for msg in owned_msgs:
        job_id, last_error, preview = _parse_message_body(msg.body)
        owned_rows.append(
            {
                "index": len(owned_rows),
                "job_id": job_id,
                "last_error": last_error,
                "body_preview": preview,
            }
        )
    sliced = owned_rows[:limit]
    items, _ = _collapse_duplicate_job_items(sliced)
    truncated = len(owned_rows) > len(sliced)
    return {
        "queue_label": queue_label,
        "queue_name": queue_name,
        "total": len(owned_rows),
        "peek_count": len(items),
        "items": items,
        "truncated": truncated,
    }


def remove_owner_queue_message(
    db: Session,
    *,
    owner_user_id: int,
    queue_label: str,
    job_id: int,
) -> dict[str, Any]:
    from services.rabbitmq_queue_admin_service import mutate_queue_messages

    queue_name, pipeline = assert_user_mq_queue_label(queue_label)
    owner = _job_owner_user_id(db, job_id, pipeline)
    if owner is None or owner != int(owner_user_id):
        raise PermissionError("forbidden")
    result = mutate_queue_messages(queue_name, job_id=int(job_id))
    invalidate_retry_dlq_snapshot()
    return result
