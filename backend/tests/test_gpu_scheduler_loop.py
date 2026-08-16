from datetime import datetime, timedelta

import pytest

from models.gpu_scheduler import GpuSchedulerLease, GpuSchedulerOutbox
from models.kb_extract_job import KbExtractJob
from models.kb_post_job import KbPostJob
from models.file import File as FileModel
from services import gpu_scheduler_dispatch, gpu_scheduler_loop
from services.gpu_scheduler_loop import GpuSchedulerLoop
from services.gpu_scheduler_persistence import (
    ack_gpu_route,
    acquire_gpu_lease,
    claim_gpu_execution,
    enqueue_gpu_route,
    publish_gpu_route,
    record_release_ack,
)


def test_loop_default_publishers_emit_gpu_route_messages(monkeypatch):
    import messaging.gpu_queues as gpu_queues
    from services import gpu_scheduler_loop

    calls = []
    monkeypatch.setattr(
        gpu_queues,
        "publish_gpu_route_message",
        lambda kind, payload: calls.append((kind, dict(payload))),
    )
    gpu_scheduler_loop._mineru_publisher({"job_id": 42})
    gpu_scheduler_loop._raptor_publisher(
        {
            "job_id": 43,
            "file_id": 7,
            "idempotency_key": "raptor:43:0",
            "attempt": 1,
            "handover_epoch": 1,
        }
    )
    mineru_kind, mineru_payload = calls[0]
    assert mineru_kind == "mineru"
    assert mineru_payload["idempotency_key"] == "mineru:42:0"
    assert mineru_payload["job_kind"] == "mineru"
    assert mineru_payload["handover_epoch"] == 0
    raptor_kind, raptor_payload = calls[1]
    assert raptor_kind == "raptor"
    assert raptor_payload["idempotency_key"] == "raptor:43:0"
    assert raptor_payload["handover_epoch"] == 1


def _seed_mineru_job(db_session, regular_user, *, created_at, status="queued") -> int:
    file = FileModel(
        filename="scheduler-loop.pdf",
        original_name="scheduler-loop.pdf",
        file_path="/tmp/scheduler-loop.pdf",
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
        status=status,
        created_at=created_at,
    )
    db_session.add(job)
    db_session.flush()
    db_session.add(
        GpuSchedulerOutbox(
            job_kind="mineru",
            job_id=str(job.id),
            file_id=file.id,
            idempotency_key=f"mineru:{job.id}:0",
            payload={"job_id": job.id},
            state="queued",
        )
    )
    db_session.flush()
    return job.id


def _seed_executing_mineru_route(
    db_session, regular_user, *, status: str, now: datetime
) -> tuple[int, int]:
    file = FileModel(
        filename="scheduler-loop-executing.pdf",
        original_name="scheduler-loop-executing.pdf",
        file_path="/tmp/scheduler-loop-executing.pdf",
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
        status=status,
        created_at=now,
    )
    db_session.add(job)
    db_session.flush()
    route = enqueue_gpu_route(
        db_session,
        job_kind="mineru",
        job_id=job.id,
        file_id=file.id,
        idempotency_key=f"mineru:{job.id}:0",
        payload={"job_id": job.id, "job_kind": "mineru", "file_id": file.id},
    )
    publish_gpu_route(db_session, outbox_id=route.id, publish=lambda _payload: None)
    claim_gpu_execution(db_session, job_kind="mineru", job_id=job.id)
    lease = acquire_gpu_lease(
        db_session,
        gpu_id="0",
        owner_id="scheduler-a",
        now=now,
    )
    lease.active_job_id = str(job.id)
    db_session.commit()
    return job.id, route.id


def _seed_waiting_raptor_job(
    db_session, regular_user, *, created_at, route_state: str = "queued"
) -> tuple[int, int]:
    file = FileModel(
        filename="scheduler-loop-raptor.pdf",
        original_name="scheduler-loop-raptor.pdf",
        file_path="/tmp/scheduler-loop-raptor.pdf",
        file_size=10,
        mime_type="application/pdf",
        user_id=regular_user.id,
    )
    db_session.add(file)
    db_session.flush()
    post = KbPostJob(
        user_id=regular_user.id,
        file_id=file.id,
        status="waiting_gpu",
        created_at=created_at,
    )
    db_session.add(post)
    db_session.flush()
    route = enqueue_gpu_route(
        db_session,
        job_kind="raptor",
        job_id=post.id,
        file_id=file.id,
        idempotency_key=f"raptor:{post.id}:0",
        payload={"job_id": post.id, "job_kind": "raptor", "file_id": file.id},
    )
    if route_state == "published":
        publish_gpu_route(db_session, outbox_id=route.id, publish=lambda _payload: None)
    db_session.commit()
    return post.id, route.id


def _seed_executing_raptor_route(
    db_session, regular_user, *, status: str, now: datetime
) -> tuple[int, int]:
    file = FileModel(
        filename="scheduler-loop-raptor-executing.pdf",
        original_name="scheduler-loop-raptor-executing.pdf",
        file_path="/tmp/scheduler-loop-raptor-executing.pdf",
        file_size=10,
        mime_type="application/pdf",
        user_id=regular_user.id,
    )
    db_session.add(file)
    db_session.flush()
    post = KbPostJob(
        user_id=regular_user.id,
        file_id=file.id,
        status=status,
        created_at=now,
    )
    db_session.add(post)
    db_session.flush()
    route = enqueue_gpu_route(
        db_session,
        job_kind="raptor",
        job_id=post.id,
        file_id=file.id,
        idempotency_key=f"raptor:{post.id}:0",
        payload={"job_id": post.id, "job_kind": "raptor", "file_id": file.id},
    )
    publish_gpu_route(db_session, outbox_id=route.id, publish=lambda _payload: None)
    claim_gpu_execution(db_session, job_kind="raptor", job_id=post.id)
    lease = acquire_gpu_lease(
        db_session,
        gpu_id="0",
        owner_id="scheduler-a",
        now=now,
    )
    lease.active_job_id = str(post.id)
    db_session.commit()
    return post.id, route.id


def test_loop_recovers_executing_route_when_job_waiting_gpu(db_session, regular_user):
    """执行轮以 waiting_gpu 结束 defer 后 consumer 崩溃：调度循环把 route
    退回 queued 并释放 lease，等待重新发布，避免 gpu_id 卡死。"""
    now = datetime(2026, 8, 1, 0, 0, 0)
    _job_id, route_id = _seed_executing_mineru_route(
        db_session, regular_user, status="waiting_gpu", now=now
    )
    loop = GpuSchedulerLoop(
        owner_id="scheduler-a",
        gpu_ids=["0"],
        tick_seconds=5,
        ttl_seconds=30,
        publishers={"mineru": lambda _payload: None, "raptor": lambda _payload: None},
    )

    assert loop._recover_stuck_executing_routes(db_session, now=now) == 1
    db_session.expire_all()
    route = db_session.get(GpuSchedulerOutbox, route_id)
    assert route.state == "queued"
    assert route.handover_epoch == 1
    lease = db_session.query(GpuSchedulerLease).filter_by(gpu_id="0").one()
    assert lease.state == "released"
    assert lease.active_job_id is None


def test_loop_leaves_executing_route_when_job_queued(db_session, regular_user):
    """job queued 可能是「claim 后、置 running 前」的瞬态窗口，调度循环不得
    回收，否则会释放正被使用的 lease 导致并发 GPU 执行。"""
    now = datetime(2026, 8, 1, 0, 0, 0)
    _job_id, route_id = _seed_executing_mineru_route(
        db_session, regular_user, status="queued", now=now
    )
    loop = GpuSchedulerLoop(
        owner_id="scheduler-a",
        gpu_ids=["0"],
        tick_seconds=5,
        ttl_seconds=30,
        publishers={"mineru": lambda _payload: None, "raptor": lambda _payload: None},
    )

    assert loop._recover_stuck_executing_routes(db_session, now=now) == 0
    db_session.expire_all()
    route = db_session.get(GpuSchedulerOutbox, route_id)
    assert route.state == "executing"
    lease = db_session.query(GpuSchedulerLease).filter_by(gpu_id="0").one()
    assert lease.state == "active"


def test_loop_acks_executing_route_when_job_terminal(db_session, regular_user):
    """consumer 在 job 终态后崩溃：executing route 由调度循环 ack 并释放
    lease，避免 GPU 被永久占用。"""
    now = datetime(2026, 8, 1, 0, 0, 0)
    _job_id, route_id = _seed_executing_mineru_route(
        db_session, regular_user, status="done", now=now
    )
    loop = GpuSchedulerLoop(
        owner_id="scheduler-a",
        gpu_ids=["0"],
        tick_seconds=5,
        ttl_seconds=30,
        publishers={"mineru": lambda _payload: None, "raptor": lambda _payload: None},
    )

    assert loop._recover_stuck_executing_routes(db_session, now=now) == 1
    db_session.expire_all()
    route = db_session.get(GpuSchedulerOutbox, route_id)
    assert route.state == "acked"
    lease = db_session.query(GpuSchedulerLease).filter_by(gpu_id="0").one()
    assert lease.state == "released"
    assert lease.active_job_id is None


def test_loop_leaves_executing_route_when_job_running(db_session, regular_user):
    """job running 视为执行轮仍存活：不得回收 route/lease，避免并发 GPU 执行。"""
    now = datetime(2026, 8, 1, 0, 0, 0)
    _job_id, route_id = _seed_executing_mineru_route(
        db_session, regular_user, status="running", now=now
    )
    loop = GpuSchedulerLoop(
        owner_id="scheduler-a",
        gpu_ids=["0"],
        tick_seconds=5,
        ttl_seconds=30,
        publishers={"mineru": lambda _payload: None, "raptor": lambda _payload: None},
    )

    assert loop._recover_stuck_executing_routes(db_session, now=now) == 0
    db_session.expire_all()
    route = db_session.get(GpuSchedulerOutbox, route_id)
    assert route.state == "executing"
    lease = db_session.query(GpuSchedulerLease).filter_by(gpu_id="0").one()
    assert lease.state == "active"


def test_loop_dispatches_one_route_per_gpu_and_heartbeats(db_session, regular_user):
    now = datetime(2026, 8, 1, 0, 0, 0)
    job_id = _seed_mineru_job(db_session, regular_user, created_at=now)
    published_payloads = []
    loop = GpuSchedulerLoop(
        owner_id="scheduler-a",
        gpu_ids=["0"],
        tick_seconds=5,
        ttl_seconds=30,
        publishers={"mineru": published_payloads.append, "raptor": lambda _payload: None},
    )

    assert loop.run_once(db_session, now=now) == 1
    assert published_payloads == [
        {"job_id": job_id, "attempt": 1, "handover_epoch": 0}
    ]
    lease = db_session.query(GpuSchedulerLease).filter_by(gpu_id="0").one()
    assert lease.state == "active"
    assert lease.active_job_id == str(job_id)
    assert lease.lease_expires_at == now + timedelta(seconds=30)

    # Second tick: lease is busy for the same owner, nothing new is dispatched,
    # but the owned lease is heartbeated forward.
    later = now + timedelta(seconds=5)
    assert loop.run_once(db_session, now=later) == 0
    db_session.expire_all()
    lease = db_session.query(GpuSchedulerLease).filter_by(gpu_id="0").one()
    assert lease.state == "active"
    assert lease.active_job_id == str(job_id)
    assert lease.lease_expires_at == later + timedelta(seconds=30)


def test_loop_selects_publisher_by_job_kind(db_session, regular_user):
    now = datetime(2026, 8, 1, 0, 0, 0)
    file = FileModel(
        filename="scheduler-loop-raptor.pdf",
        original_name="scheduler-loop-raptor.pdf",
        file_path="/tmp/scheduler-loop-raptor.pdf",
        file_size=10,
        mime_type="application/pdf",
        user_id=regular_user.id,
    )
    db_session.add(file)
    db_session.flush()
    post = KbPostJob(
        user_id=regular_user.id,
        file_id=file.id,
        status="queued",
        created_at=now - timedelta(seconds=901),
    )
    db_session.add(post)
    db_session.flush()
    db_session.add(
        GpuSchedulerOutbox(
            job_kind="raptor",
            job_id=str(post.id),
            file_id=file.id,
            idempotency_key=f"raptor:{post.id}:0",
            payload={"job_id": post.id},
            state="queued",
        )
    )
    db_session.flush()

    published_payloads = []
    loop = GpuSchedulerLoop(
        owner_id="scheduler-a",
        gpu_ids=["0"],
        tick_seconds=5,
        ttl_seconds=30,
        publishers={
            "mineru": lambda _payload: pytest.fail("mineru publisher must not run"),
            "raptor": published_payloads.append,
        },
    )
    assert loop.run_once(db_session, now=now) == 1
    assert published_payloads == [
        {"job_id": post.id, "attempt": 1, "handover_epoch": 0}
    ]
    published_route = db_session.query(GpuSchedulerOutbox).filter_by(state="published").one()
    assert published_route.job_kind == "raptor"


def test_loop_does_nothing_without_candidates(db_session, regular_user):
    loop = GpuSchedulerLoop(
        owner_id="scheduler-a",
        gpu_ids=["0"],
        tick_seconds=5,
        ttl_seconds=30,
        publishers={"mineru": lambda _payload: pytest.fail("must not publish"), "raptor": lambda _payload: None},
    )
    assert loop.run_once(db_session, now=datetime(2026, 8, 1, 0, 0, 0)) == 0


def test_loop_rejects_invalid_configuration():
    with pytest.raises(ValueError, match="owner_id"):
        GpuSchedulerLoop(owner_id="", gpu_ids=["0"])
    with pytest.raises(ValueError, match="gpu_ids"):
        GpuSchedulerLoop(owner_id="scheduler-a", gpu_ids=[])
    with pytest.raises(ValueError, match="tick_seconds"):
        GpuSchedulerLoop(owner_id="scheduler-a", gpu_ids=["0"], tick_seconds=0)
    with pytest.raises(ValueError, match="ttl_seconds"):
        GpuSchedulerLoop(owner_id="scheduler-a", gpu_ids=["0"], ttl_seconds=0)
    with pytest.raises(ValueError, match="publishers"):
        GpuSchedulerLoop(
            owner_id="scheduler-a",
            gpu_ids=["0"],
            publishers={"mineru": lambda _payload: None},
        )


def test_dispatch_rejects_missing_publisher_before_acquiring_lease(
    db_session, regular_user, monkeypatch
):
    now = datetime(2026, 8, 1, 0, 0, 0)
    job_id = _seed_mineru_job(db_session, regular_user, created_at=now)
    with pytest.raises(ValueError, match="no publisher"):
        gpu_scheduler_dispatch.dispatch_next_gpu_route(
            db_session,
            owner_id="scheduler-a",
            gpu_id="0",
            now=now,
            publish=None,
            publishers={"raptor": lambda _payload: None},
        )
    assert db_session.query(GpuSchedulerLease).filter_by(gpu_id="0").count() == 0
    assert db_session.query(GpuSchedulerOutbox).filter_by(job_id=str(job_id)).one().state == "queued"


def test_loop_does_not_heartbeat_taken_over_lease(db_session, regular_user):
    now = datetime(2026, 8, 1, 0, 0, 0)
    _seed_mineru_job(db_session, regular_user, created_at=now)
    loop = GpuSchedulerLoop(
        owner_id="scheduler-a",
        gpu_ids=["0"],
        tick_seconds=5,
        ttl_seconds=30,
        publishers={"mineru": lambda _payload: None, "raptor": lambda _payload: None},
    )
    assert loop.run_once(db_session, now=now) == 1
    first = db_session.query(GpuSchedulerLease).filter_by(gpu_id="0").one()
    record_release_ack(
        db_session,
        first,
        owner_id="scheduler-a",
        fencing_token=first.fencing_token,
        now=now,
    )
    db_session.commit()
    takeover = acquire_gpu_lease(
        db_session,
        gpu_id="0",
        owner_id="scheduler-b",
        now=now + timedelta(seconds=1),
    )
    assert takeover is not None
    takeover_token = takeover.fencing_token
    db_session.commit()

    assert loop.run_once(db_session, now=now + timedelta(seconds=10)) == 0
    db_session.expire_all()
    lease = db_session.query(GpuSchedulerLease).filter_by(gpu_id="0").one()
    assert lease.owner_id == "scheduler-b"
    assert lease.fencing_token == takeover_token


def test_loop_isolates_single_heartbeat_failure(db_session, regular_user, monkeypatch):
    now = datetime(2026, 8, 1, 0, 0, 0)
    loop = GpuSchedulerLoop(
        owner_id="scheduler-a",
        gpu_ids=["0", "1"],
        tick_seconds=5,
        ttl_seconds=30,
        publishers={"mineru": lambda _payload: None, "raptor": lambda _payload: None},
    )
    leases = {}
    for gpu_id in ("0", "1"):
        leases[gpu_id] = acquire_gpu_lease(
            db_session,
            gpu_id=gpu_id,
            owner_id="scheduler-a",
            now=now,
        )
    db_session.commit()
    # 本进程已通过 dispatch/恢复持有这两条租约（fencing token 记录在进程内）。
    loop._owned_fencing_tokens = {
        gpu_id: lease.fencing_token for gpu_id, lease in leases.items()
    }

    real_heartbeat = gpu_scheduler_loop.heartbeat_gpu_lease_if_owned

    def flaky_heartbeat(db, **kwargs):
        if kwargs["gpu_id"] == "0":
            raise RuntimeError("db poisoned")
        return real_heartbeat(db, **kwargs)

    monkeypatch.setattr(gpu_scheduler_loop, "heartbeat_gpu_lease_if_owned", flaky_heartbeat)
    later = now + timedelta(seconds=10)
    assert loop.run_once(db_session, now=later) == 0
    db_session.expire_all()
    lease0 = db_session.query(GpuSchedulerLease).filter_by(gpu_id="0").one()
    lease1 = db_session.query(GpuSchedulerLease).filter_by(gpu_id="1").one()
    assert lease0.lease_expires_at == now + timedelta(seconds=60)
    assert lease1.lease_expires_at == later + timedelta(seconds=30)


def test_loop_recovers_executing_running_route_after_watchdog_confirmations(
    db_session, regular_user, monkeypatch
):
    """执行中 lease 心跳停止 ≠ 可回收：必须先由 watchdog 连续两次（间隔
    5s）确认 GPU 进程为空，才把 executing route + running job 恢复为
    job queued + route queued + lease released。"""
    now = datetime(2026, 8, 1, 0, 0, 0)
    job_id, route_id = _seed_executing_mineru_route(
        db_session, regular_user, status="running", now=now
    )
    lease = db_session.query(GpuSchedulerLease).filter_by(gpu_id="0").one()
    lease.heartbeat_at = now - timedelta(seconds=121)
    lease.lease_expires_at = now - timedelta(seconds=91)
    db_session.commit()
    monkeypatch.setattr(
        gpu_scheduler_loop, "gpu_round_idle", lambda job_kind, lease: True
    )
    loop = GpuSchedulerLoop(
        owner_id="scheduler-a",
        gpu_ids=["0"],
        tick_seconds=5,
        ttl_seconds=30,
        publishers={"mineru": lambda _payload: None, "raptor": lambda _payload: None},
    )

    # 第一次空采样：记录确认 #1，尚不可回收（liveness 丢失只是前提）。
    assert loop._recover_stuck_executing_routes(db_session, now=now) == 0
    db_session.expire_all()
    lease = db_session.query(GpuSchedulerLease).filter_by(gpu_id="0").one()
    assert lease.state == "active"
    assert lease.watchdog_empty_confirmations == 1
    assert lease.last_watchdog_at == now
    assert db_session.get(KbExtractJob, job_id).status == "running"

    # 第二次空采样（间隔 >= WATCHDOG_CONFIRM_INTERVAL_SEC）：确认 #2，
    # 本轮允许回收。
    assert (
        loop._recover_stuck_executing_routes(
            db_session, now=now + timedelta(seconds=5)
        )
        == 1
    )
    db_session.expire_all()
    assert db_session.get(KbExtractJob, job_id).status == "queued"
    route = db_session.get(GpuSchedulerOutbox, route_id)
    assert route.state == "queued"
    assert route.handover_epoch == 1
    lease = db_session.query(GpuSchedulerLease).filter_by(gpu_id="0").one()
    assert lease.state == "released"
    assert lease.active_job_id is None
    assert lease.watchdog_empty_confirmations == 2


def test_loop_recovers_stale_running_route_and_rolls_back_batch_counter(
    db_session, regular_user, monkeypatch
):
    """stale-running 恢复（requeue + route 退回 queued）必须回退本轮批计数，
    否则同一 job_id 在 5-job 批边界上重复计槽（164 §7.3 按 job_id 计数）。"""
    now = datetime(2026, 8, 1, 0, 0, 0)
    job_id, route_id = _seed_executing_mineru_route(
        db_session, regular_user, status="running", now=now
    )
    lease = db_session.query(GpuSchedulerLease).filter_by(gpu_id="0").one()
    lease.heartbeat_at = now - timedelta(seconds=121)
    lease.lease_expires_at = now - timedelta(seconds=91)
    lease.model_group = "mineru"
    lease.batch_size = 3
    lease.batch_started_at = now
    db_session.commit()
    monkeypatch.setattr(
        gpu_scheduler_loop, "gpu_round_idle", lambda job_kind, lease: True
    )
    loop = GpuSchedulerLoop(
        owner_id="scheduler-a",
        gpu_ids=["0"],
        tick_seconds=5,
        ttl_seconds=30,
        publishers={"mineru": lambda _payload: None, "raptor": lambda _payload: None},
    )

    assert loop._recover_stuck_executing_routes(db_session, now=now) == 0
    assert (
        loop._recover_stuck_executing_routes(
            db_session, now=now + timedelta(seconds=5)
        )
        == 1
    )

    db_session.expire_all()
    assert db_session.get(KbExtractJob, job_id).status == "queued"
    route = db_session.get(GpuSchedulerOutbox, route_id)
    assert route.state == "queued"
    lease = db_session.query(GpuSchedulerLease).filter_by(gpu_id="0").one()
    assert lease.state == "released"
    assert lease.batch_size == 2
    assert lease.model_group == "mineru"
    assert lease.batch_started_at == now


def test_loop_fails_sla_expired_raptor_job_when_gpu_idle(db_session, regular_user):
    """spec §7.3/SC-164-005：GPU 空闲（无 active lease）且 RAPTOR 等待超过
    15 分钟 + 一个调度 tick 时进入 failed/人工处置，queued route 收口 acked。"""
    now = datetime(2026, 8, 1, 0, 0, 0)
    job_id, route_id = _seed_waiting_raptor_job(
        db_session,
        regular_user,
        created_at=now - timedelta(seconds=920),
    )
    loop = GpuSchedulerLoop(
        owner_id="scheduler-a",
        gpu_ids=["0"],
        tick_seconds=5,
        ttl_seconds=30,
        publishers={"mineru": lambda _payload: None, "raptor": lambda _payload: None},
    )

    assert loop._fail_sla_expired_raptor_jobs(db_session, now=now) == 1
    db_session.expire_all()
    job = db_session.get(KbPostJob, job_id)
    assert job.status == "error"
    assert "raptor_sla_max_wait_exceeded" in (job.last_error or "")
    file_row = db_session.get(FileModel, job.file_id)
    assert file_row.kb_post_status == "failed"
    assert "raptor_sla_max_wait_exceeded" in (file_row.kb_post_error or "")
    route = db_session.get(GpuSchedulerOutbox, route_id)
    assert route.state == "acked"


def test_loop_keeps_sla_raptor_job_within_tick_grace(db_session, regular_user):
    """aging 到达 900s 后允许一个调度 tick 的宽限：等待 903s（tick=5s）且
    GPU 空闲时不失败，仍由 dispatch 派发。"""
    now = datetime(2026, 8, 1, 0, 0, 0)
    job_id, route_id = _seed_waiting_raptor_job(
        db_session,
        regular_user,
        created_at=now - timedelta(seconds=903),
    )
    loop = GpuSchedulerLoop(
        owner_id="scheduler-a",
        gpu_ids=["0"],
        tick_seconds=5,
        ttl_seconds=30,
        publishers={"mineru": lambda _payload: None, "raptor": lambda _payload: None},
    )

    assert loop._fail_sla_expired_raptor_jobs(db_session, now=now) == 0
    db_session.expire_all()
    assert db_session.get(KbPostJob, job_id).status == "waiting_gpu"
    assert db_session.get(GpuSchedulerOutbox, route_id).state == "queued"


def test_loop_keeps_sla_expired_raptor_job_when_gpu_busy(db_session, regular_user):
    """GPU 有 active lease（其他 job 执行中）时不触发 SLA 失败：只靠 aging
    提升优先级，避免误杀排队任务。"""
    now = datetime(2026, 8, 1, 0, 0, 0)
    job_id, route_id = _seed_waiting_raptor_job(
        db_session,
        regular_user,
        created_at=now - timedelta(seconds=920),
    )
    acquire_gpu_lease(
        db_session,
        gpu_id="0",
        owner_id="scheduler-a",
        now=now,
    )
    db_session.commit()
    loop = GpuSchedulerLoop(
        owner_id="scheduler-a",
        gpu_ids=["0"],
        tick_seconds=5,
        ttl_seconds=30,
        publishers={"mineru": lambda _payload: None, "raptor": lambda _payload: None},
    )

    assert loop._fail_sla_expired_raptor_jobs(db_session, now=now) == 0
    db_session.expire_all()
    assert db_session.get(KbPostJob, job_id).status == "waiting_gpu"
    assert db_session.get(GpuSchedulerOutbox, route_id).state == "queued"


def test_loop_keeps_sla_raptor_job_within_wait_window(db_session, regular_user):
    now = datetime(2026, 8, 1, 0, 0, 0)
    job_id, route_id = _seed_waiting_raptor_job(
        db_session,
        regular_user,
        created_at=now - timedelta(seconds=899),
    )
    loop = GpuSchedulerLoop(
        owner_id="scheduler-a",
        gpu_ids=["0"],
        tick_seconds=5,
        ttl_seconds=30,
        publishers={"mineru": lambda _payload: None, "raptor": lambda _payload: None},
    )

    assert loop._fail_sla_expired_raptor_jobs(db_session, now=now) == 0
    db_session.expire_all()
    assert db_session.get(KbPostJob, job_id).status == "waiting_gpu"
    assert db_session.get(GpuSchedulerOutbox, route_id).state == "queued"


def test_loop_keeps_sla_raptor_job_when_route_in_flight(db_session, regular_user):
    now = datetime(2026, 8, 1, 0, 0, 0)
    job_id, route_id = _seed_waiting_raptor_job(
        db_session,
        regular_user,
        created_at=now - timedelta(seconds=920),
        route_state="published",
    )
    loop = GpuSchedulerLoop(
        owner_id="scheduler-a",
        gpu_ids=["0"],
        tick_seconds=5,
        ttl_seconds=30,
        publishers={"mineru": lambda _payload: None, "raptor": lambda _payload: None},
    )

    assert loop._fail_sla_expired_raptor_jobs(db_session, now=now) == 0
    db_session.expire_all()
    assert db_session.get(KbPostJob, job_id).status == "waiting_gpu"
    assert db_session.get(GpuSchedulerOutbox, route_id).state == "published"


def test_loop_blocks_stale_lease_recovery_while_gpu_busy(
    db_session, regular_user, monkeypatch
):
    """loop 停滞 >2×TTL 但 consumer 仍在执行（或双 worker 下另一 worker 持有
    GPU）时，心跳停止的 lease 不得回收：watchdog 探测到 GPU 进程非空即保持
    recovery_blocked，job/route/lease 原样保留。"""
    now = datetime(2026, 8, 1, 0, 0, 0)
    job_id, route_id = _seed_executing_mineru_route(
        db_session, regular_user, status="running", now=now
    )
    lease = db_session.query(GpuSchedulerLease).filter_by(gpu_id="0").one()
    lease.heartbeat_at = now - timedelta(seconds=121)
    lease.lease_expires_at = now - timedelta(seconds=91)
    db_session.commit()
    monkeypatch.setattr(
        gpu_scheduler_loop, "gpu_round_idle", lambda job_kind, lease: False
    )
    loop = GpuSchedulerLoop(
        owner_id="scheduler-a",
        gpu_ids=["0"],
        tick_seconds=5,
        ttl_seconds=30,
        publishers={"mineru": lambda _payload: None, "raptor": lambda _payload: None},
    )

    assert loop._recover_stuck_executing_routes(db_session, now=now) == 0
    assert (
        loop._recover_stuck_executing_routes(
            db_session, now=now + timedelta(seconds=5)
        )
        == 0
    )
    db_session.expire_all()
    assert db_session.get(KbExtractJob, job_id).status == "running"
    route = db_session.get(GpuSchedulerOutbox, route_id)
    assert route.state == "executing"
    lease = db_session.query(GpuSchedulerLease).filter_by(gpu_id="0").one()
    assert lease.state == "active"
    assert lease.watchdog_empty_confirmations == 0


def test_loop_recovers_stale_raptor_route_after_sidecar_idle(
    db_session, regular_user, monkeypatch
):
    """WHB T-9：Ollama 常驻 + sidecar 常驻 CUDA 时 nvidia-smi 永远非空，
    进程采样不可用；旧 RAPTOR 轮与 scheduler 进程共存亡，sidecar 无 active
    执行即确认旧轮已退出，stale lease 可恢复并重新调度。"""
    now = datetime(2026, 8, 1, 0, 0, 0)
    job_id, route_id = _seed_executing_raptor_route(
        db_session, regular_user, status="running", now=now
    )
    lease = db_session.query(GpuSchedulerLease).filter_by(gpu_id="0").one()
    lease.heartbeat_at = now - timedelta(seconds=121)
    lease.lease_expires_at = now - timedelta(seconds=91)
    db_session.commit()
    monkeypatch.setattr(
        gpu_scheduler_loop, "gpu_round_idle", lambda job_kind, lease: True
    )
    loop = GpuSchedulerLoop(
        owner_id="scheduler-a",
        gpu_ids=["0"],
        tick_seconds=5,
        ttl_seconds=30,
        publishers={"mineru": lambda _payload: None, "raptor": lambda _payload: None},
    )

    assert loop._recover_stuck_executing_routes(db_session, now=now) == 0
    db_session.expire_all()
    lease = db_session.query(GpuSchedulerLease).filter_by(gpu_id="0").one()
    assert lease.state == "active"
    assert lease.watchdog_empty_confirmations == 1

    assert (
        loop._recover_stuck_executing_routes(
            db_session, now=now + timedelta(seconds=5)
        )
        == 1
    )
    db_session.expire_all()
    assert db_session.get(KbPostJob, job_id).status == "queued"
    route = db_session.get(GpuSchedulerOutbox, route_id)
    assert route.state == "queued"
    lease = db_session.query(GpuSchedulerLease).filter_by(gpu_id="0").one()
    assert lease.state == "released"
    assert lease.active_job_id is None


def test_loop_blocks_stale_raptor_recovery_while_sidecar_busy(
    db_session, regular_user, monkeypatch
):
    """sidecar 仍在执行旧轮（或探测失败）时，心跳停止的 raptor lease 不得
    回收，保持 recovery_blocked。"""
    now = datetime(2026, 8, 1, 0, 0, 0)
    job_id, route_id = _seed_executing_raptor_route(
        db_session, regular_user, status="running", now=now
    )
    lease = db_session.query(GpuSchedulerLease).filter_by(gpu_id="0").one()
    lease.heartbeat_at = now - timedelta(seconds=121)
    lease.lease_expires_at = now - timedelta(seconds=91)
    db_session.commit()
    monkeypatch.setattr(
        gpu_scheduler_loop, "gpu_round_idle", lambda job_kind, lease: False
    )
    loop = GpuSchedulerLoop(
        owner_id="scheduler-a",
        gpu_ids=["0"],
        tick_seconds=5,
        ttl_seconds=30,
        publishers={"mineru": lambda _payload: None, "raptor": lambda _payload: None},
    )

    assert loop._recover_stuck_executing_routes(db_session, now=now) == 0
    assert (
        loop._recover_stuck_executing_routes(
            db_session, now=now + timedelta(seconds=5)
        )
        == 0
    )
    db_session.expire_all()
    assert db_session.get(KbPostJob, job_id).status == "running"
    route = db_session.get(GpuSchedulerOutbox, route_id)
    assert route.state == "executing"
    lease = db_session.query(GpuSchedulerLease).filter_by(gpu_id="0").one()
    assert lease.state == "active"
    assert lease.watchdog_empty_confirmations == 0


def test_loop_recovers_executing_route_with_queued_job_and_no_lease(
    db_session, regular_user
):
    """非 OperationalError 在 claim 后、running 提交前逃逸：route executing +
    job queued + 无 active lease。无 lease = 无执行轮，必须安全收回 route。"""
    now = datetime(2026, 8, 1, 0, 0, 0)
    job_id, route_id = _seed_executing_mineru_route(
        db_session, regular_user, status="queued", now=now
    )
    db_session.query(GpuSchedulerLease).filter_by(gpu_id="0").delete()
    db_session.commit()
    loop = GpuSchedulerLoop(
        owner_id="scheduler-a",
        gpu_ids=["0"],
        tick_seconds=5,
        ttl_seconds=30,
        publishers={"mineru": lambda _payload: None, "raptor": lambda _payload: None},
    )

    assert loop._recover_stuck_executing_routes(db_session, now=now) == 1
    db_session.expire_all()
    assert db_session.get(KbExtractJob, job_id).status == "queued"
    route = db_session.get(GpuSchedulerOutbox, route_id)
    assert route.state == "queued"
    assert route.handover_epoch == 1


def test_loop_recovers_published_route_after_watchdog_confirmations(
    db_session, regular_user, monkeypatch
):
    """dispatch 提交 published 后、consumer claim 前崩溃：published route +
    心跳停止的 lease 经 watchdog 两次空确认后必须退回 queued 并释放，下一
    tick 才能重新派发。"""
    now = datetime(2026, 8, 1, 0, 0, 0)
    file = FileModel(
        filename="scheduler-loop-published.pdf",
        original_name="scheduler-loop-published.pdf",
        file_path="/tmp/scheduler-loop-published.pdf",
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
    route = enqueue_gpu_route(
        db_session,
        job_kind="mineru",
        job_id=job.id,
        file_id=file.id,
        idempotency_key=f"mineru:{job.id}:0",
        payload={"job_id": job.id, "job_kind": "mineru", "file_id": file.id},
    )
    publish_gpu_route(db_session, outbox_id=route.id, publish=lambda _payload: None)
    lease = acquire_gpu_lease(
        db_session,
        gpu_id="0",
        owner_id="scheduler-a",
        now=now,
    )
    lease.active_job_id = str(job.id)
    lease.heartbeat_at = now - timedelta(seconds=121)
    lease.lease_expires_at = now - timedelta(seconds=91)
    lease.model_group = "mineru"
    lease.batch_size = 1
    lease.batch_started_at = now
    db_session.commit()
    route_id = route.id
    monkeypatch.setattr(
        gpu_scheduler_loop, "gpu_round_idle", lambda job_kind, lease: True
    )
    loop = GpuSchedulerLoop(
        owner_id="scheduler-a",
        gpu_ids=["0"],
        tick_seconds=5,
        ttl_seconds=30,
        publishers={"mineru": lambda _payload: None, "raptor": lambda _payload: None},
    )

    assert loop._recover_stuck_executing_routes(db_session, now=now) == 0
    assert (
        loop._recover_stuck_executing_routes(
            db_session, now=now + timedelta(seconds=5)
        )
        == 1
    )
    db_session.expire_all()
    route = db_session.get(GpuSchedulerOutbox, route_id)
    assert route.state == "queued"
    assert route.handover_epoch == 1
    lease = db_session.query(GpuSchedulerLease).filter_by(gpu_id="0").one()
    assert lease.state == "released"
    assert lease.active_job_id is None
    # published route 从未执行：本轮批计数回退，避免无执行轮次虚增。
    assert lease.batch_size == 0
    assert lease.model_group is None
    assert lease.batch_started_at is None


def test_loop_recovers_deferred_route_and_rolls_back_batch(
    db_session, regular_user
):
    """defer（waiting_gpu）收尾前崩溃的 executing route 由调度循环退回
    queued 时，必须回退本轮 dispatch 写入的批计数，避免无执行的 defer 轮次
    虚增 5-job/600s 批计数。"""
    now = datetime(2026, 8, 1, 0, 0, 0)
    _job_id, route_id = _seed_executing_mineru_route(
        db_session, regular_user, status="waiting_gpu", now=now
    )
    lease = db_session.query(GpuSchedulerLease).filter_by(gpu_id="0").one()
    lease.model_group = "mineru"
    lease.batch_size = 2
    lease.batch_started_at = now
    db_session.commit()
    loop = GpuSchedulerLoop(
        owner_id="scheduler-a",
        gpu_ids=["0"],
        tick_seconds=5,
        ttl_seconds=30,
        publishers={"mineru": lambda _payload: None, "raptor": lambda _payload: None},
    )

    assert loop._recover_stuck_executing_routes(db_session, now=now) == 1
    db_session.expire_all()
    assert db_session.get(GpuSchedulerOutbox, route_id).state == "queued"
    lease = db_session.query(GpuSchedulerLease).filter_by(gpu_id="0").one()
    assert lease.state == "released"
    assert lease.batch_size == 1
    assert lease.model_group == "mineru"
    assert lease.batch_started_at == now


def test_loop_does_not_heartbeat_lease_owned_by_previous_incarnation(
    db_session, regular_user
):
    """重启后的新 loop 不得续期上一进程留下的同 owner lease（进程内没有
    fencing token）：心跳保持不变，且陈旧 lease 被回收释放，dispatch 才能
    重新取得租约，gpu_id 不会永久停摆。"""
    now = datetime(2026, 8, 1, 0, 0, 0)
    lease = acquire_gpu_lease(
        db_session,
        gpu_id="0",
        owner_id="scheduler-a",
        now=now - timedelta(seconds=121),
    )
    db_session.commit()
    loop = GpuSchedulerLoop(
        owner_id="scheduler-a",
        gpu_ids=["0"],
        tick_seconds=5,
        ttl_seconds=30,
        publishers={"mineru": lambda _payload: None, "raptor": lambda _payload: None},
    )

    assert loop.run_once(db_session, now=now) == 0
    db_session.expire_all()
    lease = db_session.query(GpuSchedulerLease).filter_by(gpu_id="0").one()
    # 心跳未被新进程续期（上一进程的 heartbeat 原样保留）。
    assert lease.heartbeat_at == now - timedelta(seconds=121)
    # 陈旧 lease 被回收，下一 tick 可重新派发。
    assert lease.state == "released"


def test_loop_continues_mineru_batch_from_persisted_lease_state(
    db_session, regular_user
):
    """生产 loop 必须把持久化的 batch 状态传给 dispatch：第二个 MinerU job
    在同一 MINERU 驻留内继续 batch，而不是每次从空重新选择。"""
    now = datetime(2026, 8, 1, 0, 0, 0)
    job_id1 = _seed_mineru_job(db_session, regular_user, created_at=now)
    published_payloads = []
    loop = GpuSchedulerLoop(
        owner_id="scheduler-a",
        gpu_ids=["0"],
        tick_seconds=5,
        ttl_seconds=30,
        publishers={"mineru": published_payloads.append, "raptor": lambda _payload: None},
    )

    assert loop.run_once(db_session, now=now) == 1
    db_session.expire_all()
    lease = db_session.query(GpuSchedulerLease).filter_by(gpu_id="0").one()
    assert lease.model_group == "mineru"
    assert lease.batch_size == 1
    assert lease.batch_started_at == now
    from services.gpu_scheduler_persistence import release_gpu_lease_if_owned

    # 模拟 consumer 执行完成：ack route 并释放 dispatch lease。
    route = db_session.query(GpuSchedulerOutbox).filter_by(state="published").one()
    assert ack_gpu_route(db_session, outbox_id=route.id) is not None
    assert release_gpu_lease_if_owned(
        db_session,
        gpu_id="0",
        owner_id="scheduler-a",
        now=now + timedelta(seconds=10),
    )
    db_session.commit()

    later = now + timedelta(seconds=11)
    job_id2 = _seed_mineru_job(
        db_session, regular_user, created_at=now + timedelta(seconds=11)
    )
    assert loop.run_once(db_session, now=later) == 1
    db_session.expire_all()
    lease = db_session.query(GpuSchedulerLease).filter_by(gpu_id="0").one()
    assert lease.model_group == "mineru"
    assert lease.batch_size == 2
    assert lease.batch_started_at == now
    assert [payload["job_id"] for payload in published_payloads] == [job_id1, job_id2]
