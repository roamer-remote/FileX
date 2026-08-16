# Copyright (c) 2026 徐泽宇
"""Fanout consumer: settings invalidate -> in-process cache clear."""

from __future__ import annotations

import json
import logging
import threading

import pika

from messaging.kb_index_queues import open_blocking_connection
from messaging.settings_invalidate_queues import bind_settings_invalidate_queue

logger = logging.getLogger(__name__)

_stop = threading.Event()
_thread: threading.Thread | None = None
_connection: pika.BlockingConnection | None = None
_service: str | None = None


def apply_settings_cache_invalidate() -> None:
    """Clear in-process settings and dependent runtime caches (no re-broadcast)."""
    from services.system_setting_service import invalidate_all_settings_caches

    invalidate_all_settings_caches(broadcast=False)
    logger.info("applied settings cache invalidate")


def _on_message(ch, method, _properties, body: bytes) -> None:
    try:
        payload = json.loads(body.decode("utf-8"))
        if payload.get("event") != "settings_cache_invalidate":
            logger.warning("ignored settings invalidate payload: %r", body[:200])
    except (json.JSONDecodeError, UnicodeDecodeError):
        logger.warning("invalid settings invalidate payload: %r", body[:200])
    else:
        apply_settings_cache_invalidate()
    ch.basic_ack(delivery_tag=method.delivery_tag)


def _run() -> None:
    global _connection
    while not _stop.is_set():
        try:
            _connection = open_blocking_connection()
            ch = _connection.channel()
            queue_name = bind_settings_invalidate_queue(ch, service=_service)
            ch.basic_qos(prefetch_count=10)
            ch.basic_consume(queue=queue_name, on_message_callback=_on_message, auto_ack=False)
            logger.info(
                "settings invalidate consumer started service=%s queue=%s",
                _service or "filex",
                queue_name,
            )
            while not _stop.is_set():
                _connection.process_data_events(time_limit=1)
        except Exception:
            if _stop.is_set():
                break
            logger.exception("settings invalidate consumer error; reconnecting in 3s")
            _stop.wait(3)
        finally:
            try:
                if _connection and _connection.is_open:
                    _connection.close()
            except Exception:
                pass
            _connection = None


def start_settings_invalidate_consumer(*, service: str | None) -> None:
    """Start background fanout listener (idempotent)."""
    global _thread, _service
    if _thread and _thread.is_alive():
        return
    _service = service
    _stop.clear()
    _thread = threading.Thread(
        target=_run,
        name=f"settings-invalidate-{service or 'filex'}",
        daemon=True,
    )
    _thread.start()


def stop_settings_invalidate_consumer() -> None:
    _stop.set()
    global _connection
    try:
        if _connection and _connection.is_open:
            _connection.close()
    except Exception:
        pass
    if _thread:
        _thread.join(timeout=5)
