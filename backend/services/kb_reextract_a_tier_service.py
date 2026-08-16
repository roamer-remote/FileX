# Copyright (c) 2026 徐泽宇
"""Enqueue reextract for A-tier files missing filex:loc markers (025)."""

from __future__ import annotations

import os

from sqlalchemy.orm import Session

from models.file import File as FileModel
from services.extract.loc_markers import body_has_loc_markers
from services.extract.policy import A_TIER_EXTENSIONS, get_extension_from_file, supports_reextract
from services.kb_extract_service import enqueue_extract, publish_extract_job
from services.office_normalize_service import remove_normalized_file


def _parse_ext_filter(ext_csv: str | None) -> frozenset[str] | None:
    if not ext_csv:
        return None
    parts = {p.strip().lower().lstrip(".") for p in ext_csv.split(",") if p.strip()}
    invalid = parts - A_TIER_EXTENSIONS
    if invalid:
        raise ValueError(f"unsupported ext filter: {sorted(invalid)}; allowed: {sorted(A_TIER_EXTENSIONS)}")
    return frozenset(parts)


def _sidecar_has_marker(f: FileModel) -> bool:
    path = f.md_file_path
    if not path or not os.path.isfile(path):
        return False
    try:
        with open(path, encoding="utf-8") as fh:
            return body_has_loc_markers(fh.read())
    except OSError:
        return False


def _prepare_force_reextract(f: FileModel) -> None:
    if f.has_md and f.md_file_path and os.path.isfile(f.md_file_path):
        try:
            os.remove(f.md_file_path)
        except OSError:
            pass
        f.has_md = False
        f.md_file_path = None
    remove_normalized_file(f)


def list_a_tier_reextract_candidates(
    db: Session,
    *,
    user_id: int | None = None,
    ext_filter: str | None = None,
    skip_marked: bool = True,
) -> list[FileModel]:
    allowed = _parse_ext_filter(ext_filter)
    q = db.query(FileModel).filter(FileModel.has_md == True)  # noqa: E712
    if user_id is not None:
        q = q.filter(FileModel.user_id == user_id)
    files = q.order_by(FileModel.id).all()
    out: list[FileModel] = []
    for f in files:
        if not supports_reextract(f):
            continue
        ext = get_extension_from_file(f)
        if ext not in A_TIER_EXTENSIONS:
            continue
        if allowed is not None and ext not in allowed:
            continue
        if skip_marked and _sidecar_has_marker(f):
            continue
        out.append(f)
    return out


def enqueue_reextract_a_tier_files(
    db: Session,
    *,
    user_id: int | None = None,
    ext_filter: str | None = None,
    skip_marked: bool = True,
    force: bool = True,
) -> dict[str, int]:
    """Return candidate_count, skipped_marked, enqueued_count."""
    candidates = list_a_tier_reextract_candidates(
        db, user_id=user_id, ext_filter=ext_filter, skip_marked=False,
    )
    candidate_count = len(candidates)
    skipped_marked = 0
    enqueued = 0
    for f in candidates:
        if skip_marked and _sidecar_has_marker(f):
            skipped_marked += 1
            continue
        if force:
            _prepare_force_reextract(f)
        job_id = enqueue_extract(db, f.user_id, f.id, for_reextract=True)
        db.commit()
        if job_id is not None:
            publish_extract_job(db, f.user_id, f.id, job_id)
            enqueued += 1
    return {
        "candidate_count": candidate_count,
        "skipped_marked": skipped_marked,
        "enqueued_count": enqueued,
    }
