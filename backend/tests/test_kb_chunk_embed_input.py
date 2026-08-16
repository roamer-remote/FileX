# Copyright (c) 2026 徐泽宇
"""061 P0-B chunk embed input tests (SC-061-004～005)."""

import os
from unittest.mock import patch

from config import OLLAMA_EMBED_DIM, UPLOAD_DIR
from models.file import File as FileModel
from models.kb_chunk import KbChunk
from models.kb_index_job import KbIndexJob
from models.tag import Tag, file_tags
from models.workspace import Workspace, WORKSPACE_KIND_SHARED
from services.kb_chunk_embed_input import (
    EMBED_HEADER_VERSION,
    build_embed_input,
    load_file_embed_context,
)
from services.kb_chunk_ops_service import compute_index_source_hash, patch_chunk
from services.kb_index_fingerprint import compute_index_pipeline_fingerprint
from services.kb_index_service import JOB_DONE, run_index_job


def test_build_embed_input_differs_by_workspace_and_tags():
    """SC-061-004: same body, different metadata → different embed input."""
    body = "same paragraph text"
    base = build_embed_input(
        body=body,
        heading_path=None,
        workspace_name="ws-a",
        tags=["alpha"],
        content_kind="text",
        original_name="doc.md",
    )
    other = build_embed_input(
        body=body,
        heading_path=None,
        workspace_name="ws-b",
        tags=["beta"],
        content_kind="text",
        original_name="doc.md",
    )
    assert base != other
    assert "workspace: ws-a" in base
    assert "tags: alpha" in base
    assert body in base
    assert body in other


def test_build_embed_input_omits_file_line_when_body_has_filename_prefix():
    out = build_embed_input(
        body="【paper.pdf】\n\nintro",
        heading_path=None,
        workspace_name="",
        tags=[],
        content_kind=None,
        original_name="paper.pdf",
    )
    assert "file:" not in out.split("---")[1]


def test_index_stores_body_without_yaml_header(db_session, regular_user):
    """SC-061-005: kb_chunks.text has no --- header block."""
    os.makedirs(UPLOAD_DIR, exist_ok=True)
    md_path = os.path.join(UPLOAD_DIR, "header_check.md")
    with open(md_path, "w", encoding="utf-8") as fh:
        fh.write("# Title\n\nPlain chunk body here.")
    f = FileModel(
        filename="h.bin",
        original_name="h.pdf",
        file_path="/tmp/h.bin",
        file_size=10,
        mime_type="application/pdf",
        user_id=regular_user.id,
        has_md=True,
        md_file_path=md_path,
    )
    db_session.add(f)
    db_session.commit()

    with patch("services.kb_index_service._notify_file_index"), patch(
        "services.kb_embed_cache_service.embed_texts",
        side_effect=lambda texts, **_kwargs: [[0.01] * OLLAMA_EMBED_DIM for _ in texts],
    ):
        job = KbIndexJob(user_id=f.user_id, file_id=f.id)
        db_session.add(job)
        db_session.commit()
        run_index_job(db_session, job)
        db_session.commit()

    chunks = db_session.query(KbChunk).filter(KbChunk.file_id == f.id).all()
    assert chunks
    for ch in chunks:
        assert not ch.text.strip().startswith("---")
        assert "workspace:" not in (ch.text or "")


def test_load_file_embed_context_reads_workspace_and_tags(db_session, regular_user):
    ws = Workspace(
        name="Research Lab", slug="research-lab-embed",
        kind=WORKSPACE_KIND_SHARED,
        owner_user_id=regular_user.id,
    )
    db_session.add(ws)
    db_session.flush()
    tag = Tag(user_id=regular_user.id, workspace_id=ws.id, name="biology")
    db_session.add(tag)
    db_session.flush()
    f = FileModel(
        filename="t",
        original_name="t.md",
        file_path="/tmp/t",
        file_size=1,
        mime_type="text/markdown",
        user_id=regular_user.id,
        workspace_id=ws.id,
    )
    db_session.add(f)
    db_session.flush()
    db_session.execute(file_tags.insert().values(file_id=f.id, tag_id=tag.id))
    db_session.commit()

    ctx = load_file_embed_context(db_session, f)
    assert ctx.workspace_name == "Research Lab"
    assert ctx.tags == ["biology"]


def test_patch_chunk_embed_uses_current_file_tags(db_session, regular_user):
    ws = Workspace(name="Patch WS", slug="patch-ws-embed", kind=WORKSPACE_KIND_SHARED, owner_user_id=regular_user.id)
    db_session.add(ws)
    db_session.flush()
    tag = Tag(user_id=regular_user.id, workspace_id=ws.id, name="patch-tag")
    db_session.add(tag)
    db_session.flush()
    f = FileModel(
        filename="p",
        original_name="p.md",
        file_path="/tmp/p",
        file_size=1,
        mime_type="text/markdown",
        user_id=regular_user.id,
        workspace_id=ws.id,
        index_status="ready",
    )
    db_session.add(f)
    db_session.flush()
    db_session.execute(file_tags.insert().values(file_id=f.id, tag_id=tag.id))
    ch = KbChunk(
        user_id=regular_user.id,
        file_id=f.id,
        chunk_index=0,
        source="sidecar_md",
        text="old",
        char_start=0,
        char_end=3,
        embedding=[0.1] * OLLAMA_EMBED_DIM,
        embedding_model="test",
    )
    db_session.add(ch)
    db_session.commit()

    captured: list[str] = []

    def _capture(texts, **_kwargs):
        captured.extend(texts)
        return [[0.2] * OLLAMA_EMBED_DIM for _ in texts]

    with patch("services.kb_embed_cache_service.embed_texts", side_effect=_capture):
        patch_chunk(db_session, regular_user, f.id, ch.id, text="new body", reembed=True)

    assert captured
    assert "workspace: Patch WS" in captured[0]
    assert "tags: patch-tag" in captured[0]
    assert captured[0].endswith("new body")


def test_fingerprint_includes_embed_header_version():
    h = compute_index_source_hash("hello")
    fp = compute_index_pipeline_fingerprint(
        text_hash=h,
        profile_name="default",
        chunk_size=800,
        chunk_overlap=100,
        embed_header_version=EMBED_HEADER_VERSION,
    )
    assert len(fp) == 64
    assert compute_index_pipeline_fingerprint(
        text_hash=h,
        profile_name="default",
        chunk_size=800,
        chunk_overlap=100,
        embed_header_version=99,
    ) != fp
