# Copyright (c) 2026 徐泽宇
"""Admin API: delete / purge MQ queue messages."""

from __future__ import annotations

from unittest.mock import patch


def test_admin_delete_mq_queue_message_by_index(client, admin_jwt_token):
    with patch(
        "routers.admin.mutate_queue_messages",
        return_value={"queue_name": "kb.index.dlq", "removed": 1, "message_count": 2},
    ) as mutate:
        res = client.post(
            "/api/admin/mq/queues/kb.index.dlq/messages/delete",
            json={"index": 1},
            headers={"Authorization": f"Bearer {admin_jwt_token}"},
        )

    assert res.status_code == 200
    assert res.json() == {"queue_name": "kb.index.dlq", "removed": 1, "message_count": 2}
    mutate.assert_called_once_with("kb.index.dlq", purge=False, job_id=None, index=1)


def test_admin_purge_mq_queue_messages(client, admin_jwt_token):
    with patch(
        "routers.admin.mutate_queue_messages",
        return_value={"queue_name": "kb.index.dlq", "removed": 3, "message_count": 0},
    ) as mutate:
        res = client.post(
            "/api/admin/mq/queues/kb.index.dlq/messages/delete",
            json={"purge": True},
            headers={"Authorization": f"Bearer {admin_jwt_token}"},
        )

    assert res.status_code == 200
    assert res.json()["removed"] == 3
    mutate.assert_called_once_with("kb.index.dlq", purge=True, job_id=None, index=None)
