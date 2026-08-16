# Copyright (c) 2026 徐泽宇
"""MQ RPC client for MinerU sidecar (kb.mineru).

Authors:
    徐泽宇

Copyright:
    © 2026 徐泽宇
"""

from __future__ import annotations

import contextvars
import json
import logging
import uuid
from typing import Any

import pika
from sqlalchemy.orm import Session

from messaging.kb_mineru_queues import (
    EXCHANGE_MAIN,
    ROUTING_KEY_MINERU,
    declare_kb_mineru_topology,
    open_blocking_connection,
)
from services.kb_mineru_inflight import clear_mineru_inflight, register_mineru_inflight
from services.md_paths import resolve_upload_path
from services.mineru_config_service import (
    RUNTIME_CONFIG_VERSION,
    get_mineru_runtime_config,
    pdf_page_count,
    resolve_effective_rpc_timeout_sec,
    runtime_config_to_payload,
)
from services.gpu_model_lifecycle_service import (
    GpuExecutionContext,
    GpuModelSchedulerAdapter,
    GpuOomError,
    ModelGroup,
    ModelLifecycleError,
    validate_authorized_result,
)


def _to_mineru_sidecar_path(raw_path: str) -> str:
    """Return the path that the filex-mineru container can open.

    We mount the uploads volume at /uploads inside the sidecar (see docker-compose.local.yml
    and production compose). The payload must use /uploads/<rel> form, not the host absolute
    path or the API container's /app/uploads path.
    """
    p = resolve_upload_path(raw_path) or raw_path
    normalized = p.replace("\\", "/")
    # Strip any known uploads root and force /uploads prefix
    for anchor in ("/uploads/", "/app/uploads/", "/backend/uploads/"):
        if anchor in normalized:
            rel = normalized.split(anchor, 1)[1].lstrip("/")
            return "/uploads/" + rel
    if normalized.startswith("/uploads/"):
        return normalized
    # Fallback: use last two path segments under uploads if possible
    if "/uploads/" in normalized:
        rel = normalized.split("/uploads/", 1)[1]
        return "/uploads/" + rel.lstrip("/")
    # Last resort
    base = normalized.rsplit("/", 1)[-1] if "/" in normalized else normalized
    return "/uploads/1/unknown/" + base  # will likely fail, but won't be a huge host path


logger = logging.getLogger(__name__)

_consumer_keepalive_connection: contextvars.ContextVar[pika.BlockingConnection | None] = (
    contextvars.ContextVar("kb_extract_consumer_keepalive", default=None)
)


def bind_consumer_keepalive_connection(
    connection: pika.BlockingConnection | None,
) -> contextvars.Token:
    """Register kb.extract consumer connection for heartbeat during long MinerU RPC."""
    return _consumer_keepalive_connection.set(connection)


def reset_consumer_keepalive_connection(token: contextvars.Token) -> None:
    _consumer_keepalive_connection.reset(token)


def _process_consumer_keepalive() -> None:
    keepalive = _consumer_keepalive_connection.get()
    if keepalive is None or not keepalive.is_open:
        return
    try:
        keepalive.process_data_events(time_limit=0)
    except Exception:
        logger.debug("consumer keepalive process_data_events failed", exc_info=True)


def _lookup_mineru_username(job_id: int | None) -> str | None:
    if job_id is None:
        return None
    from database import SessionLocal
    from models.kb_extract_job import KbExtractJob
    from models.user import User

    db = SessionLocal()
    try:
        row = (
            db.query(User.username)
            .join(KbExtractJob, KbExtractJob.user_id == User.id)
            .filter(KbExtractJob.id == int(job_id))
            .first()
        )
        return row[0] if row else None
    finally:
        db.close()


class MineruRpcError(RuntimeError):
    """MinerU MQ RPC failed."""


class MineruRpcTimeout(MineruRpcError):
    """MinerU MQ RPC timed out waiting for sidecar reply."""


def _resolve_rpc_timeouts(
    *,
    db: Session | None,
    file_path: str,
) -> tuple[int, float, Any]:
    if db is None:
        from database import SessionLocal

        db = SessionLocal()
        close_db = True
    else:
        close_db = False
    try:
        cfg = get_mineru_runtime_config(db, fresh=True)
        # Resolve container-style paths (e.g. /app/uploads/...) to the current process's UPLOAD_DIR.
        # Critical for host-side kb-extract when API container persisted /app/uploads paths.
        resolved_path = resolve_upload_path(file_path) or file_path
        try:
            pages = pdf_page_count(resolved_path)
        except Exception:
            logger.warning("mineru rpc: failed to read page_count for %s", file_path, exc_info=True)
            pages = None
        effective_sec = resolve_effective_rpc_timeout_sec(cfg, page_count=pages or 0)
        timeout_ms = max(1, int(effective_sec)) * 1000
        return timeout_ms, effective_sec, cfg
    finally:
        if close_db:
            db.close()


def call_mineru_extract(
    *,
    job_id: int | None,
    file_id: int,
    file_path: str,
    original_name: str,
    bypass_cache: bool = False,
    db: Session | None = None,
    gpu_scheduler: GpuModelSchedulerAdapter | None = None,
    gpu_context: GpuExecutionContext | None = None,
) -> dict[str, Any]:
    """Execute MinerU through the scheduler when a GPU owner is supplied.

    The legacy direct call remains available for CPU/debug compatibility; any
    scheduler-backed GPU call must carry and validate lease/token/job context.
    """
    if gpu_scheduler is not None:
        if gpu_context is None:
            raise ValueError("gpu_context is required for scheduler-backed MinerU execution")
        gpu_scheduler.switch_to(ModelGroup.MINERU, gpu_context)
        gpu_scheduler.acquire_batch(ModelGroup.MINERU, [str(job_id or file_id)], gpu_context)
        try:
            result = gpu_scheduler.execute(
                ModelGroup.MINERU,
                gpu_context,
                call=lambda: _call_mineru_extract_direct(
                    job_id=job_id,
                    file_id=file_id,
                    file_path=file_path,
                    original_name=original_name,
                    bypass_cache=bypass_cache,
                    db=db,
                    gpu_context=gpu_context,
                ),
                _validate_result=validate_authorized_result,
            )
        except GpuOomError:
            # OOM 已由 adapter 释放模型组并重新探测显存；分类必须保留到 job 层，
            # 不能降级为普通 RPC 错误（否则会触发 CPU fallback 或普通重试）。
            raise
        except ModelLifecycleError as exc:
            raise MineruRpcError(str(exc)) from exc
        if not isinstance(result, dict):
            raise MineruRpcError("scheduler returned an invalid MinerU response")
        return result
    return _call_mineru_extract_direct(
        job_id=job_id,
        file_id=file_id,
        file_path=file_path,
        original_name=original_name,
        bypass_cache=bypass_cache,
        db=db,
    )


def _call_mineru_extract_direct(
    *,
    job_id: int | None,
    file_id: int,
    file_path: str,
    original_name: str,
    bypass_cache: bool = False,
    db: Session | None = None,
    gpu_context: GpuExecutionContext | None = None,
) -> dict[str, Any]:
    """Publish to kb.mineru and block until reply or timeout."""
    correlation_id = str(uuid.uuid4())
    timeout_ms, effective_rpc_sec, cfg = _resolve_rpc_timeouts(db=db, file_path=file_path)
    # For the sidecar we must send a path it can see (mounted at /uploads inside the container).
    # Do NOT send the host absolute path here.
    sidecar_file_path = _to_mineru_sidecar_path(file_path)
    request_body = {
        "job_id": job_id,
        "file_id": file_id,
        "file_path": sidecar_file_path,
        "original_name": original_name,
        "correlation_id": correlation_id,
        "bypass_cache": bypass_cache,
        "runtime_config_version": RUNTIME_CONFIG_VERSION,
        "runtime_config": runtime_config_to_payload(cfg),
        "effective_rpc_timeout_sec": effective_rpc_sec,
    }
    if gpu_context is not None:
        request_body.update(
            {
                "gpu_lease_id": gpu_context.gpu_lease_id,
                "fencing_token": gpu_context.fencing_token,
                "gpu_job_id": gpu_context.job_id,
            }
        )

    connection = open_blocking_connection()
    channel = connection.channel()
    declare_kb_mineru_topology(channel)

    reply_queue_result = channel.queue_declare(
        queue="",
        exclusive=True,
        auto_delete=True,
        arguments={"x-message-ttl": timeout_ms},
    )
    reply_queue = reply_queue_result.method.queue

    response: dict[str, Any] | None = None
    consumed = False

    def on_reply(_ch, method, props, body: bytes) -> None:
        nonlocal response, consumed
        if props.correlation_id != correlation_id:
            return
        try:
            response = json.loads(body.decode("utf-8"))
        except json.JSONDecodeError as exc:
            response = {"ok": False, "error": "invalid_json_reply", "detail": str(exc)}
        consumed = True
        _ch.basic_ack(delivery_tag=method.delivery_tag)

    channel.basic_consume(queue=reply_queue, on_message_callback=on_reply, auto_ack=False)

    register_mineru_inflight(
        file_id=file_id,
        job_id=job_id,
        filename=original_name,
        username=_lookup_mineru_username(job_id),
    )
    try:
        request_body["reply_to"] = reply_queue
        channel.basic_publish(
            exchange=EXCHANGE_MAIN,
            routing_key=ROUTING_KEY_MINERU,
            body=json.dumps(request_body, ensure_ascii=False).encode("utf-8"),
            properties=pika.BasicProperties(
                delivery_mode=2,
                content_type="application/json",
                correlation_id=correlation_id,
                reply_to=reply_queue,
                expiration=str(timeout_ms),
            ),
        )

        elapsed = 0.0
        step = 0.5
        max_wait = effective_rpc_sec + 5.0
        while not consumed and elapsed < max_wait:
            connection.process_data_events(time_limit=step)
            _process_consumer_keepalive()
            elapsed += step
    finally:
        clear_mineru_inflight(file_id)
        try:
            if channel.consumer_tags:
                channel.basic_cancel(channel.consumer_tags[0])
        except Exception:
            pass
        try:
            if connection.is_open:
                connection.close()
        except Exception:
            pass

    if not consumed or response is None:
        raise MineruRpcTimeout(
            f"MinerU RPC 超时（>{effective_rpc_sec:.0f}s），file_id={file_id}"
        )

    if response.get("ok") is False:
        err = response.get("error") or "mineru_rpc_failed"
        detail = response.get("detail") or ""
        raise MineruRpcError(f"{err}: {detail}".strip(": "))

    if gpu_context is not None:
        if (
            response.get("gpu_lease_id") != gpu_context.gpu_lease_id
            or response.get("fencing_token") != gpu_context.fencing_token
            or str(response.get("gpu_job_id")) != gpu_context.job_id
        ):
            raise MineruRpcError("MinerU RPC reply authorization context mismatch")

    return response
