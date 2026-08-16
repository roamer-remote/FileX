# Copyright (c) 2026 徐泽宇
"""RabbitMQ topology for KB text extract jobs (same exchange as index).

Authors:
    徐泽宇

Copyright:
    © 2026 徐泽宇
"""

from __future__ import annotations

import pika
from pika.adapters.blocking_connection import BlockingChannel

from config import RABBITMQ_URL
from messaging.kb_index_queues import EXCHANGE_MAIN, EXCHANGE_NOTIFY, QUEUE_NOTIFY_API, open_blocking_connection

ROUTING_KEY_EXTRACT = "extract"
ROUTING_KEY_RETRY = "extract.retry"
ROUTING_KEY_DLQ = "extract.dlq"

QUEUE_MAIN = "kb.extract"
QUEUE_RETRY = "kb.extract.retry"
QUEUE_DLQ = "kb.extract.dlq"

KB_EXTRACT_RETRY_TTL_MS = 30_000

__all__ = [
    "EXCHANGE_MAIN",
    "EXCHANGE_NOTIFY",
    "QUEUE_NOTIFY_API",
    "ROUTING_KEY_EXTRACT",
    "ROUTING_KEY_RETRY",
    "ROUTING_KEY_DLQ",
    "QUEUE_MAIN",
    "QUEUE_RETRY",
    "QUEUE_DLQ",
    "open_blocking_connection",
    "declare_kb_extract_topology",
]


def declare_kb_extract_topology(channel: BlockingChannel) -> None:
    from messaging.kb_index_queues import declare_kb_index_topology

    declare_kb_index_topology(channel)
    channel.queue_declare(queue=QUEUE_DLQ, durable=True)
    channel.queue_bind(queue=QUEUE_DLQ, exchange=EXCHANGE_MAIN, routing_key=ROUTING_KEY_DLQ)

    channel.queue_declare(
        queue=QUEUE_RETRY,
        durable=True,
        arguments={
            "x-message-ttl": KB_EXTRACT_RETRY_TTL_MS,
            "x-dead-letter-exchange": EXCHANGE_MAIN,
            "x-dead-letter-routing-key": ROUTING_KEY_EXTRACT,
        },
    )
    channel.queue_bind(queue=QUEUE_RETRY, exchange=EXCHANGE_MAIN, routing_key=ROUTING_KEY_RETRY)

    channel.queue_declare(queue=QUEUE_MAIN, durable=True)
    channel.queue_bind(queue=QUEUE_MAIN, exchange=EXCHANGE_MAIN, routing_key=ROUTING_KEY_EXTRACT)
