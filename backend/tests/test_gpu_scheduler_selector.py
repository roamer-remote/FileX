from datetime import datetime, timedelta

from services.gpu_scheduler_selector import (
    GpuQueueCandidate,
    effective_priority,
    select_next_gpu_job,
)


def test_mineru_wins_when_gpu_is_idle():
    now = datetime(2026, 8, 1, 0, 0, 0)
    result = select_next_gpu_job(
        [
            GpuQueueCandidate("r-1", "raptor", now - timedelta(seconds=30)),
            GpuQueueCandidate("m-1", "mineru", now),
        ],
        now=now,
    )
    assert result.candidate.job_id == "m-1"
    assert result.reason == "mineru_priority"


def test_aged_raptor_wins_before_new_mineru_can_insert():
    now = datetime(2026, 8, 1, 0, 0, 0)
    result = select_next_gpu_job(
        [
            GpuQueueCandidate("r-1", "raptor", now - timedelta(seconds=901)),
            GpuQueueCandidate("m-1", "mineru", now),
        ],
        now=now,
        current_model_group="mineru",
        current_batch_size=1,
        batch_started_at=now,
    )
    assert result.candidate.job_id == "r-1"
    assert result.reason == "raptor_max_wait"


def test_mineru_batch_is_limited_and_expires():
    now = datetime(2026, 8, 1, 0, 0, 0)
    candidates = [GpuQueueCandidate("m-2", "mineru", now)]
    result = select_next_gpu_job(
        candidates,
        now=now,
        current_model_group="mineru",
        current_batch_size=4,
        batch_started_at=now - timedelta(seconds=599),
    )
    assert result.reason == "continue_mineru_batch"

    expired = select_next_gpu_job(
        candidates,
        now=now,
        current_model_group="mineru",
        current_batch_size=4,
        batch_started_at=now - timedelta(seconds=600),
    )
    assert expired.reason == "start_new_mineru_batch"


def test_raptor_aging_reaches_mineru_priority_at_max_wait():
    now = datetime(2026, 8, 1, 0, 0, 0)
    candidate = GpuQueueCandidate("r-1", "raptor", now - timedelta(seconds=900))
    assert effective_priority(candidate, now=now) == 100


def test_batch_boundary_does_not_admit_new_mineru_ahead_of_raptor():
    now = datetime(2026, 8, 1, 0, 0, 0)
    result = select_next_gpu_job(
        [
            GpuQueueCandidate("m-new", "mineru", now),
            GpuQueueCandidate("r-new", "raptor", now + timedelta(seconds=1)),
        ],
        now=now,
        current_model_group="mineru",
        current_batch_size=5,
        batch_started_at=now,
    )
    assert result.candidate.job_id == "r-new"
    assert result.reason == "mineru_batch_boundary_switch_raptor"
