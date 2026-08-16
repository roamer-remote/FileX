# Copyright (c) 2026 徐泽宇
"""GET /api/external/files-awaiting-ai：无标签且无 MD 笔记的文件 Markdown 列表。

Authors:
    徐泽宇

Copyright:
    © 2026 徐泽宇
"""
import hashlib

import pytest
from fastapi import status

from models.file import File as FileModel
from models.tag import Tag, file_tags
from sqlalchemy import insert


@pytest.fixture
def _three_files(db_session, regular_user):
    uid = regular_user.id
    rows = []
    for i, (name, has_md, tag_names) in enumerate(
        [
            ("pending-a.txt", False, []),
            ("has-tags.txt", False, ["t1"]),
            ("has-md.txt", True, []),
        ]
    ):
        f = FileModel(
            filename=f"store-{i}",
            original_name=name,
            file_path=f"/tmp/f{i}",
            file_size=10,
            mime_type="text/plain",
            user_id=uid,
            has_md=has_md,
            md5_hash=hashlib.md5(f"body{i}".encode()).hexdigest(),
        )
        db_session.add(f)
        db_session.flush()
        rows.append(f)
        for tn in tag_names:
            t = db_session.query(Tag).filter(Tag.user_id == uid, Tag.name == tn).first()
            if not t:
                t = Tag(user_id=uid, name=tn)
                db_session.add(t)
                db_session.flush()
            db_session.execute(insert(file_tags).values(file_id=f.id, tag_id=t.id))
    db_session.commit()
    for r in rows:
        db_session.refresh(r)
    return rows


def test_files_awaiting_ai_markdown_only_pending(client, active_api_key, db_session, regular_user, _three_files):
    resp = client.get(
        "/api/external/files-awaiting-ai",
        headers={"Authorization": f"Bearer {active_api_key._plaintext}"},
    )
    assert resp.status_code == status.HTTP_200_OK
    assert "text/markdown" in resp.headers.get("content-type", "")
    body = resp.text
    assert "pending-a.txt" in body
    assert "has-tags.txt" not in body
    assert "has-md.txt" not in body
    pending = next(f for f in _three_files if f.original_name == "pending-a.txt")
    assert str(pending.id) in body


def test_files_awaiting_ai_jwt_rejected(client, jwt_token):
    resp = client.get(
        "/api/external/files-awaiting-ai",
        headers={"Authorization": f"Bearer {jwt_token}"},
    )
    assert resp.status_code == status.HTTP_401_UNAUTHORIZED
