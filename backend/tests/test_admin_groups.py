# Copyright (c) 2026 徐泽宇
"""059 P2 T-13：管理员用户组 CRUD。"""

from __future__ import annotations

from fastapi import status

from models.enterprise_rbac import PERM_READ, SUBJECT_GROUP, FolderAcl, Group, UserGroup
from services.workspace_service import create_shared_workspace


def _auth(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


def test_non_admin_forbidden(client, jwt_token):
    r = client.get("/api/admin/groups", headers=_auth(jwt_token))
    assert r.status_code == status.HTTP_403_FORBIDDEN


def test_admin_create_update_delete_group(client, admin_jwt_token):
    r = client.post(
        "/api/admin/groups",
        headers=_auth(admin_jwt_token),
        json={"name": "研发组", "description": "研发团队"},
    )
    assert r.status_code == 201
    group_id = r.json()["id"]
    assert r.json()["name"] == "研发组"
    assert r.json()["description"] == "研发团队"

    r2 = client.get("/api/admin/groups", headers=_auth(admin_jwt_token))
    assert r2.status_code == 200
    assert any(g["id"] == group_id for g in r2.json())

    r3 = client.put(
        f"/api/admin/groups/{group_id}",
        headers=_auth(admin_jwt_token),
        json={"name": "研发中心", "description": ""},
    )
    assert r3.status_code == 200
    assert r3.json()["name"] == "研发中心"
    assert r3.json()["description"] is None

    r4 = client.delete(f"/api/admin/groups/{group_id}", headers=_auth(admin_jwt_token))
    assert r4.status_code == 204


def test_create_group_duplicate_name_returns_400(client, admin_jwt_token):
    r1 = client.post(
        "/api/admin/groups",
        headers=_auth(admin_jwt_token),
        json={"name": "唯一组"},
    )
    assert r1.status_code == 201

    r2 = client.post(
        "/api/admin/groups",
        headers=_auth(admin_jwt_token),
        json={"name": "唯一组"},
    )
    assert r2.status_code == 400
    assert r2.json()["detail"] == "用户组名称已存在"


def test_update_group_duplicate_name_returns_400(client, admin_jwt_token):
    r1 = client.post(
        "/api/admin/groups",
        headers=_auth(admin_jwt_token),
        json={"name": "组A"},
    )
    r2 = client.post(
        "/api/admin/groups",
        headers=_auth(admin_jwt_token),
        json={"name": "组B"},
    )
    assert r1.status_code == 201 and r2.status_code == 201

    r3 = client.put(
        f"/api/admin/groups/{r2.json()['id']}",
        headers=_auth(admin_jwt_token),
        json={"name": "组A"},
    )
    assert r3.status_code == 400
    assert r3.json()["detail"] == "用户组名称已存在"


def test_delete_group_with_acl_returns_409_and_affected_acls(
    client, admin_jwt_token, db_session, regular_user
):
    group = Group(name="ACL 组", description=None)
    db_session.add(group)
    db_session.flush()

    shared = create_shared_workspace(db_session, name="组 ACL 测试库", owner=regular_user)
    acl = FolderAcl(
        workspace_id=shared.id,
        folder_id=None,
        subject_type=SUBJECT_GROUP,
        subject_id=group.id,
        permission=PERM_READ,
    )
    db_session.add(acl)
    db_session.commit()
    db_session.refresh(acl)

    r = client.delete(f"/api/admin/groups/{group.id}", headers=_auth(admin_jwt_token))
    assert r.status_code == 409
    body = r.json()
    assert "ACL" in body["detail"]
    assert body["affected_acl_ids"] == [acl.id]

    still = db_session.get(Group, group.id)
    assert still is not None


def test_delete_group_cascades_user_groups(client, admin_jwt_token, db_session, regular_user):
    group = Group(name="成员组", description=None)
    db_session.add(group)
    db_session.flush()
    db_session.add(UserGroup(user_id=regular_user.id, group_id=group.id))
    db_session.commit()

    r = client.delete(f"/api/admin/groups/{group.id}", headers=_auth(admin_jwt_token))
    assert r.status_code == 204

    assert db_session.get(Group, group.id) is None
    assert (
        db_session.query(UserGroup)
        .filter(UserGroup.group_id == group.id, UserGroup.user_id == regular_user.id)
        .count()
        == 0
    )


def test_delete_group_not_found(client, admin_jwt_token):
    r = client.delete("/api/admin/groups/999999", headers=_auth(admin_jwt_token))
    assert r.status_code == 404
    assert r.json()["detail"] == "用户组不存在"
