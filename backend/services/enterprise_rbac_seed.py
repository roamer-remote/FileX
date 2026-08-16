# Copyright (c) 2026 徐泽宇
"""059 企业 RBAC seed 与查询辅助。"""

from __future__ import annotations

from sqlalchemy.orm import Session

from models.enterprise_rbac import (
    BUILTIN_ROLE_SLUGS,
    DEPARTMENT_UNASSIGNED_NAME,
    Department,
    EnterpriseRole,
)


def get_unassigned_department(db: Session) -> Department:
    row = db.query(Department).filter(Department.name == DEPARTMENT_UNASSIGNED_NAME).first()
    if not row:
        raise RuntimeError("未分配部门不存在，请先执行 0025_enterprise_rbac 迁移")
    return row


def get_unassigned_department_id(db: Session) -> int:
    return int(get_unassigned_department(db).id)


def get_enterprise_role_by_slug(db: Session, slug: str) -> EnterpriseRole:
    if slug not in BUILTIN_ROLE_SLUGS:
        raise ValueError(f"未知内置角色 slug: {slug}")
    row = db.query(EnterpriseRole).filter(EnterpriseRole.slug == slug).first()
    if not row:
        raise RuntimeError(f"内置角色 {slug} 不存在，请先执行 0025_enterprise_rbac 迁移")
    return row
