# Copyright (c) 2026 徐泽宇
"""md tag anchor api 相关测试模块。

Authors:
    徐泽宇
"""

from unittest.mock import patch

from models.file import File as FileModel
from models.kb_index_job import KbIndexJob


def test_put_tags_creates_tag_anchors_from_sidecar_note(client, db_session, regular_user, jwt_token, tmp_path):
    """锚点来自资料笔记，与主文件类型无关。"""
    p = tmp_path / "doc.bin"
    p.write_text("binary", encoding="utf-8")
    f = FileModel(
        user_id=regular_user.id,
        filename="d.bin",
        original_name="doc.bin",
        file_path=str(p),
        file_size=p.stat().st_size,
        mime_type="application/octet-stream",
        md5_hash="e" * 32,
        has_md=False,
    )
    db_session.add(f)
    db_session.commit()
    db_session.refresh(f)

    h = {"Authorization": f"Bearer {jwt_token}"}
    r_md = client.put(
        f"/api/files/{f.id}/md",
        headers=h,
        json={"content": "# T\n\nalpha beta and alpha tail.\n"},
    )
    assert r_md.status_code == 200

    r_tag = client.put(f"/api/files/{f.id}/tags", headers=h, json={"tags": ["alpha"]})
    assert r_tag.status_code == 200

    r2 = client.get("/api/files", headers=h)
    assert r2.status_code == 200
    item = next(it for it in r2.json()["items"] if it["id"] == f.id)
    anchors = item["tag_anchors"]
    assert len(anchors) == 2
    assert all(a["tag"] == "alpha" for a in anchors)
    assert {a["occurrence_index"] for a in anchors} == {1, 2}
    for a in anchors:
        assert a["anchor_id"].startswith(f"fba-{f.id}-")
        assert a["end_offset"] > a["start_offset"]


def test_plaintext_file_tags_no_anchors_without_note(client, db_session, regular_user, jwt_token, tmp_path):
    p = tmp_path / "t.txt"
    p.write_text("alpha here", encoding="utf-8")
    f = FileModel(
        user_id=regular_user.id,
        filename="t.bin",
        original_name="t.txt",
        file_path=str(p),
        file_size=p.stat().st_size,
        mime_type="text/plain",
        md5_hash="d" * 32,
        has_md=False,
    )
    db_session.add(f)
    db_session.commit()
    db_session.refresh(f)
    h = {"Authorization": f"Bearer {jwt_token}"}
    assert client.put(f"/api/files/{f.id}/tags", headers=h, json={"tags": ["alpha"]}).status_code == 200
    r = client.get("/api/files", headers=h)
    item = next(it for it in r.json()["items"] if it["id"] == f.id)
    assert item["tag_anchors"] == []


def test_put_md_rebuilds_tag_anchors(client, db_session, regular_user, jwt_token, tmp_path):
    p = tmp_path / "y.bin"
    p.write_text("y", encoding="utf-8")
    f = FileModel(
        user_id=regular_user.id,
        filename="y.bin",
        original_name="y.bin",
        file_path=str(p),
        file_size=p.stat().st_size,
        mime_type="application/octet-stream",
        md5_hash="f" * 32,
        has_md=False,
    )
    db_session.add(f)
    db_session.commit()
    db_session.refresh(f)
    h = {"Authorization": f"Bearer {jwt_token}"}

    assert (
        client.put(f"/api/files/{f.id}/md", headers=h, json={"content": "only one alpha here\n"}).status_code == 200
    )
    assert client.put(f"/api/files/{f.id}/tags", headers=h, json={"tags": ["alpha"]}).status_code == 200
    item1 = next(it for it in client.get("/api/files", headers=h).json()["items"] if it["id"] == f.id)
    assert len(item1["tag_anchors"]) == 1

    assert (
        client.put(f"/api/files/{f.id}/md", headers=h, json={"content": "alpha and alpha again\n"}).status_code
        == 200
    )
    item2 = next(it for it in client.get("/api/files", headers=h).json()["items"] if it["id"] == f.id)
    assert len(item2["tag_anchors"]) == 2


@patch("services.md_note_service.publish_md_note_index_job")
def test_put_md_unchanged_skips_vector_reindex(mock_publish, client, db_session, regular_user, jwt_token, tmp_path):
    p = tmp_path / "note.bin"
    p.write_text("bin", encoding="utf-8")
    f = FileModel(
        user_id=regular_user.id,
        filename="note.bin",
        original_name="note.bin",
        file_path=str(p),
        file_size=p.stat().st_size,
        mime_type="application/octet-stream",
        md5_hash="a" * 32,
        has_md=False,
    )
    db_session.add(f)
    db_session.commit()
    db_session.refresh(f)
    h = {"Authorization": f"Bearer {jwt_token}"}
    content = "# unchanged note\n\nbody\n"

    r1 = client.put(f"/api/files/{f.id}/md", headers=h, json={"content": content})
    assert r1.status_code == 200
    jobs_after_first = db_session.query(KbIndexJob).filter(KbIndexJob.file_id == f.id).count()
    assert jobs_after_first >= 1
    mock_publish.reset_mock()

    r2 = client.put(f"/api/files/{f.id}/md", headers=h, json={"content": content})
    assert r2.status_code == 200
    assert r2.json().get("unchanged") is True
    assert db_session.query(KbIndexJob).filter(KbIndexJob.file_id == f.id).count() == jobs_after_first
    mock_publish.assert_not_called()
    db_session.refresh(f)
    assert f.index_status == "pending"
