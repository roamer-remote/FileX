# Copyright (c) 2026 徐泽宇
"""059 P1 T-10：共享空间成员 API（workspace_members + workspace_user_roles）。"""

from __future__ import annotations

from fastapi import HTTPException, status
from sqlalchemy.orm import Session

from models.enterprise_rbac import EnterpriseRole, WorkspaceUserRole
from models.user import User
from models.workspace import ROLE_VIEWER, WORKSPACE_ROLES, WorkspaceMember
from services.enterprise_rbac_seed import get_enterprise_role_by_slug
from services.enterprise_rbac_phase_service import assert_legacy_member_role_write_allowed
from services.workspace_access_service import uses_enterprise_rbac_for_workspace
from services.workspace_service import set_member_role

# 059 legacy workspace_members.role → enterprise_roles.slug（单向固定；新增 legacy 角色须同步更新）
LEGACY_WORKSPACE_ROLE_TO_ENTERPRISE_SLUG: dict[str, str] = {
    "admin": "space_admin",
    "curator": "folder_admin",
    "contributor": "editor",
    "viewer": "viewer",
    "auditor": "auditor",
}


def _enterprise_slugs_for_member(db: Session, workspace_id: int, user_id: int) -> list[str]:
    rows = (
        db.query(EnterpriseRole.slug)
        .join(WorkspaceUserRole, WorkspaceUserRole.role_id == EnterpriseRole.id)
        .filter(
            WorkspaceUserRole.workspace_id == workspace_id,
            WorkspaceUserRole.user_id == user_id,
            EnterpriseRole.is_active.is_(True),
        )
        .order_by(EnterpriseRole.slug.asc())
        .all()
    )
    return [str(r[0]) for r in rows]


def member_display_role(
    db: Session,
    *,
    workspace_id: int,
    user_id: int,
    legacy_role: str,
    rbac_on: bool,
) -> str:
    if not rbac_on:
        return legacy_role
    slugs = _enterprise_slugs_for_member(db, workspace_id, user_id)
    if slugs:
        return slugs[0]
    return LEGACY_WORKSPACE_ROLE_TO_ENTERPRISE_SLUG.get(legacy_role, legacy_role)


def sync_workspace_user_roles_from_legacy(
    db: Session,
    *,
    workspace_id: int,
    user_id: int,
    legacy_role: str,
) -> None:
    slug = LEGACY_WORKSPACE_ROLE_TO_ENTERPRISE_SLUG.get(legacy_role)
    if not slug:
        raise ValueError(f"无效角色: {legacy_role}")
    role = get_enterprise_role_by_slug(db, slug)
    db.query(WorkspaceUserRole).filter(
        WorkspaceUserRole.workspace_id == workspace_id,
        WorkspaceUserRole.user_id == user_id,
    ).delete(synchronize_session=False)
    db.add(
        WorkspaceUserRole(
            workspace_id=workspace_id,
            user_id=user_id,
            role_id=role.id,
        )
    )
    db.flush()


def remove_workspace_member(db: Session, *, workspace_id: int, user_id: int) -> None:
    if uses_enterprise_rbac_for_workspace(db, workspace_id):
        db.query(WorkspaceUserRole).filter(
            WorkspaceUserRole.workspace_id == workspace_id,
            WorkspaceUserRole.user_id == user_id,
        ).delete(synchronize_session=False)
    db.query(WorkspaceMember).filter(
        WorkspaceMember.workspace_id == workspace_id,
        WorkspaceMember.user_id == user_id,
    ).delete(synchronize_session=False)


def upsert_workspace_member(
    db: Session,
    *,
    workspace_id: int,
    target_user_id: int,
    legacy_role: str,
    acting_user: User,
) -> WorkspaceMember:
    assert_legacy_member_role_write_allowed(db)

    if legacy_role not in WORKSPACE_ROLES:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="无效角色")

    rbac_on = uses_enterprise_rbac_for_workspace(db, workspace_id)
    existing = (
        db.query(WorkspaceMember)
        .filter(
            WorkspaceMember.workspace_id == workspace_id,
            WorkspaceMember.user_id == target_user_id,
        )
        .first()
    )

    if rbac_on and not acting_user.is_admin:
        if legacy_role != ROLE_VIEWER:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="仅站点管理员可分配企业角色",
            )
        if existing and existing.role != ROLE_VIEWER:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="仅站点管理员可变更成员角色",
            )
        member = set_member_role(db, workspace_id, target_user_id, ROLE_VIEWER)
        return member

    member = set_member_role(db, workspace_id, target_user_id, legacy_role)
    if rbac_on:
        sync_workspace_user_roles_from_legacy(
            db,
            workspace_id=workspace_id,
            user_id=target_user_id,
            legacy_role=legacy_role,
        )
    return member
