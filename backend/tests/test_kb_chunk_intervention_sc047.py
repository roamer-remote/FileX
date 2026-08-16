# Copyright (c) 2026 徐泽宇
"""047 T-6: integration tests for SC-047-003～008 acceptance criteria."""

from __future__ import annotations

import os
from unittest.mock import patch


from config import OLLAMA_EMBED_DIM, UPLOAD_DIR
from models.file import File as FileModel
from models.kb_chunk import KbChunk
from models.kb_index_job import KbIndexJob
from services.auth_service import create_access_token
from services.kb_index_service import JOB_DONE, JOB_QUEUED, run_index_job
from services.md_note_service import save_md_note_for_file
from services.system_setting_service import KEY_SHARED_WORKSPACES_ENABLED, update_settings
from services.workspace_service import create_shared_workspace, set_member_role
from tests.conftest import _create_user


def _vec(seed: float = 0.1):
    return [seed] * OLLAMA_EMBED_DIM


def _own_file_and_chunk(db_session, owner, *, workspace_id=None, override=False):
    f = FileModel(
        filename="doc.bin",
        original_name="doc.pdf",
        file_path="/tmp/doc",
        file_size=1,
        mime_type="application/pdf",
        user_id=owner.id,
        workspace_id=workspace_id,
        index_status="ready",
        chunk_count=1,
        kb_index_manual_override=override,
        index_source_hash="hash-047",
    )
    db_session.add(f)
    db_session.commit()
    ch = KbChunk(
        user_id=owner.id,
        workspace_id=workspace_id,
        file_id=f.id,
        chunk_index=0,
        source="sidecar_md",
        text="chunk body",
        char_start=0,
        char_end=10,
        embedding=_vec(),
        embedding_model="test-model",
    )
    db_session.add(ch)
    db_session.commit()
    return f, ch


# SC-047-003
def test_shared_viewer_can_list_chunks_but_patch_404(client, db_session, regular_user, tmp_path):
    update_settings(db_session, {KEY_SHARED_WORKSPACES_ENABLED: "true"})
    viewer = _create_user(db_session, "viewer_sc047")
    shared = create_shared_workspace(db_session, name="SC047 库", owner=regular_user)
    set_member_role(db_session, shared.id, viewer.id, "viewer")
    blob = tmp_path / "shared.bin"
    blob.write_bytes(b"x")
    f = FileModel(
        filename="shared.bin",
        original_name="shared.pdf",
        file_path=str(blob),
        file_size=1,
        mime_type="application/pdf",
        user_id=regular_user.id,
        workspace_id=shared.id,
        index_status="ready",
        chunk_count=1,
        publish_status="published",
    )
    db_session.add(f)
    db_session.commit()
    ch = KbChunk(
        user_id=regular_user.id,
        workspace_id=shared.id,
        file_id=f.id,
        chunk_index=0,
        source="sidecar_md",
        text="shared chunk",
        char_start=0,
        char_end=12,
        embedding=_vec(0.2),
        embedding_model="test-model",
    )
    db_session.add(ch)
    db_session.commit()

    token = create_access_token(viewer.id, viewer.password_rev)
    headers = {"Authorization": f"Bearer {token}"}

    r_get = client.get(f"/api/knowledge-base/files/{f.id}/chunks", headers=headers)
    assert r_get.status_code == 200, r_get.text
    assert r_get.json()["total"] == 1

    r_patch = client.patch(
        f"/api/knowledge-base/files/{f.id}/chunks/{ch.id}",
        json={"text": "viewer edit", "reembed": False},
        headers=headers,
    )
    assert r_patch.status_code == 404


# SC-047-004 endpoint layer
@patch("services.kb_chunk_ops_service.resolve_embedding_vectors")
def test_admin_http_patch_other_users_chunk(mock_resolve, client, admin_jwt_token, db_session, regular_user, admin_user):
    mock_resolve.return_value = [_vec(0.3)]
    f, ch = _own_file_and_chunk(db_session, regular_user)

    r = client.patch(
        f"/api/knowledge-base/files/{f.id}/chunks/{ch.id}",
        json={"text": "admin via http", "reembed": True},
        headers={"Authorization": f"Bearer {admin_jwt_token}"},
    )
    assert r.status_code == 200, r.text
    assert r.json()["text"] == "admin via http"
    db_session.refresh(f)
    assert f.kb_index_manual_override is True


# SC-047-005: override skip on ordinary reindex (integration)
@patch("services.kb_index_service._notify_file_index")
@patch("services.kb_embed_cache_service.embed_texts")
@patch("services.kb_index_service.delete_chunks_for_file")
def test_sc047_005_override_skip_preserves_manual_chunk(
    mock_delete, mock_embed, _mock_notify, db_session, regular_user
):
    os.makedirs(UPLOAD_DIR, exist_ok=True)
    md_path = os.path.join(UPLOAD_DIR, "sc047.md")
    with open(md_path, "w", encoding="utf-8") as fh:
        fh.write("# Title\n\nBody from md.\n")
    f = FileModel(
        filename="x.bin",
        original_name="paper.pdf",
        file_path="/tmp/x",
        file_size=1,
        mime_type="application/pdf",
        user_id=regular_user.id,
        has_md=True,
        md_file_path=md_path,
        index_status="ready",
        index_source_hash="stored",
        chunk_count=1,
        kb_index_manual_override=True,
    )
    db_session.add(f)
    db_session.commit()
    ch = KbChunk(
        user_id=regular_user.id,
        file_id=f.id,
        chunk_index=0,
        source="sidecar_md",
        text="human edited",
        char_start=0,
        char_end=13,
        embedding=_vec(),
        embedding_model="test",
    )
    db_session.add(ch)
    db_session.commit()

    job = KbIndexJob(user_id=f.user_id, file_id=f.id, status=JOB_QUEUED, force=False)
    db_session.add(job)
    db_session.commit()
    run_index_job(db_session, job)
    db_session.commit()
    db_session.refresh(ch)
    db_session.refresh(job)

    assert job.status == JOB_DONE
    assert ch.text == "human edited"
    mock_delete.assert_not_called()
    mock_embed.assert_not_called()


# SC-047-006: force reindex clears override (endpoint)
@patch("messaging.kb_index_publisher.publish_kb_index_job")
@patch("services.kb_index_service._notify_file_index")
def test_sc047_006_force_reindex_clears_override(_mock_notify, _mock_pub, client, jwt_token, db_session, regular_user):
    f, _ = _own_file_and_chunk(db_session, regular_user, override=True)
    r = client.post(
        f"/api/knowledge-base/files/{f.id}/reindex",
        json={"force": True},
        headers={"Authorization": f"Bearer {jwt_token}"},
    )
    assert r.status_code == 200
    db_session.refresh(f)
    assert f.kb_index_manual_override is False
    assert f.index_source_hash is None
    job = (
        db_session.query(KbIndexJob)
        .filter(KbIndexJob.file_id == f.id)
        .order_by(KbIndexJob.id.desc())
        .first()
    )
    assert job is not None and job.force is True


# SC-047-008: md update clears override (integration via save_md_note)
@patch("services.md_note_service.rebuild_md_note_side_effects")
@patch("services.md_tag_anchor_service.rebuild_anchors_for_file")
def test_sc047_008_md_write_clears_override_and_enqueues(_anchors, _sidefx, db_session, regular_user):
    f, _ = _own_file_and_chunk(db_session, regular_user, override=True)
    os.makedirs(UPLOAD_DIR, exist_ok=True)
    path = os.path.join(UPLOAD_DIR, f"note_{f.id}.md")
    with open(path, "w", encoding="utf-8") as fh:
        fh.write("# old\n")
    f.has_md = True
    f.md_file_path = path
    db_session.commit()

    job_id = save_md_note_for_file(db_session, regular_user.id, f, "# new md body\n", enqueue_vector_index=True)
    assert job_id is not None
    assert f.kb_index_manual_override is False


# SC-047-002: keywords only leaves override false (endpoint)
def test_sc047_002_keywords_only_no_override(client, jwt_token, db_session, regular_user):
    f, ch = _own_file_and_chunk(db_session, regular_user, override=False)
    r = client.patch(
        f"/api/knowledge-base/files/{f.id}/chunks/{ch.id}",
        json={"boost_keywords": "term1", "reembed": False},
        headers={"Authorization": f"Bearer {jwt_token}"},
    )
    assert r.status_code == 200
    db_session.refresh(f)
    assert f.kb_index_manual_override is False
