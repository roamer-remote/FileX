# Copyright (c) 2026 徐泽宇
"""059 P1：acl_service 读路径委托与操作矩阵（T-6～T-8 子集）。"""

from __future__ import annotations

import pytest

from models.enterprise_rbac import PERM_MANAGE, PERM_READ, PERM_WRITE, SUBJECT_USER, FolderAcl
from models.file import File as FileModel
from models.folder import Folder
from models.workspace import ROLE_VIEWER, WorkspaceMember
from services.acl_service import (
    LegacyGrantDeprecatedError,
    accessible_file_ids,
    apply_readable_files_filter,
    create_grant,
)
from services.auth_service import create_access_token
from services.system_setting_service import (
    KEY_ENTERPRISE_RBAC_ENABLED,
    KEY_SHARED_WORKSPACES_ENABLED,
    update_settings,
)
from services.workspace_service import create_shared_workspace, ensure_personal_workspace, set_member_role
from tests.conftest import _create_user


def _enable_shared_and_rbac(db_session) -> None:
    update_settings(
        db_session,
        {
            KEY_SHARED_WORKSPACES_ENABLED: "true",
            KEY_ENTERPRISE_RBAC_ENABLED: "true",
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


def _add_file(db_session, *, owner, workspace_id, name="doc.txt", folder_id=None):
    f = FileModel(
        user_id=owner.id,
        workspace_id=workspace_id,
        folder_id=folder_id,
        filename=name,
        original_name=name,
        file_path=f"/tmp/{name}",
        file_size=1,
        mime_type="text/plain",
        md5_hash="d" * 32,
        has_md=False,
    )
    db_session.add(f)
    db_session.flush()
    return f


class TestAclRbacDelegation:
    def test_zero_acl_member_sees_no_files(self, db_session, regular_user):
        _enable_shared_and_rbac(db_session)
        member = _create_user(db_session, "zero_acl_member")
        shared = create_shared_workspace(db_session, name="零 ACL 库", owner=regular_user)
        set_member_role(db_session, shared.id, member.id, "viewer")
        _add_file(db_session, owner=regular_user, workspace_id=shared.id)
        db_session.commit()

        assert accessible_file_ids(db_session, member, shared.id) == set()

    def test_folder_read_acl_grants_file_access(self, db_session, regular_user):
        _enable_shared_and_rbac(db_session)
        member = _create_user(db_session, "read_acl_member")
        shared = create_shared_workspace(db_session, name="读 ACL 库", owner=regular_user)
        set_member_role(db_session, shared.id, member.id, "viewer")
        folder = Folder(name="docs", workspace_id=shared.id, user_id=regular_user.id, sort_order=0)
        db_session.add(folder)
        db_session.flush()
        f = _add_file(
            db_session,
            owner=regular_user,
            workspace_id=shared.id,
            folder_id=folder.id,
        )
        _add_acl(
            db_session,
            workspace_id=shared.id,
            folder_id=folder.id,
            user_id=member.id,
            permission=PERM_READ,
        )
        db_session.commit()

        allowed = accessible_file_ids(db_session, member, shared.id)
        assert allowed == {f.id}

    def test_sql_subquery_matches_materialized_ids(self, db_session, regular_user):
        _enable_shared_and_rbac(db_session)
        member = _create_user(db_session, "sql_rbac_member")
        shared = create_shared_workspace(db_session, name="SQL RBAC 库", owner=regular_user)
        set_member_role(db_session, shared.id, member.id, "viewer")
        folder = Folder(name="sql", workspace_id=shared.id, user_id=regular_user.id, sort_order=0)
        db_session.add(folder)
        db_session.flush()
        f = _add_file(
            db_session,
            owner=regular_user,
            workspace_id=shared.id,
            folder_id=folder.id,
        )
        _add_acl(
            db_session,
            workspace_id=shared.id,
            folder_id=folder.id,
            user_id=member.id,
            permission=PERM_READ,
        )
        db_session.commit()

        materialized = accessible_file_ids(db_session, member, shared.id)
        q = apply_readable_files_filter(db_session.query(FileModel.id), db_session, member, shared.id)
        sql_ids = {int(r[0]) for r in q.all()}
        assert sql_ids == materialized == {f.id}

    def test_create_grant_rejected_when_rbac_enabled(self, db_session, regular_user):
        _enable_shared_and_rbac(db_session)
        shared = create_shared_workspace(db_session, name="grant 拒绝库", owner=regular_user)
        member = _create_user(db_session, "grant_target")
        db_session.add(WorkspaceMember(workspace_id=shared.id, user_id=member.id, role=ROLE_VIEWER))
        f = _add_file(db_session, owner=regular_user, workspace_id=shared.id)
        db_session.commit()

        with pytest.raises(LegacyGrantDeprecatedError):
            create_grant(
                db_session,
                workspace_id=shared.id,
                resource_type="file",
                resource_id=f.id,
                grantee_user_id=member.id,
                permission="view",
                created_by_user_id=regular_user.id,
            )

    def test_create_grant_works_for_personal_when_rbac_enabled(self, db_session, regular_user):
        _enable_shared_and_rbac(db_session)
        personal = ensure_personal_workspace(db_session, regular_user)
        grantee = _create_user(db_session, "personal_grant_target")
        db_session.add(WorkspaceMember(workspace_id=personal.id, user_id=grantee.id, role=ROLE_VIEWER))
        f = _add_file(db_session, owner=regular_user, workspace_id=personal.id)
        db_session.commit()

        g = create_grant(
            db_session,
            workspace_id=personal.id,
            resource_type="file",
            resource_id=f.id,
            grantee_user_id=grantee.id,
            permission="view",
            created_by_user_id=regular_user.id,
        )
        db_session.commit()
        assert g.id is not None
        assert g.grantee_user_id == grantee.id

    def test_legacy_create_grant_works_when_rbac_off(self, db_session, regular_user):
        update_settings(
            db_session,
            {
                KEY_SHARED_WORKSPACES_ENABLED: "true",
                KEY_ENTERPRISE_RBAC_ENABLED: "false",
            },
        )
        shared = create_shared_workspace(db_session, name="legacy grant 库", owner=regular_user)
        member = _create_user(db_session, "legacy_grant_target")
        db_session.add(WorkspaceMember(workspace_id=shared.id, user_id=member.id, role=ROLE_VIEWER))
        f = _add_file(db_session, owner=regular_user, workspace_id=shared.id)
        db_session.commit()

        g = create_grant(
            db_session,
            workspace_id=shared.id,
            resource_type="file",
            resource_id=f.id,
            grantee_user_id=member.id,
            permission="view",
            created_by_user_id=regular_user.id,
        )
        db_session.commit()
        assert g.id is not None
        assert g.grantee_user_id == member.id


class TestRbacOperationMatrix:
    def test_delete_requires_manage_not_write(self, client, db_session, regular_user, tmp_path):
        _enable_shared_and_rbac(db_session)
        member = _create_user(db_session, "delete_write_only")
        shared = create_shared_workspace(db_session, name="删除矩阵库", owner=regular_user)
        set_member_role(db_session, shared.id, member.id, "viewer")
        folder = Folder(name="del", workspace_id=shared.id, user_id=regular_user.id, sort_order=0)
        db_session.add(folder)
        db_session.flush()
        blob = tmp_path / "owned.bin"
        blob.write_bytes(b"x")
        f = FileModel(
            user_id=member.id,
            workspace_id=shared.id,
            folder_id=folder.id,
            filename="owned.bin",
            original_name="owned.bin",
            file_path=str(blob),
            file_size=1,
            mime_type="application/octet-stream",
            md5_hash="e" * 32,
            has_md=False,
        )
        db_session.add(f)
        _add_acl(
            db_session,
            workspace_id=shared.id,
            folder_id=folder.id,
            user_id=member.id,
            permission=PERM_WRITE,
        )
        db_session.commit()

        token = create_access_token(member.id, member.password_rev)
        r = client.delete(
            f"/api/files/{f.id}",
            headers={"Authorization": f"Bearer {token}"},
            params={"workspace_id": shared.id},
        )
        assert r.status_code == 403, r.text

    def test_delete_allowed_with_manage(self, client, db_session, regular_user, tmp_path):
        _enable_shared_and_rbac(db_session)
        member = _create_user(db_session, "delete_manage")
        shared = create_shared_workspace(db_session, name="删除 manage 库", owner=regular_user)
        set_member_role(db_session, shared.id, member.id, "viewer")
        folder = Folder(name="delm", workspace_id=shared.id, user_id=regular_user.id, sort_order=0)
        db_session.add(folder)
        db_session.flush()
        blob = tmp_path / "m.bin"
        blob.write_bytes(b"x")
        f = FileModel(
            user_id=member.id,
            workspace_id=shared.id,
            folder_id=folder.id,
            filename="m.bin",
            original_name="m.bin",
            file_path=str(blob),
            file_size=1,
            mime_type="application/octet-stream",
            md5_hash="f" * 32,
            has_md=False,
        )
        db_session.add(f)
        _add_acl(
            db_session,
            workspace_id=shared.id,
            folder_id=folder.id,
            user_id=member.id,
            permission=PERM_MANAGE,
        )
        db_session.commit()

        token = create_access_token(member.id, member.password_rev)
        r = client.delete(
            f"/api/files/{f.id}",
            headers={"Authorization": f"Bearer {token}"},
            params={"workspace_id": shared.id},
        )
        assert r.status_code == 200, r.text

    def test_delete_file_requires_manage_on_parent_folder(
        self, client, db_session, regular_user, tmp_path,
    ):
        """T-27k：删除文件须对直接父目录具备 manage（write 不足；含他人文件）。"""
        _enable_shared_and_rbac(db_session)
        member = _create_user(db_session, "delete_parent_manage")
        shared = create_shared_workspace(db_session, name="父目录 manage 删除库", owner=regular_user)
        set_member_role(db_session, shared.id, member.id, "viewer")
        folder = Folder(name="parent", workspace_id=shared.id, user_id=regular_user.id, sort_order=0)
        db_session.add(folder)
        db_session.flush()
        blob = tmp_path / "owner.bin"
        blob.write_bytes(b"x")
        owned_by_owner = FileModel(
            user_id=regular_user.id,
            workspace_id=shared.id,
            folder_id=folder.id,
            filename="owner.bin",
            original_name="owner.bin",
            file_path=str(blob),
            file_size=1,
            mime_type="application/octet-stream",
            md5_hash="c" * 32,
            has_md=False,
        )
        db_session.add(owned_by_owner)
        _add_acl(
            db_session,
            workspace_id=shared.id,
            folder_id=folder.id,
            user_id=member.id,
            permission=PERM_WRITE,
        )
        db_session.commit()

        token = create_access_token(member.id, member.password_rev)
        r = client.delete(
            f"/api/files/{owned_by_owner.id}",
            headers={"Authorization": f"Bearer {token}"},
            params={"workspace_id": shared.id},
        )
        assert r.status_code == 403, r.text
