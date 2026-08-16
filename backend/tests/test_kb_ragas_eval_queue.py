# Copyright (c) 2026 徐泽宇
"""Persistent RAGAS evaluation queue tests (feature 142)."""

from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
from datetime import timedelta
import threading
import time
import uuid

from sqlalchemy import text
from sqlalchemy.orm import sessionmaker

from models.kb_ragas_eval_job import KbRagasEvalJob
from models.kb_search_eval import KbSearchEval
from models.enterprise_rbac import Department
from models.user import User
from services.kb_ragas_eval_queue_service import (
    RagasEvalContext,
    build_ragas_eval_payload,
    claim_next_ragas_eval_job,
    create_ragas_eval_job,
    effective_ragas_metric_timeout,
    finish_ragas_eval_job,
    heartbeat_ragas_eval_job,
    reconcile_stale_ragas_eval_jobs,
    start_ragas_eval_attempt,
)


def _contexts() -> list[RagasEvalContext]:
    return [
        RagasEvalContext(text=" file 1 first ", file_id=1, chunk_id=11, rank=3),
        RagasEvalContext(text="file 1 second", file_id=1, chunk_id=12, rank=4),
        RagasEvalContext(text="file 2 first long", file_id=2, chunk_id=21, rank=1),
        RagasEvalContext(text="missing file", file_id=None, chunk_id=31, rank=2),
        RagasEvalContext(text="file   2 first long", file_id=9, chunk_id=99, rank=5),
        RagasEvalContext(text="   ", file_id=3, chunk_id=32, rank=6),
    ]


def test_build_payload_is_deterministic_file_first_and_budgeted():
    payload = build_ragas_eval_payload(
        _contexts(),
        query="q",
        answer="a",
        sample_type="answer",
        max_count=3,
        max_chars_per_item=10,
        max_total_chars=24,
        total_budget_seconds=60,
    )

    assert payload["contexts"] == [
        {"text": "file 2 fir", "file_id": 2, "chunk_id": 21, "rank": 1},
        {"text": "file 1 fir", "file_id": 1, "chunk_id": 11, "rank": 3},
        {"text": "miss", "file_id": None, "chunk_id": 31, "rank": 2},
    ]
    assert payload["context_budget"] == {
        "version": "v1",
        "source_context_count": 6,
        "selected_context_count": 3,
        "selected_context_chars": 24,
        "max_count": 3,
        "max_chars_per_item": 10,
        "max_total_chars": 24,
        "warnings": [],
    }
    assert payload["total_budget_seconds"] == 60.0


def test_build_payload_uses_defaults_and_warning_for_invalid_budget():
    payload = build_ragas_eval_payload(
        [RagasEvalContext(text="x" * 2000, file_id=None, chunk_id=None, rank=0)],
        query="q",
        answer="a",
        sample_type="answer",
        max_count=0,
        max_chars_per_item=-1,
        max_total_chars=0,
        total_budget_seconds=-5,
    )

    budget = payload["context_budget"]
    assert budget["max_count"] == 8
    assert budget["max_chars_per_item"] == 1200
    assert budget["max_total_chars"] == 10000
    assert set(budget["warnings"]) == {
        "invalid_max_count",
        "invalid_max_chars_per_item",
        "invalid_max_total_chars",
        "invalid_total_budget_seconds",
    }
    assert len(payload["contexts"][0]["text"]) == 1200
    assert payload["total_budget_seconds"] == 300.0


def _create(db_session, regular_user, *, query: str = "query"):
    return create_ragas_eval_job(
        db_session,
        user_id=regular_user.id,
        workspace_id=None,
        query=query,
        answer="answer",
        contexts=[RagasEvalContext(text="context", file_id=1, chunk_id=2, rank=0)],
        agent_run_id=None,
        search_trace_id=None,
        sample_type="answer",
        max_count=8,
        max_chars_per_item=1200,
        max_total_chars=10000,
        total_budget_seconds=60,
    )


def test_create_eval_and_job_are_linked_pending(db_session, regular_user):
    eval_row, job = _create(db_session, regular_user)

    assert eval_row.status == "pending"
    assert job.status == "pending"
    assert job.eval_id == eval_row.id
    assert job.payload_json["query"] == "query"
    assert job.payload_json["contexts"][0]["chunk_id"] == 2
    assert eval_row.source_context_count == 1
    assert eval_row.selected_context_count == 1
    assert eval_row.context_budget_version == "v1"


def test_claim_uses_global_limit_fixed_deadline_and_skip_locked(
    engine,
):
    Session = sessionmaker(bind=engine)
    setup = Session()
    username = f"ragas-claim-{uuid.uuid4().hex}"
    department_id = setup.execute(text("SELECT min(id) FROM departments")).scalar_one()
    user = User(
        username=username,
        password_hash="test",
        is_admin=False,
        is_active=True,
        password_rev=0,
        primary_department_id=department_id,
    )
    setup.add(user)
    setup.flush()
    create_ragas_eval_job(
        setup,
        user_id=user.id,
        workspace_id=None,
        query="first",
        answer="answer",
        contexts=[RagasEvalContext("context", 1, 2, 0)],
        total_budget_seconds=60,
    )
    create_ragas_eval_job(
        setup,
        user_id=user.id,
        workspace_id=None,
        query="second",
        answer="answer",
        contexts=[RagasEvalContext("context", 1, 2, 0)],
        total_budget_seconds=60,
    )
    setup.commit()

    barrier = threading.Barrier(2)

    def _claim(worker_id: str):
        session = Session()
        try:
            barrier.wait(timeout=5)
            job = claim_next_ragas_eval_job(
                session, worker_id=worker_id, concurrency=1
            )
            session.commit()
            if job is None:
                return None
            return (
                job.id,
                job.status,
                job.lease_generation,
                job.started_at,
                job.evaluation_deadline_at,
                job.lease_expires_at,
            )
        finally:
            session.close()

    try:
        with ThreadPoolExecutor(max_workers=2) as pool:
            outcomes = list(pool.map(_claim, ("worker-1", "worker-2")))
        claimed = next(outcome for outcome in outcomes if outcome is not None)

        assert sum(outcome is not None for outcome in outcomes) == 1
        _, status, generation, started_at, deadline_at, lease_expires_at = claimed
        assert status == "running"
        assert generation == 1
        assert deadline_at - started_at == timedelta(seconds=60)
        assert lease_expires_at - deadline_at == timedelta(seconds=60)
    finally:
        cleanup = Session()
        try:
            cleanup.query(User).filter(User.username == username).delete()
            cleanup.commit()
        finally:
            cleanup.close()
        setup.close()


def test_heartbeat_and_finish_are_fenced(db_session, regular_user):
    created, _ = _create(db_session, regular_user)
    db_session.commit()
    claimed = claim_next_ragas_eval_job(
        db_session, worker_id="owner", concurrency=1
    )
    db_session.commit()
    assert claimed is not None

    assert heartbeat_ragas_eval_job(
        db_session,
        job_id=claimed.id,
        worker_id="stale",
        lease_generation=claimed.lease_generation,
    ) is False
    assert heartbeat_ragas_eval_job(
        db_session,
        job_id=claimed.id,
        worker_id="owner",
        lease_generation=claimed.lease_generation,
    ) is True
    original_lease = claimed.lease_expires_at
    db_session.refresh(claimed)
    assert claimed.lease_expires_at == original_lease

    assert finish_ragas_eval_job(
        db_session,
        job_id=claimed.id,
        worker_id="stale",
        lease_generation=claimed.lease_generation,
        status="succeeded",
    ) is False
    assert finish_ragas_eval_job(
        db_session,
        job_id=claimed.id,
        worker_id="owner",
        lease_generation=claimed.lease_generation,
        status="succeeded",
        faithfulness_score=0.9,
        context_precision_score=0.8,
    ) is True
    db_session.refresh(created)
    assert created.status == "succeeded"
    assert created.metric_version
    assert created.metric_variant == "faithfulness+context_precision_without_reference"


def test_lease_fence_uses_database_clock_after_row_lock_wait(engine):
    """A waiter must lose its lease if it expires while blocked on a row lock."""
    Session = sessionmaker(bind=engine)
    setup = Session()
    job_id: int | None = None
    eval_id: int | None = None
    user_id: int | None = None
    department_id: int | None = None
    try:
        department = Department(name=f"ragas-lease-dept-{uuid.uuid4().hex}")
        setup.add(department)
        setup.flush()
        department_id = int(department.id)
        user = User(
            username=f"ragas-lease-{uuid.uuid4().hex}",
            password_hash="test",
            is_admin=False,
            is_active=True,
            password_rev=0,
            primary_department_id=department_id,
        )
        setup.add(user)
        setup.flush()
        user_id = int(user.id)
        _, job = _create(setup, user)
        job_id = int(job.id)
        eval_id = int(job.eval_id)
        setup.commit()
        claimed = claim_next_ragas_eval_job(setup, worker_id="owner", concurrency=1)
        setup.commit()
        assert claimed is not None

        def _run_after_expiry(operation):
            locker = Session()
            waiter = Session()
            try:
                locker.execute(
                    text(
                        "UPDATE kb_ragas_eval_jobs "
                        "SET lease_expires_at = CAST(clock_timestamp() AS timestamp) "
                        "+ interval '0.1 seconds' WHERE id = :job_id"
                    ),
                    {"job_id": claimed.id},
                )
                with ThreadPoolExecutor(max_workers=1) as pool:
                    future = pool.submit(operation, waiter)
                    time.sleep(0.2)
                    locker.commit()
                    result = future.result(timeout=5)
                waiter.commit()
                return result
            finally:
                locker.rollback()
                locker.close()
                waiter.close()

        assert _run_after_expiry(
            lambda session: heartbeat_ragas_eval_job(
                session,
                job_id=claimed.id,
                worker_id="owner",
                lease_generation=claimed.lease_generation,
            )
        ) is False
        assert _run_after_expiry(
            lambda session: start_ragas_eval_attempt(
                session,
                job_id=claimed.id,
                worker_id="owner",
                lease_generation=claimed.lease_generation,
            )
        ) is False
        assert _run_after_expiry(
            lambda session: finish_ragas_eval_job(
                session,
                job_id=claimed.id,
                worker_id="owner",
                lease_generation=claimed.lease_generation,
                status="failed",
            )
        ) is False
    finally:
        setup.close()
        cleanup = Session()
        try:
            if job_id is not None:
                cleanup.query(KbRagasEvalJob).filter(KbRagasEvalJob.id == job_id).delete()
            if eval_id is not None:
                cleanup.query(KbSearchEval).filter(KbSearchEval.id == eval_id).delete()
            if user_id is not None:
                cleanup.query(User).filter(User.id == user_id).delete()
            if department_id is not None:
                cleanup.query(Department).filter(Department.id == department_id).delete()
            cleanup.commit()
        finally:
            cleanup.close()


def test_attempt_fencing_and_deadline_helper(db_session, regular_user):
    _, _ = _create(db_session, regular_user)
    db_session.commit()
    claimed = claim_next_ragas_eval_job(
        db_session, worker_id="owner", concurrency=1
    )
    db_session.commit()
    assert claimed is not None

    assert start_ragas_eval_attempt(
        db_session,
        job_id=claimed.id,
        worker_id="owner",
        lease_generation=claimed.lease_generation,
    ) is True
    db_session.refresh(claimed)
    assert claimed.attempt_count == 1
    assert 0 < effective_ragas_metric_timeout(db_session, claimed, 90) <= 60

    db_session.execute(
        text(
            "UPDATE kb_ragas_eval_jobs "
            "SET evaluation_deadline_at = CAST(now() AS timestamp) - interval '1 second' "
            "WHERE id = :job_id"
        ),
        {"job_id": claimed.id},
    )
    db_session.expire_all()
    assert effective_ragas_metric_timeout(db_session, claimed, 90) == 0


def test_reconcile_requeues_unstarted_fails_started_and_closes_legacy(
    db_session, regular_user
):
    eval_unstarted, _ = _create(db_session, regular_user, query="unstarted")
    db_session.commit()
    unstarted = claim_next_ragas_eval_job(
        db_session, worker_id="worker-1", concurrency=2
    )
    db_session.commit()
    assert unstarted is not None

    eval_started, _ = _create(db_session, regular_user, query="started")
    db_session.commit()
    started = claim_next_ragas_eval_job(
        db_session, worker_id="worker-2", concurrency=2
    )
    db_session.commit()
    assert started is not None
    assert start_ragas_eval_attempt(
        db_session,
        job_id=started.id,
        worker_id="worker-2",
        lease_generation=started.lease_generation,
    )

    legacy = KbSearchEval(
        user_id=regular_user.id,
        workspace_id=None,
        sample_type="answer",
        query_hash="q",
        query_preview="q",
        answer_hash="a",
        answer_preview="a",
        status="running",
    )
    db_session.add(legacy)
    db_session.flush()
    db_session.execute(
        text(
            "UPDATE kb_ragas_eval_jobs "
            "SET lease_expires_at = CAST(now() AS timestamp) - interval '1 second' "
            "WHERE id IN (:first_id, :second_id)"
        ),
        {"first_id": unstarted.id, "second_id": started.id},
    )
    db_session.commit()

    stats = reconcile_stale_ragas_eval_jobs(db_session)
    db_session.commit()
    db_session.refresh(eval_unstarted)
    db_session.refresh(eval_started)
    db_session.refresh(legacy)
    db_session.refresh(unstarted)
    db_session.refresh(started)

    assert stats == {"requeued": 1, "failed": 1, "legacy_failed": 1}
    assert unstarted.status == "pending"
    assert unstarted.lease_generation == 2
    assert eval_unstarted.status == "pending"
    assert started.status == "failed"
    assert eval_started.error_code == "worker_lease_expired"
    assert legacy.status == "failed"
    assert legacy.error_code == "legacy_running_orphan"
