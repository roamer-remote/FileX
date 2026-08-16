# Copyright (c) 2026 徐泽宇
"""Enqueue vector reindex for all indexable files (has_md).

Authors:
    徐泽宇

Copyright:
    © 2026 徐泽宇
"""

from __future__ import annotations

from sqlalchemy.orm import Session

from models.file import File as FileModel
from services.kb_index_service import enqueue_index, prepare_force_reindex_file, publish_index_job


def enqueue_reindex_all_files(
    db: Session,
    *,
    user_id: int | None = None,
    force: bool = False,
) -> dict[str, int]:
    """Return candidate_count and enqueued_count. force=True clears index_source_hash before enqueue."""
    q = db.query(FileModel).filter(FileModel.has_md == True)  # noqa: E712
    if user_id is not None:
        q = q.filter(FileModel.user_id == user_id)
    files = q.order_by(FileModel.id).all()
    candidate = len(files)
    enqueued = 0
    for f in files:
        if force:
            prepare_force_reindex_file(f)
        job_id = enqueue_index(db, f.user_id, f.id, force=force)
        db.commit()
        if job_id is not None:
            publish_index_job(db, f.user_id, f.id, job_id)
            enqueued += 1
    return {"candidate_count": candidate, "enqueued_count": enqueued}
