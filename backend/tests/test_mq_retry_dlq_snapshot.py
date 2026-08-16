# Copyright (c) 2026 徐泽宇
"""Shared retry/DLQ drain snapshot (092)."""

import json
from unittest.mock import patch

from models.file import File as FileModel
from models.kb_index_job import KbIndexJob
from services.kb_index_service import JOB_QUEUED
from services.rabbitmq_retry_dlq_snapshot_service import (
    get_retry_dlq_snapshot,
    invalidate_retry_dlq_snapshot,
)
from services.rabbitmq_queue_user_service import aggregate_user_mq_queue_counts


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


def test_snapshot_reused_for_multiple_users(db_session, regular_user, admin_user):
    invalidate_retry_dlq_snapshot()

    f_reg = _file(db_session, regular_user.id, "reg.md")
    f_adm = _file(db_session, admin_user.id, "adm.md")
    job_reg = KbIndexJob(user_id=regular_user.id, file_id=f_reg.id, status=JOB_QUEUED)
    job_adm = KbIndexJob(user_id=admin_user.id, file_id=f_adm.id, status=JOB_QUEUED)
    db_session.add_all([job_reg, job_adm])
    db_session.commit()

    bodies = {
        "index_retry": [
            json.dumps({"job_id": job_reg.id}).encode(),
            json.dumps({"job_id": job_adm.id}).encode(),
        ],
        "index_dlq": [],
        "post_retry": [],
        "post_dlq": [],
        "extract_retry": [],
        "extract_dlq": [],
    }

    call_count = {"n": 0}

    def counting_drain():
        call_count["n"] += 1
        return {label: [(None, body) for body in body_list] for label, body_list in bodies.items()}

    with patch(
        "services.rabbitmq_retry_dlq_snapshot_service._drain_all_retry_dlq_queues",
        side_effect=counting_drain,
    ):
        counts_reg = aggregate_user_mq_queue_counts(db_session, int(regular_user.id))
        counts_adm = aggregate_user_mq_queue_counts(db_session, int(admin_user.id))

    assert call_count["n"] == 1
    assert counts_reg["index_retry"] == (1, 1)
    assert counts_adm["index_retry"] == (1, 1)
    assert counts_reg["index_dlq"] == (0, 0)


def test_invalidate_snapshot_forces_refresh(db_session, regular_user):
    invalidate_retry_dlq_snapshot()

    f_reg = _file(db_session, regular_user.id, "reg2.md")
    job_reg = KbIndexJob(user_id=regular_user.id, file_id=f_reg.id, status=JOB_QUEUED)
    db_session.add(job_reg)
    db_session.commit()

    call_count = {"n": 0}

    def counting_drain():
        call_count["n"] += 1
        return {
            "index_retry": [(None, json.dumps({"job_id": job_reg.id}).encode())],
            "index_dlq": [],
            "post_retry": [],
            "post_dlq": [],
            "extract_retry": [],
            "extract_dlq": [],
        }

    with patch(
        "services.rabbitmq_retry_dlq_snapshot_service._drain_all_retry_dlq_queues",
        side_effect=counting_drain,
    ):
        get_retry_dlq_snapshot(db_session)
        get_retry_dlq_snapshot(db_session)
        invalidate_retry_dlq_snapshot()
        get_retry_dlq_snapshot(db_session)

    assert call_count["n"] == 2


def test_remove_owner_message_refreshes_counts(db_session, regular_user):
    from services.rabbitmq_queue_user_service import (
        aggregate_user_mq_queue_counts,
        remove_owner_queue_message,
    )

    invalidate_retry_dlq_snapshot()

    f_reg = _file(db_session, regular_user.id, "reg-remove.md")
    job_reg = KbIndexJob(user_id=regular_user.id, file_id=f_reg.id, status=JOB_QUEUED)
    db_session.add(job_reg)
    db_session.commit()

    drain_state = {"has_message": True}

    def flexible_drain():
        if drain_state["has_message"]:
            return {
                "index_retry": [(None, json.dumps({"job_id": job_reg.id}).encode())],
                "index_dlq": [],
                "post_retry": [],
                "post_dlq": [],
                "extract_retry": [],
                "extract_dlq": [],
            }
        return {
            label: []
            for label in (
                "index_retry",
                "index_dlq",
                "post_retry",
                "post_dlq",
                "extract_retry",
                "extract_dlq",
            )
        }

    with patch(
        "services.rabbitmq_retry_dlq_snapshot_service._drain_all_retry_dlq_queues",
        side_effect=flexible_drain,
    ), patch(
        "services.rabbitmq_queue_admin_service.mutate_queue_messages",
        return_value={"queue_name": "kb.index.retry", "removed": 1, "message_count": 0},
    ):
        counts_before = aggregate_user_mq_queue_counts(db_session, int(regular_user.id))
        assert counts_before["index_retry"] == (1, 1)

        remove_owner_queue_message(
            db_session,
            owner_user_id=int(regular_user.id),
            queue_label="index_retry",
            job_id=int(job_reg.id),
        )

        drain_state["has_message"] = False
        counts_after = aggregate_user_mq_queue_counts(db_session, int(regular_user.id))
        assert counts_after["index_retry"] == (0, 0)
