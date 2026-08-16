# Copyright (c) 2026 徐泽宇
"""Deterministic MinerU/RAPTOR GPU queue selection rules (T-4/T-5)."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime

MINERU_PRIORITY = 100
RAPTOR_PRIORITY = 50
# Five 18-second increments raise RAPTOR from 50 to the MinerU-equivalent
# priority of 100 by the fixed 15-minute max_wait boundary.
RAPTOR_AGING_STEP_SEC = 18
RAPTOR_MAX_WAIT_SEC = 900
MINERU_BATCH_LIMIT = 5
MINERU_BATCH_MAX_SEC = 600


@dataclass(frozen=True)
class GpuQueueCandidate:
    job_id: str
    job_kind: str
    created_at: datetime

    def __post_init__(self) -> None:
        if not self.job_id.strip() or self.job_kind not in {"mineru", "raptor"}:
            raise ValueError("job_id and supported job_kind are required")


@dataclass(frozen=True)
class GpuSelection:
    candidate: GpuQueueCandidate
    effective_priority: int
    reason: str


def effective_priority(candidate: GpuQueueCandidate, *, now: datetime) -> int:
    if candidate.job_kind == "mineru":
        return MINERU_PRIORITY
    waited = max(0, int((now - candidate.created_at).total_seconds()))
    return min(MINERU_PRIORITY, RAPTOR_PRIORITY + waited // RAPTOR_AGING_STEP_SEC)


def select_next_gpu_job(
    candidates: list[GpuQueueCandidate] | tuple[GpuQueueCandidate, ...],
    *,
    now: datetime,
    current_model_group: str | None = None,
    current_batch_size: int = 0,
    batch_started_at: datetime | None = None,
) -> GpuSelection | None:
    """Select one waiting job without preempting the currently running job."""
    if current_batch_size < 0:
        raise ValueError("current_batch_size must not be negative")
    if current_model_group not in (None, "mineru", "raptor"):
        raise ValueError("current_model_group must be mineru, raptor or None")
    if not candidates:
        return None

    ordered = sorted(
        candidates,
        key=lambda item: (
            -effective_priority(item, now=now),
            item.created_at,
            item.job_id,
        ),
    )
    aged_raptor = [
        item
        for item in candidates
        if item.job_kind == "raptor"
        and (now - item.created_at).total_seconds() >= RAPTOR_MAX_WAIT_SEC
    ]
    if aged_raptor:
        selected = min(aged_raptor, key=lambda item: (item.created_at, item.job_id))
        return GpuSelection(selected, effective_priority(selected, now=now), "raptor_max_wait")

    if current_model_group == "mineru":
        batch_age = (
            (now - batch_started_at).total_seconds()
            if batch_started_at is not None
            else MINERU_BATCH_MAX_SEC
        )
        mineru = [item for item in candidates if item.job_kind == "mineru"]
        if mineru and current_batch_size < MINERU_BATCH_LIMIT and batch_age < MINERU_BATCH_MAX_SEC:
            selected = min(mineru, key=lambda item: (item.created_at, item.job_id))
            return GpuSelection(selected, MINERU_PRIORITY, "continue_mineru_batch")
        if current_batch_size >= MINERU_BATCH_LIMIT or batch_age >= MINERU_BATCH_MAX_SEC:
            raptor = [item for item in candidates if item.job_kind == "raptor"]
            if raptor:
                selected = min(raptor, key=lambda item: (item.created_at, item.job_id))
                return GpuSelection(
                    selected,
                    effective_priority(selected, now=now),
                    "mineru_batch_boundary_switch_raptor",
                )
            if mineru:
                selected = min(mineru, key=lambda item: (item.created_at, item.job_id))
                return GpuSelection(selected, MINERU_PRIORITY, "start_new_mineru_batch")

    selected = ordered[0]
    reason = "mineru_priority" if selected.job_kind == "mineru" else "raptor_aging_priority"
    return GpuSelection(selected, effective_priority(selected, now=now), reason)
