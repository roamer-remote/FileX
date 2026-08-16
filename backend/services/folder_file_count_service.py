# Copyright (c) 2026 徐泽宇
"""目录直接文件数统计（不含子目录内文件）。

Authors:
    徐泽宇

Copyright:
    © 2026 徐泽宇
"""

from __future__ import annotations

from sqlalchemy import func
from sqlalchemy.orm import Session

from models.file import File as FileModel
from models.user import User
from services.acl_service import accessible_file_ids
from services.wiki_page_filters import source_files_only
from services.workspace_access_service import require_workspace_member


def direct_file_counts_for_workspace(
    db: Session,
    user: User,
    workspace_id: int,
) -> tuple[dict[int, int], int]:
    """返回 (folder_id -> 直接文件数, 未分类直接文件数)。"""
    member = require_workspace_member(db, user, workspace_id)
    allowed = accessible_file_ids(db, user, workspace_id, member=member)
    if not allowed:
        return {}, 0

    query = source_files_only(
        db.query(FileModel.folder_id, func.count(FileModel.id))
        .filter(FileModel.workspace_id == workspace_id)
        .filter(FileModel.id.in_(allowed))
    )
    rows = query.group_by(FileModel.folder_id).all()

    folder_counts: dict[int, int] = {}
    uncategorized = 0
    for folder_id, count in rows:
        n = int(count or 0)
        if folder_id is None:
            uncategorized = n
        else:
            folder_counts[int(folder_id)] = n
    return folder_counts, uncategorized
