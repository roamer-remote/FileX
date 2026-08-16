# Copyright (c) 2026 徐泽宇
"""GET /api/files/stats

Authors:
    徐泽宇

Copyright:
    © 2026 徐泽宇
"""
from starlette import status

from models.file import File as FileModel
from models.tag import Tag


def test_file_stats_type_buckets(client, db_session, regular_user, jwt_token):
    """各已知扩展名应单独计入对应类型，而非全部归入 other。"""
    uid = regular_user.id
    samples = [
        ("a.pdf", "application/pdf"),
        ("b.png", "image/png"),
        ("c.docx", "application/vnd.openxmlformats-officedocument.wordprocessingml.document"),
        ("d.md", "text/markdown"),
        ("e.pptx", "application/vnd.openxmlformats-officedocument.presentationml.presentation"),
    ]
    for i, (name, mime) in enumerate(samples):
        db_session.add(
            FileModel(
                user_id=uid,
                filename=f"f{i}.bin",
                original_name=name,
                file_path=f"/tmp/type-{i}",
                file_size=1,
                mime_type=mime,
                md5_hash=f"{i:02d}" * 16,
                has_md=False,
            )
        )
    db_session.commit()

    data = client.get("/api/files/stats", headers={"Authorization": f"Bearer {jwt_token}"}).json()
    keys = {item["key"] for item in data["file_types"]}
    assert keys >= {"pdf", "img", "docx", "md", "pptx"}


def test_file_stats_returns_shape(client, jwt_token):

    resp = client.get("/api/files/stats", headers={"Authorization": f"Bearer {jwt_token}"})
    assert resp.status_code == status.HTTP_200_OK
    data = resp.json()
    assert "total_files" in data
    assert "file_types" in data
    assert isinstance(data["file_types"], list)


def test_file_stats_tag_count_matches_list_sum(client, db_session, regular_user, jwt_token):
    """侧栏 tag_count 应等于文件列表各条 tags 长度之和，不含未挂文件的孤儿标签。"""
    uid = regular_user.id
    for i, name in enumerate(("a.txt", "b.txt")):
        db_session.add(
            FileModel(
                user_id=uid,
                filename=f"f{i}.bin",
                original_name=name,
                file_path=f"/tmp/stats-{i}",
                file_size=1,
                mime_type="text/plain",
                md5_hash=f"{i}" * 32,
                has_md=False,
            )
        )
    for n in ("orphan-1", "orphan-2"):
        db_session.add(Tag(user_id=uid, name=n))
    db_session.commit()

    h = {"Authorization": f"Bearer {jwt_token}"}
    assert client.get("/api/files/stats", headers=h).json()["tag_count"] == 0

    files = client.get("/api/files", headers=h).json()["items"]
    assert sum(len(it.get("tags") or []) for it in files) == 0

    f0_id = files[0]["id"]
    assert (
        client.put(f"/api/files/{f0_id}/tags", headers=h, json={"tags": ["alpha", "beta"]}).status_code
        == 200
    )
    assert (
        client.put(f"/api/files/{files[1]['id']}/tags", headers=h, json={"tags": ["alpha"]}).status_code
        == 200
    )

    items = client.get("/api/files", headers=h).json()["items"]
    list_sum = sum(len(it.get("tags") or []) for it in items)
    assert list_sum == 3

    stats = client.get("/api/files/stats", headers=h).json()
    assert stats["tag_count"] == list_sum
