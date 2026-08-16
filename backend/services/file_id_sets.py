# Copyright (c) 2026 徐泽宇
"""工作空间内文件 ID 集合查询（acl_service / PermissionService 共用）。"""

from __future__ import annotations

from sqlalchemy.orm import Session

from models.file import File as FileModel


def all_file_ids_in_workspace(db: Session, workspace_id: int) -> set[int]:
    rows = db.query(FileModel.id).filter(FileModel.workspace_id == workspace_id).all()
    return {int(r[0]) for r in rows}
