# Copyright (c) 2026 徐泽宇
"""RabbitMQ topology for KB vector index jobs (declare idempotently).

Authors:
    徐泽宇

Copyright:
    © 2026 徐泽宇
"""

from __future__ import annotations

import pika
from pika.adapters.blocking_connection import BlockingChannel

from config import RABBITMQ_URL

EXCHANGE_MAIN = "filex.kb"
ROUTING_KEY_INDEX = "index"
ROUTING_KEY_RETRY = "retry"
ROUTING_KEY_DLQ = "dlq"

QUEUE_MAIN = "kb.index"
QUEUE_RETRY = "kb.index.retry"
QUEUE_DLQ = "kb.index.dlq"

EXCHANGE_NOTIFY = "kb.index.notify"
QUEUE_NOTIFY_API = "kb.index.notify.api"

KB_INDEX_RETRY_TTL_MS = 30_000


def open_blocking_connection() -> pika.BlockingConnection:
    if not RABBITMQ_URL:
        raise RuntimeError("RABBITMQ_URL 未设置，无法连接 RabbitMQ")
    params = pika.URLParameters(RABBITMQ_URL)
    return pika.BlockingConnection(params)


def declare_kb_index_topology(channel: BlockingChannel) -> None:
    channel.exchange_declare(exchange=EXCHANGE_MAIN, exchange_type="direct", durable=True)
    channel.exchange_declare(exchange=EXCHANGE_NOTIFY, exchange_type="fanout", durable=True)

    channel.queue_declare(queue=QUEUE_DLQ, durable=True)
    channel.queue_bind(queue=QUEUE_DLQ, exchange=EXCHANGE_MAIN, routing_key=ROUTING_KEY_DLQ)

    channel.queue_declare(
        queue=QUEUE_RETRY,
        durable=True,
        arguments={
            "x-message-ttl": KB_INDEX_RETRY_TTL_MS,
            "x-dead-letter-exchange": EXCHANGE_MAIN,
            "x-dead-letter-routing-key": ROUTING_KEY_INDEX,
        },
    )
    channel.queue_bind(queue=QUEUE_RETRY, exchange=EXCHANGE_MAIN, routing_key=ROUTING_KEY_RETRY)

    channel.queue_declare(queue=QUEUE_MAIN, durable=True)
    channel.queue_bind(queue=QUEUE_MAIN, exchange=EXCHANGE_MAIN, routing_key=ROUTING_KEY_INDEX)

    channel.queue_declare(queue=QUEUE_NOTIFY_API, durable=True)
    channel.queue_bind(queue=QUEUE_NOTIFY_API, exchange=EXCHANGE_NOTIFY)
