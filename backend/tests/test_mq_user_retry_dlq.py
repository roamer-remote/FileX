# Copyright (c) 2026 徐泽宇
"""User-scoped retry/DLQ MQ queue visibility (091)."""

import json
from contextlib import ExitStack, contextmanager
from unittest.mock import patch

from models.file import File as FileModel
from models.kb_extract_job import KbExtractJob
from models.kb_index_job import KbIndexJob
from models.kb_post_job import KbPostJob
from services.kb_extract_service import JOB_QUEUED as EXTRACT_QUEUED
from services.kb_index_service import JOB_QUEUED
from services.kb_post_service import JOB_QUEUED as POST_QUEUED
from services.rabbitmq_retry_dlq_snapshot_service import invalidate_retry_dlq_snapshot


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


@contextmanager
def _with_peek_patches(bodies_by_label: dict[str, list] | None = None, bodies: list | None = None):
    if bodies_by_label is None:
        bodies_by_label = {
            "index_retry": bodies or [],
            "index_dlq": [],
            "post_retry": [],
            "post_dlq": [],
            "extract_retry": [],
            "extract_dlq": [],
        }

    def fake_drain_all():
        return {label: [(None, body) for body in body_list] for label, body_list in bodies_by_label.items()}

    invalidate_retry_dlq_snapshot()
    with ExitStack() as stack:
        stack.enter_context(
            patch(
                "services.rabbitmq_retry_dlq_snapshot_service._drain_all_retry_dlq_queues",
                side_effect=fake_drain_all,
            )
        )
        yield


def test_peek_queue_messages_for_owner_filters_other_user_index(db_session, regular_user, admin_user):
    from services.rabbitmq_queue_user_service import peek_queue_messages_for_owner

    f_reg = _file(db_session, regular_user.id, "reg.md")
    f_adm = _file(db_session, admin_user.id, "adm.md")
    job_reg = KbIndexJob(user_id=regular_user.id, file_id=f_reg.id, status=JOB_QUEUED)
    job_adm = KbIndexJob(user_id=admin_user.id, file_id=f_adm.id, status=JOB_QUEUED)
    db_session.add_all([job_reg, job_adm])
    db_session.commit()

    bodies = [
        json.dumps({"job_id": job_reg.id}).encode(),
        json.dumps({"job_id": job_adm.id}).encode(),
    ]

    with _with_peek_patches(bodies=bodies):
        payload = peek_queue_messages_for_owner(
            db_session,
            owner_user_id=int(regular_user.id),
            queue_label="index_retry",
            limit=50,
        )

    assert payload["total"] == 1
    assert payload["items"][0]["job_id"] == job_reg.id


def test_peek_queue_messages_for_owner_filters_other_user_extract(db_session, regular_user, admin_user):
    from services.rabbitmq_queue_user_service import peek_queue_messages_for_owner

    f_reg = _file(db_session, regular_user.id, "reg-extract.md")
    f_adm = _file(db_session, admin_user.id, "adm-extract.md")
    job_reg = KbExtractJob(user_id=regular_user.id, file_id=f_reg.id, status=EXTRACT_QUEUED)
    job_adm = KbExtractJob(user_id=admin_user.id, file_id=f_adm.id, status=EXTRACT_QUEUED)
    db_session.add_all([job_reg, job_adm])
    db_session.commit()

    bodies = [
        json.dumps({"job_id": job_reg.id}).encode(),
        json.dumps({"job_id": job_adm.id}).encode(),
    ]

    with _with_peek_patches(
        bodies_by_label={
            "index_retry": [],
            "index_dlq": [],
            "post_retry": [],
            "post_dlq": [],
            "extract_retry": [],
            "extract_dlq": bodies,
        }
    ):
        payload = peek_queue_messages_for_owner(
            db_session,
            owner_user_id=int(regular_user.id),
            queue_label="extract_dlq",
            limit=50,
        )

    assert payload["total"] == 1
    assert payload["items"][0]["job_id"] == job_reg.id


def test_peek_queue_messages_for_owner_filters_other_user_post(db_session, regular_user, admin_user):
    from services.rabbitmq_queue_user_service import peek_queue_messages_for_owner

    f_reg = _file(db_session, regular_user.id, "reg-post.md")
    f_adm = _file(db_session, admin_user.id, "adm-post.md")
    job_reg = KbPostJob(user_id=regular_user.id, file_id=f_reg.id, status=POST_QUEUED)
    job_adm = KbPostJob(user_id=admin_user.id, file_id=f_adm.id, status=POST_QUEUED)
    db_session.add_all([job_reg, job_adm])
    db_session.commit()

    bodies = [
        json.dumps({"job_id": job_reg.id}).encode(),
        json.dumps({"job_id": job_adm.id}).encode(),
    ]

    with _with_peek_patches(
        bodies_by_label={
            "index_retry": [],
            "index_dlq": [],
            "post_retry": bodies,
            "post_dlq": [],
            "extract_retry": [],
            "extract_dlq": [],
        }
    ):
        payload = peek_queue_messages_for_owner(
            db_session,
            owner_user_id=int(regular_user.id),
            queue_label="post_retry",
            limit=50,
        )

    assert payload["total"] == 1
    assert payload["items"][0]["job_id"] == job_reg.id


def test_user_remove_queue_message_forbidden_for_other_owner(db_session, regular_user, admin_user):
    from services.rabbitmq_queue_user_service import remove_owner_queue_message

    f_adm = _file(db_session, admin_user.id, "adm.md")
    job_adm = KbIndexJob(user_id=admin_user.id, file_id=f_adm.id, status=JOB_QUEUED)
    db_session.add(job_adm)
    db_session.commit()

    try:
        remove_owner_queue_message(
            db_session,
            owner_user_id=int(regular_user.id),
            queue_label="index_dlq",
            job_id=int(job_adm.id),
        )
        assert False, "expected PermissionError"
    except PermissionError:
        pass


def test_user_peek_queue_messages_api_returns_owned_only(client, db_session, jwt_token, regular_user):
    peek_payload = {
        "queue_label": "index_retry",
        "total": 1,
        "peek_count": 1,
        "items": [{"index": 0, "job_id": 42, "last_error": "err", "body_preview": "{}", "duplicate_count": 1}],
        "truncated": False,
    }
    with patch("routers.mq.peek_queue_messages_for_owner", return_value=peek_payload) as mock_peek:
        r = client.get(
            "/api/mq/queue-messages",
            params={"queue": "index_retry"},
            headers={"Authorization": f"Bearer {jwt_token}"},
        )
    assert r.status_code == 200
    body = r.json()
    assert body["total"] == 1
    assert body["items"][0]["job_id"] == 42
    mock_peek.assert_called_once()
    assert mock_peek.call_args.kwargs["owner_user_id"] == int(regular_user.id)


def test_user_remove_queue_messages_api_forbidden_other_job(
    client, db_session, jwt_token, admin_user
):
    f_adm = _file(db_session, admin_user.id, "adm-extract.md")
    job_adm = KbExtractJob(user_id=admin_user.id, file_id=f_adm.id, status=EXTRACT_QUEUED)
    db_session.add(job_adm)
    db_session.commit()

    r = client.post(
        "/api/mq/queue-messages/remove",
        json={"queue_label": "extract_dlq", "job_id": int(job_adm.id)},
        headers={"Authorization": f"Bearer {jwt_token}"},
    )
    assert r.status_code == 403
