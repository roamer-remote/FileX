# Copyright (c) 2026 徐泽宇
"""032 PR-B: MQ monitor extract + mineru queues and active_tasks."""

from __future__ import annotations

from unittest.mock import patch

from models.file import File as FileModel
from models.kb_extract_job import KbExtractJob
from models.kb_index_job import KbIndexJob
from services.kb_extract_service import JOB_QUEUED as EXTRACT_QUEUED
from services.kb_extract_service import JOB_RUNNING as EXTRACT_RUNNING
from services.kb_extract_service import JOB_WAITING_WEBHOOK as EXTRACT_WAITING_WEBHOOK
from services.kb_extract_service import STATUS_EXTRACTING
from services.kb_index_service import JOB_RUNNING
from services.kb_mineru_inflight import register_mineru_inflight, reset_mineru_inflight_for_tests
from services.kb_docling_inflight import register_docling_inflight, reset_docling_inflight_for_tests


def _mq_test_session(db_session):
    class _NoCloseSession:
        def __init__(self, inner):
            self._inner = inner

        def close(self):
            return None

        def __getattr__(self, name):
            return getattr(self._inner, name)

    return _NoCloseSession(db_session)


def _mq_status_with_session(db_session):
    from services.rabbitmq_status_service import get_mq_status

    with patch("database.SessionLocal", lambda: _mq_test_session(db_session)):
        with patch("services.rabbitmq_status_service.RABBITMQ_URL", ""):
            return get_mq_status(viewer=None)


def test_get_mq_status_includes_extract_and_mineru_queues(db_session, regular_user):
    reset_mineru_inflight_for_tests()
    reset_docling_inflight_for_tests()
    status = _mq_status_with_session(db_session)
    labels = {q["label"] for q in status["queues"]}
    assert "index_main" in labels
    assert "extract_main" in labels
    assert "mineru_main" in labels
    assert "docling_main" in labels
    assert "extract_retry" in labels


def test_get_mq_status_extract_main_backlog(db_session, regular_user):
    reset_mineru_inflight_for_tests()
    f = FileModel(
        filename="e.pdf",
        original_name="e.pdf",
        file_path="/tmp/e.pdf",
        file_size=1,
        mime_type="application/pdf",
        user_id=regular_user.id,
        extract_status=STATUS_EXTRACTING,
    )
    db_session.add(f)
    db_session.flush()
    db_session.add(
        KbExtractJob(user_id=regular_user.id, file_id=f.id, status=EXTRACT_RUNNING, attempts=1)
    )
    db_session.add(
        KbExtractJob(user_id=regular_user.id, file_id=f.id, status=EXTRACT_QUEUED)
    )
    db_session.commit()

    status = _mq_status_with_session(db_session)
    extract_main = next(q for q in status["queues"] if q["label"] == "extract_main")
    assert extract_main["jobs_pending"] == 1
    assert extract_main["backlog_total"] == 1
    assert extract_main["consumer_busy"] is True


def test_get_mq_status_extract_waiting_webhook_counts_as_active(db_session, regular_user):
    reset_mineru_inflight_for_tests()
    f = FileModel(
        filename="waiting.pdf",
        original_name="waiting.pdf",
        file_path="/tmp/waiting.pdf",
        file_size=1,
        mime_type="application/pdf",
        user_id=regular_user.id,
        extract_status=STATUS_EXTRACTING,
    )
    db_session.add(f)
    db_session.flush()
    db_session.add(
        KbExtractJob(
            user_id=regular_user.id,
            file_id=f.id,
            status=EXTRACT_WAITING_WEBHOOK,
            provider="insavlo",
            attempts=1,
            remote_transaction_id="tx-waiting",
        )
    )
    db_session.commit()

    status = _mq_status_with_session(db_session)
    extract_main = next(q for q in status["queues"] if q["label"] == "extract_main")
    assert extract_main["jobs_pending"] == 0
    assert extract_main["backlog_total"] == 1
    assert extract_main["consumer_busy"] is True
    task = next(t for t in status["active_tasks"] if t["file_id"] == f.id)
    assert task["kind"] == "kb_extract"


def test_active_tasks_kb_extract_and_kb_mineru_same_file_id(db_session, regular_user):
    reset_mineru_inflight_for_tests()
    f = FileModel(
        filename="dual.pdf",
        original_name="dual.pdf",
        file_path="/tmp/dual.pdf",
        file_size=1,
        mime_type="application/pdf",
        user_id=regular_user.id,
        extract_status=STATUS_EXTRACTING,
    )
    db_session.add(f)
    db_session.flush()
    db_session.add(
        KbExtractJob(user_id=regular_user.id, file_id=f.id, status=EXTRACT_RUNNING, attempts=1)
    )
    db_session.commit()

    register_mineru_inflight(
        file_id=f.id,
        job_id=99,
        filename="dual.pdf",
        username=regular_user.username,
    )

    status = _mq_status_with_session(db_session)
    kinds = {t["kind"] for t in status["active_tasks"] if t["file_id"] == f.id}
    assert kinds == {"kb_extract", "kb_mineru"}
    mineru = next(
        x for x in status["active_tasks"] if x["kind"] == "kb_mineru" and x["file_id"] == f.id
    )
    assert mineru["username"] == regular_user.username


def test_active_tasks_kb_extract_and_kb_docling_same_file_id(db_session, regular_user):
    reset_mineru_inflight_for_tests()
    reset_docling_inflight_for_tests()
    f = FileModel(
        filename="docling-dual.pdf",
        original_name="docling-dual.pdf",
        file_path="/tmp/docling-dual.pdf",
        file_size=1,
        mime_type="application/pdf",
        user_id=regular_user.id,
        extract_status=STATUS_EXTRACTING,
    )
    db_session.add(f)
    db_session.flush()
    db_session.add(
        KbExtractJob(user_id=regular_user.id, file_id=f.id, status=EXTRACT_RUNNING, attempts=1)
    )
    db_session.commit()

    register_docling_inflight(
        file_id=f.id,
        job_id=100,
        filename="docling-dual.pdf",
        username=regular_user.username,
    )

    status = _mq_status_with_session(db_session)
    kinds = {t["kind"] for t in status["active_tasks"] if t["file_id"] == f.id}
    assert kinds == {"kb_extract", "kb_docling"}


def test_list_kb_extract_queued_jobs(client, admin_jwt_token, db_session, regular_user):
    f = FileModel(
        filename="eq.pdf",
        original_name="eq.pdf",
        file_path="/tmp/eq.pdf",
        file_size=1,
        mime_type="application/pdf",
        user_id=regular_user.id,
    )
    db_session.add(f)
    db_session.flush()
    db_session.add(KbExtractJob(user_id=regular_user.id, file_id=f.id, status=EXTRACT_QUEUED))
    db_session.commit()

    res = client.get(
        "/api/admin/mq/extract-queued-jobs",
        headers={"Authorization": f"Bearer {admin_jwt_token}"},
    )
    assert res.status_code == 200
    data = res.json()
    ours = [x for x in data["items"] if x["filename"] == "eq.pdf"]
    assert len(ours) == 1
    assert ours[0]["username"] == regular_user.username


def test_index_main_backlog_label_regression(db_session, regular_user):
    reset_mineru_inflight_for_tests()
    f = FileModel(
        filename="a.md",
        original_name="a.md",
        file_path="/tmp/a.md",
        file_size=1,
        mime_type="text/markdown",
        user_id=regular_user.id,
        has_md=True,
        index_status="indexing",
    )
    db_session.add(f)
    db_session.flush()
    db_session.add(
        KbIndexJob(user_id=regular_user.id, file_id=f.id, status=JOB_RUNNING, attempts=1)
    )
    db_session.commit()

    status = _mq_status_with_session(db_session)
    index_main = next(q for q in status["queues"] if q["label"] == "index_main")
    assert index_main["consumer_busy"] is True
