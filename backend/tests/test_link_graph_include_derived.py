# Copyright (c) 2026 徐泽宇
"""016 Sprint D: link-graph include_derived 参数。

Authors:
    徐泽宇

Copyright:
    © 2026 徐泽宇
"""

from models.file import File as FileModel
from services.workspace_service import ensure_personal_workspace


def test_link_graph_include_derived(client, db_session, regular_user, jwt_token, tmp_path):
    personal = ensure_personal_workspace(db_session, regular_user)
    ws_id = personal.id
    h = {"Authorization": f"Bearer {jwt_token}"}

    p = tmp_path / "derived_src.txt"
    p.write_text("x", encoding="utf-8")
    f = FileModel(
        user_id=regular_user.id,
        workspace_id=ws_id,
        filename="derived_src.txt",
        original_name="derived_src.txt",
        file_path=str(p),
        file_size=1,
        mime_type="text/plain",
        md5_hash="a" * 32,
        has_md=True,
        extract_status="done",
        page_kind="source",
    )
    db_session.add(f)
    db_session.commit()
    db_session.refresh(f)

    client.put(f"/api/files/{f.id}/md", headers=h, json={"content": "# notes\n"})

    base = client.get("/api/knowledge-base/link-graph", headers=h).json()
    assert not any(e.get("edge_type") == "derived_from" for e in base["links"])

    derived = client.get(
        "/api/knowledge-base/link-graph",
        headers=h,
        params={"include_derived": True},
    ).json()
    d_edges = [e for e in derived["links"] if e.get("edge_type") == "derived_from"]
    assert len(d_edges) >= 1
    assert any(int(e["source"]) == f.id and int(e["target"]) == f.id for e in d_edges)
