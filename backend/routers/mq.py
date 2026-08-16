# Copyright (c) 2026 徐泽宇
"""Authenticated user MQ task monitoring (/api/mq/*).

Personal-scope only for all logged-in users (including admin).
Full-site ops remain on /api/admin/mq-*.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.orm import Session

from database import get_db
from messaging.mq_status_watcher import request_refresh
from middleware.auth import get_current_user
from models.user import User
from schemas.mq_status import (
    MqUserJobCancelResponse,
    MqUserQueuedJobsResponse,
    MqUserQueuedJobItem,
)
from schemas.mq_queue_messages import (
    MqUserQueueMessageRemoveRequest,
    MqUserQueueMessageRemoveResponse,
    MqUserQueueMessagesResponse,
    MqUserQueueMessageItem,
)
from services.kb_mq_user_service import UserMqJobCancelError, cancel_user_kb_job
from services.rabbitmq_queue_user_service import (
    USER_MQ_QUEUE_LABELS,
    peek_queue_messages_for_owner,
    remove_owner_queue_message,
)
from services.rabbitmq_status_service import (
    list_kb_extract_queued_jobs,
    list_kb_index_queued_jobs,
    list_kb_post_queued_jobs,
)

router = APIRouter()


@router.get("/queued-jobs", response_model=MqUserQueuedJobsResponse)
def user_list_index_queued_jobs(
    limit: int = Query(50, ge=1, le=100),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """List current user's queued index jobs (personal scope)."""
    payload = list_kb_index_queued_jobs(db, limit=limit, owner_user_id=int(current_user.id))
    return MqUserQueuedJobsResponse(
        total=int(payload["total"]),
        items=[MqUserQueuedJobItem(**item) for item in payload["items"]],
        truncated=bool(payload.get("truncated")),
    )


@router.get("/extract-queued-jobs", response_model=MqUserQueuedJobsResponse)
def user_list_extract_queued_jobs(
    limit: int = Query(50, ge=1, le=100),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """List current user's queued extract jobs (personal scope)."""
    payload = list_kb_extract_queued_jobs(db, limit=limit, owner_user_id=int(current_user.id))
    return MqUserQueuedJobsResponse(
        total=int(payload["total"]),
        items=[MqUserQueuedJobItem(**item) for item in payload["items"]],
        truncated=bool(payload.get("truncated")),
    )


@router.get("/post-queued-jobs", response_model=MqUserQueuedJobsResponse)
def user_list_post_queued_jobs(
    limit: int = Query(50, ge=1, le=100),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """List current user's queued post jobs (personal scope)."""
    payload = list_kb_post_queued_jobs(db, limit=limit, owner_user_id=int(current_user.id))
    return MqUserQueuedJobsResponse(
        total=int(payload["total"]),
        items=[MqUserQueuedJobItem(**item) for item in payload["items"]],
        truncated=bool(payload.get("truncated")),
    )


@router.post("/index-jobs/{job_id}/cancel", response_model=MqUserJobCancelResponse)
def user_cancel_index_job(
    job_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    try:
        result = cancel_user_kb_job(db, current_user, job_id, "index")
    except UserMqJobCancelError as exc:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=str(exc)) from exc
    return MqUserJobCancelResponse(**result)


@router.post("/extract-jobs/{job_id}/cancel", response_model=MqUserJobCancelResponse)
def user_cancel_extract_job(
    job_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    try:
        result = cancel_user_kb_job(db, current_user, job_id, "extract")
    except UserMqJobCancelError as exc:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=str(exc)) from exc
    return MqUserJobCancelResponse(**result)


@router.get("/queue-messages", response_model=MqUserQueueMessagesResponse)
def user_peek_queue_messages(
    queue: str = Query(..., description="index_retry|index_dlq|extract_retry|extract_dlq"),
    limit: int = Query(50, ge=1, le=100),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Peek retry/DLQ messages owned by current user (personal scope)."""
    if queue not in USER_MQ_QUEUE_LABELS:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="invalid queue")
    try:
        payload = peek_queue_messages_for_owner(
            db,
            owner_user_id=int(current_user.id),
            queue_label=queue,
            limit=limit,
        )
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc
    except Exception as exc:
        raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail=str(exc)) from exc
    return MqUserQueueMessagesResponse(
        queue_label=str(payload["queue_label"]),
        total=int(payload["total"]),
        peek_count=int(payload["peek_count"]),
        items=[MqUserQueueMessageItem(**item) for item in payload["items"]],
        truncated=bool(payload.get("truncated")),
    )


@router.post("/queue-messages/remove", response_model=MqUserQueueMessageRemoveResponse)
def user_remove_queue_message(
    body: MqUserQueueMessageRemoveRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Remove one owned message from retry/DLQ by job_id."""
    if body.queue_label not in USER_MQ_QUEUE_LABELS:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="invalid queue")
    try:
        result = remove_owner_queue_message(
            db,
            owner_user_id=int(current_user.id),
            queue_label=body.queue_label,
            job_id=int(body.job_id),
        )
    except PermissionError as exc:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc
    except Exception as exc:
        raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail=str(exc)) from exc
    request_refresh()
    return MqUserQueueMessageRemoveResponse(
        queue_label=body.queue_label,
        removed=int(result.get("removed", 0)),
    )
