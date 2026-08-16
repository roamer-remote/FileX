# Copyright (c) 2026 徐泽宇
"""RabbitMQ topology for GPU scheduler routes (164 §6).

``filex.gpu.mineru`` / ``filex.gpu.raptor`` are the durable route queues that
only the GPU scheduler consumes. A route message is published only after the
dispatch owner fences a fresh ``gpu_leases`` row, so consumers never execute a
job without a lease. Every message carries ``job_id``, ``job_kind``,
``file_id``, ``idempotency_key`` and ``attempt`` (plus ``handover_epoch`` for
the migration handover contract).
"""

from __future__ import annotations

import json
import logging

import pika
from pika.adapters.blocking_connection import BlockingChannel

from messaging.kb_index_queues import EXCHANGE_MAIN, open_blocking_connection

logger = logging.getLogger(__name__)

ROUTING_KEY_GPU_MINERU = "gpu.mineru"
ROUTING_KEY_GPU_RAPTOR = "gpu.raptor"

QUEUE_GPU_MINERU = "filex.gpu.mineru"
QUEUE_GPU_RAPTOR = "filex.gpu.raptor"

GPU_ROUTE_JOB_KINDS = {
    "mineru": ROUTING_KEY_GPU_MINERU,
    "raptor": ROUTING_KEY_GPU_RAPTOR,
}

GPU_ROUTE_REQUIRED_FIELDS = (
    "job_id",
    "job_kind",
    "file_id",
    "idempotency_key",
    "attempt",
    "handover_epoch",
)

__all__ = [
    "EXCHANGE_MAIN",
    "ROUTING_KEY_GPU_MINERU",
    "ROUTING_KEY_GPU_RAPTOR",
    "QUEUE_GPU_MINERU",
    "QUEUE_GPU_RAPTOR",
    "GPU_ROUTE_JOB_KINDS",
    "GPU_ROUTE_REQUIRED_FIELDS",
    "open_blocking_connection",
    "declare_gpu_topology",
    "validate_gpu_route_payload",
    "parse_gpu_route_body",
    "publish_gpu_route_message",
]


def declare_gpu_topology(channel: BlockingChannel) -> None:
    """Declare the two durable scheduler route queues (idempotent)."""
    from messaging.kb_index_queues import declare_kb_index_topology

    declare_kb_index_topology(channel)
    for queue, routing_key in (
        (QUEUE_GPU_MINERU, ROUTING_KEY_GPU_MINERU),
        (QUEUE_GPU_RAPTOR, ROUTING_KEY_GPU_RAPTOR),
    ):
        channel.queue_declare(queue=queue, durable=True)
        channel.queue_bind(queue=queue, exchange=EXCHANGE_MAIN, routing_key=routing_key)


def validate_gpu_route_payload(payload: dict) -> dict:
    """Validate the mandatory GPU route message contract (164 §6)."""
    if not isinstance(payload, dict):
        raise ValueError("gpu route payload must be a dict")
    missing = [
        field
        for field in GPU_ROUTE_REQUIRED_FIELDS
        if payload.get(field) in (None, "")
    ]
    if missing:
        raise ValueError(f"gpu route payload missing fields: {', '.join(missing)}")
    job_kind = str(payload["job_kind"])
    if job_kind not in GPU_ROUTE_JOB_KINDS:
        raise ValueError(f"unsupported gpu route job_kind={job_kind!r}")
    return payload


def parse_gpu_route_body(body: bytes) -> dict:
    payload = json.loads(body.decode("utf-8"))
    return validate_gpu_route_payload(payload)


def _publish(
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
        declare_gpu_topology(ch)
        ch.basic_publish(
            exchange=EXCHANGE_MAIN,
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


def publish_gpu_route_message(
    job_kind: str,
    payload: dict,
    *,
    connection: pika.BlockingConnection | None = None,
) -> None:
    """Publish one GPU route to the scheduler-owned ``filex.gpu.*`` queue."""
    normalized = dict(payload)
    normalized.setdefault("job_kind", job_kind)
    validate_gpu_route_payload(normalized)
    routing_key = GPU_ROUTE_JOB_KINDS[str(job_kind)]
    _publish(routing_key, normalized, connection=connection)
