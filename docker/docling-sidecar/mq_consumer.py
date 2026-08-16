# Copyright (c) 2026 徐泽宇
"""kb.docling RPC consumer (prefetch=1)."""
from __future__ import annotations

import json
import logging
import os
import threading
import time
from concurrent.futures import ThreadPoolExecutor

import pika

logger = logging.getLogger(__name__)

EXCHANGE_MAIN = "filex.kb"
ROUTING_KEY_DOCLING = "docling"
QUEUE_MAIN = "kb.docling"

_executor = ThreadPoolExecutor(max_workers=1, thread_name_prefix="docling-parse")


def _max_mq_retries() -> int:
    return max(0, int(os.environ.get("DOCLING_MQ_MAX_RETRIES", "2")))


def _mq_heartbeat_sec() -> int:
    return max(60, int(os.environ.get("DOCLING_MQ_HEARTBEAT_SEC", "1800")))


def _open_consumer_connection(url: str) -> pika.BlockingConnection:
    params = pika.URLParameters(url)
    hb = _mq_heartbeat_sec()
    params.heartbeat = hb
    params.blocked_connection_timeout = hb
    return pika.BlockingConnection(params)


def _declare_topology(channel: pika.adapters.blocking_connection.BlockingChannel) -> None:
    channel.exchange_declare(exchange=EXCHANGE_MAIN, exchange_type="direct", durable=True)
    channel.queue_declare(queue=QUEUE_MAIN, durable=True)
    channel.queue_bind(queue=QUEUE_MAIN, exchange=EXCHANGE_MAIN, routing_key=ROUTING_KEY_DOCLING)


def _retry_count(method, properties) -> int:
    if not getattr(method, "redelivered", False):
        return 0
    headers = getattr(properties, "headers", None) or {}
    for death in headers.get("x-death") or []:
        if death.get("queue") == QUEUE_MAIN:
            return int(death.get("count", 0))
    return 1


def _is_retryable(exc: Exception) -> bool:
    if isinstance(exc, (json.JSONDecodeError, KeyError, ValueError, FileNotFoundError)):
        return False
    return True


def _normalize_file_path(file_path: str) -> str:
    upload_dir = (os.environ.get("UPLOAD_DIR") or "/uploads").rstrip("/")
    legacy_prefix = "/app/uploads"
    path = file_path.strip()
    if path == legacy_prefix or path.startswith(legacy_prefix + "/"):
        suffix = path[len(legacy_prefix) :]
        if suffix and not suffix.startswith("/"):
            suffix = "/" + suffix
        return upload_dir + suffix
    return path


def _handle_message(body: bytes) -> dict:
    from docling_runner import run_docling_pipeline

    payload = json.loads(body.decode("utf-8"))
    file_path = _normalize_file_path(payload["file_path"])
    original_name = payload.get("original_name") or "document"
    file_id = payload.get("file_id")
    job_id = payload.get("job_id")
    if file_id is not None:
        file_id = int(file_id)
    if job_id is not None:
        job_id = int(job_id)
    bypass_cache = bool(payload.get("bypass_cache"))
    return run_docling_pipeline(
        file_path,
        original_name,
        file_id=file_id,
        job_id=job_id,
        bypass_cache=bypass_cache,
    )


def _publish_reply(ch, reply_to: str, correlation_id: str | None, reply: dict) -> None:
    ch.basic_publish(
        exchange="",
        routing_key=reply_to,
        body=json.dumps(reply, ensure_ascii=False).encode("utf-8"),
        properties=pika.BasicProperties(
            content_type="application/json",
            correlation_id=correlation_id,
        ),
    )


def _wait_parse_result(conn, future):
    connection_lost: Exception | None = None
    while not future.done():
        try:
            conn.process_data_events(time_limit=1)
        except Exception as exc:
            logger.warning(
                "kb.docling connection lost during parse wait job may redeliver: %s",
                exc,
            )
            connection_lost = exc
            break
    result = future.result()
    if connection_lost is not None:
        raise ConnectionError("AMQP connection lost during Docling parse") from connection_lost
    return result


def _on_message(ch, method, properties, body: bytes) -> None:
    from docling_runner import format_local_ts

    reply_to = properties.reply_to
    correlation_id = properties.correlation_id
    job_id = None
    file_id = None
    original_name = None
    try:
        preview = json.loads(body.decode("utf-8"))
        job_id = preview.get("job_id")
        file_id = preview.get("file_id")
        original_name = preview.get("original_name")
    except Exception:
        pass

    mq_received_at = format_local_ts()
    logger.info(
        "docling mq job received received_at=%s job_id=%s file_id=%s name=%s correlation_id=%s",
        mq_received_at,
        job_id,
        file_id,
        original_name,
        correlation_id,
    )

    conn = ch.connection
    future = _executor.submit(_handle_message, body)
    try:
        result = _wait_parse_result(conn, future)
        contract = {k: v for k, v in result.items() if k != "ok"}
        reply = {**contract, "ok": True, "correlation_id": correlation_id}
        if reply_to:
            _publish_reply(ch, reply_to, correlation_id, reply)
        ch.basic_ack(delivery_tag=method.delivery_tag)
        return
    except Exception as exc:
        logger.exception(
            "docling mq job failed job_id=%s file_id=%s retry=%s",
            job_id,
            file_id,
            _retry_count(method, properties),
        )
        retries = _retry_count(method, properties)
        if _is_retryable(exc) and retries < _max_mq_retries():
            ch.basic_nack(delivery_tag=method.delivery_tag, requeue=True)
            logger.warning(
                "docling mq nack requeue job_id=%s file_id=%s attempt=%s/%s",
                job_id,
                file_id,
                retries + 1,
                _max_mq_retries(),
            )
            return

        reply = {
            "ok": False,
            "error": "docling_parse_failed",
            "detail": str(exc)[:2000],
            "correlation_id": correlation_id,
        }
        if reply_to:
            _publish_reply(ch, reply_to, correlation_id, reply)
        ch.basic_ack(delivery_tag=method.delivery_tag)


def _consumer_loop() -> None:
    url = (os.environ.get("RABBITMQ_URL") or "").strip()
    if not url:
        logger.warning("RABBITMQ_URL unset; kb.docling consumer disabled")
        return

    prefetch = max(1, int(os.environ.get("DOCLING_MAX_CONCURRENT", "1")))
    heartbeat = _mq_heartbeat_sec()
    while True:
        connection = None
        try:
            connection = _open_consumer_connection(url)
            channel = connection.channel()
            _declare_topology(channel)
            channel.basic_qos(prefetch_count=prefetch)
            channel.basic_consume(queue=QUEUE_MAIN, on_message_callback=_on_message, auto_ack=False)
            logger.info(
                "kb.docling consumer listening prefetch=%s DOCLING_MQ_MAX_RETRIES=%s "
                "DOCLING_MAX_CONCURRENT=%s DOCLING_MQ_HEARTBEAT_SEC=%s DOCLING_PARSE_TIMEOUT_SEC=%s",
                prefetch,
                _max_mq_retries(),
                prefetch,
                heartbeat,
                os.environ.get("DOCLING_PARSE_TIMEOUT_SEC", "550"),
            )
            channel.start_consuming()
        except Exception:
            logger.exception("kb.docling consumer error; reconnecting")
            time.sleep(3)
        finally:
            if connection is not None and connection.is_open:
                try:
                    connection.close()
                except Exception:
                    pass


def start_mq_consumer_thread() -> threading.Thread:
    thread = threading.Thread(target=_consumer_loop, name="kb-docling-consumer", daemon=True)
    thread.start()
    return thread
