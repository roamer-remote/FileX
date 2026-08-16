# Copyright (c) 2026 徐泽宇
"""059 P3 T-27：S4 cutover 阶段判定与 legacy 路径守卫。"""

from __future__ import annotations

from fastapi import HTTPException, status
from sqlalchemy.orm import Session

from models.workspace import WORKSPACE_KIND_SHARED, Workspace, WorkspaceMember
from models.user import User
from services.system_setting_service import (
    get_enterprise_rbac_write_mode,
    is_enterprise_rbac_cutover,
    is_enterprise_rbac_enabled,
)
from services.workspace_access_service import ROLE_VIEWER, get_membership, role_at_least


def is_s4_cutover_active(db: Session) -> bool:
    """S4：RBAC 开启 + new_only + cutover。"""
    return (
        is_enterprise_rbac_enabled(db)
        and get_enterprise_rbac_write_mode(db) == "new_only"
        and is_enterprise_rbac_cutover(db)
    )


def legacy_resource_grants_api_removed(db: Session) -> bool:
    """S4 后移除 resource_grants 对外读写 API。"""
    return is_s4_cutover_active(db)


def legacy_workspace_member_role_writes_removed(db: Session) -> bool:
    """S4 后禁止经 legacy role 字段写入成员角色。"""
    return is_s4_cutover_active(db)


def assert_legacy_resource_grants_api_allowed(db: Session) -> None:
    if legacy_resource_grants_api_removed(db):
        raise HTTPException(
            status_code=status.HTTP_410_GONE,
            detail="S4 cutover 后 resource_grants API 已移除，请使用目录 ACL API",
        )


def assert_legacy_member_role_write_allowed(db: Session) -> None:
    if legacy_workspace_member_role_writes_removed(db):
        raise HTTPException(
            status_code=status.HTTP_410_GONE,
            detail="S4 cutover 后不可经 legacy 角色字段管理成员，请使用企业角色 API",
        )


def shared_member_has_workspace_access(
    db: Session,
    user: User,
    workspace_id: int,
    *,
    member: WorkspaceMember | None = None,
) -> bool:
    """共享空间成员是否纳入跨空间可读性并集（S4 仅看成员关系，不看 legacy role 列）。"""
    if user.is_admin and not member:
        return True
    member = member or get_membership(db, workspace_id, user.id)
    if not member:
        return False
    if is_s4_cutover_active(db):
        ws = db.query(Workspace).filter(Workspace.id == workspace_id).first()
        if ws and ws.kind == WORKSPACE_KIND_SHARED:
            return True
    return role_at_least(member.role, ROLE_VIEWER)
