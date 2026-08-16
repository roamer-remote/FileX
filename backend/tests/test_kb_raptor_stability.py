# Copyright (c) 2026 徐泽宇
"""101 P2: RAPTOR ollama response handling, retry, fail_open operation_log."""

from unittest.mock import MagicMock, patch

import pytest

from models.file import File as FileModel
from models.kb_index_job import KbIndexJob
from models.operation_log import OperationLog
from config import OLLAMA_EMBED_DIM
from services.kb_raptor_service import (
    RaptorBuildError,
    _parse_ollama_summary_content,
    _ollama_summarize,
    build_tree,
    maybe_build_raptor_tree,
)
from services.kb_pipeline_log_service import ACTION_KB_RAPTOR_WARN
from services.system_setting_service import (
    KEY_KB_LARGE_DOC_CHAR_THRESHOLD,
    KEY_KB_LARGE_DOC_RAPTOR_ENABLED,
    KEY_KB_RAPTOR_ENABLED,
    KEY_KB_RAPTOR_FAIL_OPEN,
    KEY_KB_RAPTOR_MIN_CHARS,
    invalidate_settings_cache,
    update_settings,
)


def test_parse_ollama_summary_content_empty():
    assert _parse_ollama_summary_content(None) == (None, "empty_content")
    assert _parse_ollama_summary_content("   ") == (None, "empty_content")


def test_parse_ollama_summary_content_invalid_json():
    assert _parse_ollama_summary_content("not-json") == (None, "invalid_json")
    assert _parse_ollama_summary_content("[]") == (None, "invalid_json")


def test_parse_ollama_summary_content_empty_summary():
    assert _parse_ollama_summary_content('{"summary":""}') == (None, "empty_summary")


def test_parse_ollama_summary_content_ok():
    assert _parse_ollama_summary_content('{"summary":"hello"}') == ("hello", None)


@patch("services.kb_raptor_service._ollama_summarize_once")
@patch("services.kb_raptor_service.time.sleep")
def test_ollama_summarize_retries_then_succeeds(mock_sleep, mock_once):
    mock_once.side_effect = [
        (None, "invalid_json"),
        ("ok summary", None),
    ]
    result = _ollama_summarize("text", timeout_sec=5.0)
    assert result == "ok summary"
    assert mock_once.call_count == 2
    mock_sleep.assert_called_once()


@patch("services.kb_raptor_service._ollama_summarize_once")
@patch("services.kb_raptor_service.time.sleep")
def test_ollama_summarize_raises_after_max_attempts(mock_sleep, mock_once):
    mock_once.return_value = (None, "timeout")
    with pytest.raises(RaptorBuildError, match="timeout"):
        _ollama_summarize("text", timeout_sec=5.0)
    assert mock_once.call_count == 2


@patch("services.kb_raptor_service._build_and_persist_tree")
def test_build_tree_caps_summaries_for_large_doc(mock_build, db_session, regular_user):
    from models.kb_chunk import KbChunk

    update_settings(
        db_session,
        {
            KEY_KB_RAPTOR_ENABLED: "true",
            KEY_KB_RAPTOR_MIN_CHARS: "10",
        },
    )
    invalidate_settings_cache()
    mock_build.return_value = 1

    f = FileModel(
        filename="large",
        original_name="large.md",
        file_path="/tmp/large",
        file_size=5000,
        mime_type="text/markdown",
        user_id=regular_user.id,
        has_md=True,
    )
    db_session.add(f)
    db_session.commit()

    for idx in range(2):
        db_session.add(
            KbChunk(
                user_id=regular_user.id,
                file_id=f.id,
                chunk_index=idx,
                source="sidecar_md",
                text=f"chunk {idx} " + ("x" * 200),
                char_start=idx * 100,
                char_end=(idx + 1) * 100,
                embedding=[0.1] * OLLAMA_EMBED_DIM,
                embedding_model="test",
            )
        )
    db_session.commit()

    with patch("services.kb_raptor_service.get_vector_index_backend") as mock_backend:
        mock_backend.return_value.get_many.return_value = {
            int(c.id): ([0.1] * OLLAMA_EMBED_DIM, "test")
            for c in db_session.query(KbChunk).filter(KbChunk.file_id == f.id).all()
        }
        build_tree(
            db_session,
            f,
            md_char_count=500_000,
            source="sidecar_md",
            fts_config="simple",
        )

    assert mock_build.called
    kwargs = mock_build.call_args.kwargs
    assert kwargs["max_summaries"] == 16


@patch("services.kb_raptor_service.build_tree")
def test_fail_open_logs_operation_log(mock_build, db_session, regular_user):
    update_settings(
        db_session,
        {
            KEY_KB_RAPTOR_ENABLED: "true",
            KEY_KB_RAPTOR_FAIL_OPEN: "true",
            KEY_KB_RAPTOR_MIN_CHARS: "10",
            KEY_KB_LARGE_DOC_RAPTOR_ENABLED: "true",
            KEY_KB_LARGE_DOC_CHAR_THRESHOLD: "100000",
        },
    )
    invalidate_settings_cache()
    mock_build.side_effect = RaptorBuildError("ollama summary failed: timeout")

    f = FileModel(
        filename="f",
        original_name="f.md",
        file_path="/tmp/f",
        file_size=100,
        mime_type="text/markdown",
        user_id=regular_user.id,
        has_md=True,
    )
    db_session.add(f)
    db_session.commit()
    job = KbIndexJob(user_id=regular_user.id, file_id=f.id, status="running", force=True)
    db_session.add(job)
    db_session.commit()

    maybe_build_raptor_tree(
        db_session,
        f,
        md_char_count=5000,
        source="sidecar_md",
        fts_config="simple",
        job=job,
    )

    db_session.refresh(job)
    assert "raptor warning" in (job.last_error or "")

    row = (
        db_session.query(OperationLog)
        .filter(
            OperationLog.target_id == f.id,
            OperationLog.action == ACTION_KB_RAPTOR_WARN,
        )
        .order_by(OperationLog.id.desc())
        .first()
    )
    assert row is not None
    assert "reason=" in (row.detail or "")
