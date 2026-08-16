# Copyright (c) 2026 徐泽宇
"""016 P2: library-report refresh/get API。

Authors:
    徐泽宇

Copyright:
    © 2026 徐泽宇
"""

from models.file import File as FileModel
from models.folder import Folder
from models.operation_log import OperationLog
from services.workspace_service import ensure_personal_workspace


def _add_source(db_session, user_id, ws_id, tmp_path, name, md5, *, folder_id=None):
    p = tmp_path / name
    p.write_text("x", encoding="utf-8")
    f = FileModel(
        user_id=user_id,
        workspace_id=ws_id,
        folder_id=folder_id,
        filename=name,
        original_name=name,
        file_path=str(p),
        file_size=1,
        mime_type="text/plain",
        md5_hash=md5,
        has_md=False,
        page_kind="source",
    )
    db_session.add(f)
    db_session.commit()
    db_session.refresh(f)
    return f


def test_sync_refresh_small_workspace(client, db_session, regular_user, jwt_token, tmp_path):
    personal = ensure_personal_workspace(db_session, regular_user)
    ws_id = personal.id
    h = {"Authorization": f"Bearer {jwt_token}"}

    _add_source(db_session, regular_user.id, ws_id, tmp_path, "lr_a.txt", "a" * 32)

    r = client.post("/api/knowledge-base/library-report/refresh", headers=h, params={"workspace_id": ws_id})
    assert r.status_code == 200
    data = r.json()
    assert data["status"] == "ready"
    assert data["payload"] is not None
    assert "meta" in data["payload"]
    assert "hub_files" in data["payload"]
    assert "surprising_links" in data["payload"]
    assert "governance" in data["payload"]

    r2 = client.post("/api/knowledge-base/library-report/refresh", headers=h, params={"workspace_id": ws_id})
    assert r2.status_code == 200
    assert r2.json()["status"] == "ready"


def test_get_library_report(client, db_session, regular_user, jwt_token, tmp_path):
    personal = ensure_personal_workspace(db_session, regular_user)
    ws_id = personal.id
    h = {"Authorization": f"Bearer {jwt_token}"}
    _add_source(db_session, regular_user.id, ws_id, tmp_path, "lr_get.txt", "b" * 32)
    client.post("/api/knowledge-base/library-report/refresh", headers=h, params={"workspace_id": ws_id})

    r = client.get("/api/knowledge-base/library-report", headers=h, params={"workspace_id": ws_id})
    assert r.status_code == 200
    data = r.json()
    assert data["status"] == "ready"
    assert data["payload"]["meta"]["workspace_id"] == ws_id


def test_surprising_cross_top_folder(client, db_session, regular_user, jwt_token, tmp_path):
    personal = ensure_personal_workspace(db_session, regular_user)
    ws_id = personal.id
    h = {"Authorization": f"Bearer {jwt_token}"}

    folder_a = Folder(name="top-a", parent_id=None, user_id=regular_user.id, workspace_id=ws_id)
    folder_b = Folder(name="top-b", parent_id=None, user_id=regular_user.id, workspace_id=ws_id)
    db_session.add_all([folder_a, folder_b])
    db_session.commit()
    db_session.refresh(folder_a)
    db_session.refresh(folder_b)

    fa = _add_source(
        db_session, regular_user.id, ws_id, tmp_path, "surp_a.txt", "c" * 32, folder_id=folder_a.id
    )
    fb = _add_source(
        db_session, regular_user.id, ws_id, tmp_path, "surp_b.txt", "d" * 32, folder_id=folder_b.id
    )
    client.put(f"/api/files/{fa.id}/md", headers=h, json={"content": f"link [[file:{fb.id}]]\n"})

    r = client.post("/api/knowledge-base/library-report/refresh", headers=h, params={"workspace_id": ws_id})
    assert r.status_code == 200
    surprising = r.json()["payload"]["surprising_links"]
    assert any(
        row["source_file_id"] == fa.id
        and row["target_file_id"] == fb.id
        and row["top_folder_a"] == folder_a.id
        and row["top_folder_b"] == folder_b.id
        and row["source_folder_path"] == "top-a"
        and row["target_folder_path"] == "top-b"
        for row in surprising
    )


def test_async_refresh_threshold(monkeypatch, client, db_session, regular_user, jwt_token, tmp_path):
    from services.library_report_service import run_refresh_job

    monkeypatch.setattr("services.library_report_service.LIBRARY_REPORT_SYNC_THRESHOLD", 1)
    monkeypatch.setattr("config.LIBRARY_REPORT_SYNC_THRESHOLD", 1)

    personal = ensure_personal_workspace(db_session, regular_user)
    ws_id = personal.id
    h = {"Authorization": f"Bearer {jwt_token}"}

    _add_source(db_session, regular_user.id, ws_id, tmp_path, "async1.txt", "e" * 32)
    _add_source(db_session, regular_user.id, ws_id, tmp_path, "async2.txt", "f" * 32)

    r = client.post("/api/knowledge-base/library-report/refresh", headers=h, params={"workspace_id": ws_id})
    assert r.status_code == 202
    data = r.json()
    assert data["status"] == "pending"
    assert data["report_id"] is not None

    # 测试库同事务：BackgroundTasks 的独立 Session 不可见未提交数据，在此模拟 job 完成
    run_refresh_job(db_session, data["report_id"])
    db_session.expire_all()

    r2 = client.get("/api/knowledge-base/library-report", headers=h, params={"workspace_id": ws_id})
    assert r2.status_code == 200
    assert r2.json()["status"] == "ready"
    assert r2.json()["payload"] is not None


def test_refresh_writes_operation_log(client, db_session, regular_user, jwt_token, tmp_path):
    personal = ensure_personal_workspace(db_session, regular_user)
    ws_id = personal.id
    h = {"Authorization": f"Bearer {jwt_token}"}
    _add_source(db_session, regular_user.id, ws_id, tmp_path, "log.txt", "0" * 32)

    before = (
        db_session.query(OperationLog)
        .filter(OperationLog.user_id == regular_user.id, OperationLog.action == "library_report_refresh")
        .count()
    )
    client.post("/api/knowledge-base/library-report/refresh", headers=h, params={"workspace_id": ws_id})
    after = (
        db_session.query(OperationLog)
        .filter(OperationLog.user_id == regular_user.id, OperationLog.action == "library_report_refresh")
        .count()
    )
    assert after == before + 1


def test_refresh_without_workspace_id(client, db_session, regular_user, jwt_token, tmp_path):
    """共享空间关闭时前端不传 workspace_id，应默认个人空间。"""
    personal = ensure_personal_workspace(db_session, regular_user)
    h = {"Authorization": f"Bearer {jwt_token}"}
    _add_source(db_session, regular_user.id, personal.id, tmp_path, "lr_no_ws.txt", "9" * 32)

    r = client.post("/api/knowledge-base/library-report/refresh", headers=h)
    assert r.status_code == 200
    data = r.json()
    assert data["status"] == "ready"
    assert data["payload"]["meta"]["workspace_id"] == personal.id

    r2 = client.get("/api/knowledge-base/library-report", headers=h)
    assert r2.status_code == 200
    assert r2.json()["payload"]["meta"]["workspace_id"] == personal.id


def test_surprising_excludes_uncategorized(client, db_session, regular_user, jwt_token, tmp_path):
    personal = ensure_personal_workspace(db_session, regular_user)
    ws_id = personal.id
    h = {"Authorization": f"Bearer {jwt_token}"}

    folder_a = Folder(name="only-top", parent_id=None, user_id=regular_user.id, workspace_id=ws_id)
    db_session.add(folder_a)
    db_session.commit()
    db_session.refresh(folder_a)

    fa = _add_source(
        db_session, regular_user.id, ws_id, tmp_path, "cat_a.txt", "1" * 32, folder_id=folder_a.id
    )
    fb = _add_source(db_session, regular_user.id, ws_id, tmp_path, "uncat_b.txt", "2" * 32)
    client.put(f"/api/files/{fa.id}/md", headers=h, json={"content": f"link [[file:{fb.id}]]\n"})

    r = client.post("/api/knowledge-base/library-report/refresh", headers=h, params={"workspace_id": ws_id})
    assert r.status_code == 200
    surprising = r.json()["payload"]["surprising_links"]
    assert not any(
        row["source_file_id"] == fa.id and row["target_file_id"] == fb.id for row in surprising
    )

def test_hub_files_degrees_file_direct_only(db_session, regular_user, tmp_path):
    """hub_files 出度/入度/得分仅统计 source↔source 的 [[file:id]] 直链，不含共引与主题页。"""
    from models.file import File as FileModel
    from services.library_report_service import _hub_files

    personal = ensure_personal_workspace(db_session, regular_user)
    ws_id = personal.id

    def _file(name: str, md5: str) -> FileModel:
        p = tmp_path / name
        p.write_text("x", encoding="utf-8")
        f = FileModel(
            user_id=regular_user.id,
            workspace_id=ws_id,
            filename=name,
            original_name=name,
            file_path=str(p),
            file_size=1,
            mime_type="text/plain",
            md5_hash=md5,
            has_md=True,
            page_kind="source",
        )
        db_session.add(f)
        db_session.commit()
        db_session.refresh(f)
        return f

    hub = _file("hub.txt", "a" * 32)
    peer_a = _file("peer_a.txt", "b" * 32)
    peer_b = _file("peer_b.txt", "c" * 32)
    concept = _file("concept.md", "d" * 32)
    concept.page_kind = "concept"
    db_session.commit()

    allowed = {hub.id, peer_a.id, peer_b.id, concept.id}
    links = [
        {"source": hub.id, "target": peer_a.id, "edge_type": "file_direct"},
        {"source": hub.id, "target": peer_b.id, "edge_type": "file_direct"},
        {"source": hub.id, "target": concept.id, "edge_type": "file_direct"},
        {"source": hub.id, "target": concept.id, "edge_type": "wiki_topic", "wiki_slug": "topic-x"},
        {"source": peer_a.id, "target": peer_b.id, "edge_type": "wiki_coref", "wiki_slug": "shared"},
        {"source": peer_b.id, "target": hub.id, "edge_type": "file_direct"},
    ]

    rows = _hub_files(links, db_session, allowed)
    by_id = {row["file_id"]: row for row in rows}

    assert by_id[hub.id]["out_degree"] == 2
    assert by_id[hub.id]["in_degree"] == 1
    assert by_id[hub.id]["coref_count"] == 0
    assert by_id[hub.id]["score"] == 3.0

    assert by_id[peer_a.id]["out_degree"] == 0
    assert by_id[peer_a.id]["in_degree"] == 1
    assert by_id[peer_a.id]["coref_count"] == 0
    assert by_id[peer_a.id]["score"] == 1.0

    assert by_id[peer_b.id]["out_degree"] == 1
    assert by_id[peer_b.id]["in_degree"] == 1
    assert by_id[peer_b.id]["coref_count"] == 0
    assert by_id[peer_b.id]["score"] == 2.0
    assert concept.id not in by_id


def test_hub_files_excludes_theme_pages(db_session, regular_user, tmp_path):
    """hub_files 排名不含主题页（entity/concept/synthesis）。"""
    from models.file import File as FileModel
    from services.library_report_service import _hub_files

    personal = ensure_personal_workspace(db_session, regular_user)
    ws_id = personal.id

    def _file(name: str, md5: str, *, page_kind: str = "source") -> FileModel:
        p = tmp_path / name
        p.write_text("x", encoding="utf-8")
        f = FileModel(
            user_id=regular_user.id,
            workspace_id=ws_id,
            filename=name,
            original_name=name,
            file_path=str(p),
            file_size=1,
            mime_type="text/plain",
            md5_hash=md5,
            has_md=True,
            page_kind=page_kind,
        )
        db_session.add(f)
        db_session.commit()
        db_session.refresh(f)
        return f

    source = _file("source.txt", "f" * 32)
    topic = _file("topic.md", "e" * 32, page_kind="concept")
    allowed = {source.id, topic.id}
    links = [
        {"source": source.id, "target": topic.id, "edge_type": "file_direct"},
        {"source": topic.id, "target": source.id, "edge_type": "file_direct"},
    ]

    rows = _hub_files(links, db_session, allowed)
    ids = {row["file_id"] for row in rows}

    assert len(rows) == 0
    assert source.id not in ids
    assert topic.id not in ids


def test_hub_wiki_slugs_includes_file_id_when_theme_page_exists(db_session, regular_user, tmp_path):
    """hub_wiki_slugs 在主题页已存在时返回 file_id，供前端点击预览。"""
    from services.library_report_service import _hub_wiki_slugs

    personal = ensure_personal_workspace(db_session, regular_user)
    ws_id = personal.id

    p = tmp_path / "topic.md"
    p.write_text("# topic", encoding="utf-8")
    topic = FileModel(
        user_id=regular_user.id,
        workspace_id=ws_id,
        filename="topic.md",
        original_name="抗衰老资料",
        file_path=str(p),
        file_size=8,
        mime_type="text/markdown",
        md5_hash="e" * 32,
        has_md=True,
        page_kind="synthesis",
        wiki_slug="抗衰老资料",
    )
    db_session.add(topic)
    db_session.commit()
    db_session.refresh(topic)

    source_p = tmp_path / "src.txt"
    source_p.write_text("x", encoding="utf-8")
    source = FileModel(
        user_id=regular_user.id,
        workspace_id=ws_id,
        filename="src.txt",
        original_name="src.txt",
        file_path=str(source_p),
        file_size=1,
        mime_type="text/plain",
        md5_hash="f" * 32,
        has_md=False,
        page_kind="source",
    )
    db_session.add(source)
    db_session.commit()
    db_session.refresh(source)

    allowed = {topic.id, source.id}
    links = [
        {"source": source.id, "target": topic.id, "edge_type": "wiki_topic", "wiki_slug": "抗衰老资料"},
        {"source": source.id, "target": 0, "edge_type": "wiki_topic", "wiki_slug": "待编译主题"},
    ]

    rows = _hub_wiki_slugs(links, db_session, ws_id, allowed)
    by_slug = {row["slug"]: row for row in rows}

    assert by_slug["抗衰老资料"]["file_id"] == topic.id
    assert by_slug["抗衰老资料"]["page_kind"] == "synthesis"
    assert by_slug["待编译主题"]["file_id"] is None

