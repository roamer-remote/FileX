# Copyright (c) 2026 徐泽宇
"""管理员全站资料列表：用户筛选与文件名搜索。

Authors:
    徐泽宇

Copyright:
    © 2026 徐泽宇
"""

from models.file import File as FileModel
from services.workspace_service import ensure_personal_workspace


def _add_file(db_session, *, user_id: int, workspace_id: int, original_name: str) -> FileModel:
    f = FileModel(
        user_id=user_id,
        workspace_id=workspace_id,
        filename=original_name,
        original_name=original_name,
        file_path=f"/tmp/{original_name}",
        file_size=1,
        mime_type="text/plain",
    )
    db_session.add(f)
    db_session.commit()
    db_session.refresh(f)
    return f


def test_admin_files_filter_by_user_and_search(client, admin_jwt_token, regular_user, admin_user, db_session):
    ws_reg = ensure_personal_workspace(db_session, regular_user)
    ws_admin = ensure_personal_workspace(db_session, admin_user)

    _add_file(db_session, user_id=regular_user.id, workspace_id=ws_reg.id, original_name="alpha-report.pdf")
    _add_file(db_session, user_id=regular_user.id, workspace_id=ws_reg.id, original_name="beta-notes.txt")
    _add_file(db_session, user_id=admin_user.id, workspace_id=ws_admin.id, original_name="alpha-admin.pdf")

    h = {"Authorization": f"Bearer {admin_jwt_token}"}

    r = client.get(
        "/api/admin/files",
        headers=h,
        params={"user_id": regular_user.id, "search": "alpha"},
    )
    assert r.status_code == 200
    names = [x["original_name"] for x in r.json()["items"]]
    assert names == ["alpha-report.pdf"]
    assert r.json()["total"] == 1


def test_admin_files_search_by_id(client, admin_jwt_token, regular_user, db_session):
    ws = ensure_personal_workspace(db_session, regular_user)
    target = _add_file(
        db_session,
        user_id=regular_user.id,
        workspace_id=ws.id,
        original_name="report.pdf",
    )
    h = {"Authorization": f"Bearer {admin_jwt_token}"}
    r = client.get("/api/admin/files", headers=h, params={"search": str(target.id)})
    assert r.status_code == 200
    assert r.json()["total"] == 1
    assert r.json()["items"][0]["id"] == target.id


def test_admin_files_search_id_prefix(client, admin_jwt_token, regular_user, db_session):
    ws = ensure_personal_workspace(db_session, regular_user)
    target = _add_file(
        db_session,
        user_id=regular_user.id,
        workspace_id=ws.id,
        original_name="other.pdf",
    )
    h = {"Authorization": f"Bearer {admin_jwt_token}"}
    r = client.get("/api/admin/files", headers=h, params={"search": f"id:{target.id}"})
    assert r.status_code == 200
    assert r.json()["total"] == 1
    assert r.json()["items"][0]["id"] == target.id


def test_admin_files_search_without_user(client, admin_jwt_token, regular_user, db_session):
    ws = ensure_personal_workspace(db_session, regular_user)
    _add_file(db_session, user_id=regular_user.id, workspace_id=ws.id, original_name="unique-xyz.doc")

    h = {"Authorization": f"Bearer {admin_jwt_token}"}
    r = client.get("/api/admin/files", headers=h, params={"search": "unique-xyz"})
    assert r.status_code == 200
    assert r.json()["total"] >= 1
    assert any(x["original_name"] == "unique-xyz.doc" for x in r.json()["items"])
