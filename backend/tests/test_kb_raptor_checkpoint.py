# Copyright (c) 2026 徐泽宇
"""114 P1 Step 8: RAPTOR per-level checkpoint + retry resume."""

from __future__ import annotations

from unittest.mock import patch

import pytest

from config import OLLAMA_EMBED_DIM
from models.file import File as FileModel
from models.kb_chunk import KbChunk
from models.kb_enums import ContentKind
from models.kb_index_job import KbIndexJob
from models.kb_post_job import KbPostJob
from services.kb_index_service import delete_chunks_for_file
from services.kb_post_service import KbPostJobAborted, reconcile_superseded_running_post_jobs
from services.kb_raptor_service import (
    RAPTOR_CONTENT_KIND,
    _can_resume_raptor_checkpoint,
    _clear_raptor_summaries,
    _resume_build_state,
    build_tree,
)
from services.system_setting_service import (
    KEY_KB_RAPTOR_ENABLED,
    KEY_KB_RAPTOR_MAX_LEVELS,
    KEY_KB_RAPTOR_MIN_CHARS,
    invalidate_settings_cache,
    update_settings,
)


def _vec(seed: float = 0.5) -> list[float]:
    v = [0.0] * OLLAMA_EMBED_DIM
    v[0] = seed
    return v


def _long_text(n: int = 120) -> str:
    return ("RAPTOR checkpoint paragraph. " * max(1, n // 28))[:n]


def _seed_file_with_base_chunks(db_session, regular_user, *, n: int = 4) -> FileModel:
    f = FileModel(
        filename="ckpt.md",
        original_name="ckpt.md",
        file_path="/tmp/ckpt.md",
        file_size=1000,
        mime_type="text/markdown",
        user_id=regular_user.id,
        has_md=True,
        index_status="ready",
        chunk_count=n,
    )
    db_session.add(f)
    db_session.flush()
    for idx in range(n):
        db_session.add(
            KbChunk(
                user_id=regular_user.id,
                file_id=f.id,
                chunk_index=idx,
                source="sidecar_md",
                text=f"base {idx} " + _long_text(80),
                char_start=idx * 100,
                char_end=(idx + 1) * 100,
                embedding=_vec(0.1 + idx * 0.01),
                embedding_model="test",
            )
        )
    db_session.commit()
    db_session.refresh(f)
    return f


def _enable_raptor(db_session) -> None:
    update_settings(
        db_session,
        {
            KEY_KB_RAPTOR_ENABLED: "true",
            KEY_KB_RAPTOR_MIN_CHARS: "10",
            KEY_KB_RAPTOR_MAX_LEVELS: "3",
        },
    )
    invalidate_settings_cache()


def test_can_resume_raptor_checkpoint_partial():
    f = FileModel(chunk_count=10, raptor_built_chunk_count=2, raptor_built_md_chars=5000)
    assert _can_resume_raptor_checkpoint(f, md_char_count=5000, summary_count=2)
    assert not _can_resume_raptor_checkpoint(f, md_char_count=5000, summary_count=3)
    assert not _can_resume_raptor_checkpoint(f, md_char_count=4999, summary_count=2)
    f.raptor_built_chunk_count = 10
    assert not _can_resume_raptor_checkpoint(f, md_char_count=5000, summary_count=2)


def test_clear_raptor_summaries(db_session, regular_user):
    f = _seed_file_with_base_chunks(db_session, regular_user, n=2)
    db_session.add(
        KbChunk(
            user_id=regular_user.id,
            file_id=f.id,
            chunk_index=10,
            source="sidecar_md",
            text="partial summary",
            char_start=0,
            char_end=10,
            content_kind=ContentKind.raptor_summary.value,
            content_meta={"level": 1, "child_chunk_ids": [1]},
            embedding=_vec(0.9),
            embedding_model="test",
        )
    )
    db_session.commit()
    assert (
        db_session.query(KbChunk)
        .filter(KbChunk.file_id == f.id, KbChunk.content_kind == RAPTOR_CONTENT_KIND)
        .count()
        == 1
    )
    _clear_raptor_summaries(db_session, f.id)
    db_session.commit()
    assert (
        db_session.query(KbChunk)
        .filter(KbChunk.file_id == f.id, KbChunk.content_kind == RAPTOR_CONTENT_KIND)
        .count()
        == 0
    )


def test_resume_build_state_from_partial(db_session, regular_user):
    f = _seed_file_with_base_chunks(db_session, regular_user, n=4)
    base_ids = [
        int(c.id)
        for c in db_session.query(KbChunk)
        .filter(KbChunk.file_id == f.id, KbChunk.content_kind.is_(None))
        .order_by(KbChunk.chunk_index)
        .all()
    ]
    summary = KbChunk(
        user_id=regular_user.id,
        file_id=f.id,
        chunk_index=10,
        source="sidecar_md",
        text="level-2 summary",
        char_start=0,
        char_end=400,
        content_kind=ContentKind.raptor_summary.value,
        content_meta={"level": 2, "child_chunk_ids": base_ids[:2]},
        embedding=_vec(0.8),
        embedding_model="test",
    )
    db_session.add(summary)
    f.raptor_built_md_chars = 5000
    f.raptor_built_chunk_count = 1
    db_session.commit()

    base_chunks = (
        db_session.query(KbChunk)
        .filter(KbChunk.file_id == f.id, KbChunk.content_kind.is_(None))
        .order_by(KbChunk.chunk_index)
        .all()
    )
    state = _resume_build_state(db_session, f, base_chunks, md_char_count=5000)
    assert state is not None
    nodes, next_level, summary_count, next_chunk_index = state
    assert summary_count == 1
    assert next_level == 1
    assert len(nodes) == 1
    assert next_chunk_index == 11


@patch("services.kb_raptor_service._ollama_summarize")
@patch("services.kb_raptor_service._raptor_embed_vector")
def test_build_tree_resume_skips_completed_level(
    mock_raptor_embed, mock_summarize, db_session, regular_user
):
    _enable_raptor(db_session)
    mock_raptor_embed.side_effect = lambda _db, _text: _vec(0.7)
    mock_summarize.return_value = "summary text for checkpoint test"

    f = _seed_file_with_base_chunks(db_session, regular_user, n=4)
    md_chars = 5000

    summarize_calls: list[int] = []

    def _summarize_side_effect(*_args, **_kwargs):
        summarize_calls.append(1)
        return "summary text for checkpoint test"

    mock_summarize.side_effect = _summarize_side_effect

    count_full, _ = build_tree(
        db_session,
        f,
        md_char_count=md_chars,
        source="sidecar_md",
        fts_config="simple",
    )
    full_calls = len(summarize_calls)
    assert count_full >= 1
    db_session.refresh(f)
    assert f.raptor_built_chunk_count == f.chunk_count

    summaries = (
        db_session.query(KbChunk)
        .filter(KbChunk.file_id == f.id, KbChunk.content_kind == RAPTOR_CONTENT_KIND)
        .all()
    )
    assert len(summaries) >= 1
    full_summary_count = len(summaries)
    levels = [
        int(s.content_meta.get("level", 0)) if isinstance(s.content_meta, dict) else 0
        for s in summaries
    ]
    frontier_level = max(levels)
    keep_ids = {
        int(s.id)
        for s in summaries
        if (isinstance(s.content_meta, dict) and int(s.content_meta.get("level", 0)) == frontier_level)
    }
    drop_ids = [int(s.id) for s in summaries if int(s.id) not in keep_ids]
    if drop_ids:
        from services.vector_index import get_vector_index_backend

        get_vector_index_backend(db_session).delete_by_chunk_ids(drop_ids)
        db_session.query(KbChunk).filter(KbChunk.id.in_(drop_ids)).delete(synchronize_session=False)
    f.raptor_built_chunk_count = len(keep_ids)
    f.raptor_built_md_chars = md_chars
    db_session.commit()

    summarize_calls.clear()
    build_tree(
        db_session,
        f,
        md_char_count=md_chars,
        source="sidecar_md",
        fts_config="simple",
    )
    assert len(summarize_calls) < full_calls
    db_session.refresh(f)
    assert f.raptor_built_chunk_count == f.chunk_count
    resumed_count = (
        db_session.query(KbChunk)
        .filter(KbChunk.file_id == f.id, KbChunk.content_kind == RAPTOR_CONTENT_KIND)
        .count()
    )
    assert resumed_count == full_summary_count


def test_checkpoint_supersede_delete_chunks_clears_partial(db_session, regular_user):
    """SC-114-005：partial checkpoint 经 supersede + delete_chunks 全清。"""
    f = _seed_file_with_base_chunks(db_session, regular_user, n=4)
    base_ids = [
        int(c.id)
        for c in db_session.query(KbChunk)
        .filter(KbChunk.file_id == f.id, KbChunk.content_kind.is_(None))
        .order_by(KbChunk.chunk_index)
        .all()
    ]
    db_session.add(
        KbChunk(
            user_id=regular_user.id,
            file_id=f.id,
            chunk_index=10,
            source="sidecar_md",
            text="checkpoint partial summary",
            char_start=0,
            char_end=400,
            content_kind=ContentKind.raptor_summary.value,
            content_meta={"level": 2, "child_chunk_ids": base_ids[:2]},
            embedding=_vec(0.8),
            embedding_model="test",
        )
    )
    f.raptor_built_md_chars = 5000
    f.raptor_built_chunk_count = 1
    f.kb_post_status = "running"
    db_session.flush()
    index_job = KbIndexJob(user_id=regular_user.id, file_id=f.id, status="running", force=True)
    post_job = KbPostJob(
        user_id=regular_user.id,
        file_id=f.id,
        index_job_id=index_job.id,
        status="running",
    )
    db_session.add(index_job)
    db_session.add(post_job)
    db_session.commit()

    reconcile_superseded_running_post_jobs(
        db_session,
        f.id,
        superseding_index_job_id=int(index_job.id) + 1,
    )
    delete_chunks_for_file(db_session, f.id)
    db_session.commit()
    db_session.refresh(f)

    assert f.raptor_built_chunk_count is None
    assert f.raptor_built_md_chars is None
    assert (
        db_session.query(KbChunk)
        .filter(KbChunk.file_id == f.id, KbChunk.content_kind == RAPTOR_CONTENT_KIND)
        .count()
        == 0
    )


@patch("services.kb_raptor_service._ollama_summarize")
@patch("services.kb_raptor_service._raptor_embed_vector")
def test_build_tree_abort_after_checkpoint_on_supersede(
    mock_raptor_embed, mock_summarize, db_session, regular_user
):
    _enable_raptor(db_session)
    mock_raptor_embed.side_effect = lambda _db, _text: _vec(0.7)
    mock_summarize.return_value = "summary during supersede race"

    f = _seed_file_with_base_chunks(db_session, regular_user, n=4)
    md_chars = 5000
    post_job = KbPostJob(user_id=regular_user.id, file_id=f.id, status="running")
    db_session.add(post_job)
    db_session.commit()

    checkpoint_rounds = [0]

    def _abort_check() -> None:
        checkpoint_rounds[0] += 1
        if checkpoint_rounds[0] >= 2:
            reconcile_superseded_running_post_jobs(
                db_session,
                f.id,
                superseding_index_job_id=999,
            )
            db_session.refresh(post_job)
            raise KbPostJobAborted("superseded during raptor checkpoint")

    with pytest.raises(KbPostJobAborted):
        build_tree(
            db_session,
            f,
            md_char_count=md_chars,
            source="sidecar_md",
            fts_config="simple",
            abort_check=_abort_check,
        )

    delete_chunks_for_file(db_session, f.id)
    db_session.commit()
    db_session.refresh(f)
    assert f.raptor_built_chunk_count is None
    assert (
        db_session.query(KbChunk)
        .filter(KbChunk.file_id == f.id, KbChunk.content_kind == RAPTOR_CONTENT_KIND)
        .count()
        == 0
    )

@patch("services.kb_raptor_service._ollama_summarize")
@patch("services.kb_raptor_service._raptor_embed_vector")
def test_fingerprint_mismatch_clears_partial_and_rebuilds(
    mock_raptor_embed, mock_summarize, db_session, regular_user
):
    _enable_raptor(db_session)
    mock_raptor_embed.side_effect = lambda _db, _text: _vec(0.7)
    mock_summarize.return_value = "rebuilt summary"

    f = _seed_file_with_base_chunks(db_session, regular_user, n=3)
    db_session.add(
        KbChunk(
            user_id=regular_user.id,
            file_id=f.id,
            chunk_index=99,
            source="sidecar_md",
            text="stale partial",
            char_start=0,
            char_end=10,
            content_kind=ContentKind.raptor_summary.value,
            content_meta={"level": 2, "child_chunk_ids": [1, 2]},
            embedding=_vec(0.5),
            embedding_model="test",
        )
    )
    f.raptor_built_chunk_count = 1
    f.raptor_built_md_chars = 1111
    db_session.commit()

    count, _ = build_tree(
        db_session,
        f,
        md_char_count=2222,
        source="sidecar_md",
        fts_config="simple",
    )
    assert count >= 1
    texts = [
        c.text
        for c in db_session.query(KbChunk)
        .filter(KbChunk.file_id == f.id, KbChunk.content_kind == RAPTOR_CONTENT_KIND)
        .all()
    ]
    assert all("stale" not in (t or "") for t in texts)
