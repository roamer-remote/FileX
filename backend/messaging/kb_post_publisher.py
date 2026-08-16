# Copyright (c) 2026 徐泽宇
"""Publish KB post jobs and UI notify events to RabbitMQ (114)."""

from __future__ import annotations

import json
import logging

import pika

from messaging.kb_post_queues import (
    EXCHANGE_MAIN,
    EXCHANGE_POST_NOTIFY,
    ROUTING_KEY_POST,
    ROUTING_KEY_POST_DLQ,
    ROUTING_KEY_POST_RETRY,
    declare_kb_post_topology,
    open_blocking_connection,
)
from models.file import File as FileModel

logger = logging.getLogger(__name__)


def file_post_notify_payload(
    f: FileModel,
    *,
    processing_duration_ms: int | None = None,
    post_entity_ms: int | None = None,
    post_sag_ms: int | None = None,
    post_raptor_ms: int | None = None,
    post_skip_reason: str | None = None,
) -> dict:
    payload: dict = {
        "type": "kb_post_updated",
        "file_id": f.id,
        "kb_post_status": f.kb_post_status,
        "kb_post_error": f.kb_post_error,
    }
    if processing_duration_ms is not None and processing_duration_ms >= 0:
        payload["processing_duration_ms"] = int(processing_duration_ms)
    if post_entity_ms is not None:
        payload["post_entity_ms"] = int(post_entity_ms)
    if post_sag_ms is not None:
        payload["post_sag_ms"] = int(post_sag_ms)
    if post_raptor_ms is not None:
        payload["post_raptor_ms"] = int(post_raptor_ms)
    if post_skip_reason:
        payload["post_skip_reason"] = post_skip_reason
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
        declare_kb_post_topology(ch)
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


def publish_kb_post_job(job_id: int, *, connection: pika.BlockingConnection | None = None) -> None:
    _publish(EXCHANGE_MAIN, ROUTING_KEY_POST, {"job_id": job_id}, connection=connection)


def publish_kb_post_retry(job_id: int, *, connection: pika.BlockingConnection | None = None) -> None:
    _publish(EXCHANGE_MAIN, ROUTING_KEY_POST_RETRY, {"job_id": job_id}, connection=connection)


def publish_kb_post_dlq(job_id: int, *, last_error: str | None = None) -> None:
    _publish(
        EXCHANGE_MAIN,
        ROUTING_KEY_POST_DLQ,
        {"job_id": job_id, "last_error": last_error},
    )


def publish_kb_post_notify(payload: dict, *, connection: pika.BlockingConnection | None = None) -> None:
    _publish(EXCHANGE_POST_NOTIFY, "", payload, connection=connection)


def publish_kb_post_progress_notify(
    payload: dict,
    *,
    connection: pika.BlockingConnection | None = None,
) -> None:
    """Worker-side throttled RAPTOR/entity progress (FR-122-003 B1)."""
    _publish(EXCHANGE_POST_NOTIFY, "", payload, connection=connection)


def publish_file_post_notify(
    f: FileModel,
    *,
    connection: pika.BlockingConnection | None = None,
    processing_duration_ms: int | None = None,
    post_entity_ms: int | None = None,
    post_sag_ms: int | None = None,
    post_raptor_ms: int | None = None,
    post_skip_reason: str | None = None,
) -> None:
    body = dict(
        file_post_notify_payload(
            f,
            processing_duration_ms=processing_duration_ms,
            post_entity_ms=post_entity_ms,
            post_sag_ms=post_sag_ms,
            post_raptor_ms=post_raptor_ms,
            post_skip_reason=post_skip_reason,
        )
    )
    body["user_id"] = f.user_id
    publish_kb_post_notify(body, connection=connection)
