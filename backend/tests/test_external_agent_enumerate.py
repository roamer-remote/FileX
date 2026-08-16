# Copyright (c) 2026 徐泽宇
"""智能体枚举：workspace-layout、files-awaiting-ai 空间过滤、GET /api/files enumerate。

Authors:
    徐泽宇

Copyright:
    © 2026 徐泽宇
"""
import hashlib

import pytest
from fastapi import status

from models.file import File as FileModel
from models.folder import Folder as FolderModel
from services.workspace_service import ensure_personal_workspace


@pytest.fixture
def _layout_files(db_session, regular_user):
    ws = ensure_personal_workspace(db_session, regular_user)
    folder = FolderModel(
        name="文献",
        parent_id=None,
        user_id=regular_user.id,
        workspace_id=ws.id,
    )
    db_session.add(folder)
    db_session.flush()
    f1 = FileModel(
        filename="a.bin",
        original_name="alpha.pdf",
        file_path="/tmp/a",
        file_size=1,
        mime_type="application/pdf",
        user_id=regular_user.id,
        workspace_id=ws.id,
        folder_id=folder.id,
        md5_hash=hashlib.md5(b"a").hexdigest(),
        page_kind="source",
    )
    f2 = FileModel(
        filename="b.bin",
        original_name="beta.pdf",
        file_path="/tmp/b",
        file_size=1,
        mime_type="application/pdf",
        user_id=regular_user.id,
        workspace_id=ws.id,
        folder_id=None,
        md5_hash=hashlib.md5(b"b").hexdigest(),
        page_kind="source",
    )
    db_session.add_all([f1, f2])
    db_session.commit()
    db_session.refresh(folder)
    for x in (f1, f2):
        db_session.refresh(x)
    return ws, folder, f1, f2


def test_workspace_layout_markdown(client, active_api_key, _layout_files):
    ws, folder, _f1, _f2 = _layout_files
    resp = client.get(
        f"/api/external/workspace-layout?workspace_id={ws.id}",
        headers={"Authorization": f"Bearer {active_api_key._plaintext}"},
    )
    assert resp.status_code == status.HTTP_200_OK
    assert "text/markdown" in resp.headers.get("content-type", "")
    body = resp.text
    assert "alpha.pdf" in body
    assert "beta.pdf" in body
    assert str(folder.id) in body


def test_files_awaiting_ai_cross_workspace_conflict(client, active_api_key):
    resp = client.get(
        "/api/external/files-awaiting-ai?workspace_id=1&cross_workspace=true",
        headers={"Authorization": f"Bearer {active_api_key._plaintext}"},
    )
    assert resp.status_code == status.HTTP_400_BAD_REQUEST


def test_list_files_enumerate_api_key(client, active_api_key, _layout_files):
    ws, _folder, _f1, _f2 = _layout_files
    resp = client.get(
        f"/api/files?workspace_id={ws.id}&enumerate=true",
        headers={"Authorization": f"Bearer {active_api_key._plaintext}"},
    )
    assert resp.status_code == status.HTTP_200_OK
    data = resp.json()
    assert data["total"] >= 2
    assert len(data["items"]) >= 2
    names = {it["original_name"] for it in data["items"]}
    assert "alpha.pdf" in names
    assert "beta.pdf" in names


def test_list_files_enumerate_rejects_jwt(client, jwt_token, _layout_files):
    ws, *_ = _layout_files
    resp = client.get(
        f"/api/files?workspace_id={ws.id}&enumerate=true",
        headers={"Authorization": f"Bearer {jwt_token}"},
    )
    assert resp.status_code == status.HTTP_400_BAD_REQUEST
