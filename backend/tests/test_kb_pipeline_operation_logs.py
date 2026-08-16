# Copyright (c) 2026 徐泽宇
"""067 T-5: KB pipeline operation_logs integration tests (SC-067-001～011)."""

from __future__ import annotations

import hashlib
import hmac
import json
import os
from datetime import datetime
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from config import OLLAMA_EMBED_DIM
from models.file import File as FileModel
from models.kb_extract_job import KbExtractJob
from models.kb_index_job import KbIndexJob
from models.insavlo_webhook_event import InsavloWebhookEvent
from models.operation_log import OperationLog
from services.extract.base import ExtractResult
from services.extract.providers.insavlo_provider import InsavloSubmission
from services.insavlo_webhook_writeback import EVENT_PENDING, process_insavlo_writeback_once
from services.kb_extract_service import JOB_QUEUED, JOB_WAITING_WEBHOOK, STATUS_READY, run_extract_job
from services.kb_index_service import _log_index_pipeline, run_index_job
from services.kb_pipeline_log_service import (
    ACTION_INSAVLO_SUBMIT,
    ACTION_INSAVLO_WEBHOOK_RECEIVED,
    ACTION_INSAVLO_WRITEBACK_DONE,
    ACTION_INSAVLO_WRITEBACK_ERROR,
    ACTION_KB_EXTRACT_DONE,
    ACTION_KB_EXTRACT_ERROR,
    ACTION_KB_EXTRACT_FALLBACK,
    ACTION_KB_EXTRACT_SKIP,
    ACTION_KB_EXTRACT_START,
    ACTION_KB_INDEX_DONE,
    ACTION_KB_INDEX_ERROR,
    ACTION_KB_INDEX_SKIP,
    ACTION_KB_INDEX_START,
)
from services.rag_quality_failure_service import (
    build_failure_event,
    persist_failure_event,
    project_failure_event,
)
from services.md_hash_service import touch_md_content_hash
from services.md_paths import md_note_path
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

WEBHOOK_URL = "/api/webhooks/insavlo/document-process"
WEBHOOK_SECRET = "insavlo-webhook-secret-pipeline"


def _configure_insavlo(db_session) -> None:
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


def _op_logs(
    db_session,
    user_id: int,
    *,
    action: str | None = None,
    target_id: int | None = None,
) -> list[OperationLog]:
    q = db_session.query(OperationLog).filter(OperationLog.user_id == user_id)
    if action is not None:
        q = q.filter(OperationLog.action == action)
    if target_id is not None:
        q = q.filter(OperationLog.target_id == target_id)
    return q.order_by(OperationLog.id.asc()).all()


def _count_action(db_session, user_id: int, action: str, *, target_id: int | None = None) -> int:
    return len(_op_logs(db_session, user_id, action=action, target_id=target_id))


def _sign(secret: str, raw: bytes) -> str:
    return "sha256=" + hmac.new(secret.encode("utf-8"), raw, hashlib.sha256).hexdigest()


def _post_webhook(client, payload, *, secret=WEBHOOK_SECRET):
    body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
    tid = payload.get("transaction_id", "")
    return client.post(
        WEBHOOK_URL,
        content=body,
        headers={
            "content-type": "application/json",
            "x-webhook-event": "document_process.completed",
            "x-transaction-id": tid,
            "x-webhook-signature": _sign(secret, body),
        },
    )


def _completed_payload(transaction_id: str, file_id: str = "remote-1"):
    return {
        "event": "document_process.completed",
        "transaction_id": transaction_id,
        "status": "completed",
        "skill_code": "filex-md",
        "files": [
            {
                "file_id": file_id,
                "file_name": "invoice.pdf",
                "status": "completed",
                "skill_code": "filex-md",
                "result": {"INVOICE_NO": "INV-1"},
            }
        ],
        "timestamp": "2026-06-19T12:00:00Z",
    }


@pytest.fixture
def pdf_file(db_session, regular_user):
    f = FileModel(
        filename="paper.pdf",
        original_name="paper.pdf",
        file_path="/tmp/paper.pdf",
        file_size=100,
        mime_type="application/pdf",
        user_id=regular_user.id,
        has_md=False,
    )
    db_session.add(f)
    db_session.commit()
    db_session.refresh(f)
    return f


@patch("services.kb_extract_service._notify_file")
@patch("services.kb_index_service.publish_index_job")
@patch("services.extract.providers.registry.extract_with_provider")
def test_sc067_001_extract_success_operation_logs(
    mock_extract, _mock_publish_index, _mock_notify, db_session, regular_user, pdf_file
):
    mock_extract.return_value = ExtractResult(text="# Title\n\nBody text.", engine="markitdown")
    job = KbExtractJob(
        user_id=regular_user.id,
        file_id=pdf_file.id,
        status=JOB_QUEUED,
        provider="legacy",
        attempts=0,
    )
    db_session.add(job)
    db_session.commit()

    run_extract_job(db_session, job)
    db_session.commit()

    logs = _op_logs(db_session, regular_user.id, target_id=pdf_file.id)
    actions = [row.action for row in logs]
    assert ACTION_KB_EXTRACT_START in actions
    assert ACTION_KB_EXTRACT_DONE in actions
    done_row = next(row for row in logs if row.action == ACTION_KB_EXTRACT_DONE)
    assert f"job_id={job.id}" in (done_row.detail or "")
    assert "engine=markitdown" in (done_row.detail or "")
    assert "provider_ms=" in (done_row.detail or "")
    assert "persist_ms=" in (done_row.detail or "")
    assert "side_effects_ms=" in (done_row.detail or "")


@patch("services.kb_extract_service._notify_file")
@patch("services.kb_index_service.publish_index_job")
@patch("services.extract.providers.registry.extract_with_provider")
def test_mineru_ocr_models_are_persisted_in_system_log(
    mock_extract, _mock_publish_index, _mock_notify, db_session, regular_user, pdf_file
):
    mock_extract.return_value = ExtractResult(
        text="# MinerU\n",
        engine="mineru",
        ocr_model_usage=[
            {
                "component": "ocr_det",
                "model_name": "ch_PP-OCRv6_small_det_infer",
                "model_path": "/models/ocr/det.safetensors",
            },
            {
                "component": "ocr_rec",
                "model_name": "ch_PP-OCRv6_small_rec_infer",
                "model_path": "/models/ocr/rec.safetensors",
            },
        ],
    )
    job = KbExtractJob(
        user_id=regular_user.id,
        file_id=pdf_file.id,
        status=JOB_QUEUED,
        provider="mineru",
        attempts=0,
    )
    db_session.add(job)
    db_session.commit()

    run_extract_job(db_session, job)
    db_session.commit()

    done_row = next(
        row
        for row in _op_logs(db_session, regular_user.id, target_id=pdf_file.id)
        if row.action == ACTION_KB_EXTRACT_DONE
    )
    assert "ocr_model_ocr_det=ch_PP-OCRv6_small_det_infer" in (done_row.detail or "")
    assert "ocr_model_path_ocr_det=/models/ocr/det.safetensors" in (done_row.detail or "")
    assert "ocr_model_ocr_rec=ch_PP-OCRv6_small_rec_infer" in (done_row.detail or "")


@patch("services.kb_extract_service._notify_file")
@patch("services.extract.providers.registry.extract_with_provider")
def test_sc067_002_extract_failure_operation_logs(
    mock_extract, _mock_notify, db_session, regular_user, pdf_file
):
    mock_extract.side_effect = RuntimeError("extract failed badly")
    job = KbExtractJob(
        user_id=regular_user.id,
        file_id=pdf_file.id,
        status=JOB_QUEUED,
        provider="legacy",
        attempts=0,
    )
    db_session.add(job)
    db_session.commit()

    run_extract_job(db_session, job)
    db_session.commit()

    assert _count_action(
        db_session, regular_user.id, ACTION_KB_EXTRACT_ERROR, target_id=pdf_file.id
    ) >= 1
    error_row = _op_logs(
        db_session, regular_user.id, action=ACTION_KB_EXTRACT_ERROR, target_id=pdf_file.id
    )[-1]
    assert f"job_id={job.id}" in (error_row.detail or "")
    assert "reason=" in (error_row.detail or "")
    failure_rows = _op_logs(
        db_session, regular_user.id, action="rag_quality_failure", target_id=pdf_file.id
    )
    assert failure_rows
    assert project_failure_event(failure_rows[-1].detail).reason == "unknown"
    assert project_failure_event(failure_rows[-1].detail).retryable is False


@patch("services.kb_extract_service._notify_file")
@patch("services.kb_index_service.publish_index_job")
@patch("services.extract.providers.registry.extract_with_provider")
def test_extract_fallback_to_legacy_operation_log(
    mock_extract, _mock_publish_index, _mock_notify, db_session, regular_user, pdf_file
):
    mock_extract.return_value = ExtractResult(
        text="# Title\n\nBody text.",
        engine="pymupdf",
        fallback_from="docling",
        fallback_reason="docling sidecar unavailable",
    )
    job = KbExtractJob(
        user_id=regular_user.id,
        file_id=pdf_file.id,
        status=JOB_QUEUED,
        provider="docling",
        attempts=0,
    )
    db_session.add(job)
    db_session.commit()

    run_extract_job(db_session, job)
    db_session.commit()

    logs = _op_logs(db_session, regular_user.id, target_id=pdf_file.id)
    actions = [row.action for row in logs]
    assert ACTION_KB_EXTRACT_START in actions
    assert ACTION_KB_EXTRACT_FALLBACK in actions
    assert ACTION_KB_EXTRACT_DONE in actions
    fallback_row = next(row for row in logs if row.action == ACTION_KB_EXTRACT_FALLBACK)
    assert f"job_id={job.id}" in (fallback_row.detail or "")
    assert "provider=docling" in (fallback_row.detail or "")
    assert "reason=docling_sidecar_unavailable" in (fallback_row.detail or "")


@patch("services.kb_extract_service._notify_file")
@patch("services.extract.providers.registry.extract_with_provider")
def test_sc067_003_extract_hash_skip_operation_logs(
    mock_extract, _mock_notify, db_session, regular_user, tmp_path, monkeypatch
):
    md_dir = tmp_path / ".md_notes"
    md_dir.mkdir()
    monkeypatch.setattr("services.md_paths.UPLOAD_DIR", str(tmp_path))
    monkeypatch.setattr("services.md_paths.MD_DIR", str(md_dir))
    f = FileModel(
        filename="x.bin",
        original_name="paper.pdf",
        file_path="/tmp/unused.bin",
        file_size=10,
        mime_type="application/pdf",
        user_id=regular_user.id,
        has_md=True,
        extract_status=STATUS_READY,
    )
    db_session.add(f)
    db_session.commit()
    content = "# existing note\n"
    note = Path(md_note_path(f.id))
    note.parent.mkdir(parents=True, exist_ok=True)
    note.write_text(content, encoding="utf-8")
    f.md_file_path = str(note)
    touch_md_content_hash(db_session, f, content=content)
    db_session.commit()

    job = KbExtractJob(user_id=f.user_id, file_id=f.id, status=JOB_QUEUED, attempts=0)
    db_session.add(job)
    db_session.commit()

    run_extract_job(db_session, job)
    db_session.commit()

    mock_extract.assert_not_called()
    skip_row = _op_logs(
        db_session, regular_user.id, action=ACTION_KB_EXTRACT_SKIP, target_id=f.id
    )[-1]
    assert "reason=hash_unchanged" in (skip_row.detail or "")


@patch("services.kb_index_service._notify_file_index")
@patch("services.kb_embed_cache_service.embed_texts")
def test_sc067_004_index_success_operation_logs(
    mock_embed, _mock_notify, db_session, regular_user,
):
    from config import UPLOAD_DIR

    os.makedirs(UPLOAD_DIR, exist_ok=True)
    md_path = os.path.join(UPLOAD_DIR, "pipeline_index_note.md")
    with open(md_path, "w", encoding="utf-8") as fh:
        fh.write("# Title\n\nParagraph about microscopy imaging.\n")
    f = FileModel(
        filename="x.bin",
        original_name="paper.pdf",
        file_path="/tmp/unused.bin",
        file_size=10,
        mime_type="application/pdf",
        user_id=regular_user.id,
        has_md=True,
        md_file_path=md_path,
    )
    db_session.add(f)
    db_session.commit()
    job = KbIndexJob(user_id=regular_user.id, file_id=f.id, status=JOB_QUEUED, force=False)
    db_session.add(job)
    db_session.commit()
    mock_embed.side_effect = lambda texts, **_kwargs: [[0.01] * OLLAMA_EMBED_DIM for _ in texts]

    run_index_job(db_session, job)
    db_session.commit()

    logs = _op_logs(db_session, regular_user.id, target_id=f.id)
    actions = [row.action for row in logs]
    assert ACTION_KB_INDEX_START in actions
    assert ACTION_KB_INDEX_DONE in actions
    done_row = next(row for row in logs if row.action == ACTION_KB_INDEX_DONE)
    assert f"job_id={job.id}" in (done_row.detail or "")
    assert "chunk_count=" in (done_row.detail or "")
    assert "source=" in (done_row.detail or "")
    assert "embed_ms=" in (done_row.detail or "")
    assert "persist_ms=" in (done_row.detail or "")
    assert "post_index_ms=" not in (done_row.detail or "")


@patch("services.kb_index_service._notify_file_index")
def test_sc067_005_index_no_text_skip_operation_logs(
    _mock_notify, db_session, regular_user, pdf_file
):
    job = KbIndexJob(user_id=regular_user.id, file_id=pdf_file.id, status=JOB_QUEUED, force=False)
    db_session.add(job)
    db_session.commit()

    run_index_job(db_session, job)
    db_session.commit()

    skip_row = _op_logs(
        db_session, regular_user.id, action=ACTION_KB_INDEX_SKIP, target_id=pdf_file.id
    )[-1]
    assert "reason=no_text" in (skip_row.detail or "")


def test_index_failure_pipeline_log_emits_structured_quality_failure(
    db_session, regular_user, pdf_file
):
    job = KbIndexJob(user_id=regular_user.id, file_id=pdf_file.id, status=JOB_QUEUED, force=False)
    db_session.add(job)
    db_session.flush()

    _log_index_pipeline(
        db_session,
        job,
        ACTION_KB_INDEX_ERROR,
        reason="embedding_timeout",
    )
    db_session.flush()

    rows = _op_logs(db_session, regular_user.id, action="rag_quality_failure", target_id=pdf_file.id)
    assert rows
    event = project_failure_event(rows[-1].detail)
    assert event is not None
    assert event.stage == "index"
    assert event.reason == "timeout"


def test_index_failure_event_race_does_not_rollback_067_pipeline_log(
    db_session, regular_user, pdf_file
):
    job = KbIndexJob(user_id=regular_user.id, file_id=pdf_file.id, status=JOB_QUEUED, force=False)
    db_session.add(job)
    db_session.flush()
    event = build_failure_event(
        stage="index",
        reason="timeout",
        file_id=pdf_file.id,
        job_id=job.id,
        request_id=None,
        trace_id=None,
        summary="embedding_timeout",
    )
    persist_failure_event(db_session, regular_user.id, event)

    original_query = db_session.query
    first_failure_lookup = True

    def query_side_effect(*entities, **kwargs):
        nonlocal first_failure_lookup
        if first_failure_lookup and entities == (OperationLog.detail,):
            first_failure_lookup = False
            empty_query = MagicMock()
            empty_query.filter.return_value.all.return_value = []
            return empty_query
        return original_query(*entities, **kwargs)

    with patch.object(db_session, "query", side_effect=query_side_effect):
        _log_index_pipeline(db_session, job, ACTION_KB_INDEX_ERROR, reason="embedding_timeout")

    assert _count_action(db_session, regular_user.id, ACTION_KB_INDEX_ERROR, target_id=pdf_file.id) == 1
    assert _count_action(db_session, regular_user.id, "rag_quality_failure", target_id=pdf_file.id) == 1


@patch("services.kb_index_service.publish_index_job")
@patch("messaging.kb_extract_publisher.publish_file_extract_notify")
def test_sc067_006_insavlo_full_chain_operation_logs(
    _mock_notify, _mock_publish_index, client, db_session, regular_user, pdf_file
):
    _configure_insavlo(db_session)
    job = KbExtractJob(
        user_id=regular_user.id,
        file_id=pdf_file.id,
        status=JOB_QUEUED,
        provider="insavlo",
        attempts=0,
    )
    db_session.add(job)
    db_session.commit()

    submitted = InsavloSubmission(
        transaction_id="tx-sc067-006",
        file_id="remote-sc067",
        skill_code="filex-md",
        submitted_at=naive_db_now(),
    )
    with patch(
        "services.extract.providers.insavlo_provider.submit_insavlo_extract",
        return_value=submitted,
    ):
        run_extract_job(db_session, job)
        db_session.commit()

    resp = _post_webhook(
        client,
        _completed_payload("tx-sc067-006", file_id="remote-sc067"),
    )
    assert resp.status_code == 200
    process_insavlo_writeback_once(db_session)

    logs = _op_logs(db_session, regular_user.id, target_id=pdf_file.id)
    actions = [row.action for row in logs]
    assert ACTION_INSAVLO_SUBMIT in actions
    assert ACTION_INSAVLO_WEBHOOK_RECEIVED in actions
    assert ACTION_INSAVLO_WRITEBACK_DONE in actions
    assert actions.count(ACTION_KB_EXTRACT_DONE) == 1

    for action in (
        ACTION_INSAVLO_SUBMIT,
        ACTION_INSAVLO_WEBHOOK_RECEIVED,
        ACTION_INSAVLO_WRITEBACK_DONE,
    ):
        row = next(r for r in logs if r.action == action)
        assert "transaction_id=tx-sc067-006" in (row.detail or "")


@patch("services.kb_index_service.publish_index_job")
@patch("messaging.kb_extract_publisher.publish_file_extract_notify")
def test_sc067_007_insavlo_writeback_failure_no_extract_done(
    _mock_notify, _mock_publish_index, db_session, regular_user, pdf_file
):
    job = KbExtractJob(
        user_id=regular_user.id,
        file_id=pdf_file.id,
        status=JOB_WAITING_WEBHOOK,
        provider="insavlo",
        remote_transaction_id="tx-sc067-007",
        remote_file_id="remote-7",
        remote_skill_code="filex-md",
        remote_submitted_at=datetime.utcnow(),
    )
    db_session.add(job)
    db_session.flush()
    event = InsavloWebhookEvent(
        transaction_id="tx-sc067-007",
        job_id=job.id,
        file_id=pdf_file.id,
        payload_json={
            "transaction_id": "tx-sc067-007",
            "status": "error",
            "error": "upstream blew up",
            "files": [],
        },
        status=EVENT_PENDING,
    )
    db_session.add(event)
    db_session.commit()

    process_insavlo_writeback_once(db_session)

    assert _count_action(
        db_session, regular_user.id, ACTION_INSAVLO_WRITEBACK_ERROR, target_id=pdf_file.id
    ) >= 1
    assert _count_action(
        db_session, regular_user.id, ACTION_KB_EXTRACT_DONE, target_id=pdf_file.id
    ) == 0


def test_sc067_008_webhook_401_writes_no_operation_log(client, db_session, regular_user, pdf_file):
    _configure_insavlo(db_session)
    job = KbExtractJob(
        user_id=regular_user.id,
        file_id=pdf_file.id,
        status=JOB_WAITING_WEBHOOK,
        provider="insavlo",
        remote_transaction_id="tx-sc067-008",
        remote_file_id="remote-8",
        remote_skill_code="filex-md",
        remote_submitted_at=datetime.utcnow(),
    )
    db_session.add(job)
    db_session.commit()

    before = _count_action(db_session, regular_user.id, ACTION_INSAVLO_WEBHOOK_RECEIVED)
    resp = _post_webhook(
        client,
        _completed_payload("tx-sc067-008"),
        secret="wrong-secret",
    )
    assert resp.status_code == 401
    after = _count_action(db_session, regular_user.id, ACTION_INSAVLO_WEBHOOK_RECEIVED)
    assert after == before


@patch("services.kb_index_service.publish_index_job")
@patch("messaging.kb_extract_publisher.publish_file_extract_notify")
def test_sc067_011_writeback_retry_success_single_extract_done(
    _mock_notify, _mock_publish_index, db_session, regular_user, pdf_file
):
    """SC-067-011: 首次写回失败、重置后重试成功，终态仅一条「KB 提取完成」。"""
    user_id = regular_user.id
    file_id = pdf_file.id
    job = KbExtractJob(
        user_id=user_id,
        file_id=file_id,
        status=JOB_WAITING_WEBHOOK,
        provider="insavlo",
        remote_transaction_id="tx-sc067-011",
        remote_file_id="remote-11",
        remote_skill_code="filex-md",
        remote_submitted_at=datetime.utcnow(),
    )
    db_session.add(job)
    db_session.flush()
    event = InsavloWebhookEvent(
        transaction_id="tx-sc067-011",
        job_id=job.id,
        file_id=file_id,
        payload_json={
            "transaction_id": "tx-sc067-011",
            "status": "error",
            "error": "transient upstream failure",
            "files": [],
        },
        status=EVENT_PENDING,
    )
    db_session.add(event)
    db_session.commit()
    event_id = event.id
    job_id = job.id

    process_insavlo_writeback_once(db_session)
    assert _count_action(
        db_session, user_id, ACTION_INSAVLO_WRITEBACK_ERROR, target_id=file_id
    ) >= 1
    assert _count_action(db_session, user_id, ACTION_KB_EXTRACT_DONE, target_id=file_id) == 0

    ev = db_session.get(InsavloWebhookEvent, event_id)
    j = db_session.get(KbExtractJob, job_id)
    fl = db_session.get(FileModel, file_id)
    assert ev is not None and j is not None and fl is not None
    ev.status = EVENT_PENDING
    ev.last_error = None
    ev.payload_json = _completed_payload("tx-sc067-011", file_id="remote-11")
    j.status = JOB_WAITING_WEBHOOK
    j.last_error = None
    fl.extract_status = "extracting"
    fl.extract_error = None
    db_session.commit()

    process_insavlo_writeback_once(db_session)
    assert _count_action(
        db_session, user_id, ACTION_INSAVLO_WRITEBACK_DONE, target_id=file_id
    ) >= 1
    assert _count_action(db_session, user_id, ACTION_KB_EXTRACT_DONE, target_id=file_id) == 1
