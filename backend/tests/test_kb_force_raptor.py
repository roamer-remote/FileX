# Copyright (c) 2026 徐泽宇
"""118: force RAPTOR API and service tests."""

from unittest.mock import patch

import pytest
from config import OLLAMA_EMBED_DIM
from models.file import File as FileModel
from models.kb_chunk import KbChunk
from models.kb_post_job import KbPostJob
from models.gpu_scheduler import GpuSchedulerOutbox
from models.enterprise_rbac import PERM_READ, PERM_WRITE
from services.auth_service import create_access_token
from services.kb_force_raptor_service import (
    ForceRaptorRejected,
    count_base_chunks,
    try_force_raptor,
)
from services.kb_post_service import JOB_ERROR, JOB_QUEUED, JOB_RUNNING, POST_STATUS_FAILED, POST_STATUS_QUEUED
from services.kb_raptor_service import RAPTOR_CONTENT_KIND
from services.system_setting_service import (
    KEY_KB_POST_ASYNC_ENABLED,
    KEY_KB_RAPTOR_ENABLED,
    KEY_KB_RAPTOR_FAIL_OPEN,
    KEY_KB_SEARCH_HYBRID_ENABLED,
    invalidate_settings_cache,
    update_settings,
)
from services.vector_index import VectorRecord, get_vector_index_backend
from tests.conftest import _create_user
from tests.test_acl_rbac_p1 import _add_acl, _enable_shared_and_rbac


def _vec(seed: float = 0.5) -> list[float]:
    v = [0.0] * OLLAMA_EMBED_DIM
    v[0] = seed
    return v


def _ready_file(db_session, user_id, *, name="f", chunk_count=2):
    f = FileModel(
        filename=f"{name}.md",
        original_name=f"{name}.md",
        file_path=f"/tmp/{name}.md",
        file_size=100,
        mime_type="text/markdown",
        user_id=user_id,
        has_md=True,
        index_status="ready",
        chunk_count=chunk_count,
        kb_post_status="ready",
    )
    db_session.add(f)
    db_session.flush()
    for i in range(chunk_count):
        row = KbChunk(
            user_id=user_id,
            file_id=f.id,
            chunk_index=i,
            source="sidecar_md",
            text=f"paragraph {i} " * 20,
            char_start=i * 100,
            char_end=(i + 1) * 100,
        )
        db_session.add(row)
    db_session.flush()
    backend = get_vector_index_backend(db_session)
    for row in db_session.query(KbChunk).filter(KbChunk.file_id == f.id).all():
        backend.upsert_many(
            [
                VectorRecord(
                    chunk_id=int(row.id),
                    file_id=f.id,
                    workspace_id=f.workspace_id,
                    user_id=user_id,
                    content_kind=None,
                    embedding=_vec(0.1 * row.chunk_index),
                    embedding_model="test",
                )
            ]
        )
    db_session.commit()
    return f


@patch("services.kb_post_service.resolve_index_text", return_value=("x " * 500, "sidecar_md"))
@patch("services.kb_force_raptor_service.resolve_index_text", return_value=("x " * 500, "sidecar_md"))
@patch("services.kb_raptor_service._ollama_summarize", return_value="summary text")
@patch("services.kb_raptor_service._raptor_embed_vector", return_value=_vec(0.8))
def test_force_raptor_builds_when_settings_off(
    _mock_embed,
    _mock_sum,
    _mock_gate_text,
    _mock_post_text,
    db_session,
    regular_user,
):
    update_settings(
        db_session,
        {
            KEY_KB_RAPTOR_ENABLED: "false",
            KEY_KB_POST_ASYNC_ENABLED: "false",
        },
    )
    invalidate_settings_cache()
    f = _ready_file(db_session, regular_user.id)
    job_id, status = try_force_raptor(db_session, regular_user, f.id)
    db_session.commit()

    assert status == "ready"
    assert job_id > 0
    summaries = (
        db_session.query(KbChunk)
        .filter(KbChunk.file_id == f.id, KbChunk.content_kind == RAPTOR_CONTENT_KIND)
        .count()
    )
    assert summaries >= 1


def test_force_raptor_async_creates_durable_route(db_session, regular_user):
    update_settings(db_session, {KEY_KB_POST_ASYNC_ENABLED: "true"})
    invalidate_settings_cache()
    f = _ready_file(db_session, regular_user.id)
    db_session.commit()

    from services.kb_force_raptor_service import enqueue_force_raptor

    job_id, status = enqueue_force_raptor(db_session, regular_user, f)
    db_session.commit()

    assert status == POST_STATUS_QUEUED
    route = (
        db_session.query(GpuSchedulerOutbox)
        .filter_by(job_kind="raptor", job_id=str(job_id))
        .first()
    )
    assert route is not None
    assert route.state == "queued"


def test_force_raptor_gpu_mode_queues_instead_of_sync(db_session, regular_user, monkeypatch):
    monkeypatch.setattr("services.kb_force_raptor_service.GPU_SCHEDULER_ENABLED", True)
    update_settings(db_session, {KEY_KB_POST_ASYNC_ENABLED: "false"})
    invalidate_settings_cache()
    f = _ready_file(db_session, regular_user.id)
    db_session.commit()

    from services.kb_force_raptor_service import enqueue_force_raptor

    job_id, status = enqueue_force_raptor(db_session, regular_user, f)
    db_session.commit()

    assert status == POST_STATUS_QUEUED
    route = (
        db_session.query(GpuSchedulerOutbox)
        .filter_by(job_kind="raptor", job_id=str(job_id))
        .first()
    )
    assert route is not None
    assert route.state == "queued"


def test_run_sync_force_raptor_fails_closed_when_gpu_scheduler_enabled(
    db_session, regular_user, monkeypatch
):
    monkeypatch.setattr("services.kb_post_service.GPU_SCHEDULER_ENABLED", True)
    f = _ready_file(db_session, regular_user.id)

    from services.kb_post_service import run_sync_force_raptor

    with pytest.raises(RuntimeError, match="禁止同步执行"):
        run_sync_force_raptor(db_session, regular_user, f)


@patch("services.kb_post_service._execute_raptor_only_post", side_effect=RuntimeError("ollama down"))
@patch("services.kb_post_service.resolve_index_text", return_value=("x " * 500, "sidecar_md"))
@patch("services.kb_force_raptor_service.resolve_index_text", return_value=("x " * 500, "sidecar_md"))
def test_force_raptor_sync_failure_returns_failed_status(
    _mock_gate_text,
    _mock_post_text,
    _mock_execute,
    db_session,
    regular_user,
):
    update_settings(
        db_session,
        {
            KEY_KB_RAPTOR_ENABLED: "false",
            KEY_KB_POST_ASYNC_ENABLED: "false",
            KEY_KB_RAPTOR_FAIL_OPEN: "false",
        },
    )
    invalidate_settings_cache()
    f = _ready_file(db_session, regular_user.id)
    job_id, status = try_force_raptor(db_session, regular_user, f.id)
    db_session.commit()

    assert status == POST_STATUS_FAILED
    assert job_id > 0
    db_session.refresh(f)
    assert f.kb_post_status == POST_STATUS_FAILED
    job = db_session.query(KbPostJob).filter(KbPostJob.id == job_id).first()
    assert job is not None
    assert job.status == JOB_ERROR


@patch("services.kb_force_raptor_service.resolve_index_text", return_value=("body " * 100, "sidecar_md"))
def test_force_raptor_rejects_active_post_without_deleting_summary(_mock_text, db_session, regular_user):
    update_settings(db_session, {KEY_KB_POST_ASYNC_ENABLED: "true"})
    invalidate_settings_cache()

    f = _ready_file(db_session, regular_user.id)
    summary = KbChunk(
        user_id=regular_user.id,
        file_id=f.id,
        chunk_index=99,
        source="sidecar_md",
        text="old summary",
        char_start=0,
        char_end=11,
        content_kind=RAPTOR_CONTENT_KIND,
        content_meta={"level": 0, "child_chunk_ids": [1]},
    )
    db_session.add(summary)
    active = KbPostJob(user_id=regular_user.id, file_id=f.id, status=JOB_RUNNING)
    db_session.add(active)
    db_session.commit()

    with pytest.raises(ForceRaptorRejected) as exc:
        try_force_raptor(db_session, regular_user, f.id)
    assert exc.value.status_code == 409
    remaining = (
        db_session.query(KbChunk)
        .filter(KbChunk.file_id == f.id, KbChunk.content_kind == RAPTOR_CONTENT_KIND)
        .count()
    )
    assert remaining == 1


@patch("services.kb_post_service.resolve_index_text", return_value=("content " * 200, "sidecar_md"))
@patch("services.kb_force_raptor_service.resolve_index_text", return_value=("content " * 200, "sidecar_md"))
@patch("services.kb_raptor_service._ollama_summarize", return_value="summary")
@patch("services.kb_raptor_service._raptor_embed_vector", return_value=_vec(0.7))
@patch("services.kb_sag_event_extract_service.rebuild_sag_events_for_file")
@patch("services.kb_entity_extract_service.rebuild_doc_entity_edges_for_file")
def test_force_raptor_skips_entity_and_sag(
    mock_entity,
    mock_sag,
    _e,
    _s,
    _mock_gate_text,
    _mock_post_text,
    db_session,
    regular_user,
):
    update_settings(db_session, {KEY_KB_RAPTOR_ENABLED: "false", KEY_KB_POST_ASYNC_ENABLED: "false"})
    invalidate_settings_cache()
    f = _ready_file(db_session, regular_user.id)
    try_force_raptor(db_session, regular_user, f.id)
    db_session.commit()
    mock_entity.assert_not_called()
    mock_sag.assert_not_called()


@patch("services.kb_force_raptor_service.resolve_index_text")
def test_force_raptor_api_acl(mock_resolve, client, db_session, regular_user, tmp_path):
    _enable_shared_and_rbac(db_session)
    writer = _create_user(db_session, "fr_writer")
    reader = _create_user(db_session, "fr_reader")
    from models.folder import Folder
    from services.workspace_service import create_shared_workspace, set_member_role

    shared = create_shared_workspace(db_session, name="fr_ws", owner=regular_user)
    set_member_role(db_session, shared.id, writer.id, "viewer")
    set_member_role(db_session, shared.id, reader.id, "viewer")
    folder = Folder(name="d", workspace_id=shared.id, user_id=regular_user.id, sort_order=0)
    db_session.add(folder)
    db_session.flush()
    blob = tmp_path / "w.md"
    blob.write_text("note body " * 50, encoding="utf-8")
    f = FileModel(
        user_id=writer.id,
        workspace_id=shared.id,
        folder_id=folder.id,
        filename="w.md",
        original_name="w.md",
        file_path=str(blob),
        file_size=blob.stat().st_size,
        mime_type="text/markdown",
        md5_hash="b" * 32,
        has_md=True,
        index_status="ready",
        chunk_count=2,
    )
    db_session.add(f)
    db_session.flush()
    for i in range(2):
        db_session.add(
            KbChunk(
                user_id=writer.id,
                file_id=f.id,
                chunk_index=i,
                source="sidecar_md",
                text=f"chunk {i} " * 15,
                char_start=i * 100,
                char_end=(i + 1) * 100,
            )
        )
    _add_acl(db_session, workspace_id=shared.id, folder_id=folder.id, user_id=writer.id, permission=PERM_WRITE)
    _add_acl(db_session, workspace_id=shared.id, folder_id=folder.id, user_id=reader.id, permission=PERM_READ)
    db_session.commit()
    mock_resolve.return_value = (blob.read_text(encoding="utf-8"), "sidecar_md")

    with patch("services.kb_raptor_service._ollama_summarize", return_value="s"), patch(
        "services.kb_raptor_service._raptor_embed_vector",
        return_value=_vec(0.5),
    ), patch(
        "services.kb_post_service.publish_post_job",
    ), patch(
        "services.system_setting_service.is_kb_post_async_enabled",
        return_value=True,
    ):
        w_token = create_access_token(writer.id, writer.password_rev)
        r = client.post(
            f"/api/knowledge-base/files/{f.id}/force-raptor",
            headers={"Authorization": f"Bearer {w_token}"},
        )
        assert r.status_code == 200

        r_token = create_access_token(reader.id, reader.password_rev)
        r2 = client.post(
            f"/api/knowledge-base/files/{f.id}/force-raptor",
            headers={"Authorization": f"Bearer {r_token}"},
        )
        assert r2.status_code == 403


@patch("services.kb_search_service.embed_text")
def test_search_includes_raptor_on_explicit_expand_when_disabled(mock_embed, db_session, regular_user):
    update_settings(
        db_session,
        {KEY_KB_RAPTOR_ENABLED: "false", KEY_KB_SEARCH_HYBRID_ENABLED: "false"},
    )
    invalidate_settings_cache()
    mock_embed.return_value = _vec(0.9)

    f = _ready_file(db_session, regular_user.id, name="srch")
    query = "raptorForceExpandSeed"
    base = (
        db_session.query(KbChunk)
        .filter(KbChunk.file_id == f.id, KbChunk.content_kind.is_(None))
        .first()
    )
    summary = KbChunk(
        user_id=regular_user.id,
        file_id=f.id,
        chunk_index=50,
        source="sidecar_md",
        text=f"{query} hierarchical summary",
        char_start=0,
        char_end=40,
        content_kind=RAPTOR_CONTENT_KIND,
        content_meta={"level": 0, "child_chunk_ids": [int(base.id)]},
        embedding=_vec(0.95),
        embedding_model="test",
    )
    db_session.add(summary)
    db_session.commit()
    get_vector_index_backend(db_session).upsert_many(
        [
            VectorRecord(
                chunk_id=int(summary.id),
                file_id=f.id,
                workspace_id=f.workspace_id,
                user_id=regular_user.id,
                content_kind=RAPTOR_CONTENT_KIND,
                embedding=_vec(0.95),
                embedding_model="test",
            )
        ]
    )
    db_session.commit()

    from services.kb_search_service import search_kb

    items, _, _, _ = search_kb(
        db_session,
        regular_user.id,
        query,
        file_ids=[f.id],
        top_k=5,
        include_raptor_summaries=True,
    )
    chunk_ids = {int(it["chunk_id"]) for it in items if it.get("chunk_id") is not None}
    assert int(summary.id) in chunk_ids


def test_count_base_chunks_excludes_raptor(db_session, regular_user):
    f = _ready_file(db_session, regular_user.id, chunk_count=2)
    db_session.add(
        KbChunk(
            user_id=regular_user.id,
            file_id=f.id,
            chunk_index=99,
            source="sidecar_md",
            text="sum",
            char_start=0,
            char_end=3,
            content_kind=RAPTOR_CONTENT_KIND,
            content_meta={"level": 0, "child_chunk_ids": [1]},
        )
    )
    db_session.commit()
    assert count_base_chunks(db_session, f.id) == 2
