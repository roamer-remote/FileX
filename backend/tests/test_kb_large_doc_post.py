# Copyright (c) 2026 徐泽宇
"""101 P0: large doc post-processing protection (force=true)."""

from __future__ import annotations

from unittest.mock import patch

from config import OLLAMA_EMBED_DIM
from models.file import File as FileModel
from models.kb_index_job import KbIndexJob
from services.kb_chunking import TextChunk
from services.kb_index_service import run_index_job
from services.kb_pipeline_log_service import ACTION_KB_INDEX_DONE, ACTION_KB_POST_SKIP
from services.kb_raptor_service import maybe_build_raptor_tree
from services.system_setting_service import (
    KEY_KB_LARGE_DOC_CHAR_THRESHOLD,
    KEY_KB_LARGE_DOC_POST_ENABLED,
    KEY_KB_LARGE_DOC_RAPTOR_ENABLED,
    KEY_KB_RAPTOR_ENABLED,
    invalidate_settings_cache,
    update_settings,
)
from tests.test_kb_pipeline_operation_logs import _op_logs


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


def _large_pdf_text(char_count: int = 500_000) -> str:
    unit = "Large PDF paragraph for indexing protection tests. "
    repeat = max(1, char_count // len(unit) + 1)
    return (unit * repeat)[:char_count]


@patch("services.kb_sag_event_extract_service.rebuild_sag_events_for_file")
@patch("services.kb_entity_extract_service.rebuild_doc_entity_edges_for_file")
@patch("services.kb_raptor_service.build_tree")
@patch("services.kb_index_service.resolve_embedding_vectors")
@patch("services.kb_index_service.chunk_markdown", return_value=_text_chunks())
@patch("services.kb_index_service.chunk_text", return_value=_text_chunks())
@patch("services.kb_index_service._notify_file_index")
@patch("services.kb_index_service.resolve_index_text")
def test_large_pdf_force_skips_post_by_default(
    mock_resolve,
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
    update_settings(
        db_session,
        {
            KEY_KB_LARGE_DOC_CHAR_THRESHOLD: "15000",
            KEY_KB_LARGE_DOC_POST_ENABLED: "false",
            KEY_KB_LARGE_DOC_RAPTOR_ENABLED: "false",
            KEY_KB_RAPTOR_ENABLED: "true",
        },
    )
    invalidate_settings_cache()

    text = _large_pdf_text()
    mock_resolve.return_value = (text, "sidecar_md")
    mock_embed.side_effect = lambda _db, texts, **kwargs: [_vec(0.1 * i) for i, _ in enumerate(texts)]

    f = FileModel(
        filename="big.pdf",
        original_name="big.pdf",
        file_path="/tmp/big.pdf",
        file_size=len(text),
        mime_type="application/pdf",
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
    assert job.status == "done"
    skip_row = next(
        row for row in _op_logs(db_session, regular_user.id, target_id=f.id) if row.action == ACTION_KB_POST_SKIP
    )
    assert "reason=large_doc_post_skipped" in (skip_row.detail or "")


@patch("services.kb_sag_event_extract_service.rebuild_sag_events_for_file")
@patch("services.kb_entity_extract_service.rebuild_doc_entity_edges_for_file")
@patch("services.kb_raptor_service.build_tree", return_value=(2, None))
@patch("services.kb_index_service.resolve_embedding_vectors")
@patch("services.kb_index_service.chunk_markdown", return_value=_text_chunks())
@patch("services.kb_index_service.chunk_text", return_value=_text_chunks())
@patch("services.kb_index_service._notify_file_index")
@patch("services.kb_index_service.resolve_index_text")
@patch("services.kb_pipeline_service.should_rebuild_entity_edges_after_index", return_value=True)
def test_large_pdf_force_runs_post_when_enabled(
    _should_entity,
    mock_resolve,
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
    update_settings(
        db_session,
        {
            KEY_KB_LARGE_DOC_CHAR_THRESHOLD: "15000",
            KEY_KB_LARGE_DOC_POST_ENABLED: "true",
            KEY_KB_LARGE_DOC_RAPTOR_ENABLED: "true",
            KEY_KB_RAPTOR_ENABLED: "true",
        },
    )
    invalidate_settings_cache()

    text = _large_pdf_text()
    mock_resolve.return_value = (text, "sidecar_md")
    mock_embed.side_effect = lambda _db, texts, **kwargs: [_vec(0.1 * i) for i, _ in enumerate(texts)]

    f = FileModel(
        filename="big.pdf",
        original_name="big.pdf",
        file_path="/tmp/big.pdf",
        file_size=len(text),
        mime_type="application/pdf",
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

    mock_entity.assert_called_once()
    mock_sag.assert_called_once()
    mock_build_tree.assert_called_once()
    assert job.status == "done"


def test_maybe_build_raptor_tree_skips_large_pdf_when_disabled(db_session, regular_user):
    update_settings(
        db_session,
        {
            KEY_KB_LARGE_DOC_CHAR_THRESHOLD: "15000",
            KEY_KB_LARGE_DOC_RAPTOR_ENABLED: "false",
            KEY_KB_RAPTOR_ENABLED: "true",
        },
    )
    invalidate_settings_cache()

    f = FileModel(
        filename="big.pdf",
        original_name="big.pdf",
        file_path="/tmp/big.pdf",
        file_size=10,
        mime_type="application/pdf",
        user_id=regular_user.id,
    )
    db_session.add(f)
    db_session.commit()
    job = KbIndexJob(user_id=regular_user.id, file_id=f.id, status="queued", force=True)

    with patch("services.kb_raptor_service.build_tree") as mock_build:
        maybe_build_raptor_tree(
            db_session,
            f,
            md_char_count=500_000,
            source="sidecar_md",
            fts_config="simple",
            job=job,
        )
        mock_build.assert_not_called()


def test_maybe_build_raptor_tree_skips_large_markdown_when_disabled(db_session, regular_user):
    update_settings(
        db_session,
        {
            KEY_KB_LARGE_DOC_CHAR_THRESHOLD: "15000",
            KEY_KB_LARGE_DOC_RAPTOR_ENABLED: "false",
            KEY_KB_RAPTOR_ENABLED: "true",
        },
    )
    invalidate_settings_cache()

    f = FileModel(
        filename="big.md",
        original_name="big.md",
        file_path="/tmp/big.md",
        file_size=10,
        mime_type="text/markdown",
        user_id=regular_user.id,
    )
    db_session.add(f)
    db_session.commit()
    job = KbIndexJob(user_id=regular_user.id, file_id=f.id, status="queued", force=True)

    with patch("services.kb_raptor_service.build_tree") as mock_build:
        maybe_build_raptor_tree(
            db_session,
            f,
            md_char_count=500_000,
            source="sidecar_md",
            fts_config="simple",
            job=job,
        )
        mock_build.assert_not_called()
