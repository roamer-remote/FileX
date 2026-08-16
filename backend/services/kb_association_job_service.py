# Copyright (c) 2026 徐泽宇
"""Durable enqueue/recovery primitives for association extraction."""

from sqlalchemy.orm import Session
from sqlalchemy.exc import IntegrityError

from models.file import File as FileModel
from models.kb_association_job import KbAssociationJob
from models.kb_association_reconcile import KbAssociationReconcileCheckpoint
from services.kb_association_version import association_source_fingerprint
from database import SessionLocal
import logging

logger = logging.getLogger(__name__)
ASSOCIATION_HEARTBEAT_SEC = 20
ASSOCIATION_STALE_SEC = 300
ASSOCIATION_MAX_ATTEMPTS = 3
ASSOCIATION_RECOVERY_BATCH = 50
ASSOCIATION_RECONCILE_BATCH = 100
CANCELLED_FILE_DELETED_MSG = "file deleted"
from utils.timezone import naive_db_now
from datetime import timedelta
import threading


def enqueue_association_job(db: Session, file: FileModel) -> KbAssociationJob | None:
    if file.workspace_id is None:
        return None
    fingerprint = association_source_fingerprint(file)
    generation = int(file.md_content_rev or 0)
    existing = (
        db.query(KbAssociationJob)
        .filter(
            KbAssociationJob.file_id == file.id,
            KbAssociationJob.generation == generation,
            KbAssociationJob.source_fingerprint == fingerprint,
        )
        .order_by(KbAssociationJob.id.desc())
        .first()
    )
    if existing and existing.status != "cancelled":
        return existing
    job = KbAssociationJob(user_id=file.user_id, file_id=file.id, workspace_id=file.workspace_id,
                           source_fingerprint=fingerprint, generation=generation, status="queued")
    # Savepoint: failure to enqueue must not poison the caller's indexing transaction.
    try:
        with db.begin_nested():
            db.add(job)
            db.flush()
    except IntegrityError:
        # Another indexing transaction may have won the unique insert race.
        # The savepoint keeps the caller's transaction usable; return the
        # durable winner instead of surfacing a duplicate enqueue failure.
        return (
            db.query(KbAssociationJob)
            .filter(
                KbAssociationJob.file_id == file.id,
                KbAssociationJob.generation == generation,
                KbAssociationJob.source_fingerprint == fingerprint,
            )
            .order_by(KbAssociationJob.id.desc())
            .first()
        )
    return job


def reconcile_association_jobs(
    db: Session,
    *,
    workspace_id: int | None = None,
    batch_size: int = ASSOCIATION_RECONCILE_BATCH,
    after_id: int = 0,
) -> int:
    """Ensure current workspace files have a durable association job.

    This is deliberately bounded and restart-safe: each invocation advances by
    file id and only requeues failed/superseded rows for the current generation.
    """
    query = db.query(FileModel).filter(
        FileModel.workspace_id.isnot(None), FileModel.id > max(0, int(after_id))
    ).order_by(FileModel.id)
    if workspace_id is not None:
        query = query.filter(FileModel.workspace_id == workspace_id)
    files = query.limit(max(1, min(int(batch_size), ASSOCIATION_RECONCILE_BATCH))).all()
    repaired = 0
    for file in files:
        fingerprint = association_source_fingerprint(file)
        generation = int(file.md_content_rev or 0)
        current = db.query(KbAssociationJob).filter(
            KbAssociationJob.file_id == file.id,
            KbAssociationJob.generation == generation,
            KbAssociationJob.source_fingerprint == fingerprint,
        ).order_by(KbAssociationJob.id.desc()).first()
        if current is None:
            if enqueue_association_job(db, file) is not None:
                repaired += 1
        elif current.status in {"failed", "superseded"} and int(current.attempts or 0) < ASSOCIATION_MAX_ATTEMPTS:
            current.status = "queued"
            current.last_error = None
            current.worker_id = None
            current.heartbeat_at = None
            repaired += 1
    if repaired:
        db.commit()
    return repaired


def reset_association_job(
    db: Session,
    *,
    file_id: int,
    workspace_id: int | None = None,
) -> bool:
    """Explicit operator action to retry a terminal poison job."""
    query = db.query(KbAssociationJob).filter(KbAssociationJob.file_id == file_id)
    if workspace_id is not None:
        query = query.filter(KbAssociationJob.workspace_id == workspace_id)
    job = query.order_by(KbAssociationJob.id.desc()).first()
    if job is None or job.status not in {"failed", "superseded"}:
        return False
    job.status = "queued"
    job.attempts = 0
    job.last_error = None
    job.worker_id = None
    job.heartbeat_at = None
    db.commit()
    return True


def abort_kb_association_jobs_for_file_delete(db: Session, file_id: int) -> list[int]:
    """删除文件前标记 queued/running 关联作业为 cancelled。"""
    jobs = (
        db.query(KbAssociationJob)
        .filter(
            KbAssociationJob.file_id == file_id,
            KbAssociationJob.status.in_(("queued", "running")),
        )
        .all()
    )
    cancelled_ids: list[int] = []
    for job in jobs:
        job.status = "cancelled"
        job.last_error = CANCELLED_FILE_DELETED_MSG
        cancelled_ids.append(int(job.id))
    return cancelled_ids

def reconcile_association_file(db: Session, *, file: FileModel) -> dict[str, object]:
    """Explicit, generation-safe repair for one authorized file."""
    fingerprint = association_source_fingerprint(file)
    generation = int(file.md_content_rev or 0)
    current = db.query(KbAssociationJob).filter(
        KbAssociationJob.file_id == file.id,
        KbAssociationJob.generation == generation,
        KbAssociationJob.source_fingerprint == fingerprint,
    ).order_by(KbAssociationJob.id.desc()).first()
    if current is None:
        job = enqueue_association_job(db, file)
        db.commit()
        return {"created": job is not None, "reset": False, "job_id": int(job.id) if job else None}
    if current.status in {"failed", "superseded"}:
        current.status = "queued"
        current.attempts = 0
        current.last_error = None
        current.worker_id = None
        current.heartbeat_at = None
        db.commit()
        return {"created": False, "reset": True, "job_id": int(current.id)}
    return {"created": False, "reset": False, "job_id": int(current.id)}


def reconcile_workspace_page(
    db: Session,
    *,
    workspace_id: int,
    batch_size: int = ASSOCIATION_RECONCILE_BATCH,
) -> dict[str, int | bool | str]:
    """Process and persist one workspace page; safe to resume after a crash."""
    checkpoint = db.query(KbAssociationReconcileCheckpoint).filter_by(workspace_id=workspace_id).first()
    if checkpoint is None:
        checkpoint = KbAssociationReconcileCheckpoint(workspace_id=workspace_id, cursor=0, status="running")
        db.add(checkpoint)
        db.flush()
    elif checkpoint.status == "complete":
        checkpoint.cursor = 0
        checkpoint.scan_round = int(checkpoint.scan_round or 0) + 1
        checkpoint.status = "running"
        db.flush()
    cursor = int(checkpoint.cursor or 0)
    ids = [
        int(file_id)
        for (file_id,) in db.query(FileModel.id)
        .filter(FileModel.workspace_id == workspace_id, FileModel.id > cursor)
        .order_by(FileModel.id)
        .limit(max(1, min(int(batch_size), ASSOCIATION_RECONCILE_BATCH)) + 1)
        .all()
    ]
    page_ids = ids[: max(1, min(int(batch_size), ASSOCIATION_RECONCILE_BATCH))]
    if not page_ids:
        checkpoint.status = "complete"
        db.commit()
        return {"repaired": 0, "cursor": cursor, "next_cursor": cursor, "has_more": False, "status": "complete", "scan_round": int(checkpoint.scan_round)}
    repaired = reconcile_association_jobs(
        db, workspace_id=workspace_id, batch_size=len(page_ids), after_id=cursor
    )
    checkpoint.cursor = page_ids[-1]
    checkpoint.status = "running" if len(ids) > len(page_ids) else "complete"
    checkpoint.last_error = None
    db.commit()
    return {
        "repaired": repaired,
        "cursor": cursor,
        "next_cursor": int(checkpoint.cursor),
        "has_more": len(ids) > len(page_ids),
        "status": checkpoint.status,
        "scan_round": int(checkpoint.scan_round),
    }


def claim_association_job(db: Session, *, worker_id: str) -> KbAssociationJob | None:
    recovered = recover_stale_association_jobs(db)
    # Recovery is its own durable transaction. This is essential when the only
    # stale rows are poison jobs and no queued row exists to claim afterward.
    if recovered:
        db.commit()
    job = (
        db.query(KbAssociationJob)
        .filter(KbAssociationJob.status == "queued")
        .order_by(KbAssociationJob.id)
        .with_for_update(skip_locked=True)
        .first()
    )
    if job is None:
        return None
    job.status = "running"
    job.worker_id = worker_id
    job.attempts = int(job.attempts or 0) + 1
    job.lease_generation = int(job.lease_generation or 0) + 1
    job.heartbeat_at = naive_db_now()
    db.flush()
    return job


def recover_stale_association_jobs(db: Session, *, timeout_seconds: int = ASSOCIATION_STALE_SEC) -> int:
    cutoff = naive_db_now() - timedelta(seconds=timeout_seconds)
    rows = db.query(KbAssociationJob).filter(
        KbAssociationJob.status == "running",
        KbAssociationJob.heartbeat_at < cutoff,
    ).order_by(KbAssociationJob.id).with_for_update(skip_locked=True).limit(ASSOCIATION_RECOVERY_BATCH).all()
    for row in rows:
        row.status = "failed" if int(row.attempts or 0) >= ASSOCIATION_MAX_ATTEMPTS else "queued"
        row.worker_id = None
        row.last_error = "stale association lease recovered"
        row.lease_generation = int(row.lease_generation or 0) + 1
    if rows:
        db.flush()
    return len(rows)


def run_one_association_job(db: Session, *, worker_id: str, max_attempts: int = ASSOCIATION_MAX_ATTEMPTS) -> bool:
    job = claim_association_job(db, worker_id=worker_id)
    if job is None:
        return False
    job_id = int(job.id)
    attempts = int(job.attempts or 0)
    lease_generation = int(job.lease_generation or 0)
    db.commit()  # persist lease/attempt before any rebuild SQL can fail
    file = db.query(FileModel).filter(FileModel.id == job.file_id).first()
    try:
        if file is None:
            raise RuntimeError("file not found")
        current_fingerprint = association_source_fingerprint(file)
        current_generation = int(file.md_content_rev or 0)
        if (
            file.workspace_id != job.workspace_id
            or current_generation != int(job.generation or 0)
            or current_fingerprint != job.source_fingerprint
        ):
            db.query(KbAssociationJob).filter(
                KbAssociationJob.id == job_id,
                KbAssociationJob.status == "running",
                KbAssociationJob.worker_id == worker_id,
                KbAssociationJob.lease_generation == lease_generation,
            ).update({
                "status": "superseded",
                "last_error": "file changed while association job was queued",
                "updated_at": naive_db_now(),
            })
            db.commit()
            return True
        from services.kb_association_extract_service import rebuild_association_facts_for_file

        stop_heartbeat = threading.Event()
        def _heartbeat() -> None:
            while not stop_heartbeat.wait(ASSOCIATION_HEARTBEAT_SEC):
                heartbeat_db = SessionLocal()
                try:
                    heartbeat_db.query(KbAssociationJob).filter(
                        KbAssociationJob.id == job_id,
                        KbAssociationJob.status == "running",
                        KbAssociationJob.worker_id == worker_id,
                        KbAssociationJob.lease_generation == lease_generation,
                    ).update({"heartbeat_at": naive_db_now(), "updated_at": naive_db_now()})
                    heartbeat_db.commit()
                except Exception:
                    heartbeat_db.rollback()
                    logger.exception("association heartbeat failed job_id=%s", job_id)
                finally:
                    heartbeat_db.close()
        heartbeat_thread = threading.Thread(target=_heartbeat, daemon=True)
        heartbeat_thread.start()
        try:
            rebuild_association_facts_for_file(db, file)
        finally:
            stop_heartbeat.set()
            heartbeat_thread.join(timeout=2)
        updated = db.query(KbAssociationJob).filter(
            KbAssociationJob.id == job_id,
            KbAssociationJob.status == "running",
            KbAssociationJob.worker_id == worker_id,
            KbAssociationJob.lease_generation == lease_generation,
        ).update({"status": "done", "last_error": None, "updated_at": naive_db_now()})
        if updated != 1:
            db.rollback()
            return True
        db.commit()
    except Exception as exc:
        db.rollback()
        recovery = SessionLocal()
        try:
            durable = recovery.query(KbAssociationJob).filter(KbAssociationJob.id == job_id).first()
            if durable is not None and durable.status == "running" and int(durable.lease_generation or 0) == lease_generation:
                durable.last_error = str(exc)[:2000]
                durable.status = "queued" if attempts < max_attempts else "failed"
                durable.updated_at = naive_db_now()
                recovery.commit()
        finally:
            recovery.close()
    return True
