# Copyright (c) 2026 徐泽宇
"""059 P3 T-21：文件列表 can_write / can_manage 与 upload_allowed。"""

from __future__ import annotations

from models.enterprise_rbac import PERM_MANAGE, PERM_READ, PERM_WRITE
from models.file import File as FileModel
from models.folder import Folder
from services.auth_service import create_access_token
from services.workspace_service import create_shared_workspace, set_member_role
from tests.conftest import _create_user
from tests.test_acl_rbac_p1 import _add_acl, _enable_shared_and_rbac


class TestFileListCapabilities:
    def test_write_only_file_has_can_write_not_manage(self, client, db_session, regular_user, tmp_path):
        _enable_shared_and_rbac(db_session)
        member = _create_user(db_session, "cap_write_only")
        shared = create_shared_workspace(db_session, name="能力写库", owner=regular_user)
        set_member_role(db_session, shared.id, member.id, "viewer")
        folder = Folder(name="w", workspace_id=shared.id, user_id=regular_user.id, sort_order=0)
        db_session.add(folder)
        db_session.flush()
        blob = tmp_path / "w.bin"
        blob.write_bytes(b"x")
        f = FileModel(
            user_id=member.id,
            workspace_id=shared.id,
            folder_id=folder.id,
            filename="w.bin",
            original_name="w.bin",
            file_path=str(blob),
            file_size=1,
            mime_type="application/octet-stream",
            md5_hash="a" * 32,
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
        r = client.get(
            "/api/files",
            headers={"Authorization": f"Bearer {token}"},
            params={"workspace_id": shared.id},
        )
        assert r.status_code == 200, r.text
        items = r.json()["items"]
        assert len(items) == 1
        assert items[0]["can_write"] is True
        assert items[0]["can_manage"] is False

    def test_manage_file_has_both_capabilities(self, client, db_session, regular_user, tmp_path):
        _enable_shared_and_rbac(db_session)
        member = _create_user(db_session, "cap_manage")
        shared = create_shared_workspace(db_session, name="能力管库", owner=regular_user)
        set_member_role(db_session, shared.id, member.id, "viewer")
        folder = Folder(name="m", workspace_id=shared.id, user_id=regular_user.id, sort_order=0)
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
            md5_hash="b" * 32,
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
        r = client.get(
            "/api/files",
            headers={"Authorization": f"Bearer {token}"},
            params={"workspace_id": shared.id},
        )
        assert r.status_code == 200, r.text
        item = r.json()["items"][0]
        assert item["can_write"] is True
        assert item["can_manage"] is True

    def test_read_only_file_has_no_write_or_manage(self, client, db_session, regular_user, tmp_path):
        _enable_shared_and_rbac(db_session)
        member = _create_user(db_session, "cap_read")
        shared = create_shared_workspace(db_session, name="能力读库", owner=regular_user)
        set_member_role(db_session, shared.id, member.id, "viewer")
        folder = Folder(name="r", workspace_id=shared.id, user_id=regular_user.id, sort_order=0)
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
            md5_hash="c" * 32,
            has_md=False,
        )
        db_session.add(f)
        _add_acl(
            db_session,
            workspace_id=shared.id,
            folder_id=folder.id,
            user_id=member.id,
            permission=PERM_READ,
        )
        db_session.commit()

        token = create_access_token(member.id, member.password_rev)
        r = client.get(
            "/api/files",
            headers={"Authorization": f"Bearer {token}"},
            params={"workspace_id": shared.id},
        )
        assert r.status_code == 200, r.text
        item = r.json()["items"][0]
        assert item["can_write"] is False
        assert item["can_manage"] is False


class TestGetFileDetailCapabilities:
    def test_get_file_detail_returns_write_not_manage(self, client, db_session, regular_user, tmp_path):
        _enable_shared_and_rbac(db_session)
        member = _create_user(db_session, "detail_write_only")
        shared = create_shared_workspace(db_session, name="详情写库", owner=regular_user)
        set_member_role(db_session, shared.id, member.id, "viewer")
        folder = Folder(name="d", workspace_id=shared.id, user_id=regular_user.id, sort_order=0)
        db_session.add(folder)
        db_session.flush()
        blob = tmp_path / "d.bin"
        blob.write_bytes(b"x")
        f = FileModel(
            user_id=member.id,
            workspace_id=shared.id,
            folder_id=folder.id,
            filename="d.bin",
            original_name="d.bin",
            file_path=str(blob),
            file_size=1,
            mime_type="application/octet-stream",
            md5_hash="d" * 32,
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
        r = client.get(
            f"/api/files/{f.id}",
            headers={"Authorization": f"Bearer {token}"},
            params={"workspace_id": shared.id},
        )
        assert r.status_code == 200, r.text
        body = r.json()
        assert body["can_write"] is True
        assert body["can_manage"] is False


class TestUploadAllowedFlag:
    def test_upload_allowed_false_without_write(self, client, db_session, regular_user):
        _enable_shared_and_rbac(db_session)
        member = _create_user(db_session, "upload_denied")
        shared = create_shared_workspace(db_session, name="上传拒库", owner=regular_user)
        set_member_role(db_session, shared.id, member.id, "viewer")
        _add_acl(
            db_session,
            workspace_id=shared.id,
            folder_id=None,
            user_id=member.id,
            permission=PERM_READ,
        )
        db_session.commit()

        token = create_access_token(member.id, member.password_rev)
        r = client.get(
            "/api/folders/direct-file-counts",
            headers={"Authorization": f"Bearer {token}"},
            params={"workspace_id": shared.id},
        )
        assert r.status_code == 200, r.text
        assert r.json()["upload_allowed"] is False

    def test_upload_allowed_true_with_root_write(self, client, db_session, regular_user):
        _enable_shared_and_rbac(db_session)
        member = _create_user(db_session, "upload_ok")
        shared = create_shared_workspace(db_session, name="上传可库", owner=regular_user)
        set_member_role(db_session, shared.id, member.id, "viewer")
        _add_acl(
            db_session,
            workspace_id=shared.id,
            folder_id=None,
            user_id=member.id,
            permission=PERM_WRITE,
        )
        db_session.commit()

        token = create_access_token(member.id, member.password_rev)
        r = client.get(
            "/api/folders/direct-file-counts",
            headers={"Authorization": f"Bearer {token}"},
            params={"workspace_id": shared.id},
        )
        assert r.status_code == 200, r.text
        assert r.json()["upload_allowed"] is True

    def test_admin_zero_acl_upload_allowed(self, client, db_session, regular_user, admin_user):
        _enable_shared_and_rbac(db_session)
        shared = create_shared_workspace(db_session, name="admin上传库", owner=regular_user)
        db_session.commit()

        token = create_access_token(admin_user.id, admin_user.password_rev)
        r = client.get(
            "/api/folders/direct-file-counts",
            headers={"Authorization": f"Bearer {token}"},
            params={"workspace_id": shared.id},
        )
        assert r.status_code == 200, r.text
        body = r.json()
        assert body["zero_acl_member"] is False
        assert body["upload_allowed"] is True
