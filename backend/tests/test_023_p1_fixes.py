# Copyright (c) 2026 徐泽宇
"""023 P1 修复项：限速、注册原子化、external ACL、分享门控、skill License、共享元数据、settings 最小化。

Authors:
    徐泽宇

Copyright:
    © 2026 徐泽宇
"""

from __future__ import annotations

import hashlib
from io import BytesIO

import pytest
from fastapi import status, UploadFile

from models.system_setting import SystemSetting
from routers.auth import reset_auth_rate_limit_for_tests
from services.auth_service import create_access_token
from services.file_service import save_upload
from services.share_service import create_share_link
from services.system_setting_service import (
    KEY_KB_SEARCH_HYBRID_ENABLED,
    KEY_SHARED_WORKSPACES_ENABLED,
    update_settings,
)
from services.workspace_service import create_shared_workspace, set_member_role
from tests.conftest import _create_api_key, _create_user


@pytest.fixture(autouse=True)
def _reset_auth_rate_limits():
    reset_auth_rate_limit_for_tests()
    yield
    reset_auth_rate_limit_for_tests()


class TestAuthRateLimit:
    def test_login_rate_limit(self, client, regular_user):
        for _ in range(5):
            r = client.post(
                "/api/auth/login",
                json={"username": "wrong", "password": "wrong"},
            )
            assert r.status_code in (401, 403)
        r6 = client.post(
            "/api/auth/login",
            json={"username": "wrong", "password": "wrong"},
        )
        assert r6.status_code == status.HTTP_429_TOO_MANY_REQUESTS

    def test_register_rate_limit(self, client):
        for i in range(5):
            r = client.post(
                "/api/auth/register",
                json={"username": f"rate_reg_{i}", "password": "secret123"},
            )
            assert r.status_code in (200, 400)
        r6 = client.post(
            "/api/auth/register",
            json={"username": "rate_reg_6", "password": "secret123"},
        )
        assert r6.status_code == status.HTTP_429_TOO_MANY_REQUESTS


class TestRegisterFirstUserAtomic:
    def test_second_register_not_admin(self, client, db_session):
        r1 = client.post(
            "/api/auth/register",
            json={"username": "first_admin_user", "password": "secret123"},
        )
        assert r1.status_code == 200
        reset_auth_rate_limit_for_tests()

        r2 = client.post(
            "/api/auth/register",
            json={"username": "second_regular", "password": "secret123"},
        )
        assert r2.status_code == 200
        token = r2.json()["access_token"]
        me = client.get("/api/auth/me", headers={"Authorization": f"Bearer {token}"})
        assert me.status_code == 200
        assert me.json()["is_admin"] is False


def _write_owner_file(db_session, user_a, *, md5: str | None = None):
    content = b"share-gate-p1-bytes-unique"
    digest = md5 or hashlib.md5(content).hexdigest()
    uf = UploadFile(filename="doc.txt", file=BytesIO(content))
    fr = save_upload(uf, user_a.id, content)
    fr.md5_hash = digest
    db_session.add(fr)
    db_session.commit()
    db_session.refresh(fr)
    return content, digest, fr


class TestShareGateP1:
    def test_share_token_rejects_empty_file_md5(self, client, db_session):
        user_a = _create_user(db_session, "gate_empty_md5")
        key_a = _create_api_key(db_session, user_a)
        _content, md5, fr = _write_owner_file(db_session, user_a, md5="")
        share = create_share_link(db_session, fr.id, user_a.id)

        resp = client.post(
            "/api/external/md-content",
            headers={
                "Authorization": f"Bearer {key_a._plaintext}",
                "X-FileX-Share-Token": share.token,
            },
            json={"md5_hash": "a" * 32, "content": "# x\n"},
        )
        assert resp.status_code == status.HTTP_400_BAD_REQUEST
        assert "MD5" in resp.json().get("detail", "")

    def test_share_token_requires_password(self, client, db_session):
        user_a = _create_user(db_session, "gate_pwd_owner")
        key_a = _create_api_key(db_session, user_a)
        content, md5, fr = _write_owner_file(db_session, user_a)
        share = create_share_link(db_session, fr.id, user_a.id, password="secret99")

        resp = client.post(
            "/api/external/files",
            headers={
                "Authorization": f"Bearer {key_a._plaintext}",
                "X-FileX-Share-Token": share.token,
            },
            files={"file": ("doc.txt", content, "text/plain")},
        )
        assert resp.status_code == status.HTTP_401_UNAUTHORIZED

        ok = client.post(
            "/api/external/files",
            headers={
                "Authorization": f"Bearer {key_a._plaintext}",
                "X-FileX-Share-Token": share.token,
                "X-FileX-Share-Password": "secret99",
            },
            files={"file": ("doc.txt", content, "text/plain")},
        )
        assert ok.status_code == 200


class TestExternalAclP1:
    def test_curator_can_tag_shared_file_not_owned(self, client, db_session, tmp_path):
        owner = _create_user(db_session, "ext_acl_owner")
        curator = _create_user(db_session, "ext_acl_curator")
        key_curator = _create_api_key(db_session, curator)
        shared = create_shared_workspace(db_session, name="ext ACL 库", owner=owner)
        set_member_role(db_session, shared.id, curator.id, "curator")
        blob = tmp_path / "shared-doc.txt"
        content_bytes = b"shared-acl-bytes"
        blob.write_bytes(content_bytes)
        from models.file import File as FileModel

        fr = FileModel(
            filename="shared-doc.txt",
            original_name="shared-doc.txt",
            file_path=str(blob),
            file_size=len(content_bytes),
            mime_type="text/plain",
            user_id=owner.id,
            workspace_id=shared.id,
            md5_hash=hashlib.md5(content_bytes).hexdigest(),
        )
        db_session.add(fr)
        db_session.commit()
        db_session.refresh(fr)

        resp = client.put(
            f"/api/external/files/{fr.id}/tags",
            headers={"Authorization": f"Bearer {key_curator._plaintext}"},
            params={"workspace_id": shared.id},
            json={"tags": ["from-curator"]},
        )
        assert resp.status_code == 200
        assert "from-curator" in resp.json()

    def test_viewer_cannot_tag_shared_file(self, client, db_session, tmp_path):
        owner = _create_user(db_session, "ext_acl_owner2")
        viewer = _create_user(db_session, "ext_acl_viewer")
        key_viewer = _create_api_key(db_session, viewer)
        shared = create_shared_workspace(db_session, name="ext ACL 只读", owner=owner)
        set_member_role(db_session, shared.id, viewer.id, "viewer")
        blob = tmp_path / "v.txt"
        blob.write_bytes(b"v-bytes")
        from models.file import File as FileModel

        fr = FileModel(
            filename="v.txt",
            original_name="v.txt",
            file_path=str(blob),
            file_size=6,
            mime_type="text/plain",
            user_id=owner.id,
            workspace_id=shared.id,
        )
        db_session.add(fr)
        db_session.commit()

        resp = client.put(
            f"/api/external/files/{fr.id}/tags",
            headers={"Authorization": f"Bearer {key_viewer._plaintext}"},
            params={"workspace_id": shared.id},
            json={"tags": ["blocked"]},
        )
        assert resp.status_code == status.HTTP_403_FORBIDDEN


class TestSkillZipLicense:
    def test_skill_update_blocked_when_license_invalid(
        self, client, db_session, monkeypatch, seeded_skill_db,
    ):
        from datetime import datetime, timedelta

        from services.license_service import KEY_LICENSE_TRIAL_STARTED_AT, LICENSE_TRIAL_DAYS
        from utils.timezone import BEIJING_TZ

        started = datetime(2020, 1, 1, tzinfo=BEIJING_TZ)
        db_session.add(
            SystemSetting(setting_key=KEY_LICENSE_TRIAL_STARTED_AT, value=started.isoformat())
        )
        db_session.commit()
        after = started + timedelta(days=LICENSE_TRIAL_DAYS + 1)
        monkeypatch.setattr("services.license_service.beijing_now", lambda: after)

        from services import license_cache_service as lc

        lc.invalidate_license_cache()

        r = client.get("/filex-skill-update")
        assert r.status_code == status.HTTP_403_FORBIDDEN
        assert r.json().get("code") in ("license_expired", "license_invalid")


class TestSharedMetadataWhenDisabled:
    def test_get_shared_workspace_forbidden_when_disabled(self, client, db_session, regular_user):
        update_settings(db_session, {KEY_SHARED_WORKSPACES_ENABLED: "true"})
        shared = create_shared_workspace(db_session, name="meta-off", owner=regular_user)
        db_session.commit()
        update_settings(db_session, {KEY_SHARED_WORKSPACES_ENABLED: "false"})
        h = {"Authorization": f"Bearer {create_access_token(regular_user.id, regular_user.password_rev)}"}
        r = client.get(f"/api/workspaces/{shared.id}", headers=h)
        assert r.status_code == status.HTTP_403_FORBIDDEN

    def test_list_members_forbidden_when_disabled(self, client, db_session, regular_user):
        update_settings(db_session, {KEY_SHARED_WORKSPACES_ENABLED: "true"})
        shared = create_shared_workspace(db_session, name="members-off", owner=regular_user)
        db_session.commit()
        update_settings(db_session, {KEY_SHARED_WORKSPACES_ENABLED: "false"})
        h = {"Authorization": f"Bearer {create_access_token(regular_user.id, regular_user.password_rev)}"}
        r = client.get(f"/api/workspaces/{shared.id}/members", headers=h)
        assert r.status_code == status.HTTP_403_FORBIDDEN


class TestClientSettingsMinimized:
    def test_clipboard_settings_omit_internal_kb_tuning(self, client, jwt_token, db_session):
        update_settings(
            db_session,
            {KEY_KB_SEARCH_HYBRID_ENABLED: "true"},
        )
        r = client.get("/api/settings/clipboard", headers={"Authorization": f"Bearer {jwt_token}"})
        assert r.status_code == 200
        body = r.json()
        assert "kb_search_hybrid_enabled" not in body
        assert "kb_index_max_attempts" not in body
        assert "kb_fts_config" not in body
        assert "kb_retrieval_eval_enabled" not in body
        assert "clipboard_prefix" in body
        assert "max_upload_size_mb" in body
