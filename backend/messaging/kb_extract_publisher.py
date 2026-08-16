# Copyright (c) 2026 徐泽宇
"""Publish KB extract jobs and UI notify events (extends index notify payload).

Authors:
    徐泽宇

Copyright:
    © 2026 徐泽宇
"""

from __future__ import annotations

import json
import logging

import pika

from messaging.kb_extract_queues import (
    EXCHANGE_MAIN,
    ROUTING_KEY_DLQ,
    ROUTING_KEY_EXTRACT,
    ROUTING_KEY_RETRY,
    declare_kb_extract_topology,
    open_blocking_connection,
)
from messaging.kb_index_publisher import (
    file_index_notify_payload,
    publish_kb_index_notify,
)
from models.file import File as FileModel
from utils.timezone import to_beijing_time

logger = logging.getLogger(__name__)


def file_extract_notify_payload(
    f: FileModel,
    *,
    processing_duration_ms: int | None = None,
) -> dict:
    body = file_index_notify_payload(f, processing_duration_ms=processing_duration_ms)
    body["type"] = "kb_extract_updated"
    body["extract_status"] = f.extract_status
    body["extract_error"] = f.extract_error
    body["extracted_at"] = (
        to_beijing_time(f.extracted_at).isoformat() if f.extracted_at else None
    )
    body["extract_engine"] = f.extract_engine
    from services.office_normalize_service import preview_mime_type

    body["preview_mime_type"] = preview_mime_type(f)
    return body


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
        declare_kb_extract_topology(ch)
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


def publish_kb_extract_job(job_id: int, *, connection: pika.BlockingConnection | None = None) -> None:
    _publish(EXCHANGE_MAIN, ROUTING_KEY_EXTRACT, {"job_id": job_id}, connection=connection)


def publish_kb_extract_retry(job_id: int, *, connection: pika.BlockingConnection | None = None) -> None:
    _publish(EXCHANGE_MAIN, ROUTING_KEY_RETRY, {"job_id": job_id}, connection=connection)


def publish_kb_extract_dlq(job_id: int, *, last_error: str | None = None) -> None:
    _publish(EXCHANGE_MAIN, ROUTING_KEY_DLQ, {"job_id": job_id, "last_error": last_error})


def publish_file_extract_notify(
    f: FileModel,
    *,
    connection: pika.BlockingConnection | None = None,
    processing_duration_ms: int | None = None,
) -> None:
    body = dict(
        file_extract_notify_payload(f, processing_duration_ms=processing_duration_ms)
    )
    body["user_id"] = f.user_id
    publish_kb_index_notify(body, connection=connection)
