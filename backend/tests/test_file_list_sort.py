# Copyright (c) 2026 徐泽宇
"""文件列表按最后更新时间排序；标签变更刷新 updated_at。

Authors:
    徐泽宇

Copyright:
    © 2026 徐泽宇
"""

from datetime import datetime, timedelta, timezone

from fastapi import status

from models.file import File as FileModel


def _iso_parse(s: str) -> datetime:
    return datetime.fromisoformat(s.replace("Z", "+00:00"))


def test_put_tags_bumps_updated_at_and_list_order(client, db_session, regular_user, jwt_token):
    """先建两文件（f2 更新），默认列表 f2 在前；给 f1 打标签后 f1 应排到最前。"""
    base = datetime(2025, 1, 1, 12, 0, 0, tzinfo=timezone.utc)
    f1 = FileModel(
        user_id=regular_user.id,
        filename="old.bin",
        original_name="older.txt",
        file_path="/tmp/a1",
        file_size=1,
        mime_type="text/plain",
        md5_hash="a" * 32,
        has_md=False,
        created_at=base,
        updated_at=base,
    )
    f2 = FileModel(
        user_id=regular_user.id,
        filename="new.bin",
        original_name="newer.txt",
        file_path="/tmp/a2",
        file_size=1,
        mime_type="text/plain",
        md5_hash="b" * 32,
        has_md=False,
        created_at=base + timedelta(hours=1),
        updated_at=base + timedelta(hours=1),
    )
    db_session.add_all([f1, f2])
    db_session.commit()
    db_session.refresh(f1)
    db_session.refresh(f2)

    h = {"Authorization": f"Bearer {jwt_token}"}

    r0 = client.get("/api/files", headers=h)
    assert r0.status_code == 200
    ids0 = [it["id"] for it in r0.json()["items"]]
    assert ids0[0] == f2.id, "默认按更新时间倒序，新建较新的 f2 应在首行"

    u_before = _iso_parse(next(it["updated_at"] for it in r0.json()["items"] if it["id"] == f1.id))

    r_tag = client.put(
        f"/api/files/{f1.id}/tags",
        headers=h,
        json={"tags": ["alpha"]},
    )
    assert r_tag.status_code == 200

    r1 = client.get("/api/files", headers=h)
    assert r1.status_code == 200
    payload = r1.json()["items"]
    ids1 = [it["id"] for it in payload]
    assert ids1[0] == f1.id, "更新标签后 f1 的更新时间应最新，排在首位"

    u_after = _iso_parse(next(it["updated_at"] for it in payload if it["id"] == f1.id))
    assert u_after >= u_before

    r_asc = client.get("/api/files", params={"sort_time": "asc"}, headers=h)
    assert r_asc.status_code == 200
    ids_asc = [it["id"] for it in r_asc.json()["items"]]
    assert ids_asc[0] == f2.id, "升序时较旧的 f2 应在首行"


def test_sort_name_orders_by_original_name(client, db_session, regular_user, jwt_token):
    """sort_name 按 original_name 忽略大小写排序（全库，非仅当前页）。"""
    base = datetime(2025, 1, 1, 12, 0, 0, tzinfo=timezone.utc)
    f_a = FileModel(
        user_id=regular_user.id,
        filename="z.bin",
        original_name="RAG周报-2026-06-26.html",
        file_path="/tmp/z",
        file_size=1,
        mime_type="text/html",
        md5_hash="c" * 32,
        has_md=False,
        created_at=base,
        updated_at=base + timedelta(hours=2),
    )
    f_b = FileModel(
        user_id=regular_user.id,
        filename="a.bin",
        original_name="RAG周报-2026-06-14.pdf",
        file_path="/tmp/a",
        file_size=1,
        mime_type="application/pdf",
        md5_hash="d" * 32,
        has_md=False,
        created_at=base,
        updated_at=base + timedelta(hours=1),
    )
    f_c = FileModel(
        user_id=regular_user.id,
        filename="m.bin",
        original_name="RAG周报-2026-06-19.html",
        file_path="/tmp/m",
        file_size=1,
        mime_type="text/html",
        md5_hash="e" * 32,
        has_md=False,
        created_at=base,
        updated_at=base,
    )
    db_session.add_all([f_a, f_b, f_c])
    db_session.commit()

    h = {"Authorization": f"Bearer {jwt_token}"}

    r_default = client.get("/api/files", headers=h)
    assert r_default.status_code == 200
    assert [it["id"] for it in r_default.json()["items"]][0] == f_a.id

    r_asc = client.get("/api/files", params={"sort_name": "asc"}, headers=h)
    assert r_asc.status_code == 200
    names_asc = [it["original_name"] for it in r_asc.json()["items"]]
    assert names_asc == sorted(names_asc, key=str.lower)

    r_desc = client.get("/api/files", params={"sort_name": "desc"}, headers=h)
    assert r_desc.status_code == 200
    names_desc = [it["original_name"] for it in r_desc.json()["items"]]
    assert names_desc == sorted(names_desc, key=str.lower, reverse=True)


def test_sort_name_invalid_rejected(client, jwt_token):
    r = client.get(
        "/api/files",
        params={"sort_name": "bogus"},
        headers={"Authorization": f"Bearer {jwt_token}"},
    )
    assert r.status_code == status.HTTP_422_UNPROCESSABLE_ENTITY


def test_sort_time_invalid_rejected(client, jwt_token):
    r = client.get(
        "/api/files",
        params={"sort_time": "bogus"},
        headers={"Authorization": f"Bearer {jwt_token}"},
    )
    assert r.status_code == status.HTTP_422_UNPROCESSABLE_ENTITY
