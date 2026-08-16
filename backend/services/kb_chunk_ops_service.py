# Copyright (c) 2026 徐泽宇
"""Single-chunk edit and partial re-embed.

Authors:
    徐泽宇

Copyright:
    © 2026 徐泽宇
"""

from __future__ import annotations

import hashlib

from sqlalchemy import func
from sqlalchemy.orm import Session

from services.ollama_config_service import get_ollama_runtime_config
from models.file import File as FileModel
from models.kb_chunk import KbChunk
from models.user import User
from services.kb_chunk_embed_input import build_embed_input, load_file_embed_context
from services.kb_fts_service import get_effective_fts_config
from services.kb_embed_cache_service import resolve_embedding_vectors
from services.kb_ollama_embed import OllamaEmbedError
from services.vector_index import VectorRecord, get_vector_index_backend


def compute_index_source_hash(text: str) -> str:
    normalized = (text or "").strip().encode("utf-8")
    return hashlib.sha256(normalized).hexdigest()


def patch_chunk(
    db: Session,
    actor_user: User,
    file_id: int,
    chunk_id: int,
    *,
    text: str | None = None,
    boost_keywords: str | None = None,
    reembed: bool = True,
) -> KbChunk:
    _ = actor_user  # auth enforced at router (owner or admin)
    f = db.query(FileModel).filter(FileModel.id == file_id).first()
    if not f:
        raise LookupError("file not found")
    chunk = (
        db.query(KbChunk)
        .filter(KbChunk.id == chunk_id, KbChunk.file_id == file_id)
        .first()
    )
    if not chunk:
        raise LookupError("chunk not found")
    new_vec: list[float] | None = None
    if reembed and text is not None:
        stripped = text.strip()
        try:
            ctx = load_file_embed_context(db, f)
            embed_input = build_embed_input(
                body=stripped,
                heading_path=chunk.heading_path,
                workspace_name=ctx.workspace_name,
                tags=ctx.tags,
                content_kind=chunk.content_kind,
                original_name=f.original_name,
            )
            new_vec = resolve_embedding_vectors(db, [embed_input])[0]
        except OllamaEmbedError:
            raise

    if text is not None:
        chunk.text = text.strip()
        chunk.text_search = func.to_tsvector(get_effective_fts_config(db), chunk.text)
        if new_vec is not None:
            get_vector_index_backend(db).upsert_many(
                [
                    VectorRecord(
                        chunk_id=int(chunk.id),
                        file_id=int(chunk.file_id),
                        workspace_id=chunk.workspace_id,
                        user_id=int(chunk.user_id),
                        content_kind=chunk.content_kind,
                        embedding=new_vec,
                        embedding_model=get_ollama_runtime_config(db).embed_model,
                    )
                ]
            )
        f.kb_index_manual_override = True
    if boost_keywords is not None:
        chunk.boost_keywords = boost_keywords.strip() or None
    db.flush()
    return chunk
