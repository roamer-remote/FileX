# Copyright (c) 2026 徐泽宇
"""Fanout consumer: RabbitMQ notify -> WebSocket clients.

Authors:
    徐泽宇

Copyright:
    © 2026 徐泽宇
"""

from __future__ import annotations

import json
import logging
import threading

import pika

from messaging.kb_index_queues import QUEUE_NOTIFY_API, declare_kb_index_topology, open_blocking_connection
from messaging.kb_post_queues import QUEUE_POST_NOTIFY_API, declare_kb_post_topology
from messaging.kb_ws_notify_buffer import kb_ws_notify_replay_buffer
from messaging.mq_progress_notify import is_progress_notify, is_terminal_kb_notify
from messaging.mq_task_progress import clear_progress, set_progress
from messaging.ws_manager import kb_index_ws_manager

logger = logging.getLogger(__name__)

_stop = threading.Event()
_thread: threading.Thread | None = None
_connection: pika.BlockingConnection | None = None



def notify_payload_to_ws_event(payload: dict) -> dict:
    """Map RabbitMQ notify JSON to WebSocket event (subset forwarded to clients)."""
    event: dict = {
        "type": payload.get("type", "kb_index_updated"),
        "file_id": payload.get("file_id"),
    }
    for key in (
        "index_status",
        "chunk_count",
        "index_error",
        "extract_status",
        "extract_error",
        "has_md",
        "md_has_content",
        "preview_mime_type",
        "processing_duration_ms",
        "kb_post_status",
        "kb_post_error",
        "post_entity_ms",
        "post_sag_ms",
        "post_raptor_ms",
        "post_skip_reason",
    ):
        if key in payload:
            event[key] = payload[key]
    return event


def _apply_progress_notify(payload: dict) -> None:
    file_id = int(payload["file_id"])
    set_progress(
        file_id,
        kind=str(payload.get("kind", "")),
        progress_stage=str(payload.get("progress_stage", "")),
        progress_pct=payload.get("progress_pct"),
        progress_detail=payload.get("progress_detail"),
    )


def _request_mq_refresh() -> None:
    try:
        from messaging.mq_status_watcher import request_refresh

        request_refresh()
    except Exception:
        pass


def _on_notify(ch, method, _properties, body: bytes) -> None:
    try:
        payload = json.loads(body.decode("utf-8"))
        user_id = int(payload["user_id"])
    except (json.JSONDecodeError, KeyError, TypeError, ValueError):
        logger.warning("invalid kb index notify payload: %r", body[:200])
        ch.basic_ack(delivery_tag=method.delivery_tag)
        return

    if is_progress_notify(payload):
        try:
            _apply_progress_notify(payload)
        except (KeyError, TypeError, ValueError):
            logger.warning("invalid kb progress notify payload: %r", body[:200])
        else:
            _request_mq_refresh()
        ch.basic_ack(delivery_tag=method.delivery_tag)
        return

    file_id = payload.get("file_id")
    if file_id is not None and is_terminal_kb_notify(payload):
        clear_progress(int(file_id))
        try:
            from messaging.mq_progress_notify import clear_throttle_state

            clear_throttle_state(int(file_id))
        except Exception:
            pass

    event = notify_payload_to_ws_event(payload)
    kb_ws_notify_replay_buffer.append(user_id, event)
    kb_index_ws_manager.broadcast_sync(user_id, event)
    _request_mq_refresh()
    ch.basic_ack(delivery_tag=method.delivery_tag)


def _run() -> None:
    global _connection
    while not _stop.is_set():
        try:
            _connection = open_blocking_connection()
            ch = _connection.channel()
            declare_kb_index_topology(ch)
            declare_kb_post_topology(ch)
            ch.basic_qos(prefetch_count=10)
            ch.basic_consume(queue=QUEUE_NOTIFY_API, on_message_callback=_on_notify, auto_ack=False)
            ch.basic_consume(queue=QUEUE_POST_NOTIFY_API, on_message_callback=_on_notify, auto_ack=False)
            logger.info(
                "kb notify consumer started on %s and %s",
                QUEUE_NOTIFY_API,
                QUEUE_POST_NOTIFY_API,
            )
            while not _stop.is_set():
                _connection.process_data_events(time_limit=1)
        except Exception:
            if _stop.is_set():
                break
            logger.exception("kb index notify consumer error; reconnecting in 3s")
            _stop.wait(3)
        finally:
            try:
                if _connection and _connection.is_open:
                    _connection.close()
            except Exception:
                pass
            _connection = None


def start_notify_consumer() -> None:
    global _thread
    if _thread and _thread.is_alive():
        return
    _stop.clear()
    _thread = threading.Thread(target=_run, name="kb-index-notify", daemon=True)
    _thread.start()


def stop_notify_consumer() -> None:
    _stop.set()
    global _connection
    try:
        if _connection and _connection.is_open:
            _connection.close()
    except Exception:
        pass
    if _thread:
        _thread.join(timeout=5)
