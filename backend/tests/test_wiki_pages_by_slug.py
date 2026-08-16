# Copyright (c) 2026 徐泽宇
"""wiki pages by slug 相关测试模块。

Authors:
    徐泽宇
"""

from unittest.mock import patch

from models.file import File as FileModel


@patch("services.kb_index_service.enqueue_index")
def test_wiki_page_by_slug(mock_enqueue, client, db_session, regular_user, jwt_token, tmp_path):
    mock_enqueue.return_value = None
    h = {"Authorization": f"Bearer {jwt_token}"}
    r404 = client.get("/api/knowledge-base/wiki/pages/by-slug/no-such-slug", headers=h)
    assert r404.status_code == 404

    created = client.post(
        "/api/knowledge-base/wiki/pages",
        headers=h,
        json={
            "title": "By Slug",
            "wiki_slug": "by-slug-test",
            "page_kind": "concept",
            "markdown": "# By Slug\n",
        },
    )
    assert created.status_code == 201

    r = client.get("/api/knowledge-base/wiki/pages/by-slug/by-slug-test", headers=h)
    assert r.status_code == 200
    data = r.json()
    assert data["wiki_slug"] == "by-slug-test"
    assert data["page_kind"] == "concept"
    assert data["file_id"] > 0


@patch("services.kb_index_service.enqueue_index")
def test_wiki_page_by_slug_chinese(mock_enqueue, client, db_session, regular_user, jwt_token):
    mock_enqueue.return_value = None
    h = {"Authorization": f"Bearer {jwt_token}"}
    slug = "重要人才"
    created = client.post(
        "/api/knowledge-base/wiki/pages",
        headers=h,
        json={
            "title": "重要人才",
            "wiki_slug": slug,
            "page_kind": "concept",
            "markdown": "# 重要人才\n",
        },
    )
    assert created.status_code == 201

    from urllib.parse import quote

    r = client.get(f"/api/knowledge-base/wiki/pages/by-slug/{quote(slug)}", headers=h)
    assert r.status_code == 200
    assert r.json()["wiki_slug"] == slug
