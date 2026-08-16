# Copyright (c) 2026 徐泽宇
"""031：管理员跨用户 Markdown 笔记读取。"""

from models.operation_log import OperationLog
from services.workspace_service import ensure_personal_workspace
from tests.conftest import _create_api_key


def _upload_md_note(client, token: str, body: str, filename: str = "owner-note.md") -> int:
    r = client.post(
        "/api/files/upload",
        headers={"Authorization": f"Bearer {token}"},
        files={"file": (filename, body.encode("utf-8"), "text/markdown")},
    )
    assert r.status_code == 200, r.text
    data = r.json()
    assert data["has_md"] is True
    return data["id"]


def test_admin_jwt_reads_other_user_md(client, admin_jwt_token, jwt_token):
    md_body = "# 他人笔记\n\nadmin 可读\n"
    file_id = _upload_md_note(client, jwt_token, md_body)

    r = client.get(
        f"/api/admin/files/{file_id}/md",
        headers={"Authorization": f"Bearer {admin_jwt_token}"},
    )
    assert r.status_code == 200, r.text
    assert r.text == md_body
    assert "text/markdown" in (r.headers.get("content-type") or "")


def test_admin_api_key_reads_other_user_md(client, admin_user, db_session, jwt_token):
    admin_key = _create_api_key(db_session, admin_user)
    md_body = "# API Key\n\nadmin key read\n"
    file_id = _upload_md_note(client, jwt_token, md_body)

    r = client.get(
        f"/api/admin/files/{file_id}/md",
        headers={"Authorization": f"Bearer {admin_key._plaintext}"},
    )
    assert r.status_code == 200, r.text
    assert r.text == md_body


def test_regular_jwt_forbidden_on_admin_md(client, jwt_token):
    file_id = _upload_md_note(client, jwt_token, "# x\n")
    r = client.get(
        f"/api/admin/files/{file_id}/md",
        headers={"Authorization": f"Bearer {jwt_token}"},
    )
    assert r.status_code == 403, r.text
    assert r.json()["detail"] == "需要管理员权限"


def test_regular_api_key_forbidden_on_admin_md(client, active_api_key, jwt_token):
    file_id = _upload_md_note(client, jwt_token, "# x\n")
    r = client.get(
        f"/api/admin/files/{file_id}/md",
        headers={"Authorization": f"Bearer {active_api_key._plaintext}"},
    )
    assert r.status_code == 403, r.text
    assert r.json()["detail"] == "需要管理员权限"


def test_admin_md_missing_file(client, admin_jwt_token):
    r = client.get(
        "/api/admin/files/999999/md",
        headers={"Authorization": f"Bearer {admin_jwt_token}"},
    )
    assert r.status_code == 404, r.text
    assert r.json()["detail"] == "资料不存在"


def test_admin_md_no_note(client, admin_jwt_token, jwt_token):
    """SC-111-001：非 Markdown 上传先落 OKF 空壳（has_md=True / md_has_content=False）。

    admin GET md 对空壳返回 200 空正文；删除笔记后 has_md=False，admin GET md 返回 404。
    """
    from unittest.mock import patch

    with patch("services.kb_extract_service.publish_extract_job"), patch(
        "services.kb_index_service.publish_index_job"
    ):
        r = client.post(
            "/api/files/upload",
            headers={"Authorization": f"Bearer {jwt_token}"},
            files={"file": ("no-md.pdf", b"%PDF-1.4 minimal", "application/pdf")},
        )
    assert r.status_code == 200, r.text
    data = r.json()
    file_id = data["id"]
    assert data["has_md"] is True
    assert data["md_has_content"] is False

    # 空壳：笔记存在但 body 为空
    r = client.get(
        f"/api/admin/files/{file_id}/md",
        headers={"Authorization": f"Bearer {admin_jwt_token}"},
    )
    assert r.status_code == 200, r.text
    assert r.text == ""

    # 删除笔记后回到"无笔记"状态，admin GET md 返回 404
    r_del = client.delete(
        f"/api/files/{file_id}/md",
        headers={"Authorization": f"Bearer {jwt_token}"},
    )
    assert r_del.status_code == 200, r_del.text

    r = client.get(
        f"/api/admin/files/{file_id}/md",
        headers={"Authorization": f"Bearer {admin_jwt_token}"},
    )
    assert r.status_code == 404, r.text
    assert r.json()["detail"] == "该资料没有 Markdown 笔记"


def test_regular_get_md_wrong_workspace_still_404(
    client, admin_jwt_token, jwt_token, db_session, admin_user,
):
    md_body = "# ws isolation\n"
    file_id = _upload_md_note(client, jwt_token, md_body)

    admin_ws = ensure_personal_workspace(db_session, admin_user)
    r_wrong = client.get(
        f"/api/files/{file_id}/md",
        headers={"Authorization": f"Bearer {admin_jwt_token}"},
        params={"workspace_id": admin_ws.id},
    )
    assert r_wrong.status_code == 404, r_wrong.text

    r_admin = client.get(
        f"/api/admin/files/{file_id}/md",
        headers={"Authorization": f"Bearer {admin_jwt_token}"},
    )
    assert r_admin.status_code == 200, r_admin.text
    assert r_admin.text == md_body


def test_admin_md_read_writes_operation_log(
    client, admin_jwt_token, admin_user, jwt_token, db_session,
):
    md_body = "# audit\n"
    file_id = _upload_md_note(client, jwt_token, md_body, filename="audit-note.md")

    r = client.get(
        f"/api/admin/files/{file_id}/md",
        headers={"Authorization": f"Bearer {admin_jwt_token}"},
    )
    assert r.status_code == 200, r.text

    log = (
        db_session.query(OperationLog)
        .filter(
            OperationLog.user_id == admin_user.id,
            OperationLog.action == "管理员查看 Markdown 笔记",
            OperationLog.target_type == "file",
            OperationLog.target_id == file_id,
        )
        .order_by(OperationLog.id.desc())
        .first()
    )
    assert log is not None
    assert "audit-note.md" in (log.detail or "")
