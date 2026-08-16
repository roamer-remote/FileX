# Copyright (c) 2026 徐泽宇
"""Insavlo webhook receiver (044 FR-D): verify + persist event + 200, then async write-back.

Path: POST /api/webhooks/insavlo/document-process
No JWT/API Key; LicenseMiddleware allowlists the path (SC-044-009).
"""

from __future__ import annotations

import hashlib
import hmac
import json
import structlog

from fastapi import APIRouter, Depends, Request
from fastapi.responses import JSONResponse
from sqlalchemy.orm import Session

from database import get_db
from models.insavlo_webhook_event import InsavloWebhookEvent
from models.kb_extract_job import KbExtractJob
from services.insavlo_webhook_writeback import trigger_insavlo_writeback
from services.kb_pipeline_log_service import (
    ACTION_INSAVLO_WEBHOOK_RECEIVED,
    format_kb_pipeline_detail,
    log_kb_pipeline_event,
)

logger = structlog.get_logger(__name__)

router = APIRouter()

WEBHOOK_EVENT_COMPLETED = "document_process.completed"
WEBHOOK_BODY_MAX_BYTES = 10 * 1024 * 1024  # 10 MiB
JOB_DONE = "done"
JOB_ERROR = "error"
JOB_WAITING_WEBHOOK = "waiting_webhook"

REASON_CONTENT_LENGTH_INVALID = "content_length_invalid"
REASON_PAYLOAD_TOO_LARGE = "payload_too_large"
REASON_CONTENT_TYPE_INVALID = "content_type_invalid"
REASON_EVENT_MISMATCH = "event_mismatch"
REASON_INSAVLO_NOT_READY = "insavlo_not_ready"
REASON_SIGNATURE_INVALID = "signature_invalid"
REASON_PAYLOAD_INVALID = "payload_invalid"
REASON_TRANSACTION_MISMATCH = "transaction_mismatch"
REASON_TRANSACTION_NOT_FOUND = "transaction_not_found"


def _log_reject(reason: str, **fields: object) -> None:
    parts = " ".join(f"{k}={v}" for k, v in fields.items() if v is not None)
    suffix = f" {parts}" if parts else ""
    logger.warning(f"insavlo webhook rejected reason={reason}{suffix}")


def _signature_ok(secret: str, raw_body: bytes, signature_header: str | None) -> bool:
    if not signature_header or not secret:
        return False
    expected = "sha256=" + hmac.new(
        secret.encode("utf-8"), raw_body, hashlib.sha256
    ).hexdigest()
    return hmac.compare_digest(expected, signature_header)


@router.post("/document-process")
async def insavlo_document_process(request: Request, db: Session = Depends(get_db)):
    content_length = request.headers.get("content-length")
    if content_length:
        try:
            cl = int(content_length)
        except ValueError:
            _log_reject(REASON_CONTENT_LENGTH_INVALID)
            return JSONResponse(status_code=400, content={"detail": "Content-Length 非法"})
        if cl > WEBHOOK_BODY_MAX_BYTES:
            _log_reject(REASON_PAYLOAD_TOO_LARGE, content_length=cl)
            return JSONResponse(status_code=413, content={"detail": "payload too large"})

    content_type = request.headers.get("content-type", "")
    if "application/json" not in content_type:
        _log_reject(REASON_CONTENT_TYPE_INVALID)
        return JSONResponse(status_code=400, content={"detail": "Content-Type 必须为 application/json"})

    raw_body = await request.body()
    if len(raw_body) > WEBHOOK_BODY_MAX_BYTES:
        _log_reject(REASON_PAYLOAD_TOO_LARGE, body_bytes=len(raw_body))
        return JSONResponse(status_code=413, content={"detail": "payload too large"})

    event_header = request.headers.get("x-webhook-event", "")
    if event_header != WEBHOOK_EVENT_COMPLETED:
        _log_reject(REASON_EVENT_MISMATCH, webhook_event=event_header)
        return JSONResponse(status_code=400, content={"detail": "X-Webhook-Event 不匹配"})

    from services.insavlo_config_service import get_insavlo_runtime_config, is_insavlo_runtime_ready

    if not is_insavlo_runtime_ready(db):
        _log_reject(REASON_INSAVLO_NOT_READY)
        return JSONResponse(status_code=401, content={"detail": "Insavlo 未启用或配置不完整"})

    try:
        cfg = get_insavlo_runtime_config(db)
    except ValueError:
        _log_reject(REASON_INSAVLO_NOT_READY)
        return JSONResponse(status_code=401, content={"detail": "Insavlo 未启用或配置不完整"})

    signature_header = request.headers.get("x-webhook-signature")
    if not _signature_ok(cfg.webhook_secret, raw_body, signature_header):
        _log_reject(REASON_SIGNATURE_INVALID)
        return JSONResponse(status_code=401, content={"detail": "webhook 签名校验失败"})

    try:
        payload = json.loads(raw_body.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError):
        _log_reject(REASON_PAYLOAD_INVALID)
        return JSONResponse(status_code=400, content={"detail": "请求体不是合法 JSON"})

    body_transaction_id = str(payload.get("transaction_id") or "").strip()
    header_transaction_id = request.headers.get("x-transaction-id", "").strip()
    if not body_transaction_id or header_transaction_id != body_transaction_id:
        _log_reject(
            REASON_TRANSACTION_MISMATCH,
            transaction_id=body_transaction_id or None,
        )
        return JSONResponse(status_code=400, content={"detail": "X-Transaction-Id 与 body 不一致"})

    job = (
        db.query(KbExtractJob)
        .filter(
            KbExtractJob.remote_transaction_id == body_transaction_id,
            KbExtractJob.provider == "insavlo",
        )
        .with_for_update()
        .first()
    )
    if job is None:
        _log_reject(REASON_TRANSACTION_NOT_FOUND, transaction_id=body_transaction_id)
        return JSONResponse(status_code=404, content={"detail": "transaction not found"})

    logger.info(
        "insavlo webhook received "
        f"transaction_id={body_transaction_id} job_id={job.id} "
        f"file_id={job.file_id} webhook_event={event_header}"
    )

    if job.status in (JOB_DONE, JOB_ERROR):
        logger.info(
            "insavlo webhook idempotent skip "
            f"transaction_id={body_transaction_id} job_status={job.status}"
        )
        db.commit()
        return JSONResponse(status_code=200, content={"status": "accepted"})

    event = (
        db.query(InsavloWebhookEvent)
        .filter(InsavloWebhookEvent.transaction_id == body_transaction_id)
        .first()
    )
    created = event is None
    if event is None:
        event = InsavloWebhookEvent(
            transaction_id=body_transaction_id,
            job_id=job.id,
            file_id=job.file_id,
            payload_json=payload,
            status="pending",
        )
        db.add(event)
        db.flush()
        log_kb_pipeline_event(
            db,
            job.user_id,
            ACTION_INSAVLO_WEBHOOK_RECEIVED,
            job.file_id,
            detail=format_kb_pipeline_detail(
                event_id=event.id,
                job_id=job.id,
                transaction_id=body_transaction_id,
            ),
        )
    db.commit()
    db.refresh(event)

    if created:
        logger.info(
            "insavlo webhook event persisted "
            f"event_id={event.id} transaction_id={body_transaction_id} "
            f"job_id={job.id} file_id={job.file_id}"
        )
    else:
        logger.info(
            "insavlo webhook duplicate "
            f"event_id={event.id} transaction_id={body_transaction_id} event_status={event.status}"
        )

    trigger_insavlo_writeback()
    return JSONResponse(status_code=200, content={"status": "accepted"})
