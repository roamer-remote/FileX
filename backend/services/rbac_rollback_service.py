# Copyright (c) 2026 徐泽宇
"""059 P3 T-25：S2 关开关回滚报告（non-mappable 变更清单）。"""

from __future__ import annotations

from sqlalchemy.orm import Session

from models.enterprise_rbac import EnterpriseRole, FolderAcl, WorkspaceUserRole
from services.rbac_dual_write_service import is_legacy_mappable_folder_acl


def _folder_acl_entry_dict(row: FolderAcl) -> dict:
    return {
        "kind": "folder_acl",
        "id": row.id,
        "folder_id": row.folder_id,
        "subject_type": row.subject_type,
        "subject_id": row.subject_id,
        "permission": row.permission,
        "reason": "non_mappable_folder_acl",
    }


def _workspace_user_role_dict(
    *,
    workspace_id: int,
    user_id: int,
    role_id: int,
    role_slug: str,
) -> dict:
    return {
        "kind": "workspace_user_role",
        "workspace_id": workspace_id,
        "user_id": user_id,
        "role_id": role_id,
        "role_slug": role_slug,
        "reason": "workspace_user_roles_not_rollbackable",
    }


def generate_s2_rollback_report(db: Session, *, workspace_id: int) -> dict:
    """列出 S2 关开关回 S1 时不会保留到新表路径的 non-mappable 变更。"""
    non_mappable: list[dict] = []

    acl_rows = (
        db.query(FolderAcl)
        .filter(FolderAcl.workspace_id == workspace_id)
        .order_by(FolderAcl.id.asc())
        .all()
    )
    for row in acl_rows:
        if not is_legacy_mappable_folder_acl(
            folder_id=row.folder_id,
            subject_type=row.subject_type,
            permission=row.permission,
        ):
            non_mappable.append(_folder_acl_entry_dict(row))

    wur_rows = (
        db.query(WorkspaceUserRole, EnterpriseRole.slug)
        .join(EnterpriseRole, EnterpriseRole.id == WorkspaceUserRole.role_id)
        .filter(WorkspaceUserRole.workspace_id == workspace_id)
        .order_by(WorkspaceUserRole.user_id.asc(), EnterpriseRole.slug.asc())
        .all()
    )
    for wur, slug in wur_rows:
        non_mappable.append(
            _workspace_user_role_dict(
                workspace_id=workspace_id,
                user_id=int(wur.user_id),
                role_id=int(wur.role_id),
                role_slug=str(slug),
            )
        )

    return {
        "workspace_id": workspace_id,
        "non_mappable_entries": non_mappable,
        "warning_count": len(non_mappable),
    }
