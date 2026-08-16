# Copyright (c) 2026 徐泽宇
"""059 P2：用户组 CRUD 服务。"""

from __future__ import annotations

from fastapi import HTTPException, status
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from models.enterprise_rbac import SUBJECT_GROUP, FolderAcl, Group
from utils.timezone import to_beijing_time


class GroupDeleteConflictError(Exception):
    """删除用户组冲突（含 ACL 引用时需返回 affected_acl_ids）。"""

    def __init__(self, detail: str, *, affected_acl_ids: list[int] | None = None):
        super().__init__(detail)
        self.detail = detail
        self.affected_acl_ids = affected_acl_ids or []


def _group_or_404(db: Session, group_id: int) -> Group:
    row = db.query(Group).filter(Group.id == group_id).first()
    if not row:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="用户组不存在")
    return row


def _group_to_dict(group: Group) -> dict:
    return {
        "id": group.id,
        "name": group.name,
        "description": group.description,
        "created_at": to_beijing_time(group.created_at).isoformat() if group.created_at else "",
    }


def list_groups(db: Session) -> list[dict]:
    rows = db.query(Group).order_by(Group.name, Group.id).all()
    return [_group_to_dict(g) for g in rows]




def _flush_or_raise_duplicate(db: Session) -> None:
    try:
        db.flush()
    except IntegrityError as exc:
        db.rollback()
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="用户组名称已存在") from exc

def _ensure_unique_group_name(db: Session, name: str, *, exclude_id: int | None = None) -> None:
    q = db.query(Group.id).filter(Group.name == name.strip())
    if exclude_id is not None:
        q = q.filter(Group.id != exclude_id)
    if q.first():
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="用户组名称已存在")


def create_group(db: Session, *, name: str, description: str | None = None) -> dict:
    clean_name = name.strip()
    _ensure_unique_group_name(db, clean_name)
    group = Group(name=clean_name, description=description.strip() if description else None)
    db.add(group)
    _flush_or_raise_duplicate(db)
    return _group_to_dict(group)


def update_group(
    db: Session,
    group_id: int,
    *,
    name: str | None = None,
    description: str | None = None,
) -> dict:
    group = _group_or_404(db, group_id)
    if name is not None:
        clean_name = name.strip()
        _ensure_unique_group_name(db, clean_name, exclude_id=group.id)
        group.name = clean_name
    if description is not None:
        group.description = description.strip() or None
    _flush_or_raise_duplicate(db)
    return _group_to_dict(group)


def delete_group(db: Session, group_id: int) -> None:
    group = _group_or_404(db, group_id)
    acl_rows = (
        db.query(FolderAcl.id)
        .filter(FolderAcl.subject_type == SUBJECT_GROUP, FolderAcl.subject_id == group_id)
        .all()
    )
    if acl_rows:
        acl_ids = [int(r[0]) for r in acl_rows]
        raise GroupDeleteConflictError(
            f"该用户组在 {len(acl_ids)} 条目录 ACL 中被引用，请先移除",
            affected_acl_ids=acl_ids,
        )
    db.delete(group)
    db.flush()
