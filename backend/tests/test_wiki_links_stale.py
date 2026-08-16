# Copyright (c) 2026 徐泽宇
"""016 Sprint D: wiki_links_stale 检测。

Authors:
    徐泽宇

Copyright:
    © 2026 徐泽宇
"""

from models.file import File as FileModel
from services.md_wiki_link_service import rebuild_wiki_links_for_file, wiki_links_stale_for_file
from services.workspace_service import ensure_personal_workspace


def test_wiki_links_stale_after_md_change_without_rebuild(
    client, db_session, regular_user, jwt_token, tmp_path
):
    personal = ensure_personal_workspace(db_session, regular_user)
    ws_id = personal.id
    h = {"Authorization": f"Bearer {jwt_token}"}

    p = tmp_path / "stale.txt"
    p.write_text("x", encoding="utf-8")
    f = FileModel(
        user_id=regular_user.id,
        workspace_id=ws_id,
        filename="stale.txt",
        original_name="stale.txt",
        file_path=str(p),
        file_size=1,
        mime_type="text/plain",
        md5_hash="a" * 32,
        has_md=False,
        page_kind="source",
    )
    db_session.add(f)
    db_session.commit()
    db_session.refresh(f)

    client.put(f"/api/files/{f.id}/md", headers=h, json={"content": "[[wiki:alpha]]\n"})
    rebuild_wiki_links_for_file(db_session, regular_user, f.id)
    db_session.commit()
    assert wiki_links_stale_for_file(db_session, f.id) is False

    with open(f.md_file_path, "w", encoding="utf-8") as fh:
        fh.write("[[wiki:beta]]\n")
    assert wiki_links_stale_for_file(db_session, f.id) is True

    r = client.get(f"/api/files/{f.id}", headers=h, params={"include_wiki_stale": True})
    assert r.status_code == 200
    assert r.json()["wiki_links_stale"] is True


def test_wiki_links_not_stale_when_content_hash_null(
    client, db_session, regular_user, jwt_token, tmp_path
):
    from models.file_wiki_link import FileWikiLink

    personal = ensure_personal_workspace(db_session, regular_user)
    ws_id = personal.id
    h = {"Authorization": f"Bearer {jwt_token}"}

    p = tmp_path / "nullhash.txt"
    p.write_text("x", encoding="utf-8")
    f = FileModel(
        user_id=regular_user.id,
        workspace_id=ws_id,
        filename="nullhash.txt",
        original_name="nullhash.txt",
        file_path=str(p),
        file_size=1,
        mime_type="text/plain",
        md5_hash="b" * 32,
        has_md=False,
        page_kind="source",
    )
    db_session.add(f)
    db_session.commit()
    db_session.refresh(f)

    client.put(f"/api/files/{f.id}/md", headers=h, json={"content": "[[wiki:gamma]]\n"})
    rebuild_wiki_links_for_file(db_session, regular_user, f.id)
    db_session.query(FileWikiLink).filter(FileWikiLink.source_file_id == f.id).update(
        {"content_hash": None}
    )
    db_session.commit()

    assert wiki_links_stale_for_file(db_session, f.id) is False
