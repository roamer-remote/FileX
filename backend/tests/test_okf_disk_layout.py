# Copyright (c) 2026 徐泽宇
"""112 OKF disk layout: sidecar paths under uploads/{ws}/okf/."""

from __future__ import annotations

import os
from unittest.mock import patch

from config import UPLOAD_DIR
from models.file import File as FileModel
from services.md_note_service import save_md_note_for_file
from services.md_paths import (
    content_list_json_path,
    is_legacy_flat_md_note_path,
    md_note_path,
    okf_sidecar_path,
    resolve_concept_sidecar_path,
)
from services.okf.frontmatter import split_frontmatter
from services.okf.paths import relpath_from_concept_id
from services.okf_note_service import create_okf_note_shell, read_okf_raw_for_file


def _okf_sidecar_for_upload(data: dict) -> str:
    return okf_sidecar_path(data["workspace_id"], data["okf_concept_path"])


def test_upload_writes_okf_tree_sidecar(client, jwt_token):
    """SC-112-001: new upload sidecar lives under uploads/{ws}/okf/sources/.../*.md."""
    body = "# Title\n\nHello.\n"
    with patch("services.kb_index_service.publish_index_job"):
        r = client.post(
            "/api/files/upload",
            headers={"Authorization": f"Bearer {jwt_token}"},
            files={"file": ("photo.png", b"\x89PNG\r\n\x1a\n", "image/png")},
        )
    assert r.status_code == 200, r.text
    data = r.json()
    sidecar = _okf_sidecar_for_upload(data)
    assert os.path.isfile(sidecar)
    assert f"/{data['workspace_id']}/okf/" in sidecar.replace("\\", "/")
    assert not os.path.isfile(md_note_path(data["id"]))
    meta, note_body = split_frontmatter(open(sidecar, encoding="utf-8").read())
    assert meta["type"] == "FileX Source"
    assert meta["filex"]["file_id"] == data["id"]
    assert note_body == ""


def test_md_file_path_points_to_okf_tree(client, jwt_token, db_session):
    """SC-112-002: md_file_path and GET /okf/raw match on-disk okf tree."""
    body = "# Body\n\nplain.\n"
    with patch("services.kb_index_service.publish_index_job"):
        r = client.post(
            "/api/files/upload",
            headers={"Authorization": f"Bearer {jwt_token}"},
            files={"file": ("note.md", body.encode("utf-8"), "text/markdown")},
        )
    assert r.status_code == 200
    data = r.json()
    file_id = data["id"]
    sidecar = _okf_sidecar_for_upload(data)

    f = db_session.query(FileModel).filter(FileModel.id == file_id).one()
    assert f.md_file_path
    assert is_legacy_flat_md_note_path(f.md_file_path) is False
    assert "/okf/" in f.md_file_path.replace("\\", "/")
    assert os.path.isfile(sidecar)

    raw_api = client.get(
        f"/api/files/{file_id}/okf",
        headers={"Authorization": f"Bearer {jwt_token}"},
    )
    assert raw_api.status_code == 200
    assert raw_api.text == open(sidecar, encoding="utf-8").read()


def test_legacy_md_notes_readonly_fallback(db_session, regular_user, tmp_path):
    """SC-112-005: legacy .md_notes/{id}.md readable; new shell writes okf tree."""
    legacy_path = md_note_path(88001)
    legacy_body = (
        "---\n"
        "type: FileX Source\n"
        "title: Legacy\n"
        "okf_version: '0.1'\n"
        "---\n"
        "Legacy body\n"
    )
    os.makedirs(os.path.dirname(legacy_path), exist_ok=True)
    with open(legacy_path, "w", encoding="utf-8") as fh:
        fh.write(legacy_body)

    f = FileModel(
        id=88001,
        user_id=regular_user.id,
        workspace_id=1,
        folder_id=None,
        filename="legacy.pdf",
        original_name="legacy.pdf",
        file_path=str(tmp_path / "legacy.pdf"),
        file_size=100,
        mime_type="application/pdf",
        md5_hash="0" * 32,
        has_md=True,
        md_file_path=legacy_path,
        okf_concept_path="sources/uncategorized/legacy",
        page_kind="source",
    )
    db_session.add(f)
    db_session.flush()

    assert resolve_concept_sidecar_path(f) == legacy_path
    assert read_okf_raw_for_file(f) == legacy_body

    new_file = FileModel(
        id=88002,
        user_id=regular_user.id,
        workspace_id=1,
        folder_id=None,
        filename="new.pdf",
        original_name="new.pdf",
        file_path=str(tmp_path / "new.pdf"),
        file_size=100,
        mime_type="application/pdf",
        md5_hash="1" * 32,
        has_md=False,
        md_file_path=None,
        page_kind="source",
    )
    create_okf_note_shell(new_file, concept_path="sources/uncategorized/new")
    okf_path = okf_sidecar_path(1, "sources/uncategorized/new")
    assert os.path.isfile(okf_path)
    assert not os.path.isfile(md_note_path(88002))
    assert new_file.md_file_path == okf_path


def test_content_list_stays_flat_md_notes(client, jwt_token):
    """SC-112-007: content_list.json remains under .md_notes/, not okf tree."""
    with patch("services.kb_index_service.publish_index_job"):
        r = client.post(
            "/api/files/upload",
            headers={"Authorization": f"Bearer {jwt_token}"},
            files={"file": ("doc.pdf", b"%PDF-1.4\n", "application/pdf")},
        )
    assert r.status_code == 200
    file_id = r.json()["id"]
    cl_path = content_list_json_path(file_id)
    assert "/.md_notes/" in cl_path.replace("\\", "/")
    assert "/okf/" not in cl_path.replace("\\", "/")


def test_save_md_note_for_file_rejects_okf_native(db_session, regular_user, tmp_path):
    f = FileModel(
        id=88003,
        user_id=regular_user.id,
        workspace_id=1,
        folder_id=None,
        filename="native.pdf",
        original_name="native.pdf",
        file_path=str(tmp_path / "native.pdf"),
        file_size=100,
        mime_type="application/pdf",
        md5_hash="2" * 32,
        has_md=False,
        md_file_path=None,
        page_kind="source",
    )
    create_okf_note_shell(f, concept_path="sources/uncategorized/native")
    try:
        save_md_note_for_file(db_session, regular_user.id, f, "# blocked\n", enqueue_vector_index=False)
        assert False, "expected ValueError"
    except ValueError as exc:
        assert "save_okf_body_for_file" in str(exc)


def test_save_md_note_blocks_import_style_okf_concept_path(db_session, regular_user, tmp_path):
    """Major #1：has_md=False + okf_concept_path 时禁止写 .md_notes/{id}.md。"""
    f = FileModel(
        id=88004,
        user_id=regular_user.id,
        workspace_id=1,
        folder_id=None,
        filename="imported.md",
        original_name="imported.md",
        file_path=str(tmp_path / "imported.md"),
        file_size=10,
        mime_type="text/markdown",
        md5_hash="3" * 32,
        has_md=False,
        md_file_path=None,
        okf_concept_path="sources/imported/note",
        page_kind="source",
    )
    try:
        save_md_note_for_file(db_session, regular_user.id, f, "# import body\n", enqueue_vector_index=False)
        assert False, "expected ValueError"
    except ValueError:
        pass
    assert not os.path.isfile(md_note_path(f.id))


def test_put_okf_meta_relocates_sidecar_to_new_okf_path(client, jwt_token, db_session):
    """FR-112-004(a)：显式改 concept_path 时 sidecar 搬迁至新 okf 路径。"""
    body = "# Body\n"
    with patch("services.kb_index_service.publish_index_job"):
        r = client.post(
            "/api/files/upload",
            headers={"Authorization": f"Bearer {jwt_token}"},
            files={"file": ("relocate.md", body.encode("utf-8"), "text/markdown")},
        )
    assert r.status_code == 200
    data = r.json()
    file_id = data["id"]
    old_path = _okf_sidecar_for_upload(data)

    r = client.put(
        f"/api/files/{file_id}/okf/meta",
        headers={"Authorization": f"Bearer {jwt_token}"},
        json={"okf_concept_path": "sources/research/relocated-title"},
    )
    assert r.status_code == 200, r.text

    new_path = okf_sidecar_path(data["workspace_id"], "sources/research/relocated-title")
    f = db_session.query(FileModel).filter(FileModel.id == file_id).one()
    assert f.md_file_path == new_path
    assert os.path.isfile(new_path)
    assert not os.path.isfile(old_path)
    meta, saved_body = split_frontmatter(open(new_path, encoding="utf-8").read())
    assert meta["filex"].get("concept_path_custom") is True
    assert saved_body == body


def test_okf_sidecar_path_formula():
    path = okf_sidecar_path(2, "sources/uncategorized/photo-1")
    expected = os.path.join(UPLOAD_DIR, "2", "okf", "sources", "uncategorized", "photo-1.md")
    assert path == expected


def _auth(jwt_token):
    return {"Authorization": f"Bearer {jwt_token}"}


def test_relocate_sidecar_service_direct(db_session, regular_user, tmp_path):
    """Direct service test: folder change removes old sidecar path."""
    from models.folder import Folder
    from services.okf_note_service import (
        create_okf_note_shell,
        maybe_relocate_okf_sidecar_on_folder_change,
        _default_concept_path,
    )
    from services.workspace_service import ensure_personal_workspace

    ws = ensure_personal_workspace(db_session, regular_user)
    fa = Folder(name="FolderA", workspace_id=ws.id, user_id=regular_user.id)
    fb = Folder(name="FolderB", workspace_id=ws.id, user_id=regular_user.id)
    db_session.add_all([fa, fb])
    db_session.flush()

    f = FileModel(
        user_id=regular_user.id,
        workspace_id=ws.id,
        folder_id=fa.id,
        filename="doc.pdf",
        original_name="doc.pdf",
        file_path=str(tmp_path / "doc.pdf"),
        file_size=4,
        mime_type="application/pdf",
        md5_hash="a" * 32,
        has_md=False,
    )
    db_session.add(f)
    db_session.flush()
    cp = _default_concept_path(db_session, f)
    create_okf_note_shell(f, concept_path=cp)
    old_path = f.md_file_path
    assert os.path.isfile(old_path)

    f.folder_id = fb.id
    maybe_relocate_okf_sidecar_on_folder_change(
        db_session, f, new_folder_id=fb.id, previous_folder_id=fa.id
    )
    db_session.commit()

    assert f.md_file_path != old_path
    assert os.path.isfile(f.md_file_path)
    assert not os.path.isfile(old_path), f"old still exists: {old_path}"


def test_folder_move_relocates_default_concept_path(client, jwt_token, db_session):
    """SC-112-003：非 custom path 时 folder_id 变更触发 sidecar 搬迁。"""
    h = _auth(jwt_token)
    r_a = client.post("/api/folders", json={"name": "FolderA"}, headers=h)
    assert r_a.status_code == 201, r_a.text
    folder_a = r_a.json()["id"]
    r_b = client.post("/api/folders", json={"name": "FolderB"}, headers=h)
    assert r_b.status_code == 201
    folder_b = r_b.json()["id"]

    with patch("services.kb_index_service.publish_index_job"):
        r = client.post(
            "/api/files/upload",
            headers=h,
            files={"file": ("doc.pdf", b"%PDF-1.4", "application/pdf")},
            data={"folder_id": str(folder_a)},
        )
    assert r.status_code == 200, r.text
    data = r.json()
    file_id = data["id"]
    ws_id = data["workspace_id"]
    f_before = db_session.query(FileModel).filter(FileModel.id == file_id).one()
    old_sidecar = f_before.md_file_path
    assert os.path.isfile(old_sidecar)
    assert "FolderA" in old_sidecar.replace("\\", "/")

    r_move = client.put(f"/api/files/{file_id}", json={"folder_id": folder_b}, headers=h)
    assert r_move.status_code == 200, r_move.text

    f = db_session.query(FileModel).filter(FileModel.id == file_id).one()
    new_sidecar = okf_sidecar_path(ws_id, f.okf_concept_path)
    assert f.md_file_path == new_sidecar
    assert os.path.isfile(new_sidecar)
    assert not os.path.isfile(old_sidecar)
    assert "FolderB" in new_sidecar.replace("\\", "/")
    meta, _ = split_frontmatter(open(new_sidecar, encoding="utf-8").read())
    assert meta["filex"].get("concept_path_custom") is not True


def test_custom_concept_path_frozen_on_folder_move(client, jwt_token, db_session):
    """SC-112-003：concept_path_custom=true 时 folder 移动不搬迁 path。"""
    h = _auth(jwt_token)
    r_a = client.post("/api/folders", json={"name": "SrcFolder"}, headers=h)
    r_b = client.post("/api/folders", json={"name": "DstFolder"}, headers=h)
    folder_a = r_a.json()["id"]
    folder_b = r_b.json()["id"]

    with patch("services.kb_index_service.publish_index_job"):
        r = client.post(
            "/api/files/upload",
            headers=h,
            files={"file": ("freeze.pdf", b"%PDF", "application/pdf")},
            data={"folder_id": str(folder_a)},
        )
    assert r.status_code == 200
    data = r.json()
    file_id = data["id"]
    ws_id = data["workspace_id"]
    custom_path = "sources/frozen/custom-path"

    r_meta = client.put(
        f"/api/files/{file_id}/okf/meta",
        headers=h,
        json={"okf_concept_path": custom_path},
    )
    assert r_meta.status_code == 200, r_meta.text
    frozen_sidecar = okf_sidecar_path(ws_id, custom_path)
    assert os.path.isfile(frozen_sidecar)

    r_move = client.put(f"/api/files/{file_id}", json={"folder_id": folder_b}, headers=h)
    assert r_move.status_code == 200

    f = db_session.query(FileModel).filter(FileModel.id == file_id).one()
    assert f.okf_concept_path == custom_path
    assert f.md_file_path == frozen_sidecar
    assert os.path.isfile(frozen_sidecar)
    meta, _ = split_frontmatter(open(frozen_sidecar, encoding="utf-8").read())
    assert meta["filex"].get("concept_path_custom") is True


def test_folder_rename_relocates_default_concept_path(client, jwt_token, db_session):
    """SC-112-003 建议测：folder 重命名时非 custom sidecar 随 default path 搬迁。"""
    h = _auth(jwt_token)
    r_folder = client.post("/api/folders", json={"name": "OldName"}, headers=h)
    assert r_folder.status_code == 201
    folder_id = r_folder.json()["id"]

    with patch("services.kb_index_service.publish_index_job"):
        r = client.post(
            "/api/files/upload",
            headers=h,
            files={"file": ("rename-me.pdf", b"%PDF", "application/pdf")},
            data={"folder_id": str(folder_id)},
        )
    assert r.status_code == 200
    data = r.json()
    file_id = data["id"]
    ws_id = data["workspace_id"]
    f_before = db_session.query(FileModel).filter(FileModel.id == file_id).one()
    old_sidecar = f_before.md_file_path
    assert "OldName" in old_sidecar.replace("\\", "/")

    r_rename = client.put(f"/api/folders/{folder_id}", json={"name": "NewName"}, headers=h)
    assert r_rename.status_code == 200, r_rename.text

    f = db_session.query(FileModel).filter(FileModel.id == file_id).one()
    new_sidecar = okf_sidecar_path(ws_id, f.okf_concept_path)
    assert f.md_file_path == new_sidecar
    assert os.path.isfile(new_sidecar)
    assert not os.path.isfile(old_sidecar)
    assert "NewName" in new_sidecar.replace("\\", "/")
    assert "OldName" not in new_sidecar.replace("\\", "/")


def test_export_paths_match_on_disk_okf_tree(client, jwt_token, db_session):
    """SC-112-004：export zip 内 concept 相对路径与 on-disk okf 树一致。"""
    import io
    import zipfile

    h = _auth(jwt_token)
    with patch("services.kb_index_service.publish_index_job"):
        r = client.post(
            "/api/files/upload",
            headers=h,
            files={"file": ("export-check.pdf", b"%PDF", "application/pdf")},
        )
    assert r.status_code == 200
    data = r.json()
    ws_id = data["workspace_id"]
    f = db_session.query(FileModel).filter(FileModel.id == data["id"]).one()
    disk_path = okf_sidecar_path(ws_id, f.okf_concept_path)
    assert os.path.isfile(disk_path)
    expected_rel = relpath_from_concept_id(f.okf_concept_path)

    exp = client.get(
        "/api/knowledge-base/okf/export",
        headers=h,
        params={"workspace_id": ws_id},
    )
    assert exp.status_code == 200
    zf = zipfile.ZipFile(io.BytesIO(exp.content))
    assert expected_rel in zf.namelist()
    exported_meta, exported_body = split_frontmatter(zf.read(expected_rel).decode("utf-8"))
    disk_meta, disk_body = split_frontmatter(open(disk_path, encoding="utf-8").read())
    assert exported_body == disk_body
    assert exported_meta.get("type") == disk_meta.get("type")


def test_p112_06_export_synthesizes_index_log_without_upload_persist(client, jwt_token, db_session):
    """P-112-06：新上传不在 okf 根持久化 index/log；export 合成 bundle 根 index.md / log.md。"""
    import io
    import zipfile

    from services.md_paths import okf_workspace_root

    h = _auth(jwt_token)
    with patch("services.kb_index_service.publish_index_job"):
        r = client.post(
            "/api/files/upload",
            headers=h,
            files={"file": ("p112.pdf", b"%PDF", "application/pdf")},
        )
    assert r.status_code == 200
    ws_id = r.json()["workspace_id"]
    okf_root = okf_workspace_root(ws_id)
    assert not os.path.isfile(os.path.join(okf_root, "index.md"))
    assert not os.path.isfile(os.path.join(okf_root, "log.md"))

    exp = client.get(
        "/api/knowledge-base/okf/export",
        headers=h,
        params={"workspace_id": ws_id},
    )
    assert exp.status_code == 200
    names = zipfile.ZipFile(io.BytesIO(exp.content)).namelist()
    assert "log.md" in names
    assert any(n == "index.md" or n.endswith("/index.md") for n in names)
