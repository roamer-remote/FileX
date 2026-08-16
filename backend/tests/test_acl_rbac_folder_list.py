# Copyright (c) 2026 徐泽宇
"""059 P3 T-19：用户端目录树 list+ 过滤（GET /api/folders）。"""

from __future__ import annotations

from models.enterprise_rbac import PERM_LIST, PERM_MANAGE, PERM_READ, SUBJECT_USER, FolderAcl
from models.folder import Folder
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


def _enable_shared_only(db_session) -> None:
    update_settings(
        db_session,
        {
            KEY_SHARED_WORKSPACES_ENABLED: "true",
            KEY_ENTERPRISE_RBAC_ENABLED: "false",
        },
    )


def _add_acl(db_session, *, workspace_id, folder_id, user_id, permission):
    db_session.add(
        FolderAcl(
            workspace_id=workspace_id,
            folder_id=folder_id,
            subject_type=SUBJECT_USER,
            subject_id=user_id,
            permission=permission,
        )
    )
    db_session.flush()


def _folder(db_session, *, workspace_id, owner_id, name, parent_id=None):
    f = Folder(
        name=name,
        workspace_id=workspace_id,
        user_id=owner_id,
        parent_id=parent_id,
        sort_order=0,
    )
    db_session.add(f)
    db_session.flush()
    return f


class TestFolderListRbacFilter:
    def test_zero_acl_member_sees_no_folders(self, client, db_session, regular_user):
        _enable_shared_and_rbac(db_session)
        member = _create_user(db_session, "zero_acl_tree")
        shared = create_shared_workspace(db_session, name="零 ACL 树", owner=regular_user)
        set_member_role(db_session, shared.id, member.id, "viewer")
        _folder(db_session, workspace_id=shared.id, owner_id=regular_user.id, name="hidden")
        db_session.commit()

        h = {"Authorization": f"Bearer {create_access_token(member.id, member.password_rev)}"}
        r = client.get("/api/folders", headers=h, params={"workspace_id": shared.id})
        assert r.status_code == 200, r.text
        assert r.json() == []

    def test_read_acl_makes_folder_visible_in_tree(self, client, db_session, regular_user):
        _enable_shared_and_rbac(db_session)
        member = _create_user(db_session, "read_tree_member")
        shared = create_shared_workspace(db_session, name="读可见树", owner=regular_user)
        set_member_role(db_session, shared.id, member.id, "viewer")
        folder = _folder(db_session, workspace_id=shared.id, owner_id=regular_user.id, name="docs")
        _add_acl(
            db_session,
            workspace_id=shared.id,
            folder_id=folder.id,
            user_id=member.id,
            permission=PERM_READ,
        )
        db_session.commit()

        h = {"Authorization": f"Bearer {create_access_token(member.id, member.password_rev)}"}
        r = client.get("/api/folders", headers=h, params={"workspace_id": shared.id})
        assert r.status_code == 200, r.text
        names = {item["name"] for item in r.json()}
        assert names == {"docs"}

    def test_manage_acl_makes_folder_visible_in_tree(self, client, db_session, regular_user):
        _enable_shared_and_rbac(db_session)
        member = _create_user(db_session, "manage_tree_member")
        shared = create_shared_workspace(db_session, name="manage 可见树", owner=regular_user)
        set_member_role(db_session, shared.id, member.id, "viewer")
        folder = _folder(db_session, workspace_id=shared.id, owner_id=regular_user.id, name="mgmt")
        _add_acl(
            db_session,
            workspace_id=shared.id,
            folder_id=folder.id,
            user_id=member.id,
            permission=PERM_MANAGE,
        )
        db_session.commit()

        h = {"Authorization": f"Bearer {create_access_token(member.id, member.password_rev)}"}
        r = client.get("/api/folders", headers=h, params={"workspace_id": shared.id})
        assert r.status_code == 200, r.text
        assert {item["name"] for item in r.json()} == {"mgmt"}

    def test_list_only_acl_makes_folder_visible(self, client, db_session, regular_user):
        _enable_shared_and_rbac(db_session)
        member = _create_user(db_session, "list_only_member")
        shared = create_shared_workspace(db_session, name="list 树", owner=regular_user)
        set_member_role(db_session, shared.id, member.id, "viewer")
        folder = _folder(db_session, workspace_id=shared.id, owner_id=regular_user.id, name="listed")
        _add_acl(
            db_session,
            workspace_id=shared.id,
            folder_id=folder.id,
            user_id=member.id,
            permission=PERM_LIST,
        )
        db_session.commit()

        h = {"Authorization": f"Bearer {create_access_token(member.id, member.password_rev)}"}
        r = client.get("/api/folders", headers=h, params={"workspace_id": shared.id})
        assert r.status_code == 200, r.text
        assert {item["name"] for item in r.json()} == {"listed"}

    def test_parent_read_child_no_grant_child_hidden(self, client, db_session, regular_user):
        """AC-4：父 read、子无 grant → 子不可见。"""
        _enable_shared_and_rbac(db_session)
        member = _create_user(db_session, "ac4_tree_member")
        shared = create_shared_workspace(db_session, name="AC4 树", owner=regular_user)
        set_member_role(db_session, shared.id, member.id, "viewer")
        parent = _folder(db_session, workspace_id=shared.id, owner_id=regular_user.id, name="parent")
        child = _folder(
            db_session,
            workspace_id=shared.id,
            owner_id=regular_user.id,
            name="child",
            parent_id=parent.id,
        )
        _add_acl(
            db_session,
            workspace_id=shared.id,
            folder_id=parent.id,
            user_id=member.id,
            permission=PERM_READ,
        )
        db_session.commit()

        h = {"Authorization": f"Bearer {create_access_token(member.id, member.password_rev)}"}
        r = client.get("/api/folders", headers=h, params={"workspace_id": shared.id})
        assert r.status_code == 200, r.text
        names = {item["name"] for item in r.json()}
        assert names == {"parent"}
        assert child.id not in {item["id"] for item in r.json()}

    def test_legacy_s1_viewer_sees_all_folders(self, client, db_session, regular_user):
        _enable_shared_only(db_session)
        member = _create_user(db_session, "legacy_tree_member")
        shared = create_shared_workspace(db_session, name="S1 树", owner=regular_user)
        db_session.add(WorkspaceMember(workspace_id=shared.id, user_id=member.id, role="viewer"))
        _folder(db_session, workspace_id=shared.id, owner_id=regular_user.id, name="legacy-dir")
        db_session.commit()

        h_owner = {"Authorization": f"Bearer {create_access_token(regular_user.id, regular_user.password_rev)}"}
        r_mk = client.post(
            "/api/folders",
            headers=h_owner,
            json={"name": "owner-created"},
            params={"workspace_id": shared.id},
        )
        assert r_mk.status_code == 201, r_mk.text

        h = {"Authorization": f"Bearer {create_access_token(member.id, member.password_rev)}"}
        r = client.get("/api/folders", headers=h, params={"workspace_id": shared.id})
        assert r.status_code == 200, r.text
        names = {item["name"] for item in r.json()}
        assert "legacy-dir" in names
        assert "owner-created" in names

class TestZeroAclEmptyState:
    def test_direct_file_counts_flags_zero_acl_member(self, client, db_session, regular_user):
        _enable_shared_and_rbac(db_session)
        member = _create_user(db_session, "zero_acl_flag")
        shared = create_shared_workspace(db_session, name="零 ACL 标记", owner=regular_user)
        set_member_role(db_session, shared.id, member.id, "viewer")
        _folder(db_session, workspace_id=shared.id, owner_id=regular_user.id, name="hidden")
        db_session.commit()

        h = {"Authorization": f"Bearer {create_access_token(member.id, member.password_rev)}"}
        r = client.get("/api/folders/direct-file-counts", headers=h, params={"workspace_id": shared.id})
        assert r.status_code == 200, r.text
        body = r.json()
        assert body["zero_acl_member"] is True
        assert body["uncategorized_file_count"] == 0
        assert body["folder_file_counts"] == {}

    def test_direct_file_counts_not_zero_acl_when_read_grant(self, client, db_session, regular_user):
        _enable_shared_and_rbac(db_session)
        member = _create_user(db_session, "has_acl_flag")
        shared = create_shared_workspace(db_session, name="有 ACL 标记", owner=regular_user)
        set_member_role(db_session, shared.id, member.id, "viewer")
        folder = _folder(db_session, workspace_id=shared.id, owner_id=regular_user.id, name="docs")
        _add_acl(
            db_session,
            workspace_id=shared.id,
            folder_id=folder.id,
            user_id=member.id,
            permission=PERM_READ,
        )
        db_session.commit()

        h = {"Authorization": f"Bearer {create_access_token(member.id, member.password_rev)}"}
        r = client.get("/api/folders/direct-file-counts", headers=h, params={"workspace_id": shared.id})
        assert r.status_code == 200, r.text
        assert r.json()["zero_acl_member"] is False

    def test_legacy_s1_zero_acl_flag_false(self, client, db_session, regular_user):
        _enable_shared_only(db_session)
        member = _create_user(db_session, "legacy_zero_flag")
        shared = create_shared_workspace(db_session, name="S1 标记", owner=regular_user)
        db_session.add(WorkspaceMember(workspace_id=shared.id, user_id=member.id, role="viewer"))
        db_session.commit()

        h = {"Authorization": f"Bearer {create_access_token(member.id, member.password_rev)}"}
        r = client.get("/api/folders/direct-file-counts", headers=h, params={"workspace_id": shared.id})
        assert r.status_code == 200, r.text
        assert r.json()["zero_acl_member"] is False

class TestFolderAclRootTopLevelManagementSemantics:
    """T-27b：空间根 manage 语义（顶层目录 CRUD；不自动管辖子目录）。"""

    def test_folder_acl_root_top_level_management_semantics(
        self, client, db_session, regular_user,
    ):
        _enable_shared_and_rbac(db_session)
        member = _create_user(db_session, "root_mgmt_member")
        shared = create_shared_workspace(db_session, name="根 manage 语义库", owner=regular_user)
        set_member_role(db_session, shared.id, member.id, "contributor")
        child = _folder(
            db_session,
            workspace_id=shared.id,
            owner_id=regular_user.id,
            name="existing-child",
        )
        _add_acl(
            db_session,
            workspace_id=shared.id,
            folder_id=None,
            user_id=member.id,
            permission=PERM_MANAGE,
        )
        db_session.commit()

        h = {"Authorization": f"Bearer {create_access_token(member.id, member.password_rev)}"}

        r_create = client.post(
            "/api/folders",
            headers=h,
            json={"name": "top-level-new"},
            params={"workspace_id": shared.id},
        )
        assert r_create.status_code == 201, r_create.text
        assert r_create.json()["parent_id"] is None

        r_rename_child = client.put(
            f"/api/folders/{child.id}",
            headers=h,
            json={"name": "renamed-child"},
            params={"workspace_id": shared.id},
        )
        assert r_rename_child.status_code == 403, r_rename_child.text

        r_delete_child = client.delete(
            f"/api/folders/{child.id}",
            headers=h,
            params={"workspace_id": shared.id},
        )
        assert r_delete_child.status_code == 403, r_delete_child.text

        read_only = _create_user(db_session, "root_read_only")
        set_member_role(db_session, shared.id, read_only.id, "contributor")
        _add_acl(
            db_session,
            workspace_id=shared.id,
            folder_id=None,
            user_id=read_only.id,
            permission=PERM_READ,
        )
        db_session.commit()
        h_read = {
            "Authorization": f"Bearer {create_access_token(read_only.id, read_only.password_rev)}"
        }
        r_denied = client.post(
            "/api/folders",
            headers=h_read,
            json={"name": "should-fail"},
            params={"workspace_id": shared.id},
        )
        assert r_denied.status_code == 403, r_denied.text

