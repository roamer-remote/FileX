# Copyright (c) 2026 徐泽宇
"""Monte Carlo evidence sampling for long documents (028 module B)."""

from __future__ import annotations

import random
import re
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from models.file import File as FileModel
from models.kb_chunk import KbChunk
from services.kb_citation import attach_citation_fields_to_hit
from services.okf_note_service import read_okf_body_for_file
from services.wiki_provenance_service import provenance_dict

_MAX_CANDIDATE_WINDOWS = 20
_MIN_WINDOW = 400
_MAX_WINDOW = 800


def _query_terms(query: str) -> list[str]:
    q = query.strip()
    if not q:
        return []
    parts = re.split(r"\s+", q)
    terms: list[str] = []
    for p in parts:
        p = p.strip()
        if len(p) >= 2:
            terms.append(p.lower())
    if not terms and len(q) >= 2:
        terms.append(q.lower())
    return terms


def is_long_document(
    db: Session,
    file_id: int,
    md_text: str | None,
    *,
    long_doc_chars: int,
) -> bool:
    if md_text and len(md_text) >= long_doc_chars:
        return True
    max_page = db.execute(
        select(func.max(KbChunk.loc_end)).where(
            KbChunk.file_id == file_id,
            KbChunk.loc_type == "pdf_page",
        )
    ).scalar()
    if max_page is not None and int(max_page) >= 10:
        return True
    return False


def sample_evidence(
    md_text: str,
    query: str,
    *,
    seed_char_offset: int,
    sample_k: int,
) -> list[tuple[int, int, str, float]]:
    """Return list of (char_start, char_end, text, score) windows."""
    text_len = len(md_text)
    if text_len < _MIN_WINDOW or sample_k <= 0:
        return []
    rng = random.Random()
    terms = _query_terms(query)
    candidates: list[tuple[int, int, str, float]] = []
    seen_starts: set[int] = set()

    def add_window(start: int, window_size: int | None = None) -> None:
        if len(candidates) >= _MAX_CANDIDATE_WINDOWS:
            return
        ws = window_size or rng.randint(_MIN_WINDOW, min(_MAX_WINDOW, text_len))
        ws = min(ws, text_len)
        start = max(0, min(start, text_len - 1))
        if start in seen_starts:
            return
        end = min(text_len, start + ws)
        if end - start < 80:
            return
        seen_starts.add(start)
        snippet = md_text[start:end]
        overlap = 0.0
        if terms:
            lower = snippet.lower()
            hits = sum(1 for t in terms if t in lower)
            overlap = hits / len(terms)
        center = start + (end - start) / 2
        dist = abs(center - seed_char_offset) / max(text_len, 1)
        proximity = max(0.0, 1.0 - dist)
        score = overlap * 0.6 + proximity * 0.4
        candidates.append((start, end, snippet, score))

    if terms:
        lower_full = md_text.lower()
        for term in terms[:5]:
            idx = 0
            while idx < text_len and len(candidates) < _MAX_CANDIDATE_WINDOWS:
                pos = lower_full.find(term, idx)
                if pos < 0:
                    break
                add_window(max(0, pos - rng.randint(0, 120)))
                idx = pos + len(term)

    explore_n = max(3, _MAX_CANDIDATE_WINDOWS // 3)
    for _ in range(explore_n):
        if len(candidates) >= _MAX_CANDIDATE_WINDOWS:
            break
        add_window(rng.randint(0, max(0, text_len - _MIN_WINDOW)))

    exploit_n = _MAX_CANDIDATE_WINDOWS - len(candidates)
    sigma = max(_MIN_WINDOW / 2, 200)
    for _ in range(max(0, exploit_n)):
        if len(candidates) >= _MAX_CANDIDATE_WINDOWS:
            break
        offset = int(rng.gauss(seed_char_offset, sigma))
        add_window(offset)

    candidates.sort(key=lambda x: x[3], reverse=True)
    return candidates[:sample_k]


def _monte_carlo_hit_dict(
    f: FileModel,
    *,
    char_start: int,
    char_end: int,
    text: str,
    score: float,
    sample_index: int,
) -> dict[str, Any]:
    hit: dict[str, Any] = {
        "chunk_id": None,
        "file_id": int(f.id),
        "original_name": f.original_name,
        "has_md": bool(f.has_md),
        "chunk_index": -1 - sample_index,
        "source": "monte_carlo_sample",
        "text": text,
        "score": round(float(score), 4),
        "char_start": char_start,
        "char_end": char_end,
        "heading_path": None,
        "block_type": None,
        "matched_chunks": 1,
        "context_text": None,
    }
    hit.update(
        provenance_dict(
            provenance="inferred",
            confidence=0.7,
            source_kind="monte_carlo_sample",
        )
    )
    attach_citation_fields_to_hit(hit, original_name=f.original_name or f.filename or "")
    return hit


def append_monte_carlo_hits(
    db: Session,
    items: list[dict],
    query: str,
    *,
    allowed_file_ids: set[int] | None,
    long_doc_chars: int,
    sample_k: int,
    max_files: int,
) -> tuple[list[dict], int]:
    """Append monte_carlo_sample hits; returns (items, sample_count)."""
    if sample_k <= 0 or not items:
        return items, 0

    seed_files: list[tuple[int, int]] = []
    seen: set[int] = set()
    for row in items:
        if row.get("source_kind") == "monte_carlo_sample":
            continue
        fid = int(row["file_id"])
        if fid in seen:
            continue
        if allowed_file_ids is not None and fid not in allowed_file_ids:
            continue
        seen.add(fid)
        seed_offset = int(row.get("char_start") or 0)
        seed_files.append((fid, seed_offset))
        if len(seed_files) >= max_files:
            break

    appended: list[dict] = []
    for fid, seed_offset in seed_files:
        f = db.get(FileModel, fid)
        if f is None:
            continue
        md_text = read_okf_body_for_file(f)
        if not is_long_document(db, fid, md_text, long_doc_chars=long_doc_chars):
            continue
        if not md_text:
            continue
        windows = sample_evidence(
            md_text,
            query,
            seed_char_offset=seed_offset,
            sample_k=sample_k,
        )
        for i, (start, end, snippet, sc) in enumerate(windows):
            appended.append(
                _monte_carlo_hit_dict(
                    f,
                    char_start=start,
                    char_end=end,
                    text=snippet,
                    score=sc,
                    sample_index=len(appended) + i,
                )
            )

    if not appended:
        return items, 0
    return items + appended, len(appended)
