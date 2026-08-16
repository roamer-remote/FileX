# Copyright (c) 2026 徐泽宇
"""059 P1 T-10：workspaces 成员 API + workspace_user_roles。"""

from __future__ import annotations

from models.enterprise_rbac import PERM_MANAGE, SUBJECT_USER, FolderAcl, WorkspaceUserRole
from models.workspace import WorkspaceMember
from services.auth_service import create_access_token
from services.system_setting_service import (
    KEY_ENTERPRISE_RBAC_ENABLED,
    KEY_SHARED_WORKSPACES_ENABLED,
    update_settings,
)
from services.workspace_service import create_shared_workspace, set_member_role
from tests.conftest import _create_user


def _enable_shared_and_rbac(db_session) -> None:
    update_settings(
        db_session,
        {
            KEY_SHARED_WORKSPACES_ENABLED: "true",
            KEY_ENTERPRISE_RBAC_ENABLED: "true",
        },
    )


def _root_manage_acl(db_session, *, workspace_id, user_id):
    db_session.add(
        FolderAcl(
            workspace_id=workspace_id,
            folder_id=None,
            subject_type=SUBJECT_USER,
            subject_id=user_id,
            permission=PERM_MANAGE,
        )
    )
    db_session.flush()


class TestWorkspaceMembersRbac:
    def test_site_admin_upsert_syncs_workspace_user_roles(
        self, client, db_session, admin_user,
    ):
        _enable_shared_and_rbac(db_session)
        target = _create_user(db_session, "t10_target")
        shared = create_shared_workspace(db_session, name="T10 角色库", owner=admin_user)
        db_session.commit()

        token = create_access_token(admin_user.id, admin_user.password_rev)
        r = client.post(
            f"/api/workspaces/{shared.id}/members",
            headers={"Authorization": f"Bearer {token}"},
            json={"user_id": target.id, "role": "contributor"},
        )
        assert r.status_code == 200, r.text
        assert r.json()["role"] == "editor"

        wur = (
            db_session.query(WorkspaceUserRole)
            .filter(
                WorkspaceUserRole.workspace_id == shared.id,
                WorkspaceUserRole.user_id == target.id,
            )
            .all()
        )
        assert len(wur) == 1

    def test_list_members_shows_enterprise_role_slug(
        self, client, db_session, admin_user,
    ):
        _enable_shared_and_rbac(db_session)
        target = _create_user(db_session, "t10_list")
        shared = create_shared_workspace(db_session, name="T10 列表库", owner=admin_user)
        set_member_role(db_session, shared.id, target.id, "viewer")
        db_session.commit()

        token = create_access_token(admin_user.id, admin_user.password_rev)
        client.post(
            f"/api/workspaces/{shared.id}/members",
            headers={"Authorization": f"Bearer {token}"},
            json={"user_id": target.id, "role": "curator"},
        )

        r = client.get(
            f"/api/workspaces/{shared.id}/members",
            headers={"Authorization": f"Bearer {token}"},
        )
        assert r.status_code == 200, r.text
        by_id = {row["user_id"]: row["role"] for row in r.json()}
        assert by_id[target.id] == "folder_admin"

    def test_root_manage_can_add_viewer_without_role_assign(
        self, client, db_session, regular_user,
    ):
        _enable_shared_and_rbac(db_session)
        manager = _create_user(db_session, "t10_mgr")
        target = _create_user(db_session, "t10_new")
        shared = create_shared_workspace(db_session, name="T10 根管库", owner=regular_user)
        set_member_role(db_session, shared.id, manager.id, "viewer")
        _root_manage_acl(db_session, workspace_id=shared.id, user_id=manager.id)
        db_session.commit()

        token = create_access_token(manager.id, manager.password_rev)
        r = client.post(
            f"/api/workspaces/{shared.id}/members",
            headers={"Authorization": f"Bearer {token}"},
            json={"user_id": target.id, "role": "viewer"},
        )
        assert r.status_code == 200, r.text
        assert (
            db_session.query(WorkspaceMember)
            .filter(
                WorkspaceMember.workspace_id == shared.id,
                WorkspaceMember.user_id == target.id,
            )
            .count()
            == 1
        )
        assert (
            db_session.query(WorkspaceUserRole)
            .filter(
                WorkspaceUserRole.workspace_id == shared.id,
                WorkspaceUserRole.user_id == target.id,
            )
            .count()
            == 0
        )

    def test_root_manage_cannot_assign_enterprise_role(
        self, client, db_session, regular_user,
    ):
        _enable_shared_and_rbac(db_session)
        manager = _create_user(db_session, "t10_mgr2")
        target = _create_user(db_session, "t10_role")
        shared = create_shared_workspace(db_session, name="T10 拒角色库", owner=regular_user)
        set_member_role(db_session, shared.id, manager.id, "viewer")
        _root_manage_acl(db_session, workspace_id=shared.id, user_id=manager.id)
        db_session.commit()

        token = create_access_token(manager.id, manager.password_rev)
        r = client.post(
            f"/api/workspaces/{shared.id}/members",
            headers={"Authorization": f"Bearer {token}"},
            json={"user_id": target.id, "role": "contributor"},
        )
        assert r.status_code == 403, r.text

    def test_root_manage_can_remove_member(
        self, client, db_session, regular_user,
    ):
        _enable_shared_and_rbac(db_session)
        manager = _create_user(db_session, "t10_mgr3")
        target = _create_user(db_session, "t10_rm")
        shared = create_shared_workspace(db_session, name="T10 删成员库", owner=regular_user)
        set_member_role(db_session, shared.id, manager.id, "viewer")
        set_member_role(db_session, shared.id, target.id, "viewer")
        _root_manage_acl(db_session, workspace_id=shared.id, user_id=manager.id)
        db_session.commit()

        token = create_access_token(manager.id, manager.password_rev)
        r = client.delete(
            f"/api/workspaces/{shared.id}/members/{target.id}",
            headers={"Authorization": f"Bearer {token}"},
        )
        assert r.status_code == 204, r.text
        assert (
            db_session.query(WorkspaceMember)
            .filter(
                WorkspaceMember.workspace_id == shared.id,
                WorkspaceMember.user_id == target.id,
            )
            .count()
            == 0
        )

    def test_legacy_path_unchanged_when_rbac_off(
        self, client, db_session, regular_user,
    ):
        update_settings(db_session, {KEY_SHARED_WORKSPACES_ENABLED: "true"})
        target = _create_user(db_session, "t10_legacy")
        shared = create_shared_workspace(db_session, name="T10 legacy", owner=regular_user)
        db_session.commit()

        token = create_access_token(regular_user.id, regular_user.password_rev)
        r = client.post(
            f"/api/workspaces/{shared.id}/members",
            headers={"Authorization": f"Bearer {token}"},
            json={"user_id": target.id, "role": "contributor"},
        )
        assert r.status_code == 200, r.text
        assert r.json()["role"] == "contributor"
        assert (
            db_session.query(WorkspaceUserRole)
            .filter(
                WorkspaceUserRole.workspace_id == shared.id,
                WorkspaceUserRole.user_id == target.id,
            )
            .count()
            == 0
        )
