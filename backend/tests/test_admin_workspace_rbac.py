# Copyright (c) 2026 徐泽宇
"""059 P2 T-16：管理员空间成员企业角色 + 目录 ACL。"""

from __future__ import annotations

from fastapi import status

from models.enterprise_rbac import (
    PERM_MANAGE,
    PERM_READ,
    PERM_WRITE,
    SUBJECT_DEPARTMENT,
    SUBJECT_ROLE,
    SUBJECT_USER,
    Department,
    FolderAcl,
    WorkspaceUserRole,
)
from models.folder import Folder
from services.enterprise_rbac_seed import get_enterprise_role_by_slug, get_unassigned_department_id
from services.system_setting_service import (
    KEY_ENTERPRISE_RBAC_ENABLED,
    KEY_SHARED_WORKSPACES_ENABLED,
    update_settings,
)
from services.workspace_service import create_shared_workspace, ensure_personal_workspace, set_member_role
from tests.conftest import _create_user


def _auth(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


def _enable_shared_and_rbac(db_session) -> None:
    update_settings(
        db_session,
        {
            KEY_SHARED_WORKSPACES_ENABLED: "true",
            KEY_ENTERPRISE_RBAC_ENABLED: "true",
        },
    )


def test_non_admin_forbidden(client, jwt_token, db_session, regular_user):
    shared = create_shared_workspace(db_session, name="T16 鉴权库", owner=regular_user)
    db_session.commit()
    r = client.get(f"/api/admin/workspaces/{shared.id}/folder-acl", headers=_auth(jwt_token))
    assert r.status_code == status.HTTP_403_FORBIDDEN


def test_admin_upsert_member_syncs_workspace_user_roles(
    client, admin_jwt_token, db_session, admin_user, regular_user,
):
    _enable_shared_and_rbac(db_session)
    shared = create_shared_workspace(db_session, name="T16 成员同步库", owner=admin_user)
    db_session.commit()

    r = client.post(
        f"/api/admin/workspaces/{shared.id}/members",
        headers=_auth(admin_jwt_token),
        json={"user_id": regular_user.id, "role": "contributor"},
    )
    assert r.status_code == 200, r.text

    wur = (
        db_session.query(WorkspaceUserRole)
        .filter(
            WorkspaceUserRole.workspace_id == shared.id,
            WorkspaceUserRole.user_id == regular_user.id,
        )
        .all()
    )
    assert len(wur) == 1
    editor = get_enterprise_role_by_slug(db_session, "editor")
    assert wur[0].role_id == editor.id


def test_put_member_roles(client, admin_jwt_token, db_session, admin_user, regular_user):
    _enable_shared_and_rbac(db_session)
    shared = create_shared_workspace(db_session, name="T16 角色库", owner=admin_user)
    set_member_role(db_session, shared.id, regular_user.id, "viewer")
    db_session.commit()

    editor = get_enterprise_role_by_slug(db_session, "editor")
    viewer = get_enterprise_role_by_slug(db_session, "viewer")

    r = client.put(
        f"/api/admin/workspaces/{shared.id}/members/{regular_user.id}/roles",
        headers=_auth(admin_jwt_token),
        json={"role_ids": [editor.id, viewer.id]},
    )
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["user_id"] == regular_user.id
    assert set(body["role_ids"]) == {editor.id, viewer.id}
    assert set(body["role_slugs"]) == {"editor", "viewer"}

    rows = (
        db_session.query(WorkspaceUserRole.role_id)
        .filter(
            WorkspaceUserRole.workspace_id == shared.id,
            WorkspaceUserRole.user_id == regular_user.id,
        )
        .all()
    )
    assert {int(x[0]) for x in rows} == {editor.id, viewer.id}


def test_get_member_roles(client, admin_jwt_token, db_session, admin_user, regular_user):
    _enable_shared_and_rbac(db_session)
    shared = create_shared_workspace(db_session, name="T16 GET 角色库", owner=admin_user)
    set_member_role(db_session, shared.id, regular_user.id, "viewer")
    db_session.commit()

    editor = get_enterprise_role_by_slug(db_session, "editor")
    viewer = get_enterprise_role_by_slug(db_session, "viewer")
    db_session.add(
        WorkspaceUserRole(
            workspace_id=shared.id,
            user_id=regular_user.id,
            role_id=editor.id,
        )
    )
    db_session.add(
        WorkspaceUserRole(
            workspace_id=shared.id,
            user_id=regular_user.id,
            role_id=viewer.id,
        )
    )
    db_session.commit()

    r = client.get(
        f"/api/admin/workspaces/{shared.id}/members/{regular_user.id}/roles",
        headers=_auth(admin_jwt_token),
    )
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["user_id"] == regular_user.id
    assert set(body["role_ids"]) == {editor.id, viewer.id}
    assert set(body["role_slugs"]) == {"editor", "viewer"}


def test_put_member_roles_requires_member(client, admin_jwt_token, db_session, admin_user):
    _enable_shared_and_rbac(db_session)
    shared = create_shared_workspace(db_session, name="T16 非成员库", owner=admin_user)
    outsider = _create_user(db_session, "t16_outsider")
    db_session.commit()

    editor = get_enterprise_role_by_slug(db_session, "editor")
    r = client.put(
        f"/api/admin/workspaces/{shared.id}/members/{outsider.id}/roles",
        headers=_auth(admin_jwt_token),
        json={"role_ids": [editor.id]},
    )
    assert r.status_code == 404
    assert r.json()["detail"] == "用户不是该空间成员"


def test_put_member_roles_rejects_inactive_role(client, admin_jwt_token, db_session, admin_user, regular_user):
    _enable_shared_and_rbac(db_session)
    shared = create_shared_workspace(db_session, name="T16 禁用角色库", owner=admin_user)
    set_member_role(db_session, shared.id, regular_user.id, "viewer")
    r_create = client.post(
        "/api/admin/enterprise-roles",
        headers=_auth(admin_jwt_token),
        json={"slug": "t16_inactive", "name": "已禁用角色", "description": None},
    )
    assert r_create.status_code == 201
    role_id = r_create.json()["id"]
    r_disable = client.put(
        f"/api/admin/enterprise-roles/{role_id}",
        headers=_auth(admin_jwt_token),
        json={"is_active": False},
    )
    assert r_disable.status_code == 200

    r = client.put(
        f"/api/admin/workspaces/{shared.id}/members/{regular_user.id}/roles",
        headers=_auth(admin_jwt_token),
        json={"role_ids": [role_id]},
    )
    assert r.status_code == 400
    assert "禁用" in r.json()["detail"]


def test_get_and_put_folder_acl_root(client, admin_jwt_token, db_session, admin_user, regular_user):
    _enable_shared_and_rbac(db_session)
    shared = create_shared_workspace(db_session, name="T16 ACL 库", owner=admin_user)
    set_member_role(db_session, shared.id, regular_user.id, "viewer")
    editor = get_enterprise_role_by_slug(db_session, "editor")
    db_session.commit()

    r = client.put(
        f"/api/admin/workspaces/{shared.id}/folder-acl",
        headers=_auth(admin_jwt_token),
        json={
            "entries": [
                {
                    "folder_id": None,
                    "subject_type": SUBJECT_ROLE,
                    "subject_id": editor.id,
                    "permission": PERM_READ,
                }
            ]
        },
    )
    assert r.status_code == 200, r.text
    assert r.json()["upserted"] == 1
    assert r.json()["updated"] == 0

    r2 = client.get(f"/api/admin/workspaces/{shared.id}/folder-acl", headers=_auth(admin_jwt_token))
    assert r2.status_code == 200
    assert len(r2.json()) == 1
    assert r2.json()[0]["folder_id"] is None
    assert r2.json()[0]["permission"] == PERM_READ


def test_folder_acl_root_unique_upsert_does_not_duplicate_null_folder_id(
    client, admin_jwt_token, db_session, admin_user,
):
    """T-27g：根 ACL 同键 upsert 不产生重复行。"""
    _enable_shared_and_rbac(db_session)
    shared = create_shared_workspace(db_session, name="T16 根 upsert 库", owner=admin_user)
    editor = get_enterprise_role_by_slug(db_session, "editor")
    db_session.commit()

    payload = {
        "entries": [
            {
                "folder_id": None,
                "subject_type": SUBJECT_ROLE,
                "subject_id": editor.id,
                "permission": PERM_READ,
            }
        ]
    }
    r1 = client.put(
        f"/api/admin/workspaces/{shared.id}/folder-acl",
        headers=_auth(admin_jwt_token),
        json=payload,
    )
    assert r1.status_code == 200
    assert r1.json()["upserted"] == 1

    payload["entries"][0]["permission"] = PERM_WRITE
    r2 = client.put(
        f"/api/admin/workspaces/{shared.id}/folder-acl",
        headers=_auth(admin_jwt_token),
        json=payload,
    )
    assert r2.status_code == 200
    assert r2.json()["upserted"] == 0
    assert r2.json()["updated"] == 1

    count = (
        db_session.query(FolderAcl)
        .filter(
            FolderAcl.workspace_id == shared.id,
            FolderAcl.folder_id.is_(None),
            FolderAcl.subject_type == SUBJECT_ROLE,
            FolderAcl.subject_id == editor.id,
        )
        .count()
    )
    assert count == 1
    row = (
        db_session.query(FolderAcl)
        .filter(
            FolderAcl.workspace_id == shared.id,
            FolderAcl.folder_id.is_(None),
            FolderAcl.subject_type == SUBJECT_ROLE,
            FolderAcl.subject_id == editor.id,
        )
        .one()
    )
    assert row.permission == PERM_WRITE
    assert row.updated_by_user_id is not None
    assert row.updated_at is not None


def test_folder_acl_put_rejects_folder_from_other_workspace(
    client, admin_jwt_token, db_session, admin_user, regular_user,
):
    """T-27f：跨 workspace 目录 ID 拒绝。"""
    _enable_shared_and_rbac(db_session)
    ws1 = create_shared_workspace(db_session, name="T16 空间一", owner=admin_user)
    ws2 = create_shared_workspace(db_session, name="T16 空间二", owner=regular_user)
    folder = Folder(name="跨空间目录", parent_id=None, workspace_id=ws2.id, user_id=regular_user.id)
    db_session.add(folder)
    db_session.flush()
    editor = get_enterprise_role_by_slug(db_session, "editor")
    db_session.commit()

    r_bulk = client.put(
        f"/api/admin/workspaces/{ws1.id}/folder-acl",
        headers=_auth(admin_jwt_token),
        json={
            "entries": [
                {
                    "folder_id": folder.id,
                    "subject_type": SUBJECT_ROLE,
                    "subject_id": editor.id,
                    "permission": PERM_READ,
                }
            ]
        },
    )
    assert r_bulk.status_code == 400
    assert r_bulk.json()["detail"] == "目录不属于该知识空间"

    r_single = client.put(
        f"/api/admin/workspaces/{ws1.id}/folders/{folder.id}/acl",
        headers=_auth(admin_jwt_token),
        json={
            "entries": [
                {
                    "subject_type": SUBJECT_ROLE,
                    "subject_id": editor.id,
                    "permission": PERM_READ,
                }
            ]
        },
    )
    assert r_single.status_code == 400
    assert r_single.json()["detail"] == "目录不属于该知识空间"


def test_folder_acl_rejects_unassigned_department_subject(
    client, admin_jwt_token, db_session, admin_user,
):
    """T-27j：禁止对「未分配」部门配置 ACL。"""
    _enable_shared_and_rbac(db_session)
    shared = create_shared_workspace(db_session, name="T16 未分配部门库", owner=admin_user)
    unassigned_id = get_unassigned_department_id(db_session)
    db_session.commit()

    r = client.put(
        f"/api/admin/workspaces/{shared.id}/folders/root/acl",
        headers=_auth(admin_jwt_token),
        json={
            "entries": [
                {
                    "subject_type": SUBJECT_DEPARTMENT,
                    "subject_id": unassigned_id,
                    "permission": PERM_READ,
                }
            ]
        },
    )
    assert r.status_code == 400
    assert r.json()["detail"] == "不可对「未分配」部门配置目录 ACL"


def test_folder_acl_rejects_personal_workspace(client, admin_jwt_token, db_session, regular_user):
    personal = ensure_personal_workspace(db_session, regular_user)
    db_session.commit()

    r = client.get(
        f"/api/admin/workspaces/{personal.id}/folder-acl",
        headers=_auth(admin_jwt_token),
    )
    assert r.status_code == 400
    assert "共享" in r.json()["detail"]


def test_folder_acl_user_subject_must_be_member(
    client, admin_jwt_token, db_session, admin_user,
):
    _enable_shared_and_rbac(db_session)
    shared = create_shared_workspace(db_session, name="T16 用户主体库", owner=admin_user)
    outsider = _create_user(db_session, "t16_acl_outsider")
    db_session.commit()

    r = client.put(
        f"/api/admin/workspaces/{shared.id}/folders/root/acl",
        headers=_auth(admin_jwt_token),
        json={
            "entries": [
                {
                    "subject_type": SUBJECT_USER,
                    "subject_id": outsider.id,
                    "permission": PERM_MANAGE,
                }
            ]
        },
    )
    assert r.status_code == 400
    assert r.json()["detail"] == "ACL 用户主体须为该空间成员"


def test_put_single_folder_acl_via_root_alias(
    client, admin_jwt_token, db_session, admin_user, regular_user,
):
    _enable_shared_and_rbac(db_session)
    shared = create_shared_workspace(db_session, name="T16 单目录库", owner=admin_user)
    set_member_role(db_session, shared.id, regular_user.id, "viewer")
    db_session.commit()

    r = client.put(
        f"/api/admin/workspaces/{shared.id}/folders/root/acl",
        headers=_auth(admin_jwt_token),
        json={
            "entries": [
                {
                    "subject_type": SUBJECT_USER,
                    "subject_id": regular_user.id,
                    "permission": PERM_MANAGE,
                }
            ]
        },
    )
    assert r.status_code == 200
    assert r.json()["upserted"] == 1
