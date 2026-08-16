# Copyright (c) 2026 徐泽宇
"""146 P2: Multi-representation index service — write and search."""

from __future__ import annotations

from sqlalchemy import and_, delete, select, text
from sqlalchemy.orm import Session

from models.kb_multi_repr import KbMultiRepr
from services.kb_ollama_embed import embed_text


def build_section_repr_text(*, heading_path: str, chunks: list[str]) -> str:
    """Build a retrieval representation that preserves a section's locator context."""
    heading = (heading_path or "").strip()
    body = "\n".join(chunk.strip() for chunk in chunks if chunk and chunk.strip())
    return "\n".join(part for part in (heading, body) if part).strip()


def write_repr(
    db: Session,
    *,
    workspace_id: int | None,
    file_id: int,
    representation_type: str,
    source_id: str,
    text_content: str,
    embed: bool = True,
) -> KbMultiRepr | None:
    """Write or update a representation entry. Returns the entry or None if text is empty."""
    text_content = (text_content or "").strip()
    if not text_content:
        return None

    # Upsert: delete existing entry for same type + source_id, then insert
    db.execute(
        delete(KbMultiRepr).where(
            and_(
                KbMultiRepr.file_id == file_id,
                KbMultiRepr.representation_type == representation_type,
                KbMultiRepr.source_id == source_id,
            )
        )
    )

    embedding = None
    if embed:
        try:
            embedding = embed_text(text_content)
        except Exception:
            pass

    entry = KbMultiRepr(
        workspace_id=workspace_id,
        file_id=file_id,
        representation_type=representation_type,
        source_id=source_id,
        text=text_content,
        embedding=embedding,
    )
    db.add(entry)
    db.flush()
    return entry


def delete_reprs_for_file(db: Session, file_id: int) -> int:
    """Delete all representation entries for a file. Returns count deleted."""
    result = db.execute(
        delete(KbMultiRepr).where(KbMultiRepr.file_id == file_id)
    )
    return result.rowcount


def search_repr(
    db: Session,
    query_vec: list[float],
    *,
    workspace_id: int | None = None,
    allowed_file_ids: set[int] | None = None,
    representation_types: list[str] | None = None,
    top_k: int = 20,
) -> list[dict]:
    """Search multi-representation index by vector similarity.

    Returns list of dicts with keys: id, file_id, representation_type, source_id, text, score.
    """
    if not query_vec:
        return []

    vec_str = "[" + ",".join(str(v) for v in query_vec) + "]"

    conditions = ["mr.embedding IS NOT NULL"]
    params: dict = {"top_k": top_k}

    if workspace_id is not None:
        conditions.append("mr.workspace_id = :ws_id")
        params["ws_id"] = workspace_id
    if allowed_file_ids is not None:
        if not allowed_file_ids:
            return []
        conditions.append("mr.file_id = ANY(:file_ids)")
        params["file_ids"] = list(allowed_file_ids)
    if representation_types:
        conditions.append("mr.representation_type = ANY(:types)")
        params["types"] = representation_types

    where = " AND ".join(conditions)

    sql = text(f"""
        SELECT mr.id, mr.file_id, mr.representation_type, mr.source_id, mr.text,
               1 - (mr.embedding <=> :query_vec) AS score
        FROM kb_multi_repr mr
        WHERE {where}
        ORDER BY mr.embedding <=> :query_vec
        LIMIT :top_k
    """)

    result = db.execute(sql, {**params, "query_vec": vec_str})
    return [
        {
            "id": row.id,
            "file_id": row.file_id,
            "representation_type": row.representation_type,
            "source_id": row.source_id,
            "text": row.text,
            "score": float(row.score),
        }
        for row in result
    ]
