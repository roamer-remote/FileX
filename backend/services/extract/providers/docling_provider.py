# Copyright (c) 2026 徐泽宇
"""Docling extract provider (MQ RPC production path; HTTP debug)."""

from __future__ import annotations

import logging

import httpx

from config import (
    KB_EXTRACT_DOCLING_CACHE_MOUNT,
    KB_EXTRACT_DOCLING_HTTP_TIMEOUT_SEC,
    KB_EXTRACT_DOCLING_URL,
    KB_EXTRACT_DOCLING_USE_MQ,
)
from models.file import File as FileModel
from services.extract.base import ExtractResult
from services.extract.docling_content_list_adapter import adapt_docling_content_list
from services.extract.ocr_stats import ocr_stats_for_sidecar_provider

logger = logging.getLogger(__name__)

DOCLING_URL = KB_EXTRACT_DOCLING_URL


def _normalize_docling_assets_dir(assets_dir: str | None) -> str | None:
    if not assets_dir:
        return None
    path = str(assets_dir).strip() or None
    if not path:
        return None
    mount = KB_EXTRACT_DOCLING_CACHE_MOUNT
    if mount and (path == "/cache" or path.startswith("/cache/")):
        return mount + path[len("/cache") :]
    return path


class DoclingRpcError(RuntimeError):
    """Docling MQ RPC failed."""


def _parse_docling_payload(data: dict, f: FileModel | None = None) -> ExtractResult:
    text = data.get("markdown") or data.get("text") or ""
    content_list_raw = data.get("content_list")
    if content_list_raw is not None and not isinstance(content_list_raw, list):
        logger.warning("docling content_list invalid type=%s", type(content_list_raw).__name__)
        content_list_raw = None
    # 空数组 -> None，走扁平 persist（050 spec Engine/fallback：adapter 降级扁平仍 extract_engine=docling）
    content_list = adapt_docling_content_list(content_list_raw) if content_list_raw else None
    if not str(text).strip() and not content_list:
        raise ValueError("docling 返回空正文")
    assets_dir = _normalize_docling_assets_dir(data.get("assets_dir"))
    result = ExtractResult(
        text=str(text),
        engine="docling",
        content_list=content_list,
        mineru_assets_dir=assets_dir,
    )
    if f is not None:
        result.ocr_stats = ocr_stats_for_sidecar_provider(f, ocr_engine="docling")
    return result


def _docling_payload_from_rpc_reply(data: dict) -> dict:
    if data.get("ok") is False:
        raise DoclingRpcError(data.get("error") or "docling rpc failed")
    return {
        k: data[k]
        for k in ("markdown", "text", "content_list", "assets_dir")
        if k in data
    }


def _extract_docling_http(f: FileModel, *, bypass_cache: bool = False) -> ExtractResult:
    if not DOCLING_URL:
        raise RuntimeError("KB_EXTRACT_DOCLING_URL 未配置")
    timeout = max(30.0, float(KB_EXTRACT_DOCLING_HTTP_TIMEOUT_SEC))
    with open(f.file_path, "rb") as fh:
        files = {"file": (f.original_name or "document", fh)}
        data = {"bypass_cache": "true" if bypass_cache else "false"}
        with httpx.Client(timeout=timeout) as client:
            resp = client.post(f"{DOCLING_URL}/extract", files=files, data=data)
            resp.raise_for_status()
            payload = resp.json()
    return _parse_docling_payload(payload, f)


def _extract_docling_mq(
    f: FileModel,
    *,
    job_id: int | None,
    bypass_cache: bool = False,
) -> ExtractResult:
    from messaging.kb_docling_rpc import call_docling_extract

    reply = call_docling_extract(
        job_id=job_id,
        file_id=int(f.id) if f.id is not None else 0,
        file_path=f.file_path,
        original_name=f.original_name or f.filename or "document",
        bypass_cache=bypass_cache,
    )
    cleaned = _docling_payload_from_rpc_reply(reply)
    return _parse_docling_payload(cleaned, f)


def extract_docling(
    f: FileModel,
    *,
    job_id: int | None = None,
    bypass_cache: bool = False,
) -> ExtractResult:
    if KB_EXTRACT_DOCLING_USE_MQ:
        return _extract_docling_mq(f, job_id=job_id, bypass_cache=bypass_cache)
    return _extract_docling_http(f, bypass_cache=bypass_cache)
