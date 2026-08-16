# Copyright (c) 2026 徐泽宇
"""KB vector index: enqueue jobs, process chunks, delete on MD removal.

Authors:
    徐泽宇

Copyright:
    © 2026 徐泽宇
"""

from __future__ import annotations

import logging
import os
import socket
import time
import uuid
from collections.abc import Callable
from datetime import timedelta

from sqlalchemy import func, text
from sqlalchemy.exc import OperationalError
from sqlalchemy.orm import Session

from config import KB_INDEX_RUNNING_STALE_SEC
from services.ollama_config_service import get_ollama_runtime_config
from models.file import File as FileModel
from models.kb_chunk import KbChunk
from models.kb_index_job import KbIndexJob
from models.kb_correction_overlay import KbCorrectionOverlay
from services.kb_pipeline_log_service import (
    ACTION_KB_INDEX_DONE,
    ACTION_KB_INDEX_ERROR,
    ACTION_KB_INDEX_RECOVER,
    ACTION_KB_INDEX_SKIP,
    ACTION_KB_INDEX_START,
    format_kb_pipeline_detail,
    log_kb_pipeline_event,
    pipeline_reason,
)
from services.kb_chunking import chunk_markdown, chunk_text, TextChunk
from services.kb_chunk_embed_input import build_embed_input, load_file_embed_context
from services.kb_heading_path import (
    KB_HEADING_DEBUG_PREFIX_LEN,
    KB_HEADING_PATH_MAX_LEN,
    cap_heading_path,
)
from services.kb_content_kind import enrich_chunks_with_content_metadata
from services.kb_fts_service import get_effective_fts_config
from services.kb_chunk_profile import resolve_effective_chunk_params
from services.kb_index_fingerprint import (
    build_text_to_chunk,
    compute_index_pipeline_fingerprint,
    fingerprint_canonical_json,
    fingerprint_payload,
    log_fingerprint_mismatch,
)
from services.kb_chunk_ops_service import compute_index_source_hash
from services.user_setting_service import get_user_effective_dict
from services.kb_embed_cache_service import resolve_embedding_vectors
from services.kb_ollama_embed import OllamaEmbedError
from services.kb_text_source import resolve_index_text
from services.kb_figure_refs import resolve_figure_asset_abs_path
from services.kb_chunk_strategy import (
    apply_chunk_strategy,
    build_strategy_chunk_id,
    build_strategy_chunk_metadata,
    resolve_chunk_strategy,
    validate_multimodal_metadata,
)
from services.vector_index import VectorRecord, get_vector_index_backend
from utils.timezone import naive_db_now

logger = logging.getLogger(__name__)

KB_INDEX_DEADLOCK_MAX_RETRIES = 3
KB_INDEX_DEADLOCK_BACKOFF_BASE_SEC = 0.05


def is_pg_deadlock(exc: BaseException) -> bool:
    """True when exc is PostgreSQL deadlock (40P01)."""
    if not isinstance(exc, OperationalError):
        return False
    orig = getattr(exc, "orig", None)
    if orig is not None and getattr(orig, "pgcode", None) == "40P01":
        return True
    return "deadlock detected" in str(exc).lower()

STATUS_PENDING = "pending"
STATUS_INDEXING = "indexing"
STATUS_READY = "ready"
STATUS_FAILED = "failed"
STATUS_SKIPPED = "skipped"

JOB_QUEUED = "queued"
JOB_RUNNING = "running"
JOB_DONE = "done"
JOB_ERROR = "error"

CANCELLED_FILE_DELETED_MSG = "cancelled: file deleted"
LEASE_LOST_MSG = "job lease lost"

ADVISORY_LOCK_KB_INDEX_CLAIM = 900127

from collections import namedtuple
_LeaseToken = namedtuple("_LeaseToken", ["worker_id", "lease_generation"])


class KbIndexJobAborted(Exception):
    """索引任务因文件删除或任务取消而协作终止。"""


def make_kb_index_worker_id() -> str:
    return f"kb-index:{socket.gethostname()}:{os.getpid()}:{uuid.uuid4().hex[:12]}"


def claim_kb_index_job(db: Session, job_id: int, *, worker_id: str) -> KbIndexJob | None:
    """Atomically claim one queued index job with a worker lease."""
    job = (
        db.query(KbIndexJob)
        .filter(KbIndexJob.id == job_id, KbIndexJob.status == JOB_QUEUED)
        .with_for_update()
        .first()
    )
    if job is None:
        return None
    # Prevent concurrent claims for the same file via advisory lock.
    # Without this, two bg threads on two queued jobs for the same file
    # could each lock a different row and both see zero running jobs,
    # violating the "one active job per type per file" invariant.
    db.execute(text("SELECT pg_advisory_xact_lock(:key1, :key2)"), {
        "key1": ADVISORY_LOCK_KB_INDEX_CLAIM,
        "key2": job.file_id,
    })
    active_same_file = (
        db.query(KbIndexJob.id)
        .filter(
            KbIndexJob.file_id == job.file_id,
            KbIndexJob.status == JOB_RUNNING,
            KbIndexJob.id != job.id,
        )
        .limit(1)
        .first()
    )
    if active_same_file is not None:
        return None
    now = naive_db_now()
    job.status = JOB_RUNNING
    job.worker_id = worker_id
    job.claimed_at = now
    job.heartbeat_at = now
    job.updated_at = now
    job.lease_generation = (job.lease_generation or 0) + 1
    db.flush()
    return job


def _ensure_index_job_claimed(db: Session, job: KbIndexJob) -> KbIndexJob | None:
    if job.status == JOB_RUNNING:
        return job
    if job.status != JOB_QUEUED:
        return None
    claimed = claim_kb_index_job(db, int(job.id), worker_id=make_kb_index_worker_id())
    if claimed is None:
        return None
    db.refresh(claimed)
    return claimed


def _index_lease_matches(
    job: KbIndexJob,
    *,
    worker_id: str | None,
    lease_generation: int | None,
) -> bool:
    if worker_id is None and lease_generation is None:
        return True
    return (
        job.worker_id == worker_id
        and int(job.lease_generation or 0) == int(lease_generation or 0)
    )


def abort_kb_index_jobs_for_file_delete(db: Session, file_id: int) -> list[int]:
    """删除文件前标记 queued/running 索引任务为 error，便于 worker 协作退出。"""
    jobs = (
        db.query(KbIndexJob)
        .filter(
            KbIndexJob.file_id == file_id,
            KbIndexJob.status.in_((JOB_QUEUED, JOB_RUNNING)),
        )
        .all()
    )
    cancelled_ids: list[int] = []
    for job in jobs:
        job.status = JOB_ERROR
        job.last_error = CANCELLED_FILE_DELETED_MSG
        cancelled_ids.append(int(job.id))
    return cancelled_ids


def purge_kb_index_mq_for_jobs(job_ids: list[int]) -> None:
    """尽力从索引主/重试/DLQ队列移除指定 job 消息。"""
    if not job_ids:
        return
    from messaging.kb_index_queues import QUEUE_DLQ, QUEUE_MAIN, QUEUE_RETRY
    from services.rabbitmq_queue_admin_service import mutate_queue_messages_by_job_ids

    for queue_name in (QUEUE_MAIN, QUEUE_RETRY, QUEUE_DLQ):
        try:
            mutate_queue_messages_by_job_ids(queue_name, job_ids={int(job_id) for job_id in job_ids})
        except Exception:
            logger.warning("abort index mq purge failed queue=%s job_ids=%s", queue_name, job_ids, exc_info=True)


def _cooperative_index_abort_check(
    db: Session,
    job: KbIndexJob,
    *,
    worker_id: str | None = None,
    lease_generation: int | None = None,
) -> None:
    """刷新 job/文件状态；若应停止索引则抛 KbIndexJobAborted。"""
    db.refresh(job)
    if job.status != JOB_RUNNING:
        raise KbIndexJobAborted(job.last_error or "job no longer running")
    if not _index_lease_matches(
        job,
        worker_id=worker_id,
        lease_generation=lease_generation,
    ):
        raise KbIndexJobAborted(LEASE_LOST_MSG)
    exists = (
        db.query(FileModel.id)
        .filter(FileModel.id == job.file_id, FileModel.user_id == job.user_id)
        .first()
    )
    if not exists:
        job.status = JOB_ERROR
        job.last_error = "file not found"
        raise KbIndexJobAborted("file not found")


def delete_chunks_for_file(db: Session, file_id: int) -> None:
    from services.kb_association_claim_service import delete_association_artifacts_for_file
    from services.kb_entity_extract_service import delete_doc_entity_edges_for_file
    from services.kb_sag_event_extract_service import delete_sag_events_for_file
    from services.vector_index import get_vector_index_backend

    delete_association_artifacts_for_file(db, file_id)
    delete_doc_entity_edges_for_file(db, file_id)
    delete_sag_events_for_file(db, file_id)
    get_vector_index_backend(db).delete_by_file_id(file_id)
    db.query(KbChunk).filter(KbChunk.file_id == file_id).delete()


def _notify_file_index(f: FileModel) -> None:
    from messaging.kb_index_publisher import publish_file_index_notify

    try:
        publish_file_index_notify(f)
    except Exception:
        logger.exception("publish kb index notify failed file_id=%s", f.id)




def prepare_force_reindex_file(f: FileModel) -> None:
    """Clear manual override and fingerprint before force reindex (047/061)."""
    f.kb_index_manual_override = False
    f.index_source_hash = None
    f.index_pipeline_fingerprint = None
    f.index_fingerprint_payload = None
    f.raptor_built_chunk_count = None
    f.raptor_built_md_chars = None


def should_force_index_after_extract(f: FileModel, job) -> bool:
    """Reextract with force overwrite or on already-indexed file must rebuild vectors."""
    if job.bypass_mineru_cache:
        return True
    if not job.provider:
        return False
    return bool(f.index_pipeline_fingerprint) or (f.chunk_count or 0) > 0


def enqueue_index_after_extract(db: Session, f: FileModel, job) -> int | None:
    force = should_force_index_after_extract(f, job)
    if force:
        prepare_force_reindex_file(f)
    return enqueue_index(db, f.user_id, f.id, force=force)


def enqueue_index(db: Session, user_id: int, file_id: int, *, force: bool = False) -> int | None:
    """写入 queued 任务并置 pending；须在 db.commit() 之后调用 publish_index_job。

    若存在在途 post job，会在本函数内调用 reconcile_and_commit_superseded_post_jobs
    并 commit，使 supersede 跨 Session 可见（调用方 Session 内已 flush 的变更亦会提交）。
    """

    f = db.query(FileModel).filter(FileModel.id == file_id, FileModel.user_id == user_id).first()
    if not f:
        return None
    from services.kb_post_service import reconcile_and_commit_superseded_post_jobs
    existing_queued = (
        db.query(KbIndexJob)
        .filter(KbIndexJob.file_id == file_id, KbIndexJob.status == JOB_QUEUED)
        .order_by(KbIndexJob.id.desc())
        .first()
    )
    existing_running = (
        db.query(KbIndexJob)
        .filter(KbIndexJob.file_id == file_id, KbIndexJob.status == JOB_RUNNING)
        .first()
    )
    f.index_status = STATUS_PENDING
    f.index_error = None
    f.indexed_at = None
    job_to_publish: int | None = None
    if existing_running:
        # 正在索引时再次保存 MD：追加新任务，当前任务完成后会消费到最新内容
        new_job = KbIndexJob(user_id=user_id, file_id=file_id, status=JOB_QUEUED, force=force)
        db.add(new_job)
        db.flush()
        job_to_publish = new_job.id
    elif existing_queued:
        # 队列中已有任务但可能未投递到 RabbitMQ（或消息丢失）：重新发布
        if force:
            existing_queued.force = True
        job_to_publish = existing_queued.id
        db.flush()
    else:
        new_job = KbIndexJob(user_id=user_id, file_id=file_id, status=JOB_QUEUED, force=force)
        db.add(new_job)
        db.flush()
        job_to_publish = new_job.id
    if job_to_publish is not None:
        reconcile_and_commit_superseded_post_jobs(
            db,
            file_id,
            superseding_index_job_id=job_to_publish,
        )
    return job_to_publish


def publish_index_job(db: Session, user_id: int, file_id: int, job_id: int) -> None:
    """在 enqueue 对应事务 commit 之后调用，避免消费者先于提交收到消息。"""
    from messaging.kb_index_publisher import publish_kb_index_job

    try:
        publish_kb_index_job(job_id)
    except Exception:
        logger.exception("publish kb index job failed job_id=%s", job_id)
    f = db.query(FileModel).filter(FileModel.id == file_id, FileModel.user_id == user_id).first()
    if f:
        _notify_file_index(f)
        try:
            from messaging.mq_status_watcher import request_refresh

            request_refresh()
        except Exception:
            pass


def mark_skipped_no_text(db: Session, f: FileModel, job: KbIndexJob | None) -> None:
    from services.kb_post_service import reconcile_and_commit_superseded_post_jobs

    reconcile_and_commit_superseded_post_jobs(
        db, f.id, superseding_index_job_id=job.id if job else None
    )
    delete_chunks_for_file(db, f.id)
    f.index_status = STATUS_SKIPPED
    f.chunk_count = 0
    f.indexed_at = None
    f.index_error = None
    if job:
        job.status = JOB_DONE
        job.last_error = None
        _log_index_pipeline(db, job, ACTION_KB_INDEX_SKIP, reason="no_text")


def _log_index_pipeline(db: Session, job: KbIndexJob, action: str, **fields) -> None:
    detail = format_kb_pipeline_detail(job_id=job.id, **fields)
    log_kb_pipeline_event(db, job.user_id, action, job.file_id, detail=detail)
    if action != ACTION_KB_INDEX_ERROR:
        return
    reason_text = str(fields.get("reason") or "").lower()
    reason = "timeout" if "timeout" in reason_text else "unknown"
    try:
        from services.rag_quality_failure_service import build_failure_event, persist_failure_event

        persist_failure_event(
            db,
            job.user_id,
            build_failure_event(
                stage="index",
                reason=reason,
                file_id=job.file_id,
                job_id=job.id,
                request_id=None,
                trace_id=None,
                provider="ollama" if "embed" in reason_text else None,
                summary=fields.get("reason") or action,
                retryable=False,
            ),
        )
    except Exception:
        logger.warning("persist index failure telemetry failed job_id=%s", job.id, exc_info=True)


def resolve_index_job_text(
    db: Session,
    f: FileModel,
    job: KbIndexJob,
) -> tuple[str | None, str | None]:
    """Resolve normal source text or an active correction overlay for this job."""
    if not job.correction_overlay_id:
        return resolve_index_text(f)
    overlay = db.get(KbCorrectionOverlay, job.correction_overlay_id)
    if overlay is None or overlay.source_file_id != f.id:
        raise ValueError("correction overlay source file not found")
    if overlay.state != "ACTIVE":
        raise ValueError("correction overlay is not active")
    return overlay.content, "correction_overlay"


def run_index_job(
    db: Session,
    job: KbIndexJob,
    *,
    effective: dict[str, str] | None = None,
    resume_after_deadlock: bool = False,
) -> None:
    f = db.query(FileModel).filter(FileModel.id == job.file_id, FileModel.user_id == job.user_id).first()
    if not f:
        job.attempts = (job.attempts or 0) + 1
        job.status = JOB_ERROR
        job.last_error = "file not found"
        return

    if resume_after_deadlock:
        db.refresh(job)
        db.refresh(f)
    else:
        claimed = _ensure_index_job_claimed(db, job)
        if claimed is None:
            logger.warning(
                "kb_index_job_not_claimed job_id=%s status=%s",
                getattr(job, "id", None),
                getattr(job, "status", None),
            )
            return
        job = claimed
        job.attempts = (job.attempts or 0) + 1
        f.index_status = STATUS_INDEXING
        f.index_error = None
        db.flush()
        # 提交后 API / MQ 监控才能看到 running；长任务（Ollama）期间保持可见
        db.commit()
        _notify_file_index(f)
        _log_index_pipeline(db, job, ACTION_KB_INDEX_START, force=bool(job.force))
    expected_worker_id = job.worker_id
    expected_lease_generation = job.lease_generation

    text, source = resolve_index_job_text(db, f, job)
    if not text or not source:
        _cooperative_index_abort_check(
            db,
            job,
            worker_id=expected_worker_id,
            lease_generation=expected_lease_generation,
        )
        mark_skipped_no_text(db, f, job)
        return

    text_to_chunk = build_text_to_chunk(f, text)
    md_char_count = len(text)

    if f.kb_index_manual_override and not job.force:
        logger.info("kb_index_manual_override_skip file_id=%s job_id=%s", f.id, job.id)
        _cooperative_index_abort_check(
            db,
            job,
            worker_id=expected_worker_id,
            lease_generation=expected_lease_generation,
        )
        if (f.chunk_count or 0) > 0:
            f.index_status = STATUS_READY
        job.status = JOB_DONE
        job.last_error = None
        if overlay := db.get(KbCorrectionOverlay, job.correction_overlay_id) if job.correction_overlay_id else None:
            overlay.reindex_status = "SUCCEEDED"
        _log_index_pipeline(db, job, ACTION_KB_INDEX_SKIP, reason="manual_override")
        return

    if effective is None:
        effective = get_user_effective_dict(db, f.user_id)
    ollama_cfg = get_ollama_runtime_config(db, fresh=True)
    chunk_params = resolve_effective_chunk_params(db, f, effective=effective, md_char_count=md_char_count)
    text_hash = compute_index_source_hash(text_to_chunk)
    from services.system_setting_service import get_kb_sag_event_fingerprint_fields

    fp_payload = fingerprint_payload(
        text_hash=text_hash,
        profile_name=chunk_params.profile_name,
        chunk_size=chunk_params.chunk_size,
        chunk_overlap=chunk_params.overlap,
        embedding_model=ollama_cfg.embed_model,
        **get_kb_sag_event_fingerprint_fields(db),
    )
    computed_fingerprint = compute_index_pipeline_fingerprint(**fp_payload)

    if (
        not job.force
        and f.index_status == STATUS_READY
        and f.index_pipeline_fingerprint
        and f.index_pipeline_fingerprint == computed_fingerprint
        and (f.chunk_count or 0) > 0
    ):
        _cooperative_index_abort_check(
            db,
            job,
            worker_id=expected_worker_id,
            lease_generation=expected_lease_generation,
        )
        job.status = JOB_DONE
        job.last_error = None
        _log_index_pipeline(db, job, ACTION_KB_INDEX_SKIP, reason="fingerprint_unchanged")
        _notify_file_index(f)
        return

    if (
        not job.force
        and f.index_pipeline_fingerprint
        and f.index_pipeline_fingerprint != computed_fingerprint
    ):
        log_fingerprint_mismatch(
            f,
            computed_fingerprint=computed_fingerprint,
            payload=fp_payload,
        )

    try:
        large_pdf = False
        if chunk_params.use_structure:
            pieces = chunk_markdown(
                text_to_chunk,
                chunk_size=chunk_params.chunk_size,
                overlap=chunk_params.overlap,
                split_recursive=chunk_params.split_recursive,
            )
        else:
            pieces = chunk_text(
                text_to_chunk,
                chunk_size=chunk_params.chunk_size,
                overlap=chunk_params.overlap,
                split_recursive=chunk_params.split_recursive,
            )

        stored_strategy_id = getattr(job, "strategy_id", None)
        strategy_id = stored_strategy_id or "current"
        strategy_version = getattr(job, "strategy_version", None) if stored_strategy_id else "current-v1"
        strategy_id, strategy_version = resolve_chunk_strategy(strategy_id, strategy_version)
        if strategy_id != "current" and not f.source_sha256:
            raise ValueError("non-current chunk strategies require files.source_sha256")
        strategy_items = apply_chunk_strategy(
            text_to_chunk,
            pieces,
            strategy_id=strategy_id,
            strategy_version=strategy_version,
        )
        pieces = [item.chunk for item in strategy_items]

        logger.info(
            "kb_index chunks ready file_id=%s job_id=%s chunks=%d source=%s md_chars=%d use_structure=%s",
            f.id,
            job.id,
            len(pieces),
            source,
            md_char_count,
            bool(chunk_params.use_structure),
        )

        from services.system_setting_service import get_kb_large_doc_settings
        large = get_kb_large_doc_settings(db)
        large_pdf = (md_char_count or 0) > large["char_threshold"]
        if large_pdf:
            logger.info(
                "kb_index large_pdf_mode file_id=%s md_chars=%d chosen_chunk_size=%d profile=%s",
                f.id, md_char_count, chunk_params.chunk_size, chunk_params.profile_name
            )

        from services.kb_post_service import reconcile_and_commit_superseded_post_jobs

        reconcile_and_commit_superseded_post_jobs(
            db, f.id, superseding_index_job_id=job.id
        )
        db.refresh(f)
        db.refresh(job)

        persist_elapsed_sec = 0.0
        t_delete = time.perf_counter()
        delete_chunks_for_file(db, f.id)
        persist_elapsed_sec += time.perf_counter() - t_delete
        if not pieces:
            _cooperative_index_abort_check(
                db,
                job,
                worker_id=expected_worker_id,
                lease_generation=expected_lease_generation,
            )
            mark_skipped_no_text(db, f, job)
            return

        fts_config = get_effective_fts_config(db, effective=effective)
        prefix_offset = len(text_to_chunk) - len(text)
        marker_pieces = [
            TextChunk(
                text=piece.text,
                char_start=piece.char_start - prefix_offset,
                char_end=piece.char_end - prefix_offset,
                heading_path=piece.heading_path,
                block_type=piece.block_type,
                loc_type=piece.loc_type,
                loc_start=piece.loc_start,
                loc_end=piece.loc_end,
                loc_label=piece.loc_label,
            )
            for piece in pieces
        ]
        enriched = enrich_chunks_with_content_metadata(text, marker_pieces)
        if strategy_id == "multimodal":
            for idx, ((marker_piece, content_kind, content_meta), _) in enumerate(zip(enriched, strategy_items)):
                if strategy_items[idx].role != "multimodal":
                    continue
                validate_multimodal_metadata(
                    content_kind,
                    content_meta,
                    source_hash=f.source_sha256 or "",
                    has_locator=bool(
                        marker_piece.loc_type
                        or marker_piece.loc_start is not None
                        or marker_piece.loc_end is not None
                    ),
                    asset_exists=(
                        resolve_figure_asset_abs_path(f, content_meta) is not None
                        if content_kind == "figure"
                        else None
                    ),
                )
        embed_ctx = load_file_embed_context(db, f)
        embed_inputs = [
            build_embed_input(
                body=pieces[idx].text,
                heading_path=pieces[idx].heading_path,
                workspace_name=embed_ctx.workspace_name,
                tags=embed_ctx.tags,
                content_kind=content_kind,
                original_name=f.original_name,
            )
            for idx, (_, content_kind, _) in enumerate(enriched)
        ]
        t_embed = time.perf_counter()
        total_chunks = len(embed_inputs)
        logger.info(
            "kb_index embedding file_id=%s job_id=%s chunks=%d",
            f.id,
            job.id,
            total_chunks,
        )
        heartbeat_cb = _job_heartbeat_cb(job.id, expected_worker_id, expected_lease_generation)

        def _emit_embed_chunk_progress(done: int, total: int) -> None:
            pct = (100.0 * done / total) if total else 0.0
            logger.info(
                "kb_index embed chunk done file_id=%s job_id=%s chunk=%d/%d pct=%.1f%%",
                f.id,
                job.id,
                done,
                total,
                pct,
            )
            from messaging.mq_progress_notify import maybe_publish_index_progress

            maybe_publish_index_progress(
                user_id=int(f.user_id),
                file_id=int(f.id),
                progress_stage="向量嵌入",
                progress_pct=int(pct),
                progress_detail=f"{done}/{total}",
            )

        try:
            vectors = resolve_embedding_vectors(
                db,
                embed_inputs,
                heartbeat_cb=heartbeat_cb,
                progress_cb=_emit_embed_chunk_progress,
            )
        except KbIndexJobAborted:
            logger.info("kb_index job aborted during embed job_id=%s file_id=%s", job.id, job.file_id)
            return
        embed_ms = int((time.perf_counter() - t_embed) * 1000)
        from messaging.mq_progress_notify import maybe_publish_index_progress

        maybe_publish_index_progress(
            user_id=int(f.user_id),
            file_id=int(f.id),
            progress_stage="写入向量",
            progress_pct=None,
            force=True,
        )
        try:
            _cooperative_index_abort_check(
                db,
                job,
                worker_id=expected_worker_id,
                lease_generation=expected_lease_generation,
            )
        except KbIndexJobAborted:
            logger.info(
                "kb_index job aborted before persist job_id=%s file_id=%s",
                job.id,
                job.file_id,
            )
            return
        logger.info("kb_index embed done file_id=%s embed_ms=%d", f.id, embed_ms)
        if len(vectors) != len(pieces):
            raise OllamaEmbedError(f"embedding count {len(vectors)} != chunk count {len(pieces)}")
        vector_backend = get_vector_index_backend(db)
        pending_chunks: list[tuple[KbChunk, str, list[float]]] = []
        t_persist = time.perf_counter()
        parent_ids: dict[str, str] = {}
        if f.source_sha256 and strategy_id != "current":
            for idx, item in enumerate(strategy_items):
                if item.role not in {"parent", "outline"}:
                    continue
                stored = item.chunk
                parent_ids[item.parent_group or "__document__"] = build_strategy_chunk_id(
                    source_file_id=f.id,
                    source_hash=f.source_sha256,
                    strategy_id=strategy_id,
                    strategy_version=strategy_version,
                    locator={
                        "kind": stored.loc_type or item.role,
                        "start": stored.loc_start,
                        "end": stored.loc_end,
                        "label": stored.loc_label,
                        "path": stored.heading_path,
                    },
                    ordinal=idx,
                )
        for idx, ((marker_piece, content_kind, content_meta), vec) in enumerate(zip(enriched, vectors)):
            stored = pieces[idx]
            heading_path = cap_heading_path(stored.heading_path)
            if (
                stored.heading_path
                and heading_path is not None
                and len(stored.heading_path.strip()) > KB_HEADING_PATH_MAX_LEN
            ):
                logger.debug(
                    "kb_heading_path_truncated file_id=%s chunk_index=%s orig_len=%s cap=%s prefix=%r",
                    f.id,
                    idx,
                    len(stored.heading_path.strip()),
                    KB_HEADING_PATH_MAX_LEN,
                    heading_path[:KB_HEADING_DEBUG_PREFIX_LEN],
                )
            persisted_content_meta = dict(content_meta or {})
            if f.source_sha256:
                parent_chunk_id = None
                if strategy_id != "current" and strategy_items[idx].role in {"child", "chunk", "multimodal"}:
                    parent_chunk_id = parent_ids.get(strategy_items[idx].parent_group or "")
                locator = {
                    "kind": stored.loc_type or "text",
                    "start": stored.loc_start,
                    "end": stored.loc_end,
                    "label": stored.loc_label,
                }
                if strategy_id != "current":
                    locator["path"] = stored.heading_path
                persisted_content_meta["strategy_provenance"] = build_strategy_chunk_metadata(
                    source_file_id=f.id,
                    source_hash=f.source_sha256,
                    strategy_id=strategy_id,
                    strategy_version=strategy_version,
                    locator=locator,
                    ordinal=idx,
                    parent_chunk_id=parent_chunk_id,
                    directory_path=heading_path.split(" > ") if heading_path else [],
                    content_kind=strategy_items[idx].content_kind or content_kind or "text",
                    acl_scope={"workspace_id": f.workspace_id, "user_id": f.user_id},
                )
            chunk = KbChunk(
                user_id=f.user_id,
                workspace_id=f.workspace_id,
                file_id=f.id,
                chunk_index=idx,
                source=source,
                text=stored.text,
                heading_path=heading_path,
                block_type=stored.block_type,
                content_kind=content_kind,
                content_meta=persisted_content_meta or None,
                text_search=func.to_tsvector(fts_config, stored.text),
                char_start=stored.char_start,
                char_end=stored.char_end,
                loc_type=stored.loc_type,
                loc_start=stored.loc_start,
                loc_end=stored.loc_end,
                loc_label=stored.loc_label,
            )
            db.add(chunk)
            pending_chunks.append((chunk, content_kind, vec))
        db.flush()
        vector_records: list[VectorRecord] = []
        for chunk, content_kind, vec in pending_chunks:
            vector_records.append(
                VectorRecord(
                    chunk_id=int(chunk.id),
                    file_id=f.id,
                    workspace_id=f.workspace_id,
                    user_id=f.user_id,
                    content_kind=content_kind,
                    embedding=vec,
                    embedding_model=ollama_cfg.embed_model,
                )
            )
        if vector_records:
            vector_backend.upsert_many(vector_records, heartbeat_cb=heartbeat_cb)
        _cooperative_index_abort_check(
            db,
            job,
            worker_id=expected_worker_id,
            lease_generation=expected_lease_generation,
        )
        persist_elapsed_sec += time.perf_counter() - t_persist
        persist_ms = int(persist_elapsed_sec * 1000)
        f.index_status = STATUS_READY
        f.chunk_count = len(pieces)
        f.indexed_at = naive_db_now()
        f.index_error = None
        f.index_pipeline_fingerprint = computed_fingerprint
        f.index_fingerprint_payload = fingerprint_canonical_json(fp_payload)
        # 144: enqueue only. Association extraction must not make vector indexing
        # fail when its LLM/DB path is unavailable.
        from services.kb_association_job_service import enqueue_association_job

        try:
            enqueue_association_job(db, f)
        except Exception:
            logger.exception("kb association enqueue failed file_id=%s; index remains ready", f.id)
        job.status = JOB_DONE
        job.last_error = None
        if overlay := db.get(KbCorrectionOverlay, job.correction_overlay_id) if job.correction_overlay_id else None:
            overlay.reindex_status = "SUCCEEDED"
        done_fields: dict[str, object] = dict(
            chunk_count=len(pieces),
            source=source,
            embed_ms=embed_ms,
            persist_ms=persist_ms,
            large_pdf=large_pdf,
        )
        _log_index_pipeline(db, job, ACTION_KB_INDEX_DONE, **done_fields)

        from services.kb_post_service import maybe_enqueue_post_job, run_sync_post_in_index
        from services.system_setting_service import is_kb_post_async_enabled

        if is_kb_post_async_enabled(db):
            maybe_enqueue_post_job(
                db,
                f,
                job,
                md_char_count=md_char_count,
                large_pdf=large_pdf,
                pipeline_fingerprint=computed_fingerprint,
            )
        else:
            run_sync_post_in_index(
                db,
                f,
                job,
                md_char_count=md_char_count,
                source=source,
                fts_config=fts_config,
                large_pdf=large_pdf,
                pipeline_fingerprint=computed_fingerprint,
            )
    except KbIndexJobAborted:
        logger.info("kb_index job aborted job_id=%s file_id=%s", job.id, job.file_id)
        return
    except OllamaEmbedError as exc:
        logger.warning(
            "kb_index_job_embed_failed job_id=%s file_id=%s error=%s",
            job.id,
            job.file_id,
            str(exc)[:500],
        )
        db.refresh(job)
        if job.status != JOB_RUNNING or not _index_lease_matches(
            job,
            worker_id=expected_worker_id,
            lease_generation=expected_lease_generation,
        ):
            logger.info("kb_index skip terminal error after lease lost job_id=%s", job.id)
            return
        f.index_status = STATUS_FAILED
        f.index_error = str(exc)[:2000]
        job.status = JOB_ERROR
        job.last_error = str(exc)[:2000]
        _log_index_pipeline(db, job, ACTION_KB_INDEX_ERROR, reason=pipeline_reason(str(exc)))
    except Exception as exc:
        logger.exception("index job %s failed", job.id)
        db.refresh(job)
        if job.status != JOB_RUNNING or not _index_lease_matches(
            job,
            worker_id=expected_worker_id,
            lease_generation=expected_lease_generation,
        ):
            logger.info("kb_index skip terminal error after lease lost job_id=%s", job.id)
            return
        f.index_status = STATUS_FAILED
        f.index_error = str(exc)[:2000]
        job.status = JOB_ERROR
        job.last_error = str(exc)[:2000]
        _log_index_pipeline(db, job, ACTION_KB_INDEX_ERROR, reason=pipeline_reason(str(exc)))


STALE_RUNNING_RECOVERED_MSG = "stale running recovered (indexer interrupted or superseded)"
STALE_RUNNING_REQUEUED_MSG = "stale running requeued (worker interrupted)"


def touch_kb_index_job_heartbeat(
    job_id: int,
    *,
    worker_id: str | None = None,
    lease_generation: int | None = None,
) -> bool:
    """独立短事务刷新 running job 的 heartbeat_at；不得复用 run_index_job 主 Session。

    仅由 run_index_job 经 heartbeat_cb 调用；RAPTOR / chunk patch 等侧路径不接（RAPTOR 在长事务内运行，直连会自锁 kb_index_jobs 行）。
    若文件已删或 job 已取消，抛 KbIndexJobAborted 以便 embed 循环提前结束。
    """
    from database import SessionLocal

    db = SessionLocal()
    try:
        job = db.query(KbIndexJob).filter(KbIndexJob.id == job_id).first()
        if job is None or job.status != JOB_RUNNING:
            raise KbIndexJobAborted(job.last_error if job else "job missing")
        if not _index_lease_matches(
            job,
            worker_id=worker_id,
            lease_generation=lease_generation,
        ):
            return False
        file_exists = db.query(FileModel.id).filter(FileModel.id == job.file_id).first()
        if not file_exists:
            job.status = JOB_ERROR
            job.last_error = "file not found"
            db.commit()
            raise KbIndexJobAborted("file not found")
        now = naive_db_now()
        job.heartbeat_at = now
        job.updated_at = now
        db.commit()
        return True
    except KbIndexJobAborted:
        raise
    except Exception:
        logger.warning("kb_index_job_heartbeat_failed job_id=%s", job_id, exc_info=True)
        db.rollback()
        return False
    finally:
        db.close()


def _job_heartbeat_cb(
    job_id: int,
    worker_id: str | None,
    lease_generation: int | None,
) -> Callable[[], None]:
    def _touch() -> None:
        ok = touch_kb_index_job_heartbeat(
            job_id,
            worker_id=worker_id,
            lease_generation=lease_generation,
        )
        if not ok:
            raise KbIndexJobAborted(LEASE_LOST_MSG)

    return _touch


def _request_mq_status_refresh() -> None:
    try:
        from messaging.mq_status_watcher import request_refresh

        request_refresh()
    except Exception:
        pass


def _newer_finished_job_exists(db: Session, file_id: int, running_job: KbIndexJob) -> bool:
    return (
        db.query(KbIndexJob.id)
        .filter(
            KbIndexJob.file_id == file_id,
            KbIndexJob.status.in_((JOB_DONE, JOB_ERROR)),
            KbIndexJob.id > running_job.id,
        )
        .limit(1)
        .first()
        is not None
    )


def _should_close_stale_running(
    db: Session, job: KbIndexJob, f: FileModel | None, *, stale_by_time: bool
) -> str | None:
    """返回应收尾的状态 done/error；None 表示仍视为活跃 running。"""
    if _newer_finished_job_exists(db, job.file_id, job):
        return JOB_DONE
    if f and f.index_status in (STATUS_READY, STATUS_SKIPPED):
        return JOB_DONE
    if not stale_by_time:
        return None
    if f and f.index_status == STATUS_FAILED:
        job.last_error = (f.index_error or STALE_RUNNING_RECOVERED_MSG)[:2000]
        return JOB_ERROR
    job.last_error = STALE_RUNNING_RECOVERED_MSG
    if f:
        f.index_status = STATUS_FAILED
        f.index_error = STALE_RUNNING_RECOVERED_MSG
    return JOB_ERROR


def reconcile_superseded_running_jobs(db: Session, file_id: int, active_job_id: int) -> int:
    """同文件另一索引任务已结束后，收尾遗留的 running 行（避免 MQ 监控长期误报）。"""
    others = (
        db.query(KbIndexJob)
        .filter(
            KbIndexJob.file_id == file_id,
            KbIndexJob.status == JOB_RUNNING,
            KbIndexJob.id < active_job_id,
        )
        .all()
    )
    if not others:
        return 0
    now = naive_db_now()
    for job in others:
        job.status = JOB_DONE
        job.last_error = None
        job.updated_at = now
    logger.info(
        "reconciled superseded running kb index job(s) file_id=%s active_job_id=%s count=%s ids=%s",
        file_id,
        active_job_id,
        len(others),
        [j.id for j in others],
    )
    return len(others)


def reconcile_stale_kb_index_jobs(db: Session) -> dict[str, int]:
    """启动或周期调用：恢复陈旧 running，并修正无 running 却 indexing 的文件。"""
    now = naive_db_now()
    cutoff = now - timedelta(seconds=KB_INDEX_RUNNING_STALE_SEC)
    running_jobs = db.query(KbIndexJob).filter(KbIndexJob.status == JOB_RUNNING).all()
    closed_done = 0
    closed_error = 0
    requeued = 0
    for job in running_jobs:
        f = db.query(FileModel).filter(FileModel.id == job.file_id).first()
        heartbeat_at = job.heartbeat_at or job.updated_at
        stale_by_time = heartbeat_at is not None and heartbeat_at <= cutoff
        stale_age_sec = (
            int((now - heartbeat_at).total_seconds()) if heartbeat_at is not None else None
        )
        new_status = _should_close_stale_running(db, job, f, stale_by_time=stale_by_time)
        if new_status is None:
            continue
        if new_status == JOB_DONE:
            job.status = JOB_DONE
            job.updated_at = now
            job.last_error = None
            closed_done += 1
        else:
            old_worker_id = job.worker_id
            job.status = JOB_QUEUED
            job.last_error = STALE_RUNNING_REQUEUED_MSG
            job.worker_id = None
            job.claimed_at = None
            job.heartbeat_at = now
            job.updated_at = now
            job.lease_generation = (job.lease_generation or 0) + 1
            if f:
                f.index_status = STATUS_PENDING
                f.index_error = None
            _log_index_pipeline(
                db,
                job,
                ACTION_KB_INDEX_RECOVER,
                reason="stale_running_requeued",
                worker_id=old_worker_id,
                lease_generation=job.lease_generation,
            )
            requeued += 1
        logger.warning(
            "reconciled stale running kb index job_id=%s file_id=%s -> %s stale_by_time=%s "
            "stale_age_sec=%s cutoff=%s",
            job.id,
            job.file_id,
            job.status,
            stale_by_time,
            stale_age_sec,
            cutoff.isoformat(),
        )

    active_file_ids = {
        row[0]
        for row in db.query(KbIndexJob.file_id).filter(KbIndexJob.status == JOB_RUNNING).distinct().all()
    }
    orphan_files = 0
    for f in db.query(FileModel).filter(FileModel.index_status == STATUS_INDEXING).all():
        if f.id in active_file_ids:
            continue
        f.index_status = STATUS_PENDING
        f.index_error = None
        orphan_files += 1
        logger.warning("reconciled orphan indexing file_id=%s -> pending", f.id)

    if closed_done or closed_error or requeued or orphan_files:
        _request_mq_status_refresh()
    return {
        "running_closed_done": closed_done,
        "running_closed_error": closed_error,
        "running_requeued": requeued,
        "orphan_indexing_files": orphan_files,
    }
