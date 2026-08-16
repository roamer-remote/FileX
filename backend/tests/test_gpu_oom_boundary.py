"""164 T-7：OOM 识别 → 释放/重探 → 最多一次受控重试 → failed/DLQ 边界。"""

from __future__ import annotations

from unittest.mock import patch

import pytest

from models.file import File as FileModel
from models.kb_extract_job import KbExtractJob
from services.gpu_model_lifecycle_service import GpuExecutionContext, GpuOomError
from services.kb_extract_service import (
    JOB_ERROR,
    JOB_QUEUED,
    get_kb_extract_max_attempts,
    run_extract_job,
)


@pytest.fixture
def pdf_file(db_session, regular_user):
    f = FileModel(
        filename="oom.pdf",
        original_name="oom.pdf",
        file_path="/tmp/oom.pdf",
        file_size=100,
        mime_type="application/pdf",
        user_id=regular_user.id,
        has_md=False,
    )
    db_session.add(f)
    db_session.commit()
    db_session.refresh(f)
    return f


def _extract_job(db_session, pdf_file, regular_user, *, attempts: int, oom_retry_count: int):
    job = KbExtractJob(
        user_id=regular_user.id,
        file_id=pdf_file.id,
        status=JOB_QUEUED,
        provider="mineru",
        attempts=attempts,
        oom_retry_count=oom_retry_count,
    )
    db_session.add(job)
    db_session.commit()
    db_session.refresh(job)
    return job


def test_extract_oom_first_failure_allows_one_controlled_retry(db_session, pdf_file, regular_user):
    job = _extract_job(db_session, pdf_file, regular_user, attempts=0, oom_retry_count=0)

    with patch(
        "services.extract.providers.registry.extract_with_provider",
        side_effect=GpuOomError("CUDA out of memory"),
    ):
        run_extract_job(db_session, job)
        db_session.commit()

    db_session.refresh(job)
    assert job.status == JOB_ERROR
    assert job.oom_retry_count == 1
    assert job.attempts == 1
    assert job.attempts < get_kb_extract_max_attempts()
    assert "gpu_oom_release_reprobe" in job.last_error


def test_extract_oom_second_failure_reaches_dlq_cap(db_session, pdf_file, regular_user):
    job = _extract_job(db_session, pdf_file, regular_user, attempts=1, oom_retry_count=1)

    with patch(
        "services.extract.providers.registry.extract_with_provider",
        side_effect=GpuOomError("CUDA out of memory"),
    ):
        run_extract_job(db_session, job)
        db_session.commit()

    db_session.refresh(job)
    assert job.status == JOB_ERROR
    assert job.oom_retry_count == 2
    assert job.attempts == get_kb_extract_max_attempts()


def test_mineru_rpc_preserves_gpu_oom_classification():
    from messaging.kb_mineru_rpc import call_mineru_extract

    class FakeScheduler:
        def switch_to(self, *_args, **_kwargs) -> None:
            return None

        def acquire_batch(self, *_args, **_kwargs) -> None:
            return None

        def execute(self, *_args, **_kwargs) -> object:
            raise GpuOomError("CUDA out of memory")

    with pytest.raises(GpuOomError, match="out of memory"):
        call_mineru_extract(
            job_id=1,
            file_id=2,
            file_path="/tmp/a.pdf",
            original_name="a.pdf",
            gpu_scheduler=FakeScheduler(),  # type: ignore[arg-type]
            gpu_context=GpuExecutionContext("lease-1", "fence-1", "1"),
        )


def test_mineru_registry_does_not_fallback_to_cpu_on_gpu_oom(db_session, pdf_file, regular_user):
    from services.extract.providers.registry import extract_with_provider

    with patch(
        "services.extract.providers.mineru_provider.extract_mineru",
        side_effect=GpuOomError("CUDA out of memory"),
    ):
        with pytest.raises(GpuOomError, match="out of memory"):
            extract_with_provider(
                pdf_file,
                db_session,
                provider_override="mineru",
                job_id=1,
            )
