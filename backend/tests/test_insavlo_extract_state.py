# Copyright (c) 2026 徐泽宇
"""Insavlo extract job state machine."""

from datetime import datetime, timedelta
from unittest.mock import patch

from sqlalchemy.orm import sessionmaker

from config import GPU_SCHEDULER_OWNER_ID, GPU_SCHEDULER_TTL_SEC, KB_EXTRACT_RUNNING_STALE_SEC
from models.file import File as FileModel
from models.gpu_scheduler import GpuSchedulerLease, GpuSchedulerOutbox
from models.insavlo_webhook_event import InsavloWebhookEvent
from models.kb_extract_job import KbExtractJob
from services.gpu_scheduler_persistence import (
    acquire_gpu_lease,
    claim_gpu_execution,
    enqueue_gpu_route,
    find_gpu_route,
    publish_gpu_route,
)
from services.kb_extract_service import (
    JOB_ERROR,
    JOB_QUEUED,
    JOB_RUNNING,
    JOB_WAITING_WEBHOOK,
    STATUS_EXTRACTING,
    STATUS_PENDING,
    enqueue_extract,
    reconcile_stale_kb_extract_jobs,
    run_extract_job,
)
from services.extract.providers.insavlo_provider import InsavloSubmission


def _pdf(db_session, regular_user, name="insavlo.pdf"):
    f = FileModel(
        filename=name,
        original_name=name,
        file_path=f"/tmp/{name}",
        file_size=100,
        mime_type="application/pdf",
        user_id=regular_user.id,
        has_md=False,
    )
    db_session.add(f)
    db_session.commit()
    db_session.refresh(f)
    return f


def test_kb_extract_job_remote_fields_exist(db_session, regular_user):
    f = _pdf(db_session, regular_user)
    job = KbExtractJob(
        user_id=regular_user.id,
        file_id=f.id,
        status=JOB_WAITING_WEBHOOK,
        provider="insavlo",
        remote_transaction_id="tx-1",
        remote_file_id="remote-file-1",
        remote_skill_code="filex-md",
        remote_submitted_at=datetime.utcnow(),
    )
    db_session.add(job)
    db_session.commit()
    db_session.refresh(job)

    assert job.remote_transaction_id == "tx-1"
    assert job.remote_file_id == "remote-file-1"
    assert job.remote_skill_code == "filex-md"
    assert job.remote_submitted_at is not None
    assert job.remote_completed_at is None


def test_insavlo_webhook_event_model_exists(db_session, regular_user):
    f = _pdf(db_session, regular_user)
    job = KbExtractJob(
        user_id=regular_user.id,
        file_id=f.id,
        status=JOB_WAITING_WEBHOOK,
        provider="insavlo",
        remote_transaction_id="tx-event",
    )
    db_session.add(job)
    db_session.flush()
    event = InsavloWebhookEvent(
        transaction_id="tx-event",
        job_id=job.id,
        file_id=f.id,
        payload_json={"transaction_id": "tx-event"},
    )
    db_session.add(event)
    db_session.commit()
    db_session.refresh(event)

    assert event.status == "pending"
    assert event.attempts == 0
    assert event.processed_at is None


def test_enqueue_extract_treats_waiting_webhook_as_active(db_session, regular_user):
    f = _pdf(db_session, regular_user)
    existing = KbExtractJob(
        user_id=regular_user.id,
        file_id=f.id,
        status=JOB_WAITING_WEBHOOK,
        provider="insavlo",
        remote_transaction_id="tx-active",
    )
    db_session.add(existing)
    db_session.commit()

    new_job_id = enqueue_extract(db_session, regular_user.id, f.id, provider="insavlo")
    db_session.commit()

    assert new_job_id is not None
    db_session.refresh(existing)
    assert existing.status == JOB_WAITING_WEBHOOK
    new_job = db_session.query(KbExtractJob).filter(KbExtractJob.id == new_job_id).one()
    assert new_job.status == JOB_QUEUED
    assert new_job.provider == "insavlo"
    assert f.extract_status == STATUS_EXTRACTING


def test_enqueue_extract_keeps_extracting_when_running_job_is_active(db_session, regular_user):
    f = _pdf(db_session, regular_user)
    f.extract_status = STATUS_EXTRACTING
    existing = KbExtractJob(
        user_id=regular_user.id,
        file_id=f.id,
        status=JOB_RUNNING,
        provider="legacy",
    )
    db_session.add(existing)
    db_session.commit()

    new_job_id = enqueue_extract(db_session, regular_user.id, f.id, provider="insavlo")
    db_session.commit()

    assert new_job_id is not None
    db_session.refresh(f)
    assert f.extract_status == STATUS_EXTRACTING


def test_force_reextract_supersedes_waiting_webhook_job(db_session, regular_user):
    f = _pdf(db_session, regular_user)
    existing = KbExtractJob(
        user_id=regular_user.id,
        file_id=f.id,
        status=JOB_WAITING_WEBHOOK,
        provider="insavlo",
        remote_transaction_id="tx-old",
    )
    db_session.add(existing)
    db_session.commit()

    new_job_id = enqueue_extract(
        db_session,
        regular_user.id,
        f.id,
        provider="insavlo",
        for_reextract=True,
    )
    db_session.commit()

    db_session.refresh(existing)
    assert existing.status == JOB_ERROR
    assert existing.last_error == "superseded by reextract"
    new_job = db_session.query(KbExtractJob).filter(KbExtractJob.id == new_job_id).one()
    assert new_job.status == JOB_QUEUED
    assert new_job.provider == "insavlo"


def test_reconcile_stale_running_with_remote_transaction_restores_waiting_webhook(db_session, regular_user):
    f = _pdf(db_session, regular_user)
    f.extract_status = STATUS_EXTRACTING
    job = KbExtractJob(
        user_id=regular_user.id,
        file_id=f.id,
        status=JOB_RUNNING,
        provider="insavlo",
        remote_transaction_id="tx-running",
    )
    db_session.add(job)
    db_session.commit()

    count = reconcile_stale_kb_extract_jobs(db_session)
    db_session.commit()

    assert count == 1
    db_session.refresh(job)
    db_session.refresh(f)
    assert job.status == JOB_WAITING_WEBHOOK
    assert f.extract_status == STATUS_EXTRACTING


def test_reconcile_stale_running_requeues_and_recovers_gpu_route(db_session, regular_user):
    """consumer 崩溃后 extract job 重排队时，executing route 必须退回 queued
    并释放 dispatch lease，否则调度循环永远不再选中该 job，gpu_id 卡死。"""
    f = _pdf(db_session, regular_user)
    f.extract_status = STATUS_EXTRACTING
    job = KbExtractJob(
        user_id=regular_user.id,
        file_id=f.id,
        status=JOB_RUNNING,
        provider="mineru",
    )
    db_session.add(job)
    db_session.flush()
    route = enqueue_gpu_route(
        db_session,
        job_kind="mineru",
        job_id=job.id,
        file_id=f.id,
        idempotency_key=f"mineru:{job.id}:0",
        payload={"job_id": job.id, "job_kind": "mineru", "file_id": f.id},
    )
    publish_gpu_route(db_session, outbox_id=route.id, publish=lambda _payload: None)
    claim_gpu_execution(db_session, job_kind="mineru", job_id=job.id)
    lease = acquire_gpu_lease(
        db_session,
        gpu_id="0",
        owner_id=GPU_SCHEDULER_OWNER_ID,
        now=datetime.utcnow(),
    )
    lease.active_job_id = str(job.id)
    db_session.commit()

    count = reconcile_stale_kb_extract_jobs(db_session)
    db_session.commit()

    assert count == 1
    db_session.refresh(job)
    assert job.status == JOB_QUEUED
    db_session.expire_all()
    route = find_gpu_route(db_session, job_kind="mineru", job_id=job.id)
    assert route.state == "queued"
    assert route.handover_epoch == 1
    lease = db_session.query(GpuSchedulerLease).filter_by(gpu_id="0").one()
    assert lease.state == "released"
    assert lease.active_job_id is None


def test_reconcile_skips_fresh_running_job_when_stale_seconds_set(db_session, regular_user):
    """周期 reconcile 必须带 stale 门控：新鲜 running job（无 GPU lease）不得
    被误回收，否则长任务会被重复执行。"""
    f = _pdf(db_session, regular_user)
    job = KbExtractJob(
        user_id=regular_user.id,
        file_id=f.id,
        status=JOB_RUNNING,
        provider="legacy",
    )
    db_session.add(job)
    db_session.commit()

    count = reconcile_stale_kb_extract_jobs(db_session, stale_seconds=3600)
    db_session.commit()

    assert count == 0
    db_session.refresh(job)
    assert job.status == JOB_RUNNING


def test_reconcile_recovers_stale_running_job_after_threshold_without_lease(
    db_session, regular_user
):
    """无 GPU lease 的 running job 超过 updated_at 阈值后应被重排队。"""
    f = _pdf(db_session, regular_user)
    f.extract_status = STATUS_EXTRACTING
    job = KbExtractJob(
        user_id=regular_user.id,
        file_id=f.id,
        status=JOB_RUNNING,
        provider="legacy",
        updated_at=datetime.now() - timedelta(seconds=3601),
    )
    db_session.add(job)
    db_session.commit()

    count = reconcile_stale_kb_extract_jobs(db_session, stale_seconds=3600)
    db_session.commit()

    assert count == 1
    db_session.refresh(job)
    db_session.refresh(f)
    assert job.status == JOB_QUEUED
    assert f.extract_status == STATUS_PENDING


def test_reconcile_recovers_running_job_after_watchdog_confirmations(
    db_session, regular_user, monkeypatch
):
    """GPU 调度模式下 lease heartbeat 是权威 liveness：scheduler 崩溃后心跳
    停止；但执行中 lease 必须由 watchdog 连续两次（间隔 5s）确认 GPU 进程为
    空后才重排队并恢复 route/lease，liveness 丢失本身不构成回收授权。"""
    import services.kb_extract_service as extract_service

    f = _pdf(db_session, regular_user)
    f.extract_status = STATUS_EXTRACTING
    job = KbExtractJob(
        user_id=regular_user.id,
        file_id=f.id,
        status=JOB_RUNNING,
        provider="mineru",
    )
    db_session.add(job)
    db_session.flush()
    route = enqueue_gpu_route(
        db_session,
        job_kind="mineru",
        job_id=job.id,
        file_id=f.id,
        idempotency_key=f"mineru:{job.id}:0",
        payload={"job_id": job.id, "job_kind": "mineru", "file_id": f.id},
    )
    publish_gpu_route(db_session, outbox_id=route.id, publish=lambda _payload: None)
    claim_gpu_execution(db_session, job_kind="mineru", job_id=job.id)
    now = datetime(2026, 8, 1, 0, 0, 0)
    lease = acquire_gpu_lease(
        db_session,
        gpu_id="0",
        owner_id=GPU_SCHEDULER_OWNER_ID,
        now=now - timedelta(seconds=2 * GPU_SCHEDULER_TTL_SEC + 1),
    )
    lease.active_job_id = str(job.id)
    db_session.commit()
    monkeypatch.setattr(extract_service, "naive_db_now", lambda: now)
    monkeypatch.setattr(
        "services.gpu_watchdog.gpu_round_idle", lambda job_kind, lease: True
    )

    # 第一次空采样：记录确认 #1，job 保持 running。
    count = reconcile_stale_kb_extract_jobs(
        db_session, stale_seconds=KB_EXTRACT_RUNNING_STALE_SEC
    )
    db_session.commit()
    assert count == 0
    db_session.expire_all()
    assert db_session.get(KbExtractJob, job.id).status == JOB_RUNNING
    lease = db_session.query(GpuSchedulerLease).filter_by(gpu_id="0").one()
    assert lease.state == "active"
    assert lease.watchdog_empty_confirmations == 1

    # 第二次空采样（间隔 >= 5s）：确认 #2，允许重排队并恢复 route/lease。
    monkeypatch.setattr(
        extract_service, "naive_db_now", lambda: now + timedelta(seconds=5)
    )
    count = reconcile_stale_kb_extract_jobs(
        db_session, stale_seconds=KB_EXTRACT_RUNNING_STALE_SEC
    )
    db_session.commit()

    assert count == 1
    db_session.refresh(job)
    assert job.status == JOB_QUEUED
    db_session.expire_all()
    route = find_gpu_route(db_session, job_kind="mineru", job_id=job.id)
    assert route.state == "queued"
    lease = db_session.query(GpuSchedulerLease).filter_by(gpu_id="0").one()
    assert lease.state == "released"
    assert lease.active_job_id is None


def test_reconcile_keeps_running_job_when_gpu_busy_despite_stale_lease(
    db_session, regular_user, monkeypatch
):
    """loop 停滞但执行仍在进行（或双 worker 下另一执行轮持有 GPU）时，心跳
    停止的 job 不得被旧 consumer 误回收：watchdog 探测非空即保持 running。"""
    import services.kb_extract_service as extract_service

    f = _pdf(db_session, regular_user)
    f.extract_status = STATUS_EXTRACTING
    job = KbExtractJob(
        user_id=regular_user.id,
        file_id=f.id,
        status=JOB_RUNNING,
        provider="mineru",
    )
    db_session.add(job)
    db_session.flush()
    route = enqueue_gpu_route(
        db_session,
        job_kind="mineru",
        job_id=job.id,
        file_id=f.id,
        idempotency_key=f"mineru:{job.id}:0",
        payload={"job_id": job.id, "job_kind": "mineru", "file_id": f.id},
    )
    publish_gpu_route(db_session, outbox_id=route.id, publish=lambda _payload: None)
    claim_gpu_execution(db_session, job_kind="mineru", job_id=job.id)
    now = datetime(2026, 8, 1, 0, 0, 0)
    lease = acquire_gpu_lease(
        db_session,
        gpu_id="0",
        owner_id=GPU_SCHEDULER_OWNER_ID,
        now=now - timedelta(seconds=2 * GPU_SCHEDULER_TTL_SEC + 1),
    )
    lease.active_job_id = str(job.id)
    db_session.commit()
    monkeypatch.setattr(extract_service, "naive_db_now", lambda: now)
    monkeypatch.setattr(
        "services.gpu_watchdog.gpu_round_idle", lambda job_kind, lease: False
    )

    count = reconcile_stale_kb_extract_jobs(
        db_session, stale_seconds=KB_EXTRACT_RUNNING_STALE_SEC
    )
    db_session.commit()
    assert count == 0
    monkeypatch.setattr(
        extract_service, "naive_db_now", lambda: now + timedelta(seconds=5)
    )
    count = reconcile_stale_kb_extract_jobs(
        db_session, stale_seconds=KB_EXTRACT_RUNNING_STALE_SEC
    )
    db_session.commit()
    assert count == 0
    db_session.expire_all()
    assert db_session.get(KbExtractJob, job.id).status == JOB_RUNNING
    route = find_gpu_route(db_session, job_kind="mineru", job_id=job.id)
    assert route.state == "executing"
    lease = db_session.query(GpuSchedulerLease).filter_by(gpu_id="0").one()
    assert lease.state == "active"
    assert lease.watchdog_empty_confirmations == 0


def test_extract_replay_loop_invokes_periodic_stale_reconcile(engine, monkeypatch):
    """kb-extract 消费者必须周期调用带 stale 门控的 reconcile，否则 GPU
    scheduler 崩溃后的 running MinerU job 没有恢复路径。"""
    from messaging import kb_extract_consumer as mod

    called = {}

    def fake_reconcile(db, *, stale_seconds):
        called["stale_seconds"] = stale_seconds
        return 1

    def fake_replay(db, *, full):
        called["full"] = full
        return 0

    class _StopOnce:
        def __init__(self):
            self._flag = False

        def is_set(self):
            return self._flag

        def wait(self, _seconds):
            self._flag = True

        def clear(self):
            self._flag = False

        def set(self):
            self._flag = True

    monkeypatch.setattr(mod, "SessionLocal", lambda: sessionmaker(bind=engine)())
    monkeypatch.setattr(mod, "require_license_or_wait", lambda _db: True)
    from services import kb_extract_service

    monkeypatch.setattr(kb_extract_service, "reconcile_stale_kb_extract_jobs", fake_reconcile)
    monkeypatch.setattr(mod, "replay_queued_jobs", fake_replay)
    monkeypatch.setattr(mod, "_replay_stop", _StopOnce())

    mod._replay_loop()

    assert called == {
        "stale_seconds": KB_EXTRACT_RUNNING_STALE_SEC,
        "full": True,
    }


def test_run_extract_job_insavlo_submission_enters_waiting_webhook(db_session, regular_user):
    f = _pdf(db_session, regular_user)
    job = KbExtractJob(
        user_id=regular_user.id,
        file_id=f.id,
        status=JOB_QUEUED,
        provider="insavlo",
    )
    db_session.add(job)
    db_session.commit()
    submitted_at = datetime.utcnow()

    with patch(
        "services.extract.providers.insavlo_provider.submit_insavlo_extract",
        return_value=InsavloSubmission(
            transaction_id="tx-submit",
            file_id="remote-submit",
            skill_code="filex-md",
            submitted_at=submitted_at,
        ),
    ), patch("services.kb_extract_service.persist_extract_result") as mock_persist:
        run_extract_job(db_session, job)
        db_session.commit()

    db_session.refresh(job)
    db_session.refresh(f)
    assert job.status == JOB_WAITING_WEBHOOK
    assert job.remote_transaction_id == "tx-submit"
    assert job.remote_file_id == "remote-submit"
    assert job.remote_skill_code == "filex-md"
    assert job.remote_submitted_at == submitted_at
    assert f.extract_status == STATUS_EXTRACTING
    mock_persist.assert_not_called()


def test_run_extract_job_defers_queued_job_when_same_file_has_active_waiting_webhook(db_session, regular_user):
    f = _pdf(db_session, regular_user)
    active = KbExtractJob(
        user_id=regular_user.id,
        file_id=f.id,
        status=JOB_WAITING_WEBHOOK,
        provider="insavlo",
        remote_transaction_id="tx-active",
    )
    queued = KbExtractJob(
        user_id=regular_user.id,
        file_id=f.id,
        status=JOB_QUEUED,
        provider="insavlo",
    )
    db_session.add_all([active, queued])
    db_session.commit()

    with patch("services.extract.providers.insavlo_provider.submit_insavlo_extract") as mock_submit:
        run_extract_job(db_session, queued)
        db_session.commit()

    db_session.refresh(queued)
    db_session.refresh(f)
    assert queued.status == JOB_QUEUED
    assert queued.attempts == 0
    assert queued.remote_transaction_id is None
    assert f.extract_status == STATUS_EXTRACTING
    mock_submit.assert_not_called()


def test_consumer_defers_queued_job_when_same_file_has_active_waiting_webhook(db_session, regular_user):
    from messaging.kb_extract_consumer import _handle_job

    f = _pdf(db_session, regular_user)
    active = KbExtractJob(
        user_id=regular_user.id,
        file_id=f.id,
        status=JOB_WAITING_WEBHOOK,
        provider="insavlo",
        remote_transaction_id="tx-active",
    )
    queued = KbExtractJob(
        user_id=regular_user.id,
        file_id=f.id,
        status=JOB_QUEUED,
        provider="insavlo",
    )
    db_session.add_all([active, queued])
    db_session.commit()

    with (
        patch("messaging.kb_extract_consumer.publish_file_extract_notify"),
        patch("messaging.kb_extract_consumer.publish_kb_extract_retry") as mock_retry,
        patch("messaging.kb_extract_consumer.publish_kb_extract_dlq") as mock_dlq,
        patch("services.extract.providers.insavlo_provider.submit_insavlo_extract") as mock_submit,
    ):
        _handle_job(db_session, queued.id, object())

    db_session.refresh(queued)
    db_session.refresh(f)
    assert queued.status == JOB_QUEUED
    assert queued.attempts == 0
    assert queued.remote_transaction_id is None
    assert f.extract_status == STATUS_EXTRACTING
    mock_submit.assert_not_called()
    mock_retry.assert_not_called()
    mock_dlq.assert_not_called()
