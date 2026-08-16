# Copyright (c) 2026 徐泽宇
"""管理员知识空间 API。

Authors:
    徐泽宇

Copyright:
    © 2026 徐泽宇
"""

from models.file import File as FileModel
from services.workspace_service import ensure_personal_workspace


def test_non_admin_forbidden(client, jwt_token):
    r = client.get("/api/admin/workspaces", headers={"Authorization": f"Bearer {jwt_token}"})
    assert r.status_code == 403


def test_admin_list_and_create_workspace(client, admin_jwt_token, regular_user, db_session):
    r = client.get("/api/admin/workspaces", headers={"Authorization": f"Bearer {admin_jwt_token}"})
    assert r.status_code == 200
    items = r.json()
    assert any(w["kind"] == "personal" for w in items)

    r2 = client.post(
        "/api/admin/workspaces",
        headers={"Authorization": f"Bearer {admin_jwt_token}"},
        json={"name": "研发共享库", "owner_user_id": regular_user.id},
    )
    assert r2.status_code == 201
    ws_id = r2.json()["id"]
    assert r2.json()["kind"] == "shared"

    r3 = client.post(
        f"/api/admin/workspaces/{ws_id}/members",
        headers={"Authorization": f"Bearer {admin_jwt_token}"},
        json={"user_id": regular_user.id, "role": "curator"},
    )
    assert r3.status_code == 200

    ensure_personal_workspace(db_session, regular_user)
    f = FileModel(
        user_id=regular_user.id,
        workspace_id=ws_id,
        filename="t.txt",
        original_name="t.txt",
        file_path="/tmp/t.txt",
        file_size=1,
        mime_type="text/plain",
    )
    db_session.add(f)
    db_session.commit()
    db_session.refresh(f)

    r4 = client.post(
        f"/api/admin/workspaces/{ws_id}/grants",
        headers={"Authorization": f"Bearer {admin_jwt_token}"},
        json={
            "resource_type": "file",
            "resource_id": f.id,
            "grantee_user_id": regular_user.id,
            "permission": "view",
        },
    )
    assert r4.status_code == 201

    r5 = client.put(
        f"/api/admin/files/{f.id}/publish-status",
        headers={"Authorization": f"Bearer {admin_jwt_token}"},
        json={"publish_status": "draft"},
    )
    assert r5.status_code == 200
    assert r5.json()["publish_status"] == "draft"

    r6 = client.get(
        "/api/admin/files",
        headers={"Authorization": f"Bearer {admin_jwt_token}"},
        params={"workspace_id": ws_id},
    )
    assert r6.status_code == 200
    assert any(x["id"] == f.id for x in r6.json()["items"])


def test_regular_user_cannot_create_shared_workspace(client, jwt_token):
    r = client.post(
        "/api/workspaces",
        headers={"Authorization": f"Bearer {jwt_token}"},
        json={"name": "非法空间"},
    )
    assert r.status_code == 403
