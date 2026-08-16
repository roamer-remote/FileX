"""State and idempotency rules for 187-P2 correction overlays."""

from __future__ import annotations

import hashlib
from datetime import datetime, timezone

from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from models.kb_correction_overlay import KbCorrectionOverlay
from models.file import File
from models.kb_index_job import KbIndexJob
from models.user import User
from services.log_service import log_operation


_TRANSITIONS = {"DRAFT": {"ACTIVE"}, "ACTIVE": {"REVOKED"}, "REVOKED": set()}

# Shared-workspace read access does not grant authority to mutate source
# corrections. Overlay writes stay owner/admin-only until a separate
# collaboration-write contract defines role, audit, and conflict semantics.


def _content_hash(content: str) -> str:
    return hashlib.sha256(content.encode("utf-8")).hexdigest()


def create_correction_overlay(
    db: Session,
    *,
    file_id: int,
    source_hash: str,
    overlay_version: int,
    actor_id: int,
    workspace_id: int,
    content: str,
    reason: str,
    idempotency_key: str,
    parent_version: int | None = None,
) -> KbCorrectionOverlay:
    source_file = db.get(File, file_id)
    if source_file is None:
        raise ValueError("source file not found")
    actor = db.get(User, actor_id)
    if actor is None or (source_file.user_id != actor_id and not actor.is_admin):
        raise ValueError("overlay write requires file owner or admin")
    expected_source_hash = source_file.source_sha256 or source_file.index_source_hash
    if expected_source_hash and expected_source_hash != source_hash:
        raise ValueError("source hash does not match original file")

    existing = db.query(KbCorrectionOverlay).filter_by(idempotency_key=idempotency_key).one_or_none()
    if existing is not None:
        requested = (file_id, source_hash, overlay_version, actor_id, workspace_id, content, reason)
        actual = (
            existing.source_file_id,
            existing.source_hash,
            existing.overlay_version,
            existing.actor_id,
            existing.workspace_id,
            existing.content,
            existing.reason,
        )
        if requested != actual:
            raise ValueError("idempotency key already used for a different overlay")
        return existing

    overlay = KbCorrectionOverlay(
        source_file_id=file_id,
        source_hash=source_hash,
        overlay_version=overlay_version,
        actor_id=actor_id,
        workspace_id=workspace_id,
        content=content,
        content_hash=_content_hash(content),
        reason=reason,
        parent_version=parent_version,
        idempotency_key=idempotency_key,
        state="DRAFT",
    )
    db.add(overlay)
    try:
        db.flush()
        log_operation(
            db,
            actor_id,
            "kb_correction_overlay_create",
            "kb_correction_overlay",
            overlay.id,
            f"file_id={file_id} source_hash={source_hash} overlay_version={overlay_version}",
            commit=False,
        )
        db.commit()
    except IntegrityError:
        db.rollback()
        duplicate = db.query(KbCorrectionOverlay).filter_by(idempotency_key=idempotency_key).one_or_none()
        if duplicate is not None:
            return duplicate
        raise
    db.refresh(overlay)
    return overlay


def _check_overlay_actor(db: Session, overlay: KbCorrectionOverlay, actor_id: int | None) -> int:
    effective_actor_id = overlay.actor_id if actor_id is None else actor_id
    actor = db.get(User, effective_actor_id)
    source_file = db.get(File, overlay.source_file_id)
    if actor is None or source_file is None:
        raise ValueError("overlay actor or source file not found")
    if source_file.user_id != effective_actor_id and not actor.is_admin:
        raise ValueError("overlay write requires file owner or admin")
    return effective_actor_id


def transition_correction_overlay(
    db: Session,
    overlay_id: int,
    target_state: str,
    *,
    actor_id: int | None = None,
) -> KbCorrectionOverlay:
    overlay = db.get(KbCorrectionOverlay, overlay_id)
    if overlay is None:
        raise ValueError("correction overlay not found")
    effective_actor_id = _check_overlay_actor(db, overlay, actor_id)
    target_state = target_state.upper()
    if target_state not in _TRANSITIONS.get(overlay.state, set()):
        raise ValueError(f"invalid correction overlay transition: {overlay.state} -> {target_state}")
    if target_state == "REVOKED" and overlay.reindex_status in {"QUEUED", "RUNNING"}:
        if overlay.reindex_job_id:
            job = db.get(KbIndexJob, overlay.reindex_job_id)
            if job is not None and job.status in {"queued", "running"}:
                job.status = "cancelled"
                job.last_error = "overlay revoked"
        overlay.reindex_status = "CANCELLED"
    overlay.state = target_state
    now = datetime.now(timezone.utc).replace(tzinfo=None)
    if target_state == "ACTIVE":
        overlay.activated_at = now
    elif target_state == "REVOKED":
        overlay.revoked_at = now
    log_operation(
        db,
        effective_actor_id,
        "kb_correction_overlay_state_change",
        "kb_correction_overlay",
        overlay.id,
        f"state={target_state}",
        commit=False,
    )
    db.commit()
    db.refresh(overlay)
    return overlay


def queue_correction_overlay_reindex(
    db: Session,
    overlay_id: int,
    *,
    strategy_version: str,
    strategy_id: str | None = None,
    actor_id: int | None = None,
) -> KbIndexJob:
    """Create one queued index job for an active overlay/strategy pair."""
    overlay = db.get(KbCorrectionOverlay, overlay_id)
    if overlay is None:
        raise ValueError("correction overlay not found")
    effective_actor_id = _check_overlay_actor(db, overlay, actor_id)
    if overlay.state != "ACTIVE":
        raise ValueError("only an active correction overlay can be reindexed")
    from services.kb_chunk_strategy import resolve_chunk_strategy

    resolved_strategy_id: str | None = strategy_id
    if strategy_id is not None:
        resolved_strategy_id, strategy_version = resolve_chunk_strategy(strategy_id, strategy_version)
    else:
        try:
            resolved_strategy_id, strategy_version = resolve_chunk_strategy(None, strategy_version)
        except ValueError:
            # Preserve the pre-T2 request contract for old callers while making
            # all newly explicit strategies version-validated.
            resolved_strategy_id = None
    if resolved_strategy_id is None:
        request_key = f"overlay:{overlay.id}:{strategy_version}"
    else:
        request_key = (
            f"overlay:{overlay.source_file_id}:{overlay.source_hash}:"
            f"{overlay.overlay_version}:{resolved_strategy_id}:{strategy_version}"
        )
    existing = db.query(KbIndexJob).filter(KbIndexJob.request_key == request_key).one_or_none()
    if existing is not None:
        return existing
    source_file = db.get(File, overlay.source_file_id)
    if source_file is None:
        raise ValueError("source file not found")
    job = KbIndexJob(
        user_id=source_file.user_id,
        file_id=overlay.source_file_id,
        status="queued",
        force=True,
        correction_overlay_id=overlay.id,
        request_key=request_key,
        strategy_id=resolved_strategy_id,
        strategy_version=strategy_version,
    )
    db.add(job)
    try:
        db.flush()
        overlay.reindex_job_id = job.id
        overlay.reindex_status = "QUEUED"
        log_operation(
            db,
            effective_actor_id,
            "kb_correction_overlay_reindex_queued",
            "kb_correction_overlay",
            overlay.id,
            f"job_id={job.id} request_key={request_key}",
            commit=False,
        )
        db.commit()
        db.refresh(job)
        return job
    except IntegrityError:
        db.rollback()
        duplicate = db.query(KbIndexJob).filter(KbIndexJob.request_key == request_key).one_or_none()
        if duplicate is not None:
            return duplicate
        raise


def complete_correction_overlay_reindex(
    db: Session,
    overlay_id: int,
    *,
    success: bool,
    error: str | None = None,
) -> KbCorrectionOverlay:
    """Record a terminal reindex outcome without deleting the prior index on failure."""
    overlay = db.get(KbCorrectionOverlay, overlay_id)
    if overlay is None:
        raise ValueError("correction overlay not found")
    if overlay.reindex_job_id is None:
        raise ValueError("correction overlay has no reindex job")
    job = db.get(KbIndexJob, overlay.reindex_job_id)
    if job is None:
        raise ValueError("correction overlay reindex job not found")
    if success:
        job.status = "done"
        job.last_error = None
        overlay.reindex_status = "SUCCEEDED"
    else:
        job.status = "error"
        job.last_error = error or "correction overlay reindex failed"
        overlay.reindex_status = "FAILED"
    log_operation(
        db,
        overlay.actor_id,
        "kb_correction_overlay_reindex_terminal",
        "kb_correction_overlay",
        overlay.id,
        f"job_id={job.id} status={overlay.reindex_status}",
        commit=False,
    )
    db.commit()
    db.refresh(overlay)
    return overlay
