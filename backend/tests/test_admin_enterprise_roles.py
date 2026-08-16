# Copyright (c) 2026 徐泽宇
"""059 P2 T-14：管理员企业角色 CRUD + T-27i CASCADE 删除。"""

from __future__ import annotations

from fastapi import status

from models.enterprise_rbac import (
    BUILTIN_ROLE_SLUGS,
    PERM_WRITE,
    SUBJECT_ROLE,
    EnterpriseRole,
    FolderAcl,
    WorkspaceUserRole,
)
from services.enterprise_rbac_seed import get_enterprise_role_by_slug
from services.workspace_service import create_shared_workspace, set_member_role


def _auth(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


def test_non_admin_forbidden(client, jwt_token):
    r = client.get("/api/admin/enterprise-roles", headers=_auth(jwt_token))
    assert r.status_code == status.HTTP_403_FORBIDDEN


def test_admin_list_includes_builtin_roles(client, admin_jwt_token):
    r = client.get("/api/admin/enterprise-roles", headers=_auth(admin_jwt_token))
    assert r.status_code == 200
    slugs = {item["slug"] for item in r.json()}
    assert slugs >= set(BUILTIN_ROLE_SLUGS)
    editor = next(x for x in r.json() if x["slug"] == "editor")
    assert editor["is_builtin"] is True
    assert editor["is_active"] is True


def test_admin_create_update_delete_custom_role(client, admin_jwt_token):
    r = client.post(
        "/api/admin/enterprise-roles",
        headers=_auth(admin_jwt_token),
        json={"slug": "custom_reviewer", "name": "复核员", "description": "自定义"},
    )
    assert r.status_code == 201
    role_id = r.json()["id"]
    assert r.json()["is_builtin"] is False

    r2 = client.put(
        f"/api/admin/enterprise-roles/{role_id}",
        headers=_auth(admin_jwt_token),
        json={"name": "高级复核员", "is_active": False},
    )
    assert r2.status_code == 200
    assert r2.json()["name"] == "高级复核员"
    assert r2.json()["is_active"] is False

    r3 = client.delete(f"/api/admin/enterprise-roles/{role_id}", headers=_auth(admin_jwt_token))
    assert r3.status_code == 200
    assert r3.json()["deleted_user_role_assignments"] == 0
    assert r3.json()["deleted_acl_rows"] == 0


def test_cannot_create_reserved_builtin_slug(client, admin_jwt_token):
    r = client.post(
        "/api/admin/enterprise-roles",
        headers=_auth(admin_jwt_token),
        json={"slug": "editor", "name": "假编辑者"},
    )
    assert r.status_code == 400
    assert "内置" in r.json()["detail"]


def test_cannot_delete_builtin_role(client, admin_jwt_token, db_session):
    role = get_enterprise_role_by_slug(db_session, "viewer")
    r = client.delete(f"/api/admin/enterprise-roles/{role.id}", headers=_auth(admin_jwt_token))
    assert r.status_code == 400
    assert r.json()["detail"] == "内置角色不可删除"


def test_delete_custom_role_cascades_to_workspace_user_roles_and_folder_acl(
    client, admin_jwt_token, db_session, regular_user
):
    """T-27i：删自定义角色 CASCADE workspace_user_roles + folder_acl。"""
    role = EnterpriseRole(
        slug="temp_auditor",
        name="临时审计",
        description=None,
        is_builtin=False,
        is_active=True,
    )
    db_session.add(role)
    db_session.flush()

    shared = create_shared_workspace(db_session, name="角色删除测试库", owner=regular_user)
    member = regular_user
    set_member_role(db_session, shared.id, member.id, "viewer")
    db_session.add(
        WorkspaceUserRole(workspace_id=shared.id, user_id=member.id, role_id=role.id)
    )
    acl = FolderAcl(
        workspace_id=shared.id,
        folder_id=None,
        subject_type=SUBJECT_ROLE,
        subject_id=role.id,
        permission=PERM_WRITE,
    )
    db_session.add(acl)
    db_session.commit()
    db_session.refresh(role)

    r = client.delete(f"/api/admin/enterprise-roles/{role.id}", headers=_auth(admin_jwt_token))
    assert r.status_code == 200
    body = r.json()
    assert body["deleted_user_role_assignments"] == 1
    assert body["deleted_acl_rows"] == 1
    assert "temp_auditor" in body["message"]

    assert db_session.get(EnterpriseRole, role.id) is None
    assert (
        db_session.query(WorkspaceUserRole)
        .filter(WorkspaceUserRole.role_id == role.id)
        .count()
        == 0
    )
    assert (
        db_session.query(FolderAcl)
        .filter(FolderAcl.subject_type == SUBJECT_ROLE, FolderAcl.subject_id == role.id)
        .count()
        == 0
    )


def test_update_builtin_role_is_active(client, admin_jwt_token, db_session):
    role = get_enterprise_role_by_slug(db_session, "auditor")
    r = client.put(
        f"/api/admin/enterprise-roles/{role.id}",
        headers=_auth(admin_jwt_token),
        json={"is_active": False},
    )
    assert r.status_code == 200
    assert r.json()["is_active"] is False

    r2 = client.put(
        f"/api/admin/enterprise-roles/{role.id}",
        headers=_auth(admin_jwt_token),
        json={"is_active": True},
    )
    assert r2.status_code == 200
    assert r2.json()["is_active"] is True




def test_cannot_create_role_with_duplicate_slug(client, admin_jwt_token):
    r1 = client.post(
        "/api/admin/enterprise-roles",
        headers=_auth(admin_jwt_token),
        json={"slug": "dup_role_slug", "name": "角色一"},
    )
    assert r1.status_code == 201

    r2 = client.post(
        "/api/admin/enterprise-roles",
        headers=_auth(admin_jwt_token),
        json={"slug": "dup_role_slug", "name": "角色二"},
    )
    assert r2.status_code == 400
    assert r2.json()["detail"] == "企业角色 slug 已存在"


def test_update_role_not_found(client, admin_jwt_token):
    r = client.put(
        "/api/admin/enterprise-roles/999999",
        headers=_auth(admin_jwt_token),
        json={"name": "不存在"},
    )
    assert r.status_code == 404
    assert r.json()["detail"] == "企业角色不存在"

def test_delete_role_not_found(client, admin_jwt_token):
    r = client.delete("/api/admin/enterprise-roles/999999", headers=_auth(admin_jwt_token))
    assert r.status_code == 404
    assert r.json()["detail"] == "企业角色不存在"
