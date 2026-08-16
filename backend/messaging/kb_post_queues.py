# Copyright (c) 2026 徐泽宇
"""RabbitMQ topology for KB post jobs (114)."""

from __future__ import annotations

import pika
from pika.adapters.blocking_connection import BlockingChannel

from config import RABBITMQ_URL

from messaging.kb_index_queues import EXCHANGE_MAIN, open_blocking_connection

ROUTING_KEY_POST = "post"
ROUTING_KEY_POST_RETRY = "post.retry"
ROUTING_KEY_POST_DLQ = "post.dlq"

QUEUE_MAIN = "kb.post"
QUEUE_RETRY = "kb.post.retry"
QUEUE_DLQ = "kb.post.dlq"

EXCHANGE_POST_NOTIFY = "kb.post.notify"
QUEUE_POST_NOTIFY_API = "kb.post.notify.api"

KB_POST_RETRY_TTL_MS = 30_000


def declare_kb_post_topology(channel: BlockingChannel) -> None:
    from messaging.kb_index_queues import declare_kb_index_topology

    declare_kb_index_topology(channel)

    channel.exchange_declare(exchange=EXCHANGE_POST_NOTIFY, exchange_type="fanout", durable=True)

    channel.queue_declare(queue=QUEUE_DLQ, durable=True)
    channel.queue_bind(queue=QUEUE_DLQ, exchange=EXCHANGE_MAIN, routing_key=ROUTING_KEY_POST_DLQ)

    channel.queue_declare(
        queue=QUEUE_RETRY,
        durable=True,
        arguments={
            "x-message-ttl": KB_POST_RETRY_TTL_MS,
            "x-dead-letter-exchange": EXCHANGE_MAIN,
            "x-dead-letter-routing-key": ROUTING_KEY_POST,
        },
    )
    channel.queue_bind(queue=QUEUE_RETRY, exchange=EXCHANGE_MAIN, routing_key=ROUTING_KEY_POST_RETRY)

    channel.queue_declare(queue=QUEUE_MAIN, durable=True)
    channel.queue_bind(queue=QUEUE_MAIN, exchange=EXCHANGE_MAIN, routing_key=ROUTING_KEY_POST)

    channel.queue_declare(queue=QUEUE_POST_NOTIFY_API, durable=True)
    channel.queue_bind(queue=QUEUE_POST_NOTIFY_API, exchange=EXCHANGE_POST_NOTIFY)
