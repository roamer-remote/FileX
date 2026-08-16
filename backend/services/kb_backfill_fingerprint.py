# Copyright (c) 2026 徐泽宇
"""Backfill files.index_pipeline_fingerprint for ready indexed files (061 P0-C)."""

from __future__ import annotations

import logging

from sqlalchemy.orm import Session

from models.file import File as FileModel
from services.kb_index_fingerprint import compute_file_fingerprint, fingerprint_canonical_json
from services.kb_index_service import STATUS_READY

logger = logging.getLogger(__name__)


def backfill(db: Session, *, batch_size: int = 200) -> dict[str, int]:
    """Compute and persist fingerprints for ready files with chunks."""
    updated = 0
    skipped = 0
    offset = 0
    while True:
        rows = (
            db.query(FileModel)
            .filter(
                FileModel.index_status == STATUS_READY,
                FileModel.chunk_count > 0,
            )
            .order_by(FileModel.id)
            .offset(offset)
            .limit(batch_size)
            .all()
        )
        if not rows:
            break
        for f in rows:
            fp, payload = compute_file_fingerprint(db, f)
            if not fp:
                skipped += 1
                continue
            if f.index_pipeline_fingerprint == fp:
                skipped += 1
                continue
            f.index_pipeline_fingerprint = fp
            if payload is not None:
                f.index_fingerprint_payload = fingerprint_canonical_json(payload)
            updated += 1
        db.flush()
        offset += batch_size
    logger.info("kb_backfill_fingerprint updated=%s skipped=%s", updated, skipped)
    return {"updated": updated, "skipped": skipped}
