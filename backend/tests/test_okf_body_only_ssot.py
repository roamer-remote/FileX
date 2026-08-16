# Copyright (c) 2026 徐泽宇
"""Task 4 回归：frontmatter 不进入 chunks/hash/anchors/wiki/context/external 正文。

Authors:
    徐泽宇

Copyright:
    © 2026 徐泽宇
"""

from __future__ import annotations

import os
from pathlib import Path
from unittest.mock import patch

from models.file import File as FileModel
from models.file_tag_anchor import FileTagAnchor
from models.file_wiki_link import FileWikiLink
from services.md_hash_service import compute_md_content_hash
from services.md_paths import md_note_path
from services.md_tag_anchor_service import rebuild_anchors_for_file
from services.md_wiki_link_service import rebuild_wiki_links_for_file, wiki_links_stale_for_file
from services.okf.frontmatter import split_frontmatter
from services.workspace_service import get_personal_workspace


def _setup_dirs(tmp_path, monkeypatch):
    upload = tmp_path / "uploads"
    md_dir = upload / ".md_notes"
    md_dir.mkdir(parents=True, exist_ok=True)
    monkeypatch.setattr("services.md_paths.UPLOAD_DIR", str(upload))
    monkeypatch.setattr("services.md_paths.MD_DIR", str(md_dir))
    monkeypatch.setattr("config.UPLOAD_DIR", str(upload))
    return md_dir


def _okf_file(db_session, regular_user, *, frontmatter: str, body: str, md5="0" * 32):
    f = FileModel(
        filename="okf.bin",
        original_name="okf.pdf",
        file_path="/tmp/okf.bin",
        file_size=10,
        mime_type="application/pdf",
        user_id=regular_user.id,
        md5_hash=md5,
        has_md=True,
        extract_status="pending",
    )
    ws = get_personal_workspace(db_session, regular_user.id)
    if ws is not None:
        f.workspace_id = ws.id
    db_session.add(f)
    db_session.commit()
    db_session.refresh(f)
    note = Path(md_note_path(f.id))
    note.parent.mkdir(parents=True, exist_ok=True)
    note.write_text(frontmatter + body, encoding="utf-8")
    f.md_file_path = str(note)
    f.md_content_hash = compute_md_content_hash(body)
    db_session.commit()
    db_session.refresh(f)
    return f


_OKF_FM = (
    "---\n"
    "type: FileX Source\n"
    "title: Sample\n"
    "okf_version: '0.1'\n"
    "filex:\n"
    "  file_id: {fid}\n"
    "  extract_status: pending\n"
    "---\n"
)


def test_resolve_index_text_excludes_frontmatter(db_session, regular_user, tmp_path, monkeypatch):
    """SC-111-006：chunk 文本不含 YAML frontmatter。"""
    _setup_dirs(tmp_path, monkeypatch)
    body = "# 正文标题\n\n这是 body 内容，不应包含 YAML 元数据。\n"
    f = _okf_file(db_session, regular_user, frontmatter=_OKF_FM.format(fid=1), body=body)

    from services.kb_text_source import resolve_index_text

    text, source = resolve_index_text(f)
    assert source == "sidecar_md"
    assert text == body
    assert "---" not in text
    assert "type:" not in text
    assert "filex" not in text


def test_persist_extract_markdown_preserves_frontmatter(db_session, regular_user, tmp_path, monkeypatch):
    """SC-111-002：提取只替换 body，保留 frontmatter，并刷新 filex.extract_status。"""
    _setup_dirs(tmp_path, monkeypatch)
    body = "# old body\n"
    f = _okf_file(db_session, regular_user, frontmatter=_OKF_FM.format(fid=1), body=body)

    from services.kb_extract_service import persist_extract_markdown

    with patch("services.md_tag_anchor_service.rebuild_anchors_for_file"), patch(
        "services.md_note_service.rebuild_md_note_side_effects"
    ):
        persist_extract_markdown(db_session, f, "# 提取正文\n", engine="test", user_id=regular_user.id)

    raw = open(f.md_file_path, encoding="utf-8").read()
    meta, body_after = split_frontmatter(raw)
    assert meta["type"] == "FileX Source"
    assert meta["title"] == "Sample"
    assert body_after == "# 提取正文\n"
    assert meta["filex"]["extract_status"] == "ready"
    assert f.md_content_hash == compute_md_content_hash("# 提取正文\n")


def test_extract_skip_uses_body_only_for_okf_file(db_session, regular_user, tmp_path, monkeypatch):
    """SC-111-011：extract skip 基于 body-only hash；OKF 文件 frontmatter 不干扰 skip。"""
    _setup_dirs(tmp_path, monkeypatch)
    body = "# body unchanged\n"
    f = _okf_file(db_session, regular_user, frontmatter=_OKF_FM.format(fid=1), body=body)

    from services.kb_extract_service import _md_extract_hash_unchanged

    assert _md_extract_hash_unchanged(f, bypass=False) is True


def test_tag_anchor_offsets_are_body_based(db_session, regular_user, tmp_path, monkeypatch):
    """SC-111-007：tag anchor offset 基于 body，不被 frontmatter 偏移。"""
    _setup_dirs(tmp_path, monkeypatch)
    body = "prefix alpha suffix\n"
    f = _okf_file(db_session, regular_user, frontmatter=_OKF_FM.format(fid=1), body=body)

    from services.tag_service import replace_file_tags

    replace_file_tags(db_session, regular_user.id, f.id, ["alpha"])
    db_session.commit()
    rebuild_anchors_for_file(db_session, regular_user.id, f.id)
    db_session.commit()

    anchors = db_session.query(FileTagAnchor).filter(FileTagAnchor.file_id == f.id).all()
    assert len(anchors) == 1
    # body 中 "alpha" 起始偏移为 7；frontmatter 长度远大于此，证明 offset 基于 body
    assert anchors[0].start_offset == 7
    assert anchors[0].end_offset == 12


def test_wiki_link_stale_uses_body_only(db_session, regular_user, tmp_path, monkeypatch):
    """SC-111-007：wiki link stale 基于 body；仅改 frontmatter 不视为 stale。"""
    _setup_dirs(tmp_path, monkeypatch)
    body = "[[file:999]] link in body\n"
    f = _okf_file(db_session, regular_user, frontmatter=_OKF_FM.format(fid=1), body=body)

    rebuild_wiki_links_for_file(db_session, regular_user, f.id)
    db_session.commit()
    assert wiki_links_stale_for_file(db_session, f.id) is False

    rows = db_session.query(FileWikiLink).filter(FileWikiLink.source_file_id == f.id).all()
    assert rows and rows[0].content_hash

    # 仅修改 frontmatter（title），body 不变 → 不应 stale
    new_fm = (
        "---\n"
        "type: FileX Source\n"
        "title: Changed Title\n"
        "okf_version: '0.1'\n"
        "filex:\n"
        "  file_id: 1\n"
        "  extract_status: pending\n"
        "---\n"
    )
    open(f.md_file_path, "w", encoding="utf-8").write(new_fm + body)
    assert wiki_links_stale_for_file(db_session, f.id) is False


def test_external_md_content_returns_body_only(client, jwt_token, active_api_key):
    """Task 4 Minor #1：外部 GET /md-content 返回 body-only，不泄漏 frontmatter。"""
    body = "# body via external\n"
    with patch("services.kb_index_service.publish_index_job"):
        r = client.post(
            "/api/files/upload",
            headers={"Authorization": f"Bearer {jwt_token}"},
            files={"file": ("ext_okf.md", body.encode("utf-8"), "text/markdown")},
        )
    assert r.status_code == 200, r.text
    md5 = r.json()["md5_hash"]

    resp = client.get(
        f"/api/external/md-content/{md5}",
        headers={"Authorization": f"Bearer {active_api_key._plaintext}"},
    )
    assert resp.status_code == 200, resp.text
    assert resp.text == body
    assert "---" not in resp.text
    assert "filex" not in resp.text


def test_admin_restore_version_preserves_frontmatter_and_version_chain(
    db_session, regular_user, admin_jwt_token, client, tmp_path, monkeypatch
):
    """Major #1：admin 恢复 OKF native 版本只替换 body、保留 frontmatter，并续接版本链。"""
    _setup_dirs(tmp_path, monkeypatch)
    body_v1 = "# 第一版正文\n"
    f = _okf_file(db_session, regular_user, frontmatter=_OKF_FM.format(fid=1), body=body_v1)

    # 模拟一次 body-only 编辑：把当前 body 快照成历史版本，写入新 body
    from models.file_md_version import FileMdVersion

    snap = FileMdVersion(file_id=f.id, version=1, content=body_v1, created_by_user_id=regular_user.id)
    db_session.add(snap)
    db_session.commit()
    db_session.refresh(snap)
    f.md_content_rev = 1
    db_session.commit()

    from services.okf_note_service import save_okf_body_for_file

    save_okf_body_for_file(f, "# 第二版正文\n")
    db_session.commit()

    # admin 恢复到 v1（body-only）
    with patch("services.kb_index_service.enqueue_index"), patch(
        "services.kb_index_service.publish_index_job"
    ), patch("services.md_tag_anchor_service.rebuild_anchors_for_file"), patch(
        "services.md_note_service.rebuild_md_note_side_effects"
    ):
        r = client.post(
            f"/api/admin/files/{f.id}/md/restore-version",
            headers={"Authorization": f"Bearer {admin_jwt_token}"},
            json={"version_id": snap.id},
        )
    assert r.status_code == 200, r.text

    raw = open(f.md_file_path, encoding="utf-8").read()
    meta, body_after = split_frontmatter(raw)
    # frontmatter 完整保留
    assert meta["type"] == "FileX Source"
    assert meta["title"] == "Sample"
    assert meta["filex"]["file_id"] == f.id
    # body 恢复为 v1，frontmatter 未泄漏进 body
    assert body_after == body_v1
    assert "---" not in body_after
    # 版本链：恢复前当前 body（v2）被快照为新版本
    new_versions = (
        db_session.query(FileMdVersion)
        .filter(FileMdVersion.file_id == f.id, FileMdVersion.version == 2)
        .all()
    )
    assert len(new_versions) == 1
    assert new_versions[0].content == "# 第二版正文\n"
    assert f.md_content_hash == compute_md_content_hash(body_v1)


def test_admin_restore_version_legacy_raw(db_session, regular_user, admin_jwt_token, client, tmp_path, monkeypatch):
    """Major #1：legacy sidecar（无 frontmatter）恢复版本仍走 raw 整段覆写。"""
    _setup_dirs(tmp_path, monkeypatch)
    legacy_v1 = "# legacy raw v1\n"
    f = _okf_file(db_session, regular_user, frontmatter="", body=legacy_v1)

    from models.file_md_version import FileMdVersion

    snap = FileMdVersion(file_id=f.id, version=1, content=legacy_v1, created_by_user_id=regular_user.id)
    db_session.add(snap)
    f.md_content_rev = 1
    db_session.commit()
    db_session.refresh(snap)

    from services.md_note_service import save_md_note_for_file

    save_md_note_for_file(db_session, regular_user.id, f, "# legacy raw v2\n", enqueue_vector_index=False)
    db_session.commit()

    with patch("services.kb_index_service.enqueue_index"), patch(
        "services.kb_index_service.publish_index_job"
    ), patch("services.md_tag_anchor_service.rebuild_anchors_for_file"), patch(
        "services.md_note_service.rebuild_md_note_side_effects"
    ):
        r = client.post(
            f"/api/admin/files/{f.id}/md/restore-version",
            headers={"Authorization": f"Bearer {admin_jwt_token}"},
            json={"version_id": snap.id},
        )
    assert r.status_code == 200, r.text

    raw = open(f.md_file_path, encoding="utf-8").read()
    assert raw == legacy_v1
    assert "type:" not in raw


def test_empty_extract_refreshes_filex_extract_status(db_session, regular_user, tmp_path, monkeypatch):
    """Minor #1：空 extract 不覆写 body，但刷新 frontmatter 的 filex.extract_status。"""
    _setup_dirs(tmp_path, monkeypatch)
    body = "# 已有正文\n"
    f = _okf_file(db_session, regular_user, frontmatter=_OKF_FM.format(fid=1), body=body)

    from services.kb_extract_service import persist_extract_markdown

    with patch("services.md_tag_anchor_service.rebuild_anchors_for_file"), patch(
        "services.md_note_service.rebuild_md_note_side_effects"
    ):
        persist_extract_markdown(db_session, f, "", engine="test", user_id=regular_user.id)

    raw = open(f.md_file_path, encoding="utf-8").read()
    meta, body_after = split_frontmatter(raw)
    # body 被保留（未被空提取覆写）
    assert body_after == body
    # frontmatter 的 filex.extract_status 镜像为 skipped
    assert meta["filex"]["extract_status"] == "skipped"
    assert f.extract_status == "skipped"


def test_read_md_note_content_for_hash_returns_none_when_disk_missing(
    db_session, regular_user, tmp_path, monkeypatch
):
    """Minor #2：sidecar 在磁盘缺失时返回 None，避免误判为空正文触发错误 skip。"""
    _setup_dirs(tmp_path, monkeypatch)
    body = "# body\n"
    f = _okf_file(db_session, regular_user, frontmatter=_OKF_FM.format(fid=1), body=body)
    # 标记存在 hash，但删除磁盘文件
    f.md_content_hash = compute_md_content_hash(body)
    db_session.commit()
    os.remove(f.md_file_path)

    from services.md_hash_service import read_md_note_content_for_hash

    assert read_md_note_content_for_hash(f) is None
    from services.kb_extract_service import _md_extract_hash_unchanged

    # 磁盘缺失不应被误判为"内容未变"而跳过提取
    assert _md_extract_hash_unchanged(f, bypass=False) is False
