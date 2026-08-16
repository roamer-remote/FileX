# Copyright (c) 2026 徐泽宇
"""分享来源 + 外部 API：错用他人 API Key 时应在携带分享令牌的情况下被拒绝。

Authors:
    徐泽宇

Copyright:
    © 2026 徐泽宇
"""

import hashlib

from fastapi import status

from services.share_service import create_share_link


def _write_owner_file(db_session, user_a):
    from io import BytesIO

    from fastapi import UploadFile

    from services.file_service import save_upload

    content = b"share-gate-test-bytes-unique-xyz"
    md5 = hashlib.md5(content).hexdigest()
    uf = UploadFile(filename="doc.txt", file=BytesIO(content))
    fr = save_upload(uf, user_a.id, content)
    fr.md5_hash = md5
    db_session.add(fr)
    db_session.commit()
    db_session.refresh(fr)
    return content, md5, fr


def test_external_upload_share_token_wrong_api_user_forbidden(client, db_session):
    from tests.conftest import _create_api_key, _create_user

    user_a = _create_user(db_session, "gate_owner_a")
    user_b = _create_user(db_session, "gate_other_b")
    key_b = _create_api_key(db_session, user_b)

    content, md5, fr = _write_owner_file(db_session, user_a)
    share = create_share_link(db_session, fr.id, user_a.id)

    resp = client.post(
        "/api/external/files",
        headers={
            "Authorization": f"Bearer {key_b._plaintext}",
            "X-FileX-Share-Token": share.token,
        },
        files={"file": ("doc.txt", content, "text/plain")},
    )
    assert resp.status_code == status.HTTP_403_FORBIDDEN
    assert "所有者" in resp.json().get("detail", "")


def test_external_upload_share_token_owner_ok(client, db_session):
    from tests.conftest import _create_api_key, _create_user

    user_a = _create_user(db_session, "gate_owner_a2")
    key_a = _create_api_key(db_session, user_a)

    content, md5, fr = _write_owner_file(db_session, user_a)
    share = create_share_link(db_session, fr.id, user_a.id)

    resp = client.post(
        "/api/external/files",
        headers={
            "Authorization": f"Bearer {key_a._plaintext}",
            "X-FileX-Share-Token": share.token,
        },
        files={"file": ("doc.txt", content, "text/plain")},
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data.get("deduplicated") is True
    assert data.get("md5_hash") == md5


def test_md_content_share_token_wrong_api_user_forbidden(client, db_session):
    from tests.conftest import _create_api_key, _create_user

    user_a = _create_user(db_session, "gate_owner_md_a")
    user_b = _create_user(db_session, "gate_other_md_b")
    key_b = _create_api_key(db_session, user_b)

    content, md5, fr = _write_owner_file(db_session, user_a)
    share = create_share_link(db_session, fr.id, user_a.id)

    resp = client.post(
        "/api/external/md-content",
        headers={
            "Authorization": f"Bearer {key_b._plaintext}",
            "X-FileX-Share-Token": share.token,
        },
        json={"md5_hash": md5, "content": "# Generated\n"},
    )
    assert resp.status_code == status.HTTP_403_FORBIDDEN


def test_md_content_share_token_md5_mismatch(client, db_session):
    from tests.conftest import _create_api_key, _create_user

    user_a = _create_user(db_session, "gate_owner_md5")
    key_a = _create_api_key(db_session, user_a)

    content, md5, fr = _write_owner_file(db_session, user_a)
    share = create_share_link(db_session, fr.id, user_a.id)

    wrong_md5 = "a" * 32
    resp = client.post(
        "/api/external/md-content",
        headers={
            "Authorization": f"Bearer {key_a._plaintext}",
            "X-FileX-Share-Token": share.token,
        },
        json={"md5_hash": wrong_md5, "content": "# x\n"},
    )
    assert resp.status_code == status.HTTP_400_BAD_REQUEST


def test_files_with_md_third_party_bundle(client, db_session):
    """第三方来源：无分享令牌，单次请求上传原文并附带 Markdown。"""
    from tests.conftest import _create_api_key, _create_user

    user = _create_user(db_session, "bundle_tp_user")
    key = _create_api_key(db_session, user)
    content = b"third-party-file-bytes-unique"
    md_txt = "# Summary\n\nOK.\n"
    resp = client.post(
        "/api/external/files-with-md",
        headers={"Authorization": f"Bearer {key._plaintext}"},
        files={"file": ("paper.pdf", content, "application/pdf")},
        data={"markdown": md_txt},
    )
    assert resp.status_code == status.HTTP_200_OK
    payload = resp.json()
    assert payload["markdown_saved"] is True
    assert payload["file"]["has_md"] is True
    assert payload["file"]["md5_hash"] == hashlib.md5(content).hexdigest()
    from models.file import File as FileModel
    from services.okf_note_service import read_okf_note

    file_record = db_session.get(FileModel, payload["file"]["id"])
    assert file_record is not None
    note = read_okf_note(file_record)
    meta, body = note.frontmatter, note.body
    assert meta["type"] == "FileX Source"
    assert body == md_txt


def test_files_with_md_optional_markdown_skipped(client, db_session):
    """仅上传原文、不传 markdown 或与空白等价于只入库文件。"""
    from tests.conftest import _create_api_key, _create_user

    user = _create_user(db_session, "bundle_nomd_user")
    key = _create_api_key(db_session, user)
    content = b"no-markdown-body"
    resp = client.post(
        "/api/external/files-with-md",
        headers={"Authorization": f"Bearer {key._plaintext}"},
        files={"file": ("x.txt", content, "text/plain")},
        data={"markdown": "   \n  "},
    )
    assert resp.status_code == status.HTTP_200_OK
    payload = resp.json()
    assert payload["markdown_saved"] is False
    assert payload["file"]["has_md"] is True


def test_files_with_md_share_token_wrong_user(client, db_session):
    """合并接口在携带分享令牌时同样校验所有者。"""
    from tests.conftest import _create_api_key, _create_user

    user_a = _create_user(db_session, "bundle_owner_a")
    user_b = _create_user(db_session, "bundle_other_b")
    key_b = _create_api_key(db_session, user_b)

    content, _md5, fr = _write_owner_file(db_session, user_a)
    share = create_share_link(db_session, fr.id, user_a.id)

    resp = client.post(
        "/api/external/files-with-md",
        headers={
            "Authorization": f"Bearer {key_b._plaintext}",
            "X-FileX-Share-Token": share.token,
        },
        files={"file": ("doc.txt", content, "text/plain")},
        data={"markdown": "# x\n"},
    )
    assert resp.status_code == status.HTTP_403_FORBIDDEN
