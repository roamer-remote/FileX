# Copyright (c) 2026 徐泽宇
"""GET /api/files search：文件名 + 资料 ID 集成测试。"""

from __future__ import annotations

from models.file import File as FileModel
from services.auth_service import create_access_token
from services.file_list_search import MAX_FILE_ID
from services.system_setting_service import (
    KEY_ENTERPRISE_RBAC_ENABLED,
    KEY_SHARED_WORKSPACES_ENABLED,
    update_settings,
)
from services.workspace_service import create_shared_workspace, ensure_personal_workspace, set_member_role
from tests.conftest import _create_user


def _add_file(db_session, *, user_id: int, workspace_id: int, original_name: str) -> FileModel:
    f = FileModel(
        user_id=user_id,
        workspace_id=workspace_id,
        filename=original_name,
        original_name=original_name,
        file_path=f"/tmp/{original_name}",
        file_size=1,
        mime_type="text/plain",
    )
    db_session.add(f)
    db_session.commit()
    db_session.refresh(f)
    return f


def test_files_search_by_filename(client, jwt_token, regular_user, db_session):
    ws = ensure_personal_workspace(db_session, regular_user)
    hit = _add_file(
        db_session,
        user_id=regular_user.id,
        workspace_id=ws.id,
        original_name="alpha-report.pdf",
    )
    _add_file(
        db_session,
        user_id=regular_user.id,
        workspace_id=ws.id,
        original_name="beta-notes.txt",
    )
    h = {"Authorization": f"Bearer {jwt_token}"}
    r = client.get("/api/files", headers=h, params={"search": "alpha"})
    assert r.status_code == 200
    ids = [x["id"] for x in r.json()["items"]]
    assert ids == [hit.id]


def test_files_search_by_numeric_id(client, jwt_token, regular_user, db_session):
    ws = ensure_personal_workspace(db_session, regular_user)
    target = _add_file(
        db_session,
        user_id=regular_user.id,
        workspace_id=ws.id,
        original_name="report.pdf",
    )
    h = {"Authorization": f"Bearer {jwt_token}"}
    r = client.get("/api/files", headers=h, params={"search": str(target.id)})
    assert r.status_code == 200
    assert r.json()["total"] == 1
    assert r.json()["items"][0]["id"] == target.id


def test_files_search_id_prefix_exact(client, jwt_token, regular_user, db_session):
    ws = ensure_personal_workspace(db_session, regular_user)
    target = _add_file(
        db_session,
        user_id=regular_user.id,
        workspace_id=ws.id,
        original_name="other.pdf",
    )
    _add_file(
        db_session,
        user_id=regular_user.id,
        workspace_id=ws.id,
        original_name="abc-notes.pdf",
    )
    h = {"Authorization": f"Bearer {jwt_token}"}
    r = client.get("/api/files", headers=h, params={"search": f"id:{target.id}"})
    assert r.status_code == 200
    assert r.json()["total"] == 1
    assert r.json()["items"][0]["id"] == target.id


def test_files_search_id_empty_suffix(client, jwt_token):
    h = {"Authorization": f"Bearer {jwt_token}"}
    r = client.get("/api/files", headers=h, params={"search": "id:"})
    assert r.status_code == 200
    assert r.json()["total"] == 0


def test_files_search_overflow_digits_filename_only(client, jwt_token, regular_user, db_session):
    ws = ensure_personal_workspace(db_session, regular_user)
    overflow = str(MAX_FILE_ID + 1)
    _add_file(
        db_session,
        user_id=regular_user.id,
        workspace_id=ws.id,
        original_name=f"prefix-{overflow}-suffix.pdf",
    )
    h = {"Authorization": f"Bearer {jwt_token}"}
    r = client.get("/api/files", headers=h, params={"search": overflow})
    assert r.status_code == 200
    assert r.json()["total"] == 1


def test_files_search_hidden_file_by_id_acl(client, db_session, regular_user):
    update_settings(
        db_session,
        {
            KEY_SHARED_WORKSPACES_ENABLED: "true",
            KEY_ENTERPRISE_RBAC_ENABLED: "true",
        },
    )
    member = _create_user(db_session, "search_acl_member")
    shared = create_shared_workspace(db_session, name="搜索 ACL 库", owner=regular_user)
    set_member_role(db_session, shared.id, member.id, "viewer")
    hidden = _add_file(
        db_session,
        user_id=regular_user.id,
        workspace_id=shared.id,
        original_name="secret.pdf",
    )
    token = create_access_token(member.id, member.password_rev)
    h = {"Authorization": f"Bearer {token}"}

    r1 = client.get(
        "/api/files",
        headers=h,
        params={"workspace_id": shared.id, "search": str(hidden.id)},
    )
    assert r1.status_code == 200
    assert r1.json()["total"] == 0

    r2 = client.get(
        "/api/files",
        headers=h,
        params={"workspace_id": shared.id, "search": f"id:{hidden.id}"},
    )
    assert r2.status_code == 200
    assert r2.json()["total"] == 0
