"""164 §6：旧 extract/post consumer 与发布入口的 GPU 交接门禁。"""

from __future__ import annotations

from datetime import datetime, timedelta
from unittest.mock import MagicMock

import pytest
from sqlalchemy import select

from models.file import File as FileModel
from models.gpu_scheduler import GpuSchedulerLease, GpuSchedulerOutbox
from models.kb_extract_job import KbExtractJob
from models.kb_post_job import KbPostJob
from config import GPU_SCHEDULER_OWNER_ID
from services.gpu_scheduler_persistence import (
    OUTBOX_ACKED,
    OUTBOX_EXECUTING,
    OUTBOX_PUBLISHED,
    OUTBOX_QUEUED,
    ack_gpu_route,
    acquire_gpu_lease,
    enqueue_gpu_route,
    publish_gpu_route,
    reopen_gpu_route,
)


def _seed_extract_route(db_session, regular_user, *, state: str = "queued") -> tuple[KbExtractJob, GpuSchedulerOutbox]:
    file = FileModel(
        filename="handover-extract.pdf",
        original_name="handover-extract.pdf",
        file_path="/tmp/handover-extract.pdf",
        file_size=10,
        mime_type="application/pdf",
        user_id=regular_user.id,
    )
    db_session.add(file)
    db_session.flush()
    job = KbExtractJob(
        user_id=regular_user.id,
        file_id=file.id,
        provider="mineru",
        status="queued",
        created_at=datetime(2026, 8, 1, 0, 0, 0),
    )
    db_session.add(job)
    db_session.flush()
    route = enqueue_gpu_route(
        db_session,
        job_kind="mineru",
        job_id=job.id,
        file_id=file.id,
        idempotency_key=f"mineru:{job.id}:0",
        payload={"job_id": job.id, "job_kind": "mineru", "file_id": file.id, "attempt": 0},
    )
    if state == "published":
        publish_gpu_route(db_session, outbox_id=route.id, publish=lambda _payload: None)
    return job, route


def _seed_post_route(db_session, regular_user) -> tuple[KbPostJob, GpuSchedulerOutbox]:
    file = FileModel(
        filename="handover-post.pdf",
        original_name="handover-post.pdf",
        file_path="/tmp/handover-post.pdf",
        file_size=10,
        mime_type="application/pdf",
        user_id=regular_user.id,
    )
    db_session.add(file)
    db_session.flush()
    job = KbPostJob(
        user_id=regular_user.id,
        file_id=file.id,
        status="queued",
        created_at=datetime(2026, 8, 1, 0, 0, 0),
    )
    db_session.add(job)
    db_session.flush()
    route = enqueue_gpu_route(
        db_session,
        job_kind="raptor",
        job_id=job.id,
        file_id=file.id,
        idempotency_key=f"raptor:{job.id}:0",
        payload={"job_id": job.id, "job_kind": "raptor", "file_id": file.id, "attempt": 0},
    )
    publish_gpu_route(db_session, outbox_id=route.id, publish=lambda _payload: None)
    return job, route


def test_extract_consumer_hands_over_without_executing(
    db_session, regular_user, monkeypatch
):
    monkeypatch.setattr("config.GPU_SCHEDULER_ENABLED", True)
    job, route = _seed_extract_route(db_session, regular_user, state="published")
    monkeypatch.setattr(
        "messaging.kb_extract_consumer.run_extract_job",
        lambda *args: pytest.fail("old extract consumer must not execute GPU work"),
    )
    from messaging.kb_extract_consumer import _handle_job

    _handle_job(db_session, job.id, None)
    db_session.expire_all()
    assert db_session.get(GpuSchedulerOutbox, route.id).state == OUTBOX_QUEUED
    assert db_session.get(KbExtractJob, job.id).status == "queued"


def test_extract_consumer_handover_skips_published_route_with_active_lease(
    db_session, regular_user, monkeypatch
):
    """旧 extract consumer 不得重开 scheduler 已取得租约的 published route：
    route 保持 published、lease 保持 active，避免丢弃 in-flight 消息并触发
    并发重派发（P3）。"""
    monkeypatch.setattr("config.GPU_SCHEDULER_ENABLED", True)
    job, route = _seed_extract_route(db_session, regular_user, state="published")
    lease = acquire_gpu_lease(
        db_session,
        gpu_id="0",
        owner_id=GPU_SCHEDULER_OWNER_ID,
        now=datetime(2026, 8, 1, 0, 0, 0),
    )
    lease.active_job_id = str(job.id)
    db_session.commit()

    from messaging.kb_extract_consumer import _handle_job

    _handle_job(db_session, job.id, None)
    db_session.expire_all()
    assert db_session.get(GpuSchedulerOutbox, route.id).state == OUTBOX_PUBLISHED
    lease = db_session.query(GpuSchedulerLease).filter_by(gpu_id="0").one()
    assert lease.state == "active"
    assert lease.active_job_id == str(job.id)


def test_extract_consumer_handover_skips_stale_lease_published_route(
    db_session, regular_user, monkeypatch
):
    """即使 lease 心跳已停止，旧 extract consumer 也不得自行重开 published
    route；stale-lease 回收必须交给调度循环的 watchdog 确认（P1/P3）。"""
    monkeypatch.setattr("config.GPU_SCHEDULER_ENABLED", True)
    job, route = _seed_extract_route(db_session, regular_user, state="published")
    now = datetime(2026, 8, 1, 0, 0, 0)
    lease = acquire_gpu_lease(
        db_session,
        gpu_id="0",
        owner_id=GPU_SCHEDULER_OWNER_ID,
        now=now - timedelta(seconds=121),
    )
    lease.active_job_id = str(job.id)
    db_session.commit()

    from messaging.kb_extract_consumer import _handle_job

    _handle_job(db_session, job.id, None)
    db_session.expire_all()
    assert db_session.get(GpuSchedulerOutbox, route.id).state == OUTBOX_PUBLISHED
    lease = db_session.query(GpuSchedulerLease).filter_by(gpu_id="0").one()
    assert lease.state == "active"
    assert lease.active_job_id == str(job.id)


def test_extract_consumer_executes_when_gpu_disabled(
    db_session, regular_user, monkeypatch
):
    job, route = _seed_extract_route(db_session, regular_user, state="published")

    def fake_run(db, current_job):
        current_job.status = "done"

    monkeypatch.setattr("messaging.kb_extract_consumer.run_extract_job", fake_run)
    monkeypatch.setattr(
        "messaging.kb_extract_consumer._publish_extract_notify_safe",
        lambda *args, **kwargs: None,
    )
    from messaging.kb_extract_consumer import _handle_job

    _handle_job(db_session, job.id, None)
    db_session.expire_all()
    assert db_session.get(GpuSchedulerOutbox, route.id).state == OUTBOX_ACKED


def test_extract_consumer_backfills_mineru_route_when_gpu_enabled_and_route_missing(
    db_session, regular_user, monkeypatch
):
    monkeypatch.setattr("config.GPU_SCHEDULER_ENABLED", True)
    file = FileModel(
        filename="backfill-extract.pdf",
        original_name="backfill-extract.pdf",
        file_path="/tmp/backfill-extract.pdf",
        file_size=10,
        mime_type="application/pdf",
        user_id=regular_user.id,
    )
    db_session.add(file)
    db_session.flush()
    job = KbExtractJob(
        user_id=regular_user.id,
        file_id=file.id,
        provider="mineru",
        status="queued",
        created_at=datetime(2026, 8, 1, 0, 0, 0),
    )
    db_session.add(job)
    db_session.commit()
    monkeypatch.setattr(
        "messaging.kb_extract_consumer.run_extract_job",
        lambda *args: pytest.fail("old extract consumer must not execute MinerU without route"),
    )

    from messaging.kb_extract_consumer import _handle_job

    _handle_job(db_session, job.id, None)
    db_session.expire_all()
    route = (
        db_session.query(GpuSchedulerOutbox)
        .filter_by(job_kind="mineru", job_id=str(job.id))
        .one()
    )
    assert route.state == OUTBOX_QUEUED
    assert db_session.get(KbExtractJob, job.id).status == "queued"


def test_post_consumer_hands_over_without_executing(
    db_session, regular_user, monkeypatch
):
    monkeypatch.setattr("config.GPU_SCHEDULER_ENABLED", True)
    job, route = _seed_post_route(db_session, regular_user)
    monkeypatch.setattr(
        "messaging.kb_post_consumer.claim_kb_post_job",
        lambda *args: pytest.fail("old post consumer must not claim GPU work"),
    )
    from messaging.kb_post_consumer import _handle_job

    assert _handle_job(db_session, job.id, None) == (None, None)
    db_session.expire_all()
    assert db_session.get(GpuSchedulerOutbox, route.id).state == OUTBOX_QUEUED
    assert db_session.get(KbPostJob, job.id).status == "queued"


def test_post_consumer_handover_skips_published_route_with_active_lease(
    db_session, regular_user, monkeypatch
):
    """旧 post consumer 不得重开 scheduler 已取得租约的 published route：
    route 保持 published、lease 保持 active（P3）。"""
    monkeypatch.setattr("config.GPU_SCHEDULER_ENABLED", True)
    job, route = _seed_post_route(db_session, regular_user)
    lease = acquire_gpu_lease(
        db_session,
        gpu_id="0",
        owner_id=GPU_SCHEDULER_OWNER_ID,
        now=datetime(2026, 8, 1, 0, 0, 0),
    )
    lease.active_job_id = str(job.id)
    db_session.commit()

    from messaging.kb_post_consumer import _handle_job

    assert _handle_job(db_session, job.id, None) == (None, None)
    db_session.expire_all()
    assert db_session.get(GpuSchedulerOutbox, route.id).state == OUTBOX_PUBLISHED
    lease = db_session.query(GpuSchedulerLease).filter_by(gpu_id="0").one()
    assert lease.state == "active"
    assert lease.active_job_id == str(job.id)


def test_extract_consumer_retry_reopens_route_when_from_gpu_scheduler(
    db_session, regular_user, monkeypatch
):
    """GPU 调度模式下 extract 错误重试由 dispatch loop 重新发布：handler 必须
    在 retry 路径立即把 route 退回 queued（递增 handover_epoch），不能依赖旧
    consumer 交接（旧 consumer 见到活跃 lease 会跳过重开）。"""
    monkeypatch.setattr("config.GPU_SCHEDULER_ENABLED", True)
    job, route = _seed_extract_route(db_session, regular_user, state="published")
    monkeypatch.setattr(
        "messaging.kb_extract_consumer.run_extract_job",
        lambda db, current_job: setattr(current_job, "status", "error"),
    )
    monkeypatch.setattr(
        "messaging.kb_extract_consumer._publish_extract_notify_safe",
        lambda *args, **kwargs: None,
    )
    monkeypatch.setattr(
        "messaging.kb_extract_consumer.publish_kb_extract_retry",
        lambda *args, **kwargs: None,
    )

    from messaging.kb_extract_consumer import _handle_job

    claimed_id = _handle_job(db_session, job.id, None, _from_gpu_scheduler=True)
    assert claimed_id == route.id
    db_session.expire_all()
    route_row = db_session.get(GpuSchedulerOutbox, route.id)
    assert route_row.state == OUTBOX_QUEUED
    assert route_row.handover_epoch == 1
    assert db_session.get(KbExtractJob, job.id).status == "queued"


def test_post_consumer_retry_reopens_route_when_from_gpu_scheduler(
    db_session, regular_user, monkeypatch
):
    """GPU 调度模式下 post 错误重试同样由 dispatch loop 重新发布：retry 路径
    立即把 route 退回 queued（递增 handover_epoch）。"""
    monkeypatch.setattr("config.GPU_SCHEDULER_ENABLED", True)
    job, route = _seed_post_route(db_session, regular_user)
    monkeypatch.setattr(
        "messaging.kb_post_consumer.run_post_job",
        lambda db, current_job, **kwargs: setattr(current_job, "status", "error"),
    )
    monkeypatch.setattr(
        "messaging.kb_post_consumer.get_user_effective_dict",
        lambda *args, **kwargs: {},
    )
    monkeypatch.setattr(
        "messaging.kb_post_consumer.get_kb_post_max_attempts",
        lambda *args, **kwargs: 3,
    )
    monkeypatch.setattr(
        "messaging.kb_post_consumer._publish_post_notify_safe",
        lambda *args, **kwargs: None,
    )
    monkeypatch.setattr(
        "messaging.kb_post_consumer.publish_kb_post_retry",
        lambda *args, **kwargs: None,
    )

    from messaging.kb_post_consumer import _handle_job

    token, claimed_id = _handle_job(db_session, job.id, None, _from_gpu_scheduler=True)
    assert claimed_id == route.id
    db_session.expire_all()
    route_row = db_session.get(GpuSchedulerOutbox, route.id)
    assert route_row.state == OUTBOX_QUEUED
    assert route_row.handover_epoch == 1
    assert db_session.get(KbPostJob, job.id).status == "queued"


def test_post_consumer_backfills_raptor_route_when_gpu_enabled_and_route_missing(
    db_session, regular_user, monkeypatch
):
    monkeypatch.setattr("config.GPU_SCHEDULER_ENABLED", True)
    file = FileModel(
        filename="backfill-post.md",
        original_name="backfill-post.md",
        file_path="/tmp/backfill-post.md",
        file_size=100,
        mime_type="text/markdown",
        user_id=regular_user.id,
    )
    db_session.add(file)
    db_session.flush()
    job = KbPostJob(
        user_id=regular_user.id,
        file_id=file.id,
        status="queued",
        raptor_only=True,
        created_at=datetime(2026, 8, 1, 0, 0, 0),
    )
    db_session.add(job)
    db_session.commit()
    monkeypatch.setattr(
        "messaging.kb_post_consumer.claim_kb_post_job",
        lambda *args: pytest.fail("old post consumer must not claim GPU work without route"),
    )

    from messaging.kb_post_consumer import _handle_job

    assert _handle_job(db_session, job.id, None) == (None, None)
    db_session.expire_all()
    route = (
        db_session.query(GpuSchedulerOutbox)
        .filter_by(job_kind="raptor", job_id=str(job.id))
        .one()
    )
    assert route.state == OUTBOX_QUEUED
    assert db_session.get(KbPostJob, job.id).status == "queued"


def test_publish_extract_job_leaves_route_queued_when_gpu_enabled(
    db_session, regular_user, monkeypatch
):
    import services.kb_extract_service as extract_service

    job, route = _seed_extract_route(db_session, regular_user, state="queued")
    monkeypatch.setattr(extract_service, "GPU_SCHEDULER_ENABLED", True)
    monkeypatch.setattr(
        "messaging.kb_extract_publisher.publish_kb_extract_job",
        lambda *args: pytest.fail("GPU mode must not publish legacy extract queue"),
    )
    extract_service.publish_extract_job(db_session, regular_user.id, job.file_id, job.id)
    db_session.expire_all()
    assert db_session.get(GpuSchedulerOutbox, route.id).state == OUTBOX_QUEUED


def test_publish_extract_job_publishes_legacy_when_gpu_disabled(
    db_session, regular_user, monkeypatch
):
    import services.kb_extract_service as extract_service

    job, route = _seed_extract_route(db_session, regular_user, state="queued")
    published = []
    monkeypatch.setattr(
        "messaging.kb_extract_publisher.publish_kb_extract_job",
        lambda job_id: published.append(job_id),
    )
    extract_service.publish_extract_job(db_session, regular_user.id, job.file_id, job.id)
    db_session.expire_all()
    assert published == [job.id]
    assert db_session.get(GpuSchedulerOutbox, route.id).state == "published"


def test_extract_replay_skips_gpu_route_jobs_when_gpu_enabled(
    db_session, regular_user, monkeypatch
):
    """GPU 模式下旧拓扑 replay 不得为已建 durable route 的 mineru job 发消息，
    否则会与调度发布竞态（P3）；无 route 的 CPU job 仍正常 replay。"""
    import services.kb_extract_service as extract_service

    monkeypatch.setattr(extract_service, "GPU_SCHEDULER_ENABLED", True)
    gpu_file = FileModel(
        filename="replay-gpu.pdf",
        original_name="replay-gpu.pdf",
        file_path="/tmp/replay-gpu.pdf",
        file_size=10,
        mime_type="application/pdf",
        user_id=regular_user.id,
    )
    db_session.add(gpu_file)
    db_session.flush()
    gpu_job = KbExtractJob(
        user_id=regular_user.id,
        file_id=gpu_file.id,
        provider="mineru",
        status="queued",
        created_at=datetime(2026, 8, 1, 0, 0, 0),
    )
    db_session.add(gpu_job)
    db_session.flush()
    enqueue_gpu_route(
        db_session,
        job_kind="mineru",
        job_id=gpu_job.id,
        file_id=gpu_file.id,
        idempotency_key=f"mineru:{gpu_job.id}:0",
        payload={"job_id": gpu_job.id, "job_kind": "mineru", "file_id": gpu_file.id},
    )
    cpu_file = FileModel(
        filename="replay-cpu.pdf",
        original_name="replay-cpu.pdf",
        file_path="/tmp/replay-cpu.pdf",
        file_size=10,
        mime_type="application/pdf",
        user_id=regular_user.id,
    )
    db_session.add(cpu_file)
    db_session.flush()
    cpu_job = KbExtractJob(
        user_id=regular_user.id,
        file_id=cpu_file.id,
        provider="legacy",
        status="queued",
        created_at=datetime(2026, 8, 1, 0, 0, 0),
    )
    db_session.add(cpu_job)
    db_session.commit()

    published: list[int] = []
    monkeypatch.setattr(
        "messaging.kb_extract_publisher.publish_kb_extract_job",
        lambda job_id, connection=None: published.append(job_id),
    )
    monkeypatch.setattr(
        "messaging.kb_extract_queues.open_blocking_connection",
        lambda: MagicMock(),
    )
    n = extract_service.replay_queued_jobs(db_session, full=True)
    assert n == 1
    assert published == [cpu_job.id]


def test_post_replay_skips_gpu_route_jobs_when_gpu_enabled(
    db_session, regular_user, monkeypatch
):
    """GPU 模式下 post replay 同样跳过已有 durable raptor route 的 job。"""
    import services.kb_post_service as post_service

    monkeypatch.setattr(post_service, "GPU_SCHEDULER_ENABLED", True)
    job, _route = _seed_post_route(db_session, regular_user)
    cpu_file = FileModel(
        filename="replay-post-cpu.md",
        original_name="replay-post-cpu.md",
        file_path="/tmp/replay-post-cpu.md",
        file_size=100,
        mime_type="text/markdown",
        user_id=regular_user.id,
    )
    db_session.add(cpu_file)
    db_session.flush()
    cpu_job = KbPostJob(
        user_id=regular_user.id,
        file_id=cpu_file.id,
        status="queued",
        created_at=datetime(2026, 8, 1, 0, 0, 0),
    )
    db_session.add(cpu_job)
    db_session.commit()

    published: list[int] = []
    monkeypatch.setattr(
        "messaging.kb_post_publisher.publish_kb_post_job",
        lambda job_id, connection=None: published.append(job_id),
    )
    monkeypatch.setattr(
        "messaging.kb_post_queues.open_blocking_connection",
        lambda: MagicMock(),
    )
    n = post_service.replay_queued_post_jobs(db_session, full=True)
    assert n == 1
    assert published == [cpu_job.id]
    assert job.id not in published


def test_reopen_gpu_route_only_returns_published_to_queued(db_session):
    route = enqueue_gpu_route(
        db_session,
        job_kind="mineru",
        job_id=99,
        file_id=1,
        idempotency_key="mineru:99:0",
        payload={"job_id": 99},
    )
    assert reopen_gpu_route(db_session, outbox_id=route.id) is None  # queued
    publish_gpu_route(db_session, outbox_id=route.id, publish=lambda _payload: None)
    assert db_session.get(GpuSchedulerOutbox, route.id).state == "published"
    reopened = reopen_gpu_route(db_session, outbox_id=route.id)
    assert reopened is not None
    assert reopened.state == OUTBOX_QUEUED
    assert reopened.published_at is None

    publish_gpu_route(db_session, outbox_id=route.id, publish=lambda _payload: None)
    row = db_session.execute(
        select(GpuSchedulerOutbox).where(GpuSchedulerOutbox.id == route.id).with_for_update()
    ).scalar_one()
    row.state = OUTBOX_EXECUTING
    db_session.flush()
    assert reopen_gpu_route(db_session, outbox_id=route.id) is None
    ack_gpu_route(db_session, outbox_id=route.id)
    assert reopen_gpu_route(db_session, outbox_id=route.id) is None
