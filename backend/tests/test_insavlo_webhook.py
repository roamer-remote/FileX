# Copyright (c) 2026 徐泽宇
"""044 stage 4: Insavlo webhook receiver + async write-back."""

from __future__ import annotations

import hashlib
import hmac
import json
import os
from datetime import datetime
from unittest.mock import patch

import logging

import pytest

from config import KB_EXTRACT_INSAVLO_MAX_FILE_BYTES
from middleware.license import is_license_allowlisted
from models.file import File as FileModel
from models.insavlo_webhook_event import InsavloWebhookEvent
from models.kb_extract_job import KbExtractJob
from services.insavlo_markdown_renderer import render_insavlo_markdown
from services.insavlo_webhook_writeback import (
    EVENT_DONE,
    EVENT_ERROR,
    EVENT_PENDING,
    process_insavlo_writeback_once,
)
from services.kb_extract_service import JOB_DONE, JOB_ERROR, JOB_WAITING_WEBHOOK
from services.md_paths import md_note_path
from routers.insavlo_webhook import WEBHOOK_BODY_MAX_BYTES
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

WEBHOOK_URL = "/api/webhooks/insavlo/document-process"
WEBHOOK_SECRET = "insavlo-webhook-secret"


def _configure_insavlo(db_session):
    update_settings(
        db_session,
        {
            KEY_KB_EXTRACT_INSAVLO_ENABLED: "true",
            KEY_KB_EXTRACT_INSAVLO_BASE_URL: "https://demo.insavlo.com/insavlo/public-api/",
            KEY_KB_EXTRACT_INSAVLO_CALLBACK_ORIGIN: "https://ding.yyyou.top/",
            KEY_KB_EXTRACT_INSAVLO_SKILL_CODE: "filex-md",
            KEY_KB_EXTRACT_INSAVLO_API_KEY: "insavlo-api-key",
            KEY_KB_EXTRACT_INSAVLO_WEBHOOK_SECRET: WEBHOOK_SECRET,
            KEY_KB_EXTRACT_INSAVLO_TIMEOUT_MINUTES: "72",
        },
    )


def _pdf(db_session, regular_user, name="invoice.pdf"):
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


def _waiting_webhook_job(db_session, regular_user, f, transaction_id="tx-1", remote_file_id="remote-1"):
    job = KbExtractJob(
        user_id=regular_user.id,
        file_id=f.id,
        status=JOB_WAITING_WEBHOOK,
        provider="insavlo",
        remote_transaction_id=transaction_id,
        remote_file_id=remote_file_id,
        remote_skill_code="filex-md",
        remote_submitted_at=datetime.utcnow(),
    )
    db_session.add(job)
    db_session.commit()
    db_session.refresh(job)
    return job


def _completed_payload(transaction_id="tx-1", file_id="remote-1", result=None, file_status="completed"):
    if result is None:
        result = {"INVOICE_NO": "INV-2024-001", "INVOICE_DATE": "2024-01-01", "AMOUNT": "1,026.50"}
    return {
        "event": "document_process.completed",
        "transaction_id": transaction_id,
        "status": "completed",
        "skill_code": "filex-md",
        "files": [
            {
                "file_id": file_id,
                "file_name": "invoice.pdf",
                "status": file_status,
                "skill_code": "filex-md",
                "result": result,
            }
        ],
        "timestamp": "2026-06-19T12:00:00Z",
    }


def _sign(secret: str, raw: bytes) -> str:
    return "sha256=" + hmac.new(secret.encode("utf-8"), raw, hashlib.sha256).hexdigest()


def _post(client, payload, *, secret=WEBHOOK_SECRET, event="document_process.completed",
          transaction_id=None, signature=None, content_type="application/json",
          x_transaction_id=None, raw=None, extra_headers=None):
    body = raw if raw is not None else json.dumps(payload, ensure_ascii=False).encode("utf-8")
    tid = transaction_id if transaction_id is not None else payload.get("transaction_id", "")
    sig = signature if signature is not None else _sign(secret, body)
    headers = {
        "content-type": content_type,
        "x-webhook-event": event,
        "x-transaction-id": x_transaction_id if x_transaction_id is not None else tid,
        "x-webhook-signature": sig,
    }
    if extra_headers:
        headers.update(extra_headers)
    return client.post(WEBHOOK_URL, content=body, headers=headers)


# ── renderer ────────────────────────────────────────────────


def test_render_insavlo_markdown_scalar_table_and_json_appendix():
    md = render_insavlo_markdown(
        original_name="invoice.pdf",
        transaction_id="tx-1",
        file_id="remote-1",
        skill_code="filex-md",
        result={"INVOICE_NO": "INV-1", "AMOUNT": "100", "items": [{"name": "A", "qty": 2}]},
    )
    assert "# invoice.pdf" in md
    assert "INV-1" in md
    assert "## items" in md
    assert "| name | qty |" in md
    assert "```json" in md
    assert "INV-1" in md  # scalar rendered
    assert "raw" not in md.split("```json")[1]  # json block present


def test_render_insavlo_markdown_flattens_nested_objects_and_confidence():
    md = render_insavlo_markdown(
        original_name="d.pdf",
        transaction_id="tx-2",
        file_id="remote-2",
        skill_code="filex-md",
        result={
            "seller": {"name": "ACME", "tax_id": "T-1"},
            "total": {"$value": "1,026.50", "$confidence_flag": "high"},
        },
    )
    assert "seller.name" in md
    assert "seller.tax_id" in md
    assert "1,026.50" in md
    assert "置信: high" in md


# ── HTTP receiver ───────────────────────────────────────────


def test_webhook_rejects_wrong_event_header(client, db_session, regular_user):
    _configure_insavlo(db_session)
    f = _pdf(db_session, regular_user)
    _waiting_webhook_job(db_session, regular_user, f)
    payload = _completed_payload()
    resp = _post(client, payload, event="something.else")
    assert resp.status_code == 400
    assert db_session.query(InsavloWebhookEvent).count() == 0


def test_webhook_rejects_bad_signature(client, db_session, regular_user, caplog):
    _configure_insavlo(db_session)
    f = _pdf(db_session, regular_user)
    job = _waiting_webhook_job(db_session, regular_user, f)
    with caplog.at_level(logging.WARNING, logger="routers.insavlo_webhook"):
        resp = _post(client, _completed_payload(), signature="sha256=deadbeef")
    assert resp.status_code == 401
    assert db_session.query(InsavloWebhookEvent).count() == 0
    db_session.refresh(job)
    assert job.status == JOB_WAITING_WEBHOOK
    assert any(
        r.levelno == logging.WARNING and "reason=signature_invalid" in r.getMessage()
        for r in caplog.records
    )


def test_webhook_rejects_missing_signature(client, db_session, regular_user):
    _configure_insavlo(db_session)
    f = _pdf(db_session, regular_user)
    _waiting_webhook_job(db_session, regular_user, f)
    resp = _post(client, _completed_payload(), signature="")
    assert resp.status_code == 401


def test_webhook_rejects_transaction_id_mismatch(client, db_session, regular_user):
    _configure_insavlo(db_session)
    f = _pdf(db_session, regular_user)
    _waiting_webhook_job(db_session, regular_user, f)
    resp = _post(client, _completed_payload(), x_transaction_id="other-tx")
    assert resp.status_code == 400
    assert db_session.query(InsavloWebhookEvent).count() == 0


def test_webhook_rejects_non_json_content_type(client, db_session, regular_user):
    _configure_insavlo(db_session)
    f = _pdf(db_session, regular_user)
    _waiting_webhook_job(db_session, regular_user, f)
    resp = _post(client, _completed_payload(), content_type="text/plain")
    assert resp.status_code == 400


def test_webhook_rejects_invalid_content_length(client, db_session, regular_user):
    _configure_insavlo(db_session)
    f = _pdf(db_session, regular_user)
    _waiting_webhook_job(db_session, regular_user, f)
    resp = _post(
        client, _completed_payload(), extra_headers={"content-length": "abc"}
    )
    assert resp.status_code == 400
    assert db_session.query(InsavloWebhookEvent).count() == 0


def test_webhook_413_when_content_length_too_large(client, db_session, regular_user):
    _configure_insavlo(db_session)
    f = _pdf(db_session, regular_user)
    _waiting_webhook_job(db_session, regular_user, f)
    resp = _post(
        client,
        _completed_payload(),
        extra_headers={"content-length": str(WEBHOOK_BODY_MAX_BYTES + 1)},
    )
    assert resp.status_code == 413
    assert db_session.query(InsavloWebhookEvent).count() == 0


def test_late_webhook_after_supersede_does_not_writeback(client, db_session, regular_user):
    # SC-044-011: force reextract supersedes the old waiting_webhook job (-> error);
    # a late webhook for the old transaction returns 200, creates no event, and
    # never writes back Markdown or re-enqueues the index.
    from services.kb_extract_service import enqueue_extract

    _configure_insavlo(db_session)
    f = _pdf(db_session, regular_user)
    old = _waiting_webhook_job(db_session, regular_user, f, transaction_id="tx-old")

    new_job_id = enqueue_extract(
        db_session, regular_user.id, f.id, provider="insavlo", for_reextract=True
    )
    db_session.commit()
    db_session.refresh(old)
    assert old.status == JOB_ERROR
    assert old.last_error == "superseded by reextract"
    assert new_job_id is not None

    # Write-back loop is disabled in tests (conftest escape hatch), so the 200
    # path only persists an event for *active* jobs; the superseded job is
    # terminal (error) -> idempotent 200 with no event.
    resp = _post(client, _completed_payload(transaction_id="tx-old"))
    assert resp.status_code == 200
    # No event persisted for the superseded transaction; no markdown written.
    assert db_session.query(InsavloWebhookEvent).count() == 0
    assert not f.has_md
    assert not os.path.exists(md_note_path(f.id))


def test_webhook_returns_404_for_unknown_transaction(client, db_session, regular_user):
    _configure_insavlo(db_session)
    _pdf(db_session, regular_user)
    payload = _completed_payload(transaction_id="no-such-tx", file_id="x")
    resp = _post(client, payload, transaction_id="no-such-tx")
    assert resp.status_code == 404


def test_webhook_persists_event_and_returns_200_before_writeback(client, db_session, regular_user, caplog):
    _configure_insavlo(db_session)
    f = _pdf(db_session, regular_user)
    job = _waiting_webhook_job(db_session, regular_user, f, transaction_id="tx-200")

    with caplog.at_level(logging.INFO, logger="routers.insavlo_webhook"):
        resp = _post(client, _completed_payload(transaction_id="tx-200"))

    assert resp.status_code == 200
    # SC-044-012: event persisted (pending) and committed before 200; no writeback yet.
    events = db_session.query(InsavloWebhookEvent).all()
    assert len(events) == 1
    assert events[0].status == EVENT_PENDING
    assert events[0].transaction_id == "tx-200"
    assert events[0].job_id == job.id
    db_session.refresh(job)
    assert job.status == JOB_WAITING_WEBHOOK
    assert not f.has_md
    assert not os.path.exists(md_note_path(f.id))
    assert any(
        r.levelno == logging.INFO and "insavlo webhook received" in r.getMessage()
        for r in caplog.records
    )
    assert any(
        r.levelno == logging.INFO and "insavlo webhook event persisted" in r.getMessage()
        for r in caplog.records
    )


def test_webhook_idempotent_when_job_already_done(client, db_session, regular_user):
    _configure_insavlo(db_session)
    f = _pdf(db_session, regular_user)
    job = _waiting_webhook_job(db_session, regular_user, f, transaction_id="tx-done")
    job.status = JOB_DONE
    db_session.commit()

    resp = _post(client, _completed_payload(transaction_id="tx-done"))

    assert resp.status_code == 200
    assert db_session.query(InsavloWebhookEvent).count() == 0


def test_webhook_idempotent_when_job_error(client, db_session, regular_user):
    _configure_insavlo(db_session)
    f = _pdf(db_session, regular_user)
    job = _waiting_webhook_job(db_session, regular_user, f, transaction_id="tx-err")
    job.status = JOB_ERROR
    job.last_error = "superseded by reextract"
    db_session.commit()

    resp = _post(client, _completed_payload(transaction_id="tx-err"))

    assert resp.status_code == 200
    assert db_session.query(InsavloWebhookEvent).count() == 0


def test_webhook_duplicate_creates_no_second_event(client, db_session, regular_user):
    _configure_insavlo(db_session)
    f = _pdf(db_session, regular_user)
    _waiting_webhook_job(db_session, regular_user, f, transaction_id="tx-dup")

    r1 = _post(client, _completed_payload(transaction_id="tx-dup"))
    r2 = _post(client, _completed_payload(transaction_id="tx-dup"))

    assert r1.status_code == 200
    assert r2.status_code == 200
    assert db_session.query(InsavloWebhookEvent).filter(
        InsavloWebhookEvent.transaction_id == "tx-dup"
    ).count() == 1


def test_webhook_rejects_when_insavlo_not_configured(client, db_session, regular_user):
    # 未配置 -> 无 secret -> 401
    f = _pdf(db_session, regular_user)
    _waiting_webhook_job(db_session, regular_user, f, transaction_id="tx-nocfg")
    resp = _post(client, _completed_payload(transaction_id="tx-nocfg"))
    assert resp.status_code == 401


def test_license_allowlist_includes_insavlo_webhook():
    # SC-044-009: webhook path must bypass License gate so completed tasks can write back.
    assert is_license_allowlisted("/api/webhooks/insavlo/document-process") is True


# ── async write-back ────────────────────────────────────────


def _seed_pending_event(db_session, regular_user, *, transaction_id="tx-wb", payload=None,
                        remote_file_id="remote-1", file_status="completed", result=None,
                        file_msg=None):
    f = _pdf(db_session, regular_user)
    job = _waiting_webhook_job(
        db_session, regular_user, f, transaction_id=transaction_id, remote_file_id=remote_file_id
    )
    if payload is None:
        payload = _completed_payload(
            transaction_id=transaction_id, file_id=remote_file_id, file_status=file_status, result=result
        )
    if file_msg is not None and isinstance(payload.get("files"), list) and payload["files"]:
        payload["files"][0]["msg"] = file_msg
    event = InsavloWebhookEvent(
        transaction_id=transaction_id,
        job_id=job.id,
        file_id=f.id,
        payload_json=payload,
        status=EVENT_PENDING,
    )
    db_session.add(event)
    db_session.commit()
    db_session.refresh(event)
    return f, job, event


@patch("services.kb_index_service.publish_index_job")
@patch("messaging.kb_extract_publisher.publish_file_extract_notify")
def test_writeback_renders_markdown_and_marks_done(mock_notify, mock_publish_index, db_session, regular_user):
    f, job, event = _seed_pending_event(db_session, regular_user, transaction_id="tx-wb-ok")

    n = process_insavlo_writeback_once(db_session)

    assert n == 1
    db_session.refresh(event)
    db_session.refresh(job)
    db_session.refresh(f)
    assert event.status == EVENT_DONE
    assert job.status == JOB_DONE
    assert job.remote_completed_at is not None
    assert f.extract_status == "ready"
    assert f.extract_engine == "insavlo"
    assert f.has_md
    assert os.path.exists(md_note_path(f.id))
    # index enqueued
    from models.kb_index_job import KbIndexJob

    assert db_session.query(KbIndexJob).filter(KbIndexJob.file_id == f.id).count() >= 1
    mock_publish_index.assert_called_once()
    mock_notify.assert_called()


@patch("services.kb_index_service.publish_index_job")
@patch("messaging.kb_extract_publisher.publish_file_extract_notify")
def test_writeback_idempotent_after_done_no_double_write(mock_notify, mock_publish_index, db_session, regular_user):
    f, job, event = _seed_pending_event(db_session, regular_user, transaction_id="tx-wb-idem")

    process_insavlo_writeback_once(db_session)
    db_session.refresh(event)
    assert event.status == EVENT_DONE
    md_path = md_note_path(f.id)
    assert os.path.exists(md_path)
    first_mtime = os.path.getmtime(md_path)
    from models.kb_index_job import KbIndexJob

    first_index_count = db_session.query(KbIndexJob).filter(KbIndexJob.file_id == f.id).count()

    # SC-044-013: restart -> second pass finds no pending events; no double write/enqueue.
    n = process_insavlo_writeback_once(db_session)
    assert n == 0
    assert os.path.getmtime(md_path) == first_mtime
    assert (
        db_session.query(KbIndexJob).filter(KbIndexJob.file_id == f.id).count() == first_index_count
    )
    assert mock_publish_index.call_count == 1


@patch("services.kb_index_service.publish_index_job")
@patch("messaging.kb_extract_publisher.publish_file_extract_notify")
def test_writeback_marks_failed_on_transaction_error(mock_notify, mock_publish_index, db_session, regular_user):
    payload = {
        "event": "document_process.completed",
        "transaction_id": "tx-err-t",
        "status": "error",
        "error": "upstream blew up",
        "files": [],
        "timestamp": "2026-06-19T12:00:00Z",
    }
    f, job, event = _seed_pending_event(
        db_session, regular_user, transaction_id="tx-err-t", payload=payload
    )

    process_insavlo_writeback_once(db_session)

    db_session.refresh(event)
    db_session.refresh(job)
    db_session.refresh(f)
    assert event.status == EVENT_ERROR
    assert job.status == JOB_ERROR
    assert f.extract_status == "failed"
    assert "upstream blew up" in (f.extract_error or "")
    assert not f.has_md
    mock_publish_index.assert_not_called()


@patch("services.kb_index_service.publish_index_job")
@patch("messaging.kb_extract_publisher.publish_file_extract_notify")
def test_writeback_marks_failed_on_file_error(mock_notify, mock_publish_index, db_session, regular_user):
    f, job, event = _seed_pending_event(
        db_session, regular_user, transaction_id="tx-err-f", file_status="error", result={"x": 1},
        file_msg="ocr failed",
    )

    process_insavlo_writeback_once(db_session)

    db_session.refresh(event)
    db_session.refresh(f)
    assert event.status == EVENT_ERROR
    assert f.extract_status == "failed"
    assert "ocr failed" in (f.extract_error or "")


@patch("services.kb_index_service.publish_index_job")
@patch("messaging.kb_extract_publisher.publish_file_extract_notify")
def test_writeback_marks_failed_on_empty_result(mock_notify, mock_publish_index, db_session, regular_user):
    f, job, event = _seed_pending_event(
        db_session, regular_user, transaction_id="tx-err-empty", result={}
    )

    process_insavlo_writeback_once(db_session)

    db_session.refresh(event)
    db_session.refresh(f)
    assert event.status == EVENT_ERROR
    assert f.extract_status == "failed"
    assert not f.has_md


@patch("services.kb_index_service.publish_index_job")
@patch("messaging.kb_extract_publisher.publish_file_extract_notify")
def test_writeback_idempotent_when_job_already_done(mock_notify, mock_publish_index, db_session, regular_user):
    f, job, event = _seed_pending_event(db_session, regular_user, transaction_id="tx-wb-done")
    job.status = JOB_DONE
    db_session.commit()

    n = process_insavlo_writeback_once(db_session)

    assert n == 1  # event was picked up
    db_session.refresh(event)
    assert event.status == EVENT_DONE
    assert not f.has_md  # no markdown written for an already-done job
    mock_publish_index.assert_not_called()


@patch("services.kb_index_service.publish_index_job")
@patch("messaging.kb_extract_publisher.publish_file_extract_notify")
def test_end_to_end_submit_then_webhook_then_writeback(
    mock_notify, mock_publish_index, client, db_session, regular_user
):
    # 集成：mock Insavlo 提交 -> waiting_webhook -> webhook 200 -> 异步写回 -> md + index job。
    from services.extract.providers.insavlo_provider import InsavloSubmission
    from services.kb_extract_service import run_extract_job
    from utils.timezone import naive_db_now

    _configure_insavlo(db_session)
    f = _pdf(db_session, regular_user)
    job = KbExtractJob(
        user_id=regular_user.id,
        file_id=f.id,
        status="queued",
        provider="insavlo",
    )
    db_session.add(job)
    db_session.commit()
    db_session.refresh(job)

    submitted = InsavloSubmission(
        transaction_id="tx-e2e",
        file_id="remote-e2e",
        skill_code="filex-md",
        submitted_at=naive_db_now(),
    )
    with patch(
        "services.extract.providers.insavlo_provider.submit_insavlo_extract",
        return_value=submitted,
    ):
        run_extract_job(db_session, job)
        db_session.commit()

    db_session.refresh(job)
    assert job.status == JOB_WAITING_WEBHOOK
    assert job.remote_transaction_id == "tx-e2e"

    resp = _post(client, _completed_payload(transaction_id="tx-e2e", file_id="remote-e2e"))
    assert resp.status_code == 200
    events = db_session.query(InsavloWebhookEvent).all()
    assert len(events) == 1
    assert events[0].status == EVENT_PENDING

    # 异步写回（模拟后台循环消费已持久化事件）
    n = process_insavlo_writeback_once(db_session)
    assert n == 1
    db_session.refresh(job)
    db_session.refresh(f)
    assert job.status == JOB_DONE
    assert f.extract_status == "ready"
    assert f.extract_engine == "insavlo"
    assert f.has_md
    assert os.path.exists(md_note_path(f.id))
    from models.kb_index_job import KbIndexJob

    assert db_session.query(KbIndexJob).filter(KbIndexJob.file_id == f.id).count() >= 1
    mock_publish_index.assert_called_once()
