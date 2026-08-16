from models.file import File as FileModel
from models.kb_chunk import KbChunk
from models.kb_enums import ContentKind
from schemas.kb import KbChunkHit
from services.kb_search_service import _attach_file_chunk_counts, _merge_hits_by_file


def _hit(file_id: int, chunk_id: int, score: float, *, file_chunk_count: int | None = None) -> dict:
    row = {
        "chunk_id": chunk_id,
        "file_id": file_id,
        "original_name": f"file-{file_id}.md",
        "has_md": True,
        "chunk_index": chunk_id,
        "source": "main_md",
        "text": f"chunk {chunk_id}",
        "score": score,
        "char_start": 0,
        "char_end": 10,
        "citation_label": f"file-{file_id}.md",
    }
    if file_chunk_count is not None:
        row["file_chunk_count"] = file_chunk_count
    return row


def test_kb_chunk_hit_accepts_optional_file_chunk_count():
    hit = KbChunkHit(**_hit(10, 1, 0.9, file_chunk_count=3))
    assert hit.file_chunk_count == 3

    legacy = KbChunkHit(**_hit(11, 2, 0.8))
    assert legacy.file_chunk_count is None


def test_merge_hits_by_file_preserves_file_chunk_count_when_main_hit_changes():
    merged = _merge_hits_by_file(
        [
            _hit(10, 1, 0.2, file_chunk_count=3),
            _hit(10, 2, 0.9, file_chunk_count=3),
        ]
    )

    assert len(merged) == 1
    assert merged[0]["chunk_id"] == 1
    assert merged[0]["chunk_index"] == 2
    assert merged[0]["file_chunk_count"] == 3
    assert merged[0]["matched_chunks"] == 2


def test_attach_file_chunk_counts_counts_all_chunks_for_hit_files(db_session, regular_user):
    files = [
        FileModel(
            id=10,
            filename="file-10.md",
            original_name="file-10.md",
            file_path="/tmp/file-10.md",
            file_size=1,
            mime_type="text/markdown",
            user_id=regular_user.id,
            index_status="ready",
        ),
        FileModel(
            id=11,
            filename="file-11.md",
            original_name="file-11.md",
            file_path="/tmp/file-11.md",
            file_size=1,
            mime_type="text/markdown",
            user_id=regular_user.id,
            index_status="ready",
        ),
    ]
    db_session.add_all(files)
    db_session.flush()
    chunks = [
        KbChunk(
            user_id=regular_user.id,
            workspace_id=None,
            file_id=10,
            chunk_index=0,
            source="main_md",
            text="alpha",
            char_start=0,
            char_end=5,
        ),
        KbChunk(
            user_id=regular_user.id,
            workspace_id=None,
            file_id=10,
            chunk_index=1,
            source="main_md",
            text="beta",
            char_start=6,
            char_end=10,
        ),
        KbChunk(
            user_id=regular_user.id,
            workspace_id=None,
            file_id=11,
            chunk_index=0,
            source="main_md",
            text="gamma",
            char_start=0,
            char_end=5,
        ),
    ]
    db_session.add_all(chunks)
    db_session.commit()
    items = [_hit(10, 1, 0.9), _hit(11, 3, 0.8), {"source_kind": "processing_placeholder"}]

    _attach_file_chunk_counts(db_session, items)

    assert items[0]["file_chunk_count"] == 2
    assert items[1]["file_chunk_count"] == 1
    assert "file_chunk_count" not in items[2]


def test_attach_file_chunk_counts_excludes_disabled_raptor_summary_chunks(
    db_session,
    regular_user,
):
    f = FileModel(
        id=12,
        filename="short-with-raptor.md",
        original_name="short-with-raptor.md",
        file_path="/tmp/short-with-raptor.md",
        file_size=1,
        mime_type="text/markdown",
        user_id=regular_user.id,
        index_status="ready",
    )
    db_session.add(f)
    db_session.flush()
    chunks = [
        KbChunk(
            user_id=regular_user.id,
            workspace_id=None,
            file_id=12,
            chunk_index=i,
            source="main_md",
            text=f"body {i}",
            char_start=i * 10,
            char_end=i * 10 + 6,
        )
        for i in range(3)
    ]
    chunks.extend(
        KbChunk(
            user_id=regular_user.id,
            workspace_id=None,
            file_id=12,
            chunk_index=10 + i,
            source="raptor",
            text=f"summary {i}",
            char_start=100 + i * 10,
            char_end=100 + i * 10 + 9,
            content_kind=ContentKind.raptor_summary.value,
        )
        for i in range(5)
    )
    db_session.add_all(chunks)
    db_session.commit()
    items = [_hit(12, 1, 0.9)]

    _attach_file_chunk_counts(
        db_session,
        items,
        include_raptor_summaries=False,
        raptor_enabled=False,
    )

    assert items[0]["file_chunk_count"] == 3

    _attach_file_chunk_counts(
        db_session,
        items,
        include_raptor_summaries=False,
        raptor_enabled=True,
    )

    assert items[0]["file_chunk_count"] == 8
