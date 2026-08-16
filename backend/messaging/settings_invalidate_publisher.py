# Copyright (c) 2026 徐泽宇
"""Publish system settings cache invalidation to worker processes."""

from __future__ import annotations

import json
import logging

import pika

from messaging.kb_index_queues import open_blocking_connection
from messaging.settings_invalidate_queues import (
    EXCHANGE_SETTINGS_INVALIDATE,
    declare_settings_invalidate_exchange,
)
from utils.timezone import beijing_now

logger = logging.getLogger(__name__)


def publish_settings_cache_invalidate(*, connection: pika.BlockingConnection | None = None) -> None:
    """Fanout invalidate event; failures are logged and must not break admin saves."""
    body = json.dumps(
        {
            "event": "settings_cache_invalidate",
            "ts": beijing_now().isoformat(),
        }
    ).encode("utf-8")
    owns_connection = connection is None
    try:
        if connection is None:
            connection = open_blocking_connection()
        channel = connection.channel()
        declare_settings_invalidate_exchange(channel)
        channel.basic_publish(
            exchange=EXCHANGE_SETTINGS_INVALIDATE,
            routing_key="",
            body=body,
            properties=pika.BasicProperties(content_type="application/json", delivery_mode=1),
        )
        logger.info("published settings cache invalidate fanout")
    except Exception:
        logger.warning("publish settings cache invalidate failed", exc_info=True)
    finally:
        if owns_connection and connection is not None:
            try:
                if connection.is_open:
                    connection.close()
            except Exception:
                pass
