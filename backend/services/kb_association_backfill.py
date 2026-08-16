# Copyright (c) 2026 徐泽宇
"""144 reconciliation/backfill for association facts."""

from sqlalchemy.orm import Session

from models.file import File as FileModel
from models.kb_association import KbAssociationIndexState
from services.kb_association_extract_service import rebuild_association_facts_for_file
from services.kb_index_service import STATUS_READY


def backfill_association_facts(db: Session, *, batch_size: int = 50) -> dict[str, int]:
    """Build missing or stale association facts for indexed files in bounded batches."""
    files = (
        db.query(FileModel)
        .outerjoin(KbAssociationIndexState, KbAssociationIndexState.file_id == FileModel.id)
        .filter(
            FileModel.index_status == STATUS_READY,
            FileModel.workspace_id.isnot(None),
            (KbAssociationIndexState.file_id.is_(None))
            | (KbAssociationIndexState.status.in_(("not_indexed", "failed")))
            | (KbAssociationIndexState.source_fingerprint.is_distinct_from(FileModel.index_source_hash)),
        )
        .order_by(FileModel.id)
        .limit(max(1, min(batch_size, 200)))
        .all()
    )
    result = {"selected": len(files), "ready": 0, "failed": 0}
    for file in files:
        try:
            rebuild_association_facts_for_file(db, file)
            result["ready"] += 1
        except Exception:
            result["failed"] += 1
    db.flush()
    return result
