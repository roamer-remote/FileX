# Copyright (c) 2026 徐泽宇
"""主题页 wiki_slug 重命名 API 测试。"""

from unittest.mock import patch

from services.md_wiki_link_scan import replace_wiki_slug_in_markdown


def test_replace_wiki_slug_in_markdown():
    text = "见 [[wiki:old-topic]] 与 [[显示|wiki:old-topic]]\n"
    new_text, n = replace_wiki_slug_in_markdown(text, "old-topic", "new-topic")
    assert n == 2
    assert "[[wiki:new-topic]]" in new_text
    assert "[[显示|wiki:new-topic]]" in new_text
    assert "old-topic" not in new_text


@patch("services.kb_index_service.enqueue_index")
def test_patch_wiki_page_slug(mock_enqueue, client, db_session, regular_user, jwt_token):
    mock_enqueue.return_value = None
    h = {"Authorization": f"Bearer {jwt_token}"}

    created = client.post(
        "/api/knowledge-base/wiki/pages",
        headers=h,
        json={
            "title": "Old Title",
            "wiki_slug": "rename-me",
            "page_kind": "concept",
            "markdown": "# Old\n",
        },
    )
    assert created.status_code == 201
    file_id = created.json()["file"]["id"]

    r = client.patch(
        f"/api/knowledge-base/wiki/pages/{file_id}",
        headers=h,
        json={"wiki_slug": "renamed-topic"},
    )
    assert r.status_code == 200
    assert r.json()["wiki_slug"] == "renamed-topic"

    listed = client.get("/api/knowledge-base/wiki/pages", headers=h)
    slugs = [i["wiki_slug"] for i in listed.json()["items"]]
    assert "renamed-topic" in slugs
    assert "rename-me" not in slugs
