# Copyright (c) 2026 徐泽宇
"""OKF import/export integration tests."""

from __future__ import annotations

import io
import zipfile
from pathlib import Path
from unittest.mock import patch

from models.file import File as FileModel
from services.md_note_service import read_md_note_text
from services.md_paths import is_legacy_flat_md_note_path
from services.workspace_service import create_shared_workspace, ensure_personal_workspace, set_member_role

FIXTURE_ROOT = Path(__file__).resolve().parent / "fixtures" / "okf" / "minimal_bundle"


def _zip_dir(root: Path) -> bytes:
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", compression=zipfile.ZIP_DEFLATED) as zf:
        for path in root.rglob("*"):
            if path.is_file():
                zf.write(path, path.relative_to(root).as_posix())
    return buf.getvalue()


@patch("services.kb_index_service.enqueue_index")
def test_okf_validate_minimal(mock_enqueue, client, jwt_token):
    mock_enqueue.return_value = None
    h = {"Authorization": f"Bearer {jwt_token}"}
    data = _zip_dir(FIXTURE_ROOT)
    r = client.post(
        "/api/knowledge-base/okf/validate",
        headers=h,
        files={"bundle": ("minimal.zip", data, "application/zip")},
    )
    assert r.status_code == 200
    body = r.json()
    assert body["conformant"] is True
    assert body["concept_count"] >= 3


@patch("services.kb_index_service.enqueue_index")
def test_okf_import_writes_okf_tree(mock_enqueue, client, db_session, regular_user, jwt_token):
    """SC-112-006 / FR-112-005：import 新 concept 写入 uploads/{ws}/okf/ 树。"""
    mock_enqueue.return_value = None
    personal = ensure_personal_workspace(db_session, regular_user)
    h = {"Authorization": f"Bearer {jwt_token}"}
    zip_bytes = _zip_dir(FIXTURE_ROOT)

    imp = client.post(
        "/api/knowledge-base/okf/import",
        headers=h,
        data={"workspace_id": str(personal.id)},
        files={"bundle": ("minimal.zip", zip_bytes, "application/zip")},
    )
    assert imp.status_code == 200, imp.text

    rows = (
        db_session.query(FileModel)
        .filter(
            FileModel.workspace_id == personal.id,
            FileModel.okf_concept_path.isnot(None),
            FileModel.has_md.is_(True),
        )
        .all()
    )
    assert len(rows) >= 1
    for row in rows:
        assert row.md_file_path
        norm = row.md_file_path.replace("\\", "/")
        assert f"/{personal.id}/okf/" in norm
        assert is_legacy_flat_md_note_path(row.md_file_path) is False


@patch("services.kb_index_service.enqueue_index")
def test_okf_import_export_roundtrip(mock_enqueue, client, db_session, regular_user, jwt_token):
    mock_enqueue.return_value = None
    personal = ensure_personal_workspace(db_session, regular_user)
    h = {"Authorization": f"Bearer {jwt_token}"}
    zip_bytes = _zip_dir(FIXTURE_ROOT)

    imp = client.post(
        "/api/knowledge-base/okf/import",
        headers=h,
        data={"workspace_id": str(personal.id)},
        files={"bundle": ("minimal.zip", zip_bytes, "application/zip")},
    )
    assert imp.status_code == 200, imp.text
    report = imp.json()
    assert report["concepts_created"] >= 3
    assert report["log_entries_imported"] >= 1

    rows = (
        db_session.query(FileModel)
        .filter(
            FileModel.workspace_id == personal.id,
            FileModel.okf_concept_path.isnot(None),
        )
        .all()
    )
    assert len(rows) >= 3

    graph = client.get(
        "/api/knowledge-base/link-graph",
        headers=h,
        params={"workspace_id": personal.id},
    )
    assert graph.status_code == 200
    assert len(graph.json().get("links") or []) > 0

    exp = client.get(
        "/api/knowledge-base/okf/export",
        headers=h,
        params={"workspace_id": personal.id},
    )
    assert exp.status_code == 200
    assert exp.headers.get("content-type", "").startswith("application/zip")

    zf = zipfile.ZipFile(io.BytesIO(exp.content))
    names = zf.namelist()
    assert any(n.endswith("tables/orders.md") for n in names)
    root_index = zf.read("index.md").decode("utf-8")
    assert 'okf_version: "0.1"' in root_index or "okf_version: '0.1'" in root_index


@patch("services.kb_index_service.enqueue_index")
def test_okf_import_dry_run(mock_enqueue, client, db_session, regular_user, jwt_token):
    mock_enqueue.return_value = None
    personal = ensure_personal_workspace(db_session, regular_user)
    h = {"Authorization": f"Bearer {jwt_token}"}
    before = (
        db_session.query(FileModel)
        .filter(FileModel.workspace_id == personal.id, FileModel.okf_concept_path.isnot(None))
        .count()
    )
    r = client.post(
        "/api/knowledge-base/okf/import",
        headers=h,
        data={"workspace_id": str(personal.id), "dry_run": "true"},
        files={"bundle": ("minimal.zip", _zip_dir(FIXTURE_ROOT), "application/zip")},
    )
    assert r.status_code == 200
    body = r.json()
    assert body["dry_run"] is True
    assert body["concepts_created"] >= 3
    after = (
        db_session.query(FileModel)
        .filter(FileModel.workspace_id == personal.id, FileModel.okf_concept_path.isnot(None))
        .count()
    )
    assert after == before


@patch("services.kb_index_service.enqueue_index")
def test_okf_import_log_idempotent(mock_enqueue, client, db_session, regular_user, jwt_token):
    mock_enqueue.return_value = None
    personal = ensure_personal_workspace(db_session, regular_user)
    h = {"Authorization": f"Bearer {jwt_token}"}
    zip_bytes = _zip_dir(FIXTURE_ROOT)
    imp1 = client.post(
        "/api/knowledge-base/okf/import",
        headers=h,
        data={"workspace_id": str(personal.id)},
        files={"bundle": ("minimal.zip", zip_bytes, "application/zip")},
    )
    assert imp1.status_code == 200
    assert imp1.json()["log_entries_imported"] >= 1
    imp2 = client.post(
        "/api/knowledge-base/okf/import",
        headers=h,
        data={"workspace_id": str(personal.id)},
        files={"bundle": ("minimal.zip", zip_bytes, "application/zip")},
    )
    assert imp2.status_code == 200
    assert imp2.json()["log_entries_imported"] == 0


@patch("services.kb_index_service.enqueue_index")
def test_okf_export_folder_subtree(mock_enqueue, client, db_session, regular_user, jwt_token):
    mock_enqueue.return_value = None
    from models.folder import Folder

    personal = ensure_personal_workspace(db_session, regular_user)
    h = {"Authorization": f"Bearer {jwt_token}"}
    client.post(
        "/api/knowledge-base/okf/import",
        headers=h,
        data={"workspace_id": str(personal.id)},
        files={"bundle": ("minimal.zip", _zip_dir(FIXTURE_ROOT), "application/zip")},
    )
    tables_folder = (
        db_session.query(Folder)
        .filter(Folder.workspace_id == personal.id, Folder.name == "tables")
        .first()
    )
    assert tables_folder is not None

    exp = client.get(
        "/api/knowledge-base/okf/export",
        headers=h,
        params={"workspace_id": personal.id, "folder_id": tables_folder.id},
    )
    assert exp.status_code == 200
    names = zipfile.ZipFile(io.BytesIO(exp.content)).namelist()
    assert any(n.endswith("tables/orders.md") for n in names)
    assert not any(n.endswith("datasets/sales.md") for n in names)


@patch("services.kb_index_service.enqueue_index")
def test_okf_export_include_sources(mock_enqueue, client, db_session, regular_user, jwt_token, tmp_path):
    mock_enqueue.return_value = None
    import hashlib
    import os

    from config import UPLOAD_DIR
    from models.file import File as FileModel
    from services.file_service import get_mime_type
    from services.md_note_service import save_md_note_for_file

    personal = ensure_personal_workspace(db_session, regular_user)
    rel = os.path.join(str(regular_user.id), "okf-test", "plain.txt")
    full = Path(UPLOAD_DIR) / rel
    full.parent.mkdir(parents=True, exist_ok=True)
    full.write_bytes(b"hello source")
    md5 = hashlib.md5(b"hello source").hexdigest()
    src = FileModel(
        user_id=regular_user.id,
        workspace_id=personal.id,
        filename="plain.txt",
        original_name="plain.txt",
        file_path=str(full),
        file_size=12,
        mime_type=get_mime_type("plain.txt") or "text/plain",
        md5_hash=md5,
        has_md=False,
        page_kind="source",
        index_status="skipped",
    )
    db_session.add(src)
    db_session.flush()
    save_md_note_for_file(db_session, regular_user.id, src, "# Source note\n", enqueue_vector_index=False)
    db_session.commit()

    h = {"Authorization": f"Bearer {jwt_token}"}
    exp = client.get(
        "/api/knowledge-base/okf/export",
        headers=h,
        params={"workspace_id": personal.id, "include_sources": "true"},
    )
    assert exp.status_code == 200
    names = zipfile.ZipFile(io.BytesIO(exp.content)).namelist()
    assert any(n.startswith(f"sources/{src.id}.md") for n in names)


@patch("services.kb_index_service.enqueue_index")
def test_okf_validate_broken_link_warning(mock_enqueue, client, jwt_token, tmp_path):
    mock_enqueue.return_value = None
    bundle = tmp_path / "broken"
    bundle.mkdir()
    (bundle / "a.md").write_text(
        "---\ntype: Concept\n---\n\nSee [missing](/no/such.md).\n",
        encoding="utf-8",
    )
    h = {"Authorization": f"Bearer {jwt_token}"}
    r = client.post(
        "/api/knowledge-base/okf/validate",
        headers=h,
        files={"bundle": ("broken.zip", _zip_dir(bundle), "application/zip")},
    )
    assert r.status_code == 200
    body = r.json()
    assert body["conformant"] is True
    assert any("断链" in w or "no/such" in w for w in body.get("warnings") or [])


@patch("services.kb_index_service.enqueue_index")
def test_okf_import_contributor_forbidden(mock_enqueue, client, db_session, regular_user, jwt_token):
    mock_enqueue.return_value = None
    from services.auth_service import create_access_token
    from services.system_setting_service import KEY_SHARED_WORKSPACES_ENABLED, update_settings
    from tests.conftest import _create_user

    update_settings(db_session, {KEY_SHARED_WORKSPACES_ENABLED: "true"})
    contributor = _create_user(db_session, "okf_contrib")
    shared = create_shared_workspace(db_session, name="okf-acl", owner=regular_user)
    set_member_role(db_session, shared.id, contributor.id, "contributor")
    db_session.commit()

    ch = {"Authorization": f"Bearer {create_access_token(contributor.id, contributor.password_rev)}"}
    data = _zip_dir(FIXTURE_ROOT)
    r = client.post(
        "/api/knowledge-base/okf/import",
        headers=ch,
        data={"workspace_id": str(shared.id)},
        files={"bundle": ("minimal.zip", data, "application/zip")},
    )
    assert r.status_code == 403

    val = client.post(
        "/api/knowledge-base/okf/validate",
        headers=ch,
        data={"workspace_id": str(shared.id)},
        files={"bundle": ("minimal.zip", data, "application/zip")},
    )
    assert val.status_code == 200


@patch("services.okf.import_service.OKF_IMPORT_REWRITE_LINKS", False)
@patch("services.kb_index_service.enqueue_index")
def test_okf_import_preserves_okf_links_when_rewrite_disabled(
    mock_enqueue, client, db_session, regular_user, jwt_token
):
    mock_enqueue.return_value = None
    personal = ensure_personal_workspace(db_session, regular_user)
    h = {"Authorization": f"Bearer {jwt_token}"}
    imp = client.post(
        "/api/knowledge-base/okf/import",
        headers=h,
        data={"workspace_id": str(personal.id)},
        files={"bundle": ("minimal.zip", _zip_dir(FIXTURE_ROOT), "application/zip")},
    )
    assert imp.status_code == 200, imp.text

    orders = (
        db_session.query(FileModel)
        .filter(
            FileModel.workspace_id == personal.id,
            FileModel.okf_concept_path == "tables/orders",
        )
        .first()
    )
    assert orders is not None
    body = read_md_note_text(orders) or ""
    assert "/tables/customers.md" in body
    assert "[[file:" not in body

    graph = client.get(
        "/api/knowledge-base/link-graph",
        headers=h,
        params={"workspace_id": personal.id},
    )
    assert graph.status_code == 200
    assert len(graph.json().get("links") or []) > 0
