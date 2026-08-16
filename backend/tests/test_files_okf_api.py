# Copyright (c) 2026 徐泽宇
"""OKF 源码 / 元数据 API 与 body-only md API 集成测试（Task 3）。

Authors:
    徐泽宇

Copyright:
    © 2026 徐泽宇
"""

from __future__ import annotations

import os
from unittest.mock import patch

from models.file import File as FileModel
from models.file_md_version import FileMdVersion
from services.md_paths import md_note_path, okf_sidecar_path
from services.okf.frontmatter import split_frontmatter
from services.tag_service import get_file_tag_names


def _sidecar_path(data: dict) -> str:
    return okf_sidecar_path(data["workspace_id"], data["okf_concept_path"])


def _upload_md(client, jwt_token, filename="note.md", body="# Body\n\ninitial.\n"):
    with patch("services.kb_index_service.publish_index_job"):
        r = client.post(
            "/api/files/upload",
            headers={"Authorization": f"Bearer {jwt_token}"},
            files={"file": (filename, body.encode("utf-8"), "text/markdown")},
        )
    assert r.status_code == 200, r.text
    return r.json()


def _headers(jwt_token):
    return {"Authorization": f"Bearer {jwt_token}"}


def test_get_md_returns_body_only(client, jwt_token):
    """SC-111-003：上传无 frontmatter 的 .md 被包装为 OKF；GET /md 只返回原 body。"""
    body = "# Title\n\nplain body text\n"
    data = _upload_md(client, jwt_token, "plain.md", body)
    file_id = data["id"]

    r = client.get(f"/api/files/{file_id}/md", headers=_headers(jwt_token))
    assert r.status_code == 200
    assert r.text == body  # 不含 frontmatter

    raw = open(_sidecar_path(data), encoding="utf-8").read()
    meta, parsed_body = split_frontmatter(raw)
    assert meta["type"] == "FileX Source"
    assert parsed_body == body


def test_put_md_updates_body_preserves_frontmatter(client, jwt_token, db_session):
    """SC-111-005：PUT /md 只更新 body，不删除/重排 frontmatter 必填字段。"""
    data = _upload_md(client, jwt_token, "preserve.md", "# old body\n")
    file_id = data["id"]

    new_body = "# new body\n\nedited\n"
    r = client.put(f"/api/files/{file_id}/md", headers=_headers(jwt_token), json={"content": new_body})
    assert r.status_code == 200, r.text

    raw = open(_sidecar_path(data), encoding="utf-8").read()
    meta, body = split_frontmatter(raw)
    assert body == new_body
    assert meta["type"] == "FileX Source"
    assert meta["title"] == "preserve"
    assert meta["resource"] == f"filex://files/{file_id}"
    assert meta["okf_version"] == "0.1"


def test_get_okf_returns_full_raw(client, jwt_token):
    """SC-111-008：GET /okf 返回完整 OKF Markdown raw。"""
    data = _upload_md(client, jwt_token, "raw.md", "# raw body\n")
    file_id = data["id"]

    r = client.get(f"/api/files/{file_id}/okf", headers=_headers(jwt_token))
    assert r.status_code == 200
    raw = r.text
    assert raw.startswith("---\n")
    meta, body = split_frontmatter(raw)
    assert meta["type"] == "FileX Source"
    assert body == "# raw body\n"


def test_put_okf_meta_updates_fields_and_syncs_tags(client, jwt_token, db_session):
    """SC-111-008 / Step 5：PUT /okf/meta 更新 title/type/tags/path 并三向同步。"""
    data = _upload_md(client, jwt_token, "meta.md", "# body\n")
    file_id = data["id"]

    r = client.put(
        f"/api/files/{file_id}/okf/meta",
        headers=_headers(jwt_token),
        json={
            "type": "Research Note",
            "title": "Renamed",
            "description": "desc",
            "tags": ["alpha", "beta"],
            "okf_concept_path": "sources/research/renamed",
        },
    )
    assert r.status_code == 200, r.text
    payload = r.json()
    assert payload["okf_type"] == "Research Note"
    assert payload["okf_concept_path"] == "sources/research/renamed"
    assert payload["frontmatter"]["title"] == "Renamed"
    assert payload["frontmatter"]["tags"] == ["alpha", "beta"]

    db_session.expire_all()
    f = db_session.query(FileModel).filter(FileModel.id == file_id).first()
    assert f.okf_type == "Research Note"
    assert f.okf_concept_path == "sources/research/renamed"
    assert f.okf_metadata["tags"] == ["alpha", "beta"]
    assert get_file_tag_names(db_session, file_id) == ["alpha", "beta"]

    renamed_path = okf_sidecar_path(data["workspace_id"], "sources/research/renamed")
    assert f.md_file_path == renamed_path
    assert os.path.isfile(renamed_path)
    raw = open(renamed_path, encoding="utf-8").read()
    meta, body = split_frontmatter(raw)
    assert meta["type"] == "Research Note"
    assert meta["title"] == "Renamed"
    assert meta["tags"] == ["alpha", "beta"]
    assert body == "# body\n"
    old_path = _sidecar_path(data)
    assert not os.path.isfile(old_path)


def test_put_file_tags_syncs_okf_frontmatter(client, jwt_token, db_session):
    """SC-111-013：PUT /files/{id}/tags（列表标签编辑）同步 frontmatter 与 okf_metadata.tags。"""
    data = _upload_md(client, jwt_token, "list-tags.md", "# body\n")
    file_id = data["id"]

    r = client.put(
        f"/api/files/{file_id}/tags",
        headers=_headers(jwt_token),
        json={"tags": ["alpha", "beta"]},
    )
    assert r.status_code == 200, r.text
    assert r.json() == ["alpha", "beta"]

    meta = client.get(f"/api/files/{file_id}/okf/meta", headers=_headers(jwt_token)).json()
    assert meta["frontmatter"]["tags"] == ["alpha", "beta"]

    db_session.expire_all()
    f = db_session.query(FileModel).filter(FileModel.id == file_id).first()
    assert f.okf_metadata["tags"] == ["alpha", "beta"]
    assert get_file_tag_names(db_session, file_id) == ["alpha", "beta"]

    raw = open(_sidecar_path(data), encoding="utf-8").read()
    fm, body = split_frontmatter(raw)
    assert fm["tags"] == ["alpha", "beta"]
    assert body == "# body\n"


def test_put_okf_meta_path_conflict_returns_409(client, jwt_token):
    """SC-111-009b：PUT /okf/meta 保存冲突 concept_path 返回 409，不自动改写用户输入。"""
    a = _upload_md(client, jwt_token, "conflict_a.md", "# a\n")
    b = _upload_md(client, jwt_token, "conflict_b.md", "# b\n")
    a_path = client.get(f"/api/files/{a['id']}/okf/meta", headers=_headers(jwt_token)).json()["okf_concept_path"]

    r = client.put(
        f"/api/files/{b['id']}/okf/meta",
        headers=_headers(jwt_token),
        json={"okf_concept_path": a_path},
    )
    assert r.status_code == 409
    assert "占用" in r.json()["detail"]

    # B 的 path 不应被改写
    b_path = client.get(f"/api/files/{b['id']}/okf/meta", headers=_headers(jwt_token)).json()["okf_concept_path"]
    assert b_path != a_path


def test_put_okf_meta_rejects_empty_type(client, jwt_token):
    data = _upload_md(client, jwt_token, "typecheck.md", "# body\n")
    r = client.put(
        f"/api/files/{data['id']}/okf/meta",
        headers=_headers(jwt_token),
        json={"type": "   "},
    )
    assert r.status_code == 400


def test_metadata_only_update_keeps_md_content_hash(client, jwt_token, db_session):
    """SC-111-011：metadata-only 更新不改变 md_content_hash。"""
    data = _upload_md(client, jwt_token, "hash.md", "# body\n")
    file_id = data["id"]
    db_session.expire_all()
    f = db_session.query(FileModel).filter(FileModel.id == file_id).first()
    hash_before = f.md_content_hash

    r = client.put(
        f"/api/files/{file_id}/okf/meta",
        headers=_headers(jwt_token),
        json={"title": "Changed Title", "tags": ["x"]},
    )
    assert r.status_code == 200, r.text

    db_session.expire_all()
    f = db_session.query(FileModel).filter(FileModel.id == file_id).first()
    assert f.md_content_hash == hash_before


def test_put_md_creates_body_version_but_meta_does_not(client, jwt_token, db_session):
    """SC-111-012：body 更新增版本链（body-only）；metadata-only 不新增版本。"""
    data = _upload_md(client, jwt_token, "version.md", "# v0\n")
    file_id = data["id"]
    db_session.expire_all()
    f = db_session.query(FileModel).filter(FileModel.id == file_id).first()
    rev_before = int(f.md_content_rev or 0)

    # body 更新 → 新增版本
    r = client.put(
        f"/api/files/{file_id}/md",
        headers=_headers(jwt_token),
        json={"content": "# v1\n"},
    )
    assert r.status_code == 200, r.text
    db_session.expire_all()
    f = db_session.query(FileModel).filter(FileModel.id == file_id).first()
    assert int(f.md_content_rev or 0) == rev_before + 1
    versions = (
        db_session.query(FileMdVersion)
        .filter(FileMdVersion.file_id == file_id)
        .order_by(FileMdVersion.version.desc())
        .all()
    )
    assert versions and versions[0].content == "# v0\n"

    # metadata-only 更新 → 不新增版本
    rev_after_body = int(f.md_content_rev or 0)
    r = client.put(
        f"/api/files/{file_id}/okf/meta",
        headers=_headers(jwt_token),
        json={"title": "No Version Bump"},
    )
    assert r.status_code == 200, r.text
    db_session.expire_all()
    f = db_session.query(FileModel).filter(FileModel.id == file_id).first()
    assert int(f.md_content_rev or 0) == rev_after_body
    assert (
        db_session.query(FileMdVersion).filter(FileMdVersion.file_id == file_id).count() == rev_after_body
    )


def test_legacy_body_only_note_works_via_md_api(client, jwt_token, db_session):
    """SC-111-010：历史 body-only 笔记仍可通过 md API 读取/编辑。"""
    r = client.post(
        "/api/files/upload",
        headers={"Authorization": f"Bearer {jwt_token}"},
        files={"file": ("legacy.txt", b"legacy body line\n", "text/plain")},
    )
    assert r.status_code == 200, r.text
    file_id = r.json()["id"]
    note_path = md_note_path(file_id)
    legacy = "legacy body line\n"
    with open(note_path, "w", encoding="utf-8") as fh:
        fh.write(legacy)
    f = db_session.query(FileModel).filter(FileModel.id == file_id).one()
    f.md_file_path = note_path
    f.okf_concept_path = None
    f.okf_type = None
    f.okf_metadata = None
    db_session.flush()

    r_get = client.get(f"/api/files/{file_id}/md", headers=_headers(jwt_token))
    assert r_get.status_code == 200
    assert r_get.text == legacy

    r_put = client.put(
        f"/api/files/{file_id}/md",
        headers=_headers(jwt_token),
        json={"content": "edited legacy\n"},
    )
    assert r_put.status_code == 200, r_put.text
    r_get2 = client.get(f"/api/files/{file_id}/md", headers=_headers(jwt_token))
    assert r_get2.text == "edited legacy\n"


def test_get_okf_meta_returns_frontmatter_fields(client, jwt_token):
    """Task 3 Minor #3：独立校验 GET /okf/meta 返回 frontmatter 字段完整性。"""
    data = _upload_md(client, jwt_token, "getmeta.md", "# body\n")
    file_id = data["id"]

    r = client.get(f"/api/files/{file_id}/okf/meta", headers=_headers(jwt_token))
    assert r.status_code == 200, r.text
    payload = r.json()
    assert payload["okf_concept_path"].startswith("sources/")
    fm = payload["frontmatter"]
    assert fm["type"] == "FileX Source"
    assert fm["title"] == "getmeta"
    assert fm["resource"] == f"filex://files/{file_id}"
    assert fm["okf_version"] == "0.1"
    assert fm["filex"]["file_id"] == file_id
    assert "tags" in fm
    assert "timestamp" in fm
