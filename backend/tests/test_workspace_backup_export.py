# Copyright (c) 2026 徐泽宇
"""087 个人空间备份下载 — 门禁、路径与 source 导出。"""

from __future__ import annotations

import io
import json
import os
import tempfile
import zipfile

from models.file import File as FileModel
from models.folder import Folder
from models.operation_log import OperationLog
from services.auth_service import create_access_token
from constants.workspace_backup_errors import (
    WORKSPACE_BACKUP_NOT_OWNER,
    WORKSPACE_BACKUP_SHARED_NOT_SUPPORTED,
    WORKSPACE_BACKUP_TOO_LARGE,
)
from services.md_note_service import read_md_note_text, save_md_note_for_file
from services.okf_note_service import _default_concept_path, create_okf_note_shell, save_okf_body_for_file
from services.system_setting_service import KEY_SHARED_WORKSPACES_ENABLED, update_settings
from services.wiki_page_service import create_wiki_page
from services.workspace_backup_paths import sanitize_zip_path_segment
from services.workspace_service import create_shared_workspace, ensure_personal_workspace
from tests.conftest import _create_user


def _auth_header(user) -> dict[str, str]:
    token = create_access_token(user.id, user.password_rev)
    return {"Authorization": f"Bearer {token}"}


def _set_shared_enabled(db_session, enabled: bool) -> None:
    update_settings(db_session, {KEY_SHARED_WORKSPACES_ENABLED: "true" if enabled else "false"})


def _download_zip(client, user, ws_id: int) -> tuple[zipfile.ZipFile, dict, str]:
    r = client.get(f"/api/workspaces/{ws_id}/backup", headers=_auth_header(user))
    assert r.status_code == 200, r.text
    zf = zipfile.ZipFile(io.BytesIO(r.content))
    manifest_name = next(n for n in zf.namelist() if n.endswith("manifest.json"))
    manifest = json.loads(zf.read(manifest_name).decode("utf-8"))
    slug_prefix = manifest_name[: -len("manifest.json")]
    return zf, manifest, slug_prefix


def _add_published_source(
    db_session,
    *,
    user,
    workspace_id: int,
    folder_id: int | None,
    tmp_path,
    original_name: str,
    content: bytes,
    note: str | None = None,
    assets: dict[str, bytes] | None = None,
) -> FileModel:
    blob = tmp_path / original_name.replace("/", "_")
    blob.parent.mkdir(parents=True, exist_ok=True)
    blob.write_bytes(content)
    f = FileModel(
        user_id=user.id,
        workspace_id=workspace_id,
        folder_id=folder_id,
        filename=blob.name,
        original_name=original_name,
        file_path=str(blob),
        file_size=len(content),
        mime_type="application/pdf",
        publish_status="published",
        page_kind="source",
    )
    db_session.add(f)
    db_session.flush()
    if note is not None:
        save_md_note_for_file(db_session, user.id, f, note, enqueue_vector_index=False)
    if assets:
        assets_dir = blob.parent / ".extract_assets" / str(f.id)
        assets_dir.mkdir(parents=True, exist_ok=True)
        for name, data in assets.items():
            target = assets_dir / name
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes(data)
    db_session.commit()
    db_session.refresh(f)
    return f


def _add_wiki_page(
    db_session,
    *,
    user,
    workspace_id: int,
    title: str,
    wiki_slug: str,
    markdown: str,
    page_kind: str = "concept",
    folder_id: int | None = None,
) -> FileModel:
    f = create_wiki_page(
        db_session,
        user,
        title=title,
        wiki_slug=wiki_slug,
        page_kind=page_kind,
        markdown=markdown,
        workspace_id=workspace_id,
    )
    if folder_id is not None:
        f.folder_id = folder_id
    db_session.commit()
    db_session.refresh(f)
    return f


def _add_empty_wiki_placeholder(
    db_session,
    *,
    user,
    workspace_id: int,
    title: str,
    wiki_slug: str,
    placeholder_path,
    page_kind: str = "concept",
) -> FileModel:
    """无笔记正文的主题页：磁盘上有占位 file_path，备份不得将其当原件导出。"""
    placeholder_path.parent.mkdir(parents=True, exist_ok=True)
    placeholder_path.write_bytes(b"")
    safe_name = title if title.lower().endswith(".md") else f"{title}.md"
    f = FileModel(
        user_id=user.id,
        workspace_id=workspace_id,
        filename=placeholder_path.name,
        original_name=safe_name,
        file_path=str(placeholder_path),
        file_size=0,
        mime_type="text/markdown",
        has_md=False,
        page_kind=page_kind,
        wiki_slug=wiki_slug,
        publish_status="published",
    )
    db_session.add(f)
    db_session.commit()
    db_session.refresh(f)
    return f


class TestWorkspaceBackupAccess:
    def test_owner_downloads_zip(self, client, db_session, regular_user):
        ws = ensure_personal_workspace(db_session, regular_user)
        db_session.commit()
        r = client.get(
            f"/api/workspaces/{ws.id}/backup",
            headers=_auth_header(regular_user),
        )
        assert r.status_code == 200, r.text
        assert r.headers["content-type"] == "application/zip"
        assert "attachment" in r.headers.get("content-disposition", "").lower()
        with zipfile.ZipFile(io.BytesIO(r.content)) as zf:
            names = zf.namelist()
            assert any(n.endswith("manifest.json") for n in names)
            manifest_name = next(n for n in names if n.endswith("manifest.json"))
            manifest = json.loads(zf.read(manifest_name).decode("utf-8"))
            assert manifest["import_supported"] is False
            assert manifest["workspace_id"] == ws.id

    def test_shared_workspace_forbidden(self, client, db_session, regular_user):
        _set_shared_enabled(db_session, True)
        shared = create_shared_workspace(db_session, name="共享库", owner=regular_user)
        db_session.commit()
        r = client.get(
            f"/api/workspaces/{shared.id}/backup",
            headers=_auth_header(regular_user),
        )
        assert r.status_code == 403, r.text
        assert r.json()["detail"] == WORKSPACE_BACKUP_SHARED_NOT_SUPPORTED

    def test_non_owner_personal_forbidden(self, client, db_session, regular_user):
        other = _create_user(db_session, "other_owner")
        other_ws = ensure_personal_workspace(db_session, other)
        db_session.commit()
        r = client.get(
            f"/api/workspaces/{other_ws.id}/backup",
            headers=_auth_header(regular_user),
        )
        assert r.status_code == 403, r.text
        assert r.json()["detail"] == WORKSPACE_BACKUP_NOT_OWNER

    def test_admin_cannot_backup_others_personal(self, client, db_session, regular_user, admin_user):
        victim_ws = ensure_personal_workspace(db_session, regular_user)
        db_session.commit()
        r = client.get(
            f"/api/workspaces/{victim_ws.id}/backup",
            headers=_auth_header(admin_user),
        )
        assert r.status_code == 403, r.text
        assert r.json()["detail"] == WORKSPACE_BACKUP_NOT_OWNER


class TestWorkspaceBackupPaths:
    def test_sanitize_preserves_cjk(self):
        from services.workspace_backup_paths import sanitize_zip_path_segment

        assert sanitize_zip_path_segment("项目A") == "项目A"
        assert sanitize_zip_path_segment("客户画像.md") == "客户画像.md"

    def test_sanitize_strips_illegal_chars(self):
        from services.workspace_backup_paths import sanitize_zip_path_segment

        assert sanitize_zip_path_segment("report:draft.pdf") == "report_draft.pdf"
        assert sanitize_zip_path_segment("..") == "unknown"

    def test_zip_path_allocator_collision(self):
        from services.workspace_backup_paths import ZipPathAllocator

        alloc = ZipPathAllocator()
        assert alloc.allocate("项目A", "报告.pdf") == "项目A/报告.pdf"
        assert alloc.allocate("项目A", "报告.pdf") == "项目A/报告 (2).pdf"
        assert alloc.allocate("", "note.md") == "note.md"
        assert alloc.allocate("", "note.md") == "note (2).md"


class TestWorkspaceBackupSourceExport:
    def test_nested_folders_with_cjk_paths(self, client, db_session, regular_user, tmp_path):
        ws = ensure_personal_workspace(db_session, regular_user)
        l1 = Folder(name="文件夹A", parent_id=None, user_id=regular_user.id, workspace_id=ws.id)
        db_session.add(l1)
        db_session.flush()
        l2 = Folder(name="子目录", parent_id=l1.id, user_id=regular_user.id, workspace_id=ws.id)
        db_session.add(l2)
        db_session.flush()
        _add_published_source(
            db_session,
            user=regular_user,
            workspace_id=ws.id,
            folder_id=l2.id,
            tmp_path=tmp_path,
            original_name="报告.pdf",
            content=b"%PDF-1.4",
            note="# 笔记",
        )
        zf, manifest, slug_prefix = _download_zip(client, regular_user, ws.id)
        names = zf.namelist()
        assert any("文件夹A/子目录/报告.pdf" in n for n in names)
        assert all(n.startswith(slug_prefix) for n in names)
        assert all("/../" not in n and not n.endswith("/..") for n in names)
        entry = manifest["entries"][0]
        assert entry["zip_paths"]["original"].startswith("文件夹A/子目录/")
        assert entry["zip_paths"]["note"].endswith("报告.pdf.md")

    def test_source_with_assets(self, client, db_session, regular_user, tmp_path):
        ws = ensure_personal_workspace(db_session, regular_user)
        _add_published_source(
            db_session,
            user=regular_user,
            workspace_id=ws.id,
            folder_id=None,
            tmp_path=tmp_path,
            original_name="doc.pdf",
            content=b"%PDF",
            note="has note",
            assets={"fig1.jpg": b"\xff\xd8\xff"},
        )
        zf, manifest, slug_prefix = _download_zip(client, regular_user, ws.id)
        names = zf.namelist()
        assert any(n.endswith("doc.pdf.assets/fig1.jpg") for n in names)
        assert manifest["entries"][0]["zip_paths"]["assets"] == "doc.pdf.assets/"
        assert zf.read(next(n for n in names if n.endswith("fig1.jpg"))) == b"\xff\xd8\xff"

    def test_nested_asset_subdirs_sanitized(self, client, db_session, regular_user, tmp_path):
        ws = ensure_personal_workspace(db_session, regular_user)
        _add_published_source(
            db_session,
            user=regular_user,
            workspace_id=ws.id,
            folder_id=None,
            tmp_path=tmp_path,
            original_name="scan.pdf",
            content=b"%PDF",
            assets={"images:raw/fig1.jpg": b"\xff\xd8\xff", "images/normal/fig2.jpg": b"ok"},
        )
        zf, manifest, slug_prefix = _download_zip(client, regular_user, ws.id)
        safe_raw = sanitize_zip_path_segment("images:raw")
        names = zf.namelist()
        assert any(n.endswith(f"scan.pdf.assets/{safe_raw}/fig1.jpg") for n in names)
        assert any(n.endswith("scan.pdf.assets/images/normal/fig2.jpg") for n in names)
        for n in names:
            assert n.startswith(slug_prefix)
            assert ".." not in n.split("/")
            assert ":" not in n
        assert manifest["entries"][0]["zip_paths"]["assets"] == "scan.pdf.assets/"

    def test_missing_original_still_succeeds(self, client, db_session, regular_user, tmp_path):
        ws = ensure_personal_workspace(db_session, regular_user)
        f = _add_published_source(
            db_session,
            user=regular_user,
            workspace_id=ws.id,
            folder_id=None,
            tmp_path=tmp_path,
            original_name="gone.pdf",
            content=b"x",
            note="only note",
        )
        os.unlink(f.file_path)
        db_session.commit()
        zf, manifest, _ = _download_zip(client, regular_user, ws.id)
        assert not any(n.endswith("gone.pdf") and not n.endswith(".md") for n in zf.namelist())
        assert manifest["entries"][0]["original_missing"] is True
        assert any("gone.pdf.md" in n for n in zf.namelist())
        assert any("original missing" in w for w in manifest["warnings"])

    def test_illegal_folder_name_sanitized_in_zip(self, client, db_session, regular_user, tmp_path):
        ws = ensure_personal_workspace(db_session, regular_user)
        bad_name = "bad/name"
        folder = Folder(
            name=bad_name,
            parent_id=None,
            user_id=regular_user.id,
            workspace_id=ws.id,
        )
        db_session.add(folder)
        db_session.flush()
        _add_published_source(
            db_session,
            user=regular_user,
            workspace_id=ws.id,
            folder_id=folder.id,
            tmp_path=tmp_path,
            original_name="file:1.pdf",
            content=b"data",
        )
        zf, manifest, slug_prefix = _download_zip(client, regular_user, ws.id)
        safe_folder = sanitize_zip_path_segment(bad_name)
        safe_file = sanitize_zip_path_segment("file:1.pdf")
        assert any(n.endswith(f"{safe_folder}/{safe_file}") for n in zf.namelist())
        for n in zf.namelist():
            assert n.startswith(slug_prefix)
            assert ".." not in n.split("/")

    def test_empty_note_skips_sidecar(self, client, db_session, regular_user, tmp_path):
        ws = ensure_personal_workspace(db_session, regular_user)
        _add_published_source(
            db_session,
            user=regular_user,
            workspace_id=ws.id,
            folder_id=None,
            tmp_path=tmp_path,
            original_name="silent.pdf",
            content=b"data",
            note=None,
        )
        zf, manifest, _ = _download_zip(client, regular_user, ws.id)
        assert not any("silent.pdf.md" in n for n in zf.namelist())
        assert manifest["entries"][0]["note_empty"] is True
        assert "note" not in manifest["entries"][0]["zip_paths"]

    def test_backup_does_not_create_extract_assets_dir(self, client, db_session, regular_user, tmp_path):
        ws = ensure_personal_workspace(db_session, regular_user)
        f = _add_published_source(
            db_session,
            user=regular_user,
            workspace_id=ws.id,
            folder_id=None,
            tmp_path=tmp_path,
            original_name="plain.pdf",
            content=b"plain",
        )
        assets_path = os.path.join(os.path.dirname(f.file_path), ".extract_assets", str(f.id))
        assert not os.path.isdir(assets_path)
        _download_zip(client, regular_user, ws.id)
        assert not os.path.isdir(assets_path)

    def test_manifest_total_bytes_includes_self(self, client, db_session, regular_user, tmp_path):
        ws = ensure_personal_workspace(db_session, regular_user)
        _add_published_source(
            db_session,
            user=regular_user,
            workspace_id=ws.id,
            folder_id=None,
            tmp_path=tmp_path,
            original_name="count.pdf",
            content=b"x",
        )
        zf, manifest, _ = _download_zip(client, regular_user, ws.id)
        manifest_name = next(n for n in zf.namelist() if n.endswith("manifest.json"))
        manifest_size = len(zf.read(manifest_name))
        entry_sizes = sum(len(zf.read(n)) for n in zf.namelist())
        assert manifest["total_bytes"] == entry_sizes
        assert manifest["total_bytes"] >= manifest_size


class TestWorkspaceBackupWikiExport:
    def test_wiki_page_with_content(self, client, db_session, regular_user):
        ws = ensure_personal_workspace(db_session, regular_user)
        _add_wiki_page(
            db_session,
            user=regular_user,
            workspace_id=ws.id,
            title="客户画像",
            wiki_slug="customer-profile",
            markdown="# 客户画像\n\n正文",
        )
        zf, manifest, slug_prefix = _download_zip(client, regular_user, ws.id)
        note_path = next(n for n in zf.namelist() if n.endswith("客户画像.md"))
        assert note_path.startswith(slug_prefix)
        assert zf.read(note_path).decode("utf-8") == "# 客户画像\n\n正文"
        entry = next(e for e in manifest["entries"] if e["page_kind"] == "concept")
        assert entry["note_empty"] is False
        assert entry["zip_paths"]["note"] == "客户画像.md"
        assert manifest["file_count"] == 1

    def test_empty_wiki_page_exports_zero_byte_md(self, client, db_session, regular_user, tmp_path):
        ws = ensure_personal_workspace(db_session, regular_user)
        placeholder = tmp_path / "wiki-pages" / "abc123_空主题.md"
        _add_empty_wiki_placeholder(
            db_session,
            user=regular_user,
            workspace_id=ws.id,
            title="空主题",
            wiki_slug="empty-topic",
            placeholder_path=placeholder,
        )
        zf, manifest, _ = _download_zip(client, regular_user, ws.id)
        note_path = next(n for n in zf.namelist() if n.endswith("空主题.md"))
        assert zf.read(note_path) == b""
        entry = manifest["entries"][0]
        assert entry["note_empty"] is True
        assert entry["zip_paths"] == {"note": "空主题.md"}
        assert not any(n.endswith(placeholder.name) for n in zf.namelist())

    def test_wiki_placeholder_file_path_not_exported_as_binary(self, client, db_session, regular_user, tmp_path):
        ws = ensure_personal_workspace(db_session, regular_user)
        placeholder = tmp_path / "wiki-pages" / "deadbeef_占位.md"
        f = _add_empty_wiki_placeholder(
            db_session,
            user=regular_user,
            workspace_id=ws.id,
            title="占位页",
            wiki_slug="placeholder-page",
            placeholder_path=placeholder,
        )
        zf, manifest, _ = _download_zip(client, regular_user, ws.id)
        names = zf.namelist()
        assert any(n.endswith("占位页.md") for n in names)
        assert not any(n.endswith(os.path.basename(f.file_path)) for n in names)
        assert "original" not in manifest["entries"][0]["zip_paths"]
        assert manifest["file_count"] == 1


class TestWorkspaceBackupIntegration:
    def test_duplicate_original_names_get_suffix(self, client, db_session, regular_user, tmp_path):
        ws = ensure_personal_workspace(db_session, regular_user)
        _add_published_source(
            db_session,
            user=regular_user,
            workspace_id=ws.id,
            folder_id=None,
            tmp_path=tmp_path,
            original_name="dup.pdf",
            content=b"first",
        )
        _add_published_source(
            db_session,
            user=regular_user,
            workspace_id=ws.id,
            folder_id=None,
            tmp_path=tmp_path / "b",
            original_name="dup.pdf",
            content=b"second",
        )
        zf, manifest, _ = _download_zip(client, regular_user, ws.id)
        names = [n for n in zf.namelist() if n.endswith(".pdf") and not n.endswith(".md")]
        assert any(n.endswith("dup.pdf") for n in names)
        assert any("dup (2).pdf" in n for n in names)
        zip_paths = [e["zip_paths"].get("original") for e in manifest["entries"]]
        assert "dup.pdf" in zip_paths
        assert "dup (2).pdf" in zip_paths
        assert manifest["file_count"] == 2

    def test_draft_source_excluded(self, client, db_session, regular_user, tmp_path):
        ws = ensure_personal_workspace(db_session, regular_user)
        blob = tmp_path / "draft.pdf"
        blob.write_bytes(b"draft")
        draft = FileModel(
            user_id=regular_user.id,
            workspace_id=ws.id,
            folder_id=None,
            filename=blob.name,
            original_name="draft.pdf",
            file_path=str(blob),
            file_size=5,
            mime_type="application/pdf",
            publish_status="draft",
            page_kind="source",
        )
        db_session.add(draft)
        _add_published_source(
            db_session,
            user=regular_user,
            workspace_id=ws.id,
            folder_id=None,
            tmp_path=tmp_path / "pub",
            original_name="pub.pdf",
            content=b"pub",
        )
        zf, manifest, _ = _download_zip(client, regular_user, ws.id)
        assert manifest["file_count"] == 1
        assert manifest["entries"][0]["original_name"] == "pub.pdf"
        assert not any("draft.pdf" in n for n in zf.namelist())

    def test_too_large_returns_413_and_no_audit_log(self, client, db_session, regular_user, tmp_path, monkeypatch):
        ws = ensure_personal_workspace(db_session, regular_user)
        monkeypatch.setattr(
            "services.workspace_backup_service.get_workspace_backup_max_bytes",
            lambda _db: 50,
        )
        created_paths: list[str] = []
        real_ntf = tempfile.NamedTemporaryFile

        def tracking_ntf(*args, **kwargs):
            tmp = real_ntf(*args, **kwargs)
            created_paths.append(tmp.name)
            return tmp

        monkeypatch.setattr("services.workspace_backup_service.tempfile.NamedTemporaryFile", tracking_ntf)
        _add_published_source(
            db_session,
            user=regular_user,
            workspace_id=ws.id,
            folder_id=None,
            tmp_path=tmp_path,
            original_name="big.pdf",
            content=b"x" * 200,
        )
        before = db_session.query(OperationLog).filter(OperationLog.user_id == regular_user.id).count()
        r = client.get(f"/api/workspaces/{ws.id}/backup", headers=_auth_header(regular_user))
        after = db_session.query(OperationLog).filter(OperationLog.user_id == regular_user.id).count()
        assert r.status_code == 413, r.text
        body = r.json()
        assert body["detail"]["code"] == WORKSPACE_BACKUP_TOO_LARGE
        assert body["detail"]["total_bytes"] > body["detail"]["max_bytes"]
        assert body["detail"]["max_bytes"] == 50
        assert body["detail"]["file_count"] == 1
        assert after == before
        assert created_paths == []

    def test_cross_type_sidecar_wiki_name_collision(self, client, db_session, regular_user, tmp_path):
        ws = ensure_personal_workspace(db_session, regular_user)
        _add_published_source(
            db_session,
            user=regular_user,
            workspace_id=ws.id,
            folder_id=None,
            tmp_path=tmp_path,
            original_name="doc.pdf",
            content=b"pdf",
            note="# source note",
        )
        _add_wiki_page(
            db_session,
            user=regular_user,
            workspace_id=ws.id,
            title="doc.pdf",
            wiki_slug="doc-pdf-wiki",
            markdown="# wiki note",
        )
        zf, manifest, _ = _download_zip(client, regular_user, ws.id)
        md_entries = [n for n in zf.namelist() if n.endswith(".md") and not n.endswith("manifest.json")]
        assert any(n.endswith("doc.pdf.md") for n in md_entries)
        assert any("doc.pdf (2).md" in n for n in md_entries)
        zip_notes = [
            e["zip_paths"].get("note")
            for e in manifest["entries"]
            if e.get("zip_paths", {}).get("note")
        ]
        assert "doc.pdf.md" in zip_notes
        assert "doc.pdf (2).md" in zip_notes

    def test_okf_reserved_role_in_manifest(self, client, db_session, regular_user, tmp_path):
        ws = ensure_personal_workspace(db_session, regular_user)
        f = _add_published_source(
            db_session,
            user=regular_user,
            workspace_id=ws.id,
            folder_id=None,
            tmp_path=tmp_path,
            original_name="okf-index.pdf",
            content=b"okf",
        )
        f.okf_reserved_role = "index"
        db_session.commit()
        _, manifest, _ = _download_zip(client, regular_user, ws.id)
        entry = next(e for e in manifest["entries"] if e.get("okf_reserved_role") == "index")
        assert entry["page_kind"] == "source"
        assert entry["original_name"] == "okf-index.pdf"

    def test_backup_includes_okf_tree_sidecar(self, client, db_session, regular_user, tmp_path):
        """112 plan Step 4：workspace backup 经 read_md_note_text 读取 okf 树 sidecar。"""
        ws = ensure_personal_workspace(db_session, regular_user)
        blob = tmp_path / "okf-backup.pdf"
        blob.write_bytes(b"%PDF")
        f = FileModel(
            user_id=regular_user.id,
            workspace_id=ws.id,
            folder_id=None,
            filename=blob.name,
            original_name="okf-backup.pdf",
            file_path=str(blob),
            file_size=4,
            mime_type="application/pdf",
            md5_hash="d" * 32,
            publish_status="published",
            page_kind="source",
        )
        db_session.add(f)
        db_session.flush()
        cp = _default_concept_path(db_session, f)
        create_okf_note_shell(f, concept_path=cp)
        save_okf_body_for_file(f, "# okf tree backup note\n")
        db_session.commit()
        db_session.refresh(f)

        assert f"/{ws.id}/okf/" in (f.md_file_path or "").replace("\\", "/")
        assert "# okf tree backup note" in (read_md_note_text(f) or "")

        zf, manifest, slug_prefix = _download_zip(client, regular_user, ws.id)
        note_rel = manifest["entries"][0]["zip_paths"].get("note")
        assert note_rel
        note_bytes = zf.read(f"{slug_prefix}{note_rel}")
        assert "# okf tree backup note" in note_bytes.decode("utf-8")

    def test_success_writes_audit_log(self, client, db_session, regular_user, tmp_path):
        ws = ensure_personal_workspace(db_session, regular_user)
        _add_published_source(
            db_session,
            user=regular_user,
            workspace_id=ws.id,
            folder_id=None,
            tmp_path=tmp_path,
            original_name="audit.pdf",
            content=b"x",
        )
        before = db_session.query(OperationLog).filter(OperationLog.user_id == regular_user.id).count()
        _download_zip(client, regular_user, ws.id)
        row = (
            db_session.query(OperationLog)
            .filter(OperationLog.user_id == regular_user.id, OperationLog.action == "备份下载")
            .order_by(OperationLog.id.desc())
            .first()
        )
        assert row is not None
        assert row.target_type == "workspace"
        assert row.target_id == ws.id
        assert f"slug={ws.slug}" in (row.detail or "")
        assert db_session.query(OperationLog).filter(OperationLog.user_id == regular_user.id).count() == before + 1

    def test_download_filename_uses_username(self, client, db_session, regular_user, tmp_path):
        ws = ensure_personal_workspace(db_session, regular_user)
        _add_published_source(
            db_session,
            user=regular_user,
            workspace_id=ws.id,
            folder_id=None,
            tmp_path=tmp_path,
            original_name="name.pdf",
            content=b"x",
        )
        r = client.get(f"/api/workspaces/{ws.id}/backup", headers=_auth_header(regular_user))
        assert r.status_code == 200, r.text
        cd = r.headers.get("content-disposition", "")
        assert "testuser-backup-" in cd
        assert cd.endswith('.zip"') or cd.endswith(".zip")

    def test_manifest_exported_by_username(self, client, db_session, regular_user, tmp_path):
        ws = ensure_personal_workspace(db_session, regular_user)
        _add_published_source(
            db_session,
            user=regular_user,
            workspace_id=ws.id,
            folder_id=None,
            tmp_path=tmp_path,
            original_name="who.pdf",
            content=b"x",
        )
        _, manifest, _ = _download_zip(client, regular_user, ws.id)
        assert manifest["exported_by_username"] == "testuser"
        assert manifest["exported_by_user_id"] == regular_user.id

    def test_estimate_total_bytes_not_below_written_zip(self, db_session, regular_user, tmp_path):
        from services.workspace_backup_service import build_workspace_backup_zip, estimate_workspace_backup

        ws = ensure_personal_workspace(db_session, regular_user)
        _add_published_source(
            db_session,
            user=regular_user,
            workspace_id=ws.id,
            folder_id=None,
            tmp_path=tmp_path,
            original_name="est.pdf",
            content=b"hello",
            note="# note",
        )
        plan = estimate_workspace_backup(db_session, regular_user, ws)
        result = build_workspace_backup_zip(db_session, regular_user, ws)
        try:
            assert plan.total_bytes >= result.total_bytes
        finally:
            if os.path.isfile(result.zip_path):
                os.unlink(result.zip_path)

    def test_success_unlinks_temp_zip_after_response(
        self, client, db_session, regular_user, tmp_path, monkeypatch
    ):
        ws = ensure_personal_workspace(db_session, regular_user)
        created_paths: list[str] = []
        real_ntf = tempfile.NamedTemporaryFile

        def tracking_ntf(*args, **kwargs):
            tmp = real_ntf(*args, **kwargs)
            created_paths.append(tmp.name)
            return tmp

        monkeypatch.setattr("services.workspace_backup_service.tempfile.NamedTemporaryFile", tracking_ntf)
        _add_published_source(
            db_session,
            user=regular_user,
            workspace_id=ws.id,
            folder_id=None,
            tmp_path=tmp_path,
            original_name="unlink.pdf",
            content=b"ok",
        )
        r = client.get(f"/api/workspaces/{ws.id}/backup", headers=_auth_header(regular_user))
        assert r.status_code == 200, r.text
        assert len(created_paths) == 1
        assert not os.path.isfile(created_paths[0])


class TestWorkspaceBackupMaxSetting:
    def test_get_workspace_backup_max_bytes_uses_db_row(self, db_session):
        from models.system_setting import SystemSetting
        from services.system_setting_service import (
            KEY_WORKSPACE_BACKUP_MAX_MB,
            get_workspace_backup_max_bytes,
            invalidate_settings_cache,
        )

        db_session.add(SystemSetting(setting_key=KEY_WORKSPACE_BACKUP_MAX_MB, value="42"))
        db_session.commit()
        invalidate_settings_cache()
        assert get_workspace_backup_max_bytes(db_session) == 42 * 1024 * 1024

    def test_get_workspace_backup_max_bytes_env_fallback(self, db_session, monkeypatch):
        from services.system_setting_service import get_workspace_backup_max_bytes, invalidate_settings_cache

        invalidate_settings_cache()
        monkeypatch.setattr("config.WORKSPACE_BACKUP_MAX_BYTES", 51200)
        assert get_workspace_backup_max_bytes(db_session) == 51200

    def test_system_setting_controls_413_threshold(self, client, db_session, regular_user, tmp_path):
        from models.system_setting import SystemSetting
        from services.system_setting_service import KEY_WORKSPACE_BACKUP_MAX_MB, invalidate_settings_cache

        ws = ensure_personal_workspace(db_session, regular_user)
        db_session.add(SystemSetting(setting_key=KEY_WORKSPACE_BACKUP_MAX_MB, value="1"))
        db_session.commit()
        invalidate_settings_cache()
        _add_published_source(
            db_session,
            user=regular_user,
            workspace_id=ws.id,
            folder_id=None,
            tmp_path=tmp_path,
            original_name="big.pdf",
            content=b"x" * (1024 * 1024 + 100),
        )
        r = client.get(f"/api/workspaces/{ws.id}/backup", headers=_auth_header(regular_user))
        assert r.status_code == 413, r.text
        detail = r.json()["detail"]
        assert detail["file_count"] == 1
        assert detail["total_bytes"] > detail["max_bytes"]
