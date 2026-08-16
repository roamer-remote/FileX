# Copyright (c) 2026 徐泽宇
"""Admin bulk KB reindex endpoint.

Authors:
    徐泽宇

Copyright:
    © 2026 徐泽宇
"""

from unittest.mock import patch

from models.file import File as FileModel


def test_admin_reindex_all_requires_admin(client, jwt_token):
    r = client.post("/api/admin/kb/reindex-all", json={"force": True}, headers={"Authorization": f"Bearer {jwt_token}"})
    assert r.status_code == 403


@patch("services.kb_reindex_all_service.publish_index_job")
@patch("services.kb_reindex_all_service.enqueue_index")
def test_admin_reindex_all_enqueues(mock_enqueue, mock_publish, client, admin_jwt_token, db_session, regular_user):
    mock_enqueue.return_value = 101
    f = FileModel(
        filename="a",
        original_name="note.pdf",
        file_path="/tmp/a",
        file_size=1,
        mime_type="application/pdf",
        user_id=regular_user.id,
        has_md=True,
        index_status="ready",
        index_source_hash="abc123",
        kb_index_manual_override=True,
    )
    db_session.add(f)
    db_session.commit()

    r = client.post(
        "/api/admin/kb/reindex-all",
        json={"force": True, "user_id": regular_user.id},
        headers={"Authorization": f"Bearer {admin_jwt_token}"},
    )
    assert r.status_code == 200
    data = r.json()
    assert data["candidate_count"] == 1
    assert data["enqueued_count"] == 1
    db_session.refresh(f)
    assert f.index_source_hash is None
    assert f.kb_index_manual_override is False
    mock_enqueue.assert_called_once()
    mock_publish.assert_called_once()
