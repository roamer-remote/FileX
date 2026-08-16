"""Default-closed, in-memory budget contract for 187-P2 read-only retrieval."""

from __future__ import annotations

import hashlib
import json
import os
from dataclasses import dataclass, field, replace
from enum import StrEnum
from typing import Callable, TypeVar


_ResultT = TypeVar("_ResultT")


def build_evidence_receipt(
    items: list[dict],
    *,
    acl_file_ids: set[int],
    parent_trace: str,
) -> str:
    """Create a deterministic receipt only from ACL-scoped, cited chunk hits."""
    if not parent_trace.strip():
        raise ValueError("parent trace is required for evidence receipt")
    if not items:
        raise ValueError("citation evidence is required")
    canonical: list[dict[str, object]] = []
    for item in items:
        try:
            file_id = int(item["file_id"])
            chunk_id = int(item["chunk_id"])
        except (KeyError, TypeError, ValueError) as exc:
            raise ValueError("citation evidence requires file and chunk IDs") from exc
        if file_id not in acl_file_ids:
            raise ValueError("citation evidence contains file outside ACL")
        if not str(item.get("citation_tier") or "").strip() or not str(
            item.get("citation_label") or ""
        ).strip():
            raise ValueError("citation evidence requires citation fields")
        canonical.append(
            {
                "file_id": file_id,
                "chunk_id": chunk_id,
                "citation_tier": str(item["citation_tier"]),
                "citation_label": str(item["citation_label"]),
            }
        )
    payload = {
        "parent_trace": parent_trace,
        "hits": sorted(canonical, key=lambda row: (int(row["file_id"]), int(row["chunk_id"]))),
    }
    digest = hashlib.sha256(
        json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode(
            "utf-8"
        )
    ).hexdigest()
    return f"evidence-187:{digest}"


class WorkflowStatus(StrEnum):
    RUNNING = "RUNNING"
    COMPLETED = "COMPLETED"
    DEGRADED = "DEGRADED"
    BUDGET_EXHAUSTED = "BUDGET_EXHAUSTED"
    TIMEOUT = "TIMEOUT"
    CANCELLED = "CANCELLED"
    BLOCKED_BY_EVIDENCE = "BLOCKED_BY_EVIDENCE"


TERMINAL_STATUSES = frozenset({
    WorkflowStatus.COMPLETED,
    WorkflowStatus.DEGRADED,
    WorkflowStatus.BUDGET_EXHAUSTED,
    WorkflowStatus.TIMEOUT,
    WorkflowStatus.CANCELLED,
    WorkflowStatus.BLOCKED_BY_EVIDENCE,
})


@dataclass(frozen=True, slots=True)
class WorkflowBudget:
    max_steps: int = 2
    deadline_ms: int = 2500
    max_vector_queries: int = 4
    max_file_reads: int = 2
    max_input_tokens: int = 4000
    max_output_tokens: int = 2000


@dataclass(frozen=True, slots=True)
class RetrievalReceipt:
    accepted: bool
    run_id: str
    parent_trace: str
    reason: str
    remaining: dict[str, int]
    acl_file_ids: tuple[int, ...]
    evidence_receipt: str


@dataclass(frozen=True, slots=True)
class ReadonlyWorkflowState:
    run_id: str
    enabled: bool
    started_at_ms: int
    status: WorkflowStatus
    budget: WorkflowBudget = field(default_factory=WorkflowBudget)
    steps: int = 0
    vector_queries: int = 0
    file_reads: int = 0
    input_tokens: int = 0
    output_tokens: int = 0
    receipts: tuple[RetrievalReceipt, ...] = ()

    def _remaining(self, now_ms: int) -> dict[str, int]:
        return {
            "steps": max(0, self.budget.max_steps - self.steps),
            "vector_queries": max(0, self.budget.max_vector_queries - self.vector_queries),
            "file_reads": max(0, self.budget.max_file_reads - self.file_reads),
            "input_tokens": max(0, self.budget.max_input_tokens - self.input_tokens),
            "output_tokens": max(0, self.budget.max_output_tokens - self.output_tokens),
            "deadline_ms": max(0, self.started_at_ms + self.budget.deadline_ms - now_ms),
        }

    def append_retrieval(
        self,
        *,
        now_ms: int,
        parent_trace: str,
        reason: str,
        acl_file_ids: tuple[int, ...],
        evidence_receipt: str,
        vector_queries: int,
        file_reads: int,
        input_tokens: int,
        output_tokens: int,
    ) -> tuple["ReadonlyWorkflowState", RetrievalReceipt]:
        if not evidence_receipt.strip():
            raise ValueError("evidence receipt is required")
        if not parent_trace.strip():
            raise ValueError("parent trace is required")
        if not reason.strip():
            raise ValueError("retrieval reason is required")
        receipt = RetrievalReceipt(
            accepted=False,
            run_id=self.run_id,
            parent_trace=parent_trace,
            reason=reason,
            remaining=self._remaining(now_ms),
            acl_file_ids=tuple(sorted(set(int(file_id) for file_id in acl_file_ids))),
            evidence_receipt=evidence_receipt,
        )
        if not self.enabled or self.status in TERMINAL_STATUSES:
            return replace(self, status=self.status if self.status in TERMINAL_STATUSES else WorkflowStatus.BLOCKED_BY_EVIDENCE), receipt
        if now_ms > self.started_at_ms + self.budget.deadline_ms:
            return replace(self, status=WorkflowStatus.TIMEOUT), receipt
        requested = (1, vector_queries, file_reads, input_tokens, output_tokens)
        available = (
            self.budget.max_steps - self.steps,
            self.budget.max_vector_queries - self.vector_queries,
            self.budget.max_file_reads - self.file_reads,
            self.budget.max_input_tokens - self.input_tokens,
            self.budget.max_output_tokens - self.output_tokens,
        )
        if any(value < 0 for value in requested) or any(value > limit for value, limit in zip(requested, available)):
            return replace(self, status=WorkflowStatus.BUDGET_EXHAUSTED), receipt
        accepted = replace(
            self,
            steps=self.steps + 1,
            vector_queries=self.vector_queries + vector_queries,
            file_reads=self.file_reads + file_reads,
            input_tokens=self.input_tokens + input_tokens,
            output_tokens=self.output_tokens + output_tokens,
        )
        accepted_receipt = replace(
            receipt,
            accepted=True,
            remaining=accepted._remaining(now_ms),
        )
        return replace(accepted, receipts=accepted.receipts + (accepted_receipt,)), accepted_receipt

    def complete(self) -> "ReadonlyWorkflowState":
        if self.status is not WorkflowStatus.RUNNING:
            return self
        return replace(self, status=WorkflowStatus.COMPLETED)

    def cancel(self) -> "ReadonlyWorkflowState":
        if self.status in TERMINAL_STATUSES:
            return self
        return replace(self, status=WorkflowStatus.CANCELLED)


def create_readonly_workflow(
    *,
    run_id: str,
    opt_in: bool,
    started_at_ms: int,
    budget: WorkflowBudget | None = None,
) -> ReadonlyWorkflowState:
    if not opt_in:
        return ReadonlyWorkflowState(
            run_id=run_id,
            enabled=False,
            started_at_ms=started_at_ms,
            status=WorkflowStatus.BLOCKED_BY_EVIDENCE,
            budget=budget or WorkflowBudget(),
        )
    return ReadonlyWorkflowState(
        run_id=run_id,
        enabled=True,
        started_at_ms=started_at_ms,
        status=WorkflowStatus.RUNNING,
        budget=budget or WorkflowBudget(),
    )


def run_readonly_retrieval(
    state: ReadonlyWorkflowState,
    *,
    now_ms: int,
    parent_trace: str,
    reason: str,
    acl_file_ids: tuple[int, ...],
    evidence_receipt: str,
    vector_queries: int,
    file_reads: int,
    input_tokens: int,
    output_tokens: int,
    executor: Callable[[RetrievalReceipt], _ResultT],
    kill_switch: bool = False,
    clock_ms: Callable[[], int] | None = None,
) -> tuple[ReadonlyWorkflowState, RetrievalReceipt, _ResultT | None]:
    """Run one explicitly opted-in read-only retrieval step.

    The executor receives only an immutable, ACL-filtered receipt.  This adapter
    has no database/session access and therefore cannot write indexes, overlays,
    settings, or business facts.  Callers may serialize ``workflow_audit_payload``
    to the existing operation-log/trace pipeline after the run.
    """
    if kill_switch:
        cancelled = state.cancel()
        cancelled, receipt = cancelled.append_retrieval(
            now_ms=now_ms,
            parent_trace=parent_trace,
            reason="kill switch: " + reason,
            acl_file_ids=acl_file_ids,
            evidence_receipt=evidence_receipt,
            vector_queries=vector_queries,
            file_reads=file_reads,
            input_tokens=input_tokens,
            output_tokens=output_tokens,
        )
        return cancelled, receipt, None

    state, receipt = state.append_retrieval(
        now_ms=now_ms,
        parent_trace=parent_trace,
        reason=reason,
        acl_file_ids=acl_file_ids,
        evidence_receipt=evidence_receipt,
        vector_queries=vector_queries,
        file_reads=file_reads,
        input_tokens=input_tokens,
        output_tokens=output_tokens,
    )
    if not receipt.accepted:
        return state, receipt, None
    try:
        result = executor(receipt)
    except Exception:
        # Keep the failure deterministic and avoid leaking provider/error text
        # into the trace or operation log.
        return replace(state, status=WorkflowStatus.DEGRADED), receipt, None
    if clock_ms is not None and clock_ms() > state.started_at_ms + state.budget.deadline_ms:
        return replace(state, status=WorkflowStatus.TIMEOUT), receipt, None
    return state.complete(), receipt, result


def workflow_audit_payload(state: ReadonlyWorkflowState) -> dict[str, object]:
    """Return a stable, non-secret audit projection for trace/operation logs."""
    return {
        "run_id": state.run_id,
        "status": state.status.value,
        "enabled": state.enabled,
        "receipts": len(state.receipts),
        "budget_used": {
            "steps": state.steps,
            "vector_queries": state.vector_queries,
            "file_reads": state.file_reads,
            "input_tokens": state.input_tokens,
            "output_tokens": state.output_tokens,
        },
        "receipt_summaries": [
            {
                "accepted": receipt.accepted,
                "run_id": receipt.run_id,
                "parent_trace": receipt.parent_trace,
                "reason": receipt.reason,
                "remaining": receipt.remaining,
                "acl_file_ids": list(receipt.acl_file_ids),
                "evidence_receipt": receipt.evidence_receipt,
            }
            for receipt in state.receipts
        ],
    }


def is_readonly_workflow_kill_switch_enabled() -> bool:
    """Read the process-level emergency stop; unset means the feature is live."""
    return os.environ.get("FILEX_KB_READONLY_WORKFLOW_KILL_SWITCH", "false").strip().lower() in {
        "1",
        "true",
        "yes",
        "on",
    }
