# Copyright (c) 2026 徐泽宇
"""MQ RPC client for Docling sidecar (kb.docling)."""

from __future__ import annotations

import json
import logging
import uuid
from typing import Any

import pika

from config import KB_EXTRACT_DOCLING_TIMEOUT_SEC
from messaging.kb_docling_queues import (
    EXCHANGE_MAIN,
    ROUTING_KEY_DOCLING,
    declare_kb_docling_topology,
    open_blocking_connection,
)
from messaging.kb_mineru_rpc import _process_consumer_keepalive
from services.kb_docling_inflight import clear_docling_inflight, register_docling_inflight

logger = logging.getLogger(__name__)


def _lookup_docling_username(job_id: int | None) -> str | None:
    if job_id is None:
        return None
    from database import SessionLocal
    from models.kb_extract_job import KbExtractJob
    from models.user import User

    db = SessionLocal()
    try:
        row = (
            db.query(User.username)
            .join(KbExtractJob, KbExtractJob.user_id == User.id)
            .filter(KbExtractJob.id == int(job_id))
            .first()
        )
        return row[0] if row else None
    finally:
        db.close()


class DoclingRpcError(RuntimeError):
    """Docling MQ RPC failed."""


class DoclingRpcTimeout(DoclingRpcError):
    """Docling MQ RPC timed out waiting for sidecar reply."""


def _timeout_ms() -> int:
    return max(1, int(KB_EXTRACT_DOCLING_TIMEOUT_SEC)) * 1000


def call_docling_extract(
    *,
    job_id: int | None,
    file_id: int,
    file_path: str,
    original_name: str,
    bypass_cache: bool = False,
) -> dict[str, Any]:
    """Publish to kb.docling and block until reply or timeout."""
    correlation_id = str(uuid.uuid4())
    timeout_ms = _timeout_ms()
    request_body = {
        "job_id": job_id,
        "file_id": file_id,
        "file_path": file_path,
        "original_name": original_name,
        "correlation_id": correlation_id,
        "bypass_cache": bypass_cache,
    }

    connection = open_blocking_connection()
    channel = connection.channel()
    declare_kb_docling_topology(channel)

    reply_queue_result = channel.queue_declare(
        queue="",
        exclusive=True,
        auto_delete=True,
        arguments={"x-message-ttl": timeout_ms},
    )
    reply_queue = reply_queue_result.method.queue

    response: dict[str, Any] | None = None
    consumed = False

    def on_reply(_ch, method, props, body: bytes) -> None:
        nonlocal response, consumed
        if props.correlation_id != correlation_id:
            return
        try:
            response = json.loads(body.decode("utf-8"))
        except json.JSONDecodeError as exc:
            response = {"ok": False, "error": "invalid_json_reply", "detail": str(exc)}
        consumed = True
        _ch.basic_ack(delivery_tag=method.delivery_tag)

    channel.basic_consume(queue=reply_queue, on_message_callback=on_reply, auto_ack=False)

    register_docling_inflight(
        file_id=file_id,
        job_id=job_id,
        filename=original_name,
        username=_lookup_docling_username(job_id),
    )
    try:
        request_body["reply_to"] = reply_queue
        channel.basic_publish(
            exchange=EXCHANGE_MAIN,
            routing_key=ROUTING_KEY_DOCLING,
            body=json.dumps(request_body, ensure_ascii=False).encode("utf-8"),
            properties=pika.BasicProperties(
                delivery_mode=2,
                content_type="application/json",
                correlation_id=correlation_id,
                reply_to=reply_queue,
                expiration=str(timeout_ms),
            ),
        )

        elapsed = 0.0
        step = 0.5
        max_wait = KB_EXTRACT_DOCLING_TIMEOUT_SEC + 5.0
        while not consumed and elapsed < max_wait:
            connection.process_data_events(time_limit=step)
            _process_consumer_keepalive()
            elapsed += step
    finally:
        clear_docling_inflight(file_id)
        try:
            if channel.consumer_tags:
                channel.basic_cancel(channel.consumer_tags[0])
        except Exception:
            pass
        try:
            if connection.is_open:
                connection.close()
        except Exception:
            pass

    if not consumed or response is None:
        raise DoclingRpcTimeout(
            f"Docling RPC 超时（>{KB_EXTRACT_DOCLING_TIMEOUT_SEC}s），file_id={file_id}"
        )

    if response.get("ok") is False:
        err = response.get("error") or "docling_rpc_failed"
        detail = response.get("detail") or ""
        raise DoclingRpcError(f"{err}: {detail}".strip(": "))

    return response
