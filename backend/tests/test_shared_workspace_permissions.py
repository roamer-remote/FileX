# Copyright (c) 2026 徐泽宇
"""共享空间权限与跨空间检索全案：系统开关开启/关闭两种模式。

Authors:
    徐泽宇

Copyright:
    © 2026 徐泽宇
"""

from __future__ import annotations

from unittest.mock import patch

from services.auth_service import create_access_token
from services.system_setting_service import KEY_SHARED_WORKSPACES_ENABLED, update_settings
from services.workspace_service import create_shared_workspace, ensure_personal_workspace, set_member_role
from tests.conftest import _create_user


def _set_shared_enabled(db_session, enabled: bool) -> None:
    update_settings(db_session, {KEY_SHARED_WORKSPACES_ENABLED: "true" if enabled else "false"})


def _make_shared_with_members(db_session, owner, member_b, *, member_role: str = "viewer"):
    shared = create_shared_workspace(db_session, name="权限测试库", owner=owner)
    set_member_role(db_session, shared.id, member_b.id, member_role)
    db_session.commit()
    return shared


def _add_shared_file(db_session, *, owner, workspace_id: int, tmp_path, name: str = "shared.bin"):
    blob = tmp_path / name
    blob.write_bytes(b"shared-workspace-bytes")
    from models.file import File as FileModel

    f = FileModel(
        filename=name,
        original_name=name,
        file_path=str(blob),
        file_size=blob.stat().st_size,
        mime_type="application/octet-stream",
        user_id=owner.id,
        workspace_id=workspace_id,
        index_status="ready",
        publish_status="published",
    )
    db_session.add(f)
    db_session.commit()
    return f


def _add_kb_chunk(db_session, *, owner, file_id: int, workspace_id: int, text: str):
    from config import OLLAMA_EMBED_DIM
    from models.kb_chunk import KbChunk

    db_session.add(
        KbChunk(
            user_id=owner.id,
            workspace_id=workspace_id,
            file_id=file_id,
            chunk_index=0,
            source="sidecar_md",
            text=text,
            char_start=0,
            char_end=len(text),
            embedding=[0.5] * OLLAMA_EMBED_DIM,
            embedding_model="test-model",
        )
    )
    db_session.commit()


class TestSharedEnabled:
    """共享启用 单元测试。

        Authors:
            徐泽宇

        Copyright:
            © 2026 徐泽宇

        Since:
            2026-05-24
    """
    def test_non_member_cannot_list_shared_files(
        self, client, db_session, regular_user, tmp_path,
    ):
        _set_shared_enabled(db_session, True)
        outsider = _create_user(db_session, "outsider_list")
        shared = create_shared_workspace(db_session, name="非成员库", owner=regular_user)
        _add_shared_file(db_session, owner=regular_user, workspace_id=shared.id, tmp_path=tmp_path)
        db_session.commit()

        token = create_access_token(outsider.id, outsider.password_rev)
        r = client.get(
            "/api/files",
            headers={"Authorization": f"Bearer {token}"},
            params={"workspace_id": shared.id},
        )
        assert r.status_code == 403, r.text

    def test_viewer_can_read_but_cannot_upload(
        self, client, db_session, regular_user, tmp_path,
    ):
        _set_shared_enabled(db_session, True)
        viewer = _create_user(db_session, "viewer_upload")
        shared = _make_shared_with_members(db_session, regular_user, viewer, member_role="viewer")
        shared_file = _add_shared_file(
            db_session, owner=regular_user, workspace_id=shared.id, tmp_path=tmp_path,
        )

        h = {"Authorization": f"Bearer {create_access_token(viewer.id, viewer.password_rev)}"}
        r_list = client.get("/api/files", headers=h, params={"workspace_id": shared.id})
        assert r_list.status_code == 200
        assert any(x["id"] == shared_file.id for x in r_list.json()["items"])

        r_get = client.get(f"/api/files/{shared_file.id}", headers=h, params={"workspace_id": shared.id})
        assert r_get.status_code == 200

        r_up = client.post(
            "/api/files/upload",
            headers=h,
            data={"workspace_id": str(shared.id)},
            files={"file": ("new.txt", b"new", "text/plain")},
        )
        assert r_up.status_code == 403, r_up.text

    def test_contributor_can_upload_to_shared(self, client, db_session, regular_user):
        _set_shared_enabled(db_session, True)
        contributor = _create_user(db_session, "contrib_upload")
        shared = _make_shared_with_members(
            db_session, regular_user, contributor, member_role="contributor",
        )

        h = {"Authorization": f"Bearer {create_access_token(contributor.id, contributor.password_rev)}"}
        r = client.post(
            "/api/files/upload",
            headers=h,
            data={"workspace_id": str(shared.id)},
            files={"file": ("contrib.txt", b"from-contributor", "text/plain")},
        )
        assert r.status_code == 200, r.text
        assert r.json()["workspace_id"] == shared.id
        assert r.json()["user_id"] == contributor.id

    def test_member_can_list_folders_in_shared(self, client, db_session, regular_user):
        _set_shared_enabled(db_session, True)
        member = _create_user(db_session, "folder_member")
        shared = _make_shared_with_members(db_session, regular_user, member, member_role="viewer")

        h_owner = {"Authorization": f"Bearer {create_access_token(regular_user.id, regular_user.password_rev)}"}
        r_mk = client.post(
            "/api/folders",
            headers=h_owner,
            json={"name": "共享目录"},
            params={"workspace_id": shared.id},
        )
        assert r_mk.status_code == 201, r_mk.text

        h = {"Authorization": f"Bearer {create_access_token(member.id, member.password_rev)}"}
        r = client.get("/api/folders", headers=h, params={"workspace_id": shared.id})
        assert r.status_code == 200, r.text
        assert any(f["name"] == "共享目录" for f in r.json())

    @patch("services.kb_search_service.embed_text")
    def test_cross_workspace_search_merges_personal_and_shared(
        self, mock_embed, client, db_session, regular_user,
    ):
        from config import OLLAMA_EMBED_DIM
        from models.file import File as FileModel

        _set_shared_enabled(db_session, True)
        mock_embed.return_value = [0.5] * OLLAMA_EMBED_DIM
        personal = ensure_personal_workspace(db_session, regular_user)
        shared = create_shared_workspace(db_session, name="跨空间库", owner=regular_user)

        for ws_id, label in ((personal.id, "personal-x"), (shared.id, "shared-x")):
            f = FileModel(
                filename=f"{label}.pdf",
                original_name=f"{label}.pdf",
                file_path=f"/tmp/{label}.pdf",
                file_size=1,
                mime_type="application/pdf",
                user_id=regular_user.id,
                workspace_id=ws_id,
                index_status="ready",
                publish_status="published",
            )
            db_session.add(f)
            db_session.commit()
            _add_kb_chunk(
                db_session,
                owner=regular_user,
                file_id=f.id,
                workspace_id=ws_id,
                text=f"quantum {label} marker",
            )

        h = {"Authorization": f"Bearer {create_access_token(regular_user.id, regular_user.password_rev)}"}
        r = client.post(
            "/api/knowledge-base/search",
            headers=h,
            json={"query": "quantum", "top_k": 10},
            params={"cross_workspace": True},
        )
        assert r.status_code == 200, r.text
        names = {item["original_name"] for item in r.json()["items"]}
        assert "personal-x.pdf" in names
        assert "shared-x.pdf" in names


class TestSharedDisabled:
    """共享禁用 单元测试。

        Authors:
            徐泽宇

        Copyright:
            © 2026 徐泽宇

        Since:
            2026-05-24
    """
    def test_list_files_with_shared_workspace_id_forbidden(
        self, client, db_session, regular_user, tmp_path,
    ):
        _set_shared_enabled(db_session, False)
        shared = create_shared_workspace(db_session, name="关闭后不可见", owner=regular_user)
        _add_shared_file(db_session, owner=regular_user, workspace_id=shared.id, tmp_path=tmp_path)
        db_session.commit()

        h = {"Authorization": f"Bearer {create_access_token(regular_user.id, regular_user.password_rev)}"}
        r = client.get("/api/files", headers=h, params={"workspace_id": shared.id})
        assert r.status_code == 403, r.text

    def test_list_folders_with_shared_workspace_id_forbidden(self, client, db_session, regular_user):
        _set_shared_enabled(db_session, False)
        shared = create_shared_workspace(db_session, name="关闭后目录", owner=regular_user)
        db_session.commit()

        h = {"Authorization": f"Bearer {create_access_token(regular_user.id, regular_user.password_rev)}"}
        r = client.get("/api/folders", headers=h, params={"workspace_id": shared.id})
        assert r.status_code == 403, r.text

    def test_upload_with_shared_workspace_id_forbidden(self, client, db_session, regular_user):
        _set_shared_enabled(db_session, False)
        shared = create_shared_workspace(db_session, name="关闭后上传", owner=regular_user)
        db_session.commit()

        h = {"Authorization": f"Bearer {create_access_token(regular_user.id, regular_user.password_rev)}"}
        r = client.post(
            "/api/files/upload",
            headers=h,
            data={"workspace_id": str(shared.id)},
            files={"file": ("x.txt", b"x", "text/plain")},
        )
        assert r.status_code == 403, r.text

    def test_member_cannot_download_shared_file_by_id_when_disabled(
        self, client, db_session, regular_user, tmp_path,
    ):
        _set_shared_enabled(db_session, True)
        member = _create_user(db_session, "member_disabled_dl")
        shared = _make_shared_with_members(db_session, regular_user, member, member_role="viewer")
        shared_file = _add_shared_file(
            db_session, owner=regular_user, workspace_id=shared.id, tmp_path=tmp_path,
        )

        _set_shared_enabled(db_session, False)
        h = {"Authorization": f"Bearer {create_access_token(member.id, member.password_rev)}"}

        assert client.get(f"/api/files/{shared_file.id}", headers=h).status_code == 404
        assert client.get(f"/api/files/{shared_file.id}/download", headers=h).status_code == 404
        assert client.get(f"/api/files/{shared_file.id}/preview", headers=h).status_code == 404

    def test_owner_cannot_download_own_shared_file_when_disabled(
        self, client, db_session, regular_user, tmp_path,
    ):
        _set_shared_enabled(db_session, True)
        shared = create_shared_workspace(db_session, name="关闭后 owner", owner=regular_user)
        shared_file = _add_shared_file(
            db_session, owner=regular_user, workspace_id=shared.id, tmp_path=tmp_path,
        )

        _set_shared_enabled(db_session, False)
        h = {"Authorization": f"Bearer {create_access_token(regular_user.id, regular_user.password_rev)}"}
        assert client.get(f"/api/files/{shared_file.id}/download", headers=h).status_code == 404

    @patch("services.kb_search_service.embed_text")
    def test_kb_search_only_personal_when_disabled(
        self, mock_embed, client, db_session, regular_user,
    ):
        from config import OLLAMA_EMBED_DIM
        from models.file import File as FileModel

        _set_shared_enabled(db_session, False)
        mock_embed.return_value = [0.5] * OLLAMA_EMBED_DIM
        personal = ensure_personal_workspace(db_session, regular_user)
        shared = create_shared_workspace(db_session, name="关闭检索库", owner=regular_user)

        personal_file = FileModel(
            filename="p.pdf",
            original_name="only-personal.pdf",
            file_path="/tmp/p.pdf",
            file_size=1,
            mime_type="application/pdf",
            user_id=regular_user.id,
            workspace_id=personal.id,
            index_status="ready",
            publish_status="published",
        )
        shared_file = FileModel(
            filename="s.pdf",
            original_name="only-shared.pdf",
            file_path="/tmp/s.pdf",
            file_size=1,
            mime_type="application/pdf",
            user_id=regular_user.id,
            workspace_id=shared.id,
            index_status="ready",
            publish_status="published",
        )
        db_session.add_all([personal_file, shared_file])
        db_session.commit()
        for f, text in (
            (personal_file, "quantum personal disabled"),
            (shared_file, "quantum shared disabled"),
        ):
            _add_kb_chunk(
                db_session,
                owner=regular_user,
                file_id=f.id,
                workspace_id=f.workspace_id,
                text=text,
            )

        h = {"Authorization": f"Bearer {create_access_token(regular_user.id, regular_user.password_rev)}"}
        r = client.post(
            "/api/knowledge-base/search",
            headers=h,
            json={"query": "quantum", "top_k": 8},
            params={"workspace_id": shared.id, "cross_workspace": True},
        )
        assert r.status_code == 200, r.text
        hit_ids = {item["file_id"] for item in r.json()["items"]}
        assert personal_file.id in hit_ids
        assert shared_file.id not in hit_ids

    def test_workspaces_list_hides_shared(self, client, db_session, regular_user):
        _set_shared_enabled(db_session, False)
        create_shared_workspace(db_session, name="隐藏于列表", owner=regular_user)
        db_session.commit()

        h = {"Authorization": f"Bearer {create_access_token(regular_user.id, regular_user.password_rev)}"}
        r = client.get("/api/workspaces", headers=h)
        assert r.status_code == 200
        assert all(w["kind"] != "shared" for w in r.json())


class TestToggleRegression:
    """toggleregression 单元测试。

        Authors:
            徐泽宇

        Copyright:
            © 2026 徐泽宇

        Since:
            2026-05-24
    """
    def test_reenable_shared_restores_member_access(
        self, client, db_session, regular_user, tmp_path,
    ):
        member = _create_user(db_session, "toggle_member")
        _set_shared_enabled(db_session, True)
        shared = _make_shared_with_members(db_session, regular_user, member, member_role="viewer")
        shared_file = _add_shared_file(
            db_session, owner=regular_user, workspace_id=shared.id, tmp_path=tmp_path,
        )

        _set_shared_enabled(db_session, False)
        h = {"Authorization": f"Bearer {create_access_token(member.id, member.password_rev)}"}
        assert client.get(f"/api/files/{shared_file.id}", headers=h).status_code == 404

        _set_shared_enabled(db_session, True)
        r = client.get(
            f"/api/files/{shared_file.id}",
            headers=h,
            params={"workspace_id": shared.id},
        )
        assert r.status_code == 200, r.text
        assert client.get(
            f"/api/files/{shared_file.id}/download",
            headers=h,
            params={"workspace_id": shared.id},
        ).status_code == 200
