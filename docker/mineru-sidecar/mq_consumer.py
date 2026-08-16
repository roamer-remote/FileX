# Copyright (c) 2026 徐泽宇
"""kb.mineru RPC consumer (prefetch=1)."""
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
ROUTING_KEY_MINERU = "mineru"
QUEUE_MAIN = "kb.mineru"

_executor = ThreadPoolExecutor(max_workers=1, thread_name_prefix="mineru-parse")


def _max_mq_retries() -> int:
    return max(0, int(os.environ.get("MINERU_MQ_MAX_RETRIES", "2")))


def _mq_heartbeat_sec() -> int:
    return max(60, int(os.environ.get("MINERU_MQ_HEARTBEAT_SEC", "1800")))


def _open_consumer_connection(url: str) -> pika.BlockingConnection:
    params = pika.URLParameters(url)
    hb = _mq_heartbeat_sec()
    params.heartbeat = hb
    params.blocked_connection_timeout = hb
    return pika.BlockingConnection(params)


def _declare_topology(channel: pika.adapters.blocking_connection.BlockingChannel) -> None:
    channel.exchange_declare(exchange=EXCHANGE_MAIN, exchange_type="direct", durable=True)
    channel.queue_declare(queue=QUEUE_MAIN, durable=True)
    channel.queue_bind(queue=QUEUE_MAIN, exchange=EXCHANGE_MAIN, routing_key=ROUTING_KEY_MINERU)


def _retry_count(method, properties) -> int:
    """估算当前消息已被笔记侧处理的次数（用于 nack 上限）。

    nack+requeue 通常不会立刻写入 x-death；首次 redelivered 可能仅有
    method.redelivered=True。此处用 redelivered + x-death.count 估算，
    实际执行次数可能为 max_retries+1，属可接受偏差（见 FR-MQ-106）。
    """
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


def _mineru_device() -> str:
    return (os.environ.get("MINERU_DEVICE") or "cpu").strip().lower()


def _authorization_required() -> bool:
    """Only the GPU sidecar must reject RPCs without a scheduler lease context."""
    return _mineru_device() == "cuda"


def _normalize_file_path(file_path: str) -> str:
    """Map kb-extract RPC paths (/app/uploads) to sidecar UPLOAD_DIR (/uploads)."""
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
    from mineru_runner import SUPPORTED_RUNTIME_CONFIG_VERSION, run_mineru_pipeline
    from lifecycle_state import begin_execution, end_execution

    payload = json.loads(body.decode("utf-8"))
    version = payload.get("runtime_config_version")
    if version is not None and int(version) != SUPPORTED_RUNTIME_CONFIG_VERSION:
        raise ValueError(
            f"runtime_config_version_mismatch: expected {SUPPORTED_RUNTIME_CONFIG_VERSION}, got {version}"
        )
    # 164 §6（spec.md:100）：GPU sidecar 只接受带 lease/token/job 的授权 RPC。
    # 缺失即拒绝执行（ValueError 为非重试错误，消息直接丢弃），成功回包必须
    # 回传同一上下文，供 scheduler 侧校验请求往返绑定（validate_authorized_result）。
    gpu_lease_id = str(payload.get("gpu_lease_id") or "").strip()
    gpu_fencing_token = str(payload.get("fencing_token") or "").strip()
    gpu_job_id = str(payload.get("gpu_job_id") or "").strip()
    auth_fields = (gpu_lease_id, gpu_fencing_token, gpu_job_id)
    has_full_auth = all(auth_fields)
    if (_authorization_required() or any(auth_fields)) and not has_full_auth:
        raise ValueError(
            "mineru_authorization_context_missing: gpu_lease_id/fencing_token/gpu_job_id required"
        )
    file_path = _normalize_file_path(payload["file_path"])
    original_name = payload.get("original_name") or "document"
    file_id = payload.get("file_id")
    job_id = payload.get("job_id")
    if file_id is not None:
        file_id = int(file_id)
    if job_id is not None:
        job_id = int(job_id)
    bypass_cache = bool(payload.get("bypass_cache"))
    runtime_config = payload.get("runtime_config")
    begin_execution(
        gpu_lease_id=gpu_lease_id,
        fencing_token=gpu_fencing_token,
        gpu_job_id=gpu_job_id,
    )
    try:
        result = run_mineru_pipeline(
            file_path,
            original_name,
            file_id=file_id,
            job_id=job_id,
            bypass_cache=bypass_cache,
            runtime_config=runtime_config if isinstance(runtime_config, dict) else None,
        )
    finally:
        end_execution(gpu_job_id)
    if not isinstance(result, dict):
        raise RuntimeError("mineru pipeline returned a non-dict result")
    if has_full_auth:
        result["gpu_lease_id"] = gpu_lease_id
        result["fencing_token"] = gpu_fencing_token
        result["gpu_job_id"] = gpu_job_id
    return result


def _publish_reply(ch, reply_to: str, correlation_id: str | None, reply: dict) -> None:
    try:
        ch.basic_publish(
            exchange="",
            routing_key=reply_to,
            body=json.dumps(reply, ensure_ascii=False).encode("utf-8"),
            properties=pika.BasicProperties(
                content_type="application/json",
                correlation_id=correlation_id,
            ),
        )
    except Exception:
        # Long-running parse can leave the consumer channel in bad state (e.g. ack timeout
        # from RabbitMQ after 30min+). Fall back to a fresh short-lived connection for reply only.
        try:
            url = (os.environ.get("RABBITMQ_URL") or "").strip()
            if not url:
                raise RuntimeError("RABBITMQ_URL not set for reply fallback")
            reply_conn = _open_consumer_connection(url)
            try:
                reply_ch = reply_conn.channel()
                reply_ch.basic_publish(
                    exchange="",
                    routing_key=reply_to,
                    body=json.dumps(reply, ensure_ascii=False).encode("utf-8"),
                    properties=pika.BasicProperties(
                        content_type="application/json",
                        correlation_id=correlation_id,
                    ),
                )
                reply_ch.close()
            finally:
                if reply_conn.is_open:
                    try:
                        reply_conn.close()
                    except Exception:
                        pass
            logger.info("reply published via fresh connection for correlation_id=%s", correlation_id)
        except Exception as exc:
            logger.error("failed to publish reply even with fresh conn: %s", exc)
            raise


def _wait_parse_result(conn, future):
    """Run MinerU parse in worker thread; service AMQP heartbeats on main thread."""
    connection_lost: Exception | None = None
    while not future.done():
        try:
            conn.process_data_events(time_limit=1)
        except Exception as exc:
            logger.warning(
                "kb.mineru connection lost during parse wait job may redeliver: %s",
                exc,
            )
            connection_lost = exc
            break
    # Always wait for worker (incl. subprocess) before nack/reconnect.
    result = future.result()
    if connection_lost is not None:
        raise ConnectionError("AMQP connection lost during MinerU parse") from connection_lost
    return result


def _on_message(ch, method, properties, body: bytes) -> None:
    from mineru_runner import format_local_ts

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
        "mineru mq job received received_at=%s job_id=%s file_id=%s name=%s correlation_id=%s",
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
            "mineru mq job failed job_id=%s file_id=%s retry=%s",
            job_id,
            file_id,
            _retry_count(method, properties),
        )
        retries = _retry_count(method, properties)
        if _is_retryable(exc) and retries < _max_mq_retries():
            ch.basic_nack(delivery_tag=method.delivery_tag, requeue=True)
            logger.warning(
                "mineru mq nack requeue job_id=%s file_id=%s attempt=%s/%s",
                job_id,
                file_id,
                retries + 1,
                _max_mq_retries(),
            )
            return

        reply = {
            "ok": False,
            "error": "runtime_config_version_mismatch"
            if "runtime_config_version_mismatch" in str(exc)
            else "mineru_parse_failed",
            "detail": str(exc)[:2000],
            "correlation_id": correlation_id,
        }
        if reply_to:
            _publish_reply(ch, reply_to, correlation_id, reply)
        ch.basic_ack(delivery_tag=method.delivery_tag)


def _consumer_loop() -> None:
    url = (os.environ.get("RABBITMQ_URL") or "").strip()
    if not url:
        logger.warning("RABBITMQ_URL unset; kb.mineru consumer disabled")
        return

    prefetch = max(1, int(os.environ.get("MINERU_MAX_CONCURRENT", "1")))
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
                "kb.mineru consumer listening prefetch=%s MINERU_MQ_MAX_RETRIES=%s "
                "MINERU_MAX_CONCURRENT=%s MINERU_MQ_HEARTBEAT_SEC=%s "
                "MINERU_PARSE_TIMEOUT_SEC=%s MINERU_LOG_CLI=%s OMP_NUM_THREADS=%s",
                prefetch,
                _max_mq_retries(),
                prefetch,
                heartbeat,
                os.environ.get("MINERU_PARSE_TIMEOUT_SEC", "850"),
                os.environ.get("MINERU_LOG_CLI", "0"),
                os.environ.get("OMP_NUM_THREADS", "(default)"),
            )
            channel.start_consuming()
        except Exception:
            logger.exception("kb.mineru consumer error; reconnecting")
            time.sleep(3)
        finally:
            if connection is not None and connection.is_open:
                try:
                    connection.close()
                except Exception:
                    pass


def start_mq_consumer_thread() -> threading.Thread:
    thread = threading.Thread(target=_consumer_loop, name="kb-mineru-consumer", daemon=True)
    thread.start()
    return thread
