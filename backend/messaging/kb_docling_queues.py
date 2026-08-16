# Copyright (c) 2026 徐泽宇
"""RabbitMQ topology for Docling sidecar RPC (P0: main queue only)."""

from __future__ import annotations

from pika.adapters.blocking_connection import BlockingChannel

from messaging.kb_index_queues import EXCHANGE_MAIN, declare_kb_index_topology, open_blocking_connection

ROUTING_KEY_DOCLING = "docling"
QUEUE_MAIN = "kb.docling"

__all__ = [
    "EXCHANGE_MAIN",
    "ROUTING_KEY_DOCLING",
    "QUEUE_MAIN",
    "open_blocking_connection",
    "declare_kb_docling_topology",
]


def declare_kb_docling_topology(channel: BlockingChannel) -> None:
    declare_kb_index_topology(channel)
    channel.queue_declare(queue=QUEUE_MAIN, durable=True)
    channel.queue_bind(queue=QUEUE_MAIN, exchange=EXCHANGE_MAIN, routing_key=ROUTING_KEY_DOCLING)
