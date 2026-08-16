# Copyright (c) 2026 徐泽宇
"""114 KB post async MQ tests."""

from __future__ import annotations

import pytest
from unittest.mock import patch

from config import OLLAMA_EMBED_DIM
from models.file import File as FileModel
from models.kb_chunk import KbChunk
from models.kb_enums import ContentKind
from models.kb_index_job import KbIndexJob
from models.kb_multi_repr import KbMultiRepr
from models.kb_post_job import KbPostJob
from models.gpu_scheduler import GpuSchedulerOutbox
from services.kb_chunking import TextChunk
from services.kb_index_service import run_index_job
from services.kb_post_service import (
    JOB_QUEUED,
    KbPostJobAborted,
    POST_STATUS_QUEUED,
    POST_STATUS_READY,
    POST_STATUS_SKIPPED,
    reconcile_stale_kb_post_jobs,
    reconcile_superseded_running_post_jobs,
    run_post_job,
    run_sync_post_in_index,
)
from services.system_setting_service import (
    KEY_KB_POST_ASYNC_ENABLED,
    KEY_KB_RAPTOR_ENABLED,
    KEY_KB_RAPTOR_MIN_CHARS,
    invalidate_settings_cache,
    update_settings,
)


def _vec(seed: float = 0.5) -> list[float]:
    v = [0.0] * OLLAMA_EMBED_DIM
    v[0] = seed
    return v


def _text_chunks(n: int = 2) -> list[TextChunk]:
    return [
        TextChunk(
            text=f"paragraph {i} with enough text for chunking.",
            char_start=i * 40,
            char_end=i * 40 + 30,
            heading_path=None,
            block_type=None,
            loc_type=None,
            loc_start=None,
            loc_end=None,
            loc_label=None,
        )
        for i in range(n)
    ]


def _enable_post_async(db_session) -> None:
    update_settings(db_session, {KEY_KB_POST_ASYNC_ENABLED: "true"})
    invalidate_settings_cache()


@patch("messaging.kb_post_publisher.publish_kb_post_job")
@patch("services.kb_index_service.resolve_embedding_vectors")
@patch("services.kb_index_service.chunk_markdown", return_value=_text_chunks())
@patch("services.kb_index_service.chunk_text", return_value=_text_chunks())
@patch("services.kb_index_service._notify_file_index")
@patch("services.kb_index_service.resolve_index_text", return_value=("hello world " * 20, "sidecar_md"))
def test_index_async_enqueues_post_job_db_before_mq(
    _resolve,
    _notify,
    _chunk_text,
    _chunk_md,
    mock_embed,
    mock_publish,
    db_session,
    regular_user,
):
    _enable_post_async(db_session)
    mock_embed.side_effect = lambda _db, texts, **kwargs: [_vec(0.1 * i) for i, _ in enumerate(texts)]

    f = FileModel(
        filename="note.md",
        original_name="note.md",
        file_path="/tmp/note.md",
        file_size=100,
        mime_type="text/markdown",
        user_id=regular_user.id,
        has_md=True,
        index_status="pending",
    )
    db_session.add(f)
    db_session.commit()
    job = KbIndexJob(user_id=regular_user.id, file_id=f.id, status="queued", force=True)
    db_session.add(job)
    db_session.commit()

    run_index_job(db_session, job)
    db_session.commit()

    post_job = (
        db_session.query(KbPostJob)
        .filter(KbPostJob.index_job_id == job.id)
        .one()
    )
    assert post_job.status == JOB_QUEUED
    assert f.index_status == "ready"
    assert f.kb_post_status == POST_STATUS_QUEUED
    assert (
        db_session.query(GpuSchedulerOutbox)
        .filter(GpuSchedulerOutbox.job_id == str(post_job.id))
        .count()
        == 0
    )
    mock_publish.assert_not_called()


@patch("services.kb_sag_event_extract_service.rebuild_sag_events_for_file")
@patch("services.kb_entity_extract_service.rebuild_doc_entity_edges_for_file")
@patch("services.kb_raptor_service.build_tree")
@patch("services.kb_index_service.resolve_embedding_vectors")
@patch("services.kb_index_service.chunk_markdown", return_value=_text_chunks())
@patch("services.kb_index_service.chunk_text", return_value=_text_chunks())
@patch("services.kb_index_service._notify_file_index")
@patch("services.kb_index_service.resolve_index_text", return_value=("hello world " * 20, "sidecar_md"))
def test_index_async_does_not_run_sync_post(
    _resolve,
    _notify,
    _chunk_text,
    _chunk_md,
    mock_embed,
    mock_build_tree,
    mock_entity,
    mock_sag,
    db_session,
    regular_user,
):
    _enable_post_async(db_session)
    mock_embed.side_effect = lambda _db, texts, **kwargs: [_vec(0.1 * i) for i, _ in enumerate(texts)]

    f = FileModel(
        filename="note.md",
        original_name="note.md",
        file_path="/tmp/note.md",
        file_size=100,
        mime_type="text/markdown",
        user_id=regular_user.id,
        has_md=True,
        index_status="pending",
    )
    db_session.add(f)
    db_session.commit()
    job = KbIndexJob(user_id=regular_user.id, file_id=f.id, status="queued", force=True)
    db_session.add(job)
    db_session.commit()

    run_index_job(db_session, job)
    db_session.commit()

    mock_entity.assert_not_called()
    mock_sag.assert_not_called()
    mock_build_tree.assert_not_called()


def test_supersede_running_post_resets_raptor_built_and_skips_new_summary(
    db_session,
    regular_user,
):
    _enable_post_async(db_session)
    update_settings(db_session, {KEY_KB_RAPTOR_ENABLED: "true"})
    invalidate_settings_cache()

    f = FileModel(
        filename="note.md",
        original_name="note.md",
        file_path="/tmp/note.md",
        file_size=100,
        mime_type="text/markdown",
        user_id=regular_user.id,
        has_md=True,
        index_status="ready",
        kb_post_status="running",
        raptor_built_chunk_count=10,
        raptor_built_md_chars=5000,
    )
    db_session.add(f)
    db_session.flush()
    index_job = KbIndexJob(user_id=regular_user.id, file_id=f.id, status="running", force=True)
    db_session.add(index_job)
    db_session.flush()
    post_job = KbPostJob(
        user_id=regular_user.id,
        file_id=f.id,
        index_job_id=index_job.id,
        status="running",
    )
    db_session.add(post_job)
    db_session.commit()

    reconcile_superseded_running_post_jobs(
        db_session,
        f.id,
        superseding_index_job_id=index_job.id + 1,
    )
    db_session.commit()
    db_session.refresh(f)

    assert f.raptor_built_chunk_count is None
    assert f.raptor_built_md_chars is None
    db_session.refresh(post_job)
    assert post_job.status == "error"


@patch("services.kb_sag_event_extract_service.rebuild_sag_events_for_file")
@patch("services.kb_entity_extract_service.rebuild_doc_entity_edges_for_file")
@patch("services.kb_raptor_service.build_tree", return_value=(1, None))
def test_sync_fallback_sets_kb_post_ready(
    mock_build_tree,
    mock_entity,
    mock_sag,
    db_session,
    regular_user,
):
    update_settings(db_session, {KEY_KB_POST_ASYNC_ENABLED: "false"})
    invalidate_settings_cache()

    f = FileModel(
        filename="note.md",
        original_name="note.md",
        file_path="/tmp/note.md",
        file_size=100,
        mime_type="text/markdown",
        user_id=regular_user.id,
        has_md=True,
        index_status="ready",
        chunk_count=2,
    )
    db_session.add(f)
    db_session.flush()
    index_job = KbIndexJob(user_id=regular_user.id, file_id=f.id, status="done", force=True)
    db_session.add(index_job)
    db_session.commit()

    with patch(
        "services.kb_text_source.resolve_index_text",
        return_value=("hello world " * 50, "sidecar_md"),
    ):
        run_sync_post_in_index(
            db_session,
            f,
            index_job,
            md_char_count=len("hello world " * 50),
            source="sidecar_md",
            fts_config="simple",
            large_pdf=False,
        )

    db_session.commit()
    db_session.refresh(f)
    assert f.kb_post_status == POST_STATUS_READY
    mock_entity.assert_called_once()
    mock_sag.assert_called_once()


@patch("services.kb_sag_event_extract_service.rebuild_sag_events_for_file")
@patch("services.kb_entity_extract_service.rebuild_doc_entity_edges_for_file")
def test_sync_fallback_hands_raptor_to_scheduler_when_gpu_enabled(
    mock_entity,
    mock_sag,
    db_session,
    regular_user,
    monkeypatch,
):
    monkeypatch.setattr("services.kb_post_service.GPU_SCHEDULER_ENABLED", True)
    update_settings(
        db_session,
        {
            KEY_KB_POST_ASYNC_ENABLED: "false",
            KEY_KB_RAPTOR_ENABLED: "true",
            KEY_KB_RAPTOR_MIN_CHARS: "1000",
        },
    )
    invalidate_settings_cache()

    f = FileModel(
        filename="note.md",
        original_name="note.md",
        file_path="/tmp/note.md",
        file_size=100,
        mime_type="text/markdown",
        user_id=regular_user.id,
        has_md=True,
        index_status="ready",
        chunk_count=2,
    )
    db_session.add(f)
    db_session.flush()
    index_job = KbIndexJob(user_id=regular_user.id, file_id=f.id, status="done", force=True)
    db_session.add(index_job)
    db_session.commit()

    run_sync_post_in_index(
        db_session,
        f,
        index_job,
        md_char_count=1500,
        source="sidecar_md",
        fts_config="simple",
        large_pdf=False,
    )
    db_session.commit()
    db_session.refresh(f)

    assert f.kb_post_status == POST_STATUS_QUEUED
    post_job = (
        db_session.query(KbPostJob)
        .filter(KbPostJob.index_job_id == index_job.id)
        .one()
    )
    assert post_job.status == JOB_QUEUED
    route = (
        db_session.query(GpuSchedulerOutbox)
        .filter_by(job_kind="raptor", job_id=str(post_job.id))
        .one()
    )
    assert route.state == "queued"
    mock_entity.assert_not_called()
    mock_sag.assert_not_called()


def test_run_post_job_bypasses_async_disabled_gate_when_from_gpu_scheduler(
    db_session, regular_user, monkeypatch
):
    update_settings(db_session, {KEY_KB_POST_ASYNC_ENABLED: "false"})
    invalidate_settings_cache()
    f = FileModel(
        filename="scheduler-post.md",
        original_name="scheduler-post.md",
        file_path="/tmp/scheduler-post.md",
        file_size=100,
        mime_type="text/markdown",
        user_id=regular_user.id,
        has_md=True,
        index_status="ready",
    )
    db_session.add(f)
    db_session.flush()
    post_job = KbPostJob(
        user_id=regular_user.id,
        file_id=f.id,
        status=JOB_QUEUED,
        raptor_only=True,
    )
    db_session.add(post_job)
    db_session.flush()
    ran = []
    monkeypatch.setattr(
        "services.kb_post_service._run_raptor_only_post_job",
        lambda *args, **kwargs: ran.append(args),
    )

    run_post_job(db_session, post_job, _from_gpu_scheduler=True)
    db_session.commit()
    assert ran
    assert post_job.status != "error"

    # 非 scheduler 路径仍受 async_disabled 门禁约束。
    post_job2 = KbPostJob(
        user_id=regular_user.id,
        file_id=f.id,
        status=JOB_QUEUED,
        raptor_only=True,
    )
    db_session.add(post_job2)
    db_session.flush()
    run_post_job(db_session, post_job2)
    db_session.commit()
    assert post_job2.status == "error"
    assert post_job2.last_error == "async_disabled"


@patch("services.kb_post_service.publish_file_post_notify_safe")
def test_reconcile_async_disabled_updates_file_post_status(
    mock_notify,
    db_session,
    regular_user,
):
    update_settings(db_session, {KEY_KB_POST_ASYNC_ENABLED: "false"})
    invalidate_settings_cache()

    f = FileModel(
        filename="note.md",
        original_name="note.md",
        file_path="/tmp/note.md",
        file_size=100,
        mime_type="text/markdown",
        user_id=regular_user.id,
        has_md=True,
        kb_post_status=POST_STATUS_QUEUED,
    )
    db_session.add(f)
    db_session.flush()
    post_job = KbPostJob(user_id=regular_user.id, file_id=f.id, status=JOB_QUEUED)
    db_session.add(post_job)
    db_session.commit()

    stats = reconcile_stale_kb_post_jobs(db_session)
    db_session.commit()
    db_session.refresh(f)

    assert stats["queued_skipped_async_disabled"] == 1
    assert f.kb_post_status == POST_STATUS_SKIPPED
    mock_notify.assert_called_once()


@patch("services.kb_post_service.publish_file_post_notify_safe")
def test_reconcile_async_disabled_keeps_scheduler_raptor_job(
    mock_notify,
    db_session,
    regular_user,
    monkeypatch,
):
    """GPU 调度模式下，async_disabled 的 reconcile 不得跳过带 raptor route 的
    scheduler job（否则 RAPTOR 永不执行、文件被标 SKIPPED）。"""
    monkeypatch.setattr("services.kb_post_service.GPU_SCHEDULER_ENABLED", True)
    update_settings(db_session, {KEY_KB_POST_ASYNC_ENABLED: "false"})
    invalidate_settings_cache()

    f = FileModel(
        filename="note-raptor.md",
        original_name="note-raptor.md",
        file_path="/tmp/note-raptor.md",
        file_size=100,
        mime_type="text/markdown",
        user_id=regular_user.id,
        has_md=True,
        kb_post_status=POST_STATUS_QUEUED,
    )
    db_session.add(f)
    db_session.flush()
    post_job = KbPostJob(user_id=regular_user.id, file_id=f.id, status=JOB_QUEUED, raptor_only=True)
    db_session.add(post_job)
    db_session.flush()
    db_session.add(
        GpuSchedulerOutbox(
            job_kind="raptor",
            job_id=str(post_job.id),
            file_id=f.id,
            idempotency_key=f"raptor:{post_job.id}:0",
            payload={"job_id": post_job.id},
            state="queued",
        )
    )
    db_session.commit()

    stats = reconcile_stale_kb_post_jobs(db_session)
    db_session.commit()
    db_session.refresh(f)

    assert stats == {"queued_skipped_async_disabled": 0}
    assert db_session.get(KbPostJob, post_job.id).status == JOB_QUEUED
    assert f.kb_post_status == POST_STATUS_QUEUED
    mock_notify.assert_not_called()


@patch("services.kb_post_service.publish_file_post_notify_safe")
@patch("services.kb_sag_event_extract_service.rebuild_sag_events_for_file")
@patch("services.kb_entity_extract_service.rebuild_doc_entity_edges_for_file")
def test_post_abort_rolls_back_raptor_chunk_on_supersede(
    _entity,
    _sag,
    _notify,
    db_session,
    regular_user,
):
    _enable_post_async(db_session)
    update_settings(db_session, {KEY_KB_RAPTOR_ENABLED: "true"})
    invalidate_settings_cache()

    f = FileModel(
        filename="note.md",
        original_name="note.md",
        file_path="/tmp/note.md",
        file_size=100,
        mime_type="text/markdown",
        user_id=regular_user.id,
        has_md=True,
        kb_post_status=POST_STATUS_QUEUED,
    )
    db_session.add(f)
    db_session.flush()
    post_job = KbPostJob(user_id=regular_user.id, file_id=f.id, status=JOB_QUEUED)
    db_session.add(post_job)
    db_session.commit()
    file_id = int(f.id)

    def _raptor_side_effect(db, file_model, **kwargs):
        db.add(
            KbChunk(
                user_id=file_model.user_id,
                file_id=file_model.id,
                chunk_index=0,
                source=kwargs.get("source") or "sidecar_md",
                text="orphan raptor summary",
                char_start=0,
                char_end=20,
                content_kind=ContentKind.raptor_summary.value,
            )
        )
        db.flush()
        reconcile_superseded_running_post_jobs(
            db,
            file_model.id,
            superseding_index_job_id=999,
        )

    with patch(
        "services.kb_raptor_service.maybe_build_raptor_tree",
        side_effect=_raptor_side_effect,
    ):
        with patch(
            "services.kb_post_service.resolve_index_text",
            return_value=("hello world " * 50, "sidecar_md"),
        ):
            with pytest.raises(KbPostJobAborted):
                run_post_job(db_session, post_job)

    db_session.expire_all()
    raptor_count = (
        db_session.query(KbChunk)
        .filter(
            KbChunk.file_id == file_id,
            KbChunk.content_kind == ContentKind.raptor_summary.value,
        )
        .count()
    )
    assert raptor_count == 0


# --- 154: _write_raptor_multi_repr 字段 + logger 回归 ---

def test_write_raptor_multi_repr_uses_content_kind(db_session, regular_user):
    """154 SC-154-011: 验证 select 走 content_kind；不引用 chunk_type.

    修复前 KbChunk.chunk_type AttributeError；修复后走 ContentKind.raptor_summary.value。
    """
    from services.kb_post_service import _write_raptor_multi_repr
    from services.kb_multi_repr_service import write_repr as real_write_repr

    f = FileModel(
        filename="rt.bin",
        original_name="rt.md",
        file_path="/tmp/rt",
        file_size=1,
        mime_type="text/markdown",
        user_id=regular_user.id,
        index_status="ready",
    )
    db_session.add(f)
    db_session.commit()
    db_session.add(
        KbChunk(
            user_id=regular_user.id,
            file_id=f.id,
            chunk_index=0,
            source="raptor_summary",
            content_kind=ContentKind.raptor_summary.value,
            text="RAPTOR 摘要核心句",
            char_start=0,
            char_end=10,
        )
    )
    db_session.commit()

    with patch(
        "services.kb_multi_repr_service.write_repr",
        wraps=real_write_repr,
    ) as mock_write:
        _write_raptor_multi_repr(db_session, f)
        # 至少被调 1 次（成功路径）
        assert mock_write.call_count >= 1, "write_repr should be called for raptor_summary chunks"


def test_write_raptor_multi_repr_logs_exception_on_failure(db_session, regular_user, caplog):
    """154 SC-154-012: 注入 AttributeError 模拟旧字段路径，断言 logger.exception 被调。"""
    from services.kb_post_service import _write_raptor_multi_repr

    f = FileModel(
        filename="rf.bin",
        original_name="rf.md",
        file_path="/tmp/rf",
        file_size=1,
        mime_type="text/markdown",
        user_id=regular_user.id,
        index_status="ready",
    )
    db_session.add(f)
    db_session.commit()

    with patch("services.kb_post_service.select", side_effect=AttributeError("simulated old chunk_type")):
        with caplog.at_level("ERROR"):
            _write_raptor_multi_repr(db_session, f)

    # logger.exception 应当产生 "failed for file_id" 记录
    exc_records = [r for r in caplog.records if "failed for file_id" in r.getMessage()]
    assert exc_records, f"expected logger.exception to be called, records={caplog.records!r}"
    # 不应有 logger.warning 吞错
    warn_records = [
        r for r in caplog.records
        if r.levelname == "WARNING" and "failed for file_id" in r.getMessage()
    ]
    assert not warn_records, f"logger.warning should NOT be used, got {warn_records!r}"


def test_post_rebuild_replaces_stale_section_locator_with_current_chunk(
    db_session,
    regular_user,
):
    """SC-157-006: 重建后章节入口不得继续指向已删除的旧 chunk。"""
    from services.kb_post_service import _execute_post_phases

    f = FileModel(
        filename="resume.md",
        original_name="resume.md",
        file_path="/tmp/resume.md",
        file_size=100,
        mime_type="text/markdown",
        user_id=regular_user.id,
        index_status="ready",
    )
    db_session.add(f)
    db_session.flush()
    db_session.add(
        KbMultiRepr(
            workspace_id=None,
            file_id=f.id,
            representation_type="section_context",
            source_id="chunk:stale",
            text="工作经历 / 旧公司\n已删除的章节内容",
        )
    )
    current_chunk = KbChunk(
        user_id=regular_user.id,
        file_id=f.id,
        chunk_index=0,
        source="sidecar_md",
        text="徐泽宇与邓良玉曾在世范软件共事。",
        heading_path="工作经历 / 世范软件",
        char_start=120,
        char_end=140,
        content_kind=ContentKind.text.value,
    )
    db_session.add(current_chunk)
    db_session.flush()
    job = KbIndexJob(user_id=regular_user.id, file_id=f.id, status="running")

    with (
        patch("services.kb_pipeline_service.should_rebuild_entity_edges_after_index", return_value=False),
        patch("services.kb_sag_event_extract_service.rebuild_sag_events_for_file"),
        patch("services.kb_raptor_service.maybe_build_raptor_tree"),
        patch("services.kb_multi_repr_service.embed_text", return_value=None),
        patch("messaging.mq_progress_notify.maybe_publish_post_progress"),
    ):
        _execute_post_phases(
            db_session,
            f,
            job,
            md_char_count=100,
            source="sidecar_md",
            fts_config="simple",
            large_pdf=False,
        )

    section_rows = (
        db_session.query(KbMultiRepr)
        .filter(
            KbMultiRepr.file_id == f.id,
            KbMultiRepr.representation_type == "section_context",
        )
        .all()
    )
    assert [(row.source_id, row.text) for row in section_rows] == [
        (
            f"chunk:{current_chunk.id}",
            "工作经历 / 世范软件\n徐泽宇与邓良玉曾在世范软件共事。",
        )
    ]
