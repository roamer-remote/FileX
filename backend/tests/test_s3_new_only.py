# Copyright (c) 2026 徐泽宇
"""059 P3 T-26：S3 new_only 行为与生产就绪校验。"""

from __future__ import annotations

from models.enterprise_rbac import SUBJECT_USER, FolderAcl
from models.file import File as FileModel
from models.folder import Folder
from models.resource_grant import ResourceGrant
from models.workspace import WorkspaceMember
from services.acl_service import LegacyGrantDeprecatedError, accessible_file_ids, create_grant
from services.folder_acl_admin_service import put_single_folder_acl
from services.rbac_reverse_to_legacy_service import reverse_workspace_to_legacy
from services.rbac_s3_validate_service import detect_rbac_phase, validate_s3_readiness
from services.rbac_migration_service import migrate_workspace_roles_for_workspace
from services.system_setting_service import (
    KEY_ENTERPRISE_RBAC_ENABLED,
    KEY_ENTERPRISE_RBAC_WRITE_MODE,
    KEY_SHARED_WORKSPACES_ENABLED,
    update_settings,
)
from services.workspace_member_roles_service import set_workspace_member_roles
from services.workspace_service import create_shared_workspace, set_member_role
from tests.conftest import _create_user


def _enable_s3(db_session) -> None:
    update_settings(
        db_session,
        {
            KEY_SHARED_WORKSPACES_ENABLED: "true",
            KEY_ENTERPRISE_RBAC_ENABLED: "true",
            KEY_ENTERPRISE_RBAC_WRITE_MODE: "new_only",
        },
    )


def _enable_s2(db_session) -> None:
    update_settings(
        db_session,
        {
            KEY_SHARED_WORKSPACES_ENABLED: "true",
            KEY_ENTERPRISE_RBAC_ENABLED: "true",
            KEY_ENTERPRISE_RBAC_WRITE_MODE: "dual",
        },
    )


class TestS3NewOnlyWrite:
    def test_s3_legacy_mappable_acl_does_not_mirror_resource_grant(
        self, db_session, regular_user
    ):
        """S3：user+folder+read 写入 folder_acl 但不产生 resource_grant。"""
        grantee = _create_user(db_session, "s3_grantee")
        shared = create_shared_workspace(db_session, name="S3不写旧表", owner=regular_user)
        set_member_role(db_session, shared.id, grantee.id, "viewer")
        folder = Folder(name="d", workspace_id=shared.id, user_id=regular_user.id, sort_order=0)
        db_session.add(folder)
        db_session.flush()
        db_session.commit()

        _enable_s3(db_session)
        grants_before = db_session.query(ResourceGrant).filter(
            ResourceGrant.workspace_id == shared.id
        ).count()

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
        grants_after = db_session.query(ResourceGrant).filter(
            ResourceGrant.workspace_id == shared.id
        ).count()
        assert grants_after == grants_before
        assert (
            db_session.query(FolderAcl)
            .filter(
                FolderAcl.workspace_id == shared.id,
                FolderAcl.folder_id == folder.id,
                FolderAcl.subject_id == grantee.id,
            )
            .count()
            == 1
        )

    def test_s3_workspace_user_roles_no_rollback_warning(self, db_session, regular_user):
        member = _create_user(db_session, "s3_wur")
        shared = create_shared_workspace(db_session, name="S3角色", owner=regular_user)
        set_member_role(db_session, shared.id, member.id, "viewer")
        from services.enterprise_rbac_seed import get_enterprise_role_by_slug

        viewer_role = get_enterprise_role_by_slug(db_session, "viewer")
        db_session.commit()

        _enable_s3(db_session)
        result = set_workspace_member_roles(
            db_session,
            workspace=shared,
            user_id=member.id,
            role_ids=[viewer_role.id],
        )
        assert result["rollback_warning"] is False

    def test_s3_create_grant_still_rejected(self, db_session, regular_user):
        _enable_s3(db_session)
        shared = create_shared_workspace(db_session, name="S3拒绝grant", owner=regular_user)
        member = _create_user(db_session, "s3_target")
        set_member_role(db_session, shared.id, member.id, "viewer")
        f = FileModel(
            user_id=regular_user.id,
            workspace_id=shared.id,
            filename="a.txt",
            original_name="a.txt",
            file_path="/tmp/a.txt",
            file_size=1,
            mime_type="text/plain",
            md5_hash="a" * 32,
            has_md=False,
        )
        db_session.add(f)
        db_session.commit()

        import pytest

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


class TestS3Validate:
    def test_detect_phase_s3(self, db_session):
        _enable_s3(db_session)
        assert detect_rbac_phase(db_session) == "S3"

    def test_validate_passes_after_workspace_role_migration(self, db_session, regular_user):
        user = _create_user(db_session, "s3_val_member")
        shared = create_shared_workspace(db_session, name="S3校验库", owner=regular_user)
        set_member_role(db_session, shared.id, user.id, "contributor")
        db_session.commit()

        _enable_s2(db_session)
        migrate_workspace_roles_for_workspace(
            db_session, shared, actor_user_id=regular_user.id
        )
        db_session.commit()

        report = validate_s3_readiness(db_session, workspace_id=shared.id)
        assert report["ready_for_new_only"] is True
        assert report["summary"]["members_without_wur"] == 0

    def test_validate_blocks_members_without_wur(self, db_session, regular_user):
        _create_user(db_session, "s3_nowur")
        shared = create_shared_workspace(db_session, name="缺WUR库", owner=regular_user)
        orphan = _create_user(db_session, "s3_orphan")
        set_member_role(db_session, shared.id, orphan.id, "viewer")
        db_session.commit()

        _enable_s2(db_session)
        report = validate_s3_readiness(db_session, workspace_id=shared.id)
        assert report["ready_for_new_only"] is False
        assert report["summary"]["members_without_wur"] >= 1


class TestS3ReverseToLegacy:
    def test_reverse_syncs_legacy_mappable_acl_to_grants(
        self, db_session, regular_user, tmp_path
    ):
        grantee = _create_user(db_session, "s3_rev")
        shared = create_shared_workspace(db_session, name="反向库", owner=regular_user)
        set_member_role(db_session, shared.id, grantee.id, "viewer")
        folder = Folder(name="r", workspace_id=shared.id, user_id=regular_user.id, sort_order=0)
        db_session.add(folder)
        db_session.flush()
        blob = tmp_path / "r.bin"
        blob.write_bytes(b"x")
        secret = FileModel(
            user_id=regular_user.id,
            workspace_id=shared.id,
            folder_id=folder.id,
            filename="r.bin",
            original_name="r.bin",
            file_path=str(blob),
            file_size=1,
            mime_type="application/octet-stream",
            md5_hash="r" * 32,
            has_md=False,
        )
        db_session.add(secret)
        db_session.commit()

        _enable_s3(db_session)
        migrate_workspace_roles_for_workspace(
            db_session, shared, actor_user_id=regular_user.id
        )
        put_single_folder_acl(
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

        report = reverse_workspace_to_legacy(
            db_session, shared, actor_user_id=regular_user.id
        )
        db_session.commit()

        assert report["grants_mirrored"] >= 1
        member = (
            db_session.query(WorkspaceMember)
            .filter(
                WorkspaceMember.workspace_id == shared.id,
                WorkspaceMember.user_id == grantee.id,
            )
            .one()
        )
        assert member.role == "viewer"

        update_settings(db_session, {KEY_ENTERPRISE_RBAC_ENABLED: "false"})
        db_session.commit()
        assert secret.id in accessible_file_ids(db_session, grantee, shared.id)
