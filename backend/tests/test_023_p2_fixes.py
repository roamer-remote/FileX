# Copyright (c) 2026 徐泽宇
"""023 P2 修复项：分享 POST/cookie、basename 净化、library report ACL、License Redis 限速、consumer retry。

Authors:
    徐泽宇

Copyright:
    © 2026 徐泽宇
"""

from __future__ import annotations

import hashlib
from io import BytesIO
from unittest.mock import MagicMock

import pytest
from fastapi import status, UploadFile

from messaging.kb_index_consumer import _recover_handler_error
from models.file import File as FileModel
from routers.license import reset_activate_rate_limit_for_tests
from services.auth_service import create_access_token
from services.file_service import sanitize_upload_basename, save_upload
from services.kb_index_service import JOB_QUEUED, JOB_RUNNING, _LeaseToken
from services.share_service import SHARE_VERIFY_COOKIE, create_share_link, share_verify_cookie_value
from services.workspace_service import create_shared_workspace, ensure_personal_workspace, set_member_role
from tests.conftest import _create_user


@pytest.fixture(autouse=True)
def _reset_license_rate_limits():
    reset_activate_rate_limit_for_tests()
    yield
    reset_activate_rate_limit_for_tests()


def _write_file(db_session, user, tmp_path, name="doc.txt", content=b"hello-share"):
    p = tmp_path / name
    p.write_bytes(content)
    fr = FileModel(
        filename=name,
        original_name=name,
        file_path=str(p),
        file_size=len(content),
        mime_type="text/plain",
        user_id=user.id,
        workspace_id=ensure_personal_workspace(db_session, user).id,
        md5_hash=hashlib.md5(content).hexdigest(),
    )
    db_session.add(fr)
    db_session.commit()
    db_session.refresh(fr)
    return fr


class TestShareDownloadP2:
    def test_get_download_rejects_password_query(self, client, db_session, tmp_path):
        user = _create_user(db_session, "share_p2_owner")
        fr = _write_file(db_session, user, tmp_path)
        share = create_share_link(db_session, fr.id, user.id, password="s3cret")
        r = client.get(f"/api/share/{share.token}/download?password=s3cret")
        assert r.status_code == status.HTTP_400_BAD_REQUEST
        assert "URL" in r.json().get("detail", "")

    def test_verify_cookie_then_get_download(self, client, db_session, tmp_path):
        user = _create_user(db_session, "share_p2_cookie")
        fr = _write_file(db_session, user, tmp_path)
        share = create_share_link(db_session, fr.id, user.id, password="cookie99")

        bad = client.get(f"/api/share/{share.token}/download")
        assert bad.status_code == status.HTTP_403_FORBIDDEN

        v = client.post(f"/api/share/{share.token}/verify", json={"password": "cookie99"})
        assert v.status_code == 200
        cookie_val = v.cookies.get(SHARE_VERIFY_COOKIE)
        assert cookie_val == share_verify_cookie_value(share.token)

        ok = client.get(
            f"/api/share/{share.token}/download",
            cookies={SHARE_VERIFY_COOKIE: cookie_val},
        )
        assert ok.status_code == 200

    def test_post_download_with_password_body(self, client, db_session, tmp_path):
        user = _create_user(db_session, "share_p2_post")
        fr = _write_file(db_session, user, tmp_path)
        share = create_share_link(db_session, fr.id, user.id, password="postpwd")

        r = client.post(
            f"/api/share/{share.token}/download",
            json={"password": "postpwd"},
        )
        assert r.status_code == 200


class TestUploadBasenameP2:
    def test_sanitize_strips_path_traversal(self):
        assert sanitize_upload_basename("../../etc/passwd") == "passwd"
        assert sanitize_upload_basename("..\\evil.txt") == "evil.txt"
        assert sanitize_upload_basename("..") == "unknown"

    def test_save_upload_uses_safe_basename(self, db_session, regular_user, tmp_path, monkeypatch):
        monkeypatch.setattr("services.file_service.UPLOAD_DIR", str(tmp_path))
        upload = UploadFile(filename="../../../traversal.txt", file=BytesIO(b"hello"))
        fr = save_upload(upload, regular_user.id, content=b"hello")
        assert fr.original_name == "traversal.txt"
        assert ".." not in fr.filename


class TestLibraryReportAclP2:
    def test_get_report_scoped_to_trigger_user(self, client, db_session, tmp_path):
        owner = _create_user(db_session, "lr_acl_owner")
        viewer = _create_user(db_session, "lr_acl_viewer")
        shared = create_shared_workspace(db_session, name="lr ACL", owner=owner)
        set_member_role(db_session, shared.id, viewer.id, "viewer")

        p = tmp_path / "only-owner.txt"
        p.write_text("x", encoding="utf-8")
        fr = FileModel(
            user_id=owner.id,
            workspace_id=shared.id,
            filename="only-owner.txt",
            original_name="only-owner.txt",
            file_path=str(p),
            file_size=1,
            mime_type="text/plain",
            md5_hash="f" * 32,
            page_kind="source",
        )
        db_session.add(fr)
        db_session.commit()

        h_owner = {"Authorization": f"Bearer {create_access_token(owner.id, owner.password_rev)}"}
        h_viewer = {"Authorization": f"Bearer {create_access_token(viewer.id, viewer.password_rev)}"}

        r_refresh = client.post(
            "/api/knowledge-base/library-report/refresh",
            headers=h_owner,
            params={"workspace_id": shared.id},
        )
        assert r_refresh.status_code == 200

        r_owner = client.get(
            "/api/knowledge-base/library-report",
            headers=h_owner,
            params={"workspace_id": shared.id},
        )
        assert r_owner.status_code == 200
        assert r_owner.json()["status"] == "ready"

        r_viewer = client.get(
            "/api/knowledge-base/library-report",
            headers=h_viewer,
            params={"workspace_id": shared.id},
        )
        assert r_viewer.status_code == status.HTTP_404_NOT_FOUND


class TestLicenseActivateRateLimitP2:
    def test_activate_rate_limit_uses_redis_limiter(self, client, admin_user):
        body = {
            "license_key": "FILEX1.invalid",
            "admin_username": "adminuser",
            "admin_password": "password123",
        }
        for _ in range(5):
            r = client.post("/api/license/activate", json=body)
            assert r.status_code in (400, 401)
        r6 = client.post("/api/license/activate", json=body)
        assert r6.status_code == status.HTTP_429_TOO_MANY_REQUESTS


class TestKbIndexHandlerRetryP2:
    def test_recover_handler_error_requeues_under_max_attempts(self, monkeypatch):
        fake_job = MagicMock()
        fake_job.status = JOB_RUNNING
        fake_job.attempts = 0
        fake_job.id = 42
        fake_job.file_id = 99
        fake_job.worker_id = "test-worker"
        fake_job.lease_generation = 1

        fake_file = MagicMock()
        fake_file.user_id = 7
        fake_db = MagicMock()
        fake_db.query.return_value.filter.return_value.first.side_effect = [fake_job, fake_file, fake_file]

        monkeypatch.setattr("messaging.kb_index_consumer.SessionLocal", lambda: fake_db)
        monkeypatch.setattr("messaging.kb_index_consumer.get_user_effective_dict", lambda *a, **k: {})
        monkeypatch.setattr("messaging.kb_index_consumer.get_kb_index_max_attempts", lambda *a, **k: 3)
        published: list[int] = []
        monkeypatch.setattr(
            "messaging.kb_index_consumer.publish_kb_index_retry",
            lambda jid, connection=None: published.append(jid),
        )
        monkeypatch.setattr("messaging.kb_index_consumer.publish_file_index_notify", lambda *a, **k: None)
        monkeypatch.setattr("messaging.kb_index_consumer.publish_kb_index_dlq", lambda *a, **k: None)

        _recover_handler_error(
            42,
            "boom",
            MagicMock(),
            token=_LeaseToken(worker_id="test-worker", lease_generation=1),
        )

        assert fake_job.status == JOB_QUEUED
        assert fake_job.attempts == 1
        assert published == [42]
        fake_db.commit.assert_called()

    def test_recover_handler_error_falls_back_when_settings_read_fails(self, monkeypatch):
        fake_job = MagicMock()
        fake_job.status = JOB_RUNNING
        fake_job.attempts = 0
        fake_job.id = 43
        fake_job.file_id = 100
        fake_job.worker_id = "test-worker"
        fake_job.lease_generation = 1

        fake_file = MagicMock()
        fake_file.user_id = 7
        fake_db = MagicMock()
        fake_db.query.return_value.filter.return_value.first.side_effect = [fake_job, fake_file, fake_file]

        monkeypatch.setattr("messaging.kb_index_consumer.SessionLocal", lambda: fake_db)
        monkeypatch.setattr(
            "messaging.kb_index_consumer.get_user_effective_dict",
            lambda *a, **k: (_ for _ in ()).throw(RuntimeError("settings unavailable")),
        )
        published: list[int] = []
        monkeypatch.setattr(
            "messaging.kb_index_consumer.publish_kb_index_retry",
            lambda jid, connection=None: published.append(jid),
        )
        monkeypatch.setattr("messaging.kb_index_consumer.publish_file_index_notify", lambda *a, **k: None)
        monkeypatch.setattr("messaging.kb_index_consumer.publish_kb_index_dlq", lambda *a, **k: None)

        _recover_handler_error(
            43,
            "boom",
            MagicMock(),
            token=_LeaseToken(worker_id="test-worker", lease_generation=1),
        )

        assert fake_job.status == JOB_QUEUED
        assert fake_job.attempts == 1
        assert published == [43]
        fake_db.commit.assert_called()
