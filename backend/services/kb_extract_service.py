# Copyright (c) 2026 徐泽宇
"""KB text extract: enqueue jobs, run extraction, persist auto-markdown.

Authors:
    徐泽宇

Copyright:
    © 2026 徐泽宇
"""

from __future__ import annotations

import logging
import os
import time
from dataclasses import dataclass
from datetime import datetime, timedelta
from utils.timezone import naive_db_now

from sqlalchemy.orm import Session

from config import (
    EXTRACT_MD_MAX_BYTES,
    GPU_SCHEDULER_ENABLED,
    KB_EXTRACT_JOB_TIMEOUT_SEC,
    KB_EXTRACT_MAX_ATTEMPTS,
)
from models.file import File as FileModel
from models.kb_extract_job import KbExtractJob
from services.kb_pipeline_log_service import (
    ACTION_INSAVLO_SUBMIT,
    ACTION_KB_EXTRACT_DEFER,
    ACTION_KB_EXTRACT_DONE,
    ACTION_KB_EXTRACT_ERROR,
    ACTION_KB_EXTRACT_FALLBACK,
    ACTION_KB_EXTRACT_SKIP,
    ACTION_KB_EXTRACT_START,
    format_kb_pipeline_detail,
    log_kb_pipeline_event,
    pipeline_reason,
)
from services.extract.policy import needs_extract
from services.gpu_model_lifecycle_service import GpuOomError, GpuWaitingError
from services.md_paths import md_note_path

logger = logging.getLogger(__name__)

STATUS_NOT_NEEDED = "not_needed"
STATUS_PENDING = "pending"
STATUS_EXTRACTING = "extracting"
STATUS_READY = "ready"
STATUS_FAILED = "failed"
STATUS_SKIPPED = "skipped"

JOB_QUEUED = "queued"
JOB_RUNNING = "running"
JOB_WAITING_WEBHOOK = "waiting_webhook"
JOB_WAITING_GPU = "waiting_gpu"
JOB_DONE = "done"
JOB_ERROR = "error"
ACTIVE_EXTRACT_JOB_STATUSES = (JOB_RUNNING, JOB_WAITING_WEBHOOK, JOB_WAITING_GPU)
CANCELLED_FILE_DELETED_MSG = "cancelled: file deleted"


@dataclass(frozen=True)
class ExtractPersistTimings:
    persist_ms: int = 0
    side_effects_ms: int = 0


def _apply_extract_skip_terminal(f: FileModel) -> None:
    """Mark extract complete when job skips because content already exists or type is not extractable."""
    if f.has_md and f.md_file_path:
        f.extract_status = STATUS_READY
    else:
        f.extract_status = STATUS_NOT_NEEDED
    f.extract_error = None


def _notify_file(f: FileModel) -> None:
    from messaging.kb_extract_publisher import publish_file_extract_notify

    try:
        publish_file_extract_notify(f)
    except Exception:
        logger.exception("publish kb extract notify failed file_id=%s", f.id)


from services.extract.providers.registry import VALID_PROVIDERS

VALID_JOB_PROVIDERS = VALID_PROVIDERS


def _resolve_enqueue_provider(db: Session, f: FileModel) -> str:
    from services.kb_pipeline_service import resolve_extract_provider

    return resolve_extract_provider(db, f, explicit_provider=None)


def _explicit_job_provider(provider: str) -> str | None:
    from services.kb_pipeline_service import PIPELINE_JOB_PROVIDERS, normalize_route_provider

    name = normalize_route_provider(provider.strip().lower())
    return name if name in PIPELINE_JOB_PROVIDERS else None


def _job_provider_for_enqueue(
    db: Session,
    f: FileModel,
    provider: str | None,
    *,
    for_reextract: bool,
) -> str | None:
    """Explicit reextract provider is pinned on the job; system default resolves at run time."""
    if provider is not None:
        return _explicit_job_provider(provider)
    if for_reextract:
        return None
    return _resolve_enqueue_provider(db, f)


def _apply_job_provider(job: KbExtractJob, provider: str | None) -> None:
    if provider is None:
        job.provider = None
        return
    name = provider.strip().lower()
    job.provider = name if name in VALID_JOB_PROVIDERS else None


def _is_intentional_reextract_job(job: KbExtractJob) -> bool:
    """Pinned provider or force reextract must run even when a note already exists."""
    return bool(job.provider) or bool(job.bypass_mineru_cache)


def _should_run_extract(f: FileModel, job: KbExtractJob) -> bool:
    from services.extract.policy import needs_extract as file_needs_extract

    if file_needs_extract(f):
        return True
    return _is_intentional_reextract_job(job)


def has_active_extract_job_for_file(
    db: Session,
    *,
    file_id: int,
    exclude_job_id: int | None = None,
) -> bool:
    return _get_active_extract_job_id_for_file(
        db, file_id=file_id, exclude_job_id=exclude_job_id
    ) is not None


def _get_active_extract_job_id_for_file(
    db: Session,
    *,
    file_id: int,
    exclude_job_id: int | None = None,
) -> int | None:
    q = db.query(KbExtractJob.id).filter(
        KbExtractJob.file_id == file_id,
        KbExtractJob.status.in_(ACTIVE_EXTRACT_JOB_STATUSES),
    )
    if exclude_job_id is not None:
        q = q.filter(KbExtractJob.id != exclude_job_id)
    row = q.first()
    return row[0] if row else None


def _pipeline_job_provider(db: Session, job: KbExtractJob, f: FileModel) -> str:
    """Provider for operation_logs: pinned job provider or runtime-resolved default."""
    if job.provider:
        return job.provider
    from services.kb_pipeline_service import resolve_extract_provider

    return resolve_extract_provider(db, f, explicit_provider=None)


def _mineru_pipeline_log_fields(db: Session, f: FileModel) -> dict[str, int]:
    from services.mineru_config_service import (
        RUNTIME_CONFIG_VERSION,
        estimate_chunk_count,
        get_mineru_runtime_config,
        pdf_page_count,
        resolve_effective_batch,
    )

    cfg = get_mineru_runtime_config(db, fresh=True)
    try:
        pages = pdf_page_count(f.file_path)
    except Exception:
        pages = 0
    mem_limit = 8 * 1024**3
    return {
        "mineru_batch": resolve_effective_batch(pages, mem_limit, cfg),
        "mineru_chunks": estimate_chunk_count(pages, cfg),
        "runtime_config_version": RUNTIME_CONFIG_VERSION,
    }


def _log_extract_pipeline(db: Session, job: KbExtractJob, action: str, **fields) -> None:
    detail = format_kb_pipeline_detail(job_id=job.id, **fields)
    log_kb_pipeline_event(db, job.user_id, action, job.file_id, detail=detail)
    if action not in {ACTION_KB_EXTRACT_ERROR, ACTION_KB_EXTRACT_FALLBACK}:
        return
    reason_text = str(fields.get("reason") or "").lower()
    if action == ACTION_KB_EXTRACT_FALLBACK:
        reason = "provider_fallback"
    elif "oom" in reason_text or "out_of_memory" in reason_text:
        reason = "oom"
    elif "timeout" in reason_text:
        reason = "timeout"
    else:
        reason = "unknown"
    try:
        from services.rag_quality_failure_service import build_failure_event, persist_failure_event

        persist_failure_event(
            db,
            job.user_id,
            build_failure_event(
                stage="extraction",
                reason=reason,
                file_id=job.file_id,
                job_id=job.id,
                request_id=None,
                trace_id=None,
                provider=fields.get("provider"),
                summary=fields.get("reason") or action,
                retryable=reason in {"oom", "timeout"},
            ),
        )
    except Exception:
        # Failure telemetry is diagnostic and must not alter extraction semantics.
        logger.warning("persist extraction failure telemetry failed job_id=%s", job.id, exc_info=True)


def _ocr_detail_fields(result) -> dict:
    fields = {}
    stats = getattr(result, "ocr_stats", None)
    if stats is not None:
        fields.update(stats.pipeline_detail_fields())
    for model in getattr(result, "ocr_model_usage", None) or []:
        if not isinstance(model, dict):
            continue
        component = str(model.get("component") or "").strip()
        model_name = str(model.get("model_name") or "").strip()
        model_path = str(model.get("model_path") or "").strip()
        if not component or not model_name or not model_path:
            continue
        safe_component = "".join(ch if ch.isalnum() else "_" for ch in component)
        fields[f"ocr_model_{safe_component}"] = model_name
        fields[f"ocr_model_path_{safe_component}"] = model_path
    return fields


def enqueue_extract(
    db: Session,
    user_id: int,
    file_id: int,
    *,
    provider: str | None = None,
    for_reextract: bool = False,
    bypass_mineru_cache: bool = False,
) -> int | None:
    f = db.query(FileModel).filter(FileModel.id == file_id, FileModel.user_id == user_id).first()
    if not f:
        return None
    from services.extract.policy import supports_reextract

    if for_reextract:
        if not supports_reextract(f):
            return None
    elif not needs_extract(f):
        if f.extract_status in (None, "", STATUS_PENDING):
            f.extract_status = STATUS_NOT_NEEDED
        return None

    existing_queued = (
        db.query(KbExtractJob)
        .filter(KbExtractJob.file_id == file_id, KbExtractJob.status == JOB_QUEUED)
        .order_by(KbExtractJob.id.desc())
        .first()
    )
    existing_active = (
        db.query(KbExtractJob)
        .filter(KbExtractJob.file_id == file_id, KbExtractJob.status.in_(ACTIVE_EXTRACT_JOB_STATUSES))
        .order_by(KbExtractJob.id.desc())
        .all()
    )
    if for_reextract and (existing_active or existing_queued):
        superseded = list(existing_active)
        if existing_queued:
            superseded.append(existing_queued)
            existing_queued = None
        for old_job in superseded:
            old_job.status = JOB_ERROR
            old_job.last_error = "superseded by reextract"

    if _md_extract_hash_unchanged(f, bypass=bypass_mineru_cache or provider is not None):
        logger.info("kb_extract_skip hash_unchanged file_id=%s", f.id)
        _complete_extract_hash_skip(f)
        return None

    active_job = existing_active[0] if existing_active and not for_reextract else None
    f.extract_status = STATUS_EXTRACTING if active_job else STATUS_PENDING
    f.extract_error = None
    if for_reextract:
        f.extract_engine = None
        f.extracted_at = None
    job_to_publish: int | None = None
    job_provider = _job_provider_for_enqueue(db, f, provider, for_reextract=for_reextract)
    route_provider = job_provider
    if route_provider is None and for_reextract:
        # 164 §6：reextract 未显式指定 provider 时按运行时默认解析；若默认是
        # mineru，必须有 durable route，避免 GPU 调度模式下绕过 lease 执行。
        route_provider = _resolve_enqueue_provider(db, f)
    if active_job:
        new_job = KbExtractJob(
            user_id=user_id,
            file_id=file_id,
            status=JOB_QUEUED,
            bypass_mineru_cache=bypass_mineru_cache,
        )
        _apply_job_provider(new_job, job_provider)
        db.add(new_job)
        db.flush()
        job_to_publish = new_job.id
    elif existing_queued:
        _apply_job_provider(existing_queued, job_provider)
        if bypass_mineru_cache:
            existing_queued.bypass_mineru_cache = True
        job_to_publish = existing_queued.id
        db.flush()
    else:
        new_job = KbExtractJob(
            user_id=user_id,
            file_id=file_id,
            status=JOB_QUEUED,
            bypass_mineru_cache=bypass_mineru_cache,
        )
        _apply_job_provider(new_job, job_provider)
        db.add(new_job)
        db.flush()
        job_to_publish = new_job.id
    if job_to_publish is not None and route_provider == "mineru":
        from services.gpu_scheduler_persistence import enqueue_gpu_route

        enqueue_gpu_route(
            db,
            job_kind="mineru",
            job_id=job_to_publish,
            file_id=file_id,
            idempotency_key=f"mineru:{job_to_publish}:0",
            payload={
                "job_id": job_to_publish,
                "job_kind": "mineru",
                "file_id": file_id,
                "attempt": 0,
                "idempotency_key": f"mineru:{job_to_publish}:0",
                "handover_epoch": 0,
            },
        )
    return job_to_publish


def abort_kb_extract_jobs_for_file_delete(db: Session, file_id: int) -> list[int]:
    """删除文件前终止所有仍可能被 worker 执行的提取任务。"""
    jobs = (
        db.query(KbExtractJob)
        .filter(
            KbExtractJob.file_id == file_id,
            KbExtractJob.status.in_((JOB_QUEUED, *ACTIVE_EXTRACT_JOB_STATUSES)),
        )
        .all()
    )
    cancelled_ids: list[int] = []
    for job in jobs:
        job.status = JOB_ERROR
        job.last_error = CANCELLED_FILE_DELETED_MSG
        cancelled_ids.append(int(job.id))
    return cancelled_ids


def purge_kb_extract_mq_for_jobs(job_ids: list[int]) -> None:
    """尽力清理提取主/重试/DLQ中的指定任务消息。"""
    if not job_ids:
        return
    from messaging.kb_extract_queues import QUEUE_DLQ, QUEUE_MAIN, QUEUE_RETRY
    from services.rabbitmq_queue_admin_service import (
        mutate_queue_messages_by_job_ids,
    )

    job_id_set = {int(job_id) for job_id in job_ids}
    for queue_name in (QUEUE_MAIN, QUEUE_RETRY, QUEUE_DLQ):
        try:
            mutate_queue_messages_by_job_ids(queue_name, job_ids=job_id_set)
        except Exception:
            logger.warning("abort extract mq purge failed queue=%s jobs=%s", queue_name, job_ids, exc_info=True)

def purge_gpu_route_mq_for_jobs(
    *,
    file_id: int,
    mineru_job_ids: list[int],
    raptor_job_ids: list[int],
) -> None:
    """按队列类型 + file_id + job_id 三重约束清理 GPU 路由消息。"""
    if not mineru_job_ids and not raptor_job_ids:
        return
    from services.rabbitmq_queue_admin_service import mutate_queue_messages_by_file_and_job_ids
    from messaging.gpu_queues import QUEUE_GPU_MINERU, QUEUE_GPU_RAPTOR

    for queue_name, job_ids in (
        (QUEUE_GPU_MINERU, mineru_job_ids),
        (QUEUE_GPU_RAPTOR, raptor_job_ids),
    ):
        if not job_ids:
            continue
        try:
            mutate_queue_messages_by_file_and_job_ids(
                queue_name, file_id=int(file_id), job_ids={int(job_id) for job_id in job_ids}
            )
        except Exception:
            logger.warning(
                "abort gpu route mq purge failed queue=%s file_id=%s jobs=%s",
                queue_name,
                file_id,
                job_ids,
                exc_info=True,
            )



def copy_markdown_source_to_sidecar(f: FileModel) -> str:
    from services.extract.policy import is_markdown_source_file

    if not is_markdown_source_file(f):
        raise ValueError("文件不是可复制的文本源文件")
    from services.md_paths import resolve_upload_path

    path = resolve_upload_path(f.file_path) or f.file_path
    if not path or not os.path.isfile(path):
        raise FileNotFoundError(f"文件不存在: {f.file_path}")
    with open(path, encoding="utf-8") as fh:
        return fh.read()


def publish_extract_job(db: Session, user_id: int, file_id: int, job_id: int) -> None:
    from messaging.kb_extract_publisher import publish_kb_extract_job

    try:
        from services.gpu_scheduler_persistence import find_gpu_route, publish_gpu_route

        route = find_gpu_route(db, job_kind="mineru", job_id=job_id)
        if route is None:
            publish_kb_extract_job(job_id)
        elif GPU_SCHEDULER_ENABLED:
            # 164 §6：GPU 调度模式下发布入口只入队；route 保持 queued，由
            # scheduler 取得租约后统一发布 filex.gpu.*，旧 worker 不执行 GPU。
            db.commit()
        else:
            publish_gpu_route(
                db,
                outbox_id=route.id,
                publish=lambda payload: publish_kb_extract_job(int(payload["job_id"])),
            )
            db.commit()
    except Exception:
        logger.exception("publish kb extract job failed job_id=%s", job_id)
    f = db.query(FileModel).filter(FileModel.id == file_id, FileModel.user_id == user_id).first()
    if f:
        _notify_file(f)
        try:
            from messaging.mq_status_watcher import request_refresh

            request_refresh()
        except Exception:
            pass




def persist_extract_result(db: Session, f: FileModel, result, user_id: int) -> ExtractPersistTimings:
    from services.extract.base import ExtractResult

    if not isinstance(result, ExtractResult):
        raise TypeError("result must be ExtractResult")
    text = result.text
    if result.content_list:
        from services.extract.content_list_persist import prepare_structured_extract

        text = prepare_structured_extract(f, result.content_list, result.mineru_assets_dir)
        if not text.strip() and result.text.strip():
            text = result.text
    return persist_extract_markdown(db, f, text, engine=result.engine, user_id=user_id)


def persist_extract_markdown(
    db: Session, f: FileModel, text: str, engine: str, *, user_id: int
) -> ExtractPersistTimings:
    raw = (text or "").strip()
    if not raw:
        f.extract_status = STATUS_SKIPPED
        f.extract_error = None
        f.extract_engine = engine
        f.extracted_at = naive_db_now()
        # 空 extract 不覆写 body，但刷新 frontmatter 的 filex 块以镜像 DB 状态
        from services.okf_note_service import refresh_okf_filex_block

        refresh_okf_filex_block(f)
        return ExtractPersistTimings()

    encoded = raw.encode("utf-8")
    if len(encoded) > EXTRACT_MD_MAX_BYTES:
        raise ValueError(
            f"提取正文超过上限 {EXTRACT_MD_MAX_BYTES // (1024 * 1024)} MiB",
        )

    from services.md_tag_anchor_service import rebuild_anchors_for_file
    from services.md_note_service import clear_manual_override_on_md_write, rebuild_md_note_side_effects
    from services.okf_note_service import save_okf_body_for_file

    t_persist = time.perf_counter()
    clear_manual_override_on_md_write(f)
    f.extract_status = STATUS_READY
    f.extract_error = None
    f.extract_engine = engine
    f.extracted_at = naive_db_now()
    # FR-111-003：只替换 body，保留 frontmatter；原子写盘 + body-only hash + okf_* 同步
    save_okf_body_for_file(f, raw)
    persist_ms = int((time.perf_counter() - t_persist) * 1000)

    t_side = time.perf_counter()
    rebuild_anchors_for_file(db, user_id, f.id)
    rebuild_md_note_side_effects(db, user_id, f.id)
    side_effects_ms = int((time.perf_counter() - t_side) * 1000)
    return ExtractPersistTimings(persist_ms=persist_ms, side_effects_ms=side_effects_ms)


def _md_extract_hash_unchanged(f: FileModel, *, bypass: bool) -> bool:
    if bypass:
        return False
    if not f.md_content_hash:
        return False
    from services.md_hash_service import compute_md_content_hash, read_md_note_content_for_hash
    from services.extract.policy import needs_extract

    content = read_md_note_content_for_hash(f)
    if content is None:
        return False
    # 111 上传空 OKF 壳时 md_content_hash 已是空 body 的 digest；若仍待首次提取则不得 skip。
    if not content.strip() and needs_extract(f):
        return False
    return compute_md_content_hash(content) == f.md_content_hash


def _should_skip_extract_hash_unchanged(f: FileModel, job: KbExtractJob) -> bool:
    """Run-stage guard: same hash check as enqueue, reading bypass from persisted job."""
    if _is_intentional_reextract_job(job):
        return False
    return _md_extract_hash_unchanged(f, bypass=bool(job.bypass_mineru_cache))


def _complete_extract_hash_skip(f: FileModel) -> None:
    f.extract_status = STATUS_READY
    f.extract_error = None
    _notify_file(f)


def run_extract_job(db: Session, job: KbExtractJob) -> None:
    f = (
        db.query(FileModel)
        .filter(FileModel.id == job.file_id, FileModel.user_id == job.user_id)
        .first()
    )
    if not f:
        job.attempts = (job.attempts or 0) + 1
        job.status = JOB_ERROR
        job.last_error = "file not found"
        return

    active_job_id = _get_active_extract_job_id_for_file(
        db, file_id=job.file_id, exclude_job_id=job.id
    )
    if active_job_id is not None:
        f.extract_status = STATUS_EXTRACTING
        f.extract_error = None
        db.flush()
        _log_extract_pipeline(
            db,
            job,
            ACTION_KB_EXTRACT_DEFER,
            reason="active_job_on_file",
            active_job_id=active_job_id,
        )
        logger.info(
            "defer kb extract job because file has active extract job job_id=%s file_id=%s",
            job.id,
            job.file_id,
        )
        return

    from services.extract.policy import is_markdown_source_file

    if is_markdown_source_file(f):
        from services.extract.policy import get_extension_from_file

        job.status = JOB_RUNNING
        job.attempts = (job.attempts or 0) + 1
        f.extract_status = STATUS_EXTRACTING
        f.extract_error = None
        db.flush()
        _log_extract_pipeline(db, job, ACTION_KB_EXTRACT_START, provider=job.provider or "markdown-copy")
        db.commit()
        _notify_file(f)
        index_enqueued = False
        copy_engine = "markdown-copy"
        try:
            t_provider = time.perf_counter()
            text = copy_markdown_source_to_sidecar(f)
            provider_ms = int((time.perf_counter() - t_provider) * 1000)
            copy_engine = "text-copy" if get_extension_from_file(f) == "txt" else "markdown-copy"
            persist_timings = persist_extract_markdown(db, f, text, user_id=job.user_id, engine=copy_engine)
            job.status = JOB_DONE
            from services.knowledge_base_index_service import auto_sync_kb_index

            auto_sync_kb_index(db, f.user_id)
            job.last_error = None
            if text.strip():
                from services.kb_index_service import enqueue_index_after_extract

                index_job_id = enqueue_index_after_extract(db, f, job)
                if index_job_id is not None:
                    index_enqueued = True
                    db.commit()
                    from services.kb_index_service import publish_index_job

                    publish_index_job(db, f.user_id, f.id, index_job_id)
            _log_extract_pipeline(
                db,
                job,
                ACTION_KB_EXTRACT_DONE,
                provider=job.provider or "markdown-copy",
                engine=copy_engine,
                index_enqueued=index_enqueued,
                provider_ms=provider_ms,
                persist_ms=persist_timings.persist_ms,
                side_effects_ms=persist_timings.side_effects_ms,
            )
        except Exception as exc:
            logger.exception("markdown copy job %s failed", job.id)
            msg = str(exc)[:2000]
            f.extract_status = STATUS_FAILED
            f.extract_error = msg
            job.status = JOB_ERROR
            job.last_error = msg
            _log_extract_pipeline(
                db,
                job,
                ACTION_KB_EXTRACT_ERROR,
                provider=job.provider or "markdown-copy",
                reason=pipeline_reason(msg),
            )
        db.commit()
        _notify_file(f)
        return

    from services.extract.policy import needs_extract as file_needs_extract
    from services.office_normalize_service import ensure_office_normalized, is_legacy_office_file

    if is_legacy_office_file(f):
        try:
            ensure_office_normalized(f)
            db.commit()
            _notify_file(f)
        except Exception as exc:
            logger.exception("normalize legacy office failed file_id=%s", f.id)
            msg = str(exc)[:2000]
            if file_needs_extract(f):
                f.extract_status = STATUS_FAILED
                f.extract_error = msg
                job.status = JOB_ERROR
                job.last_error = msg
                _log_extract_pipeline(
                    db,
                    job,
                    ACTION_KB_EXTRACT_ERROR,
                    reason=pipeline_reason(msg),
                    stage="office_normalize",
                )
            else:
                job.status = JOB_DONE
                job.last_error = f"normalize failed: {msg}"
                _apply_extract_skip_terminal(f)
            db.commit()
            _notify_file(f)
            return

    if _should_skip_extract_hash_unchanged(f, job):
        logger.info("kb_extract_skip hash_unchanged file_id=%s", f.id)
        job.status = JOB_DONE
        job.last_error = None
        _complete_extract_hash_skip(f)
        _log_extract_pipeline(db, job, ACTION_KB_EXTRACT_SKIP, reason="hash_unchanged")
        db.commit()
        return

    if not _should_run_extract(f, job):
        _apply_extract_skip_terminal(f)
        job.status = JOB_DONE
        job.last_error = None
        _log_extract_pipeline(db, job, ACTION_KB_EXTRACT_SKIP, reason="not_needed")
        db.commit()
        _notify_file(f)
        return

    job.status = JOB_RUNNING
    job.attempts = (job.attempts or 0) + 1
    f.extract_status = STATUS_EXTRACTING
    f.extract_error = None
    db.flush()
    start_fields: dict = {"provider": _pipeline_job_provider(db, job, f)}
    if start_fields["provider"] == "mineru":
        start_fields.update(_mineru_pipeline_log_fields(db, f))
    _log_extract_pipeline(db, job, ACTION_KB_EXTRACT_START, **start_fields)
    db.commit()
    _notify_file(f)

    try:
        if job.provider == "insavlo":
            from services.extract.providers.insavlo_provider import submit_insavlo_extract

            submission = submit_insavlo_extract(f, db, job_id=job.id)
            job.remote_transaction_id = submission.transaction_id
            job.remote_file_id = submission.file_id
            job.remote_skill_code = submission.skill_code
            job.remote_submitted_at = submission.submitted_at
            job.status = JOB_WAITING_WEBHOOK
            job.last_error = None
            f.extract_status = STATUS_EXTRACTING
            f.extract_error = None
            db.flush()
            _log_extract_pipeline(
                db,
                job,
                ACTION_INSAVLO_SUBMIT,
                provider=job.provider or "insavlo",
                transaction_id=submission.transaction_id,
                remote_file_id=submission.file_id,
            )
            return

        from services.extract.providers.registry import extract_with_provider

        t_provider = time.perf_counter()
        result = extract_with_provider(
            f,
            db,
            provider_override=job.provider,
            job_id=job.id,
            bypass_cache=bool(job.bypass_mineru_cache),
        )
        provider_ms = int((time.perf_counter() - t_provider) * 1000)
        if result.fallback_from:
            _log_extract_pipeline(
                db,
                job,
                ACTION_KB_EXTRACT_FALLBACK,
                provider=result.fallback_from,
                reason=pipeline_reason(result.fallback_reason),
            )
        persist_timings = persist_extract_result(db, f, result, user_id=job.user_id)
        job.status = JOB_DONE
        from services.knowledge_base_index_service import auto_sync_kb_index

        auto_sync_kb_index(db, f.user_id)
        job.last_error = None
        index_enqueued = False
        if result.text.strip():
            from services.kb_index_service import enqueue_index_after_extract

            index_job_id = enqueue_index_after_extract(db, f, job)
            if index_job_id is not None:
                index_enqueued = True
                db.commit()
                from services.kb_index_service import publish_index_job

                publish_index_job(db, f.user_id, f.id, index_job_id)
        _log_extract_pipeline(
            db,
            job,
            ACTION_KB_EXTRACT_DONE,
            provider=_pipeline_job_provider(db, job, f),
            engine=result.engine,
            index_enqueued=index_enqueued,
            provider_ms=provider_ms,
            persist_ms=persist_timings.persist_ms,
            side_effects_ms=persist_timings.side_effects_ms,
            **_ocr_detail_fields(result),
        )
    except GpuOomError as exc:
        msg = f"{exc.reason_code}: {exc}"[:2000]
        f.extract_status = STATUS_FAILED
        f.extract_error = msg
        job.status = JOB_ERROR
        job.last_error = msg
        job.oom_retry_count = (job.oom_retry_count or 0) + 1
        if (job.oom_retry_count or 0) > GpuOomError.max_controlled_retries:
            # spec §8：OOM 最多一次受控重试；第二次 OOM 直接到 failed/DLQ。
            job.attempts = get_kb_extract_max_attempts()
        _log_extract_pipeline(
            db,
            job,
            ACTION_KB_EXTRACT_ERROR,
            provider=_pipeline_job_provider(db, job, f),
            reason=pipeline_reason(msg),
        )
        logger.error("kb extract job gpu oom job_id=%s file_id=%s oom_retry=%s error=%s",
                     job.id, f.id, job.oom_retry_count, msg[:500])
    except GpuWaitingError as exc:
        msg = f"{exc.reason_code}: {exc}"[:2000]
        f.extract_status = STATUS_PENDING
        f.extract_error = msg
        job.status = JOB_WAITING_GPU
        job.last_error = msg
        _log_extract_pipeline(
            db,
            job,
            ACTION_KB_EXTRACT_DEFER,
            provider=_pipeline_job_provider(db, job, f),
            reason=msg,
        )
        logger.warning("kb extract job waiting for GPU job_id=%s file_id=%s reason=%s", job.id, f.id, msg)
    except Exception as exc:
        logger.exception("extract job %s failed", job.id)
        msg = str(exc)[:2000]
        f.extract_status = STATUS_FAILED
        f.extract_error = msg
        job.status = JOB_ERROR
        job.last_error = msg
        _log_extract_pipeline(
            db,
            job,
            ACTION_KB_EXTRACT_ERROR,
            provider=_pipeline_job_provider(db, job, f),
            reason=pipeline_reason(msg),
        )


STALE_RUNNING_RECOVERED_MSG = "stale running recovered (extract worker interrupted)"


def requeue_stale_running_extract_job(
    db: Session,
    job: KbExtractJob,
    *,
    now: datetime,
    recover_route: bool = True,
) -> bool:
    """把中断的 running extract job 恢复为 queued（或 waiting_webhook）。

    与 route/lease 恢复同一事务：GPU 调度模式下 consumer 崩溃后 route 停在
    executing、lease 仍 active，必须把 route 退回 queued 并释放 lease，
    调度循环才能重新取得租约并发布。调用方若自行恢复 route/lease（如调度
    循环按 owner 恢复），可传 ``recover_route=False`` 避免双重处理。
    返回是否发生状态恢复。
    """
    job.updated_at = now
    f = db.query(FileModel).filter(FileModel.id == job.file_id).first()
    if job.remote_transaction_id:
        job.status = JOB_WAITING_WEBHOOK
        if f and f.extract_status != STATUS_EXTRACTING:
            f.extract_status = STATUS_EXTRACTING
            f.extract_error = None
        return True
    job.status = JOB_QUEUED
    if f and f.extract_status == STATUS_EXTRACTING:
        f.extract_status = STATUS_PENDING
        f.extract_error = None
    if recover_route:
        from services.gpu_scheduler_persistence import recover_gpu_route_for_requeue

        recover_gpu_route_for_requeue(db, job_kind="mineru", job_id=job.id)
    return True


def _extract_job_is_stale(
    db: Session,
    job: KbExtractJob,
    *,
    now: datetime,
    stale_seconds: float,
) -> tuple[bool, bool]:
    """running job 是否可判定为中断；返回 ``(is_stale, watchdog_recorded)``。

    GPU 调度模式下 lease heartbeat 是权威 liveness：调度循环存活时每 tick
    续期，scheduler 崩溃/停滞后台心跳停止。但 liveness 丢失 ≠ 回收授权：
    执行中的 lease 必须先由 watchdog 确认旧执行轮已退出（release_ack 或连续
    两次间隔 5 秒的确认；MinerU 轮次以 sidecar /lifecycle/status 为准）才可
    重排队，否则 loop 线程停滞或双 worker 场景下会把仍在执行的 job 误判为
    中断并并发重跑（164 §5.5）。无 lease 的 CPU job 退回 updated_at 阈值门控。
    """
    from config import GPU_SCHEDULER_TTL_SEC
    from services.gpu_scheduler_persistence import (
        WATCHDOG_CONFIRMATIONS_REQUIRED,
        find_active_lease_for_job,
        record_watchdog_empty_confirmation,
    )
    from services.gpu_watchdog import gpu_round_idle

    lease = find_active_lease_for_job(db, job_id=str(job.id))
    if lease is not None:
        if lease.release_ack_at is not None:
            return True, False
        if (lease.watchdog_empty_confirmations or 0) >= WATCHDOG_CONFIRMATIONS_REQUIRED:
            return True, False
        if lease.heartbeat_at is not None and (
            now - lease.heartbeat_at
        ).total_seconds() <= 2 * GPU_SCHEDULER_TTL_SEC:
            # 心跳新鲜：执行轮仍存活（含 claim 后 running 提交前的瞬态）。
            return False, False
        if not gpu_round_idle(job_kind="mineru", lease=lease):
            # 旧执行轮仍存活（或探测失败）：不得确认，job 保持 running，
            # 等待调度循环/旧 consumer 后续采样。
            return False, False
        with db.begin_nested():
            confirmed = record_watchdog_empty_confirmation(db, lease, now=now)
        return confirmed, True
    cutoff = now - timedelta(seconds=stale_seconds)
    return (job.updated_at is None or job.updated_at <= cutoff), False


def reconcile_stale_kb_extract_jobs(
    db: Session,
    *,
    stale_seconds: float | None = None,
) -> int:
    """回收中断的 running 任务，避免监控无消费者且消息被忽略。

    ``stale_seconds=None`` 表示启动时无条件回收（单实例 worker 重启语义）；
    传入阈值时按 lease 心跳/updated_at 门控，供周期性 reconcile 使用。
    """
    running_jobs = db.query(KbExtractJob).filter(KbExtractJob.status == JOB_RUNNING).all()
    if not running_jobs:
        return 0
    now = naive_db_now()
    recovered_ids: list[int] = []
    watchdog_recorded = False
    for job in running_jobs:
        if stale_seconds is not None:
            stale, recorded = _extract_job_is_stale(
                db,
                job,
                now=now,
                stale_seconds=stale_seconds,
            )
            watchdog_recorded = watchdog_recorded or recorded
            if not stale:
                continue
        if requeue_stale_running_extract_job(db, job, now=now):
            recovered_ids.append(int(job.id))
    if recovered_ids or watchdog_recorded:
        db.commit()
        logger.info(
            "reconciled stale running kb extract job(s) count=%s ids=%s "
            "(watchdog_recorded=%s)",
            len(recovered_ids),
            recovered_ids,
            watchdog_recorded,
        )
    return len(recovered_ids)


def replay_queued_jobs(db: Session, *, full: bool = False) -> int:
    from config import KB_EXTRACT_REPLAY_STALE_SEC
    from messaging.kb_extract_publisher import publish_kb_extract_job

    q = db.query(KbExtractJob).filter(KbExtractJob.status.in_((JOB_QUEUED, JOB_WAITING_GPU)))
    if not full:
        cutoff = naive_db_now() - timedelta(seconds=KB_EXTRACT_REPLAY_STALE_SEC)
        q = q.filter(KbExtractJob.updated_at <= cutoff)
    jobs = q.order_by(KbExtractJob.id).all()
    if not jobs:
        return 0
    if GPU_SCHEDULER_ENABLED:
        # 164 §6：GPU 模式下持久化 route 由 dispatch loop 负责重发，旧拓扑
        # replay 只会与调度发布竞态（旧 consumer 重开 published route 会释放
        # in-flight lease）；跳过已建 durable route 的 job。
        from models.gpu_scheduler import GpuSchedulerOutbox
        from services.gpu_scheduler_persistence import (
            OUTBOX_EXECUTING,
            OUTBOX_PUBLISHED,
            OUTBOX_QUEUED,
        )

        route_job_ids = {
            str(row[0])
            for row in db.query(GpuSchedulerOutbox.job_id).filter(
                GpuSchedulerOutbox.job_kind == "mineru",
                GpuSchedulerOutbox.state.in_(
                    (OUTBOX_QUEUED, OUTBOX_PUBLISHED, OUTBOX_EXECUTING)
                ),
            )
        }
        jobs = [job for job in jobs if str(job.id) not in route_job_ids]
        if not jobs:
            return 0
    from messaging.kb_extract_queues import open_blocking_connection

    conn = open_blocking_connection()
    now = naive_db_now()
    try:
        for job in jobs:
            publish_kb_extract_job(job.id, connection=conn)
            job.updated_at = now
    finally:
        conn.close()
    db.commit()
    logger.info("replayed %s queued kb extract job(s) (full=%s)", len(jobs), full)
    return len(jobs)


def get_kb_extract_max_attempts() -> int:
    return max(1, int(KB_EXTRACT_MAX_ATTEMPTS))
