# Copyright (c) 2026 徐泽宇
"""企业知识空间 API。

Authors:
    徐泽宇

Copyright:
    © 2026 徐泽宇
"""

from unittest.mock import patch

from services.workspace_service import ensure_personal_workspace, create_shared_workspace


def test_list_workspaces(client, jwt_token, regular_user):
    r = client.get("/api/workspaces", headers={"Authorization": f"Bearer {jwt_token}"})
    assert r.status_code == 200
    data = r.json()
    assert any(w["kind"] == "personal" for w in data)


def test_create_shared_workspace_forbidden_for_regular_user(client, jwt_token):
    r = client.post(
        "/api/workspaces",
        headers={"Authorization": f"Bearer {jwt_token}"},
        json={"name": "测试协作库"},
    )
    assert r.status_code == 403

def test_upload_with_folder_id(client, jwt_token, db_session, regular_user):
    """回归：上传前校验文件夹时 ws_id 须已解析（曾 UnboundLocalError）。"""
    from models.workspace import Workspace
    from services.workspace_service import ensure_personal_workspace

    ws = ensure_personal_workspace(db_session, regular_user)
    r_folder = client.post(
        "/api/folders",
        headers={"Authorization": f"Bearer {jwt_token}"},
        json={"name": "upload-target"},
        params={"workspace_id": ws.id},
    )
    assert r_folder.status_code in (200, 201)
    folder_id = r_folder.json()["id"]
    r = client.post(
        "/api/files/upload",
        headers={"Authorization": f"Bearer {jwt_token}"},
        data={"folder_id": str(folder_id), "workspace_id": str(ws.id)},
        files={"file": ("in-folder.txt", b"hello", "text/plain")},
    )
    assert r.status_code == 200
    assert r.json()["folder_id"] == folder_id


def test_upload_to_shared_workspace_requires_workspace_id(client, jwt_token, db_session, regular_user):
    """共享空间上传须带 workspace_id，否则目录校验失败或文件落入个人空间。"""
    from services.workspace_service import create_shared_workspace

    shared = create_shared_workspace(db_session, name="上传测试库", owner=regular_user)
    r_folder = client.post(
        "/api/folders",
        headers={"Authorization": f"Bearer {jwt_token}"},
        json={"name": "共享目录"},
        params={"workspace_id": shared.id},
    )
    assert r_folder.status_code == 201, r_folder.text
    folder_id = r_folder.json()["id"]

    r_bad = client.post(
        "/api/files/upload",
        headers={"Authorization": f"Bearer {jwt_token}"},
        data={"folder_id": str(folder_id)},
        files={"file": ("shared-only.txt", b"shared ws upload", "text/plain")},
    )
    assert r_bad.status_code == 404, r_bad.text

    r_ok = client.post(
        "/api/files/upload",
        headers={"Authorization": f"Bearer {jwt_token}"},
        data={"folder_id": str(folder_id), "workspace_id": str(shared.id)},
        files={"file": ("shared-only.txt", b"shared ws upload", "text/plain")},
    )
    assert r_ok.status_code == 200, r_ok.text
    assert r_ok.json()["workspace_id"] == shared.id
    assert r_ok.json()["folder_id"] == folder_id

    r_list = client.get(
        "/api/files",
        headers={"Authorization": f"Bearer {jwt_token}"},
        params={"workspace_id": shared.id},
    )
    assert r_list.status_code == 200
    assert any(item["original_name"] == "shared-only.txt" for item in r_list.json()["items"])


def test_shared_workspace_md_note_requires_workspace_id(client, jwt_token, db_session, regular_user):
    """共享空间文件的资料笔记读写须带 workspace_id，否则按个人空间解析会 404。"""
    shared = create_shared_workspace(db_session, name="笔记测试库", owner=regular_user)
    md_body = "# 共享笔记\n\nextracted content\n"
    r_up = client.post(
        "/api/files/upload",
        headers={"Authorization": f"Bearer {jwt_token}"},
        data={"workspace_id": str(shared.id)},
        files={"file": ("shared-note.md", md_body.encode("utf-8"), "text/markdown")},
    )
    assert r_up.status_code == 200, r_up.text
    file_id = r_up.json()["id"]
    assert r_up.json()["has_md"] is True

    h = {"Authorization": f"Bearer {jwt_token}"}
    r_missing_ws = client.get(f"/api/files/{file_id}/md", headers=h)
    assert r_missing_ws.status_code == 404, r_missing_ws.text

    r_get = client.get(f"/api/files/{file_id}/md", headers=h, params={"workspace_id": shared.id})
    assert r_get.status_code == 200, r_get.text
    assert r_get.text == md_body

    updated = "# 共享笔记\n\nupdated\n"
    r_put = client.put(
        f"/api/files/{file_id}/md",
        headers=h,
        params={"workspace_id": shared.id},
        json={"content": updated},
    )
    assert r_put.status_code == 200, r_put.text
    r_get2 = client.get(f"/api/files/{file_id}/md", headers=h, params={"workspace_id": shared.id})
    assert r_get2.status_code == 200
    assert r_get2.text == updated


def test_list_workspaces_hides_shared_when_disabled(client, jwt_token, db_session, regular_user):
    from services.system_setting_service import KEY_SHARED_WORKSPACES_ENABLED, update_settings
    from services.workspace_service import create_shared_workspace

    create_shared_workspace(db_session, name="隐藏库", owner=regular_user)
    db_session.commit()
    update_settings(db_session, {KEY_SHARED_WORKSPACES_ENABLED: "false"})

    r = client.get("/api/workspaces", headers={"Authorization": f"Bearer {jwt_token}"})
    assert r.status_code == 200, r.text
    kinds = [w["kind"] for w in r.json()]
    assert "shared" not in kinds
    assert any(k == "personal" for k in kinds)


def test_admin_create_shared_workspace_blocked_when_disabled(
    client, admin_jwt_token, regular_user, db_session,
):
    from services.system_setting_service import KEY_SHARED_WORKSPACES_ENABLED, update_settings

    update_settings(db_session, {KEY_SHARED_WORKSPACES_ENABLED: "false"})
    r = client.post(
        "/api/admin/workspaces",
        headers={"Authorization": f"Bearer {admin_jwt_token}"},
        json={"name": "不应创建", "owner_user_id": regular_user.id},
    )
    assert r.status_code == 403, r.text


@patch("services.kb_search_service.embed_text")
def test_kb_search_cross_all_accessible_workspaces_when_shared_enabled(
    mock_embed, client, jwt_token, db_session, regular_user,
):
    """共享空间开启且用户可访问共享库时，向量检索跨全部可访问空间。"""
    from config import OLLAMA_EMBED_DIM
    from models.file import File as FileModel
    from models.kb_chunk import KbChunk
    from services.system_setting_service import KEY_SHARED_WORKSPACES_ENABLED, update_settings
    from services.workspace_service import ensure_personal_workspace

    update_settings(db_session, {KEY_SHARED_WORKSPACES_ENABLED: "true"})
    mock_embed.return_value = [0.5] * OLLAMA_EMBED_DIM
    personal = ensure_personal_workspace(db_session, regular_user)
    shared = create_shared_workspace(db_session, name="检索测试库", owner=regular_user)

    personal_file = FileModel(
        filename="personal.pdf",
        original_name="personal-quantum.pdf",
        file_path="/tmp/personal.pdf",
        file_size=1,
        mime_type="application/pdf",
        user_id=regular_user.id,
        workspace_id=personal.id,
        index_status="ready",
        publish_status="published",
    )
    shared_file = FileModel(
        filename="shared.pdf",
        original_name="shared-quantum.pdf",
        file_path="/tmp/shared.pdf",
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
        (personal_file, "quantum biology personal workspace"),
        (shared_file, "quantum biology shared workspace"),
    ):
        db_session.add(
            KbChunk(
                user_id=regular_user.id,
                workspace_id=f.workspace_id,
                file_id=f.id,
                chunk_index=0,
                source="sidecar_md",
                text=text,
                char_start=0,
                char_end=30,
                embedding=[0.5] * OLLAMA_EMBED_DIM,
                embedding_model="test-model",
            )
        )
    db_session.commit()

    h = {"Authorization": f"Bearer {jwt_token}"}
    r = client.post(
        "/api/knowledge-base/search",
        headers=h,
        json={"query": "quantum", "top_k": 8},
        params={"workspace_id": personal.id, "cross_workspace": True},
    )
    assert r.status_code == 200, r.text
    hit_ids = {item["file_id"] for item in r.json()["items"]}
    assert personal_file.id in hit_ids
    assert shared_file.id in hit_ids


@patch("services.kb_search_service.embed_text")
def test_kb_search_single_workspace_when_shared_disabled(
    mock_embed, client, jwt_token, db_session, regular_user,
):
    """共享空间功能关闭时，向量检索仍限定在当前空间。"""
    from config import OLLAMA_EMBED_DIM
    from models.file import File as FileModel
    from models.kb_chunk import KbChunk
    from services.system_setting_service import KEY_SHARED_WORKSPACES_ENABLED, update_settings
    from services.workspace_service import ensure_personal_workspace

    update_settings(db_session, {KEY_SHARED_WORKSPACES_ENABLED: "false"})
    mock_embed.return_value = [0.5] * OLLAMA_EMBED_DIM
    personal = ensure_personal_workspace(db_session, regular_user)
    shared = create_shared_workspace(db_session, name="关闭时检索库", owner=regular_user)
    shared_only = FileModel(
        filename="shared.pdf",
        original_name="shared-only-quantum.pdf",
        file_path="/tmp/shared-only.pdf",
        file_size=1,
        mime_type="application/pdf",
        user_id=regular_user.id,
        workspace_id=shared.id,
        index_status="ready",
        publish_status="published",
    )
    db_session.add(shared_only)
    db_session.commit()
    db_session.add(
        KbChunk(
            user_id=regular_user.id,
            workspace_id=shared.id,
            file_id=shared_only.id,
            chunk_index=0,
            source="sidecar_md",
            text="quantum biology shared only",
            char_start=0,
            char_end=24,
            embedding=[0.5] * OLLAMA_EMBED_DIM,
            embedding_model="test-model",
        )
    )
    db_session.commit()

    h = {"Authorization": f"Bearer {jwt_token}"}
    r = client.post(
        "/api/knowledge-base/search",
        headers=h,
        json={"query": "quantum", "top_k": 5},
        params={"workspace_id": personal.id},
    )
    assert r.status_code == 200, r.text
    assert r.json()["items"] == []


@patch("services.kb_search_service.embed_text")
def test_kb_search_current_workspace_when_cross_workspace_off(
    mock_embed, client, jwt_token, db_session, regular_user,
):
    """cross_workspace=false 时仅检索 workspace_id 所指空间（共享空间选中则搜共享库）。"""
    from config import OLLAMA_EMBED_DIM
    from models.file import File as FileModel
    from models.kb_chunk import KbChunk
    from services.system_setting_service import KEY_SHARED_WORKSPACES_ENABLED, update_settings
    from services.workspace_service import ensure_personal_workspace

    update_settings(db_session, {KEY_SHARED_WORKSPACES_ENABLED: "true"})
    mock_embed.return_value = [0.5] * OLLAMA_EMBED_DIM
    personal = ensure_personal_workspace(db_session, regular_user)
    shared = create_shared_workspace(db_session, name="开关测试库", owner=regular_user)
    personal_file = FileModel(
        filename="p.pdf",
        original_name="personal-only.pdf",
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
        original_name="shared-only.pdf",
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
        (personal_file, "quantum personal only"),
        (shared_file, "quantum shared only"),
    ):
        db_session.add(
            KbChunk(
                user_id=regular_user.id,
                workspace_id=f.workspace_id,
                file_id=f.id,
                chunk_index=0,
                source="sidecar_md",
                text=text,
                char_start=0,
                char_end=20,
                embedding=[0.5] * OLLAMA_EMBED_DIM,
                embedding_model="test-model",
            )
        )
    db_session.commit()

    h = {"Authorization": f"Bearer {jwt_token}"}
    r = client.post(
        "/api/knowledge-base/search",
        headers=h,
        json={"query": "quantum", "top_k": 8},
        params={"workspace_id": shared.id, "cross_workspace": False},
    )
    assert r.status_code == 200, r.text
    hit_ids = {item["file_id"] for item in r.json()["items"]}
    assert shared_file.id in hit_ids
    assert personal_file.id not in hit_ids

    r_personal = client.post(
        "/api/knowledge-base/search",
        headers=h,
        json={"query": "quantum", "top_k": 8},
        params={"workspace_id": personal.id, "cross_workspace": False},
    )
    assert r_personal.status_code == 200, r_personal.text
    personal_hits = {item["file_id"] for item in r_personal.json()["items"]}
    assert personal_file.id in personal_hits
    assert shared_file.id not in personal_hits


@patch("services.kb_search_service.embed_text")
def test_kb_search_ignores_cross_workspace_when_shared_disabled(
    mock_embed, client, jwt_token, db_session, regular_user,
):
    """共享空间功能关闭时，即使请求 cross_workspace=true 且 workspace_id 指向共享库，也仅搜个人空间。"""
    from config import OLLAMA_EMBED_DIM
    from models.file import File as FileModel
    from models.kb_chunk import KbChunk
    from services.system_setting_service import KEY_SHARED_WORKSPACES_ENABLED, update_settings
    from services.workspace_service import ensure_personal_workspace

    update_settings(db_session, {KEY_SHARED_WORKSPACES_ENABLED: "false"})
    mock_embed.return_value = [0.5] * OLLAMA_EMBED_DIM
    personal = ensure_personal_workspace(db_session, regular_user)
    shared = create_shared_workspace(db_session, name="关闭跨空间库", owner=regular_user)
    personal_file = FileModel(
        filename="p.pdf",
        original_name="personal-hit.pdf",
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
        original_name="shared-hit.pdf",
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
        (personal_file, "quantum personal hit"),
        (shared_file, "quantum shared hit"),
    ):
        db_session.add(
            KbChunk(
                user_id=regular_user.id,
                workspace_id=f.workspace_id,
                file_id=f.id,
                chunk_index=0,
                source="sidecar_md",
                text=text,
                char_start=0,
                char_end=20,
                embedding=[0.5] * OLLAMA_EMBED_DIM,
                embedding_model="test-model",
            )
        )
    db_session.commit()

    h = {"Authorization": f"Bearer {jwt_token}"}
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

def test_shared_workspace_member_can_get_preview_download_and_search(
    client, db_session, regular_user, tmp_path,
):
    """A 上传到共享空间的文件，B 作为成员可读、预览、下载并在当前空间检索命中。"""
    from config import OLLAMA_EMBED_DIM
    from models.file import File as FileModel
    from models.kb_chunk import KbChunk
    from services.auth_service import create_access_token
    from services.system_setting_service import KEY_SHARED_WORKSPACES_ENABLED, update_settings
    from services.workspace_service import set_member_role
    from tests.conftest import _create_user
    from unittest.mock import patch

    update_settings(db_session, {KEY_SHARED_WORKSPACES_ENABLED: "true"})
    user_b = _create_user(db_session, "shared_member_b")
    shared = create_shared_workspace(db_session, name="成员可读库", owner=regular_user)
    set_member_role(db_session, shared.id, user_b.id, "viewer")
    db_session.commit()

    blob_path = tmp_path / "shared-by-a.bin"
    blob_path.write_bytes(b"content-from-user-a")
    shared_file = FileModel(
        filename="shared-by-a.bin",
        original_name="shared-by-a.bin",
        file_path=str(blob_path),
        file_size=blob_path.stat().st_size,
        mime_type="application/octet-stream",
        user_id=regular_user.id,
        workspace_id=shared.id,
        index_status="ready",
        publish_status="published",
    )
    db_session.add(shared_file)
    db_session.commit()
    db_session.add(
        KbChunk(
            user_id=regular_user.id,
            workspace_id=shared.id,
            file_id=shared_file.id,
            chunk_index=0,
            source="sidecar_md",
            text="member readable quantum chunk",
            char_start=0,
            char_end=30,
            embedding=[0.5] * OLLAMA_EMBED_DIM,
            embedding_model="test-model",
        )
    )
    db_session.commit()

    token_b = create_access_token(user_b.id, user_b.password_rev)
    h_b = {"Authorization": f"Bearer {token_b}"}

    r_list = client.get("/api/files", headers=h_b, params={"workspace_id": shared.id})
    assert r_list.status_code == 200, r_list.text
    assert any(item["id"] == shared_file.id for item in r_list.json()["items"])

    r_get = client.get(
        f"/api/files/{shared_file.id}",
        headers=h_b,
        params={"workspace_id": shared.id},
    )
    assert r_get.status_code == 200, r_get.text
    assert r_get.json()["original_name"] == "shared-by-a.bin"

    r_dl = client.get(
        f"/api/files/{shared_file.id}/download",
        headers=h_b,
        params={"workspace_id": shared.id},
    )
    assert r_dl.status_code == 200, r_dl.text
    assert r_dl.content == b"content-from-user-a"

    r_preview = client.get(
        f"/api/files/{shared_file.id}/preview",
        headers=h_b,
        params={"workspace_id": shared.id},
    )
    assert r_preview.status_code == 200, r_preview.text

    with patch("services.kb_search_service.embed_text") as mock_embed:
        mock_embed.return_value = [0.5] * OLLAMA_EMBED_DIM
        r_search = client.post(
            "/api/knowledge-base/search",
            headers=h_b,
            json={"query": "quantum", "top_k": 8, "group_by_file": True},
            params={"workspace_id": shared.id, "cross_workspace": False},
        )
    assert r_search.status_code == 200, r_search.text
    assert any(item["file_id"] == shared_file.id for item in r_search.json()["items"])

    with patch("services.kb_search_service.embed_text") as mock_embed:
        mock_embed.return_value = [0.5] * OLLAMA_EMBED_DIM
        r_cross = client.post(
            "/api/knowledge-base/search",
            headers=h_b,
            json={"query": "quantum", "top_k": 8, "group_by_file": True},
            params={"cross_workspace": True},
        )
    assert r_cross.status_code == 200, r_cross.text
    assert any(item["file_id"] == shared_file.id for item in r_cross.json()["items"])

