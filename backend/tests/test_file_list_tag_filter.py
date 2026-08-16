# Copyright (c) 2026 徐泽宇
"""文件列表 tag + tag2 双标签筛选（标签关系图点击连线）。

Authors:
    徐泽宇

Copyright:
    © 2026 徐泽宇
"""

from datetime import datetime, timezone

from models.file import File as FileModel
from services.tag_service import replace_file_tags


def test_list_files_tag_and_tag2_sorted(client, db_session, regular_user, jwt_token):
    """PostgreSQL：DISTINCT + ORDER BY coalesce 非法；file_tags 主键保证连接不重复。"""
    base = datetime(2025, 2, 1, 8, 0, 0, tzinfo=timezone.utc)
    f_both = FileModel(
        user_id=regular_user.id,
        filename="both.bin",
        original_name="both.txt",
        file_path="/tmp/both",
        file_size=1,
        mime_type="text/plain",
        md5_hash="c" * 32,
        has_md=False,
        created_at=base,
        updated_at=base,
    )
    f_one = FileModel(
        user_id=regular_user.id,
        filename="one.bin",
        original_name="one.txt",
        file_path="/tmp/one",
        file_size=1,
        mime_type="text/plain",
        md5_hash="d" * 32,
        has_md=False,
        created_at=base,
        updated_at=base,
    )
    db_session.add_all([f_both, f_one])
    db_session.commit()
    db_session.refresh(f_both)
    db_session.refresh(f_one)

    replace_file_tags(db_session, regular_user.id, f_both.id, ["alpha", "beta"])
    replace_file_tags(db_session, regular_user.id, f_one.id, ["alpha"])
    db_session.commit()

    h = {"Authorization": f"Bearer {jwt_token}"}
    r = client.get(
        "/api/files",
        params={"tag": "alpha", "tag2": "beta", "sort_time": "desc"},
        headers=h,
    )
    assert r.status_code == 200, r.text
    payload = r.json()
    assert payload["total"] == 1
    assert len(payload["items"]) == 1
    assert payload["items"][0]["id"] == f_both.id
    assert set(payload["items"][0]["tags"]) >= {"alpha", "beta"}
