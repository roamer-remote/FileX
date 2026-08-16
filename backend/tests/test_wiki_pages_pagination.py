# Copyright (c) 2026 徐泽宇
"""GET /wiki/pages 服务端分页测试。"""

from unittest.mock import patch


@patch("services.kb_index_service.enqueue_index")
def test_wiki_pages_pagination(mock_enqueue, client, jwt_token):
    mock_enqueue.return_value = None
    h = {"Authorization": f"Bearer {jwt_token}"}

    for i in range(3):
        r = client.post(
            "/api/knowledge-base/wiki/pages",
            headers=h,
            json={
                "title": f"Page {i}",
                "wiki_slug": f"pag-test-{i}",
                "page_kind": "concept",
                "markdown": f"# Page {i}\n",
            },
        )
        assert r.status_code == 201

    page1 = client.get("/api/knowledge-base/wiki/pages", headers=h, params={"page": 1, "page_size": 2})
    assert page1.status_code == 200
    data1 = page1.json()
    assert data1["total"] >= 3
    assert data1["page"] == 1
    assert data1["page_size"] == 2
    assert len(data1["items"]) == 2

    page2 = client.get("/api/knowledge-base/wiki/pages", headers=h, params={"page": 2, "page_size": 2})
    assert page2.status_code == 200
    data2 = page2.json()
    assert len(data2["items"]) >= 1
    ids1 = {item["file_id"] for item in data1["items"]}
    ids2 = {item["file_id"] for item in data2["items"]}
    assert ids1.isdisjoint(ids2)


@patch("services.kb_index_service.enqueue_index")
def test_wiki_pages_pagination_empty_page(mock_enqueue, client, jwt_token):
    mock_enqueue.return_value = None
    h = {"Authorization": f"Bearer {jwt_token}"}
    r = client.get("/api/knowledge-base/wiki/pages", headers=h, params={"page": 999, "page_size": 20})
    assert r.status_code == 200
    data = r.json()
    assert data["items"] == []
    assert data["page"] == 999


@patch("services.kb_index_service.enqueue_index")
def test_wiki_pages_pagination_workspace_isolated_total(mock_enqueue, client, db_session, regular_user, jwt_token):
    """ACL/空间隔离：各 workspace 的 total 与 items 仅含该空间可见主题页。"""
    mock_enqueue.return_value = None
    from services.workspace_service import create_shared_workspace, ensure_personal_workspace

    personal = ensure_personal_workspace(db_session, regular_user)
    shared = create_shared_workspace(db_session, name="wiki-pag-acl", owner=regular_user)
    h = {"Authorization": f"Bearer {jwt_token}"}

    personal_created = client.post(
        "/api/knowledge-base/wiki/pages",
        headers=h,
        json={
            "title": "Personal Topic",
            "wiki_slug": "personal-topic-acl",
            "page_kind": "concept",
            "markdown": "# Personal\n",
            "workspace_id": personal.id,
        },
    )
    assert personal_created.status_code == 201
    personal_id = personal_created.json()["file"]["id"]

    shared_created = client.post(
        "/api/knowledge-base/wiki/pages",
        headers=h,
        json={
            "title": "Shared Topic",
            "wiki_slug": "shared-topic-acl",
            "page_kind": "concept",
            "markdown": "# Shared\n",
            "workspace_id": shared.id,
        },
    )
    assert shared_created.status_code == 201
    shared_id = shared_created.json()["file"]["id"]

    personal_list = client.get(
        "/api/knowledge-base/wiki/pages",
        headers=h,
        params={"workspace_id": personal.id, "page": 1, "page_size": 20},
    )
    assert personal_list.status_code == 200
    pdata = personal_list.json()
    assert pdata["total"] == 1
    assert len(pdata["items"]) == 1
    assert pdata["items"][0]["file_id"] == personal_id

    shared_list = client.get(
        "/api/knowledge-base/wiki/pages",
        headers=h,
        params={"workspace_id": shared.id, "page": 1, "page_size": 20},
    )
    assert shared_list.status_code == 200
    sdata = shared_list.json()
    assert sdata["total"] == 1
    assert len(sdata["items"]) == 1
    assert sdata["items"][0]["file_id"] == shared_id


@patch("services.kb_index_service.enqueue_index")
def test_wiki_pages_pagination_acl_shared_disabled_empty(mock_enqueue, client, db_session, regular_user, jwt_token):
    """共享空间功能关闭时，共享库主题页 ACL 过滤后 total=0。"""
    mock_enqueue.return_value = None
    from services.system_setting_service import KEY_SHARED_WORKSPACES_ENABLED, update_settings
    from services.workspace_service import create_shared_workspace

    shared = create_shared_workspace(db_session, name="wiki-pag-disabled", owner=regular_user)
    h = {"Authorization": f"Bearer {jwt_token}"}

    created = client.post(
        "/api/knowledge-base/wiki/pages",
        headers=h,
        json={
            "title": "Hidden When Off",
            "wiki_slug": "hidden-when-off",
            "page_kind": "concept",
            "markdown": "# Hidden\n",
            "workspace_id": shared.id,
        },
    )
    assert created.status_code == 201

    before = client.get(
        "/api/knowledge-base/wiki/pages",
        headers=h,
        params={"workspace_id": shared.id, "page": 1, "page_size": 20},
    )
    assert before.status_code == 200
    assert before.json()["total"] == 1

    update_settings(db_session, {KEY_SHARED_WORKSPACES_ENABLED: "false"})

    after = client.get(
        "/api/knowledge-base/wiki/pages",
        headers=h,
        params={"workspace_id": shared.id, "page": 1, "page_size": 20},
    )
    assert after.status_code == 200
    adata = after.json()
    assert adata["total"] == 0
    assert adata["items"] == []
