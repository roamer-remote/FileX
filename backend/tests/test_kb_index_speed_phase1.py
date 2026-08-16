# Copyright (c) 2026 徐泽宇
"""080 Phase 1：索引 chunk 批量 flush 与阶段耗时日志。"""

from __future__ import annotations

import os
from unittest.mock import patch

from config import OLLAMA_EMBED_DIM, UPLOAD_DIR
from models.file import File as FileModel
from models.kb_chunk import KbChunk
from models.kb_index_job import KbIndexJob
from services.kb_chunking import TextChunk
from services.kb_index_service import JOB_QUEUED, run_index_job


def _text_chunks(n: int) -> list[TextChunk]:
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


def _parse_detail_kv(detail: str) -> dict[str, str]:
    out: dict[str, str] = {}
    for part in detail.split():
        if "=" in part:
            key, value = part.split("=", 1)
            out[key] = value
    return out


def _run_index_counting_flush(db_session, regular_user, *, n_chunks: int) -> int:
    os.makedirs(UPLOAD_DIR, exist_ok=True)
    md_path = os.path.join(UPLOAD_DIR, f"speed_phase1_{n_chunks}.md")
    with open(md_path, "w", encoding="utf-8") as fh:
        fh.write("# Title\n\n" + "\n\n".join(f"Section {i}\n\nBody {i}." for i in range(n_chunks)))
    f = FileModel(
        filename="x.bin",
        original_name=f"paper-{n_chunks}.pdf",
        file_path="/tmp/unused.bin",
        file_size=10,
        mime_type="application/pdf",
        user_id=regular_user.id,
        has_md=True,
        md_file_path=md_path,
    )
    db_session.add(f)
    db_session.commit()
    job = KbIndexJob(user_id=regular_user.id, file_id=f.id, status=JOB_QUEUED, force=True)
    db_session.add(job)
    db_session.commit()

    pieces = _text_chunks(n_chunks)
    flush_count = 0
    original_flush = db_session.flush

    def counting_flush(*args, **kwargs):
        nonlocal flush_count
        flush_count += 1
        return original_flush(*args, **kwargs)

    with (
        patch("services.kb_index_service._notify_file_index"),
        patch("services.kb_index_service.chunk_markdown", return_value=pieces),
        patch("services.kb_index_service.chunk_text", return_value=pieces),
        patch("services.kb_embed_cache_service.embed_texts") as mock_embed,
        patch("services.kb_pipeline_service.should_rebuild_entity_edges_after_index", return_value=False),
        patch("services.kb_sag_event_extract_service.rebuild_sag_events_for_file"),
        patch("services.kb_raptor_service.maybe_build_raptor_tree"),
    ):
        mock_embed.side_effect = lambda texts, **kwargs: [[0.01] * OLLAMA_EMBED_DIM for _ in texts]
        db_session.flush = counting_flush  # type: ignore[method-assign]
        try:
            run_index_job(db_session, job)
            db_session.commit()
        finally:
            db_session.flush = original_flush  # type: ignore[method-assign]

    chunks = db_session.query(KbChunk).filter(KbChunk.file_id == f.id).all()
    assert len(chunks) == n_chunks
    return flush_count


@patch("services.kb_index_service._notify_file_index")
@patch("services.kb_embed_cache_service.embed_texts")
def test_chunk_flush_increment_independent_of_chunk_count(
    mock_embed, _mock_notify, db_session, regular_user
):
    """chunk 创建循环不应随 chunk 数增加而增加 flush 次数。"""
    mock_embed.side_effect = lambda texts, **kwargs: [[0.01] * OLLAMA_EMBED_DIM for _ in texts]
    flush_one = _run_index_counting_flush(db_session, regular_user, n_chunks=1)
    flush_three = _run_index_counting_flush(db_session, regular_user, n_chunks=3)
    # 旧实现 per-chunk flush 会在 chunk 循环内额外增加 (3-1)=2 次 flush；批量 flush 不应如此。
    assert flush_three - flush_one < 3 - 1


@patch("services.kb_index_service._notify_file_index")
@patch("services.kb_embed_cache_service.embed_texts")
def test_index_done_log_includes_index_phase_timings_only(mock_embed, _mock_notify, db_session, regular_user):
    from services.kb_pipeline_log_service import ACTION_KB_INDEX_DONE
    from tests.test_kb_pipeline_operation_logs import _op_logs

    os.makedirs(UPLOAD_DIR, exist_ok=True)
    md_path = os.path.join(UPLOAD_DIR, "speed_phase1_timing.md")
    with open(md_path, "w", encoding="utf-8") as fh:
        fh.write("# Title\n\nParagraph about microscopy imaging.\n")
    f = FileModel(
        filename="x.bin",
        original_name="paper.pdf",
        file_path="/tmp/unused.bin",
        file_size=10,
        mime_type="application/pdf",
        user_id=regular_user.id,
        has_md=True,
        md_file_path=md_path,
    )
    db_session.add(f)
    db_session.commit()
    job = KbIndexJob(user_id=regular_user.id, file_id=f.id, status=JOB_QUEUED, force=False)
    db_session.add(job)
    db_session.commit()
    mock_embed.side_effect = lambda texts, **kwargs: [[0.01] * OLLAMA_EMBED_DIM for _ in texts]

    with (
        patch("services.kb_pipeline_service.should_rebuild_entity_edges_after_index", return_value=False),
        patch("services.kb_sag_event_extract_service.rebuild_sag_events_for_file"),
        patch("services.kb_raptor_service.maybe_build_raptor_tree"),
    ):
        run_index_job(db_session, job)
        db_session.commit()

    done_row = next(
        row for row in _op_logs(db_session, regular_user.id, target_id=f.id) if row.action == ACTION_KB_INDEX_DONE
    )
    detail = done_row.detail or ""
    kv = _parse_detail_kv(detail)
    for key in ("embed_ms", "persist_ms"):
        assert key in kv
        assert int(kv[key]) >= 0
    for key in ("post_index_ms", "post_entity_ms", "post_sag_ms", "post_raptor_ms"):
        assert key not in kv
