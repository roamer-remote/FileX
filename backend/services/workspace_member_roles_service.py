# Copyright (c) 2026 徐泽宇
"""059 P2 T-16：管理员按空间分配企业角色（workspace_user_roles）。"""

from __future__ import annotations

from fastapi import HTTPException, status
from sqlalchemy.orm import Session

from models.enterprise_rbac import EnterpriseRole, WorkspaceUserRole
from models.user import User
from models.workspace import WORKSPACE_KIND_SHARED, Workspace, WorkspaceMember
from services.rbac_dual_write_service import is_s2_dual_write_active


def _require_shared_workspace(ws: Workspace) -> None:
    if ws.kind != WORKSPACE_KIND_SHARED:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="仅共享知识空间可分配企业角色",
        )


def _member_or_404(db: Session, *, workspace_id: int, user_id: int) -> WorkspaceMember:
    row = (
        db.query(WorkspaceMember)
        .filter(
            WorkspaceMember.workspace_id == workspace_id,
            WorkspaceMember.user_id == user_id,
        )
        .first()
    )
    if not row:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="用户不是该空间成员")
    return row


def _user_or_404(db: Session, user_id: int) -> User:
    row = db.query(User).filter(User.id == user_id).first()
    if not row:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="用户不存在")
    return row


def set_workspace_member_roles(
    db: Session,
    *,
    workspace: Workspace,
    user_id: int,
    role_ids: list[int],
) -> dict:
    _require_shared_workspace(workspace)
    _user_or_404(db, user_id)
    _member_or_404(db, workspace_id=workspace.id, user_id=user_id)

    unique_role_ids = list(dict.fromkeys(role_ids))
    found: dict[int, EnterpriseRole] = {}
    if unique_role_ids:
        roles = (
            db.query(EnterpriseRole)
            .filter(EnterpriseRole.id.in_(unique_role_ids))
            .all()
        )
        found = {role.id: role for role in roles}
        missing = [rid for rid in unique_role_ids if rid not in found]
        if missing:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"企业角色不存在: {', '.join(str(i) for i in missing)}",
            )
        inactive = [rid for rid in unique_role_ids if not found[rid].is_active]
        if inactive:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"企业角色已禁用: {', '.join(str(i) for i in inactive)}",
            )

    db.query(WorkspaceUserRole).filter(
        WorkspaceUserRole.workspace_id == workspace.id,
        WorkspaceUserRole.user_id == user_id,
    ).delete(synchronize_session=False)

    slugs: list[str] = []
    if unique_role_ids:
        for role_id in unique_role_ids:
            role = found[role_id]
            db.add(
                WorkspaceUserRole(
                    workspace_id=workspace.id,
                    user_id=user_id,
                    role_id=role_id,
                )
            )
            slugs.append(role.slug)
        db.flush()

    return {
        "user_id": user_id,
        "role_ids": unique_role_ids,
        "role_slugs": slugs,
        "rollback_warning": is_s2_dual_write_active(db),
    }


def get_workspace_member_roles(
    db: Session,
    *,
    workspace: Workspace,
    user_id: int,
) -> dict:
    _require_shared_workspace(workspace)
    _user_or_404(db, user_id)
    _member_or_404(db, workspace_id=workspace.id, user_id=user_id)

    rows = (
        db.query(WorkspaceUserRole.role_id, EnterpriseRole.slug)
        .join(EnterpriseRole, EnterpriseRole.id == WorkspaceUserRole.role_id)
        .filter(
            WorkspaceUserRole.workspace_id == workspace.id,
            WorkspaceUserRole.user_id == user_id,
        )
        .order_by(EnterpriseRole.slug.asc())
        .all()
    )
    role_ids = [int(r[0]) for r in rows]
    slugs = [str(r[1]) for r in rows]
    return {
        "user_id": user_id,
        "role_ids": role_ids,
        "role_slugs": slugs,
    }
