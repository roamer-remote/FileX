# Copyright (c) 2026 徐泽宇
"""Shared in-memory snapshot of KB retry/DLQ queues for per-user counts and peek (092)."""

from __future__ import annotations

import logging
import threading
import time
from dataclasses import dataclass
from typing import Any, Literal

from sqlalchemy.orm import Session

from messaging.kb_extract_queues import QUEUE_DLQ as EXTRACT_DLQ
from messaging.kb_extract_queues import QUEUE_RETRY as EXTRACT_RETRY
from messaging.kb_index_queues import QUEUE_DLQ as INDEX_DLQ
from messaging.kb_index_queues import QUEUE_RETRY as INDEX_RETRY
from messaging.kb_index_queues import open_blocking_connection
from messaging.kb_post_queues import QUEUE_DLQ as POST_DLQ
from messaging.kb_post_queues import QUEUE_RETRY as POST_RETRY
from services.rabbitmq_queue_admin_service import (
    _declare_admin_topologies,
    _drain_queue,
    _parse_message_body,
    _republish_queue,
)

logger = logging.getLogger(__name__)

PipelineKind = Literal["index", "extract", "post"]

USER_MQ_QUEUE_LABELS: frozenset[str] = frozenset(
    {
        "index_retry",
        "index_dlq",
        "post_retry",
        "post_dlq",
        "extract_retry",
        "extract_dlq",
    }
)

USER_MQ_LABEL_TO_QUEUE: dict[str, str] = {
    "index_retry": INDEX_RETRY,
    "index_dlq": INDEX_DLQ,
    "post_retry": POST_RETRY,
    "post_dlq": POST_DLQ,
    "extract_retry": EXTRACT_RETRY,
    "extract_dlq": EXTRACT_DLQ,
}

USER_MQ_LABEL_TO_PIPELINE: dict[str, PipelineKind] = {
    "index_retry": "index",
    "index_dlq": "index",
    "post_retry": "post",
    "post_dlq": "post",
    "extract_retry": "extract",
    "extract_dlq": "extract",
}

RETRY_DLQ_QUEUE_NAMES: frozenset[str] = frozenset(USER_MQ_LABEL_TO_QUEUE.values())

_SNAPSHOT_TTL_SEC = 15.0
_lock = threading.Lock()
_snapshot: RetryDlqSnapshot | None = None


@dataclass(frozen=True)
class QueuedMessage:
    props: Any
    body: bytes
    job_id: int | None


@dataclass(frozen=True)
class RetryDlqSnapshot:
    by_label: dict[str, tuple[QueuedMessage, ...]]
    index_owners: dict[int, int]
    post_owners: dict[int, int]
    extract_owners: dict[int, int]
    monotonic_at: float


def invalidate_retry_dlq_snapshot() -> None:
    global _snapshot
    with _lock:
        _snapshot = None


def invalidate_retry_dlq_snapshot_for_queue(queue_name: str) -> None:
    if queue_name in RETRY_DLQ_QUEUE_NAMES:
        invalidate_retry_dlq_snapshot()


def warm_retry_dlq_snapshot(db: Session) -> RetryDlqSnapshot:
    """Ensure snapshot is fresh; safe to call before per-user MQ status broadcast."""
    return get_retry_dlq_snapshot(db)


def get_retry_dlq_snapshot(db: Session) -> RetryDlqSnapshot:
    global _snapshot
    now = time.monotonic()
    with _lock:
        if _snapshot is not None and now - _snapshot.monotonic_at < _SNAPSHOT_TTL_SEC:
            return _snapshot
        built = _build_snapshot(db)
        _snapshot = built
        return built


def count_owned_messages(
    snapshot: RetryDlqSnapshot,
    *,
    owner_user_id: int,
    queue_label: str,
) -> int:
    pipeline = USER_MQ_LABEL_TO_PIPELINE[queue_label]
    uid = int(owner_user_id)
    total = 0
    for msg in snapshot.by_label.get(queue_label, ()):
        if _message_owner_id(snapshot, pipeline, msg.job_id) == uid:
            total += 1
    return total


def owned_messages_for_queue(
    snapshot: RetryDlqSnapshot,
    *,
    owner_user_id: int,
    queue_label: str,
) -> list[QueuedMessage]:
    pipeline = USER_MQ_LABEL_TO_PIPELINE[queue_label]
    uid = int(owner_user_id)
    out: list[QueuedMessage] = []
    for msg in snapshot.by_label.get(queue_label, ()):
        if _message_owner_id(snapshot, pipeline, msg.job_id) == uid:
            out.append(msg)
    return out


def _message_owner_id(
    snapshot: RetryDlqSnapshot,
    pipeline: PipelineKind,
    job_id: int | None,
) -> int | None:
    if job_id is None:
        return None
    if pipeline == "index":
        owners = snapshot.index_owners
    elif pipeline == "post":
        owners = snapshot.post_owners
    else:
        owners = snapshot.extract_owners
    return owners.get(int(job_id))


def _build_snapshot(db: Session) -> RetryDlqSnapshot:
    raw = _drain_all_retry_dlq_queues()
    by_label: dict[str, list[QueuedMessage]] = {}
    index_job_ids: set[int] = set()
    post_job_ids: set[int] = set()
    extract_job_ids: set[int] = set()

    for label in sorted(USER_MQ_QUEUE_LABELS):
        pipeline = USER_MQ_LABEL_TO_PIPELINE[label]
        msgs: list[QueuedMessage] = []
        for props, body in raw.get(label, []):
            job_id, _, _ = _parse_message_body(body)
            parsed_id = int(job_id) if job_id is not None else None
            msgs.append(QueuedMessage(props=props, body=body, job_id=parsed_id))
            if parsed_id is not None:
                if pipeline == "index":
                    index_job_ids.add(parsed_id)
                elif pipeline == "post":
                    post_job_ids.add(parsed_id)
                else:
                    extract_job_ids.add(parsed_id)
        by_label[label] = msgs

    return RetryDlqSnapshot(
        by_label={label: tuple(msgs) for label, msgs in by_label.items()},
        index_owners=_resolve_job_owners(db, "index", index_job_ids),
        post_owners=_resolve_job_owners(db, "post", post_job_ids),
        extract_owners=_resolve_job_owners(db, "extract", extract_job_ids),
        monotonic_at=time.monotonic(),
    )


def _drain_all_retry_dlq_queues() -> dict[str, list[tuple[Any, bytes]]]:
    by_label: dict[str, list[tuple[Any, bytes]]] = {}
    conn = open_blocking_connection()
    try:
        ch = conn.channel()
        _declare_admin_topologies(ch)
        for label in sorted(USER_MQ_QUEUE_LABELS):
            queue_name = USER_MQ_LABEL_TO_QUEUE[label]
            if label.endswith("_retry"):
                # 不 drain retry 队列：basic_get + basic_publish 回原队列会把消息当作
                # 全新消息重发、刷新 x-message-ttl，导致 retry 永不过期、永不死信回
                # 主队列，残留/孤儿消息被永久困在返工线。retry 总量由
                # rabbitmq_status_service 的 passive queue_declare 统计；按用户细分
                # 仅对 DLQ（终态、无 TTL）提供。
                by_label[label] = []
                continue
            drained = _drain_queue(ch, queue_name, max_count=None)
            _republish_queue(ch, queue_name, drained)
            by_label[label] = drained
        return by_label
    finally:
        try:
            if conn.is_open:
                conn.close()
        except Exception:
            pass


def _resolve_job_owners(
    db: Session,
    pipeline: PipelineKind,
    job_ids: set[int],
) -> dict[int, int]:
    if not job_ids:
        return {}
    from models.file import File as FileModel
    from models.kb_extract_job import KbExtractJob
    from models.kb_index_job import KbIndexJob
    from models.kb_post_job import KbPostJob

    if pipeline == "index":
        rows = (
            db.query(KbIndexJob.id, FileModel.user_id)
            .join(FileModel, FileModel.id == KbIndexJob.file_id)
            .filter(KbIndexJob.id.in_(job_ids))
            .all()
        )
    elif pipeline == "post":
        rows = (
            db.query(KbPostJob.id, KbPostJob.user_id)
            .filter(KbPostJob.id.in_(job_ids))
            .all()
        )
    else:
        rows = (
            db.query(KbExtractJob.id, FileModel.user_id)
            .join(FileModel, FileModel.id == KbExtractJob.file_id)
            .filter(KbExtractJob.id.in_(job_ids))
            .all()
        )
    return {int(job_id): int(user_id) for job_id, user_id in rows}
