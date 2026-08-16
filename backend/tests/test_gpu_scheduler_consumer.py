"""164 §6：filex.gpu.* scheduler 消费端 claim/ack 边界。"""

from __future__ import annotations

import json
from types import SimpleNamespace
from datetime import datetime, timedelta

from sqlalchemy import update

from models.gpu_scheduler import GpuSchedulerOutbox
from models.kb_extract_job import KbExtractJob
from models.file import File as FileModel
from messaging import gpu_scheduler_consumer
from config import GPU_SCHEDULER_OWNER_ID
from services.gpu_scheduler_persistence import (
    OUTBOX_ACKED,
    OUTBOX_PUBLISHED,
    OUTBOX_QUEUED,
    ack_gpu_route,
    acquire_gpu_lease,
    claim_gpu_execution,
    enqueue_gpu_route,
    find_gpu_route,
    publish_gpu_route,
    reopen_gpu_route,
    release_gpu_execution,
)
from services.gpu_scheduler_dispatch import dispatch_next_gpu_route
from services.kb_extract_service import JOB_DONE, JOB_WAITING_GPU


class _FakeDb:
    def __init__(self) -> None:
        self.closed = False

    def commit(self) -> None:
        pass

    def rollback(self) -> None:
        pass

    def close(self) -> None:
        self.closed = True


def _payload(*, job_kind: str = "mineru", job_id: int = 42, handover_epoch: int = 0) -> dict:
    return {
        "job_id": job_id,
        "job_kind": job_kind,
        "file_id": 7,
        "idempotency_key": f"{job_kind}:{job_id}:0",
        "attempt": 0,
        "handover_epoch": handover_epoch,
    }


def _seed_route(db_session, *, job_kind: str = "mineru", job_id: int = 42, state: str = "published", handover_epoch: int = 0):
    route = enqueue_gpu_route(
        db_session,
        job_kind=job_kind,
        job_id=job_id,
        file_id=7,
        idempotency_key=f"{job_kind}:{job_id}:0",
        payload=_payload(job_kind=job_kind, job_id=job_id, handover_epoch=handover_epoch),
        handover_epoch=handover_epoch,
    )
    if state == "published":
        publish_gpu_route(db_session, outbox_id=route.id, publish=lambda _payload: None)
    elif state == OUTBOX_ACKED:
        publish_gpu_route(db_session, outbox_id=route.id, publish=lambda _payload: None)
        ack_gpu_route(db_session, outbox_id=route.id)
    return route


def test_consumer_executes_published_mineru_route(db_session, monkeypatch):
    calls = []

    def fake_extract_handler(db, job_id, conn, **kwargs):
        calls.append((job_id, conn))

    monkeypatch.setattr(
        "messaging.kb_extract_consumer._handle_job",
        fake_extract_handler,
    )
    route = _seed_route(db_session, job_kind="mineru", job_id=42)
    outcome, token = gpu_scheduler_consumer.handle_gpu_route_message(
        db_session,
        None,
        _payload(job_kind="mineru", job_id=42),
    )
    assert outcome == "executed"
    assert token is None
    assert calls == [(42, None)]
    assert db_session.get(GpuSchedulerOutbox, route.id).state == "published"  # 由 handler 负责 ack


def test_wait_for_dispatch_commit_returns_published_route(db_session):
    """dispatch 已 commit 时，等待函数返回 published，route 状态保持不变。"""
    route = _seed_route(db_session, job_kind="raptor", job_id=44, state="published")
    db_session.commit()
    state = gpu_scheduler_consumer._wait_for_dispatch_commit(
        db_session, job_kind="raptor", job_id="44"
    )
    assert state == OUTBOX_PUBLISHED
    assert db_session.get(GpuSchedulerOutbox, route.id).state == OUTBOX_PUBLISHED


def test_wait_for_dispatch_commit_returns_queued_after_rollback(db_session):
    """dispatch 已回滚时，等待函数返回 queued，等待下一 tick 重新发布。"""
    _seed_route(db_session, job_kind="raptor", job_id=45, state=OUTBOX_QUEUED)
    db_session.commit()
    state = gpu_scheduler_consumer._wait_for_dispatch_commit(
        db_session, job_kind="raptor", job_id="45"
    )
    assert state == OUTBOX_QUEUED


def test_on_message_waits_for_dispatch_commit_then_executes(monkeypatch):
    """早到消息先与 dispatch 事务串行化：commit 落地后重入 handler 正常执行，
    不再把已发布 route 退回 queued（WHB T-9 stale-lease 修复后暴露的
    publish-before-commit 竞态）。"""
    handled: list[int] = []

    def fake_handle(db, conn, payload):
        handled.append(payload["job_id"])
        if len(handled) == 1:
            return "waiting", None
        return "executed", None

    monkeypatch.setattr(gpu_scheduler_consumer, "handle_gpu_route_message", fake_handle)
    monkeypatch.setattr(gpu_scheduler_consumer, "require_license_or_wait", lambda db: True)
    monkeypatch.setattr(
        gpu_scheduler_consumer, "bind_consumer_keepalive_connection", lambda conn: None
    )
    monkeypatch.setattr(
        gpu_scheduler_consumer,
        "reset_consumer_keepalive_connection",
        lambda token: None,
    )
    monkeypatch.setattr(gpu_scheduler_consumer, "SessionLocal", lambda: _FakeDb())
    monkeypatch.setattr(
        gpu_scheduler_consumer,
        "_wait_for_dispatch_commit",
        lambda db, **kwargs: OUTBOX_PUBLISHED,
    )
    ch = _FakeChannel()
    gpu_scheduler_consumer._on_message(
        ch,
        SimpleNamespace(delivery_tag=1),
        None,
        json.dumps(_payload(job_kind="raptor", job_id=44)).encode(),
    )
    assert handled == [44, 44]
    assert ch.acked == [1]
    assert ch.nacked == []


def test_on_message_requeues_when_dispatch_rolled_back(monkeypatch):
    """dispatch 已回滚（route 仍 queued）时，waiting 消息走 bounded requeue，
      由 dispatch loop 下一 tick 重新发布。"""
    handled: list[int] = []

    def fake_handle(db, conn, payload):
        handled.append(payload["job_id"])
        return "waiting", None

    monkeypatch.setattr(gpu_scheduler_consumer, "handle_gpu_route_message", fake_handle)
    monkeypatch.setattr(gpu_scheduler_consumer, "require_license_or_wait", lambda db: True)
    monkeypatch.setattr(
        gpu_scheduler_consumer, "bind_consumer_keepalive_connection", lambda conn: None
    )
    monkeypatch.setattr(
        gpu_scheduler_consumer,
        "reset_consumer_keepalive_connection",
        lambda token: None,
    )
    monkeypatch.setattr(gpu_scheduler_consumer, "SessionLocal", lambda: _FakeDb())
    monkeypatch.setattr(
        gpu_scheduler_consumer,
        "_wait_for_dispatch_commit",
        lambda db, **kwargs: OUTBOX_QUEUED,
    )
    ch = _FakeChannel()
    gpu_scheduler_consumer._on_message(
        ch,
        SimpleNamespace(delivery_tag=1),
        None,
        json.dumps(_payload(job_kind="raptor", job_id=45)).encode(),
    )
    assert handled == [45]
    assert ch.acked == []
    assert ch.nacked == [(1, True)]


def test_consumer_executes_published_raptor_route(db_session, monkeypatch):
    def fake_post_handler(db, job_id, conn, **kwargs):
        return "TOKEN", None

    monkeypatch.setattr("messaging.kb_post_consumer._handle_job", fake_post_handler)
    _seed_route(db_session, job_kind="raptor", job_id=43)
    outcome, token = gpu_scheduler_consumer.handle_gpu_route_message(
        db_session,
        None,
        _payload(job_kind="raptor", job_id=43),
    )
    assert outcome == "executed"
    assert token == "TOKEN"


def test_consumer_acks_duplicate_of_finished_route(db_session, monkeypatch):
    called = []
    monkeypatch.setattr(
        "messaging.kb_extract_consumer._handle_job",
        lambda *args: called.append(args),
    )
    _seed_route(db_session, job_kind="mineru", job_id=42, state=OUTBOX_ACKED)
    outcome, _ = gpu_scheduler_consumer.handle_gpu_route_message(
        db_session,
        None,
        _payload(job_kind="mineru", job_id=42),
    )
    assert outcome == "acked"
    assert called == []


def test_consumer_rejects_stale_handover_epoch(db_session, monkeypatch):
    called = []
    monkeypatch.setattr(
        "messaging.kb_extract_consumer._handle_job",
        lambda *args: called.append(args),
    )
    _seed_route(db_session, job_kind="mineru", job_id=42, handover_epoch=1)
    outcome, _ = gpu_scheduler_consumer.handle_gpu_route_message(
        db_session,
        None,
        _payload(job_kind="mineru", job_id=42, handover_epoch=0),
    )
    assert outcome == "stale_epoch"
    assert called == []


def test_consumer_waits_for_queued_route(db_session, monkeypatch):
    called = []
    monkeypatch.setattr(
        "messaging.kb_extract_consumer._handle_job",
        lambda *args: called.append(args),
    )
    _seed_route(db_session, job_kind="mineru", job_id=42, state=OUTBOX_QUEUED)
    outcome, _ = gpu_scheduler_consumer.handle_gpu_route_message(
        db_session,
        None,
        _payload(job_kind="mineru", job_id=42),
    )
    assert outcome == "waiting"
    assert called == []


def test_consumer_releases_lease_after_execution_and_next_route_dispatches(
    db_session, regular_user, monkeypatch
):
    now = datetime(2026, 8, 1, 0, 0, 0)
    file = FileModel(
        filename="seq.pdf",
        original_name="seq.pdf",
        file_path="/tmp/seq.pdf",
        file_size=10,
        mime_type="application/pdf",
        user_id=regular_user.id,
    )
    db_session.add(file)
    db_session.flush()
    job1 = KbExtractJob(
        user_id=regular_user.id,
        file_id=file.id,
        provider="mineru",
        status="queued",
        created_at=now,
    )
    job2 = KbExtractJob(
        user_id=regular_user.id,
        file_id=file.id,
        provider="mineru",
        status="queued",
        created_at=now + timedelta(seconds=1),
    )
    db_session.add_all([job1, job2])
    db_session.flush()
    for job in (job1, job2):
        enqueue_gpu_route(
            db_session,
            job_kind="mineru",
            job_id=job.id,
            file_id=file.id,
            idempotency_key=f"mineru:{job.id}:0",
            payload=_payload(job_kind="mineru", job_id=job.id),
        )
    db_session.commit()

    def fake_handler(db, job_id, conn, **kwargs):
        route = find_gpu_route(db, job_kind="mineru", job_id=job_id)
        claim_gpu_execution(db, job_kind="mineru", job_id=job_id)
        db.get(KbExtractJob, job_id).status = "done"
        ack_gpu_route(db, outbox_id=route.id)
        db.commit()

    monkeypatch.setattr("messaging.kb_extract_consumer._handle_job", fake_handler)

    published_payloads = []
    first = dispatch_next_gpu_route(
        db_session,
        owner_id=GPU_SCHEDULER_OWNER_ID,
        gpu_id="0",
        now=now,
        publish=published_payloads.append,
    )
    assert first is not None
    assert first.candidate.job_id == str(job1.id)

    outcome, _ = gpu_scheduler_consumer.handle_gpu_route_message(
        db_session,
        None,
        published_payloads[0],
    )
    assert outcome == "executed"
    lease = db_session.query(type(first.lease)).filter_by(gpu_id="0").one()
    assert lease.state == "released"
    assert lease.active_job_id is None

    second = dispatch_next_gpu_route(
        db_session,
        owner_id=GPU_SCHEDULER_OWNER_ID,
        gpu_id="0",
        now=now + timedelta(seconds=2),
        publish=published_payloads.append,
    )
    assert second is not None
    assert second.candidate.job_id == str(job2.id)
    assert len(published_payloads) == 2


def test_consumer_defers_waiting_gpu_job_and_releases_lease(db_session, regular_user, monkeypatch):
    now = datetime(2026, 8, 1, 0, 0, 0)
    file = FileModel(
        filename="defer.pdf",
        original_name="defer.pdf",
        file_path="/tmp/defer.pdf",
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
        created_at=now,
    )
    db_session.add(job)
    db_session.flush()
    enqueue_gpu_route(
        db_session,
        job_kind="mineru",
        job_id=job.id,
        file_id=file.id,
        idempotency_key=f"mineru:{job.id}:0",
        payload=_payload(job_kind="mineru", job_id=job.id),
    )
    db_session.commit()

    def fake_defer_handler(db, job_id, conn, **kwargs):
        route = find_gpu_route(db, job_kind="mineru", job_id=job_id)
        claim_gpu_execution(db, job_kind="mineru", job_id=job_id)
        db.get(KbExtractJob, job_id).status = "waiting_gpu"
        release_gpu_execution(db, outbox_id=route.id)
        db.commit()
        return route.id

    monkeypatch.setattr("messaging.kb_extract_consumer._handle_job", fake_defer_handler)

    published_payloads = []
    result = dispatch_next_gpu_route(
        db_session,
        owner_id=GPU_SCHEDULER_OWNER_ID,
        gpu_id="0",
        now=now,
        publish=published_payloads.append,
    )
    assert result is not None
    outcome, _ = gpu_scheduler_consumer.handle_gpu_route_message(
        db_session,
        None,
        published_payloads[0],
    )
    assert outcome == "deferred"
    route = find_gpu_route(db_session, job_kind="mineru", job_id=job.id)
    assert route.state == OUTBOX_QUEUED
    lease = db_session.query(type(result.lease)).filter_by(gpu_id="0").one()
    assert lease.state == "released"
    assert lease.active_job_id is None
    # 本轮 dispatch 未实际执行（waiting_gpu defer）：批计数必须回退。
    assert lease.batch_size == 0
    assert lease.model_group is None
    assert lease.batch_started_at is None


def test_consumer_defer_rolls_back_persisted_batch_counter(
    db_session, regular_user, monkeypatch
):
    """同一 MINERU 驻留内已执行 1 个 job（batch=2 为当前轮派发计数）后，当前
    轮 defer：批计数从 2 回退到 1，而不是被无执行的 defer 轮次虚增。"""
    now = datetime(2026, 8, 1, 0, 0, 0)
    file = FileModel(
        filename="defer-batch.pdf",
        original_name="defer-batch.pdf",
        file_path="/tmp/defer-batch.pdf",
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
        created_at=now,
    )
    db_session.add(job)
    db_session.flush()
    enqueue_gpu_route(
        db_session,
        job_kind="mineru",
        job_id=job.id,
        file_id=file.id,
        idempotency_key=f"mineru:{job.id}:0",
        payload=_payload(job_kind="mineru", job_id=job.id),
    )
    route = find_gpu_route(db_session, job_kind="mineru", job_id=job.id)
    publish_gpu_route(db_session, outbox_id=route.id, publish=lambda _payload: None)
    lease = acquire_gpu_lease(
        db_session,
        gpu_id="0",
        owner_id=GPU_SCHEDULER_OWNER_ID,
        now=now,
    )
    lease.active_job_id = str(job.id)
    lease.model_group = "mineru"
    lease.batch_size = 2
    lease.batch_started_at = now
    db_session.commit()

    def fake_defer_handler(db, job_id, conn, **kwargs):
        claimed = claim_gpu_execution(db, job_kind="mineru", job_id=job_id)
        db.get(KbExtractJob, job_id).status = "waiting_gpu"
        release_gpu_execution(db, outbox_id=claimed.id)
        db.commit()
        return claimed.id

    monkeypatch.setattr("messaging.kb_extract_consumer._handle_job", fake_defer_handler)
    outcome, _ = gpu_scheduler_consumer.handle_gpu_route_message(
        db_session,
        None,
        _payload(job_kind="mineru", job_id=job.id),
    )
    assert outcome == "deferred"
    db_session.expire_all()
    lease = db_session.query(type(lease)).filter_by(gpu_id="0").one()
    assert lease.state == "released"
    assert lease.batch_size == 1
    assert lease.model_group == "mineru"
    assert lease.batch_started_at == now


def test_consumer_does_not_release_lease_when_route_still_executing(
    db_session, regular_user, monkeypatch
):
    now = datetime(2026, 8, 1, 0, 0, 0)
    file = FileModel(
        filename="executing.pdf",
        original_name="executing.pdf",
        file_path="/tmp/executing.pdf",
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
        status="running",
        created_at=now,
    )
    db_session.add(job)
    db_session.flush()
    enqueue_gpu_route(
        db_session,
        job_kind="mineru",
        job_id=job.id,
        file_id=file.id,
        idempotency_key=f"mineru:{job.id}:0",
        payload=_payload(job_kind="mineru", job_id=job.id),
    )
    route = find_gpu_route(db_session, job_kind="mineru", job_id=job.id)
    publish_gpu_route(db_session, outbox_id=route.id, publish=lambda _payload: None)
    lease = acquire_gpu_lease(
        db_session,
        gpu_id="0",
        owner_id=GPU_SCHEDULER_OWNER_ID,
        now=now,
    )
    lease.active_job_id = str(job.id)
    db_session.commit()

    def fake_handler(db, job_id, conn, **kwargs):
        # 模拟另一个执行轮已经 claim 且仍在执行：本轮 handler 无法 claim。
        row = find_gpu_route(db, job_kind="mineru", job_id=job_id)
        db.execute(
            update(GpuSchedulerOutbox)
            .where(GpuSchedulerOutbox.id == row.id)
            .values(state="executing")
        )
        db.commit()

    monkeypatch.setattr("messaging.kb_extract_consumer._handle_job", fake_handler)
    outcome, _ = gpu_scheduler_consumer.handle_gpu_route_message(
        db_session,
        None,
        _payload(job_kind="mineru", job_id=job.id),
    )
    assert outcome == "duplicate"
    db_session.expire_all()
    lease = db_session.query(type(lease)).filter_by(gpu_id="0").one()
    assert lease.state == "active"
    assert lease.active_job_id == str(job.id)


def test_consumer_releases_lease_when_executing_route_has_terminal_job(
    db_session, regular_user, monkeypatch
):
    """执行轮已提交终态但未及释放即崩溃：重投递消息看到 route executing +
    job 终态时必须释放 lease，否则 GPU 永久占用。"""
    now = datetime(2026, 8, 1, 0, 0, 0)
    file = FileModel(
        filename="executing-done.pdf",
        original_name="executing-done.pdf",
        file_path="/tmp/executing-done.pdf",
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
        status="done",
        created_at=now,
    )
    db_session.add(job)
    db_session.flush()
    enqueue_gpu_route(
        db_session,
        job_kind="mineru",
        job_id=job.id,
        file_id=file.id,
        idempotency_key=f"mineru:{job.id}:0",
        payload=_payload(job_kind="mineru", job_id=job.id),
    )
    route = find_gpu_route(db_session, job_kind="mineru", job_id=job.id)
    publish_gpu_route(db_session, outbox_id=route.id, publish=lambda _payload: None)
    lease = acquire_gpu_lease(
        db_session,
        gpu_id="0",
        owner_id=GPU_SCHEDULER_OWNER_ID,
        now=now,
    )
    lease.active_job_id = str(job.id)
    db_session.commit()

    def fake_handler(db, job_id, conn, **kwargs):
        row = find_gpu_route(db, job_kind="mineru", job_id=job_id)
        db.execute(
            update(GpuSchedulerOutbox)
            .where(GpuSchedulerOutbox.id == row.id)
            .values(state="executing")
        )
        db.commit()
        return None

    monkeypatch.setattr("messaging.kb_extract_consumer._handle_job", fake_handler)
    outcome, _ = gpu_scheduler_consumer.handle_gpu_route_message(
        db_session,
        None,
        _payload(job_kind="mineru", job_id=job.id),
    )
    assert outcome == "executed"
    db_session.expire_all()
    lease = db_session.query(type(lease)).filter_by(gpu_id="0").one()
    assert lease.state == "released"
    assert lease.active_job_id is None


def test_consumer_does_not_recover_another_workers_defer(db_session, regular_user, monkeypatch):
    """双 worker 竞态：worker B 未 claim（route 已由 worker A 置 executing、
    job 仍 queued）时，不得推断为本轮 defer 而释放 execution/lease。"""
    now = datetime(2026, 8, 1, 0, 0, 0)
    file = FileModel(
        filename="defer-race.pdf",
        original_name="defer-race.pdf",
        file_path="/tmp/defer-race.pdf",
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
        created_at=now,
    )
    db_session.add(job)
    db_session.flush()
    enqueue_gpu_route(
        db_session,
        job_kind="mineru",
        job_id=job.id,
        file_id=file.id,
        idempotency_key=f"mineru:{job.id}:0",
        payload=_payload(job_kind="mineru", job_id=job.id),
    )
    route = find_gpu_route(db_session, job_kind="mineru", job_id=job.id)
    publish_gpu_route(db_session, outbox_id=route.id, publish=lambda _payload: None)
    lease = acquire_gpu_lease(
        db_session,
        gpu_id="0",
        owner_id=GPU_SCHEDULER_OWNER_ID,
        now=now,
    )
    lease.active_job_id = str(job.id)
    db_session.commit()

    def fake_handler_that_cannot_claim(db, job_id, conn, **kwargs):
        # worker A 已 claim 且 job 尚未提交 running；本轮（B）claim 失败。
        row = find_gpu_route(db, job_kind="mineru", job_id=job_id)
        db.execute(
            update(GpuSchedulerOutbox)
            .where(GpuSchedulerOutbox.id == row.id)
            .values(state="executing")
        )
        db.commit()
        return None

    monkeypatch.setattr("messaging.kb_extract_consumer._handle_job", fake_handler_that_cannot_claim)
    outcome, _ = gpu_scheduler_consumer.handle_gpu_route_message(
        db_session,
        None,
        _payload(job_kind="mineru", job_id=job.id),
    )
    assert outcome == "duplicate"
    db_session.expire_all()
    route = find_gpu_route(db_session, job_kind="mineru", job_id=job.id)
    assert route.state == "executing"
    lease = db_session.query(type(lease)).filter_by(gpu_id="0").one()
    assert lease.state == "active"
    assert lease.active_job_id == str(job.id)


def test_consumer_reopens_executing_route_when_handler_defers_queued_job(
    db_session, regular_user, monkeypatch
):
    """extract handler 的 active_job_on_file defer 路径：job 保持 queued、
    route 停在 executing。消费端必须把 route 退回 queued 并释放 lease，
    否则 route 永卡 executing、lease 永驻 active。"""
    now = datetime(2026, 8, 1, 0, 0, 0)
    file = FileModel(
        filename="defer-queued.pdf",
        original_name="defer-queued.pdf",
        file_path="/tmp/defer-queued.pdf",
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
        created_at=now,
    )
    db_session.add(job)
    db_session.flush()
    enqueue_gpu_route(
        db_session,
        job_kind="mineru",
        job_id=job.id,
        file_id=file.id,
        idempotency_key=f"mineru:{job.id}:0",
        payload=_payload(job_kind="mineru", job_id=job.id),
    )
    route = find_gpu_route(db_session, job_kind="mineru", job_id=job.id)
    publish_gpu_route(db_session, outbox_id=route.id, publish=lambda _payload: None)
    lease = acquire_gpu_lease(
        db_session,
        gpu_id="0",
        owner_id=GPU_SCHEDULER_OWNER_ID,
        now=now,
    )
    lease.active_job_id = str(job.id)
    db_session.commit()

    def fake_defer_handler(db, job_id, conn, **kwargs):
        # 模拟 run_extract_job 的 defer 路径：claim 成功后 job 保持 queued，
        # handler 未 release execution 直接返回。
        claimed = claim_gpu_execution(db, job_kind="mineru", job_id=job_id)
        assert claimed is not None
        db.commit()
        return claimed.id

    monkeypatch.setattr("messaging.kb_extract_consumer._handle_job", fake_defer_handler)
    outcome, _ = gpu_scheduler_consumer.handle_gpu_route_message(
        db_session,
        None,
        _payload(job_kind="mineru", job_id=job.id),
    )
    assert outcome == "deferred"
    route = find_gpu_route(db_session, job_kind="mineru", job_id=job.id)
    assert route.state == OUTBOX_QUEUED
    db_session.expire_all()
    lease = db_session.query(type(lease)).filter_by(gpu_id="0").one()
    assert lease.state == "released"
    assert lease.active_job_id is None


def test_consumer_recovers_terminal_executing_route_on_redelivery(
    db_session, regular_user, monkeypatch
):
    """执行轮提交终态后、ack/释放前崩溃：重投递消息必须 ack route 并释放
    lease，否则 GPU 被心跳永久占用、job 不再被调度。"""
    now = datetime(2026, 8, 1, 0, 0, 0)
    file = FileModel(
        filename="redeliver-terminal.pdf",
        original_name="redeliver-terminal.pdf",
        file_path="/tmp/redeliver-terminal.pdf",
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
        status=JOB_DONE,
        created_at=now,
    )
    db_session.add(job)
    db_session.flush()
    enqueue_gpu_route(
        db_session,
        job_kind="mineru",
        job_id=job.id,
        file_id=file.id,
        idempotency_key=f"mineru:{job.id}:0",
        payload=_payload(job_kind="mineru", job_id=job.id),
    )
    route = find_gpu_route(db_session, job_kind="mineru", job_id=job.id)
    publish_gpu_route(db_session, outbox_id=route.id, publish=lambda _payload: None)
    claim_gpu_execution(db_session, job_kind="mineru", job_id=job.id)
    lease = acquire_gpu_lease(
        db_session,
        gpu_id="0",
        owner_id=GPU_SCHEDULER_OWNER_ID,
        now=now,
    )
    lease.active_job_id = str(job.id)
    db_session.commit()

    called = []
    monkeypatch.setattr(
        "messaging.kb_extract_consumer._handle_job",
        lambda *args: called.append(args),
    )
    outcome, token = gpu_scheduler_consumer.handle_gpu_route_message(
        db_session,
        None,
        _payload(job_kind="mineru", job_id=job.id),
    )
    assert outcome == "executed"
    assert token is None
    assert called == []
    db_session.expire_all()
    route = find_gpu_route(db_session, job_kind="mineru", job_id=job.id)
    assert route.state == OUTBOX_ACKED
    lease = db_session.query(type(lease)).filter_by(gpu_id="0").one()
    assert lease.state == "released"
    assert lease.active_job_id is None


def test_consumer_completes_defer_for_waiting_gpu_executing_route_on_redelivery(
    db_session, regular_user, monkeypatch
):
    """执行轮在 defer 收尾前崩溃：重投递消息补完 reopen + 释放 lease，并
    递增 handover_epoch，旧一代消息后续被 stale_epoch 拒绝。"""
    now = datetime(2026, 8, 1, 0, 0, 0)
    file = FileModel(
        filename="redeliver-defer.pdf",
        original_name="redeliver-defer.pdf",
        file_path="/tmp/redeliver-defer.pdf",
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
        status=JOB_WAITING_GPU,
        created_at=now,
    )
    db_session.add(job)
    db_session.flush()
    enqueue_gpu_route(
        db_session,
        job_kind="mineru",
        job_id=job.id,
        file_id=file.id,
        idempotency_key=f"mineru:{job.id}:0",
        payload=_payload(job_kind="mineru", job_id=job.id),
    )
    route = find_gpu_route(db_session, job_kind="mineru", job_id=job.id)
    publish_gpu_route(db_session, outbox_id=route.id, publish=lambda _payload: None)
    claim_gpu_execution(db_session, job_kind="mineru", job_id=job.id)
    lease = acquire_gpu_lease(
        db_session,
        gpu_id="0",
        owner_id=GPU_SCHEDULER_OWNER_ID,
        now=now,
    )
    lease.active_job_id = str(job.id)
    db_session.commit()

    called = []
    monkeypatch.setattr(
        "messaging.kb_extract_consumer._handle_job",
        lambda *args: called.append(args),
    )
    outcome, _ = gpu_scheduler_consumer.handle_gpu_route_message(
        db_session,
        None,
        _payload(job_kind="mineru", job_id=job.id),
    )
    assert outcome == "deferred"
    assert called == []
    db_session.expire_all()
    route = find_gpu_route(db_session, job_kind="mineru", job_id=job.id)
    assert route.state == OUTBOX_QUEUED
    assert route.handover_epoch == 1
    lease = db_session.query(type(lease)).filter_by(gpu_id="0").one()
    assert lease.state == "released"
    assert lease.active_job_id is None


def test_consumer_rejects_message_from_previous_handover_generation(
    db_session, monkeypatch
):
    """route reopen 后递增 handover_epoch：上一代已发布消息必须被拒绝，避免
    旧消息绕过新租约 claim 同一 job。"""
    called = []
    monkeypatch.setattr(
        "messaging.kb_extract_consumer._handle_job",
        lambda *args: called.append(args),
    )
    _seed_route(db_session, job_kind="mineru", job_id=42)
    route = find_gpu_route(db_session, job_kind="mineru", job_id=42)
    reopen_gpu_route(db_session, outbox_id=route.id)
    db_session.commit()
    outcome, _ = gpu_scheduler_consumer.handle_gpu_route_message(
        db_session,
        None,
        _payload(job_kind="mineru", job_id=42, handover_epoch=0),
    )
    assert outcome == "stale_epoch"
    assert called == []


def test_consumer_backfills_historical_route(db_session, monkeypatch):
    called = []
    monkeypatch.setattr(
        "messaging.kb_extract_consumer._handle_job",
        lambda *args: called.append(args),
    )
    outcome, _ = gpu_scheduler_consumer.handle_gpu_route_message(
        db_session,
        None,
        _payload(job_kind="mineru", job_id=42),
    )
    assert outcome == "backfilled"
    route = db_session.query(GpuSchedulerOutbox).filter_by(job_id="42").one()
    assert route.state == OUTBOX_QUEUED
    assert route.idempotency_key == "mineru:42:0"
    assert called == []


class _FakeChannel:
    def __init__(self) -> None:
        self.acked: list[int] = []
        self.nacked: list[tuple[int, bool]] = []
        self.connection = None

    def basic_ack(self, delivery_tag: int, **_kwargs) -> None:
        self.acked.append(delivery_tag)

    def basic_nack(self, delivery_tag: int, requeue: bool = False, **_kwargs) -> None:
        self.nacked.append((delivery_tag, requeue))


def test_on_message_acks_invalid_body_without_db(db_session, monkeypatch):
    monkeypatch.setattr(gpu_scheduler_consumer, "SessionLocal", lambda: db_session)
    channel = _FakeChannel()
    gpu_scheduler_consumer._on_message(
        channel,
        SimpleNamespace(delivery_tag=1),
        None,
        b"not-json",
    )
    assert channel.acked == [1]
    assert db_session.query(GpuSchedulerOutbox).count() == 0


def test_on_message_handles_valid_route_and_acks(db_session, monkeypatch):
    handled = []
    monkeypatch.setattr(gpu_scheduler_consumer, "SessionLocal", lambda: db_session)
    monkeypatch.setattr(gpu_scheduler_consumer, "require_license_or_wait", lambda db: True)
    monkeypatch.setattr(
        "messaging.kb_extract_consumer._handle_job",
        lambda db, job_id, conn, **kwargs: handled.append(job_id),
    )
    _seed_route(db_session, job_kind="mineru", job_id=42)
    channel = _FakeChannel()
    gpu_scheduler_consumer._on_message(
        channel,
        SimpleNamespace(delivery_tag=1),
        None,
        json.dumps(_payload(job_kind="mineru", job_id=42)).encode(),
    )
    assert handled == [42]
    assert channel.acked == [1]


def test_on_message_requeues_waiting_route_bounded(db_session, monkeypatch):
    monkeypatch.setattr(gpu_scheduler_consumer, "SessionLocal", lambda: db_session)
    monkeypatch.setattr(gpu_scheduler_consumer, "require_license_or_wait", lambda db: True)
    _seed_route(db_session, job_kind="mineru", job_id=777, state=OUTBOX_QUEUED)
    channel = _FakeChannel()
    body = json.dumps(_payload(job_kind="mineru", job_id=777)).encode()
    for _ in range(gpu_scheduler_consumer.GPU_ROUTE_WAITING_MAX_REQUEUE - 1):
        gpu_scheduler_consumer._on_message(
            channel,
            SimpleNamespace(delivery_tag=1),
            None,
            body,
        )
    assert len(channel.nacked) == gpu_scheduler_consumer.GPU_ROUTE_WAITING_MAX_REQUEUE - 1
    assert all(requeue for _tag, requeue in channel.nacked)
    assert channel.acked == []

    # 超过有界重试上限后丢弃：route 已持久化，dispatch loop 会重新发布。
    gpu_scheduler_consumer._on_message(
        channel,
        SimpleNamespace(delivery_tag=1),
        None,
        body,
    )
    assert channel.acked == [1]
    assert db_session.query(GpuSchedulerOutbox).filter_by(job_id="777").one().state == OUTBOX_QUEUED


def test_reconcile_waiting_route_before_drop_reopens_published_route(
    db_session, regular_user
):
    """丢弃 waiting 消息前，若 dispatch 已把 route 提交为 published，必须收回
    queued 并释放 lease，避免消息被丢后 GPU 永久卡死。"""
    now = datetime(2026, 8, 1, 0, 0, 0)
    file = FileModel(
        filename="drop-published.pdf",
        original_name="drop-published.pdf",
        file_path="/tmp/drop-published.pdf",
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
        created_at=now,
    )
    db_session.add(job)
    db_session.flush()
    enqueue_gpu_route(
        db_session,
        job_kind="mineru",
        job_id=job.id,
        file_id=file.id,
        idempotency_key=f"mineru:{job.id}:0",
        payload=_payload(job_kind="mineru", job_id=job.id),
    )
    route = find_gpu_route(db_session, job_kind="mineru", job_id=job.id)
    publish_gpu_route(db_session, outbox_id=route.id, publish=lambda _payload: None)
    lease = acquire_gpu_lease(
        db_session,
        gpu_id="0",
        owner_id=GPU_SCHEDULER_OWNER_ID,
        now=now,
    )
    lease.active_job_id = str(job.id)
    db_session.commit()

    gpu_scheduler_consumer._reconcile_waiting_route_before_drop(
        db_session,
        job_kind="mineru",
        job_id=str(job.id),
    )
    db_session.expire_all()
    route = find_gpu_route(db_session, job_kind="mineru", job_id=job.id)
    assert route.state == OUTBOX_QUEUED
    lease = db_session.query(type(lease)).filter_by(gpu_id="0").one()
    assert lease.state == "released"
    assert lease.active_job_id is None


def test_reconcile_waiting_route_before_drop_keeps_queued_route(
    db_session, regular_user
):
    """dispatch 已回滚（route 仍 queued）时，drop 前不改变状态，dispatch loop
    会重新发布。"""
    now = datetime(2026, 8, 1, 0, 0, 0)
    file = FileModel(
        filename="drop-queued.pdf",
        original_name="drop-queued.pdf",
        file_path="/tmp/drop-queued.pdf",
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
        created_at=now,
    )
    db_session.add(job)
    db_session.flush()
    enqueue_gpu_route(
        db_session,
        job_kind="mineru",
        job_id=job.id,
        file_id=file.id,
        idempotency_key=f"mineru:{job.id}:0",
        payload=_payload(job_kind="mineru", job_id=job.id),
    )
    db_session.commit()

    gpu_scheduler_consumer._reconcile_waiting_route_before_drop(
        db_session,
        job_kind="mineru",
        job_id=str(job.id),
    )
    db_session.expire_all()
    route = find_gpu_route(db_session, job_kind="mineru", job_id=job.id)
    assert route.state == OUTBOX_QUEUED
    assert db_session.query(GpuSchedulerOutbox).count() == 1
