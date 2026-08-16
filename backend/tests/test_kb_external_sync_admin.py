# Copyright (c) 2026 徐泽宇
"""049 T-7: admin external sync API."""

from unittest.mock import patch

import pytest
from fastapi import status

from models.kb_enums import ExternalSyncDeletePolicy
from models.kb_external_sync import KbExternalSyncSource
from models.operation_log import OperationLog
from services.kb_external_sync.notion_client import NotionClientError
from services.sync_secret_service import encrypt_sync_secret
from services.workspace_service import create_shared_workspace, ensure_personal_workspace


@pytest.fixture(autouse=True)
def _sync_secret_key(monkeypatch):
    monkeypatch.setenv("FILEX_SYNC_SECRET_KEY", "test-sync-secret-key-049")


def _create_payload(workspace_id: int, secret: str = "ntn_secret_test_token_abcdefghij"):
    return {
        "workspace_id": workspace_id,
        "provider": "notion",
        "secret": secret,
        "config_public_json": {"database_id": "db-001"},
        "delete_policy": "keep_file",
        "is_active": True,
    }


def test_create_source_and_list_preview(client, admin_jwt_token, db_session, admin_user):
    ws = ensure_personal_workspace(db_session, admin_user)
    resp = client.post(
        "/api/admin/external-sync/sources",
        headers={"Authorization": f"Bearer {admin_jwt_token}"},
        json=_create_payload(ws.id),
    )
    assert resp.status_code == status.HTTP_201_CREATED
    data = resp.json()
    assert data["secret_preview"] == "ghij"
    assert "ntn_secret" not in resp.text

    listed = client.get(
        "/api/admin/external-sync/sources",
        headers={"Authorization": f"Bearer {admin_jwt_token}"},
    )
    assert listed.status_code == status.HTTP_200_OK
    assert listed.json()[0]["id"] == data["id"]


def test_workspace_acl_rejects_unmanaged_shared(client, admin_jwt_token, db_session, admin_user, regular_user):
    try:
        ws = create_shared_workspace(db_session, "ext-sync-acl", regular_user)
    except Exception:
        pytest.skip("shared workspace unavailable")
    resp = client.post(
        "/api/admin/external-sync/sources",
        headers={"Authorization": f"Bearer {admin_jwt_token}"},
        json=_create_payload(ws.id),
    )
    assert resp.status_code == status.HTTP_403_FORBIDDEN


@patch("services.kb_external_sync.notion_runner.NotionClient")
def test_test_connection_redacts_token_in_error(mock_client_cls, client, admin_jwt_token, db_session, admin_user):
    ws = ensure_personal_workspace(db_session, admin_user)
    token = "ntn_leaked_secret_token_xyz1234567890"
    create = client.post(
        "/api/admin/external-sync/sources",
        headers={"Authorization": f"Bearer {admin_jwt_token}"},
        json=_create_payload(ws.id, secret=token),
    )
    source_id = create.json()["id"]

    mock_client_cls.return_value.test_connection.side_effect = NotionClientError(
        f"Unauthorized Bearer {token}",
        status_code=401,
    )

    resp = client.post(
        f"/api/admin/external-sync/sources/{source_id}/test-connection",
        headers={"Authorization": f"Bearer {admin_jwt_token}"},
    )
    assert resp.status_code == status.HTTP_400_BAD_REQUEST
    assert token not in resp.text
    assert "****" in resp.json().get("detail", "")

    log = (
        db_session.query(OperationLog)
        .filter(OperationLog.action == "测试外部同步连接", OperationLog.target_id == source_id)
        .order_by(OperationLog.id.desc())
        .first()
    )
    assert log is not None
    assert token not in (log.detail or "")


def test_rotate_secret_updates_preview(client, admin_jwt_token, db_session, admin_user):
    ws = ensure_personal_workspace(db_session, admin_user)
    source_id = client.post(
        "/api/admin/external-sync/sources",
        headers={"Authorization": f"Bearer {admin_jwt_token}"},
        json=_create_payload(ws.id, secret="1234567890123456789012"),
    ).json()["id"]

    resp = client.post(
        f"/api/admin/external-sync/sources/{source_id}/rotate-secret",
        headers={"Authorization": f"Bearer {admin_jwt_token}"},
        json={"secret": "abcdefghijklmnop1234567890"},
    )
    assert resp.status_code == status.HTTP_200_OK
    assert resp.json()["secret_preview"] == "7890"


@patch("routers.admin_external_sync.threading.Thread")
def test_sync_now_returns_202(mock_thread, client, admin_jwt_token, db_session, admin_user):
    ws = ensure_personal_workspace(db_session, admin_user)
    source_id = client.post(
        "/api/admin/external-sync/sources",
        headers={"Authorization": f"Bearer {admin_jwt_token}"},
        json=_create_payload(ws.id),
    ).json()["id"]

    resp = client.post(
        f"/api/admin/external-sync/sources/{source_id}/sync-now",
        headers={"Authorization": f"Bearer {admin_jwt_token}"},
    )
    assert resp.status_code == status.HTTP_202_ACCEPTED
    assert resp.json()["run_id"]
    assert mock_thread.called


def test_delete_policy_hint(client, admin_jwt_token):
    resp = client.get(
        "/api/admin/external-sync/meta/delete-policy-hint",
        headers={"Authorization": f"Bearer {admin_jwt_token}"},
    )
    assert resp.status_code == status.HTTP_200_OK
    assert "不会自动删除本站资料" in resp.json()["hint"]
