# Copyright (c) 2026 徐泽宇
"""059 P3 T-27：S4 cutover 后移除 legacy resource_grants 与成员 role 写入。"""

from __future__ import annotations

import pytest
from fastapi import HTTPException

from models.enterprise_rbac import SUBJECT_USER
from models.folder import Folder
from models.resource_grant import ResourceGrant
from services.acl_service import LegacyGrantDeprecatedError, create_grant
from services.enterprise_rbac_phase_service import (
    assert_legacy_member_role_write_allowed,
    assert_legacy_resource_grants_api_allowed,
    is_s4_cutover_active,
)
from services.folder_acl_admin_service import put_single_folder_acl
from services.system_setting_service import (
    KEY_ENTERPRISE_RBAC_CUTOVER,
    KEY_ENTERPRISE_RBAC_ENABLED,
    KEY_ENTERPRISE_RBAC_WRITE_MODE,
    KEY_SHARED_WORKSPACES_ENABLED,
    update_settings,
)
from services.workspace_service import create_shared_workspace, set_member_role
from tests.conftest import _create_user


def _enable_s4(db_session) -> None:
    update_settings(
        db_session,
        {
            KEY_SHARED_WORKSPACES_ENABLED: "true",
            KEY_ENTERPRISE_RBAC_ENABLED: "true",
            KEY_ENTERPRISE_RBAC_WRITE_MODE: "new_only",
            KEY_ENTERPRISE_RBAC_CUTOVER: "true",
        },
    )


class TestS4CutoverGuards:
    def test_s4_active_requires_new_only_and_cutover(self, db_session):
        _enable_s4(db_session)
        assert is_s4_cutover_active(db_session) is True

    def test_cutover_rejected_without_new_only(self, db_session):
        update_settings(
            db_session,
            {
                KEY_SHARED_WORKSPACES_ENABLED: "true",
                KEY_ENTERPRISE_RBAC_ENABLED: "true",
                KEY_ENTERPRISE_RBAC_WRITE_MODE: "dual",
            },
        )
        with pytest.raises(ValueError, match="new_only"):
            update_settings(db_session, {KEY_ENTERPRISE_RBAC_CUTOVER: "true"})

    def test_grants_api_returns_410_when_cutover(self, db_session):
        _enable_s4(db_session)
        with pytest.raises(HTTPException) as exc:
            assert_legacy_resource_grants_api_allowed(db_session)
        assert exc.value.status_code == 410

    def test_member_role_write_returns_410_when_cutover(self, db_session):
        _enable_s4(db_session)
        with pytest.raises(HTTPException) as exc:
            assert_legacy_member_role_write_allowed(db_session)
        assert exc.value.status_code == 410

    def test_create_grant_blocked_even_internal_dual_write(self, db_session, regular_user):
        target = _create_user(db_session, "s4_grant_target")
        shared = create_shared_workspace(db_session, name="S4库", owner=regular_user)
        set_member_role(db_session, shared.id, target.id, "viewer")
        folder = Folder(name="d", workspace_id=shared.id, user_id=regular_user.id, sort_order=0)
        db_session.add(folder)
        db_session.flush()
        db_session.commit()

        _enable_s4(db_session)
        with pytest.raises(LegacyGrantDeprecatedError, match="cutover"):
            create_grant(
                db_session,
                workspace_id=shared.id,
                resource_type="folder",
                resource_id=folder.id,
                grantee_user_id=target.id,
                permission="view",
                created_by_user_id=regular_user.id,
                _internal_dual_write=True,
            )

    def test_folder_acl_still_writable_under_cutover(self, db_session, regular_user):
        grantee = _create_user(db_session, "s4_acl")
        shared = create_shared_workspace(db_session, name="S4 ACL库", owner=regular_user)
        set_member_role(db_session, shared.id, grantee.id, "viewer")
        folder = Folder(name="x", workspace_id=shared.id, user_id=regular_user.id, sort_order=0)
        db_session.add(folder)
        db_session.flush()
        db_session.commit()

        _enable_s4(db_session)
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
        assert summary["upserted"] + summary["updated"] >= 1
        assert (
            db_session.query(ResourceGrant)
            .filter(ResourceGrant.workspace_id == shared.id)
            .count()
            == 0
        )


class TestS4CutoverHttp:
    def test_admin_grants_list_410(self, client, db_session, admin_jwt_token, regular_user):
        shared = create_shared_workspace(db_session, name="S4 HTTP", owner=regular_user)
        db_session.commit()
        _enable_s4(db_session)

        r = client.get(
            f"/api/admin/workspaces/{shared.id}/grants",
            headers={"Authorization": f"Bearer {admin_jwt_token}"},
        )
        assert r.status_code == 410

    def test_workspace_member_upsert_legacy_role_410(
        self, client, db_session, admin_jwt_token, regular_user
    ):
        member = _create_user(db_session, "s4_http_member")
        shared = create_shared_workspace(db_session, name="S4成员", owner=regular_user)
        set_member_role(db_session, shared.id, member.id, "viewer")
        db_session.commit()
        _enable_s4(db_session)

        r = client.post(
            f"/api/workspaces/{shared.id}/members",
            json={"user_id": member.id, "role": "contributor"},
            headers={"Authorization": f"Bearer {admin_jwt_token}"},
        )
        assert r.status_code == 410
