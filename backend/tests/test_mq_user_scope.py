# Copyright (c) 2026 徐泽宇
"""User-scoped MQ monitoring isolation (089)."""

from unittest.mock import patch

from models.file import File as FileModel
from models.kb_extract_job import KbExtractJob
from models.kb_index_job import KbIndexJob
from services.kb_extract_service import JOB_QUEUED as EXTRACT_QUEUED
from services.kb_index_service import JOB_QUEUED, JOB_RUNNING
from services.workspace_service import create_shared_workspace, set_member_role
from tests.conftest import _create_user


def _mq_test_session(db_session):
    class _NoCloseSession:
        def __init__(self, inner):
            self._inner = inner

        def close(self):
            return None

        def __getattr__(self, name):
            return getattr(self._inner, name)

    return _NoCloseSession(db_session)


def _file(db_session, user_id: int, name: str = "a.md") -> FileModel:
    f = FileModel(
        filename=name,
        original_name=name,
        file_path=f"/tmp/{name}",
        file_size=1,
        mime_type="text/markdown",
        user_id=user_id,
        has_md=True,
    )
    db_session.add(f)
    db_session.flush()
    return f


def test_get_mq_status_user_backlog_isolated(db_session, regular_user, admin_user):
    from services.rabbitmq_status_service import get_mq_status

    _file(db_session, regular_user.id, "u1.md")
    f2 = _file(db_session, admin_user.id, "u2.md")
    db_session.add(KbIndexJob(user_id=admin_user.id, file_id=f2.id, status=JOB_QUEUED))
    db_session.commit()

    with patch("database.SessionLocal", lambda: _mq_test_session(db_session)):
        with patch("services.rabbitmq_status_service.RABBITMQ_URL", ""):
            user_status = get_mq_status(viewer=regular_user)
            admin_status = get_mq_status(viewer=admin_user)

    assert len(user_status["queues"]) == 9
    assert {q["label"] for q in user_status["queues"]} == {
        "index_main",
        "index_retry",
        "index_dlq",
        "post_main",
        "post_retry",
        "post_dlq",
        "extract_main",
        "extract_retry",
        "extract_dlq",
    }
    user_index = next(q for q in user_status["queues"] if q["label"] == "index_main")
    admin_index = next(q for q in admin_status["queues"] if q["label"] == "index_main")
    assert user_index["jobs_pending"] == 0
    assert admin_index["jobs_pending"] >= 1
    assert user_index["message_count"] == 0
    assert user_status["broker_display"] == ""


def test_get_mq_status_admin_ws_still_global(db_session, admin_user):
    from services.rabbitmq_status_service import get_mq_status

    f = _file(db_session, admin_user.id, "admin.md")
    db_session.add(KbIndexJob(user_id=admin_user.id, file_id=f.id, status=JOB_QUEUED))
    db_session.commit()

    with patch("database.SessionLocal", lambda: _mq_test_session(db_session)):
        with patch("services.rabbitmq_status_service.RABBITMQ_URL", ""):
            ws_status = get_mq_status(viewer=admin_user)
            global_status = get_mq_status(viewer=None)

    assert ws_status["queues"][0]["jobs_pending"] == global_status["queues"][0]["jobs_pending"]


def test_get_mq_status_system_resources_admin_only(db_session, regular_user, admin_user):
    from services.rabbitmq_status_service import get_mq_status

    snapshot = {"cpu_percent": 12.5, "gpu": {"available": False}}

    with patch("database.SessionLocal", lambda: _mq_test_session(db_session)):
        with patch("services.rabbitmq_status_service.RABBITMQ_URL", ""):
            with patch("services.system_resource_service.collect_system_resources", return_value=snapshot):
                user_status = get_mq_status(viewer=regular_user)
                admin_status = get_mq_status(viewer=admin_user)

    assert "system_resources" not in user_status
    assert admin_status["system_resources"] is not None
    assert admin_status["system_resources"]["gpu"] == snapshot["gpu"]
    assert admin_status["system_resources"]["cpu_percent"] == snapshot["cpu_percent"]
    # 164 §9：admin 载荷额外携带 GPU 调度观测状态与 waiting_gpu 汇总
    assert "gpu_scheduler" in admin_status["system_resources"]
    assert "gpu_waiting" in admin_status["system_resources"]


def test_user_api_cannot_list_other_queued_jobs(client, db_session, jwt_token, admin_user):
    f = _file(db_session, admin_user.id, "other.md")
    db_session.add(KbIndexJob(user_id=admin_user.id, file_id=f.id, status=JOB_QUEUED))
    db_session.commit()

    r = client.get(
        "/api/mq/queued-jobs",
        headers={"Authorization": f"Bearer {jwt_token}"},
    )
    assert r.status_code == 200
    assert r.json()["total"] == 0
    assert r.json()["items"] == []


def test_user_cancel_other_job_forbidden(client, db_session, jwt_token, admin_user):
    f = _file(db_session, admin_user.id, "other.md")
    job = KbIndexJob(user_id=admin_user.id, file_id=f.id, status=JOB_QUEUED)
    db_session.add(job)
    db_session.commit()

    r = client.post(
        f"/api/mq/index-jobs/{job.id}/cancel",
        headers={"Authorization": f"Bearer {jwt_token}"},
    )
    assert r.status_code == 403
    db_session.refresh(job)
    assert job.status == JOB_QUEUED


def test_user_cancel_own_extract_queued_job(client, db_session, regular_user, jwt_token):
    f = _file(db_session, regular_user.id, "extract.md")
    job = KbExtractJob(user_id=regular_user.id, file_id=f.id, status=EXTRACT_QUEUED)
    db_session.add(job)
    db_session.commit()

    with patch("services.kb_mq_user_service.mutate_queue_messages", return_value={"removed": 1}):
        r = client.post(
            f"/api/mq/extract-jobs/{job.id}/cancel",
            headers={"Authorization": f"Bearer {jwt_token}"},
        )
    assert r.status_code == 200
    db_session.refresh(job)
    assert job.status == "error"
    assert job.last_error == "cancelled by user"


def test_user_cancel_running_job_forbidden(client, db_session, regular_user, jwt_token):
    f = _file(db_session, regular_user.id, "running.md")
    job = KbIndexJob(user_id=regular_user.id, file_id=f.id, status=JOB_RUNNING)
    db_session.add(job)
    db_session.commit()

    r = client.post(
        f"/api/mq/index-jobs/{job.id}/cancel",
        headers={"Authorization": f"Bearer {jwt_token}"},
    )
    assert r.status_code == 403
    db_session.refresh(job)
    assert job.status == JOB_RUNNING


def test_user_cancel_own_queued_job(client, db_session, regular_user, jwt_token):
    f = _file(db_session, regular_user.id, "mine.md")
    job = KbIndexJob(user_id=regular_user.id, file_id=f.id, status=JOB_QUEUED)
    db_session.add(job)
    db_session.commit()

    with patch("services.kb_mq_user_service.mutate_queue_messages", return_value={"removed": 1}):
        r = client.post(
            f"/api/mq/index-jobs/{job.id}/cancel",
            headers={"Authorization": f"Bearer {jwt_token}"},
        )
    assert r.status_code == 200
    db_session.refresh(job)
    assert job.status == "error"
    assert job.last_error == "cancelled by user"


def test_active_tasks_owner_not_acl_reader(db_session, regular_user):
    from services.kb_index_service import STATUS_INDEXING
    from services.rabbitmq_status_service import get_mq_status

    owner = _create_user(db_session, "owner089")
    shared = create_shared_workspace(db_session, name="共享089", owner=owner)
    set_member_role(db_session, shared.id, regular_user.id, "viewer")
    f = _file(db_session, owner.id, "shared.md")
    f.index_status = STATUS_INDEXING
    db_session.add(f)
    db_session.commit()

    with patch("database.SessionLocal", lambda: _mq_test_session(db_session)):
        with patch("services.rabbitmq_status_service.RABBITMQ_URL", ""):
            status = get_mq_status(viewer=regular_user)

    file_ids = [t.get("file_id") for t in status.get("active_tasks", [])]
    assert f.id not in file_ids
    for task in status.get("active_tasks", []):
        assert "username" not in task
