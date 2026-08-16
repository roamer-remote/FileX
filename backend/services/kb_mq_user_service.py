# Copyright (c) 2026 徐泽宇
"""User-scoped KB MQ job maintenance (cancel queued jobs).

Authors:
    徐泽宇

Copyright:
    © 2026 徐泽宇
"""

from __future__ import annotations

import logging
from typing import Literal

from sqlalchemy.orm import Session

from messaging.kb_extract_queues import QUEUE_MAIN as EXTRACT_QUEUE
from messaging.kb_index_queues import QUEUE_MAIN as INDEX_QUEUE
from messaging.mq_status_watcher import request_refresh
from models.file import File as FileModel
from models.kb_extract_job import KbExtractJob
from models.kb_index_job import KbIndexJob
from models.user import User
from services.kb_extract_service import JOB_ERROR as EXTRACT_JOB_ERROR
from services.kb_extract_service import JOB_QUEUED as EXTRACT_QUEUED
from services.kb_extract_service import STATUS_PENDING as EXTRACT_STATUS_PENDING
from services.kb_index_service import JOB_ERROR as INDEX_JOB_ERROR
from services.kb_index_service import JOB_QUEUED as INDEX_QUEUED
from services.kb_index_service import STATUS_PENDING as INDEX_STATUS_PENDING
from services.log_service import log_operation
from services.rabbitmq_queue_admin_service import mutate_queue_messages

logger = logging.getLogger(__name__)

KbJobKind = Literal["index", "extract"]


class UserMqJobCancelError(Exception):
    """Raised when cancel is forbidden or job not cancellable."""

    pass


def cancel_user_kb_job(
    db: Session,
    user: User,
    job_id: int,
    kind: KbJobKind,
) -> dict[str, int | str]:
    """Cancel a queued index/extract job owned by user (DB + best-effort MQ)."""
    if kind == "index":
        job = db.query(KbIndexJob).filter(KbIndexJob.id == job_id).first()
        queue_name = INDEX_QUEUE
        action = "user_mq_index_job_cancel"
    else:
        job = db.query(KbExtractJob).filter(KbExtractJob.id == job_id).first()
        queue_name = EXTRACT_QUEUE
        action = "user_mq_extract_job_cancel"

    if job is None:
        raise UserMqJobCancelError("forbidden")

    file = db.query(FileModel).filter(FileModel.id == job.file_id).first()
    if file is None or int(file.user_id) != int(user.id):
        raise UserMqJobCancelError("forbidden")
    if int(job.user_id) != int(user.id):
        raise UserMqJobCancelError("forbidden")

    expected_queued = INDEX_QUEUED if kind == "index" else EXTRACT_QUEUED
    if job.status != expected_queued:
        raise UserMqJobCancelError("forbidden")

    job.status = INDEX_JOB_ERROR if kind == "index" else EXTRACT_JOB_ERROR
    job.last_error = "cancelled by user"
    if kind == "index":
        file.index_status = INDEX_STATUS_PENDING
    else:
        file.extract_status = EXTRACT_STATUS_PENDING
    db.add(job)
    db.add(file)
    db.commit()

    mq_removed = 0
    try:
        result = mutate_queue_messages(queue_name, job_id=int(job.id))
        mq_removed = int(result.get("removed", 0))
    except Exception as exc:
        logger.warning("user mq cancel: MQ remove failed job_id=%s kind=%s: %s", job_id, kind, exc)

    log_operation(
        db,
        user.id,
        action,
        "kb_job",
        int(job.id),
        f"用户取消 {kind} job_id={job.id} file_id={file.id} mq_removed={mq_removed}",
    )
    request_refresh()
    return {"job_id": int(job.id), "file_id": int(file.id), "kind": kind, "mq_removed": mq_removed}
