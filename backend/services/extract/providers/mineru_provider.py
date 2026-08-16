# Copyright (c) 2026 徐泽宇
"""MinerU extract provider (MQ RPC production path; HTTP debug).

Authors:
    徐泽宇

Copyright:
    © 2026 徐泽宇
"""

from __future__ import annotations

import logging

import httpx

from config import (
    KB_EXTRACT_MINERU_HTTP_TIMEOUT_SEC,
    KB_EXTRACT_MINERU_TIMEOUT_SEC,
    KB_EXTRACT_MINERU_URL,
    KB_EXTRACT_MINERU_USE_MQ,
)
from models.file import File as FileModel
from services.extract.base import ExtractResult
from services.extract.ocr_stats import ocr_stats_for_sidecar_provider
from services.gpu_model_lifecycle_service import (
    GpuExecutionContext,
    GpuModelSchedulerAdapter,
    GpuWaitingError,
)

logger = logging.getLogger(__name__)

MINERU_URL = KB_EXTRACT_MINERU_URL


def _parse_sidecar_payload(data: dict, f: FileModel | None = None) -> ExtractResult:
    text = data.get("markdown") or data.get("text") or ""
    if not str(text).strip() and not data.get("content_list"):
        raise ValueError("mineru 返回空正文")
    content_list = data.get("content_list")
    if content_list is not None and not isinstance(content_list, list):
        content_list = None
    assets_dir = data.get("assets_dir")
    if assets_dir is not None:
        assets_dir = str(assets_dir).strip() or None
        # On host kb-extract, map sidecar container paths (e.g. /cache/...) to host-visible
        from services.extract.content_list_persist import _resolve_sidecar_dir  # type: ignore
        assets_dir = _resolve_sidecar_dir(assets_dir) or assets_dir
    ocr_model_usage = data.get("ocr_model_usage")
    if not isinstance(ocr_model_usage, list):
        ocr_model_usage = None
    else:
        ocr_model_usage = [
            {
                "component": str(item.get("component") or "").strip(),
                "model_name": str(item.get("model_name") or "").strip(),
                "model_path": str(item.get("model_path") or "").strip(),
            }
            for item in ocr_model_usage
            if isinstance(item, dict)
            and str(item.get("component") or "").strip()
            and str(item.get("model_name") or "").strip()
            and str(item.get("model_path") or "").strip()
        ] or None
    result = ExtractResult(
        text=str(text),
        engine="mineru",
        content_list=content_list,
        mineru_assets_dir=assets_dir,
        ocr_model_usage=ocr_model_usage,
    )
    if f is not None:
        result.ocr_stats = ocr_stats_for_sidecar_provider(f, ocr_engine="mineru-paddle")
    return result


def _extract_mineru_http(f: FileModel) -> ExtractResult:
    if not MINERU_URL:
        raise RuntimeError("KB_EXTRACT_MINERU_URL 未配置")
    # HTTP 仅 debug/单测；生产走 MQ RPC。
    timeout = max(30.0, float(KB_EXTRACT_MINERU_HTTP_TIMEOUT_SEC))
    with open(f.file_path, "rb") as fh:
        files = {"file": (f.original_name or "document", fh)}
        with httpx.Client(timeout=timeout) as client:
            resp = client.post(f"{MINERU_URL}/extract", files=files)
            resp.raise_for_status()
            data = resp.json()
    return _parse_sidecar_payload(data, f)


def _extract_mineru_mq(
    f: FileModel,
    *,
    job_id: int | None,
    bypass_cache: bool = False,
    db=None,
    gpu_scheduler: GpuModelSchedulerAdapter | None = None,
    gpu_context: GpuExecutionContext | None = None,
) -> ExtractResult:
    from messaging.kb_mineru_rpc import call_mineru_extract

    reply = call_mineru_extract(
        job_id=job_id,
        file_id=int(f.id) if f.id is not None else 0,
        file_path=f.file_path,
        original_name=f.original_name or f.filename or "document",
        bypass_cache=bypass_cache,
        db=db,
        gpu_scheduler=gpu_scheduler,
        gpu_context=gpu_context,
    )
    return _parse_sidecar_payload(reply, f)


def extract_mineru(
    f: FileModel,
    *,
    job_id: int | None = None,
    bypass_cache: bool = False,
    db=None,
    gpu_scheduler: GpuModelSchedulerAdapter | None = None,
    gpu_context: GpuExecutionContext | None = None,
) -> ExtractResult:
    if KB_EXTRACT_MINERU_USE_MQ:
        if gpu_scheduler is None:
            from services.gpu_scheduler_runtime import scheduler_for_job

            gpu_scheduler, gpu_context = scheduler_for_job(job_id or int(f.id or 0), db=db)
        return _extract_mineru_mq(
            f,
            job_id=job_id,
            bypass_cache=bypass_cache,
            db=db,
            gpu_scheduler=gpu_scheduler,
            gpu_context=gpu_context,
        )
    if gpu_scheduler is not None and _gpu_scheduler_enabled():
        # 164 §6/§8：GPU 调度模式下必须走带授权上下文的 MQ RPC；HTTP debug 路径
        # 不校验 lease/token，禁止作为调度执行通道，fail-closed 转 waiting_gpu。
        raise GpuWaitingError(
            "mineru_mq_disabled_for_scheduled_gpu: KB_EXTRACT_MINERU_USE_MQ must be enabled"
        )
    return _extract_mineru_http(f)


def _gpu_scheduler_enabled() -> bool:
    try:
        from config import GPU_SCHEDULER_ENABLED

        return bool(GPU_SCHEDULER_ENABLED)
    except Exception:
        return False
