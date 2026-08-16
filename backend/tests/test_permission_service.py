# Copyright (c) 2026 徐泽宇
"""059 PermissionService 真值表测试（P0 T-5）。"""

from __future__ import annotations

import pytest

from models.enterprise_rbac import (
    PERM_LIST,
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
from services.permission_service import effective_folder_permission
from services.system_setting_service import KEY_ENTERPRISE_RBAC_ENABLED, update_settings
from services.workspace_service import create_shared_workspace, set_member_role
from tests.conftest import _create_user


def _enable_rbac(db_session) -> None:
    update_settings(db_session, {KEY_ENTERPRISE_RBAC_ENABLED: "true"})


def _add_acl(
    db_session,
    *,
    workspace_id: int,
    folder_id: int | None,
    subject_type: str,
    subject_id: int,
    permission: str,
) -> None:
    db_session.add(
        FolderAcl(
            workspace_id=workspace_id,
            folder_id=folder_id,
            subject_type=subject_type,
            subject_id=subject_id,
            permission=permission,
        )
    )
    db_session.flush()


def _assign_role(db_session, *, workspace_id: int, user_id: int, slug: str) -> None:
    role = get_enterprise_role_by_slug(db_session, slug)
    db_session.add(
        WorkspaceUserRole(
            workspace_id=workspace_id,
            user_id=user_id,
            role_id=role.id,
        )
    )
    db_session.flush()


class TestPermissionServiceTruthTable:
    @pytest.fixture(autouse=True)
    def _enable_rbac(self, db_session):
        _enable_rbac(db_session)

    def test_user_tier_lower_permission_masks_role_manage(self, db_session, regular_user):
        """T-27d：user tier 较低权限遮蔽同目录 role manage（降权）。"""
        owner = regular_user
        member = _create_user(db_session, "rbac_mask_member")
        shared = create_shared_workspace(db_session, name="遮蔽测试库", owner=owner)
        set_member_role(db_session, shared.id, member.id, "viewer")
        folder = Folder(name="docs", workspace_id=shared.id, user_id=owner.id, sort_order=0)
        db_session.add(folder)
        db_session.flush()

        editor = get_enterprise_role_by_slug(db_session, "editor")
        _assign_role(db_session, workspace_id=shared.id, user_id=member.id, slug="editor")
        _add_acl(
            db_session,
            workspace_id=shared.id,
            folder_id=folder.id,
            subject_type=SUBJECT_USER,
            subject_id=member.id,
            permission=PERM_LIST,
        )
        _add_acl(
            db_session,
            workspace_id=shared.id,
            folder_id=folder.id,
            subject_type=SUBJECT_ROLE,
            subject_id=editor.id,
            permission=PERM_MANAGE,
        )
        db_session.commit()

        assert (
            effective_folder_permission(db_session, member, shared.id, folder.id)
            == PERM_LIST
        )

    def test_root_manage_on_null_folder_id(self, db_session, regular_user):
        owner = regular_user
        member = _create_user(db_session, "rbac_root_manage")
        shared = create_shared_workspace(db_session, name="根权限库", owner=owner)
        set_member_role(db_session, shared.id, member.id, "viewer")
        _add_acl(
            db_session,
            workspace_id=shared.id,
            folder_id=None,
            subject_type=SUBJECT_USER,
            subject_id=member.id,
            permission=PERM_MANAGE,
        )
        db_session.commit()

        assert effective_folder_permission(db_session, member, shared.id, None) == PERM_MANAGE

    def test_workspace_scoped_roles_do_not_leak_across_workspaces(self, db_session, regular_user):
        owner = regular_user
        member = _create_user(db_session, "rbac_ws_isolation")
        ws1 = create_shared_workspace(db_session, name="空间一", owner=owner)
        ws2 = create_shared_workspace(db_session, name="空间二", owner=owner)
        set_member_role(db_session, ws1.id, member.id, "viewer")
        set_member_role(db_session, ws2.id, member.id, "viewer")
        folder2 = Folder(name="secret", workspace_id=ws2.id, user_id=owner.id, sort_order=0)
        db_session.add(folder2)
        db_session.flush()

        editor = get_enterprise_role_by_slug(db_session, "editor")
        _assign_role(db_session, workspace_id=ws1.id, user_id=member.id, slug="editor")
        _add_acl(
            db_session,
            workspace_id=ws2.id,
            folder_id=folder2.id,
            subject_type=SUBJECT_ROLE,
            subject_id=editor.id,
            permission=PERM_WRITE,
        )
        db_session.commit()

        assert effective_folder_permission(db_session, member, ws2.id, folder2.id) is None

    def test_department_acl_requires_exact_primary_department_match(self, db_session, regular_user):
        owner = regular_user
        member = _create_user(db_session, "rbac_dept_exact")
        shared = create_shared_workspace(db_session, name="部门 ACL 库", owner=owner)
        set_member_role(db_session, shared.id, member.id, "viewer")
        folder = Folder(name="研发资料", workspace_id=shared.id, user_id=owner.id, sort_order=0)
        db_session.add(folder)
        db_session.flush()

        root_id = (
            db_session.query(Department.id)
            .filter(Department.parent_id.is_(None))
            .one()[0]
        )
        child = Department(name="测试组", parent_id=root_id, sort_order=1)
        db_session.add(child)
        db_session.flush()

        member.primary_department_id = child.id
        db_session.add(member)
        _add_acl(
            db_session,
            workspace_id=shared.id,
            folder_id=folder.id,
            subject_type=SUBJECT_DEPARTMENT,
            subject_id=root_id,
            permission=PERM_READ,
        )
        db_session.commit()

        assert effective_folder_permission(db_session, member, shared.id, folder.id) is None

        member.primary_department_id = root_id
        db_session.add(member)
        db_session.commit()
        assert effective_folder_permission(db_session, member, shared.id, folder.id) == PERM_READ

    def test_inactive_role_does_not_match_acl(self, db_session, regular_user):
        owner = regular_user
        member = _create_user(db_session, "rbac_inactive_role")
        shared = create_shared_workspace(db_session, name="禁用角色库", owner=owner)
        set_member_role(db_session, shared.id, member.id, "viewer")
        folder = Folder(name="locked", workspace_id=shared.id, user_id=owner.id, sort_order=0)
        db_session.add(folder)
        db_session.flush()

        editor = get_enterprise_role_by_slug(db_session, "editor")
        editor.is_active = False
        db_session.add(editor)
        _assign_role(db_session, workspace_id=shared.id, user_id=member.id, slug="editor")
        _add_acl(
            db_session,
            workspace_id=shared.id,
            folder_id=folder.id,
            subject_type=SUBJECT_ROLE,
            subject_id=editor.id,
            permission=PERM_WRITE,
        )
        db_session.commit()

        assert effective_folder_permission(db_session, member, shared.id, folder.id) is None

    def test_same_tier_role_grants_take_max(self, db_session, regular_user):
        owner = regular_user
        member = _create_user(db_session, "rbac_role_max")
        shared = create_shared_workspace(db_session, name="同 tier max", owner=owner)
        set_member_role(db_session, shared.id, member.id, "viewer")
        folder = Folder(name="mix", workspace_id=shared.id, user_id=owner.id, sort_order=0)
        db_session.add(folder)
        db_session.flush()

        viewer = get_enterprise_role_by_slug(db_session, "viewer")
        editor = get_enterprise_role_by_slug(db_session, "editor")
        _assign_role(db_session, workspace_id=shared.id, user_id=member.id, slug="viewer")
        _assign_role(db_session, workspace_id=shared.id, user_id=member.id, slug="editor")
        _add_acl(
            db_session,
            workspace_id=shared.id,
            folder_id=folder.id,
            subject_type=SUBJECT_ROLE,
            subject_id=viewer.id,
            permission=PERM_READ,
        )
        _add_acl(
            db_session,
            workspace_id=shared.id,
            folder_id=folder.id,
            subject_type=SUBJECT_ROLE,
            subject_id=editor.id,
            permission=PERM_WRITE,
        )
        db_session.commit()

        assert effective_folder_permission(db_session, member, shared.id, folder.id) == PERM_WRITE

    def test_admin_returns_manage_without_acl(self, db_session, regular_user, admin_user):
        shared = create_shared_workspace(db_session, name="admin 库", owner=regular_user)
        assert effective_folder_permission(db_session, admin_user, shared.id, None) == PERM_MANAGE

    def test_rbac_disabled_returns_none(self, db_session, regular_user):
        update_settings(db_session, {KEY_ENTERPRISE_RBAC_ENABLED: "false"})
        member = _create_user(db_session, "rbac_off_member")
        shared = create_shared_workspace(db_session, name="S1 库", owner=regular_user)
        set_member_role(db_session, shared.id, member.id, "viewer")
        _add_acl(
            db_session,
            workspace_id=shared.id,
            folder_id=None,
            subject_type=SUBJECT_USER,
            subject_id=member.id,
            permission=PERM_MANAGE,
        )
        db_session.commit()

        assert effective_folder_permission(db_session, member, shared.id, None) is None


class TestEnterpriseRbacSettings:
    def test_admin_get_enterprise_rbac_defaults(self, client, admin_jwt_token):
        headers = {"Authorization": f"Bearer {admin_jwt_token}"}
        r = client.get("/api/admin/system-settings", headers=headers)
        assert r.status_code == 200, r.text
        body = r.json()
        assert body["enterprise_rbac_enabled"] is False
        assert body["enterprise_rbac_write_mode"] == "dual"

    def test_admin_put_enterprise_rbac_independent_from_shared(self, client, admin_jwt_token):
        headers = {"Authorization": f"Bearer {admin_jwt_token}"}
        client.put(
            "/api/admin/system-settings",
            headers=headers,
            json={"shared_workspaces_enabled": False},
        )
        r = client.put(
            "/api/admin/system-settings",
            headers=headers,
            json={"enterprise_rbac_enabled": True, "enterprise_rbac_write_mode": "new_only"},
        )
        assert r.status_code == 200, r.text
        assert r.json()["enterprise_rbac_enabled"] is True
        assert r.json()["enterprise_rbac_write_mode"] == "new_only"

        r_on = client.put(
            "/api/admin/system-settings",
            headers=headers,
            json={"shared_workspaces_enabled": True, "enterprise_rbac_write_mode": "dual"},
        )
        assert r_on.status_code == 200, r_on.text
        assert r_on.json()["enterprise_rbac_enabled"] is True
        assert r_on.json()["enterprise_rbac_write_mode"] == "dual"

    def test_seed_builtin_roles_present(self, db_session):
        for slug in ("space_admin", "folder_admin", "editor", "viewer", "auditor"):
            role = get_enterprise_role_by_slug(db_session, slug)
            assert role.is_builtin is True
            assert role.is_active is True

    def test_unassigned_department_exists(self, db_session):
        dept_id = get_unassigned_department_id(db_session)
        dept = db_session.get(Department, dept_id)
        assert dept is not None
        assert dept.name == "未分配"
