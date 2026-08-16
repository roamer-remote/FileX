# Copyright (c) 2026 徐泽宇
"""144 association fact lifecycle operations."""

from sqlalchemy.orm import Session

from models.kb_association import (
    KbAssociationIndexState,
    KbEntity,
    KbEntityAlias,
    KbEntityMention,
    KbEvidenceClaim,
)


def delete_association_artifacts_for_file(db: Session, file_id: int) -> None:
    """Remove facts sourced from one file and garbage-collect unreferenced entities.

    Canonical entities are retained while any other file-scoped mention still
    points to them. This keeps reindex/delete lifecycle operations isolated.
    """
    mention_rows = (
        db.query(KbEntityMention.id, KbEntityMention.entity_id)
        .filter(KbEntityMention.file_id == file_id)
        .all()
    )
    mention_ids = [int(row.id) for row in mention_rows]
    candidate_entity_ids = {int(row.entity_id) for row in mention_rows if row.entity_id is not None}

    db.query(KbEvidenceClaim).filter(KbEvidenceClaim.file_id == file_id).delete(
        synchronize_session=False
    )
    if mention_ids:
        db.query(KbEvidenceClaim).filter(
            KbEvidenceClaim.subject_mention_id.in_(mention_ids)
            | KbEvidenceClaim.object_mention_id.in_(mention_ids)
        ).delete(synchronize_session=False)
        db.query(KbEntityAlias).filter(KbEntityAlias.mention_id.in_(mention_ids)).delete(
            synchronize_session=False
        )
    db.query(KbEntityAlias).filter(KbEntityAlias.source_file_id == file_id).delete(
        synchronize_session=False
    )
    db.query(KbEntityMention).filter(KbEntityMention.file_id == file_id).delete(
        synchronize_session=False
    )
    db.query(KbAssociationIndexState).filter(KbAssociationIndexState.file_id == file_id).delete(
        synchronize_session=False
    )

    if candidate_entity_ids:
        referenced_entity_ids = {
            int(row[0])
            for row in db.query(KbEntityMention.entity_id)
            .filter(KbEntityMention.entity_id.in_(candidate_entity_ids))
            .distinct()
            .all()
        }
        orphan_ids = candidate_entity_ids - referenced_entity_ids
        if orphan_ids:
            db.query(KbEntity).filter(KbEntity.id.in_(orphan_ids)).delete(synchronize_session=False)
