# Copyright (c) 2026 徐泽宇
"""RAGAS durable-worker orchestration tests (feature 142)."""

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import MagicMock


def test_process_one_claims_under_configured_limit_and_executes(monkeypatch):
    from workers import kb_ragas_eval

    calls: dict[str, object] = {}
    job = SimpleNamespace(id=41, worker_id="worker-a", lease_generation=3)
    monkeypatch.setattr(kb_ragas_eval, "get_ragas_eval_worker_settings", lambda db: (2, 1.0))
    monkeypatch.setattr(
        kb_ragas_eval,
        "claim_next_ragas_eval_job",
        lambda db, *, worker_id, concurrency: calls.update(
            worker_id=worker_id, concurrency=concurrency
        ) or job,
    )
    monkeypatch.setattr(kb_ragas_eval, "start_ragas_eval_attempt", lambda db, **kwargs: True)
    monkeypatch.setattr(
        kb_ragas_eval,
        "execute_ragas_eval_job",
        lambda db, claimed_job: calls.update(executed=claimed_job.id),
    )

    db = MagicMock()
    assert kb_ragas_eval.process_one(db, worker_id="worker-a") is True
    assert calls == {"worker_id": "worker-a", "concurrency": 2, "executed": 41}
    assert db.commit.call_count == 2


def test_process_one_returns_false_without_pending_job(monkeypatch):
    from workers import kb_ragas_eval

    monkeypatch.setattr(kb_ragas_eval, "get_ragas_eval_worker_settings", lambda db: (1, 1.0))
    monkeypatch.setattr(
        kb_ragas_eval,
        "claim_next_ragas_eval_job",
        lambda db, *, worker_id, concurrency: None,
    )

    assert kb_ragas_eval.process_one(MagicMock(), worker_id="worker-a") is False


def test_process_one_does_not_call_model_when_attempt_fencing_is_lost(monkeypatch):
    from workers import kb_ragas_eval

    job = SimpleNamespace(id=41, worker_id="worker-a", lease_generation=3)
    db = MagicMock()
    monkeypatch.setattr(kb_ragas_eval, "get_ragas_eval_worker_settings", lambda db: (1, 1.0))
    monkeypatch.setattr(
        kb_ragas_eval,
        "claim_next_ragas_eval_job",
        lambda db, *, worker_id, concurrency: job,
    )
    monkeypatch.setattr(
        kb_ragas_eval,
        "start_ragas_eval_attempt",
        lambda db, **kwargs: False,
        raising=False,
    )
    execute = MagicMock()
    monkeypatch.setattr(kb_ragas_eval, "execute_ragas_eval_job", execute)

    assert kb_ragas_eval.process_one(db, worker_id="worker-a") is False
    execute.assert_not_called()
