# Copyright (c) 2026 徐泽宇
"""Route extraction to configured provider with legacy fallback.

Authors:
    徐泽宇

Copyright:
    © 2026 徐泽宇
"""

from __future__ import annotations

import logging
import os

from models.file import File as FileModel
from services.extract.base import ExtractResult
logger = logging.getLogger(__name__)

KB_EXTRACT_PROVIDER_ENV = (os.environ.get("KB_EXTRACT_PROVIDER") or "legacy").strip().lower()
VALID_PROVIDERS = frozenset({"legacy", "docling", "mineru", "liteparse", "insavlo"})


def get_extract_provider_name(db=None, *, user_id: int | None = None) -> str:
    if db is not None:
        try:
            from services.system_setting_service import get_kb_extract_provider

            name = get_kb_extract_provider(db, user_id=user_id)
            if name in VALID_PROVIDERS:
                return name
        except Exception:
            pass
    if KB_EXTRACT_PROVIDER_ENV in VALID_PROVIDERS:
        return KB_EXTRACT_PROVIDER_ENV
    return "legacy"


def _legacy_extract(f: FileModel, *, db=None) -> ExtractResult:
    from services.extract.router import extract_text_from_file

    return extract_text_from_file(f, db=db)


def _fallback_to_legacy(f: FileModel, provider: str, exc: Exception, *, db=None) -> ExtractResult:
    reason = str(exc)
    if provider == "docling":
        logger.warning("docling extract failed docling_fallback_reason=%s", exc)
    else:
        logger.warning("%s extract failed, fallback legacy: %s", provider, exc)
    result = _legacy_extract(f, db=db)
    result.fallback_from = provider
    result.fallback_reason = reason
    return result


def extract_with_provider(
    f: FileModel,
    db=None,
    *,
    provider_override: str | None = None,
    job_id: int | None = None,
    bypass_cache: bool = False,
    gpu_scheduler=None,
    gpu_context=None,
) -> ExtractResult:
    mime_type = (f.mime_type or "").lower().split(";", 1)[0].strip()
    if mime_type == "message/rfc822":
        from services.extract.eml_extract import extract_eml
        from services.md_paths import resolve_upload_path

        path = resolve_upload_path(f.file_path) or f.file_path
        if not path:
            raise FileNotFoundError(f"文件不存在: {f.file_path}")
        return extract_eml(path, file_id=f.id)
    if provider_override is not None:
        provider = provider_override.strip().lower()
        if provider not in VALID_PROVIDERS:
            provider = "legacy"
    elif db is not None:
        from services.kb_pipeline_service import resolve_extract_provider

        provider = resolve_extract_provider(db, f, explicit_provider=None)
    else:
        provider = get_extract_provider_name(db, user_id=f.user_id)
    if provider == "legacy":
        return _legacy_extract(f, db=db)
    # PDF fast path: when a sidecar provider is the default/route, still let
    # pdf-inspector short-circuit eligible text-layer PDFs before dispatching
    # to mineru/docling. Legacy already handles pdf-inspector inside extract_pdf.
    from services.extract.providers.pdf_inspector_provider import try_pdf_inspector_fast_path

    pdf_inspector_result = try_pdf_inspector_fast_path(f, db=db)
    if pdf_inspector_result is not None:
        return pdf_inspector_result
    if provider == "docling":
        from services.extract.providers.docling_provider import extract_docling

        try:
            return extract_docling(f, job_id=job_id, bypass_cache=bypass_cache)
        except Exception as exc:
            return _fallback_to_legacy(f, "docling", exc, db=db)
    if provider == "mineru":
        from services.extract.providers.mineru_provider import extract_mineru
        from services.gpu_model_lifecycle_service import GpuOomError, GpuWaitingError

        try:
            if gpu_scheduler is None:
                from services.gpu_scheduler_runtime import scheduler_for_job

                gpu_scheduler, gpu_context = scheduler_for_job(
                    job_id or int(f.id or 0), db=db
                )
            return extract_mineru(
                f,
                job_id=job_id,
                bypass_cache=bypass_cache,
                db=db,
                gpu_scheduler=gpu_scheduler,
                gpu_context=gpu_context,
            )
        except GpuWaitingError:
            raise
        except GpuOomError:
            # OOM 已释放+重探；按 spec §8 走受控重试/failed，禁止静默 CPU fallback。
            raise
        except Exception as exc:
            if _gpu_scheduler_enabled() and gpu_scheduler is not None:
                # 164 §8/§13：GPU 调度模式下 MinerU 失败（含授权往返校验失败）不得
                # 静默降级为 legacy CPU，转 GpuWaitingError 由调度循环重试，受 job
                # attempts/oom_retry_count 上限约束。
                raise GpuWaitingError(f"mineru gpu execution failed: {exc}") from exc
            return _fallback_to_legacy(f, "mineru", exc, db=db)
    if provider == "liteparse":
        from services.extract.providers.liteparse_provider import extract_liteparse

        try:
            return extract_liteparse(f)
        except Exception as exc:
            return _fallback_to_legacy(f, "liteparse", exc, db=db)
    if provider == "insavlo":
        raise RuntimeError(
            "Insavlo provider submission must run through the webhook state machine "
 "(run_extract_job -> submit_insavlo_extract), not the synchronous extract_with_provider path"
        )
    return _legacy_extract(f, db=db)


def _gpu_scheduler_enabled() -> bool:
    try:
        from config import GPU_SCHEDULER_ENABLED

        return bool(GPU_SCHEDULER_ENABLED)
    except Exception:
        return False
