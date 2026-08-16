# Copyright (c) 2026 徐泽宇
"""044 stage 5: Insavlo webhook timeout scanner."""

from __future__ import annotations

from datetime import timedelta
from unittest.mock import patch

from sqlalchemy import text

from models.file import File as FileModel
from models.kb_extract_job import KbExtractJob
from models.operation_log import OperationLog
from services.insavlo_webhook_timeout_scheduler import (
    INSAVLO_WEBHOOK_TIMEOUT_ERROR,
    INSAVLO_WEBHOOK_TIMEOUT_LOCK_KEY,
    compute_webhook_timeout_scan_interval_sec,
    scan_insavlo_webhook_timeouts,
)
from services.kb_extract_service import JOB_DONE, JOB_ERROR, JOB_WAITING_WEBHOOK, STATUS_FAILED
from services.kb_pipeline_log_service import (
    ACTION_INSAVLO_WEBHOOK_TIMEOUT,
    ACTION_KB_EXTRACT_ERROR,
)
from services.system_setting_service import (
    KEY_KB_EXTRACT_INSAVLO_API_KEY,
    KEY_KB_EXTRACT_INSAVLO_BASE_URL,
    KEY_KB_EXTRACT_INSAVLO_CALLBACK_ORIGIN,
    KEY_KB_EXTRACT_INSAVLO_ENABLED,
    KEY_KB_EXTRACT_INSAVLO_SKILL_CODE,
    KEY_KB_EXTRACT_INSAVLO_TIMEOUT_MINUTES,
    KEY_KB_EXTRACT_INSAVLO_WEBHOOK_SECRET,
    update_settings,
)
from utils.timezone import naive_db_now


def _configure_insavlo(db_session, *, timeout_minutes="2"):
    update_settings(
        db_session,
        {
            KEY_KB_EXTRACT_INSAVLO_ENABLED: "true",
            KEY_KB_EXTRACT_INSAVLO_BASE_URL: "https://demo.insavlo.com/insavlo/public-api/",
            KEY_KB_EXTRACT_INSAVLO_CALLBACK_ORIGIN: "https://ding.yyyou.top/",
            KEY_KB_EXTRACT_INSAVLO_SKILL_CODE: "filex-md",
            KEY_KB_EXTRACT_INSAVLO_API_KEY: "insavlo-api-key",
            KEY_KB_EXTRACT_INSAVLO_WEBHOOK_SECRET: "insavlo-webhook-secret",
            KEY_KB_EXTRACT_INSAVLO_TIMEOUT_MINUTES: timeout_minutes,
        },
    )


def _pdf(db_session, regular_user, name="timeout.pdf"):
    f = FileModel(
        filename=name,
        original_name=name,
        file_path=f"/tmp/{name}",
        file_size=100,
        mime_type="application/pdf",
        user_id=regular_user.id,
        has_md=False,
        extract_status="extracting",
    )
    db_session.add(f)
    db_session.commit()
    db_session.refresh(f)
    return f


def _waiting_job(db_session, regular_user, f, *, transaction_id="tx-to", submitted_at=None,
                 remote=True):
    job = KbExtractJob(
        user_id=regular_user.id,
        file_id=f.id,
        status=JOB_WAITING_WEBHOOK,
        provider="insavlo",
        remote_transaction_id=transaction_id,
        remote_file_id="remote-1",
        remote_skill_code="filex-md",
        remote_submitted_at=submitted_at if remote else None,
    )
    db_session.add(job)
    db_session.commit()
    db_session.refresh(job)
    return job


@patch("messaging.kb_extract_publisher.publish_file_extract_notify")
def test_scan_marks_timed_out_job_failed(mock_notify, db_session, regular_user):
    _configure_insavlo(db_session, timeout_minutes="2")
    f = _pdf(db_session, regular_user)
    job = _waiting_job(
        db_session, regular_user, f, submitted_at=naive_db_now() - timedelta(minutes=5)
    )

    n = scan_insavlo_webhook_timeouts(db_session)

    assert n == 1
    db_session.refresh(job)
    db_session.refresh(f)
    assert job.status == JOB_ERROR
    assert job.last_error == INSAVLO_WEBHOOK_TIMEOUT_ERROR
    assert f.extract_status == STATUS_FAILED
    assert f.extract_error == INSAVLO_WEBHOOK_TIMEOUT_ERROR
    mock_notify.assert_called_once()


@patch("messaging.kb_extract_publisher.publish_file_extract_notify")
def test_scan_timeout_writes_operation_logs(mock_notify, db_session, regular_user):
    _configure_insavlo(db_session, timeout_minutes="2")
    f = _pdf(db_session, regular_user)
    job = _waiting_job(
        db_session, regular_user, f, submitted_at=naive_db_now() - timedelta(minutes=5)
    )

    scan_insavlo_webhook_timeouts(db_session)

    logs = (
        db_session.query(OperationLog)
        .filter(OperationLog.user_id == regular_user.id, OperationLog.target_id == f.id)
        .order_by(OperationLog.id)
        .all()
    )
    actions = [log.action for log in logs]
    assert ACTION_INSAVLO_WEBHOOK_TIMEOUT in actions
    assert ACTION_KB_EXTRACT_ERROR in actions
    timeout_log = next(log for log in logs if log.action == ACTION_INSAVLO_WEBHOOK_TIMEOUT)
    assert f"job_id={job.id}" in (timeout_log.detail or "")
    assert f"transaction_id={job.remote_transaction_id}" in (timeout_log.detail or "")
    assert "timeout_minutes=2" in (timeout_log.detail or "")
    mock_notify.assert_called_once()


@patch("messaging.kb_extract_publisher.publish_file_extract_notify")
def test_scan_skips_fresh_job(mock_notify, db_session, regular_user):
    _configure_insavlo(db_session, timeout_minutes="24")
    f = _pdf(db_session, regular_user)
    job = _waiting_job(db_session, regular_user, f, submitted_at=naive_db_now())

    n = scan_insavlo_webhook_timeouts(db_session)

    assert n == 0
    db_session.refresh(job)
    assert job.status == JOB_WAITING_WEBHOOK
    assert f.extract_status == "extracting"
    mock_notify.assert_not_called()


@patch("messaging.kb_extract_publisher.publish_file_extract_notify")
def test_scan_uses_updated_at_fallback_when_remote_submitted_at_none(mock_notify, db_session, regular_user):
    _configure_insavlo(db_session, timeout_minutes="2")
    f = _pdf(db_session, regular_user)
    job = _waiting_job(db_session, regular_user, f, remote=False)
    # Force updated_at into the past (beyond the 2m timeout).
    db_session.execute(
        text("UPDATE kb_extract_jobs SET updated_at = :t WHERE id = :id"),
        {"t": naive_db_now() - timedelta(minutes=5), "id": job.id},
    )
    db_session.commit()

    n = scan_insavlo_webhook_timeouts(db_session)

    assert n == 1
    db_session.refresh(job)
    assert job.status == JOB_ERROR
    assert job.last_error == INSAVLO_WEBHOOK_TIMEOUT_ERROR


@patch("messaging.kb_extract_publisher.publish_file_extract_notify")
def test_scan_idempotent(mock_notify, db_session, regular_user):
    _configure_insavlo(db_session, timeout_minutes="2")
    f = _pdf(db_session, regular_user)
    _waiting_job(
        db_session, regular_user, f, submitted_at=naive_db_now() - timedelta(minutes=5)
    )

    assert scan_insavlo_webhook_timeouts(db_session) == 1
    # Second scan: job already error, no waiting_webhook candidates.
    assert scan_insavlo_webhook_timeouts(db_session) == 0


@patch("messaging.kb_extract_publisher.publish_file_extract_notify")
def test_scan_ignores_done_and_non_insavlo_jobs(mock_notify, db_session, regular_user):
    _configure_insavlo(db_session, timeout_minutes="2")
    f = _pdf(db_session, regular_user)
    # A done insavlo job (old submitted_at) must not be touched.
    done = KbExtractJob(
        user_id=regular_user.id,
        file_id=f.id,
        status=JOB_DONE,
        provider="insavlo",
        remote_transaction_id="tx-done",
        remote_submitted_at=naive_db_now() - timedelta(hours=48),
    )
    # A non-insavlo waiting_webhook job (defensive) must not be touched.
    other = KbExtractJob(
        user_id=regular_user.id,
        file_id=f.id,
        status=JOB_WAITING_WEBHOOK,
        provider="legacy",
        remote_submitted_at=naive_db_now() - timedelta(hours=48),
    )
    db_session.add_all([done, other])
    db_session.commit()

    n = scan_insavlo_webhook_timeouts(db_session)

    assert n == 0
    db_session.refresh(done)
    db_session.refresh(other)
    assert done.status == JOB_DONE
    assert other.status == JOB_WAITING_WEBHOOK


@patch("messaging.kb_extract_publisher.publish_file_extract_notify")
def test_scan_advisory_lock_mutex(mock_notify, db_session, regular_user, engine):
    _configure_insavlo(db_session, timeout_minutes="2")
    f = _pdf(db_session, regular_user)
    job = _waiting_job(
        db_session, regular_user, f, submitted_at=naive_db_now() - timedelta(minutes=5)
    )

    # Hold the dedicated timeout advisory lock on a different connection.
    blocker = engine.connect()
    try:
        assert blocker.execute(
            text("SELECT pg_try_advisory_lock(:k)"), {"k": INSAVLO_WEBHOOK_TIMEOUT_LOCK_KEY}
        ).scalar() is True
        # Scanner cannot acquire the lock -> returns 0 and leaves the job alone.
        assert scan_insavlo_webhook_timeouts(db_session) == 0
        db_session.refresh(job)
        assert job.status == JOB_WAITING_WEBHOOK
        blocker.execute(
            text("SELECT pg_advisory_unlock(:k)"), {"k": INSAVLO_WEBHOOK_TIMEOUT_LOCK_KEY}
        )
    finally:
        blocker.close()

    # After releasing, the scanner can acquire the lock and mark the timeout.
    assert scan_insavlo_webhook_timeouts(db_session) == 1
    db_session.refresh(job)
    assert job.status == JOB_ERROR


def test_compute_scan_interval_short_timeout():
    assert compute_webhook_timeout_scan_interval_sec(2) == 30.0


def test_compute_scan_interval_long_timeout_capped():
    assert compute_webhook_timeout_scan_interval_sec(120) == 900.0
