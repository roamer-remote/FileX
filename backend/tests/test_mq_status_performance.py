from __future__ import annotations

from unittest.mock import patch

from models.file import File as FileModel
from models.kb_extract_job import KbExtractJob
from models.kb_index_job import KbIndexJob
from services.kb_extract_service import JOB_QUEUED as EXTRACT_QUEUED
from services.kb_extract_service import JOB_RUNNING as EXTRACT_RUNNING
from services.kb_extract_service import STATUS_EXTRACTING
from services.kb_index_service import JOB_QUEUED as INDEX_QUEUED
from services.kb_index_service import JOB_RUNNING as INDEX_RUNNING
from services.kb_index_service import STATUS_INDEXING
from tests.query_counter import query_counter as query_counter

# 114：get_mq_status 对 index/extract/post 各 ~2 条 backlog 聚合 count 查询。
# 预算随 KB 队列种类扩展；164 §9 新增 3 条观测查询（extract/post waiting_gpu 计数 + scheduler state）。
# 长期可合并为单条 GROUP BY（见 review-114 N1）。
_MQ_STATUS_QUERY_BUDGET = 20


class _NoCloseSession:
    def __init__(self, inner):
        self._inner = inner

    def close(self):
        return None

    def __getattr__(self, name):
        return getattr(self._inner, name)


def _file(db, user, name: str) -> FileModel:
    f = FileModel(
        filename=name,
        original_name=name,
        file_path=f"/tmp/{name}",
        file_size=1,
        mime_type="text/plain",
        user_id=user.id,
        has_md=True,
    )
    db.add(f)
    db.flush()
    return f


def test_get_mq_status_uses_single_session_and_returns_backlog(db_session, regular_user, query_counter):
    from services import rabbitmq_status_service as svc

    f1 = _file(db_session, regular_user, "idx.md")
    f1.index_status = STATUS_INDEXING
    f2 = _file(db_session, regular_user, "ext.pdf")
    f2.extract_status = STATUS_EXTRACTING
    db_session.add_all(
        [
            KbIndexJob(user_id=regular_user.id, file_id=f1.id, status=INDEX_RUNNING),
            KbIndexJob(user_id=regular_user.id, file_id=f1.id, status=INDEX_QUEUED),
            KbExtractJob(user_id=regular_user.id, file_id=f2.id, status=EXTRACT_RUNNING),
            KbExtractJob(user_id=regular_user.id, file_id=f2.id, status=EXTRACT_QUEUED),
        ]
    )
    db_session.commit()
    session_calls = {"n": 0}

    def _session_factory():
        session_calls["n"] += 1
        return _NoCloseSession(db_session)

    with patch("database.SessionLocal", _session_factory), patch.object(svc, "RABBITMQ_URL", ""):
        with query_counter() as qc:
            status = svc.get_mq_status(viewer=None)

    assert session_calls["n"] == 1
    assert status["connected"] is False
    index_main = next(q for q in status["queues"] if q["label"] == "index_main")
    extract_main = next(q for q in status["queues"] if q["label"] == "extract_main")
    assert index_main["jobs_pending"] == 1
    assert index_main["backlog_total"] == 1
    assert extract_main["jobs_pending"] == 1
    assert extract_main["backlog_total"] == 1
    assert qc.count < _MQ_STATUS_QUERY_BUDGET


def test_mineru_inflight_tasks_batch_load_file_user(db_session, regular_user, query_counter):
    from services import rabbitmq_status_service as svc
    from services.kb_mineru_inflight import register_mineru_inflight, reset_mineru_inflight_for_tests

    reset_mineru_inflight_for_tests()
    files = [_file(db_session, regular_user, f"mineru-{i}.pdf") for i in range(3)]
    db_session.commit()
    for i, f in enumerate(files):
        register_mineru_inflight(file_id=f.id, job_id=i + 1, filename=f.filename, username=None)

    with patch("database.SessionLocal", lambda: _NoCloseSession(db_session)), patch.object(svc, "RABBITMQ_URL", ""):
        with query_counter() as qc:
            status = svc.get_mq_status(viewer=None)

    mineru = [t for t in status["active_tasks"] if t["kind"] == "kb_mineru"]
    assert len(mineru) == 3
    assert {t["username"] for t in mineru} == {regular_user.username}
    assert qc.count < _MQ_STATUS_QUERY_BUDGET
    reset_mineru_inflight_for_tests()
