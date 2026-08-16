# Copyright (c) 2026 徐泽宇
"""059 P3 T-22/T-23：legacy workspace role 与 resource_grants 迁移。"""

from __future__ import annotations

from models.enterprise_rbac import EnterpriseRole, WorkspaceUserRole
from models.file import File as FileModel
from models.folder import Folder
from models.resource_grant import PERM_EDIT, PERM_VIEW, RESOURCE_FILE, RESOURCE_FOLDER, ResourceGrant
from services.acl_service import accessible_file_ids
from services.auth_service import create_access_token
from services.enterprise_rbac_seed import get_enterprise_role_by_slug
from services.rbac_migration_service import (
    count_role_folder_acl,
    count_user_folder_acl,
    count_workspace_user_roles,
    migrate_resource_grants_for_workspace,
    migrate_workspace_roles,
    migrate_workspace_roles_for_workspace,
)
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


def _wur_slugs(db_session, *, workspace_id: int, user_id: int) -> list[str]:
    rows = (
        db_session.query(EnterpriseRole.slug)
        .join(WorkspaceUserRole, WorkspaceUserRole.role_id == EnterpriseRole.id)
        .filter(
            WorkspaceUserRole.workspace_id == workspace_id,
            WorkspaceUserRole.user_id == user_id,
        )
        .order_by(EnterpriseRole.slug)
        .all()
    )
    return [str(r[0]) for r in rows]


class TestMigrateWorkspaceRoles:
    def test_migrate_workspace_roles_does_not_grant_cross_workspace_role_power(
        self, db_session, regular_user
    ):
        """T-27a：W1 admin + W2 viewer 不 cross-grant。"""
        user = _create_user(db_session, "cross_ws_member")
        w1 = create_shared_workspace(db_session, name="迁移库甲", owner=regular_user)
        w2 = create_shared_workspace(db_session, name="迁移库乙", owner=regular_user)
        set_member_role(db_session, w1.id, user.id, "admin")
        set_member_role(db_session, w2.id, user.id, "viewer")
        db_session.commit()

        migrate_workspace_roles(db_session, actor_user_id=regular_user.id, dry_run=False)
        db_session.commit()

        assert _wur_slugs(db_session, workspace_id=w1.id, user_id=user.id) == ["space_admin"]
        assert _wur_slugs(db_session, workspace_id=w2.id, user_id=user.id) == ["viewer"]

    def test_migrate_contributor_viewer_retains_workspace_visibility(
        self, db_session, regular_user, tmp_path
    ):
        """T-27h：contributor/viewer 迁移后仍可见空间内已有文件。"""
        _enable_shared_and_rbac(db_session)
        contributor = _create_user(db_session, "mig_contrib")
        viewer = _create_user(db_session, "mig_viewer")
        shared = create_shared_workspace(db_session, name="可见性迁移库", owner=regular_user)
        set_member_role(db_session, shared.id, contributor.id, "contributor")
        set_member_role(db_session, shared.id, viewer.id, "viewer")

        folder = Folder(name="docs", workspace_id=shared.id, user_id=regular_user.id, sort_order=0)
        db_session.add(folder)
        db_session.flush()
        blob = tmp_path / "doc.bin"
        blob.write_bytes(b"x")
        f = FileModel(
            user_id=regular_user.id,
            workspace_id=shared.id,
            folder_id=folder.id,
            filename="doc.bin",
            original_name="doc.bin",
            file_path=str(blob),
            file_size=1,
            mime_type="application/octet-stream",
            md5_hash="m" * 32,
            has_md=False,
        )
        db_session.add(f)
        db_session.commit()

        migrate_workspace_roles_for_workspace(
            db_session, shared, actor_user_id=regular_user.id
        )
        db_session.commit()

        contrib_ids = accessible_file_ids(db_session, contributor, shared.id)
        viewer_ids = accessible_file_ids(db_session, viewer, shared.id)
        assert f.id in contrib_ids
        assert f.id in viewer_ids

    def test_space_admin_gets_root_and_folder_manage_batch(self, db_session, regular_user):
        shared = create_shared_workspace(db_session, name="admin批量库", owner=regular_user)
        admin_member = _create_user(db_session, "legacy_admin")
        set_member_role(db_session, shared.id, admin_member.id, "admin")
        folder = Folder(name="a", workspace_id=shared.id, user_id=regular_user.id, sort_order=0)
        db_session.add(folder)
        db_session.flush()
        db_session.commit()

        report = migrate_workspace_roles_for_workspace(
            db_session, shared, actor_user_id=regular_user.id
        )
        db_session.commit()

        assert report.role_slugs_batch_applied == ["space_admin"]
        assert report.root_acl_created == 1
        assert report.folder_acl_created == 1
        assert (
            count_role_folder_acl(
                db_session,
                workspace_id=shared.id,
                role_slug="space_admin",
                folder_id=None,
            )
            == 1
        )
        assert (
            count_role_folder_acl(
                db_session,
                workspace_id=shared.id,
                role_slug="space_admin",
                folder_id=folder.id,
            )
            == 1
        )

    def test_migration_is_idempotent(self, db_session, regular_user):
        shared = create_shared_workspace(db_session, name="幂等库", owner=regular_user)
        member = _create_user(db_session, "legacy_viewer")
        set_member_role(db_session, shared.id, member.id, "viewer")
        folder = Folder(name="v", workspace_id=shared.id, user_id=regular_user.id, sort_order=0)
        db_session.add(folder)
        db_session.flush()
        db_session.commit()

        migrate_workspace_roles_for_workspace(
            db_session, shared, actor_user_id=regular_user.id
        )
        db_session.commit()
        first_wur = count_workspace_user_roles(
            db_session, workspace_id=shared.id, user_id=member.id
        )

        report2 = migrate_workspace_roles_for_workspace(
            db_session, shared, actor_user_id=regular_user.id
        )
        db_session.commit()

        assert first_wur == 1
        assert count_workspace_user_roles(
            db_session, workspace_id=shared.id, user_id=member.id
        ) == 1
        assert report2.folder_acl_created == 0
        assert report2.folder_acl_updated >= 1

    def test_dry_run_does_not_persist(self, db_session, regular_user):
        shared = create_shared_workspace(db_session, name="dry库", owner=regular_user)
        member = _create_user(db_session, "dry_viewer")
        set_member_role(db_session, shared.id, member.id, "viewer")
        db_session.commit()

        migrate_workspace_roles(
            db_session,
            workspace_id=shared.id,
            dry_run=True,
            actor_user_id=regular_user.id,
        )

        assert (
            count_workspace_user_roles(db_session, workspace_id=shared.id, user_id=member.id)
            == 0
        )

    def test_contributor_batch_editor_write_acl(self, db_session, regular_user):
        shared = create_shared_workspace(db_session, name="contrib批量库", owner=regular_user)
        member = _create_user(db_session, "legacy_contrib")
        set_member_role(db_session, shared.id, member.id, "contributor")
        folder = Folder(name="c", workspace_id=shared.id, user_id=regular_user.id, sort_order=0)
        db_session.add(folder)
        db_session.flush()
        db_session.commit()

        report = migrate_workspace_roles_for_workspace(
            db_session, shared, actor_user_id=regular_user.id
        )
        db_session.commit()

        assert _wur_slugs(db_session, workspace_id=shared.id, user_id=member.id) == ["editor"]
        assert "editor" in report.role_slugs_batch_applied
        editor = get_enterprise_role_by_slug(db_session, "editor")
        assert (
            count_role_folder_acl(
                db_session,
                workspace_id=shared.id,
                role_slug="editor",
                folder_id=folder.id,
            )
            == 1
        )
        assert editor.id is not None

class TestMigrateResourceGrants:
    def test_folder_grant_expands_to_descendants(self, db_session, regular_user):
        viewer = _create_user(db_session, "grant_folder_viewer")
        shared = create_shared_workspace(db_session, name="grant展开库", owner=regular_user)
        set_member_role(db_session, shared.id, viewer.id, "viewer")
        parent = Folder(name="parent", workspace_id=shared.id, user_id=regular_user.id)
        db_session.add(parent)
        db_session.flush()
        child = Folder(name="child", workspace_id=shared.id, user_id=regular_user.id, parent_id=parent.id)
        db_session.add(child)
        db_session.flush()
        db_session.add(
            ResourceGrant(
                workspace_id=shared.id,
                resource_type=RESOURCE_FOLDER,
                resource_id=parent.id,
                grantee_user_id=viewer.id,
                permission=PERM_VIEW,
                created_by_user_id=regular_user.id,
            )
        )
        db_session.commit()

        report = migrate_resource_grants_for_workspace(
            db_session, shared, actor_user_id=regular_user.id
        )
        db_session.commit()

        assert report.folder_grants_expanded == 1
        assert count_user_folder_acl(
            db_session,
            workspace_id=shared.id,
            user_id=viewer.id,
            folder_id=parent.id,
            permission="read",
        ) == 1
        assert count_user_folder_acl(
            db_session,
            workspace_id=shared.id,
            user_id=viewer.id,
            folder_id=child.id,
            permission="read",
        ) == 1

    def test_file_grant_writes_parent_folder_acl_with_warn(self, db_session, regular_user, tmp_path):
        viewer = _create_user(db_session, "grant_file_viewer")
        shared = create_shared_workspace(db_session, name="file父目录库", owner=regular_user)
        set_member_role(db_session, shared.id, viewer.id, "viewer")
        folder = Folder(name="fparent", workspace_id=shared.id, user_id=regular_user.id)
        db_session.add(folder)
        db_session.flush()
        blob = tmp_path / "g.bin"
        blob.write_bytes(b"x")
        f = FileModel(
            user_id=regular_user.id,
            workspace_id=shared.id,
            folder_id=folder.id,
            filename="g.bin",
            original_name="g.bin",
            file_path=str(blob),
            file_size=1,
            mime_type="application/octet-stream",
            md5_hash="g" * 32,
            has_md=False,
        )
        db_session.add(f)
        db_session.flush()
        db_session.add(
            ResourceGrant(
                workspace_id=shared.id,
                resource_type=RESOURCE_FILE,
                resource_id=f.id,
                grantee_user_id=viewer.id,
                permission=PERM_EDIT,
                created_by_user_id=regular_user.id,
            )
        )
        db_session.commit()

        report = migrate_resource_grants_for_workspace(
            db_session, shared, actor_user_id=regular_user.id
        )
        db_session.commit()

        assert report.file_grants_to_folder == 1
        assert count_user_folder_acl(
            db_session,
            workspace_id=shared.id,
            user_id=viewer.id,
            folder_id=folder.id,
            permission="write",
        ) == 1
        warn_codes = [w["code"] for w in report.warnings]
        assert "file_parent_over_grant" in warn_codes

    def test_uncategorized_file_grant_retained_as_shim(self, db_session, regular_user, tmp_path):
        viewer = _create_user(db_session, "grant_shim_viewer")
        shared = create_shared_workspace(db_session, name="shim库", owner=regular_user)
        set_member_role(db_session, shared.id, viewer.id, "viewer")
        blob = tmp_path / "u.bin"
        blob.write_bytes(b"x")
        f = FileModel(
            user_id=regular_user.id,
            workspace_id=shared.id,
            folder_id=None,
            filename="u.bin",
            original_name="u.bin",
            file_path=str(blob),
            file_size=1,
            mime_type="application/octet-stream",
            md5_hash="u" * 32,
            has_md=False,
        )
        db_session.add(f)
        db_session.flush()
        db_session.add(
            ResourceGrant(
                workspace_id=shared.id,
                resource_type=RESOURCE_FILE,
                resource_id=f.id,
                grantee_user_id=viewer.id,
                permission=PERM_VIEW,
                created_by_user_id=regular_user.id,
            )
        )
        db_session.commit()

        report = migrate_resource_grants_for_workspace(
            db_session, shared, actor_user_id=regular_user.id
        )
        db_session.commit()

        assert report.file_grants_shim_retained == 1
        assert report.folder_acl_created == 0
        assert any(w["code"] == "file_no_folder_shim" for w in report.warnings)
        assert (
            db_session.query(ResourceGrant)
            .filter(ResourceGrant.workspace_id == shared.id, ResourceGrant.resource_id == f.id)
            .count()
            == 1
        )

    def test_orphan_folder_grant_skipped(self, db_session, regular_user):
        viewer = _create_user(db_session, "grant_orphan_viewer")
        shared = create_shared_workspace(db_session, name="孤儿库", owner=regular_user)
        set_member_role(db_session, shared.id, viewer.id, "viewer")
        db_session.add(
            ResourceGrant(
                workspace_id=shared.id,
                resource_type=RESOURCE_FOLDER,
                resource_id=999999,
                grantee_user_id=viewer.id,
                permission=PERM_VIEW,
                created_by_user_id=regular_user.id,
            )
        )
        db_session.commit()

        report = migrate_resource_grants_for_workspace(
            db_session, shared, actor_user_id=regular_user.id
        )

        assert report.orphan_grants_skipped == 1
        assert report.folder_acl_created == 0
        assert any(w["code"] == "orphan_grant" for w in report.warnings)

    def test_migrated_folder_grant_visible_under_rbac(self, db_session, regular_user, tmp_path):
        _enable_shared_and_rbac(db_session)
        viewer = _create_user(db_session, "grant_rbac_viewer")
        shared = create_shared_workspace(db_session, name="RBAC可见库", owner=regular_user)
        set_member_role(db_session, shared.id, viewer.id, "viewer")
        folder = Folder(name="rbac", workspace_id=shared.id, user_id=regular_user.id)
        db_session.add(folder)
        db_session.flush()
        blob = tmp_path / "r.bin"
        blob.write_bytes(b"x")
        f = FileModel(
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
        db_session.add(f)
        db_session.flush()
        db_session.add(
            ResourceGrant(
                workspace_id=shared.id,
                resource_type=RESOURCE_FOLDER,
                resource_id=folder.id,
                grantee_user_id=viewer.id,
                permission=PERM_VIEW,
                created_by_user_id=regular_user.id,
            )
        )
        db_session.commit()

        migrate_resource_grants_for_workspace(
            db_session, shared, actor_user_id=regular_user.id
        )
        db_session.commit()

        visible = accessible_file_ids(db_session, viewer, shared.id)
        assert f.id in visible

