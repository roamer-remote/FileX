# Copyright (c) 2026 徐泽宇
"""Tests for MQ status backlog_total (distinct files with queued/running index jobs).

Authors:
    徐泽宇

Copyright:
    © 2026 徐泽宇
"""

from unittest.mock import patch

from models.file import File as FileModel
from models.kb_index_job import KbIndexJob
from services.kb_index_service import JOB_QUEUED, JOB_RUNNING, STATUS_INDEXING


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
    from unittest.mock import patch

    from services.kb_index_service import JOB_QUEUED, JOB_RUNNING
    from services.rabbitmq_status_service import get_mq_status

    def _pending():
        return int(
            db_session.query(KbIndexJob).filter(KbIndexJob.status == JOB_QUEUED).count()
        )

    def _backlog():
        return int(
            db_session.query(KbIndexJob.file_id)
            .filter(KbIndexJob.status.in_((JOB_QUEUED, JOB_RUNNING)))
            .distinct()
            .count()
        )

    with patch("services.rabbitmq_status_service._kb_index_jobs_pending", _pending):
        with patch("services.rabbitmq_status_service._kb_index_backlog_file_count", _backlog):
            with patch("database.SessionLocal", lambda: _mq_test_session(db_session)):
                with patch("services.rabbitmq_status_service.RABBITMQ_URL", ""):
                    return get_mq_status(viewer=None)


def test_get_mq_status_backlog_total_counts_distinct_files(db_session, regular_user):
    from services.rabbitmq_status_service import get_mq_status

    f = FileModel(
        filename="a.md",
        original_name="a.md",
        file_path="/tmp/a.md",
        file_size=1,
        mime_type="text/markdown",
        user_id=regular_user.id,
        has_md=True,
        index_status=STATUS_INDEXING,
    )
    db_session.add(f)
    db_session.flush()
    db_session.add(
        KbIndexJob(user_id=regular_user.id, file_id=f.id, status=JOB_RUNNING, attempts=1)
    )
    db_session.add(
        KbIndexJob(user_id=regular_user.id, file_id=f.id, status=JOB_QUEUED)
    )
    db_session.commit()

    status = _mq_status_with_session(db_session)

    main = next(q for q in status["queues"] if q["label"] == "index_main")
    expected_pending = int(
        db_session.query(KbIndexJob).filter(KbIndexJob.status == JOB_QUEUED).count()
    )
    expected_backlog = int(
        db_session.query(KbIndexJob.file_id)
        .filter(KbIndexJob.status.in_((JOB_QUEUED, JOB_RUNNING)))
        .distinct()
        .count()
    )
    assert main["jobs_pending"] == expected_pending
    assert main["backlog_total"] == expected_backlog


def test_get_mq_status_backlog_total_across_files(db_session, regular_user):
    from services.rabbitmq_status_service import get_mq_status

    for i in range(3):
        f = FileModel(
            filename=f"f{i}.md",
            original_name=f"f{i}.md",
            file_path=f"/tmp/f{i}.md",
            file_size=1,
            mime_type="text/markdown",
            user_id=regular_user.id,
            has_md=True,
            index_status="pending",
        )
        db_session.add(f)
        db_session.flush()
        db_session.add(
            KbIndexJob(user_id=regular_user.id, file_id=f.id, status=JOB_QUEUED)
        )
    db_session.commit()

    status = _mq_status_with_session(db_session)

    main = next(q for q in status["queues"] if q["label"] == "index_main")
    expected_pending = int(
        db_session.query(KbIndexJob).filter(KbIndexJob.status == JOB_QUEUED).count()
    )
    expected_backlog = int(
        db_session.query(KbIndexJob.file_id)
        .filter(KbIndexJob.status.in_((JOB_QUEUED, JOB_RUNNING)))
        .distinct()
        .count()
    )
    assert main["jobs_pending"] == expected_pending
    assert main["backlog_total"] == expected_backlog
