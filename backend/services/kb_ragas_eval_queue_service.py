# Copyright (c) 2026 徐泽宇
"""Durable PostgreSQL queue primitives for RAGAS online evaluation.

The caller owns the transaction.  In particular, ``create_ragas_eval_job``
and ``claim_next_ragas_eval_job`` flush their changes but never commit them.
"""

from __future__ import annotations

import hashlib
import math
import re
from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Any, Literal

from sqlalchemy import func, text
from sqlalchemy.orm import Session

from models.kb_ragas_eval_job import KbRagasEvalJob
from models.kb_search_eval import KbSearchEval

RAGAS_EVAL_QUEUE_LOCK_KEY = 900142
CONTEXT_BUDGET_VERSION = "v1"
DEFAULT_CONTEXT_MAX_COUNT = 8
DEFAULT_CONTEXT_MAX_CHARS_PER_ITEM = 1200
DEFAULT_CONTEXT_MAX_TOTAL_CHARS = 10000
DEFAULT_TOTAL_BUDGET_SECONDS = 300.0
MAX_TOTAL_BUDGET_SECONDS = 300.0
LEASE_WRITEBACK_GRACE_SECONDS = 60.0
MAX_PREVIEW_CHARS = 512

JOB_PENDING = "pending"
JOB_RUNNING = "running"
JOB_SUCCEEDED = "succeeded"
JOB_FAILED = "failed"
JOB_SKIPPED = "skipped"
TERMINAL_STATUSES = {JOB_SUCCEEDED, JOB_FAILED, JOB_SKIPPED}

FailureStage = Literal["queue", "faithfulness", "context_precision", "writeback"]


@dataclass(frozen=True, slots=True)
class RagasEvalContext:
    """One retrieval context with provenance kept in a single structure."""

    text: str
    file_id: int | None
    chunk_id: int | None
    rank: int


def _valid_positive_int(value: Any, default: int, warning: str, warnings: list[str]) -> int:
    if isinstance(value, bool):
        warnings.append(warning)
        return default
    try:
        parsed = int(value)
    except (TypeError, ValueError):
        warnings.append(warning)
        return default
    if parsed <= 0:
        warnings.append(warning)
        return default
    return parsed


def _valid_total_budget(value: Any, warnings: list[str]) -> float:
    try:
        parsed = float(value)
    except (TypeError, ValueError):
        parsed = math.nan
    if not math.isfinite(parsed) or parsed <= 0:
        warnings.append("invalid_total_budget_seconds")
        return DEFAULT_TOTAL_BUDGET_SECONDS
    return min(parsed, MAX_TOTAL_BUDGET_SECONDS)


_WHITESPACE_RE = re.compile(r"\s+")


def _dedupe_key(value: str) -> str:
    return _WHITESPACE_RE.sub(" ", value.strip())


def build_ragas_eval_payload(
    contexts: list[RagasEvalContext],
    *,
    query: str,
    answer: str,
    sample_type: str,
    max_count: int = DEFAULT_CONTEXT_MAX_COUNT,
    max_chars_per_item: int = DEFAULT_CONTEXT_MAX_CHARS_PER_ITEM,
    max_total_chars: int = DEFAULT_CONTEXT_MAX_TOTAL_CHARS,
    total_budget_seconds: float = DEFAULT_TOTAL_BUDGET_SECONDS,
) -> dict[str, Any]:
    """Apply deterministic v1 selection/budgeting and return the worker payload."""

    warnings: list[str] = []
    effective_max_count = _valid_positive_int(
        max_count, DEFAULT_CONTEXT_MAX_COUNT, "invalid_max_count", warnings
    )
    effective_max_chars = _valid_positive_int(
        max_chars_per_item,
        DEFAULT_CONTEXT_MAX_CHARS_PER_ITEM,
        "invalid_max_chars_per_item",
        warnings,
    )
    effective_max_total = _valid_positive_int(
        max_total_chars,
        DEFAULT_CONTEXT_MAX_TOTAL_CHARS,
        "invalid_max_total_chars",
        warnings,
    )
    effective_total_budget = _valid_total_budget(total_budget_seconds, warnings)

    # Rank is authoritative; input position is a deterministic tie-breaker.
    ordered = sorted(enumerate(contexts), key=lambda item: (item[1].rank, item[0]))
    unique: list[RagasEvalContext] = []
    seen_text: set[str] = set()
    for _, context in ordered:
        clean_text = (context.text or "").strip()
        key = _dedupe_key(clean_text)
        if not key or key in seen_text:
            continue
        seen_text.add(key)
        unique.append(
            RagasEvalContext(
                text=clean_text,
                file_id=context.file_id,
                chunk_id=context.chunk_id,
                rank=context.rank,
            )
        )

    # Phase 1: first item from each known file.  Phase 2: every remaining item
    # in retrieval order, including provenance-less contexts.
    first_per_file: list[RagasEvalContext] = []
    first_ids: set[int] = set()
    first_object_ids: set[int] = set()
    for context in unique:
        if context.file_id is None or context.file_id in first_ids:
            continue
        first_ids.add(context.file_id)
        first_per_file.append(context)
        first_object_ids.add(id(context))
    candidates = first_per_file + [
        context for context in unique if id(context) not in first_object_ids
    ]

    selected: list[dict[str, Any]] = []
    remaining_chars = effective_max_total
    for context in candidates:
        if len(selected) >= effective_max_count or remaining_chars <= 0:
            break
        text_value = context.text[: min(effective_max_chars, remaining_chars)]
        if not text_value:
            continue
        selected.append(
            {
                "text": text_value,
                "file_id": context.file_id,
                "chunk_id": context.chunk_id,
                "rank": context.rank,
            }
        )
        remaining_chars -= len(text_value)

    selected_chars = sum(len(item["text"]) for item in selected)
    return {
        "query": query,
        "answer": answer,
        "sample_type": sample_type,
        "contexts": selected,
        "context_budget": {
            "version": CONTEXT_BUDGET_VERSION,
            "source_context_count": len(contexts),
            "selected_context_count": len(selected),
            "selected_context_chars": selected_chars,
            "max_count": effective_max_count,
            "max_chars_per_item": effective_max_chars,
            "max_total_chars": effective_max_total,
            "warnings": warnings,
        },
        "total_budget_seconds": effective_total_budget,
    }


def _hash(value: str) -> str:
    return hashlib.sha256((value or "").encode("utf-8")).hexdigest()


def _preview(value: str) -> str:
    return (value or "").strip()[:MAX_PREVIEW_CHARS]


def create_ragas_eval_job(
    db: Session,
    *,
    user_id: int,
    workspace_id: int | None,
    query: str,
    answer: str,
    contexts: list[RagasEvalContext],
    agent_run_id: str | None = None,
    search_trace_id: str | None = None,
    sample_type: str = "answer",
    max_count: int = DEFAULT_CONTEXT_MAX_COUNT,
    max_chars_per_item: int = DEFAULT_CONTEXT_MAX_CHARS_PER_ITEM,
    max_total_chars: int = DEFAULT_CONTEXT_MAX_TOTAL_CHARS,
    total_budget_seconds: float = DEFAULT_TOTAL_BUDGET_SECONDS,
) -> tuple[KbSearchEval, KbRagasEvalJob]:
    """Create the public eval row and durable job in the caller's transaction."""

    payload = build_ragas_eval_payload(
        contexts,
        query=query,
        answer=answer,
        sample_type=sample_type,
        max_count=max_count,
        max_chars_per_item=max_chars_per_item,
        max_total_chars=max_total_chars,
        total_budget_seconds=total_budget_seconds,
    )
    budget = payload["context_budget"]
    file_ids = list(
        dict.fromkeys(
            int(context["file_id"])
            for context in payload["contexts"]
            if context["file_id"] is not None
        )
    )
    chunk_ids = list(
        dict.fromkeys(
            int(context["chunk_id"])
            for context in payload["contexts"]
            if context["chunk_id"] is not None
        )
    )
    eval_row = KbSearchEval(
        user_id=user_id,
        workspace_id=workspace_id,
        agent_run_id=agent_run_id,
        search_trace_id=search_trace_id,
        sample_type=sample_type,
        query_hash=_hash(query),
        query_preview=_preview(query),
        answer_hash=_hash(answer),
        answer_preview=_preview(answer),
        context_count=int(budget["selected_context_count"]),
        context_file_ids_json=file_ids,
        context_chunk_ids_json=chunk_ids,
        status=JOB_PENDING,
        context_budget_version=CONTEXT_BUDGET_VERSION,
        source_context_count=int(budget["source_context_count"]),
        selected_context_count=int(budget["selected_context_count"]),
        selected_context_chars=int(budget["selected_context_chars"]),
    )
    db.add(eval_row)
    db.flush()
    job = KbRagasEvalJob(
        eval_id=eval_row.id,
        status=JOB_PENDING,
        payload_json=payload,
    )
    db.add(job)
    db.flush()
    return eval_row, job


def database_now(db: Session) -> datetime:
    """Return PostgreSQL wall-clock time as a naive DB datetime.

    ``now()`` is fixed at transaction start, which would make a long-running
    metric appear to have consumed no budget.  ``clock_timestamp()`` keeps the
    deadline helper correct even when a worker reuses one transaction.
    """

    return db.execute(
        text("SELECT CAST(clock_timestamp() AS timestamp without time zone)")
    ).scalar_one()


def _job_total_budget_seconds(job: KbRagasEvalJob) -> float:
    payload = job.payload_json if isinstance(job.payload_json, dict) else {}
    return _valid_total_budget(payload.get("total_budget_seconds"), [])


def _duration_ms(start: datetime | None, end: datetime) -> int | None:
    if start is None:
        return None
    return max(0, int((end - start).total_seconds() * 1000))


def claim_next_ragas_eval_job(
    db: Session,
    *,
    worker_id: str,
    concurrency: int,
) -> KbRagasEvalJob | None:
    """Claim one pending job under the global PostgreSQL concurrency gate."""

    if concurrency < 1:
        raise ValueError("concurrency must be at least 1")
    db.execute(
        text("SELECT pg_advisory_xact_lock(:lock_key)"),
        {"lock_key": RAGAS_EVAL_QUEUE_LOCK_KEY},
    )
    now = database_now(db)
    active_count = (
        db.query(func.count(KbRagasEvalJob.id))
        .filter(
            KbRagasEvalJob.status == JOB_RUNNING,
            text("lease_expires_at > CAST(clock_timestamp() AS timestamp without time zone)"),
        )
        .scalar()
        or 0
    )
    if int(active_count) >= int(concurrency):
        return None

    job = (
        db.query(KbRagasEvalJob)
        .filter(KbRagasEvalJob.status == JOB_PENDING)
        .order_by(KbRagasEvalJob.queued_at.asc(), KbRagasEvalJob.id.asc())
        .with_for_update(skip_locked=True)
        .first()
    )
    if job is None:
        return None

    deadline = now + timedelta(seconds=_job_total_budget_seconds(job))
    job.status = JOB_RUNNING
    job.worker_id = worker_id
    job.lease_generation = int(job.lease_generation or 0) + 1
    job.started_at = now
    job.heartbeat_at = now
    job.evaluation_deadline_at = deadline
    job.lease_expires_at = deadline + timedelta(seconds=LEASE_WRITEBACK_GRACE_SECONDS)
    job.finished_at = None
    job.failure_stage = None
    job.error_code = None
    job.error_message = None

    eval_row = db.get(KbSearchEval, job.eval_id)
    if eval_row is not None:
        eval_row.status = JOB_RUNNING
        eval_row.queue_duration_ms = _duration_ms(job.queued_at, now)
        eval_row.failure_stage = None
        eval_row.error_code = None
        eval_row.error_message = None
    db.flush()
    return job


def heartbeat_ragas_eval_job(
    db: Session,
    *,
    job_id: int,
    worker_id: str,
    lease_generation: int,
) -> bool:
    """Refresh heartbeat only; the fixed deadline and lease never move."""

    now = database_now(db)
    updated = (
        db.query(KbRagasEvalJob)
        .filter(
            KbRagasEvalJob.id == job_id,
            KbRagasEvalJob.status == JOB_RUNNING,
            KbRagasEvalJob.worker_id == worker_id,
            KbRagasEvalJob.lease_generation == lease_generation,
            text("lease_expires_at > CAST(clock_timestamp() AS timestamp without time zone)"),
        )
        .update({KbRagasEvalJob.heartbeat_at: now}, synchronize_session=False)
    )
    db.flush()
    return updated == 1


def start_ragas_eval_attempt(
    db: Session,
    *,
    job_id: int,
    worker_id: str,
    lease_generation: int,
) -> bool:
    """Fence and record the transition from claimed to model execution."""

    now = database_now(db)
    updated = (
        db.query(KbRagasEvalJob)
        .filter(
            KbRagasEvalJob.id == job_id,
            KbRagasEvalJob.status == JOB_RUNNING,
            KbRagasEvalJob.worker_id == worker_id,
            KbRagasEvalJob.lease_generation == lease_generation,
            text("lease_expires_at > CAST(clock_timestamp() AS timestamp without time zone)"),
            KbRagasEvalJob.attempt_count == 0,
        )
        .update(
            {
                KbRagasEvalJob.attempt_count: KbRagasEvalJob.attempt_count + 1,
                KbRagasEvalJob.heartbeat_at: now,
            },
            synchronize_session=False,
        )
    )
    db.flush()
    return updated == 1


def remaining_ragas_eval_seconds(db: Session, job: KbRagasEvalJob) -> float:
    """Return remaining execution budget using the same DB clock as claim."""

    if job.evaluation_deadline_at is None:
        return 0.0
    return max(0.0, (job.evaluation_deadline_at - database_now(db)).total_seconds())


def effective_ragas_metric_timeout(
    db: Session,
    job: KbRagasEvalJob,
    llm_timeout_seconds: float,
) -> float:
    """Bound an HTTP/async timeout by the job's immutable total deadline."""

    if llm_timeout_seconds <= 0:
        return 0.0
    return min(float(llm_timeout_seconds), remaining_ragas_eval_seconds(db, job))


def finish_ragas_eval_job(
    db: Session,
    *,
    job_id: int,
    worker_id: str,
    lease_generation: int,
    status: str,
    error_code: str | None = None,
    error_message: str | None = None,
    failure_stage: FailureStage | None = None,
    faithfulness_score: float | None = None,
    context_precision_score: float | None = None,
    faithfulness_duration_ms: int | None = None,
    context_precision_duration_ms: int | None = None,
    llm_provider: str | None = None,
    llm_model: str | None = None,
    metric_version: str | None = None,
    metric_variant: str | None = None,
) -> bool:
    """Atomically write a terminal job/eval state when the lease still matches."""

    if status not in TERMINAL_STATUSES:
        raise ValueError(f"invalid terminal status: {status}")
    job = (
        db.query(KbRagasEvalJob)
        .filter(
            KbRagasEvalJob.id == job_id,
            KbRagasEvalJob.status == JOB_RUNNING,
            KbRagasEvalJob.worker_id == worker_id,
            KbRagasEvalJob.lease_generation == lease_generation,
            text("lease_expires_at > CAST(clock_timestamp() AS timestamp without time zone)"),
        )
        .with_for_update()
        .first()
    )
    if job is None:
        return False
    now = database_now(db)
    job.status = status
    job.payload_json = {}
    job.finished_at = now
    job.heartbeat_at = now
    job.failure_stage = failure_stage
    job.error_code = error_code
    job.error_message = (error_message or "")[:2000] or None

    eval_row = db.get(KbSearchEval, job.eval_id)
    if eval_row is not None:
        eval_row.status = status
        eval_row.error_code = error_code
        eval_row.error_message = (error_message or "")[:2000] or None
        eval_row.failure_stage = failure_stage
        eval_row.faithfulness_score = faithfulness_score
        eval_row.context_precision_score = context_precision_score
        eval_row.faithfulness_duration_ms = faithfulness_duration_ms
        eval_row.context_precision_duration_ms = context_precision_duration_ms
        eval_row.llm_provider = llm_provider
        eval_row.llm_model = llm_model
        # A terminal durable job must remain interpretable even when it was
        # skipped before the RAGAS package could be imported.
        eval_row.metric_version = metric_version or "ragas-queued-v1"
        eval_row.metric_variant = (
            metric_variant or "faithfulness+context_precision_without_reference"
        )
        eval_row.duration_ms = _duration_ms(job.started_at, now)
        eval_row.evaluated_at = now
    db.flush()
    return True


def reconcile_stale_ragas_eval_jobs(db: Session) -> dict[str, int]:
    """Recover expired leases and close legacy running eval rows without jobs."""

    now = database_now(db)
    stats = {"requeued": 0, "failed": 0, "legacy_failed": 0}
    expired = (
        db.query(KbRagasEvalJob)
        .filter(
            KbRagasEvalJob.status == JOB_RUNNING,
            KbRagasEvalJob.lease_expires_at < now,
        )
        .order_by(KbRagasEvalJob.id.asc())
        .with_for_update(skip_locked=True)
        .all()
    )
    for job in expired:
        eval_row = db.get(KbSearchEval, job.eval_id)
        can_requeue = int(job.attempt_count or 0) == 0 and (
            eval_row is None or eval_row.error_code != "TimeoutError"
        )
        job.lease_generation = int(job.lease_generation or 0) + 1
        job.worker_id = None
        job.heartbeat_at = None
        job.evaluation_deadline_at = None
        job.lease_expires_at = None
        if can_requeue:
            job.status = JOB_PENDING
            job.started_at = None
            job.failure_stage = None
            job.error_code = None
            job.error_message = None
            if eval_row is not None:
                eval_row.status = JOB_PENDING
                eval_row.failure_stage = None
                eval_row.error_code = None
                eval_row.error_message = None
            stats["requeued"] += 1
            continue

        job.status = JOB_FAILED
        job.payload_json = {}
        job.finished_at = now
        job.failure_stage = "queue"
        job.error_code = "worker_lease_expired"
        job.error_message = "RAGAS evaluation worker lease expired"
        if eval_row is not None:
            eval_row.status = JOB_FAILED
            eval_row.failure_stage = "queue"
            eval_row.error_code = "worker_lease_expired"
            eval_row.error_message = "RAGAS evaluation worker lease expired"
            eval_row.duration_ms = _duration_ms(job.started_at, now)
            eval_row.evaluated_at = now
        stats["failed"] += 1

    legacy_rows = (
        db.query(KbSearchEval)
        .outerjoin(KbRagasEvalJob, KbRagasEvalJob.eval_id == KbSearchEval.id)
        .filter(KbSearchEval.status == JOB_RUNNING, KbRagasEvalJob.id.is_(None))
        .with_for_update(of=KbSearchEval, skip_locked=True)
        .all()
    )
    for eval_row in legacy_rows:
        eval_row.status = JOB_FAILED
        eval_row.failure_stage = "queue"
        eval_row.error_code = "legacy_running_orphan"
        eval_row.error_message = "legacy running RAGAS evaluation has no durable job"
        eval_row.evaluated_at = now
        stats["legacy_failed"] += 1

    db.flush()
    return stats
