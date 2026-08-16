# Copyright (c) 2026 徐泽宇
"""059 P2：企业角色 CRUD 服务。"""

from __future__ import annotations

import re

from fastapi import HTTPException, status
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from models.enterprise_rbac import (
    BUILTIN_ROLE_SLUGS,
    SUBJECT_ROLE,
    EnterpriseRole,
    FolderAcl,
    WorkspaceUserRole,
)
from utils.timezone import to_beijing_time

_SLUG_PATTERN = re.compile(r"^[a-z][a-z0-9_]*$")


def _role_or_404(db: Session, role_id: int) -> EnterpriseRole:
    row = db.query(EnterpriseRole).filter(EnterpriseRole.id == role_id).first()
    if not row:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="企业角色不存在")
    return row


def _role_to_dict(role: EnterpriseRole) -> dict:
    return {
        "id": role.id,
        "slug": role.slug,
        "name": role.name,
        "description": role.description,
        "is_builtin": bool(role.is_builtin),
        "is_active": bool(role.is_active),
        "created_at": to_beijing_time(role.created_at).isoformat() if role.created_at else "",
    }


def _validate_custom_slug(slug: str) -> str:
    clean = slug.strip()
    if not _SLUG_PATTERN.fullmatch(clean):
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="slug 须为小写字母开头，仅含小写字母、数字、下划线")
    if clean in BUILTIN_ROLE_SLUGS:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="不可使用内置角色 slug")
    return clean


def _ensure_unique_slug(db: Session, slug: str, *, exclude_id: int | None = None) -> None:
    q = db.query(EnterpriseRole.id).filter(EnterpriseRole.slug == slug)
    if exclude_id is not None:
        q = q.filter(EnterpriseRole.id != exclude_id)
    if q.first():
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="企业角色 slug 已存在")


def _flush_or_raise_duplicate(db: Session) -> None:
    try:
        db.flush()
    except IntegrityError as exc:
        db.rollback()
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="企业角色 slug 已存在") from exc


def list_enterprise_roles(db: Session) -> list[dict]:
    rows = db.query(EnterpriseRole).order_by(EnterpriseRole.is_builtin.desc(), EnterpriseRole.slug).all()
    return [_role_to_dict(r) for r in rows]


def create_enterprise_role(
    db: Session,
    *,
    slug: str,
    name: str,
    description: str | None = None,
) -> dict:
    clean_slug = _validate_custom_slug(slug)
    _ensure_unique_slug(db, clean_slug)
    role = EnterpriseRole(
        slug=clean_slug,
        name=name.strip(),
        description=description.strip() if description else None,
        is_builtin=False,
        is_active=True,
    )
    db.add(role)
    _flush_or_raise_duplicate(db)
    return _role_to_dict(role)


def update_enterprise_role(
    db: Session,
    role_id: int,
    *,
    name: str | None = None,
    description: str | None = None,
    is_active: bool | None = None,
) -> dict:
    role = _role_or_404(db, role_id)
    if name is not None:
        role.name = name.strip()
    if description is not None:
        role.description = description.strip() or None
    if is_active is not None:
        role.is_active = is_active
    db.flush()
    return _role_to_dict(role)


def delete_enterprise_role(db: Session, role_id: int) -> dict:
    role = _role_or_404(db, role_id)
    if role.is_builtin:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="内置角色不可删除")

    wur_count = (
        db.query(WorkspaceUserRole)
        .filter(WorkspaceUserRole.role_id == role_id)
        .count()
    )
    acl_deleted = (
        db.query(FolderAcl)
        .filter(FolderAcl.subject_type == SUBJECT_ROLE, FolderAcl.subject_id == role_id)
        .delete(synchronize_session=False)
    )
    slug = role.slug
    db.delete(role)
    db.flush()
    acl_count = int(acl_deleted)
    return {
        "deleted_user_role_assignments": wur_count,
        "deleted_acl_rows": acl_count,
        "message": f"已删除自定义角色 `{slug}`，移除 {wur_count} 个角色分配及 {acl_count} 条 ACL",
    }
