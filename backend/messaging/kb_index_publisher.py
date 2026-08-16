# Copyright (c) 2026 徐泽宇
"""Publish KB index jobs and UI notify events to RabbitMQ.

Authors:
    徐泽宇

Copyright:
    © 2026 徐泽宇
"""

from __future__ import annotations

import json
import logging

import pika

from messaging.kb_index_queues import (
    EXCHANGE_MAIN,
    EXCHANGE_NOTIFY,
    ROUTING_KEY_DLQ,
    ROUTING_KEY_INDEX,
    ROUTING_KEY_RETRY,
    declare_kb_index_topology,
    open_blocking_connection,
)
from models.file import File as FileModel
from utils.timezone import to_beijing_time

logger = logging.getLogger(__name__)


def file_index_notify_payload(
    f: FileModel,
    *,
    processing_duration_ms: int | None = None,
) -> dict:
    from services.file_response import _md_path_has_content

    has_md = bool(f.has_md)
    payload: dict = {
        "type": "kb_index_updated",
        "file_id": f.id,
        "index_status": f.index_status,
        "chunk_count": int(f.chunk_count or 0),
        "index_error": f.index_error,
        "extract_status": f.extract_status,
        "extract_error": f.extract_error,
        "extracted_at": (
            to_beijing_time(f.extracted_at).isoformat() if f.extracted_at else None
        ),
        "extract_engine": f.extract_engine,
        "has_md": has_md,
        "md_has_content": has_md and _md_path_has_content(f.md_file_path),
    }
    if processing_duration_ms is not None and processing_duration_ms >= 0:
        payload["processing_duration_ms"] = int(processing_duration_ms)
    return payload


def _publish(
    exchange: str,
    routing_key: str,
    body: dict,
    *,
    connection: pika.BlockingConnection | None = None,
) -> None:
    owns = connection is None
    conn = connection or open_blocking_connection()
    ch = None
    try:
        ch = conn.channel()
        declare_kb_index_topology(ch)
        ch.basic_publish(
            exchange=exchange,
            routing_key=routing_key,
            body=json.dumps(body, ensure_ascii=False).encode("utf-8"),
            properties=pika.BasicProperties(
                delivery_mode=2,
                content_type="application/json",
            ),
        )
    finally:
        if ch is not None:
            try:
                if ch.is_open:
                    ch.close()
            except Exception:
                pass
        if owns:
            try:
                if conn.is_open:
                    conn.close()
            except Exception:
                pass


def publish_kb_index_job(job_id: int, *, connection: pika.BlockingConnection | None = None) -> None:
    _publish(EXCHANGE_MAIN, ROUTING_KEY_INDEX, {"job_id": job_id}, connection=connection)


def publish_kb_index_retry(job_id: int, *, connection: pika.BlockingConnection | None = None) -> None:
    _publish(EXCHANGE_MAIN, ROUTING_KEY_RETRY, {"job_id": job_id}, connection=connection)


def publish_kb_index_dlq(job_id: int, *, last_error: str | None = None) -> None:
    _publish(
        EXCHANGE_MAIN,
        ROUTING_KEY_DLQ,
        {"job_id": job_id, "last_error": last_error},
    )


def publish_kb_index_notify(payload: dict, *, connection: pika.BlockingConnection | None = None) -> None:
    _publish(EXCHANGE_NOTIFY, "", payload, connection=connection)


def publish_kb_index_progress_notify(
    payload: dict,
    *,
    connection: pika.BlockingConnection | None = None,
) -> None:
    """Worker-side throttled embed/persist progress (FR-122-003 B1)."""
    _publish(EXCHANGE_NOTIFY, "", payload, connection=connection)


def publish_file_index_notify(
    f: FileModel,
    *,
    connection: pika.BlockingConnection | None = None,
    processing_duration_ms: int | None = None,
) -> None:
    body = dict(
        file_index_notify_payload(f, processing_duration_ms=processing_duration_ms)
    )
    body["user_id"] = f.user_id
    publish_kb_index_notify(body, connection=connection)
