import pytest

from services.kb_readonly_workflow_budget import (
    TERMINAL_STATUSES,
    WorkflowStatus,
    build_evidence_receipt,
    create_readonly_workflow,
    is_readonly_workflow_kill_switch_enabled,
    run_readonly_retrieval,
    workflow_audit_payload,
)


def test_budgeted_workflow_is_default_closed_without_opt_in():
    state = create_readonly_workflow(run_id="run-1", opt_in=False, started_at_ms=100)
    assert state.status is WorkflowStatus.BLOCKED_BY_EVIDENCE
    assert state.enabled is False
    assert state.receipts == ()


def test_append_retrieval_receipt_tracks_budget_trace_acl_and_evidence():
    state = create_readonly_workflow(run_id="run-2", opt_in=True, started_at_ms=100)
    state, receipt = state.append_retrieval(
        now_ms=200,
        parent_trace="trace-0",
        reason="citation gap",
        acl_file_ids=(3, 5),
        evidence_receipt="evidence-1",
        vector_queries=2,
        file_reads=1,
        input_tokens=100,
        output_tokens=80,
    )
    assert state.status is WorkflowStatus.RUNNING
    assert receipt.accepted is True
    assert receipt.remaining["steps"] == 1
    assert receipt.remaining["vector_queries"] == 2
    assert receipt.acl_file_ids == (3, 5)
    assert state.receipts == (receipt,)


def test_budget_exhaustion_is_terminal_and_does_not_retry():
    state = create_readonly_workflow(run_id="run-3", opt_in=True, started_at_ms=0)
    state, first = state.append_retrieval(
        now_ms=1,
        parent_trace="t0",
        reason="first",
        acl_file_ids=(1,),
        evidence_receipt="e1",
        vector_queries=4,
        file_reads=2,
        input_tokens=4000,
        output_tokens=2000,
    )
    assert state.status is WorkflowStatus.RUNNING
    state, second = state.append_retrieval(
        now_ms=2,
        parent_trace="t1",
        reason="over budget",
        acl_file_ids=(1,),
        evidence_receipt="e2",
        vector_queries=1,
        file_reads=0,
        input_tokens=1,
        output_tokens=1,
    )
    assert state.status is WorkflowStatus.BUDGET_EXHAUSTED
    assert second.accepted is False
    assert len(state.receipts) == 1
    assert state.status in TERMINAL_STATUSES


def test_timeout_and_missing_evidence_are_deterministic():
    state = create_readonly_workflow(run_id="run-4", opt_in=True, started_at_ms=0)
    with pytest.raises(ValueError, match="evidence receipt"):
        state.append_retrieval(
            now_ms=1,
            parent_trace="t0",
            reason="no receipt",
            acl_file_ids=(1,),
            evidence_receipt="",
            vector_queries=1,
            file_reads=0,
            input_tokens=1,
            output_tokens=1,
        )
    state, receipt = state.append_retrieval(
        now_ms=2501,
        parent_trace="t0",
        reason="late",
        acl_file_ids=(1,),
        evidence_receipt="e1",
        vector_queries=1,
        file_reads=0,
        input_tokens=1,
        output_tokens=1,
    )
    assert state.status is WorkflowStatus.TIMEOUT
    assert receipt.accepted is False


def test_finalize_and_cancel_are_terminal_and_reject_follow_up_work():
    state = create_readonly_workflow(run_id="run-5", opt_in=True, started_at_ms=0)
    assert state.complete().status is WorkflowStatus.COMPLETED
    cancelled = state.cancel()
    assert cancelled.status is WorkflowStatus.CANCELLED
    cancelled, receipt = cancelled.append_retrieval(
        now_ms=1,
        parent_trace="t0",
        reason="after cancel",
        acl_file_ids=(1,),
        evidence_receipt="e1",
        vector_queries=1,
        file_reads=0,
        input_tokens=1,
        output_tokens=1,
    )
    assert cancelled.status is WorkflowStatus.CANCELLED
    assert receipt.accepted is False


def test_readonly_adapter_is_default_closed_and_does_not_call_executor():
    calls: list[str] = []
    state, receipt, result = run_readonly_retrieval(
        create_readonly_workflow(run_id="run-6", opt_in=False, started_at_ms=0),
        now_ms=1,
        parent_trace="trace-6",
        reason="secondary retrieval",
        acl_file_ids=(3, 2, 3),
        evidence_receipt="evidence-6",
        vector_queries=1,
        file_reads=1,
        input_tokens=10,
        output_tokens=10,
        executor=lambda accepted: calls.append(accepted.run_id),
    )
    assert state.status is WorkflowStatus.BLOCKED_BY_EVIDENCE
    assert receipt.accepted is False
    assert result is None
    assert calls == []


def test_readonly_adapter_honors_kill_switch_and_only_executes_after_receipt():
    calls: list[tuple[str, tuple[int, ...]]] = []
    initial = create_readonly_workflow(run_id="run-7", opt_in=True, started_at_ms=0)
    killed, receipt, result = run_readonly_retrieval(
        initial,
        now_ms=1,
        parent_trace="trace-7",
        reason="secondary retrieval",
        acl_file_ids=(3, 2, 3),
        evidence_receipt="evidence-7",
        vector_queries=1,
        file_reads=1,
        input_tokens=10,
        output_tokens=10,
        kill_switch=True,
        executor=lambda accepted: calls.append((accepted.run_id, accepted.acl_file_ids)),
    )
    assert killed.status is WorkflowStatus.CANCELLED
    assert receipt.accepted is False
    assert result is None
    assert calls == []

    completed, receipt, result = run_readonly_retrieval(
        initial,
        now_ms=1,
        parent_trace="trace-7",
        reason="secondary retrieval",
        acl_file_ids=(3, 2, 3),
        evidence_receipt="evidence-7",
        vector_queries=1,
        file_reads=1,
        input_tokens=10,
        output_tokens=10,
        executor=lambda accepted: calls.append((accepted.run_id, accepted.acl_file_ids)) or "ok",
    )
    assert completed.status is WorkflowStatus.COMPLETED
    assert receipt.accepted is True
    assert result == "ok"
    assert calls == [("run-7", (2, 3))]


def test_readonly_adapter_converts_executor_failure_to_degraded_audit_state():
    state, receipt, result = run_readonly_retrieval(
        create_readonly_workflow(run_id="run-8", opt_in=True, started_at_ms=0),
        now_ms=1,
        parent_trace="trace-8",
        reason="secondary retrieval",
        acl_file_ids=(8,),
        evidence_receipt="evidence-8",
        vector_queries=1,
        file_reads=0,
        input_tokens=1,
        output_tokens=1,
        executor=lambda accepted: (_ for _ in ()).throw(RuntimeError("boom")),
    )
    assert state.status is WorkflowStatus.DEGRADED
    assert receipt.accepted is True
    assert result is None
    audit = workflow_audit_payload(state)
    assert audit["status"] == "DEGRADED"
    assert audit["run_id"] == "run-8"
    assert audit["receipts"] == 1
    assert audit["budget_used"]["steps"] == 1
    assert audit["receipt_summaries"][0]["parent_trace"] == "trace-8"


def test_evidence_receipt_requires_acl_scoped_citation_bearing_chunk_hits():
    items = [
        {
            "file_id": 7,
            "chunk_id": 11,
            "citation_tier": "paginated",
            "citation_label": "《source.pdf》第 1 页",
        }
    ]
    receipt = build_evidence_receipt(items, acl_file_ids={7}, parent_trace="trace-9")
    assert receipt.startswith("evidence-187:")
    assert receipt == build_evidence_receipt(items, acl_file_ids={7}, parent_trace="trace-9")

    with pytest.raises(ValueError, match="ACL"):
        build_evidence_receipt(items, acl_file_ids={8}, parent_trace="trace-9")
    with pytest.raises(ValueError, match="citation"):
        build_evidence_receipt(
            [{"file_id": 7, "chunk_id": 11}],
            acl_file_ids={7},
            parent_trace="trace-9",
        )


def test_readonly_adapter_enforces_deadline_after_executor_returns():
    state, receipt, result = run_readonly_retrieval(
        create_readonly_workflow(run_id="run-10", opt_in=True, started_at_ms=0),
        now_ms=1,
        parent_trace="trace-10",
        reason="secondary retrieval",
        acl_file_ids=(10,),
        evidence_receipt="evidence-10",
        vector_queries=1,
        file_reads=0,
        input_tokens=1,
        output_tokens=1,
        clock_ms=lambda: 2501,
        executor=lambda accepted: "late",
    )
    assert state.status is WorkflowStatus.TIMEOUT
    assert receipt.accepted is True
    assert result is None


def test_readonly_workflow_kill_switch_is_default_off_and_env_driven(monkeypatch):
    monkeypatch.delenv("FILEX_KB_READONLY_WORKFLOW_KILL_SWITCH", raising=False)
    assert is_readonly_workflow_kill_switch_enabled() is False
    monkeypatch.setenv("FILEX_KB_READONLY_WORKFLOW_KILL_SWITCH", "true")
    assert is_readonly_workflow_kill_switch_enabled() is True
