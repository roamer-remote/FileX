import threading
import uuid
from datetime import datetime, timedelta

import pytest
from sqlalchemy import text
from sqlalchemy.orm import sessionmaker

from models.gpu_scheduler import GpuSchedulerLease
from models.gpu_scheduler import GpuSchedulerOutbox
from models.kb_extract_job import KbExtractJob
from models.kb_post_job import KbPostJob
from models.file import File as FileModel
from services import gpu_scheduler_dispatch
from services.gpu_scheduler_persistence import acquire_gpu_lease
from services.gpu_scheduler_dispatch import (
    choose_next_waiting_gpu_job,
    dispatch_next_gpu_route,
    list_waiting_gpu_jobs,
)


def _create_committed_user(session) -> int:
    from models.user import User
    from services.auth_service import hash_password
    from services.enterprise_rbac_seed import get_unassigned_department_id
    from services.workspace_service import ensure_personal_workspace

    user = User(
        username=f"gpu-race-{uuid.uuid4().hex[:10]}",
        password_hash=hash_password("password123"),
        is_admin=False,
        is_active=True,
        password_rev=0,
        primary_department_id=get_unassigned_department_id(session),
    )
    session.add(user)
    session.commit()
    session.refresh(user)
    ensure_personal_workspace(session, user)
    session.commit()
    return user.id


def _cleanup_committed_rows(session, *, user_id: int, job_id: int) -> None:
    session.rollback()
    session.execute(
        text("DELETE FROM gpu_scheduler_outbox WHERE job_id = :job_id"),
        {"job_id": str(job_id)},
    )
    session.execute(text("DELETE FROM gpu_scheduler_leases"))
    session.execute(text("DELETE FROM kb_extract_jobs WHERE id = :job_id"), {"job_id": job_id})
    session.execute(text("DELETE FROM files WHERE user_id = :user_id"), {"user_id": user_id})
    session.execute(
        text("DELETE FROM workspace_members WHERE user_id = :user_id"),
        {"user_id": user_id},
    )
    session.execute(
        text("DELETE FROM workspaces WHERE owner_user_id = :user_id"),
        {"user_id": user_id},
    )
    session.execute(text("DELETE FROM users WHERE id = :user_id"), {"user_id": user_id})
    session.commit()


def test_dispatch_reads_only_waiting_jobs_with_gpu_routes(db_session, regular_user):
    now = datetime(2026, 8, 1, 0, 0, 0)
    file = FileModel(
        filename="dispatch.pdf",
        original_name="dispatch.pdf",
        file_path="/tmp/dispatch.pdf",
        file_size=10,
        mime_type="application/pdf",
        user_id=regular_user.id,
    )
    db_session.add(file)
    db_session.flush()
    extract = KbExtractJob(
        user_id=regular_user.id,
        file_id=file.id,
        provider="mineru",
        status="waiting_gpu",
        created_at=now - timedelta(seconds=20),
    )
    post = KbPostJob(
        user_id=regular_user.id,
        file_id=file.id,
        status="queued",
        created_at=now,
    )
    db_session.add_all([extract, post])
    db_session.flush()
    db_session.add_all(
        [
            GpuSchedulerOutbox(
                job_kind="mineru",
                job_id=str(extract.id),
                file_id=extract.file_id,
                idempotency_key=f"mineru:{extract.id}:0",
                payload={"job_id": extract.id},
                state="published",
            ),
            GpuSchedulerOutbox(
                job_kind="raptor",
                job_id=str(post.id),
                file_id=post.file_id,
                idempotency_key=f"raptor:{post.id}:0",
                payload={"job_id": post.id},
                state="published",
            ),
        ]
    )
    db_session.flush()

    candidates = list_waiting_gpu_jobs(db_session)
    assert {(item.job_kind, item.job_id) for item in candidates} == {
        ("mineru", str(extract.id)),
        ("raptor", str(post.id)),
    }
    selected, decision = choose_next_waiting_gpu_job(db_session, now=now)
    assert selected.job_kind == "mineru"
    assert decision.reason == "mineru_priority"
    # Published routes are candidates for execution, never for (re-)dispatch.
    assert choose_next_waiting_gpu_job(db_session, now=now, publishable_only=True) is None


def test_dispatch_fences_owner_before_publishing_selected_route(db_session, regular_user):
    now = datetime(2026, 8, 1, 0, 0, 0)
    file = FileModel(
        filename="dispatch-2.pdf",
        original_name="dispatch-2.pdf",
        file_path="/tmp/dispatch-2.pdf",
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
    route = GpuSchedulerOutbox(
        job_kind="mineru",
        job_id=str(job.id),
        file_id=file.id,
        idempotency_key=f"mineru:{job.id}:0",
        payload={"job_id": job.id},
        state="queued",
    )
    db_session.add(route)
    db_session.flush()
    published_payloads = []
    result = dispatch_next_gpu_route(
        db_session,
        owner_id="scheduler-a",
        gpu_id="0",
        now=now,
        publish=published_payloads.append,
    )
    assert result.candidate.job_id == str(job.id)
    assert result.route_published is True
    assert result.lease.owner_id == "scheduler-a"
    assert published_payloads == [
        {"job_id": job.id, "attempt": 1, "handover_epoch": 0}
    ]


def test_dispatch_selects_unpinned_job_with_mineru_route(db_session, regular_user):
    """reextract 未显式指定 provider 时 job.provider 为 None，但 enqueue 已按
    运行时默认建立 mineru route：该 job 必须能进入调度候选并发布。"""
    now = datetime(2026, 8, 1, 0, 0, 0)
    file = FileModel(
        filename="dispatch-unpinned.pdf",
        original_name="dispatch-unpinned.pdf",
        file_path="/tmp/dispatch-unpinned.pdf",
        file_size=10,
        mime_type="application/pdf",
        user_id=regular_user.id,
    )
    db_session.add(file)
    db_session.flush()
    job = KbExtractJob(
        user_id=regular_user.id,
        file_id=file.id,
        provider=None,
        status="queued",
        created_at=now,
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
    db_session.commit()

    published_payloads = []
    result = dispatch_next_gpu_route(
        db_session,
        owner_id="scheduler-a",
        gpu_id="0",
        now=now,
        publish=published_payloads.append,
    )
    assert result is not None
    assert result.candidate.job_id == str(job.id)
    assert result.route_published is True
    assert published_payloads == [
        {"job_id": job.id, "attempt": 1, "handover_epoch": 0}
    ]


def test_dispatch_ignores_unpinned_job_without_mineru_route(db_session, regular_user):
    """provider 为 None 且没有 mineru durable route 的 job（默认非 mineru）
    不是 GPU 调度候选。"""
    now = datetime(2026, 8, 1, 0, 0, 0)
    file = FileModel(
        filename="dispatch-noroute.pdf",
        original_name="dispatch-noroute.pdf",
        file_path="/tmp/dispatch-noroute.pdf",
        file_size=10,
        mime_type="application/pdf",
        user_id=regular_user.id,
    )
    db_session.add(file)
    db_session.flush()
    db_session.add(
        KbExtractJob(
            user_id=regular_user.id,
            file_id=file.id,
            provider=None,
            status="queued",
            created_at=now,
        )
    )
    db_session.commit()

    result = dispatch_next_gpu_route(
        db_session,
        owner_id="scheduler-a",
        gpu_id="0",
        now=now,
        publish=lambda _payload: None,
    )
    assert result is None


def test_publishable_only_excludes_published_routes(db_session, regular_user):
    now = datetime(2026, 8, 1, 0, 0, 0)
    file = FileModel(
        filename="dispatch-3.pdf",
        original_name="dispatch-3.pdf",
        file_path="/tmp/dispatch-3.pdf",
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
        status="waiting_gpu",
        created_at=now,
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
            state="published",
        )
    )
    db_session.flush()

    assert list_waiting_gpu_jobs(db_session, publishable_only=True) == []
    assert [item.job_id for item in list_waiting_gpu_jobs(db_session)] == [str(job.id)]


def test_dispatch_releases_lease_and_keeps_route_when_publish_fails(db_session, regular_user):
    now = datetime(2026, 8, 1, 0, 0, 0)
    file = FileModel(
        filename="dispatch-4.pdf",
        original_name="dispatch-4.pdf",
        file_path="/tmp/dispatch-4.pdf",
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
    route = GpuSchedulerOutbox(
        job_kind="mineru",
        job_id=str(job.id),
        file_id=file.id,
        idempotency_key=f"mineru:{job.id}:0",
        payload={"job_id": job.id},
        state="queued",
    )
    db_session.add(route)
    db_session.flush()
    db_session.commit()
    route_id = route.id

    def broken_publish(_payload):
        raise RuntimeError("broker down")

    with pytest.raises(RuntimeError, match="broker down"):
        dispatch_next_gpu_route(
            db_session,
            owner_id="scheduler-a",
            gpu_id="0",
            now=now,
            publish=broken_publish,
        )

    route = db_session.get(GpuSchedulerOutbox, route_id)
    assert route.state == "queued"
    lease = db_session.query(GpuSchedulerLease).filter_by(gpu_id="0").one()
    assert lease.state == "released"
    assert lease.active_job_id is None
    assert lease.release_ack_at == now

    # A later scheduler pass can retry the same durable route exactly once more.
    published_payloads = []
    result = dispatch_next_gpu_route(
        db_session,
        owner_id="scheduler-a",
        gpu_id="0",
        now=now + timedelta(seconds=1),
        publish=published_payloads.append,
    )
    assert result is not None
    assert result.route_published is True
    assert published_payloads == [
        {"job_id": job.id, "attempt": 2, "handover_epoch": 0}
    ]
    retried = db_session.get(GpuSchedulerOutbox, route_id)
    assert retried.state == "published"
    assert retried.attempt == 2
    assert retried.payload["attempt"] == 2


def test_dispatch_does_not_publish_when_lease_is_held_by_other_owner(db_session, regular_user):
    now = datetime(2026, 8, 1, 0, 0, 0)
    acquire_gpu_lease(db_session, gpu_id="0", owner_id="scheduler-b", now=now)
    db_session.commit()
    file = FileModel(
        filename="dispatch-5.pdf",
        original_name="dispatch-5.pdf",
        file_path="/tmp/dispatch-5.pdf",
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

    published_payloads = []
    result = dispatch_next_gpu_route(
        db_session,
        owner_id="scheduler-a",
        gpu_id="0",
        now=now,
        publish=published_payloads.append,
    )
    assert result is None
    assert published_payloads == []


def test_same_owner_concurrent_dispatch_does_not_reuse_or_release_lease(db_session, regular_user):
    now = datetime(2026, 8, 1, 0, 0, 0)
    file = FileModel(
        filename="dispatch-6.pdf",
        original_name="dispatch-6.pdf",
        file_path="/tmp/dispatch-6.pdf",
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
    # Simulate a first dispatch that already acquired and bound the lease.
    first = acquire_gpu_lease(db_session, gpu_id="0", owner_id="scheduler-a", now=now)
    first.active_job_id = str(job.id)
    db_session.commit()
    first_token = first.fencing_token

    published_payloads = []
    result = dispatch_next_gpu_route(
        db_session,
        owner_id="scheduler-a",
        gpu_id="0",
        now=now + timedelta(seconds=1),
        publish=published_payloads.append,
    )
    assert result is None
    assert published_payloads == []
    db_session.expire_all()
    lease = db_session.query(GpuSchedulerLease).filter_by(gpu_id="0").one()
    assert lease.state == "active"
    assert lease.active_job_id == str(job.id)
    assert lease.fencing_token == first_token


def test_two_sessions_same_owner_same_gpu_concurrent_dispatch_is_safe(engine):
    now = datetime(2026, 8, 1, 0, 0, 0)
    Session = sessionmaker(bind=engine)
    setup = Session()
    job = None
    user_id = None
    try:
        user_id = _create_committed_user(setup)
        file = FileModel(
            filename="dispatch-6b.pdf",
            original_name="dispatch-6b.pdf",
            file_path="/tmp/dispatch-6b.pdf",
            file_size=10,
            mime_type="application/pdf",
            user_id=user_id,
        )
        setup.add(file)
        setup.commit()
        setup.refresh(file)
        job = KbExtractJob(
            user_id=user_id,
            file_id=file.id,
            provider="mineru",
            status="queued",
            created_at=now,
        )
        setup.add(job)
        setup.commit()
        setup.refresh(job)
        setup.add(
            GpuSchedulerOutbox(
                job_kind="mineru",
                job_id=str(job.id),
                file_id=file.id,
                idempotency_key=f"mineru:{job.id}:0",
                payload={"job_id": job.id},
                state="queued",
            )
        )
        setup.commit()

        results = []
        published_payloads = []
        lock = threading.Lock()
        sessions = [Session(), Session()]

        def run(session):
            try:
                result = gpu_scheduler_dispatch.dispatch_next_gpu_route(
                    session,
                    owner_id="scheduler-a",
                    gpu_id="0",
                    now=now,
                    publish=published_payloads.append,
                )
            except Exception as exc:  # surface thread failures in the assertion below
                result = exc
            finally:
                session.close()
            with lock:
                results.append(result)

        threads = [threading.Thread(target=run, args=(session,)) for session in sessions]
        for thread in threads:
            thread.start()
        for thread in threads:
            thread.join()

        assert all(not isinstance(result, Exception) for result in results), repr(results)
        assert len([result for result in results if result is not None]) == 1
        assert published_payloads == [
            {"job_id": job.id, "attempt": 1, "handover_epoch": 0}
        ]
        lease = setup.query(GpuSchedulerLease).filter_by(gpu_id="0").one()
        assert lease.state == "active"
        assert lease.active_job_id == str(job.id)
    finally:
        if job is not None and user_id is not None:
            _cleanup_committed_rows(setup, user_id=user_id, job_id=job.id)
        setup.close()


def test_dispatch_releases_lease_when_route_claim_is_lost(db_session, regular_user, monkeypatch):
    now = datetime(2026, 8, 1, 0, 0, 0)
    file = FileModel(
        filename="dispatch-7.pdf",
        original_name="dispatch-7.pdf",
        file_path="/tmp/dispatch-7.pdf",
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
    route = GpuSchedulerOutbox(
        job_kind="mineru",
        job_id=str(job.id),
        file_id=file.id,
        idempotency_key=f"mineru:{job.id}:0",
        payload={"job_id": job.id},
        state="queued",
    )
    db_session.add(route)
    db_session.flush()
    route_id = route.id

    monkeypatch.setattr(
        gpu_scheduler_dispatch,
        "claim_gpu_route",
        lambda db, **kwargs: None,
    )
    result = dispatch_next_gpu_route(
        db_session,
        owner_id="scheduler-a",
        gpu_id="0",
        now=now,
        publish=lambda _payload: None,
    )
    assert result is None
    lease = db_session.query(GpuSchedulerLease).filter_by(gpu_id="0").one()
    assert lease.state == "released"
    assert lease.active_job_id is None
    assert db_session.get(GpuSchedulerOutbox, route_id).state == "queued"


def _seed_dispatch_job(db_session, regular_user, *, job_kind: str, created_at, name: str):
    file = FileModel(
        filename=name,
        original_name=name,
        file_path=f"/tmp/{name}",
        file_size=10,
        mime_type="application/pdf",
        user_id=regular_user.id,
    )
    db_session.add(file)
    db_session.flush()
    if job_kind == "mineru":
        job = KbExtractJob(
            user_id=regular_user.id,
            file_id=file.id,
            provider="mineru",
            status="queued",
            created_at=created_at,
        )
    else:
        job = KbPostJob(
            user_id=regular_user.id,
            file_id=file.id,
            status="queued",
            created_at=created_at,
        )
    db_session.add(job)
    db_session.flush()
    db_session.add(
        GpuSchedulerOutbox(
            job_kind=job_kind,
            job_id=str(job.id),
            file_id=file.id,
            idempotency_key=f"{job_kind}:{job.id}:0",
            payload={"job_id": job.id},
            state="queued",
        )
    )
    db_session.flush()
    return job.id


def test_dispatch_writes_batch_state_on_first_mineru_dispatch(db_session, regular_user):
    """164 §7.3：MinerU batch 首个 job 派发后，lease 必须记录 model_group、
    batch_size=1 与 batch_started_at，供下一 tick 继续计算。"""
    now = datetime(2026, 8, 1, 0, 0, 0)
    job_id = _seed_dispatch_job(
        db_session, regular_user, job_kind="mineru", created_at=now, name="batch-1.pdf"
    )

    result = dispatch_next_gpu_route(
        db_session,
        owner_id="scheduler-a",
        gpu_id="0",
        now=now,
        publish=lambda _payload: None,
    )
    assert result is not None
    assert result.candidate.job_id == str(job_id)
    db_session.expire_all()
    lease = db_session.query(GpuSchedulerLease).filter_by(gpu_id="0").one()
    assert lease.model_group == "mineru"
    assert lease.batch_size == 1
    assert lease.batch_started_at == now


def test_dispatch_continues_mineru_batch_from_persisted_state(db_session, regular_user):
    """同一 MINERU 驻留内连续派发：batch_size 递增，batch_started_at 保持不变。"""
    now = datetime(2026, 8, 1, 0, 0, 0)
    _seed_dispatch_job(
        db_session, regular_user, job_kind="mineru", created_at=now, name="batch-2a.pdf"
    )
    result = dispatch_next_gpu_route(
        db_session,
        owner_id="scheduler-a",
        gpu_id="0",
        now=now,
        publish=lambda _payload: None,
    )
    assert result is not None
    db_session.commit()
    from services.gpu_scheduler_persistence import release_gpu_lease_if_owned

    assert release_gpu_lease_if_owned(
        db_session,
        gpu_id="0",
        owner_id="scheduler-a",
        now=now + timedelta(seconds=1),
    )
    db_session.commit()

    later = now + timedelta(seconds=2)
    job_id2 = _seed_dispatch_job(
        db_session,
        regular_user,
        job_kind="mineru",
        created_at=later,
        name="batch-2b.pdf",
    )
    result2 = dispatch_next_gpu_route(
        db_session,
        owner_id="scheduler-a",
        gpu_id="0",
        now=later,
        current_model_group="mineru",
        current_batch_size=1,
        batch_started_at=now,
        publish=lambda _payload: None,
    )
    assert result2 is not None
    assert result2.candidate.job_id == str(job_id2)
    db_session.expire_all()
    lease = db_session.query(GpuSchedulerLease).filter_by(gpu_id="0").one()
    assert lease.model_group == "mineru"
    assert lease.batch_size == 2
    assert lease.batch_started_at == now


def test_dispatch_switches_model_group_at_mineru_batch_boundary(db_session, regular_user):
    """batch 达到 5 job 边界后，存在 RAPTOR 时必须切换模型组并开始新批。"""
    now = datetime(2026, 8, 1, 0, 0, 0)
    for i in range(5):
        _seed_dispatch_job(
            db_session,
            regular_user,
            job_kind="mineru",
            created_at=now + timedelta(seconds=i),
            name=f"boundary-m{i}.pdf",
        )
    raptor_id = _seed_dispatch_job(
        db_session,
        regular_user,
        job_kind="raptor",
        created_at=now + timedelta(seconds=60),
        name="boundary-r.pdf",
    )

    result = dispatch_next_gpu_route(
        db_session,
        owner_id="scheduler-a",
        gpu_id="0",
        now=now + timedelta(seconds=601),
        current_model_group="mineru",
        current_batch_size=5,
        batch_started_at=now,
        publish=lambda _payload: None,
    )
    assert result is not None
    assert result.candidate.job_id == str(raptor_id)
    assert result.selection.reason == "mineru_batch_boundary_switch_raptor"
    db_session.expire_all()
    lease = db_session.query(GpuSchedulerLease).filter_by(gpu_id="0").one()
    assert lease.model_group == "raptor"
    assert lease.batch_size == 1
    assert lease.batch_started_at == now + timedelta(seconds=601)


def test_dispatch_starts_new_batch_at_boundary_without_raptor(db_session, regular_user):
    """batch 达到边界但无 RAPTOR 等待时，MinerU 新批必须从 1 重新计数并重置
    batch_started_at，不能把旧批计数继续累加。"""
    now = datetime(2026, 8, 1, 0, 0, 0)
    for i in range(6):
        _seed_dispatch_job(
            db_session,
            regular_user,
            job_kind="mineru",
            created_at=now + timedelta(seconds=i),
            name=f"newbatch-m{i}.pdf",
        )

    result = dispatch_next_gpu_route(
        db_session,
        owner_id="scheduler-a",
        gpu_id="0",
        now=now + timedelta(seconds=601),
        current_model_group="mineru",
        current_batch_size=5,
        batch_started_at=now,
        publish=lambda _payload: None,
    )
    assert result is not None
    assert result.selection.reason == "start_new_mineru_batch"
    assert result.candidate.job_kind == "mineru"
    db_session.expire_all()
    lease = db_session.query(GpuSchedulerLease).filter_by(gpu_id="0").one()
    assert lease.model_group == "mineru"
    assert lease.batch_size == 1
    assert lease.batch_started_at == now + timedelta(seconds=601)


def test_dispatch_commit_failure_leaves_route_queued_and_recovery_republishes(engine, monkeypatch):
    now = datetime(2026, 8, 1, 0, 0, 0)
    Session = sessionmaker(bind=engine)
    session = Session()
    job = None
    user_id = None
    try:
        user_id = _create_committed_user(session)
        file = FileModel(
            filename="dispatch-8.pdf",
            original_name="dispatch-8.pdf",
            file_path="/tmp/dispatch-8.pdf",
            file_size=10,
            mime_type="application/pdf",
            user_id=user_id,
        )
        session.add(file)
        session.commit()
        session.refresh(file)
        job = KbExtractJob(
            user_id=user_id,
            file_id=file.id,
            provider="mineru",
            status="queued",
            created_at=now,
        )
        session.add(job)
        session.commit()
        session.refresh(job)
        route = GpuSchedulerOutbox(
            job_kind="mineru",
            job_id=str(job.id),
            file_id=file.id,
            idempotency_key=f"mineru:{job.id}:0",
            payload={"job_id": job.id},
            state="queued",
        )
        session.add(route)
        session.commit()
        session.refresh(route)
        route_id = route.id
        published_payloads = []
        original_commit = session.commit

        def broken_commit():
            raise RuntimeError("db commit failed")

        monkeypatch.setattr(session, "commit", broken_commit)
        with pytest.raises(RuntimeError, match="db commit failed"):
            dispatch_next_gpu_route(
                session,
                owner_id="scheduler-a",
                gpu_id="0",
                now=now,
                publish=published_payloads.append,
            )
        session.rollback()
        assert session.get(GpuSchedulerOutbox, route_id).state == "queued"
        assert session.query(GpuSchedulerLease).filter_by(gpu_id="0").count() == 0

        monkeypatch.setattr(session, "commit", original_commit)
        result = dispatch_next_gpu_route(
            session,
            owner_id="scheduler-a",
            gpu_id="0",
            now=now + timedelta(seconds=1),
            publish=published_payloads.append,
        )
        assert result is not None
        assert published_payloads == [
            # 第一次发布在 commit 前已发出但事务回滚；恢复后重新发布相同消息。
            {"job_id": job.id, "attempt": 1, "handover_epoch": 0},
            {"job_id": job.id, "attempt": 1, "handover_epoch": 0},
        ]
        assert session.get(GpuSchedulerOutbox, route_id).state == "published"
    finally:
        if job is not None and user_id is not None:
            _cleanup_committed_rows(session, user_id=user_id, job_id=job.id)
        session.close()


def test_two_dispatchers_race_same_route_publishes_exactly_once(engine, monkeypatch):
    now = datetime(2026, 8, 1, 0, 0, 0)
    Session = sessionmaker(bind=engine)
    setup = Session()
    job = None
    user_id = None
    try:
        user_id = _create_committed_user(setup)
        file = FileModel(
            filename="dispatch-9.pdf",
            original_name="dispatch-9.pdf",
            file_path="/tmp/dispatch-9.pdf",
            file_size=10,
            mime_type="application/pdf",
            user_id=user_id,
        )
        setup.add(file)
        setup.commit()
        setup.refresh(file)
        job = KbExtractJob(
            user_id=user_id,
            file_id=file.id,
            provider="mineru",
            status="queued",
            created_at=now,
        )
        setup.add(job)
        setup.commit()
        setup.refresh(job)
        setup.add(
            GpuSchedulerOutbox(
                job_kind="mineru",
                job_id=str(job.id),
                file_id=file.id,
                idempotency_key=f"mineru:{job.id}:0",
                payload={"job_id": job.id},
                state="queued",
            )
        )
        setup.commit()

        barrier = threading.Barrier(2)
        real_claim = gpu_scheduler_dispatch.claim_gpu_route

        def gated_claim(db, **kwargs):
            barrier.wait(timeout=10)
            return real_claim(db, **kwargs)

        monkeypatch.setattr(
            gpu_scheduler_dispatch,
            "claim_gpu_route",
            gated_claim,
        )
        results = []
        published_payloads = []
        lock = threading.Lock()
        sessions = [Session(), Session()]

        def run(session, owner_id, gpu_id):
            try:
                result = gpu_scheduler_dispatch.dispatch_next_gpu_route(
                    session,
                    owner_id=owner_id,
                    gpu_id=gpu_id,
                    now=now,
                    publish=published_payloads.append,
                )
            except Exception as exc:  # surface thread failures in the assertion below
                result = exc
            finally:
                session.close()
            with lock:
                results.append(result)

        threads = [
            threading.Thread(target=run, args=(sessions[0], "scheduler-a", "0")),
            threading.Thread(target=run, args=(sessions[1], "scheduler-b", "1")),
        ]
        for thread in threads:
            thread.start()
        for thread in threads:
            thread.join()

        assert all(not isinstance(result, Exception) for result in results), repr(results)
        winners = [result for result in results if result is not None]
        assert len(winners) == 1
        assert published_payloads == [
            {"job_id": job.id, "attempt": 1, "handover_epoch": 0}
        ]
        assert setup.query(GpuSchedulerOutbox).filter_by(job_id=str(job.id)).one().state == "published"
        lease0 = setup.query(GpuSchedulerLease).filter_by(gpu_id="0").one()
        lease1 = setup.query(GpuSchedulerLease).filter_by(gpu_id="1").one()
        active_leases = [lease for lease in (lease0, lease1) if lease.state == "active"]
        released_leases = [lease for lease in (lease0, lease1) if lease.state == "released"]
        assert len(active_leases) == 1
        assert len(released_leases) == 1
        assert active_leases[0].active_job_id == str(job.id)
        assert released_leases[0].active_job_id is None
    finally:
        if job is not None and user_id is not None:
            _cleanup_committed_rows(setup, user_id=user_id, job_id=job.id)
        setup.close()


def test_choose_next_mixed_queued_and_published_candidates(db_session, regular_user):
    now = datetime(2026, 8, 1, 0, 0, 0)
    file = FileModel(
        filename="dispatch-10.pdf",
        original_name="dispatch-10.pdf",
        file_path="/tmp/dispatch-10.pdf",
        file_size=10,
        mime_type="application/pdf",
        user_id=regular_user.id,
    )
    db_session.add(file)
    db_session.flush()
    older = KbExtractJob(
        user_id=regular_user.id,
        file_id=file.id,
        provider="mineru",
        status="queued",
        created_at=now - timedelta(seconds=30),
    )
    newer = KbExtractJob(
        user_id=regular_user.id,
        file_id=file.id,
        provider="mineru",
        status="waiting_gpu",
        created_at=now,
    )
    db_session.add_all([older, newer])
    db_session.flush()
    db_session.add_all(
        [
            GpuSchedulerOutbox(
                job_kind="mineru",
                job_id=str(older.id),
                file_id=file.id,
                idempotency_key=f"mineru:{older.id}:0",
                payload={"job_id": older.id},
                state="queued",
            ),
            GpuSchedulerOutbox(
                job_kind="mineru",
                job_id=str(newer.id),
                file_id=file.id,
                idempotency_key=f"mineru:{newer.id}:0",
                payload={"job_id": newer.id},
                state="published",
            ),
        ]
    )
    db_session.flush()

    all_candidates = list_waiting_gpu_jobs(db_session)
    assert {item.job_id for item in all_candidates} == {str(older.id), str(newer.id)}
    publishable = list_waiting_gpu_jobs(db_session, publishable_only=True)
    assert [item.job_id for item in publishable] == [str(older.id)]

    selected, _decision = choose_next_waiting_gpu_job(db_session, now=now)
    assert selected.job_id == str(older.id)
    queued_selected, _decision = choose_next_waiting_gpu_job(db_session, now=now, publishable_only=True)
    assert queued_selected.job_id == str(older.id)


def test_same_numeric_job_id_across_kinds_dispatches_correct_route(db_session, regular_user):
    now = datetime(2026, 8, 1, 0, 0, 0)
    file = FileModel(
        filename="dispatch-11.pdf",
        original_name="dispatch-11.pdf",
        file_path="/tmp/dispatch-11.pdf",
        file_size=10,
        mime_type="application/pdf",
        user_id=regular_user.id,
    )
    db_session.add(file)
    db_session.flush()
    shared_id = 424242
    extract = KbExtractJob(
        id=shared_id,
        user_id=regular_user.id,
        file_id=file.id,
        provider="mineru",
        status="queued",
        created_at=now,
    )
    post = KbPostJob(
        id=shared_id,
        user_id=regular_user.id,
        file_id=file.id,
        status="queued",
        created_at=now - timedelta(seconds=901),
    )
    db_session.add_all([extract, post])
    db_session.flush()
    db_session.add_all(
        [
            GpuSchedulerOutbox(
                job_kind="mineru",
                job_id=str(shared_id),
                file_id=file.id,
                idempotency_key=f"mineru:{shared_id}:0",
                payload={"job_id": shared_id},
                state="queued",
            ),
            GpuSchedulerOutbox(
                job_kind="raptor",
                job_id=str(shared_id),
                file_id=file.id,
                idempotency_key=f"raptor:{shared_id}:0",
                payload={"job_id": shared_id},
                state="queued",
            ),
        ]
    )
    db_session.flush()

    selected, _decision = choose_next_waiting_gpu_job(db_session, now=now)
    assert selected.job_kind == "raptor"
    assert selected.job_id == str(shared_id)

    published_payloads = []
    result = dispatch_next_gpu_route(
        db_session,
        owner_id="scheduler-a",
        gpu_id="0",
        now=now,
        publish=published_payloads.append,
    )
    assert result is not None
    assert result.candidate.job_kind == "raptor"
    assert result.candidate.job_id == str(shared_id)
    assert published_payloads == [
        {"job_id": shared_id, "attempt": 1, "handover_epoch": 0}
    ]
    published_route = db_session.query(GpuSchedulerOutbox).filter_by(state="published").one()
    assert published_route.job_kind == "raptor"
    mineru_route = db_session.query(GpuSchedulerOutbox).filter_by(job_kind="mineru").one()
    assert mineru_route.state == "queued"
