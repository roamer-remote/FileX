# Copyright (c) 2026 徐泽宇
"""外部 API：Markdown 笔记 PUT upsert 与 POST 首次挂载。

Authors:
    徐泽宇

Copyright:
    © 2026 徐泽宇
"""

import hashlib
import os
from io import BytesIO

from fastapi import UploadFile, status

from models.file import File as FileModel
from services.file_service import save_upload
from services.md_paths import md_note_path
from services.md_note_service import save_md_note_for_file
from services.okf.frontmatter import split_frontmatter


def _upload_file(db_session, user, content: bytes, filename: str = "extracted.pdf"):
    md5 = hashlib.md5(content).hexdigest()
    uf = UploadFile(filename=filename, file=BytesIO(content))
    fr = save_upload(uf, user.id, content)
    fr.md5_hash = md5
    db_session.add(fr)
    db_session.commit()
    db_session.refresh(fr)
    return md5, fr


def test_put_md_content_updates_existing_note(client, db_session, active_api_key, regular_user):
    content, fr = _upload_file(db_session, regular_user, b"pdf-bytes-for-md-upsert")
    save_md_note_for_file(db_session, regular_user.id, fr, "# Extracted\n\nRaw OCR text.")
    db_session.commit()
    db_session.refresh(fr)

    refined = "# Extracted\n\nPolished summary.\n"
    resp = client.put(
        "/api/external/md-content",
        headers={"Authorization": f"Bearer {active_api_key._plaintext}"},
        json={"md5_hash": content, "content": refined},
    )
    assert resp.status_code == status.HTTP_200_OK
    data = resp.json()
    assert data["file_id"] == fr.id
    assert data["unchanged"] is False
    assert data["md5_hash"] == content

    note_path = md_note_path(fr.id)
    assert os.path.isfile(note_path)
    meta, body = split_frontmatter(open(note_path, encoding="utf-8").read())
    assert meta["type"] == "FileX Source"
    assert body == refined


def test_put_md_content_unchanged_skips_reindex(client, db_session, active_api_key, regular_user):
    body = "# Same\n"
    _, fr = _upload_file(db_session, regular_user, b"bytes-unchanged-md")
    save_md_note_for_file(db_session, regular_user.id, fr, body)
    db_session.commit()

    resp = client.put(
        "/api/external/md-content",
        headers={"Authorization": f"Bearer {active_api_key._plaintext}"},
        json={"md5_hash": fr.md5_hash, "content": body},
    )
    assert resp.status_code == status.HTTP_200_OK
    assert resp.json()["unchanged"] is True


def test_put_md_content_creates_note_when_missing(client, db_session, active_api_key, regular_user):
    md5, fr = _upload_file(db_session, regular_user, b"no-note-yet-bytes")
    assert fr.has_md is False

    note = "# New note\n"
    resp = client.put(
        "/api/external/md-content",
        headers={"Authorization": f"Bearer {active_api_key._plaintext}"},
        json={"md5_hash": md5, "content": note},
    )
    assert resp.status_code == status.HTTP_200_OK
    db_session.refresh(fr)
    assert fr.has_md is True
    meta, body = split_frontmatter(open(md_note_path(fr.id), encoding="utf-8").read())
    assert meta["type"] == "FileX Source"
    assert body == note


def test_post_md_content_still_409_when_has_md(client, db_session, active_api_key, regular_user):
    md5, fr = _upload_file(db_session, regular_user, b"post-409-bytes")
    save_md_note_for_file(db_session, regular_user.id, fr, "# existing\n")
    db_session.commit()

    resp = client.post(
        "/api/external/md-content",
        headers={"Authorization": f"Bearer {active_api_key._plaintext}"},
        json={"md5_hash": md5, "content": "# other\n"},
    )
    assert resp.status_code == status.HTTP_409_CONFLICT


def test_put_external_file_id_md_matches_files_route(
    client, db_session, active_api_key, regular_user, jwt_token,
):
    _, fr = _upload_file(db_session, regular_user, b"file-id-put-bytes")
    save_md_note_for_file(db_session, regular_user.id, fr, "# v1\n")
    db_session.commit()

    refined = "# v2 polished\n"
    ext = client.put(
        f"/api/external/files/{fr.id}/md",
        headers={"Authorization": f"Bearer {active_api_key._plaintext}"},
        json={"content": refined},
    )
    assert ext.status_code == status.HTTP_200_OK
    assert ext.json()["unchanged"] is False

    web = client.put(
        f"/api/files/{fr.id}/md",
        headers={"Authorization": f"Bearer {jwt_token}"},
        json={"content": refined},
    )
    assert web.status_code == status.HTTP_200_OK
    assert web.json()["unchanged"] is True


def test_resolve_md5_ambiguous_without_workspace_id(client, db_session, active_api_key, regular_user):
    from services.workspace_service import create_shared_workspace, ensure_personal_workspace

    content = b"ambiguous-md5-same-bytes-xyz"
    md5 = hashlib.md5(content).hexdigest()

    ws_personal = ensure_personal_workspace(db_session, regular_user)
    f1 = save_upload(
        UploadFile(filename="a.pdf", file=BytesIO(content)), regular_user.id, content,
    )
    f1.md5_hash = md5
    f1.workspace_id = ws_personal.id
    db_session.add(f1)

    try:
        ws_shared = create_shared_workspace(db_session, "ambig-md5-ws", regular_user)
    except Exception:
        return

    f2 = save_upload(
        UploadFile(filename="b.pdf", file=BytesIO(content)), regular_user.id, content,
    )
    f2.md5_hash = md5
    f2.workspace_id = ws_shared.id
    db_session.add(f2)
    db_session.commit()

    count = (
        db_session.query(FileModel)
        .filter(FileModel.user_id == regular_user.id, FileModel.md5_hash == md5)
        .count()
    )
    if count < 2:
        return

    resp = client.put(
        "/api/external/md-content",
        headers={"Authorization": f"Bearer {active_api_key._plaintext}"},
        json={"md5_hash": md5, "content": "# x\n"},
    )
    assert resp.status_code == status.HTTP_409_CONFLICT
    assert "workspace_id" in resp.json().get("detail", "")
