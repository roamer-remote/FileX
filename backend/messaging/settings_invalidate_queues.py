# Copyright (c) 2026 徐泽宇
"""RabbitMQ fanout topology for cross-process system settings cache invalidation."""

from __future__ import annotations

import pika
from pika.adapters.blocking_connection import BlockingChannel

from messaging.kb_index_queues import open_blocking_connection

EXCHANGE_SETTINGS_INVALIDATE = "filex.settings.invalidate"

QUEUE_SETTINGS_INVALIDATE_KB_POST = "filex.settings.invalidate.kb-post"
QUEUE_SETTINGS_INVALIDATE_KB_INDEXER = "filex.settings.invalidate.kb-indexer"
QUEUE_SETTINGS_INVALIDATE_KB_EXTRACT = "filex.settings.invalidate.kb-extract"
QUEUE_SETTINGS_INVALIDATE_KB_RAGAS_EVAL = "filex.settings.invalidate.kb-ragas-eval"

SERVICE_QUEUE_NAMES: dict[str, str] = {
    "kb-post": QUEUE_SETTINGS_INVALIDATE_KB_POST,
    "kb-indexer": QUEUE_SETTINGS_INVALIDATE_KB_INDEXER,
    "kb-extract": QUEUE_SETTINGS_INVALIDATE_KB_EXTRACT,
    "kb-ragas-eval": QUEUE_SETTINGS_INVALIDATE_KB_RAGAS_EVAL,
}


def declare_settings_invalidate_exchange(channel: BlockingChannel) -> None:
    channel.exchange_declare(
        exchange=EXCHANGE_SETTINGS_INVALIDATE,
        exchange_type="fanout",
        durable=True,
    )


def bind_settings_invalidate_queue(
    channel: BlockingChannel,
    *,
    service: str | None,
) -> str:
    """Return queue name bound to the fanout exchange.

    Singleton workers pass ``service`` (durable shared queue). The filex API
    process passes ``service=None`` for an exclusive auto-delete queue so each
    uvicorn worker receives its own copy.
    """
    declare_settings_invalidate_exchange(channel)
    if service is None:
        result = channel.queue_declare(queue="", exclusive=True, auto_delete=True)
        queue_name = str(result.method.queue)
    else:
        queue_name = SERVICE_QUEUE_NAMES.get(service)
        if not queue_name:
            raise ValueError(f"unknown settings invalidate service: {service}")
        channel.queue_declare(queue=queue_name, durable=True)
    channel.queue_bind(queue=queue_name, exchange=EXCHANGE_SETTINGS_INVALIDATE)
    return queue_name
