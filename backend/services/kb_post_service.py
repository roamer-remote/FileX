# Copyright (c) 2026 徐泽宇
"""KB post-processing: entity / SAG / RAPTOR via kb.post MQ (114)."""

from __future__ import annotations

import logging
import os
import socket
import time
import uuid
from collections.abc import Callable
from datetime import datetime, timedelta

from sqlalchemy import select, text
from sqlalchemy.orm import Session

from config import GPU_SCHEDULER_ENABLED, KB_POST_REPLAY_STALE_SEC, KB_POST_RUNNING_STALE_SEC
from models.file import File as FileModel
from models.kb_index_job import KbIndexJob
from models.kb_post_job import KbPostJob
from models.user import User
from services.kb_fts_service import get_effective_fts_config
from services.kb_text_source import resolve_index_text
from services.gpu_model_lifecycle_service import GpuOomError, GpuWaitingError
from services.kb_pipeline_log_service import (
    ACTION_KB_FORCE_RAPTOR_DONE,
    ACTION_KB_FORCE_RAPTOR_START,
    ACTION_KB_FORCE_RAPTOR_WARN,
    ACTION_KB_POST_DONE,
    ACTION_KB_POST_ERROR,
    ACTION_KB_POST_RECOVER,
    ACTION_KB_POST_SKIP,
    ACTION_KB_POST_START,
    ACTION_KB_RAPTOR_WARN,
    format_kb_pipeline_detail,
    log_kb_pipeline_event,
    pipeline_reason,
)
from services.system_setting_service import get_kb_post_max_attempts
from services.user_setting_service import get_user_effective_dict
from utils.timezone import naive_db_now

logger = logging.getLogger(__name__)

POST_STATUS_PENDING = "pending"
POST_STATUS_QUEUED = "queued"
POST_STATUS_RUNNING = "running"
POST_STATUS_WAITING_GPU = "waiting_gpu"
POST_STATUS_READY = "ready"
POST_STATUS_FAILED = "failed"
POST_STATUS_SKIPPED = "skipped"

JOB_QUEUED = "queued"
JOB_RUNNING = "running"
JOB_WAITING_GPU = "waiting_gpu"
JOB_DONE = "done"
JOB_ERROR = "error"

STALE_RUNNING_RECOVERED_MSG = "stale running post recovered (worker interrupted or superseded)"
STALE_RUNNING_REQUEUED_MSG = "stale running post requeued (worker interrupted)"
LEASE_LOST_MSG = "post job lease lost"

ADVISORY_LOCK_KB_POST_CLAIM = 900128

from collections import namedtuple
_LeaseToken = namedtuple("_LeaseToken", ["worker_id", "lease_generation"])


class KbPostJobAborted(Exception):
    """Cooperative abort when post job superseded or file removed."""


def make_kb_post_worker_id() -> str:
    return f"kb-post:{socket.gethostname()}:{os.getpid()}:{uuid.uuid4().hex[:12]}"


def claim_kb_post_job(db: Session, job_id: int, *, worker_id: str) -> KbPostJob | None:
    """Atomically claim one queued post job with a worker lease."""
    job = (
        db.query(KbPostJob)
        .filter(KbPostJob.id == job_id, KbPostJob.status.in_((JOB_QUEUED, JOB_WAITING_GPU)))
        .with_for_update()
        .first()
    )
    if job is None:
        return None
    # Prevent concurrent claims for the same file via advisory lock.
    db.execute(text("SELECT pg_advisory_xact_lock(:key1, :key2)"), {
        "key1": ADVISORY_LOCK_KB_POST_CLAIM,
        "key2": job.file_id,
    })
    active_same_file = (
        db.query(KbPostJob.id)
        .filter(
            KbPostJob.file_id == job.file_id,
            KbPostJob.status == JOB_RUNNING,
            KbPostJob.id != job.id,
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


def _ensure_post_job_claimed(db: Session, job: KbPostJob) -> KbPostJob | None:
    if job.status == JOB_RUNNING:
        return job
    if job.status not in (JOB_QUEUED, JOB_WAITING_GPU):
        return None
    claimed = claim_kb_post_job(db, int(job.id), worker_id=make_kb_post_worker_id())
    if claimed is None:
        return None
    db.refresh(claimed)
    return claimed


def _post_lease_matches(
    job: KbPostJob,
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


def _post_work_needed(
    db: Session,
    *,
    md_char_count: int,
    large_pdf: bool,
) -> tuple[bool, str | None, bool]:
    from services.system_setting_service import (
        get_kb_raptor_settings,
        is_kb_large_doc_post_enabled,
        is_kb_large_doc_raptor_enabled,
    )
    from services.kb_pipeline_service import should_rebuild_entity_edges_after_index

    skip_entity_sag = large_pdf and not is_kb_large_doc_post_enabled(db)
    entity_needed = (not skip_entity_sag) and should_rebuild_entity_edges_after_index(db)
    sag_needed = not skip_entity_sag

    raptor_needed = False
    raptor_settings = get_kb_raptor_settings(db)
    if raptor_settings.enabled and md_char_count >= raptor_settings.min_chars:
        if large_pdf and not is_kb_large_doc_raptor_enabled(db):
            raptor_needed = False
        else:
            raptor_needed = True

    if entity_needed or sag_needed or raptor_needed:
        return True, None, raptor_needed
    if skip_entity_sag and not raptor_needed:
        return False, "large_doc_post_skipped", False
    return False, "post_not_needed", False


def reconcile_superseded_running_post_jobs(
    db: Session,
    file_id: int,
    *,
    superseding_index_job_id: int | None = None,
) -> int:
    """Mark in-flight post jobs error before index delete_chunks (M2)."""
    others = (
        db.query(KbPostJob)
        .filter(
            KbPostJob.file_id == file_id,
            KbPostJob.status.in_((JOB_QUEUED, JOB_RUNNING)),
        )
        .all()
    )
    if not others:
        return 0
    now = naive_db_now()
    msg = (
        f"superseded by index job {superseding_index_job_id}"
        if superseding_index_job_id is not None
        else "superseded"
    )
    f = db.query(FileModel).filter(FileModel.id == file_id).first()
    for job in others:
        job.status = JOB_ERROR
        job.last_error = msg[:2000]
        job.updated_at = now
    if f is not None:
        f.raptor_built_chunk_count = None
        f.raptor_built_md_chars = None
    if others:
        db.flush()
    logger.info(
        "reconciled superseded kb post job(s) file_id=%s index_job_id=%s count=%s ids=%s",
        file_id,
        superseding_index_job_id,
        len(others),
        [j.id for j in others],
    )
    return len(others)


def reconcile_and_commit_superseded_post_jobs(
    db: Session,
    file_id: int,
    *,
    superseding_index_job_id: int | None = None,
) -> int:
    """Mark superseded post jobs and commit so other Sessions see error immediately (121)."""
    count = reconcile_superseded_running_post_jobs(
        db,
        file_id,
        superseding_index_job_id=superseding_index_job_id,
    )
    if count:
        db.commit()
        f = db.query(FileModel).filter(FileModel.id == file_id).first()
        if f is not None:
            db.refresh(f)
    return count


def _cooperative_post_abort_check(
    db: Session,
    job: KbPostJob,
    *,
    worker_id: str | None = None,
    lease_generation: int | None = None,
) -> None:
    db.refresh(job)
    if job.status != JOB_RUNNING:
        raise KbPostJobAborted(job.last_error or "post job not running")
    if not _post_lease_matches(
        job,
        worker_id=worker_id,
        lease_generation=lease_generation,
    ):
        raise KbPostJobAborted(LEASE_LOST_MSG)
    f = db.query(FileModel).filter(FileModel.id == job.file_id).first()
    if f is None:
        job.status = JOB_ERROR
        job.last_error = "file not found"
        raise KbPostJobAborted("file not found")


def touch_kb_post_job_heartbeat(
    job_id: int,
    *,
    worker_id: str | None = None,
    lease_generation: int | None = None,
) -> bool:
    from database import SessionLocal

    db = SessionLocal()
    try:
        job = db.query(KbPostJob).filter(KbPostJob.id == job_id).first()
        if job is None or job.status != JOB_RUNNING:
            raise KbPostJobAborted(job.last_error if job else "post job missing")
        if not _post_lease_matches(
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
            raise KbPostJobAborted("file not found")
        now = naive_db_now()
        job.heartbeat_at = now
        job.updated_at = now
        db.commit()
        return True
    except KbPostJobAborted:
        raise
    except Exception:
        logger.warning("kb_post_job_heartbeat_failed job_id=%s", job_id, exc_info=True)
        db.rollback()
        return False
    finally:
        db.close()


def _log_post_pipeline(db: Session, job: KbPostJob, action: str, **fields) -> None:
    detail = format_kb_pipeline_detail(job_id=job.id, index_job_id=job.index_job_id, **fields)
    log_kb_pipeline_event(db, job.user_id, action, job.file_id, detail=detail)



def _write_entity_multi_repr(db: Session, f) -> None:
    """146 P2: Write entity_list representation for multi-repr index."""
    try:
        from services.kb_multi_repr_service import write_repr
        from models.kb_association import KbEntityMention

        entities = db.execute(
            select(KbEntityMention).where(KbEntityMention.file_id == f.id)
        ).scalars().all()

        if entities:
            text = "\n".join(
                f"{e.normalized_surface} ({e.entity_type or 'unknown'})"
                for e in entities[:50]
            )
            write_repr(
                db,
                workspace_id=f.workspace_id,
                file_id=int(f.id),
                representation_type="entity_list",
                source_id=f"file:{f.id}",
                text_content=text,
                embed=True,
            )
    except Exception as e:
        logger.warning("_write_entity_multi_repr failed for file_id=%s: %s", int(f.id), e)


def _write_event_multi_repr(db: Session, f) -> None:
    """146 P2: Write event_summary representation for multi-repr index."""
    try:
        from services.kb_multi_repr_service import write_repr
        from models.kb_event import KbEvent

        events = db.execute(
            select(KbEvent).where(KbEvent.file_id == f.id)
        ).scalars().all()

        for event in events:
            text = f"{event.title or ''}\n{event.summary or ''}".strip()
            if text:
                write_repr(
                    db,
                    workspace_id=f.workspace_id,
                    file_id=int(f.id),
                    representation_type="event_summary",
                    source_id=f"event:{event.id}",
                    text_content=text,
                    embed=True,
                )
    except Exception as e:
        logger.warning("_write_event_multi_repr failed for file_id=%s: %s", int(f.id), e)


def _write_raptor_multi_repr(db: Session, f) -> None:
    """146 P2: Write raptor_summary representation for multi-repr index."""
    try:
        from services.kb_multi_repr_service import write_repr
        from models.kb_chunk import KbChunk
        from models.kb_enums import ContentKind

        raptor_chunks = db.execute(
            select(KbChunk).where(
                KbChunk.file_id == f.id,
                KbChunk.content_kind == ContentKind.raptor_summary.value,
            )
        ).scalars().all()

        for chunk in raptor_chunks:
            text = (chunk.text or "").strip()
            if text:
                write_repr(
                    db,
                    workspace_id=f.workspace_id,
                    file_id=int(f.id),
                    representation_type="raptor_summary",
                    source_id=f"chunk:{chunk.id}",
                    text_content=text,
                    embed=True,
                )
    except Exception:
        logger.exception("_write_raptor_multi_repr failed for file_id=%s", int(f.id))


def _write_section_multi_repr(db: Session, f) -> None:
    """Index each heading path as a retrievable, source-locatable section entry."""
    try:
        from models.kb_chunk import KbChunk
        from models.kb_enums import ContentKind
        from services.kb_multi_repr_service import build_section_repr_text, write_repr

        chunks = db.execute(
            select(KbChunk).where(
                KbChunk.file_id == f.id,
                KbChunk.content_kind == ContentKind.text.value,
                KbChunk.heading_path.is_not(None),
            ).order_by(KbChunk.chunk_index)
        ).scalars().all()
        sections: dict[str, list] = {}
        for chunk in chunks:
            heading = (chunk.heading_path or "").strip()
            if heading:
                sections.setdefault(heading, []).append(chunk)
        for heading, section_chunks in sections.items():
            text = build_section_repr_text(
                heading_path=heading,
                chunks=[chunk.text for chunk in section_chunks[:6]],
            )
            write_repr(
                db,
                workspace_id=f.workspace_id,
                file_id=int(f.id),
                representation_type="section_context",
                source_id=f"chunk:{section_chunks[0].id}",
                text_content=text,
                embed=True,
            )
    except Exception:
        logger.exception("_write_section_multi_repr failed for file_id=%s", int(f.id))


def _execute_post_phases(
    db: Session,
    f: FileModel,
    job: KbPostJob | KbIndexJob,
    *,
    md_char_count: int,
    source: str,
    fts_config: str,
    large_pdf: bool,
    abort_check: Callable[[], None] | None = None,
) -> dict[str, object]:
    from services.kb_post_llm_service import (
        collect_kb_post_llm_telemetry,
        format_kb_post_llm_telemetry,
    )
    from services.system_setting_service import is_kb_large_doc_post_enabled
    from services.kb_pipeline_service import should_rebuild_entity_edges_after_index

    # 146 P2: Clean up old multi-repr entries before rebuilding
    try:
        from services.kb_multi_repr_service import delete_reprs_for_file
        delete_reprs_for_file(db, int(f.id))
    except Exception:
        pass

    post_entity_ms = 0
    post_sag_ms = 0
    post_raptor_ms = 0
    post_skip_reason: str | None = None
    llm_calls = []
    skip_entity_sag = large_pdf and not is_kb_large_doc_post_enabled(db)

    if skip_entity_sag:
        post_skip_reason = "large_doc_post_skipped"
    else:
        if should_rebuild_entity_edges_after_index(db):
            if abort_check:
                abort_check()
            from messaging.mq_progress_notify import maybe_publish_post_progress

            maybe_publish_post_progress(
                user_id=int(f.user_id),
                file_id=int(f.id),
                progress_stage="实体抽取",
                progress_pct=None,
                force=True,
            )
            from services.kb_entity_extract_service import rebuild_doc_entity_edges_for_file

            t_entity = time.perf_counter()
            with collect_kb_post_llm_telemetry(llm_calls):
                rebuild_doc_entity_edges_for_file(db, f)
            post_entity_ms = int((time.perf_counter() - t_entity) * 1000)
            # 146 P2: write entity_list multi-repr
            _write_entity_multi_repr(db, f)
        if abort_check:
            abort_check()
        from messaging.mq_progress_notify import maybe_publish_post_progress

        maybe_publish_post_progress(
            user_id=int(f.user_id),
            file_id=int(f.id),
            progress_stage="SAG",
            progress_pct=None,
            force=True,
        )
        from services.kb_sag_event_extract_service import rebuild_sag_events_for_file

        t_sag = time.perf_counter()
        with collect_kb_post_llm_telemetry(llm_calls):
            rebuild_sag_events_for_file(db, f)
        post_sag_ms = int((time.perf_counter() - t_sag) * 1000)
        # 146 P2: write event_summary multi-repr
        _write_event_multi_repr(db, f)

    if abort_check:
        abort_check()
    from services.kb_raptor_service import maybe_build_raptor_tree

    t_raptor = time.perf_counter()
    with collect_kb_post_llm_telemetry(llm_calls):
        maybe_build_raptor_tree(
            db,
            f,
            md_char_count=md_char_count,
            source=source,
            fts_config=fts_config,
            job=job,
            abort_check=abort_check,
            force_settings=bool(getattr(job, "force_raptor_settings", False)),
            emit_mq_progress=True,
        )
    post_raptor_ms = int((time.perf_counter() - t_raptor) * 1000)
    if abort_check:
        abort_check()

    _write_section_multi_repr(db, f)
    # 146 P2: write raptor_summary multi-repr
    _write_raptor_multi_repr(db, f)

    return {
        "post_entity_ms": post_entity_ms,
        "post_sag_ms": post_sag_ms,
        "post_raptor_ms": post_raptor_ms,
        "post_skip_reason": post_skip_reason,
        "post_index_ms": post_entity_ms + post_sag_ms + post_raptor_ms,
        **format_kb_post_llm_telemetry(llm_calls),
    }


def maybe_enqueue_post_job(
    db: Session,
    f: FileModel,
    index_job: KbIndexJob,
    *,
    md_char_count: int,
    large_pdf: bool,
    pipeline_fingerprint: str,
) -> int | None:
    from services.system_setting_service import is_kb_post_async_enabled

    if not is_kb_post_async_enabled(db):
        return None

    needed, skip_reason, raptor_needed = _post_work_needed(
        db, md_char_count=md_char_count, large_pdf=large_pdf
    )
    if not needed:
        f.kb_post_status = POST_STATUS_SKIPPED
        f.kb_post_error = None
        stub = KbPostJob(
            user_id=f.user_id,
            file_id=f.id,
            index_job_id=index_job.id,
            status=JOB_DONE,
            force=bool(index_job.force),
            pipeline_fingerprint=pipeline_fingerprint,
            post_skip_reason=skip_reason,
        )
        db.add(stub)
        db.flush()
        _log_post_pipeline(db, stub, ACTION_KB_POST_SKIP, reason=skip_reason or "post_not_needed")
        return None

    post_job = KbPostJob(
        user_id=f.user_id,
        file_id=f.id,
        index_job_id=index_job.id,
        status=JOB_QUEUED,
        force=bool(index_job.force),
        pipeline_fingerprint=pipeline_fingerprint,
    )
    db.add(post_job)
    f.kb_post_status = POST_STATUS_QUEUED
    f.kb_post_error = None
    db.flush()
    if raptor_needed:
        from services.gpu_scheduler_persistence import enqueue_gpu_route

        enqueue_gpu_route(
            db,
            job_kind="raptor",
            job_id=post_job.id,
            file_id=f.id,
            idempotency_key=f"raptor:{post_job.id}:0",
            payload={
                "job_id": int(post_job.id),
                "job_kind": "raptor",
                "file_id": int(f.id),
                "attempt": 0,
                "idempotency_key": f"raptor:{post_job.id}:0",
                "handover_epoch": 0,
            },
        )
    return int(post_job.id)


def run_sync_post_in_index(
    db: Session,
    f: FileModel,
    index_job: KbIndexJob,
    *,
    md_char_count: int,
    source: str,
    fts_config: str,
    large_pdf: bool,
    pipeline_fingerprint: str | None = None,
) -> None:
    """Sync tail fallback when kb_post_async_enabled=false (M5)."""
    needed, skip_reason, raptor_needed = _post_work_needed(
        db, md_char_count=md_char_count, large_pdf=large_pdf
    )
    if not needed:
        f.kb_post_status = POST_STATUS_SKIPPED
        f.kb_post_error = None
        stub = KbPostJob(
            user_id=f.user_id,
            file_id=f.id,
            index_job_id=index_job.id,
            status=JOB_DONE,
            force=bool(index_job.force),
            post_skip_reason=skip_reason,
        )
        db.add(stub)
        db.flush()
        _log_post_pipeline(db, stub, ACTION_KB_POST_SKIP, reason=skip_reason or "post_not_needed")
        return

    if GPU_SCHEDULER_ENABLED and raptor_needed:
        # 164 §6：sync RAPTOR 直接执行会绕过 gpu_scheduler_leases；改为创建
        # queued post job + durable route，交由 scheduler 取得租约后执行。
        post_job = KbPostJob(
            user_id=f.user_id,
            file_id=f.id,
            index_job_id=index_job.id,
            status=JOB_QUEUED,
            force=bool(index_job.force),
            pipeline_fingerprint=pipeline_fingerprint,
        )
        db.add(post_job)
        f.kb_post_status = POST_STATUS_QUEUED
        f.kb_post_error = None
        db.flush()
        from services.gpu_scheduler_persistence import enqueue_gpu_route

        enqueue_gpu_route(
            db,
            job_kind="raptor",
            job_id=post_job.id,
            file_id=f.id,
            idempotency_key=f"raptor:{post_job.id}:0",
            payload={
                "job_id": int(post_job.id),
                "job_kind": "raptor",
                "file_id": int(f.id),
                "attempt": 0,
                "idempotency_key": f"raptor:{post_job.id}:0",
                "handover_epoch": 0,
            },
        )
        logger.info(
            "kb_post sync post handed over to gpu scheduler file_id=%s index_job_id=%s",
            f.id,
            index_job.id,
        )
        return

    f.kb_post_status = POST_STATUS_RUNNING
    stub = KbPostJob(
        user_id=f.user_id,
        file_id=f.id,
        index_job_id=index_job.id,
        status=JOB_RUNNING,
        force=bool(index_job.force),
    )
    db.add(stub)
    db.flush()
    _log_post_pipeline(db, stub, ACTION_KB_POST_START, force=bool(index_job.force))
    fields = _execute_post_phases(
        db,
        f,
        index_job,
        md_char_count=md_char_count,
        source=source,
        fts_config=fts_config,
        large_pdf=large_pdf,
        abort_check=None,
    )
    raptor_warn = (index_job.last_error or "").strip()
    stub.status = JOB_DONE
    stub.post_entity_ms = int(fields["post_entity_ms"])  # type: ignore[arg-type]
    stub.post_sag_ms = int(fields["post_sag_ms"])  # type: ignore[arg-type]
    stub.post_raptor_ms = int(fields["post_raptor_ms"])  # type: ignore[arg-type]
    if fields.get("post_skip_reason"):
        stub.post_skip_reason = str(fields["post_skip_reason"])
    f.kb_post_status = POST_STATUS_READY
    f.kb_post_at = naive_db_now()
    f.kb_post_error = raptor_warn[:2000] if raptor_warn else None
    _log_post_pipeline(db, stub, ACTION_KB_POST_DONE, **fields)
    logger.info(
        "kb_post sync_done file_id=%s index_job_id=%s post_index_ms=%s",
        f.id,
        index_job.id,
        fields.get("post_index_ms"),
    )


def publish_post_job(db: Session, user_id: int, file_id: int, job_id: int) -> None:
    from messaging.kb_post_publisher import publish_kb_post_job, publish_file_post_notify

    try:
        from services.gpu_scheduler_persistence import find_gpu_route, publish_gpu_route

        route = find_gpu_route(db, job_kind="raptor", job_id=job_id)
        if route is None:
            publish_kb_post_job(job_id)
        elif GPU_SCHEDULER_ENABLED:
            # 164 §6：GPU 调度模式下发布入口只入队；route 保持 queued，由
            # scheduler 取得租约后统一发布 filex.gpu.*，旧 worker 不执行 GPU。
            db.commit()
        else:
            publish_gpu_route(
                db,
                outbox_id=route.id,
                publish=lambda payload: publish_kb_post_job(int(payload["job_id"])),
            )
            db.commit()
    except Exception:
        logger.exception("publish kb post job failed job_id=%s", job_id)
    f = db.query(FileModel).filter(FileModel.id == file_id, FileModel.user_id == user_id).first()
    if f:
        try:
            publish_file_post_notify(f)
        except Exception:
            logger.exception("publish kb post notify failed file_id=%s", file_id)
        try:
            from messaging.mq_status_watcher import request_refresh

            request_refresh()
        except Exception:
            pass


def _execute_raptor_only_post(
    db: Session,
    f: FileModel,
    job: KbPostJob | KbIndexJob,
    *,
    md_char_count: int,
    source: str,
    fts_config: str,
    abort_check: Callable[[], None] | None = None,
) -> dict[str, object]:
    from services.kb_post_llm_service import (
        collect_kb_post_llm_telemetry,
        format_kb_post_llm_telemetry,
    )
    from services.kb_raptor_service import maybe_build_raptor_tree

    if abort_check:
        abort_check()
    t_raptor = time.perf_counter()
    with collect_kb_post_llm_telemetry() as llm_calls:
        maybe_build_raptor_tree(
            db,
            f,
            md_char_count=md_char_count,
            source=source,
            fts_config=fts_config,
            job=job,
            abort_check=abort_check,
            force_settings=bool(getattr(job, "force_raptor_settings", False)),
            emit_mq_progress=True,
        )
    post_raptor_ms = int((time.perf_counter() - t_raptor) * 1000)
    if abort_check:
        abort_check()
    return {
        "post_entity_ms": 0,
        "post_sag_ms": 0,
        "post_raptor_ms": post_raptor_ms,
        "post_skip_reason": None,
        "post_index_ms": post_raptor_ms,
        **format_kb_post_llm_telemetry(llm_calls),
    }


def run_sync_force_raptor(db: Session, user: User, f: FileModel) -> tuple[int, str]:
    """Sync force RAPTOR when kb_post_async_enabled=false (118 FR-118-007)."""
    from services.kb_force_raptor_service import _log_force_raptor

    if GPU_SCHEDULER_ENABLED:
        raise RuntimeError(
            "GPU_SCHEDULER_ENABLED=true 时禁止同步执行 RAPTOR；"
            "请使用 force raptor 异步路径（scheduler 执行）"
        )

    effective = get_user_effective_dict(db, f.user_id)
    text, source = resolve_index_text(f)
    if not text or not source:
        raise ValueError("no indexable text")
    md_char_count = len(text)
    fts_config = get_effective_fts_config(db, effective=effective)

    f.kb_post_status = POST_STATUS_RUNNING
    stub = KbPostJob(
        user_id=f.user_id,
        file_id=f.id,
        status=JOB_RUNNING,
        raptor_only=True,
        force_raptor_settings=True,
    )
    db.add(stub)
    db.flush()
    _log_force_raptor(db, user.id, f.id, ACTION_KB_FORCE_RAPTOR_START, job_id=stub.id, async_mode=False)
    try:
        publish_file_post_notify_safe(f)
    except Exception:
        pass

    try:
        fields = _execute_raptor_only_post(
            db,
            f,
            stub,
            md_char_count=md_char_count,
            source=source,
            fts_config=fts_config,
            abort_check=None,
        )
        raptor_warn = (stub.last_error or "").strip()
        stub.status = JOB_DONE
        stub.post_entity_ms = 0
        stub.post_sag_ms = 0
        stub.post_raptor_ms = int(fields["post_raptor_ms"])  # type: ignore[arg-type]
        stub.last_error = raptor_warn[:2000] if raptor_warn else None
        f.kb_post_status = POST_STATUS_READY
        f.kb_post_at = naive_db_now()
        f.kb_post_error = raptor_warn[:2000] if raptor_warn else None
        _log_force_raptor(
            db,
            user.id,
            f.id,
            ACTION_KB_FORCE_RAPTOR_DONE,
            job_id=stub.id,
            **fields,
        )
    except Exception as exc:
        logger.exception("sync force raptor failed file_id=%s", f.id)
        stub.status = JOB_ERROR
        stub.last_error = str(exc)[:2000]
        f.kb_post_status = POST_STATUS_FAILED
        f.kb_post_error = str(exc)[:2000]
        _log_force_raptor(
            db,
            user.id,
            f.id,
            ACTION_KB_FORCE_RAPTOR_WARN,
            job_id=stub.id,
            reason=str(exc)[:200],
        )
        try:
            publish_file_post_notify_safe(f)
        except Exception:
            pass
        return int(stub.id), POST_STATUS_FAILED

    try:
        publish_file_post_notify_safe(
            f,
            post_raptor_ms=int(fields["post_raptor_ms"]),  # type: ignore[arg-type]
        )
    except Exception:
        pass
    return int(stub.id), f.kb_post_status or POST_STATUS_READY


def _run_raptor_only_post_job(
    db: Session,
    job: KbPostJob,
    f: FileModel,
    *,
    effective: dict[str, str] | None = None,
) -> None:
    from services.kb_force_raptor_service import _log_force_raptor

    claimed = _ensure_post_job_claimed(db, job)
    if claimed is None:
        logger.warning("kb_post_raptor_only_job_not_claimed job_id=%s status=%s", job.id, job.status)
        return
    job = claimed
    expected_worker_id = job.worker_id
    expected_lease_generation = job.lease_generation
    job.attempts = (job.attempts or 0) + 1
    f.kb_post_status = POST_STATUS_RUNNING
    f.kb_post_error = None
    db.flush()
    db.commit()
    _log_force_raptor(
        db,
        job.user_id,
        f.id,
        ACTION_KB_FORCE_RAPTOR_START,
        job_id=job.id,
        async_mode=True,
    )
    try:
        publish_file_post_notify_safe(f)
    except Exception:
        pass

    text, source = resolve_index_text(f)
    if not text or not source:
        _cooperative_post_abort_check(
            db,
            job,
            worker_id=expected_worker_id,
            lease_generation=expected_lease_generation,
        )
        job.status = JOB_DONE
        f.kb_post_status = POST_STATUS_SKIPPED
        _log_force_raptor(db, job.user_id, f.id, ACTION_KB_FORCE_RAPTOR_SKIP, job_id=job.id, reason="no_text")
        return

    if effective is None:
        effective = get_user_effective_dict(db, f.user_id)
    md_char_count = len(text)
    fts_config = get_effective_fts_config(db, effective=effective)

    def _abort() -> None:
        _cooperative_post_abort_check(
            db,
            job,
            worker_id=expected_worker_id,
            lease_generation=expected_lease_generation,
        )

    try:
        fields = _execute_raptor_only_post(
            db,
            f,
            job,
            md_char_count=md_char_count,
            source=source,
            fts_config=fts_config,
            abort_check=_abort,
        )
        db.refresh(job)
        if job.status != JOB_RUNNING or not _post_lease_matches(
            job,
            worker_id=expected_worker_id,
            lease_generation=expected_lease_generation,
        ):
            raise KbPostJobAborted(job.last_error or "post job not running")
        raptor_warn = (job.last_error or "").strip()
        job.status = JOB_DONE
        job.post_entity_ms = 0
        job.post_sag_ms = 0
        job.post_raptor_ms = int(fields["post_raptor_ms"])  # type: ignore[arg-type]
        job.last_error = raptor_warn[:2000] if raptor_warn else None
        f.kb_post_status = POST_STATUS_READY
        f.kb_post_at = naive_db_now()
        f.kb_post_error = raptor_warn[:2000] if raptor_warn else None
        _log_force_raptor(
            db,
            job.user_id,
            f.id,
            ACTION_KB_FORCE_RAPTOR_DONE,
            job_id=job.id,
            **fields,
        )
    except KbPostJobAborted:
        logger.info("kb_post raptor_only aborted job_id=%s file_id=%s", job.id, job.file_id)
        db.rollback()
        raise
    except GpuOomError as exc:
        db.refresh(job)
        if job.status != JOB_RUNNING or not _post_lease_matches(
            job,
            worker_id=expected_worker_id,
            lease_generation=expected_lease_generation,
        ):
            logger.info("kb_post skip GPU oom state after lease lost job_id=%s", job.id)
            return
        msg = f"{exc.reason_code}: {exc}"[:2000]
        f.kb_post_status = POST_STATUS_FAILED
        f.kb_post_error = msg
        job.status = JOB_ERROR
        job.last_error = msg
        job.oom_retry_count = (job.oom_retry_count or 0) + 1
        if (job.oom_retry_count or 0) > GpuOomError.max_controlled_retries:
            # spec §8：OOM 最多一次受控重试；第二次 OOM 直接到 failed/DLQ。
            job.attempts = get_kb_post_max_attempts(db)
        _log_post_pipeline(db, job, ACTION_KB_POST_ERROR, reason=pipeline_reason(msg))
        logger.error("kb post job gpu oom job_id=%s file_id=%s oom_retry=%s error=%s",
                     job.id, f.id, job.oom_retry_count, msg[:500])
    except GpuWaitingError as exc:
        db.refresh(job)
        if job.status != JOB_RUNNING or not _post_lease_matches(
            job,
            worker_id=expected_worker_id,
            lease_generation=expected_lease_generation,
        ):
            logger.info("kb_post skip GPU waiting state after lease lost job_id=%s", job.id)
            return
        msg = f"{exc.reason_code}: {exc}"[:2000]
        f.kb_post_status = POST_STATUS_WAITING_GPU
        f.kb_post_error = msg
        job.status = JOB_WAITING_GPU
        job.last_error = msg
        _log_post_pipeline(db, job, ACTION_KB_RAPTOR_WARN, reason=msg)
        logger.warning("kb post job waiting for GPU job_id=%s file_id=%s reason=%s", job.id, f.id, msg)
    except Exception as exc:
        logger.exception("raptor_only post job %s failed", job.id)
        db.refresh(job)
        if job.status != JOB_RUNNING or not _post_lease_matches(
            job,
            worker_id=expected_worker_id,
            lease_generation=expected_lease_generation,
        ):
            logger.info("kb_post raptor_only skip terminal error after lease lost job_id=%s", job.id)
            return
        f.kb_post_status = POST_STATUS_FAILED
        f.kb_post_error = str(exc)[:2000]
        job.status = JOB_ERROR
        job.last_error = str(exc)[:2000]
        _log_force_raptor(
            db,
            job.user_id,
            f.id,
            ACTION_KB_FORCE_RAPTOR_WARN,
            job_id=job.id,
            reason=str(exc)[:200],
        )


def run_post_job(
    db: Session,
    job: KbPostJob,
    *,
    effective: dict[str, str] | None = None,
    _from_gpu_scheduler: bool = False,
) -> None:
    from services.system_setting_service import is_kb_post_async_enabled

    # 164 §6：GPU 调度模式把 sync/force RAPTOR 转给 scheduler 执行时，
    # scheduler 本身就是异步执行者，不受 kb_post_async_enabled 门禁约束。
    if not is_kb_post_async_enabled(db) and not _from_gpu_scheduler:
        job.status = JOB_ERROR
        job.last_error = "async_disabled"
        f = db.query(FileModel).filter(FileModel.id == job.file_id).first()
        if f:
            f.kb_post_status = POST_STATUS_SKIPPED
        return

    f = db.query(FileModel).filter(FileModel.id == job.file_id, FileModel.user_id == job.user_id).first()
    if not f:
        job.attempts = (job.attempts or 0) + 1
        job.status = JOB_ERROR
        job.last_error = "file not found"
        return

    if getattr(job, "raptor_only", False):
        _run_raptor_only_post_job(db, job, f, effective=effective)
        return

    claimed = _ensure_post_job_claimed(db, job)
    if claimed is None:
        logger.warning("kb_post_job_not_claimed job_id=%s status=%s", job.id, job.status)
        return
    job = claimed
    expected_worker_id = job.worker_id
    expected_lease_generation = job.lease_generation
    job.attempts = (job.attempts or 0) + 1
    f.kb_post_status = POST_STATUS_RUNNING
    f.kb_post_error = None
    db.flush()
    db.commit()
    _log_post_pipeline(db, job, ACTION_KB_POST_START, force=bool(job.force))
    try:
        publish_file_post_notify_safe(f)
    except Exception:
        pass

    text, source = resolve_index_text(f)
    if not text or not source:
        _cooperative_post_abort_check(
            db,
            job,
            worker_id=expected_worker_id,
            lease_generation=expected_lease_generation,
        )
        job.status = JOB_DONE
        f.kb_post_status = POST_STATUS_SKIPPED
        _log_post_pipeline(db, job, ACTION_KB_POST_SKIP, reason="no_text")
        return

    if effective is None:
        effective = get_user_effective_dict(db, f.user_id)
    md_char_count = len(text)
    from services.system_setting_service import get_kb_large_doc_settings

    large = get_kb_large_doc_settings(db)
    large_pdf = md_char_count > large["char_threshold"]
    fts_config = get_effective_fts_config(db, effective=effective)

    def _abort() -> None:
        _cooperative_post_abort_check(
            db,
            job,
            worker_id=expected_worker_id,
            lease_generation=expected_lease_generation,
        )

    try:
        fields = _execute_post_phases(
            db,
            f,
            job,
            md_char_count=md_char_count,
            source=source,
            fts_config=fts_config,
            large_pdf=large_pdf,
            abort_check=_abort,
        )
        db.refresh(job)
        if job.status != JOB_RUNNING or not _post_lease_matches(
            job,
            worker_id=expected_worker_id,
            lease_generation=expected_lease_generation,
        ):
            raise KbPostJobAborted(job.last_error or "post job not running")
        raptor_warn = (job.last_error or "").strip()
        job.status = JOB_DONE
        job.post_entity_ms = int(fields["post_entity_ms"])  # type: ignore[arg-type]
        job.post_sag_ms = int(fields["post_sag_ms"])  # type: ignore[arg-type]
        job.post_raptor_ms = int(fields["post_raptor_ms"])  # type: ignore[arg-type]
        if fields.get("post_skip_reason"):
            job.post_skip_reason = str(fields["post_skip_reason"])
        job.last_error = raptor_warn[:2000] if raptor_warn else None
        f.kb_post_status = POST_STATUS_READY
        f.kb_post_at = naive_db_now()
        f.kb_post_error = raptor_warn[:2000] if raptor_warn else None
        _log_post_pipeline(db, job, ACTION_KB_POST_DONE, **fields)
    except KbPostJobAborted:
        logger.info("kb_post job aborted job_id=%s file_id=%s", job.id, job.file_id)
        db.rollback()
        raise
    except GpuOomError as exc:
        db.refresh(job)
        if job.status != JOB_RUNNING or not _post_lease_matches(
            job,
            worker_id=expected_worker_id,
            lease_generation=expected_lease_generation,
        ):
            logger.info("kb_post skip GPU oom state after lease lost job_id=%s", job.id)
            return
        msg = f"{exc.reason_code}: {exc}"[:2000]
        f.kb_post_status = POST_STATUS_FAILED
        f.kb_post_error = msg
        job.status = JOB_ERROR
        job.last_error = msg
        job.oom_retry_count = (job.oom_retry_count or 0) + 1
        if (job.oom_retry_count or 0) > GpuOomError.max_controlled_retries:
            job.attempts = get_kb_post_max_attempts(db)
        _log_post_pipeline(db, job, ACTION_KB_POST_ERROR, reason=pipeline_reason(msg))
        logger.error("kb post job gpu oom job_id=%s file_id=%s oom_retry=%s error=%s",
                     job.id, f.id, job.oom_retry_count, msg[:500])
    except GpuWaitingError as exc:
        db.refresh(job)
        if job.status != JOB_RUNNING or not _post_lease_matches(
            job,
            worker_id=expected_worker_id,
            lease_generation=expected_lease_generation,
        ):
            logger.info("kb_post skip GPU waiting state after lease lost job_id=%s", job.id)
            return
        msg = f"{exc.reason_code}: {exc}"[:2000]
        f.kb_post_status = POST_STATUS_WAITING_GPU
        f.kb_post_error = msg
        job.status = JOB_WAITING_GPU
        job.last_error = msg
        _log_post_pipeline(db, job, ACTION_KB_RAPTOR_WARN, reason=msg)
        logger.warning("kb post job waiting for GPU job_id=%s file_id=%s reason=%s", job.id, f.id, msg)
    except Exception as exc:
        logger.exception("post job %s failed", job.id)
        db.refresh(job)
        if job.status != JOB_RUNNING or not _post_lease_matches(
            job,
            worker_id=expected_worker_id,
            lease_generation=expected_lease_generation,
        ):
            logger.info("kb_post skip terminal error after lease lost job_id=%s", job.id)
            return
        f.kb_post_status = POST_STATUS_FAILED
        f.kb_post_error = str(exc)[:2000]
        job.status = JOB_ERROR
        job.last_error = str(exc)[:2000]
        _log_post_pipeline(db, job, ACTION_KB_POST_ERROR, reason=pipeline_reason(str(exc)))


def publish_file_post_notify_safe(
    f: FileModel,
    *,
    processing_duration_ms: int | None = None,
    post_entity_ms: int | None = None,
    post_sag_ms: int | None = None,
    post_raptor_ms: int | None = None,
    post_skip_reason: str | None = None,
) -> None:
    from messaging.kb_post_publisher import publish_file_post_notify

    publish_file_post_notify(
        f,
        processing_duration_ms=processing_duration_ms,
        post_entity_ms=post_entity_ms,
        post_sag_ms=post_sag_ms,
        post_raptor_ms=post_raptor_ms,
        post_skip_reason=post_skip_reason,
    )


def replay_queued_post_jobs(db: Session, *, full: bool = False) -> int:
    from messaging.kb_post_publisher import publish_kb_post_job

    q = db.query(KbPostJob).filter(KbPostJob.status.in_((JOB_QUEUED, JOB_WAITING_GPU)))
    if not full:
        cutoff = naive_db_now() - timedelta(seconds=KB_POST_REPLAY_STALE_SEC)
        q = q.filter(KbPostJob.updated_at <= cutoff)
    jobs = q.order_by(KbPostJob.id).all()
    if not jobs:
        return 0
    if GPU_SCHEDULER_ENABLED:
        # 164 §6：与 extract 侧对齐，跳过已有 durable raptor route 的 job，
        # 避免旧拓扑 replay 与调度发布竞态。
        from models.gpu_scheduler import GpuSchedulerOutbox
        from services.gpu_scheduler_persistence import (
            OUTBOX_EXECUTING,
            OUTBOX_PUBLISHED,
            OUTBOX_QUEUED,
        )

        route_job_ids = {
            str(row[0])
            for row in db.query(GpuSchedulerOutbox.job_id).filter(
                GpuSchedulerOutbox.job_kind == "raptor",
                GpuSchedulerOutbox.state.in_(
                    (OUTBOX_QUEUED, OUTBOX_PUBLISHED, OUTBOX_EXECUTING)
                ),
            )
        }
        jobs = [job for job in jobs if str(job.id) not in route_job_ids]
        if not jobs:
            return 0
    conn = open_blocking_connection()
    now = naive_db_now()
    try:
        for job in jobs:
            publish_kb_post_job(job.id, connection=conn)
            job.updated_at = now
    finally:
        conn.close()
    db.commit()
    logger.info("replayed %s queued kb post job(s) (full=%s)", len(jobs), full)
    return len(jobs)


def abort_kb_post_jobs_for_file_delete(db: Session, file_id: int) -> list[int]:
    """删除文件前标记 queued/running 后处理任务为 error。"""
    jobs = (
        db.query(KbPostJob)
        .filter(
            KbPostJob.file_id == file_id,
            KbPostJob.status.in_((JOB_QUEUED, JOB_RUNNING)),
        )
        .all()
    )
    cancelled_ids: list[int] = []
    for job in jobs:
        job.status = JOB_ERROR
        job.last_error = "cancelled: file deleted"
        cancelled_ids.append(int(job.id))
    return cancelled_ids


def purge_kb_post_mq_for_jobs(job_ids: list[int]) -> None:
    if not job_ids:
        return
    from messaging.kb_post_queues import QUEUE_DLQ, QUEUE_MAIN, QUEUE_RETRY
    from services.rabbitmq_queue_admin_service import mutate_queue_messages_by_job_ids

    for queue_name in (QUEUE_MAIN, QUEUE_RETRY, QUEUE_DLQ):
        try:
            mutate_queue_messages_by_job_ids(queue_name, job_ids={int(job_id) for job_id in job_ids})
        except Exception:
            logger.warning("abort post mq purge failed queue=%s job_ids=%s", queue_name, job_ids, exc_info=True)


def open_blocking_connection():
    from messaging.kb_post_queues import open_blocking_connection as _open

    return _open()


def _post_job_is_stale(
    db: Session,
    job: KbPostJob,
    *,
    now: datetime,
    stale_seconds: float,
) -> tuple[bool, bool]:
    """running post job 是否可判定为中断；返回 ``(is_stale, watchdog_recorded)``。

    GPU 调度模式下 lease heartbeat 是权威 liveness：调度循环存活时每 tick
    续期，scheduler 崩溃/停滞后台心跳停止。但 liveness 丢失 ≠ 回收授权：
    执行中的 lease 必须先由 watchdog 确认旧执行轮已退出（release_ack 或连续
    两次间隔 5 秒的确认；RAPTOR 轮次与 scheduler 进程共存亡，MinerU 轮次以
    sidecar /lifecycle/status 为准）才可重排队，否则 loop 线程停滞或双
    worker 场景下会把仍在执行的 job 误判为中断并并发重跑（164 §5.5，与
    extract 侧对称）。无 lease 的 CPU job 退回 job heartbeat/updated_at 阈值
    门控。
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
        if not gpu_round_idle(job_kind="raptor", lease=lease):
            # 旧执行轮仍存活（或探测失败）：不得确认，job 保持 running，
            # 等待后续采样。
            return False, False
        with db.begin_nested():
            confirmed = record_watchdog_empty_confirmation(db, lease, now=now)
        return confirmed, True
    cutoff = now - timedelta(seconds=stale_seconds)
    heartbeat_at = job.heartbeat_at or job.updated_at
    return (heartbeat_at is not None and heartbeat_at <= cutoff), False


def reconcile_stale_kb_post_jobs(db: Session) -> dict[str, int]:
    from services.system_setting_service import is_kb_post_async_enabled

    if not is_kb_post_async_enabled(db):
        skipped = 0
        now = naive_db_now()
        for job in db.query(KbPostJob).filter(KbPostJob.status == JOB_QUEUED).all():
            if GPU_SCHEDULER_ENABLED and _post_job_has_durable_gpu_route(db, job.id):
                # 164 §6：GPU 调度模式下，raptor route 由 scheduler 在租约下
                # 执行（run_post_job 对 _from_gpu_scheduler=True 绕过
                # async_disabled 门禁）；旧 post consumer 的周期性 reconcile
                # 不得把它当作 async_disabled 跳过。
                continue
            job.status = JOB_DONE
            job.post_skip_reason = "async_disabled"
            job.updated_at = now
            f = db.query(FileModel).filter(FileModel.id == job.file_id).first()
            if f is not None:
                f.kb_post_status = POST_STATUS_SKIPPED
                f.kb_post_error = None
                try:
                    publish_file_post_notify_safe(f)
                except Exception:
                    logger.exception("publish kb post notify after async_disabled skip file_id=%s", f.id)
            skipped += 1
        return {"queued_skipped_async_disabled": skipped}

    now = naive_db_now()
    closed_done = 0
    closed_error = 0
    requeued = 0
    watchdog_recorded = False
    for job in db.query(KbPostJob).filter(KbPostJob.status == JOB_RUNNING).all():
        stale, recorded = _post_job_is_stale(
            db,
            job,
            now=now,
            stale_seconds=KB_POST_RUNNING_STALE_SEC,
        )
        watchdog_recorded = watchdog_recorded or recorded
        if not stale:
            continue
        f = db.query(FileModel).filter(FileModel.id == job.file_id).first()
        fingerprint_mismatch = (
            f is not None
            and bool(job.pipeline_fingerprint)
            and bool(f.index_pipeline_fingerprint)
            and job.pipeline_fingerprint != f.index_pipeline_fingerprint
            and not bool(job.force)
            and not bool(job.raptor_only)
        )
        if fingerprint_mismatch:
            msg = "stale running post fingerprint mismatch; manual retry required"
            old_worker_id = job.worker_id
            job.status = JOB_ERROR
            job.last_error = msg[:2000]
            job.updated_at = now
            job.worker_id = None
            job.claimed_at = None
            job.heartbeat_at = now
            job.lease_generation = (job.lease_generation or 0) + 1
            closed_error += 1
            if f:
                f.kb_post_status = POST_STATUS_FAILED
                f.kb_post_error = msg[:2000]
            _log_post_pipeline(
                db,
                job,
                ACTION_KB_POST_RECOVER,
                reason="fingerprint_mismatch",
                worker_id=old_worker_id,
                lease_generation=job.lease_generation,
            )
            # 164 §6：job 终态后 route 无需再执行，ack 并释放 dispatch lease。
            from services.gpu_scheduler_persistence import ack_gpu_route_for_terminal

            ack_gpu_route_for_terminal(db, job_kind="raptor", job_id=job.id)
            logger.warning(
                "reconciled stale kb post job_id=%s file_id=%s -> error fingerprint_mismatch",
                job.id,
                job.file_id,
            )
            continue
        old_worker_id = requeue_stale_running_post_job(db, job, now=now)
        requeued += 1
        _log_post_pipeline(
            db,
            job,
            ACTION_KB_POST_RECOVER,
            reason="stale_running_requeued",
            worker_id=old_worker_id,
            lease_generation=job.lease_generation,
        )
        logger.warning(
            "reconciled stale kb post job_id=%s file_id=%s -> queued",
            job.id,
            job.file_id,
        )
    if watchdog_recorded:
        db.commit()
    return {
        "running_closed_error": closed_error,
        "running_closed_done": closed_done,
        "running_requeued": requeued,
    }


def requeue_stale_running_post_job(
    db: Session,
    job: KbPostJob,
    *,
    now,
    recover_route: bool = True,
) -> str | None:
    """把中断的 running post job 恢复为 queued，并同一事务内恢复 GPU route/lease。

    返回旧 worker_id 供调用方记录流水与告警。GPU 调度模式下 consumer 崩溃后
    route 停在 executing、lease 仍 active，必须把 route 退回 queued 并释放
    lease，调度循环才能重新取得租约并发布（164 §6）。调用方若自行恢复
    route/lease（如调度循环按 owner 恢复），可传 ``recover_route=False``。
    """
    old_worker_id = job.worker_id
    job.status = JOB_QUEUED
    job.last_error = STALE_RUNNING_REQUEUED_MSG
    job.updated_at = now
    job.claimed_at = None
    job.worker_id = None
    job.heartbeat_at = now
    job.lease_generation = (job.lease_generation or 0) + 1
    f = db.query(FileModel).filter(FileModel.id == job.file_id).first()
    if f:
        f.kb_post_status = POST_STATUS_QUEUED
        f.kb_post_error = None
    if recover_route:
        from services.gpu_scheduler_persistence import recover_gpu_route_for_requeue

        recover_gpu_route_for_requeue(db, job_kind="raptor", job_id=job.id)
    return old_worker_id


def _post_job_has_durable_gpu_route(db: Session, job_id: int) -> bool:
    """该 post job 是否仍存在待 scheduler 执行的 raptor durable route。"""
    from models.gpu_scheduler import GpuSchedulerOutbox
    from services.gpu_scheduler_persistence import (
        OUTBOX_EXECUTING,
        OUTBOX_PUBLISHED,
        OUTBOX_QUEUED,
    )

    return (
        db.query(GpuSchedulerOutbox.id)
        .filter(
            GpuSchedulerOutbox.job_kind == "raptor",
            GpuSchedulerOutbox.job_id == str(job_id),
            GpuSchedulerOutbox.state.in_((OUTBOX_QUEUED, OUTBOX_PUBLISHED, OUTBOX_EXECUTING)),
        )
        .first()
        is not None
    )
