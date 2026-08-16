# Copyright (c) 2026 徐泽宇
"""wiki candidates 相关测试模块。

Authors:
    徐泽宇
"""

from unittest.mock import patch

from models.file import File as FileModel


def _source_file(db_session, user, tmp_path, name: str, md5: str) -> FileModel:
    path = tmp_path / name
    path.write_text("x", encoding="utf-8")
    rec = FileModel(
        user_id=user.id,
        filename=name,
        original_name=name,
        file_path=str(path),
        file_size=1,
        mime_type="application/octet-stream",
        md5_hash=md5,
        has_md=False,
    )
    db_session.add(rec)
    db_session.commit()
    db_session.refresh(rec)
    return rec


@patch("services.kb_index_service.enqueue_index")
def test_wiki_candidates_min_sources(mock_enqueue, client, db_session, regular_user, jwt_token, tmp_path):
    mock_enqueue.return_value = None
    h = {"Authorization": f"Bearer {jwt_token}"}
    a = _source_file(db_session, regular_user, tmp_path, "a.bin", "a" * 32)
    b = _source_file(db_session, regular_user, tmp_path, "b.bin", "b" * 32)
    client.put(f"/api/files/{a.id}/md", headers=h, json={"content": "[[wiki:compile-me]]\n"})
    client.put(f"/api/files/{b.id}/md", headers=h, json={"content": "also [[wiki:compile-me]]\n"})

    r = client.get("/api/knowledge-base/wiki/candidates", headers=h, params={"min_sources": 2})
    assert r.status_code == 200
    slugs = [i["wiki_slug"] for i in r.json()["items"]]
    assert "compile-me" in slugs

    r2 = client.get("/api/knowledge-base/wiki/candidates", headers=h, params={"min_sources": 3})
    assert "compile-me" not in [i["wiki_slug"] for i in r2.json()["items"]]


@patch("services.kb_index_service.enqueue_index")
def test_lint_pending_concepts(mock_enqueue, client, db_session, regular_user, jwt_token, tmp_path):
    mock_enqueue.return_value = None
    h = {"Authorization": f"Bearer {jwt_token}"}
    a = _source_file(db_session, regular_user, tmp_path, "c.bin", "c" * 32)
    b = _source_file(db_session, regular_user, tmp_path, "d.bin", "d" * 32)
    client.put(f"/api/files/{a.id}/md", headers=h, json={"content": "[[wiki:lint-pending]]\n"})
    client.put(f"/api/files/{b.id}/md", headers=h, json={"content": "[[wiki:lint-pending]]\n"})

    r = client.post("/api/knowledge-base/lint", headers=h)
    assert r.status_code == 200
    pending = r.json().get("pending_concepts") or []
    assert any(p["wiki_slug"] == "lint-pending" for p in pending)
