# Copyright (c) 2026 徐泽宇
"""059 P2 T-16：管理员目录 ACL（folder_acl）服务。"""

from __future__ import annotations

from fastapi import HTTPException, status
from sqlalchemy.orm import Session

from models.enterprise_rbac import (
    DEPARTMENT_UNASSIGNED_NAME,
    PERMISSIONS,
    SUBJECT_DEPARTMENT,
    SUBJECT_GROUP,
    SUBJECT_ROLE,
    SUBJECT_TYPES,
    SUBJECT_USER,
    Department,
    EnterpriseRole,
    FolderAcl,
    Group,
)
from models.folder import Folder
from models.workspace import WORKSPACE_KIND_SHARED, Workspace, WorkspaceMember
from services.enterprise_rbac_seed import get_unassigned_department
from services.rbac_dual_write_service import (
    folder_acl_entry_needs_rollback_warning,
    is_s2_dual_write_active,
    mirror_folder_acl_to_legacy_grant,
)
from utils.timezone import naive_db_now


def _acl_to_dict(row: FolderAcl) -> dict:
    return {
        "id": row.id,
        "folder_id": row.folder_id,
        "subject_type": row.subject_type,
        "subject_id": row.subject_id,
        "permission": row.permission,
        "created_at": row.created_at.isoformat() if row.created_at else "",
        "updated_at": row.updated_at.isoformat() if row.updated_at else "",
    }


def require_shared_workspace_for_acl(ws: Workspace) -> None:
    if ws.kind != WORKSPACE_KIND_SHARED:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="仅共享知识空间可配置目录 ACL",
        )


def resolve_folder_id_for_workspace(
    db: Session,
    *,
    workspace_id: int,
    folder_id_or_root: str,
) -> int | None:
    if folder_id_or_root == "root":
        return None
    try:
        folder_id = int(folder_id_or_root)
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="无效的目录 ID",
        ) from exc
    folder = db.query(Folder).filter(Folder.id == folder_id).first()
    if not folder:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="目录不存在")
    if folder.workspace_id != workspace_id:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="目录不属于该知识空间",
        )
    return folder_id


def validate_folder_belongs_to_workspace(
    db: Session,
    *,
    workspace_id: int,
    folder_id: int | None,
) -> None:
    if folder_id is None:
        return
    folder = db.query(Folder).filter(Folder.id == folder_id).first()
    if not folder:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="目录不存在")
    if folder.workspace_id != workspace_id:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="目录不属于该知识空间",
        )


def validate_acl_subject(
    db: Session,
    *,
    workspace_id: int,
    subject_type: str,
    subject_id: int,
) -> None:
    if subject_type not in SUBJECT_TYPES:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="无效 ACL 主体类型")
    if subject_type == SUBJECT_USER:
        member = (
            db.query(WorkspaceMember)
            .filter(
                WorkspaceMember.workspace_id == workspace_id,
                WorkspaceMember.user_id == subject_id,
            )
            .first()
        )
        if not member:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="ACL 用户主体须为该空间成员",
            )
        return
    if subject_type == SUBJECT_ROLE:
        role = db.query(EnterpriseRole).filter(EnterpriseRole.id == subject_id).first()
        if not role:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="企业角色不存在")
        if not role.is_active:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="企业角色已禁用")
        return
    if subject_type == SUBJECT_GROUP:
        group = db.query(Group).filter(Group.id == subject_id).first()
        if not group:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="用户组不存在")
        return
    if subject_type == SUBJECT_DEPARTMENT:
        dept = db.query(Department).filter(Department.id == subject_id).first()
        if not dept:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="部门不存在")
        unassigned = get_unassigned_department(db)
        if dept.id == unassigned.id or dept.name == DEPARTMENT_UNASSIGNED_NAME:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="不可对「未分配」部门配置目录 ACL",
            )


def _find_acl_row(
    db: Session,
    *,
    workspace_id: int,
    folder_id: int | None,
    subject_type: str,
    subject_id: int,
) -> FolderAcl | None:
    q = db.query(FolderAcl).filter(
        FolderAcl.workspace_id == workspace_id,
        FolderAcl.subject_type == subject_type,
        FolderAcl.subject_id == subject_id,
    )
    if folder_id is None:
        q = q.filter(FolderAcl.folder_id.is_(None))
    else:
        q = q.filter(FolderAcl.folder_id == folder_id)
    return q.first()


def upsert_folder_acl_entry(
    db: Session,
    *,
    workspace_id: int,
    folder_id: int | None,
    subject_type: str,
    subject_id: int,
    permission: str,
    admin_user_id: int,
) -> tuple[FolderAcl, bool]:
    if permission not in PERMISSIONS:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="无效权限档位")

    validate_acl_subject(
        db,
        workspace_id=workspace_id,
        subject_type=subject_type,
        subject_id=subject_id,
    )

    now = naive_db_now()
    existing = _find_acl_row(
        db,
        workspace_id=workspace_id,
        folder_id=folder_id,
        subject_type=subject_type,
        subject_id=subject_id,
    )
    if existing:
        existing.permission = permission
        existing.updated_by_user_id = admin_user_id
        existing.updated_at = now
        db.flush()
        return existing, False

    row = FolderAcl(
        workspace_id=workspace_id,
        folder_id=folder_id,
        subject_type=subject_type,
        subject_id=subject_id,
        permission=permission,
        created_by_user_id=admin_user_id,
        updated_by_user_id=admin_user_id,
        updated_at=now,
    )
    db.add(row)
    db.flush()
    return row, True


def list_workspace_folder_acl(db: Session, workspace_id: int) -> list[dict]:
    rows = (
        db.query(FolderAcl)
        .filter(FolderAcl.workspace_id == workspace_id)
        .order_by(FolderAcl.folder_id.asc().nullsfirst(), FolderAcl.id.asc())
        .all()
    )
    return [_acl_to_dict(row) for row in rows]


def _apply_s2_dual_write_for_acl_entry(
    db: Session,
    *,
    workspace_id: int,
    folder_id: int | None,
    subject_type: str,
    subject_id: int,
    permission: str,
    admin_user_id: int,
) -> bool:
    if not is_s2_dual_write_active(db):
        return False
    if folder_acl_entry_needs_rollback_warning(
        folder_id=folder_id,
        subject_type=subject_type,
        permission=permission,
    ):
        return True
    if folder_id is not None:
        mirror_folder_acl_to_legacy_grant(
            db,
            workspace_id=workspace_id,
            folder_id=folder_id,
            subject_type=subject_type,
            subject_id=subject_id,
            permission=permission,
            admin_user_id=admin_user_id,
        )
    return False


def put_workspace_folder_acl_bulk(
    db: Session,
    *,
    workspace_id: int,
    entries: list[dict],
    admin_user_id: int,
) -> dict:
    upserted = 0
    updated = 0
    rollback_warning = False
    seen: set[tuple[int | None, str, int]] = set()
    for entry in entries:
        folder_id = entry.get("folder_id")
        subject_type = entry["subject_type"]
        subject_id = int(entry["subject_id"])
        permission = entry["permission"]
        key = (folder_id, subject_type, subject_id)
        if key in seen:
            continue
        seen.add(key)
        validate_folder_belongs_to_workspace(db, workspace_id=workspace_id, folder_id=folder_id)
        _, created = upsert_folder_acl_entry(
            db,
            workspace_id=workspace_id,
            folder_id=folder_id,
            subject_type=subject_type,
            subject_id=subject_id,
            permission=permission,
            admin_user_id=admin_user_id,
        )
        if created:
            upserted += 1
        else:
            updated += 1
        if _apply_s2_dual_write_for_acl_entry(
            db,
            workspace_id=workspace_id,
            folder_id=folder_id,
            subject_type=subject_type,
            subject_id=subject_id,
            permission=permission,
            admin_user_id=admin_user_id,
        ):
            rollback_warning = True
    return {
        "upserted": upserted,
        "updated": updated,
        "rollback_warning": rollback_warning,
    }


def put_single_folder_acl(
    db: Session,
    *,
    workspace_id: int,
    folder_id: int | None,
    entries: list[dict],
    admin_user_id: int,
) -> dict:
    upserted = 0
    updated = 0
    rollback_warning = False
    seen: set[tuple[str, int]] = set()
    for entry in entries:
        subject_type = entry["subject_type"]
        subject_id = int(entry["subject_id"])
        permission = entry["permission"]
        key = (subject_type, subject_id)
        if key in seen:
            continue
        seen.add(key)
        _, created = upsert_folder_acl_entry(
            db,
            workspace_id=workspace_id,
            folder_id=folder_id,
            subject_type=subject_type,
            subject_id=subject_id,
            permission=permission,
            admin_user_id=admin_user_id,
        )
        if created:
            upserted += 1
        else:
            updated += 1
        if _apply_s2_dual_write_for_acl_entry(
            db,
            workspace_id=workspace_id,
            folder_id=folder_id,
            subject_type=subject_type,
            subject_id=subject_id,
            permission=permission,
            admin_user_id=admin_user_id,
        ):
            rollback_warning = True
    return {
        "upserted": upserted,
        "updated": updated,
        "rollback_warning": rollback_warning,
    }
