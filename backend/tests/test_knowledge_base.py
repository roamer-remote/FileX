# Copyright (c) 2026 徐泽宇
"""Tests for per-user kb_index.md and /api/knowledge-base routes.

Authors:
    徐泽宇

Copyright:
    © 2026 徐泽宇
"""

import os
import threading
import time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from unittest.mock import patch

import pytest
from fastapi import status

from config import UPLOAD_DIR
from models.file import File as FileModel
from services.auth_service import create_access_token
from services.knowledge_base_index_service import (
    ANCHOR_END,
    ANCHOR_START,
    _short_mime_label,
    default_kb_index_markdown,
    read_text,
)


def test_short_mime_label():
    assert (
        _short_mime_label(
            "application/vnd.openxmlformats-officedocument.presentationml.presentation",
            "deck.pptx",
        )
        == "pptx"
    )
    assert _short_mime_label("application/pdf", "a.pdf") == "pdf"
    assert _short_mime_label("image/png", "x.png") == "png"


def test_default_markdown_has_single_anchor_pair():
    s = default_kb_index_markdown()
    assert s.count(ANCHOR_START) == 1
    assert s.count(ANCHOR_END) == 1
    assert "| file_id |" in s


def test_rebuild_creates_file_and_table_row(db_session, regular_user, client, jwt_token):
    f = FileModel(
        user_id=regular_user.id,
        filename="a.txt",
        original_name="doc.txt",
        file_path="/tmp/x",
        file_size=1,
        mime_type="text/plain",
        md5_hash="a" * 32,
        has_md=False,
    )
    db_session.add(f)
    db_session.commit()
    db_session.refresh(f)

    r = client.post(
        "/api/knowledge-base/rebuild",
        headers={"Authorization": f"Bearer {jwt_token}"},
    )
    assert r.status_code == 200
    path = os.path.join(UPLOAD_DIR, str(regular_user.id), "kb_index.md")
    assert os.path.isfile(path)
    text = read_text(regular_user.id)
    assert text
    assert "| file_id |" in text
    assert str(f.id) in text
    assert "doc.txt" in text

    g = client.get(
        "/api/knowledge-base/",
        headers={"Authorization": f"Bearer {jwt_token}"},
    )
    assert g.status_code == 200
    assert "doc.txt" in g.text


def test_get_404_before_rebuild(client, db_session):
    from .conftest import _create_user

    u = _create_user(db_session, "kbemptyuser")
    # On-disk index persists across test runs; clear for a true 404.
    legacy = Path(UPLOAD_DIR) / str(u.id) / "kb_index.md"
    if legacy.is_file():
        legacy.unlink()
    token = create_access_token(u.id, u.password_rev)
    resp = client.get(
        "/api/knowledge-base/",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == status.HTTP_404_NOT_FOUND


def test_put_then_get_roundtrip(client, jwt_token, regular_user):
    body = default_kb_index_markdown() + "\n## Extra\n\nhello\n"
    r = client.put(
        "/api/knowledge-base/",
        headers={"Authorization": f"Bearer {jwt_token}"},
        json={"content": body},
    )
    assert r.status_code == 200
    g = client.get(
        "/api/knowledge-base/",
        headers={"Authorization": f"Bearer {jwt_token}"},
    )
    assert g.status_code == 200
    assert "hello" in g.text


def test_rebuild_preserves_outside_anchors(db_session, regular_user, client, jwt_token):
    custom = (
        "# Title\n\nIntro paragraph.\n\n"
        f"{ANCHOR_START}\n\n| — | x |\n|---|---|\n\n{ANCHOR_END}\n\n"
        "## Footer\nkeep-me\n"
    )
    client.put(
        "/api/knowledge-base/",
        headers={"Authorization": f"Bearer {jwt_token}"},
        json={"content": custom},
    )

    f = FileModel(
        user_id=regular_user.id,
        filename="b.bin",
        original_name="b.bin",
        file_path="/tmp/y",
        file_size=2,
        mime_type="application/octet-stream",
        md5_hash="b" * 32,
        has_md=False,
    )
    db_session.add(f)
    db_session.commit()

    client.post(
        "/api/knowledge-base/rebuild",
        headers={"Authorization": f"Bearer {jwt_token}"},
    )
    text = read_text(regular_user.id)
    assert "keep-me" in text
    assert "Intro paragraph" in text
    assert "b.bin" in text


def test_delete_file_syncs_kb_index(db_session, regular_user, client, jwt_token):
    """删除文件后，kb_index.md AUTO 表应移除对应行。"""
    uid = regular_user.id
    user_dir = Path(UPLOAD_DIR) / str(uid)
    user_dir.mkdir(parents=True, exist_ok=True)
    physical = user_dir / "prune_me.txt"
    physical.write_text("x", encoding="utf-8")

    f = FileModel(
        user_id=uid,
        filename="prune_me.txt",
        original_name="prune_me.txt",
        file_path=str(physical),
        file_size=1,
        mime_type="text/plain",
        md5_hash="c" * 32,
        has_md=False,
    )
    db_session.add(f)
    db_session.commit()
    db_session.refresh(f)
    file_id = f.id

    client.post(
        "/api/knowledge-base/rebuild",
        headers={"Authorization": f"Bearer {jwt_token}"},
    )
    before = read_text(uid)
    assert before
    assert "prune_me.txt" in before
    assert str(file_id) in before

    resp = client.delete(
        f"/api/files/{file_id}",
        headers={"Authorization": f"Bearer {jwt_token}"},
    )
    assert resp.status_code == 200

    after = read_text(uid)
    assert after
    assert "prune_me.txt" not in after
    assert f"| {file_id} | {file_id} |" not in after
    assert f"| {file_id} |" not in after


def test_upload_auto_syncs_kb_index(client, jwt_token, regular_user, tmp_path):
    """上传文件后应自动创建/更新 kb_index.md。"""
    uid = regular_user.id
    legacy = Path(UPLOAD_DIR) / str(uid) / "kb_index.md"
    if legacy.is_file():
        legacy.unlink()

    content = b"hello kb index auto"
    r = client.post(
        "/api/files/upload",
        headers={"Authorization": f"Bearer {jwt_token}"},
        files={"file": ("auto_index.txt", content, "text/plain")},
    )
    assert r.status_code == 200
    file_id = r.json()["id"]
    assert os.path.isfile(legacy)
    text = read_text(uid)
    assert text
    assert "auto_index.txt" in text
    assert str(file_id) in text


def test_delete_file_can_defer_kb_index_sync(db_session, regular_user, client, jwt_token):
    uid = regular_user.id
    user_dir = Path(UPLOAD_DIR) / str(uid)
    user_dir.mkdir(parents=True, exist_ok=True)
    physical = user_dir / "defer_delete.txt"
    physical.write_text("x", encoding="utf-8")

    f = FileModel(
        user_id=uid,
        filename="defer_delete.txt",
        original_name="defer_delete.txt",
        file_path=str(physical),
        file_size=1,
        mime_type="text/plain",
        md5_hash="d" * 32,
        has_md=False,
    )
    db_session.add(f)
    db_session.commit()
    db_session.refresh(f)

    with patch("services.knowledge_base_index_service.auto_sync_kb_index") as mock_sync:
        resp = client.delete(
            f"/api/files/{f.id}?defer_kb_index_sync=true",
            headers={"Authorization": f"Bearer {jwt_token}"},
        )

    assert resp.status_code == 200
    assert mock_sync.call_count == 0
    assert db_session.get(FileModel, f.id) is None


def test_atomic_write_uses_unique_temp_file(monkeypatch, regular_user):
    from services import knowledge_base_index_service as svc

    seen_sources: list[Path] = []
    real_replace = svc.os.replace

    def capture_replace(src, dst):
        seen_sources.append(Path(src))
        return real_replace(src, dst)

    monkeypatch.setattr(svc.os, "replace", capture_replace)
    svc.atomic_write(regular_user.id, default_kb_index_markdown())

    assert seen_sources
    assert seen_sources[0].name != "kb_index.md.tmp"
    assert not (Path(UPLOAD_DIR) / str(regular_user.id) / "kb_index.md.tmp").exists()


def test_atomic_write_respects_user_write_lock(regular_user):
    from services import knowledge_base_index_service as svc

    lock = svc._write_lock_for_user(regular_user.id)
    started = threading.Event()
    finished = threading.Event()

    def write_index():
        started.set()
        svc.atomic_write(regular_user.id, default_kb_index_markdown())
        finished.set()

    lock.acquire()
    try:
        thread = threading.Thread(target=write_index)
        thread.start()
        assert started.wait(timeout=1)
        time.sleep(0.05)
        assert not finished.is_set()
    finally:
        lock.release()
    thread.join(timeout=1)
    assert finished.is_set()


def test_atomic_write_cleans_temp_file_when_write_fails(monkeypatch, regular_user):
    from services import knowledge_base_index_service as svc

    user_dir = Path(UPLOAD_DIR) / str(regular_user.id)
    user_dir.mkdir(parents=True, exist_ok=True)
    tmp_path = user_dir / "kb_index.fail.tmp"

    class FailingTemp:
        name = str(tmp_path)

        def __enter__(self):
            tmp_path.write_text("", encoding="utf-8")
            return self

        def __exit__(self, exc_type, exc, tb):
            return False

        def write(self, _text):
            raise OSError("disk full")

    monkeypatch.setattr(
        svc.tempfile,
        "NamedTemporaryFile",
        lambda *args, **kwargs: FailingTemp(),
    )

    with pytest.raises(OSError, match="disk full"):
        svc.atomic_write(regular_user.id, default_kb_index_markdown())

    assert not tmp_path.exists()


def test_concurrent_rebuild_and_save_keeps_utf8_and_cleans_temps(monkeypatch, db_session, regular_user):
    from services import knowledge_base_index_service as svc

    user_dir = Path(UPLOAD_DIR) / str(regular_user.id)
    user_dir.mkdir(parents=True, exist_ok=True)
    svc.index_md_path(regular_user.id).write_text(default_kb_index_markdown(), encoding="utf-8")

    def fake_auto_section(_db, _user_id):
        time.sleep(0.01)
        return (
            "\n\n| file_id | original_name | mime_type | has_md | tags | created_at |\n"
            "|---|---|---|---|---|---|\n"
            "| 1 | 并发.md | md | 1 | tag | 2026-07-11 |\n\n"
        )

    monkeypatch.setattr(svc, "render_auto_section", fake_auto_section)

    with ThreadPoolExecutor(max_workers=8) as executor:
        futures = [
            executor.submit(svc.rebuild_and_save, db_session, regular_user.id, sync_scope="auto")
            for _ in range(16)
        ]
        for future in futures:
            future.result(timeout=2)

    text = svc.index_md_path(regular_user.id).read_text(encoding="utf-8")
    assert text.count(svc.ANCHOR_START) == 1
    assert text.count(svc.ANCHOR_END) == 1
    assert "并发.md" in text
    assert not (user_dir / "kb_index.md.tmp").exists()
    assert list(user_dir.glob("kb_index.*.tmp")) == []


def test_rebuild_reports_backup_failure(monkeypatch, regular_user, client, jwt_token):
    from services import knowledge_base_index_service as svc

    p = Path(UPLOAD_DIR) / str(regular_user.id) / "kb_index.md"
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_bytes(b"# bad\n\xbb\n")

    def fail_backup(_user_id):
        raise OSError("readonly backup dir")

    monkeypatch.setattr(svc, "backup_corrupt_index", fail_backup)

    resp = client.post(
        "/api/knowledge-base/rebuild",
        headers={"Authorization": f"Bearer {jwt_token}"},
    )

    assert resp.status_code == status.HTTP_500_INTERNAL_SERVER_ERROR
    assert "备份损坏索引文件失败" in resp.json()["detail"]
    assert p.read_bytes() == b"# bad\n\xbb\n"


def test_get_corrupt_kb_index_returns_conflict(regular_user, client, jwt_token):
    p = Path(UPLOAD_DIR) / str(regular_user.id) / "kb_index.md"
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_bytes(b"# bad\n\xbb\n")

    resp = client.get(
        "/api/knowledge-base/",
        headers={"Authorization": f"Bearer {jwt_token}"},
    )

    assert resp.status_code == status.HTTP_409_CONFLICT
    assert "索引文件损坏" in resp.json()["detail"]


def test_rebuild_recovers_corrupt_kb_index(db_session, regular_user, client, jwt_token):
    p = Path(UPLOAD_DIR) / str(regular_user.id) / "kb_index.md"
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_bytes(b"# bad\n\xbb\n")
    f = FileModel(
        user_id=regular_user.id,
        filename="recover.txt",
        original_name="recover.txt",
        file_path="/tmp/recover.txt",
        file_size=1,
        mime_type="text/plain",
        md5_hash="e" * 32,
        has_md=False,
    )
    db_session.add(f)
    db_session.commit()

    resp = client.post(
        "/api/knowledge-base/rebuild",
        headers={"Authorization": f"Bearer {jwt_token}"},
    )

    assert resp.status_code == 200
    body = resp.json()
    assert body["recovered_from_corrupt"] is True
    assert body["backup_name"].startswith("kb_index.md.corrupt-")
    assert (p.parent / body["backup_name"]).read_bytes() == b"# bad\n\xbb\n"
    assert p.read_text(encoding="utf-8")
    assert "recover.txt" in p.read_text(encoding="utf-8")
