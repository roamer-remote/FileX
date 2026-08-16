# Copyright (c) 2026 徐泽宇
"""List stored KB vector chunks for a file (read-only, per user).

Authors:
    徐泽宇

Copyright:
    © 2026 徐泽宇
"""

from __future__ import annotations

import math
from typing import Any

from sqlalchemy.orm import Session

from config import OLLAMA_EMBED_DIM
from models.file import File as FileModel
from models.user import User
from services.acl_service import get_readable_file
from models.kb_chunk import KbChunk
from services.vector_index import get_vector_index_backend

EMBEDDING_PREVIEW_HEAD = 12
KB_CHUNKS_PAGE_SIZE_MAX = 100


def _vector_to_list(vec: Any) -> list[float]:
    if vec is None:
        return []
    if isinstance(vec, list):
        return [float(x) for x in vec]
    return [float(x) for x in list(vec)]


def embedding_preview(vec: Any, head_len: int = EMBEDDING_PREVIEW_HEAD) -> dict[str, Any]:
    arr = _vector_to_list(vec)
    if not arr:
        return {"dim": 0, "head": [], "norm": 0.0}
    head = [round(x, 6) for x in arr[:head_len]]
    norm = math.sqrt(sum(x * x for x in arr))
    return {"dim": len(arr), "head": head, "norm": round(norm, 6)}


def list_file_kb_chunks(
    db: Session,
    user: User,
    file_id: int,
    *,
    page: int = 1,
    page_size: int = 20,
    include_embedding: bool = False,
) -> dict[str, Any]:
    page = max(1, page)
    page_size = max(1, min(KB_CHUNKS_PAGE_SIZE_MAX, page_size))

    f = get_readable_file(db, user, file_id)
    if not f:
        return {"found": False}

    base = db.query(KbChunk).filter(KbChunk.file_id == file_id)
    total = base.count()
    rows = (
        base.order_by(KbChunk.chunk_index.asc(), KbChunk.id.asc())
        .offset((page - 1) * page_size)
        .limit(page_size)
        .all()
    )

    chunk_ids = [int(r.id) for r in rows]
    vec_rows = get_vector_index_backend(db).get_many(chunk_ids) if chunk_ids else {}
    items = []
    for row in rows:
        vec = vec_rows.get(int(row.id))
        preview = embedding_preview(vec[0] if vec else None)
        item: dict[str, Any] = {
            "id": row.id,
            "chunk_index": row.chunk_index,
            "source": row.source,
            "text": row.text,
            "char_start": row.char_start,
            "char_end": row.char_end,
            "embedding_model": vec[1] if vec else "",
            "embedding_dim": preview["dim"] or OLLAMA_EMBED_DIM,
            "embedding_preview": preview,
            "created_at": row.created_at.isoformat() if row.created_at else None,
            "boost_keywords": row.boost_keywords,
            "heading_path": row.heading_path,
            "block_type": row.block_type,
            "content_kind": row.content_kind,
            "content_meta": row.content_meta,
            "loc_label": row.loc_label,
        }
        if include_embedding:
            item["embedding"] = _vector_to_list(vec.embedding) if vec else []
        items.append(item)

    return {
        "found": True,
        "file_id": file_id,
        "original_name": f.original_name,
        "index_status": f.index_status or "skipped",
        "chunk_count": f.chunk_count or 0,
        "kb_index_manual_override": bool(f.kb_index_manual_override),
        "items": items,
        "total": total,
        "page": page,
        "page_size": page_size,
        "embedding_dim": OLLAMA_EMBED_DIM,
    }
