# Copyright (c) 2026 徐泽宇
"""Admin peek / purge / delete for monitored KB RabbitMQ queues.

Authors:
    徐泽宇

Copyright:
    © 2026 徐泽宇
"""

from __future__ import annotations

import json
import logging
from typing import Any

import pika
from pika import BasicProperties
from pika.exceptions import AMQPConnectionError, ChannelClosedByBroker

from messaging.kb_extract_queues import declare_kb_extract_topology
from messaging.kb_index_queues import declare_kb_index_topology, open_blocking_connection
from messaging.kb_mineru_queues import declare_kb_mineru_topology
from messaging.gpu_queues import declare_gpu_topology
from services.rabbitmq_status_service import MONITORED_QUEUES

logger = logging.getLogger(__name__)

def _declare_admin_topologies(channel: pika.channel.Channel) -> None:
    declare_kb_index_topology(channel)
    declare_kb_extract_topology(channel)
    declare_kb_mineru_topology(channel)
    declare_gpu_topology(channel)


ALLOWED_ADMIN_QUEUE_NAMES: frozenset[str] = frozenset(name for name, _ in MONITORED_QUEUES)

PEEK_LIMIT_DEFAULT = 50
PEEK_LIMIT_MAX = 100
BODY_PREVIEW_MAX = 500
DRAIN_MAX_MESSAGES = 5000


def assert_admin_queue_allowed(queue_name: str) -> None:
    if queue_name not in ALLOWED_ADMIN_QUEUE_NAMES:
        raise ValueError(f"不允许操作队列: {queue_name}")


def _parse_message_body(body: bytes) -> tuple[int | None, str | None, str]:
    raw = body.decode("utf-8", errors="replace")
    job_id: int | None = None
    last_error: str | None = None
    try:
        payload = json.loads(raw)
        if isinstance(payload, dict):
            jid = payload.get("job_id")
            if jid is not None:
                job_id = int(jid)
            err = payload.get("last_error")
            if err is not None:
                last_error = str(err)[:2000]
    except (json.JSONDecodeError, TypeError, ValueError):
        pass
    preview = raw if len(raw) <= BODY_PREVIEW_MAX else raw[:BODY_PREVIEW_MAX] + "…"
    return job_id, last_error, preview


def _queue_message_count(channel: pika.channel.Channel, queue_name: str) -> int:
    method = channel.queue_declare(queue=queue_name, passive=True)
    return int(method.method.message_count)


def _drain_queue(
    channel: pika.channel.Channel,
    queue_name: str,
    *,
    max_count: int | None = None,
) -> list[tuple[BasicProperties | None, bytes]]:
    """从队头取出消息（destructive get）；调用方负责 republish 或丢弃。"""
    drained: list[tuple[BasicProperties | None, bytes]] = []
    cap = DRAIN_MAX_MESSAGES if max_count is None else min(max_count, DRAIN_MAX_MESSAGES)
    while len(drained) < cap:
        method, props, body = channel.basic_get(queue=queue_name, auto_ack=True)
        if method is None:
            break
        drained.append((props, body))
    return drained


def _republish_queue(
    channel: pika.channel.Channel,
    queue_name: str,
    messages: list[tuple[BasicProperties | None, bytes]],
) -> None:
    for props, body in messages:
        channel.basic_publish(
            exchange="",
            routing_key=queue_name,
            body=body,
            properties=props
            if props is not None
            else BasicProperties(delivery_mode=2, content_type="application/json"),
        )



def _collapse_duplicate_job_items(items: list[dict[str, Any]]) -> tuple[list[dict[str, Any]], int]:
    """展示用：同一 job_id 仅保留队头首条，并标注 duplicate_count。"""
    from collections import Counter

    raw_count = len(items)
    job_counts = Counter(item["job_id"] for item in items if item.get("job_id") is not None)
    collapsed: list[dict[str, Any]] = []
    seen_job_ids: set[int] = set()
    for item in items:
        jid = item.get("job_id")
        if jid is None:
            collapsed.append({**item, "duplicate_count": 1})
            continue
        if jid in seen_job_ids:
            continue
        seen_job_ids.add(jid)
        collapsed.append({**item, "duplicate_count": int(job_counts[jid])})
    return collapsed, raw_count


def peek_queue_messages(queue_name: str, *, limit: int = PEEK_LIMIT_DEFAULT) -> dict[str, Any]:
    assert_admin_queue_allowed(queue_name)
    limit = min(max(1, limit), PEEK_LIMIT_MAX)
    conn = open_blocking_connection()
    try:
        ch = conn.channel()
        _declare_admin_topologies(ch)
        total = _queue_message_count(ch, queue_name)
        take = min(limit, total, DRAIN_MAX_MESSAGES)
        drained = _drain_queue(ch, queue_name, max_count=take)
        items: list[dict[str, Any]] = []
        for index, (_props, body) in enumerate(drained):
            job_id, last_error, preview = _parse_message_body(body)
            items.append(
                {
                    "index": index,
                    "job_id": job_id,
                    "last_error": last_error,
                    "body_preview": preview,
                    "raw_body": body.decode("utf-8", errors="replace"),
                    "redelivered": False,
                }
            )
        _republish_queue(ch, queue_name, drained)
        total_after = _queue_message_count(ch, queue_name)
        raw_peek_count = len(items)
        items, _ = _collapse_duplicate_job_items(items)
        peek_count = len(items)
        truncated = total > raw_peek_count or total_after > raw_peek_count
        return {
            "queue_name": queue_name,
            "message_count": total_after,
            "peek_count": peek_count,
            "raw_peek_count": raw_peek_count,
            "items": items,
            "truncated": truncated,
        }
    except ChannelClosedByBroker as exc:
        raise ValueError(f"队列不可用: {queue_name}") from exc
    finally:
        try:
            if conn.is_open:
                conn.close()
        except Exception:
            pass


def mutate_queue_messages(
    queue_name: str,
    *,
    purge: bool = False,
    job_id: int | None = None,
    index: int | None = None,
) -> dict[str, Any]:
    assert_admin_queue_allowed(queue_name)
    if purge and (job_id is not None or index is not None):
        raise ValueError("purge 与 job_id/index 不能同时使用")
    if not purge and job_id is None and index is None:
        raise ValueError("请指定 purge、job_id 或 index")

    conn = open_blocking_connection()
    removed = 0
    try:
        ch = conn.channel()
        _declare_admin_topologies(ch)
        if purge:
            method = ch.queue_purge(queue=queue_name)
            removed = int(method.method.message_count)
            total = 0
        else:
            all_msgs = _drain_queue(ch, queue_name, max_count=None)
            if job_id is not None:
                kept: list[tuple[BasicProperties | None, bytes]] = []
                for props, body in all_msgs:
                    parsed_id, _, _ = _parse_message_body(body)
                    if parsed_id == job_id:
                        removed += 1
                    else:
                        kept.append((props, body))
            elif index is not None:
                if 0 <= index < len(all_msgs):
                    kept = all_msgs[:index] + all_msgs[index + 1 :]
                    removed = 1
                else:
                    kept = all_msgs
                    removed = 0
            else:
                kept = all_msgs
            _republish_queue(ch, queue_name, kept)
            total = len(kept)
        from services.rabbitmq_retry_dlq_snapshot_service import invalidate_retry_dlq_snapshot_for_queue

        result = {
            "queue_name": queue_name,
            "removed": removed,
            "message_count": total,
        }
        invalidate_retry_dlq_snapshot_for_queue(queue_name)
        return result
    except ChannelClosedByBroker as exc:
        raise ValueError(f"队列不可用: {queue_name}") from exc
    finally:
        try:
            if conn.is_open:
                conn.close()
        except Exception:
            pass


def _message_payload(body: bytes) -> dict[str, Any] | None:
    try:
        payload = json.loads(body.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError, TypeError):
        return None
    return payload if isinstance(payload, dict) else None


def _mutate_queue_messages_matching(
    queue_name: str,
    *,
    job_ids: set[int],
    file_id: int | None = None,
) -> dict[str, Any]:
    """Remove only well-formed messages matching the exact task identity.

    Messages with missing/invalid fields are always retained.  This is used by
    file deletion, where a broad text match could delete another file's task.
    """
    assert_admin_queue_allowed(queue_name)
    normalized_job_ids = {int(job_id) for job_id in job_ids}
    if not normalized_job_ids:
        return {"queue_name": queue_name, "removed": 0, "message_count": None}

    conn = open_blocking_connection()
    try:
        ch = conn.channel()
        _declare_admin_topologies(ch)
        all_msgs = _drain_queue(ch, queue_name, max_count=None)
        kept: list[tuple[BasicProperties | None, bytes]] = []
        removed = 0
        for props, body in all_msgs:
            payload = _message_payload(body)
            matches = False
            if payload is not None:
                try:
                    payload_job_id = int(payload["job_id"])
                    matches = payload_job_id in normalized_job_ids
                    if file_id is not None:
                        matches = matches and int(payload["file_id"]) == int(file_id)
                except (KeyError, TypeError, ValueError):
                    matches = False
            if matches:
                removed += 1
            else:
                kept.append((props, body))
        _republish_queue(ch, queue_name, kept)
        from services.rabbitmq_retry_dlq_snapshot_service import invalidate_retry_dlq_snapshot_for_queue

        invalidate_retry_dlq_snapshot_for_queue(queue_name)
        return {
            "queue_name": queue_name,
            "removed": removed,
            "message_count": len(kept),
        }
    except ChannelClosedByBroker as exc:
        raise ValueError(f"队列不可用: {queue_name}") from exc
    finally:
        try:
            if conn.is_open:
                conn.close()
        except Exception:
            pass


def mutate_queue_messages_by_job_ids(queue_name: str, *, job_ids: set[int]) -> dict[str, Any]:
    return _mutate_queue_messages_matching(queue_name, job_ids=job_ids)


def mutate_queue_messages_by_file_and_job_ids(
    queue_name: str,
    *,
    file_id: int,
    job_ids: set[int],
) -> dict[str, Any]:
    return _mutate_queue_messages_matching(queue_name, file_id=file_id, job_ids=job_ids)



def dedupe_queue_messages(queue_name: str) -> dict[str, Any]:
    """按 job_id 去重：保留队头首条，丢弃后续重复消息。"""
    assert_admin_queue_allowed(queue_name)
    conn = open_blocking_connection()
    removed = 0
    try:
        ch = conn.channel()
        _declare_admin_topologies(ch)
        all_msgs = _drain_queue(ch, queue_name, max_count=None)
        seen_job_ids: set[int] = set()
        kept: list[tuple[BasicProperties | None, bytes]] = []
        for props, body in all_msgs:
            parsed_id, _, _ = _parse_message_body(body)
            if parsed_id is not None:
                if parsed_id in seen_job_ids:
                    removed += 1
                    continue
                seen_job_ids.add(parsed_id)
            kept.append((props, body))
        _republish_queue(ch, queue_name, kept)
        total = _queue_message_count(ch, queue_name)
        from services.rabbitmq_retry_dlq_snapshot_service import invalidate_retry_dlq_snapshot_for_queue

        result = {
            "queue_name": queue_name,
            "removed": removed,
            "message_count": total,
        }
        invalidate_retry_dlq_snapshot_for_queue(queue_name)
        return result
    except ChannelClosedByBroker as exc:
        raise ValueError(f"队列不可用: {queue_name}") from exc
    finally:
        try:
            if conn.is_open:
                conn.close()
        except Exception:
            pass


def mq_queue_admin_unavailable_error(exc: Exception) -> str | None:
    if isinstance(exc, AMQPConnectionError):
        return str(exc)
    if isinstance(exc, RuntimeError) and "RABBITMQ_URL" in str(exc):
        return str(exc)
    return None
