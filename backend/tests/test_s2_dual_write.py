# Copyright (c) 2026 徐泽宇
"""059 P3 T-25/T-27c：S2 legacy-mappable 双写与关开关回滚。"""

from __future__ import annotations

from models.enterprise_rbac import SUBJECT_USER, FolderAcl
from models.file import File as FileModel
from models.folder import Folder
from models.resource_grant import PERM_VIEW, RESOURCE_FOLDER, ResourceGrant
from services.acl_service import accessible_file_ids
from services.enterprise_rbac_seed import get_enterprise_role_by_slug
from services.folder_acl_admin_service import put_single_folder_acl
from services.rbac_rollback_service import generate_s2_rollback_report
from services.system_setting_service import (
    KEY_ENTERPRISE_RBAC_ENABLED,
    KEY_ENTERPRISE_RBAC_WRITE_MODE,
    KEY_SHARED_WORKSPACES_ENABLED,
    update_settings,
)
from services.workspace_member_roles_service import set_workspace_member_roles
from services.workspace_service import create_shared_workspace, set_member_role
from tests.conftest import _create_user


def _enable_s2_dual(db_session) -> None:
    update_settings(
        db_session,
        {
            KEY_SHARED_WORKSPACES_ENABLED: "true",
            KEY_ENTERPRISE_RBAC_ENABLED: "true",
            KEY_ENTERPRISE_RBAC_WRITE_MODE: "dual",
        },
    )


class TestS2DualWrite:
    def test_s2_rollback_lossless_for_legacy_mappable_acl_only(
        self, db_session, regular_user, tmp_path
    ):
        """T-27c：legacy-mappable 双写后关开关，S1 以 resource_grants 恢复可读性。"""
        grantee = _create_user(db_session, "s2_grantee")
        shared = create_shared_workspace(db_session, name="S2双写库", owner=regular_user)
        set_member_role(db_session, shared.id, grantee.id, "viewer")

        folder = Folder(name="docs", workspace_id=shared.id, user_id=regular_user.id, sort_order=0)
        db_session.add(folder)
        db_session.flush()
        blob = tmp_path / "secret.bin"
        blob.write_bytes(b"x")
        secret = FileModel(
            user_id=regular_user.id,
            workspace_id=shared.id,
            folder_id=folder.id,
            filename="secret.bin",
            original_name="secret.bin",
            file_path=str(blob),
            file_size=1,
            mime_type="application/octet-stream",
            md5_hash="s" * 32,
            has_md=False,
        )
        db_session.add(secret)
        db_session.commit()

        _enable_s2_dual(db_session)
        assert accessible_file_ids(db_session, grantee, shared.id) == set()

        summary = put_single_folder_acl(
            db_session,
            workspace_id=shared.id,
            folder_id=folder.id,
            entries=[
                {
                    "subject_type": SUBJECT_USER,
                    "subject_id": grantee.id,
                    "permission": "read",
                }
            ],
            admin_user_id=regular_user.id,
        )
        db_session.commit()

        assert summary["rollback_warning"] is False
        grant = (
            db_session.query(ResourceGrant)
            .filter(
                ResourceGrant.workspace_id == shared.id,
                ResourceGrant.resource_type == RESOURCE_FOLDER,
                ResourceGrant.resource_id == folder.id,
                ResourceGrant.grantee_user_id == grantee.id,
            )
            .one()
        )
        assert grant.permission == PERM_VIEW
        assert secret.id in accessible_file_ids(db_session, grantee, shared.id)

        db_session.query(FolderAcl).filter(FolderAcl.workspace_id == shared.id).delete(
            synchronize_session=False
        )
        db_session.commit()
        assert accessible_file_ids(db_session, grantee, shared.id) == set()

        update_settings(db_session, {KEY_ENTERPRISE_RBAC_ENABLED: "false"})
        db_session.commit()

        s1_ids = accessible_file_ids(db_session, grantee, shared.id)
        assert secret.id in s1_ids

    def test_s2_non_mappable_root_acl_sets_rollback_warning_and_report(
        self, db_session, regular_user
    ):
        grantee = _create_user(db_session, "s2_root_user")
        shared = create_shared_workspace(db_session, name="S2根ACL库", owner=regular_user)
        set_member_role(db_session, shared.id, grantee.id, "viewer")
        db_session.commit()

        grants_before = (
            db_session.query(ResourceGrant)
            .filter(ResourceGrant.workspace_id == shared.id)
            .count()
        )

        _enable_s2_dual(db_session)
        summary = put_single_folder_acl(
            db_session,
            workspace_id=shared.id,
            folder_id=None,
            entries=[
                {
                    "subject_type": SUBJECT_USER,
                    "subject_id": grantee.id,
                    "permission": "manage",
                }
            ],
            admin_user_id=regular_user.id,
        )
        db_session.commit()

        assert summary["rollback_warning"] is True
        grants_after = (
            db_session.query(ResourceGrant)
            .filter(ResourceGrant.workspace_id == shared.id)
            .count()
        )
        assert grants_after == grants_before

        report = generate_s2_rollback_report(db_session, workspace_id=shared.id)
        assert report["warning_count"] >= 1
        root_entries = [
            e
            for e in report["non_mappable_entries"]
            if e.get("kind") == "folder_acl" and e.get("folder_id") is None
        ]
        assert len(root_entries) == 1
        assert root_entries[0]["permission"] == "manage"

    def test_s2_workspace_user_roles_change_sets_rollback_warning(
        self, db_session, regular_user
    ):
        member = _create_user(db_session, "s2_wur_member")
        shared = create_shared_workspace(db_session, name="S2角色库", owner=regular_user)
        set_member_role(db_session, shared.id, member.id, "viewer")
        viewer_role = get_enterprise_role_by_slug(db_session, "viewer")
        db_session.commit()

        _enable_s2_dual(db_session)
        result = set_workspace_member_roles(
            db_session,
            workspace=shared,
            user_id=member.id,
            role_ids=[viewer_role.id],
        )
        db_session.commit()

        assert result["rollback_warning"] is True
        report = generate_s2_rollback_report(db_session, workspace_id=shared.id)
        wur_entries = [
            e for e in report["non_mappable_entries"] if e.get("kind") == "workspace_user_role"
        ]
        assert len(wur_entries) == 1
        assert wur_entries[0]["role_slug"] == "viewer"
