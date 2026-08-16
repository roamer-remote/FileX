# Copyright (c) 2026 徐泽宇
"""059 PermissionService：共享空间目录 ACL 有效权限判定。"""

from __future__ import annotations

from sqlalchemy import false, or_, select, union_all
from sqlalchemy.orm import Session

from models.enterprise_rbac import (
    PERM_LIST,
    PERM_MANAGE,
    PERM_READ,
    PERMISSION_RANK,
    SUBJECT_DEPARTMENT,
    SUBJECT_GROUP,
    SUBJECT_ROLE,
    SUBJECT_USER,
    EnterpriseRole,
    FolderAcl,
    UserGroup,
    WorkspaceUserRole,
)
from models.file import File as FileModel
from models.folder import Folder as FolderModel
from models.user import User
from models.workspace import (
    ROLE_ADMIN,
    ROLE_VIEWER,
    WORKSPACE_KIND_PERSONAL,
    WORKSPACE_KIND_SHARED,
    Workspace,
    WorkspaceMember,
)
from services.file_id_sets import all_file_ids_in_workspace
from services.system_setting_service import is_enterprise_rbac_enabled, is_shared_workspaces_enabled
from services.enterprise_rbac_phase_service import shared_member_has_workspace_access
from services.workspace_access_service import (
    get_membership,
    role_at_least,
    uses_enterprise_rbac_for_workspace,
)
from services.workspace_service import ensure_personal_workspace, list_user_workspaces


def _require_rbac_enabled(db: Session) -> None:
    """PermissionService 读路径前置条件：须 enterprise_rbac_enabled=true（acl_service 委托层保证）。"""
    if not is_enterprise_rbac_enabled(db):
        raise RuntimeError(
            "PermissionService 读路径须在 enterprise_rbac_enabled=true 时调用；"
            "请经 acl_service 入口访问"
        )


def permission_rank(permission: str) -> int:
    return PERMISSION_RANK[permission]


def permission_at_least(effective: str | None, minimum: str) -> bool:
    if effective is None:
        return False
    return permission_rank(effective) >= permission_rank(minimum)


def _max_permission(grants: list[str]) -> str | None:
    if not grants:
        return None
    return max(grants, key=permission_rank)


def _folder_acl_rows(
    db: Session,
    workspace_id: int,
    folder_id: int | None,
) -> list[FolderAcl]:
    q = db.query(FolderAcl).filter(FolderAcl.workspace_id == workspace_id)
    if folder_id is None:
        q = q.filter(FolderAcl.folder_id.is_(None))
    else:
        q = q.filter(FolderAcl.folder_id == folder_id)
    return list(q.all())


def _active_workspace_role_ids(db: Session, user_id: int, workspace_id: int) -> set[int]:
    rows = (
        db.query(WorkspaceUserRole.role_id)
        .join(EnterpriseRole, EnterpriseRole.id == WorkspaceUserRole.role_id)
        .filter(
            WorkspaceUserRole.workspace_id == workspace_id,
            WorkspaceUserRole.user_id == user_id,
            EnterpriseRole.is_active.is_(True),
        )
        .all()
    )
    return {int(r[0]) for r in rows}


def _user_group_ids(db: Session, user_id: int) -> set[int]:
    rows = db.query(UserGroup.group_id).filter(UserGroup.user_id == user_id).all()
    return {int(r[0]) for r in rows}


def _tier_grant(
    db: Session,
    user: User,
    workspace_id: int,
    rows: list[FolderAcl],
) -> str | None:
    role_ids = _active_workspace_role_ids(db, user.id, workspace_id)
    group_ids = _user_group_ids(db, user.id)
    dept_id = user.primary_department_id

    user_grants: list[str] = []
    role_grants: list[str] = []
    group_grants: list[str] = []
    dept_grants: list[str] = []

    for row in rows:
        perm = row.permission
        if row.subject_type == SUBJECT_USER and row.subject_id == user.id:
            user_grants.append(perm)
        elif row.subject_type == SUBJECT_ROLE and row.subject_id in role_ids:
            role_grants.append(perm)
        elif row.subject_type == SUBJECT_GROUP and row.subject_id in group_ids:
            group_grants.append(perm)
        elif (
            row.subject_type == SUBJECT_DEPARTMENT
            and dept_id is not None
            and row.subject_id == dept_id
        ):
            dept_grants.append(perm)

    for tier in (user_grants, role_grants, group_grants, dept_grants):
        best = _max_permission(tier)
        if best is not None:
            return best
    return None


def effective_folder_permission(
    db: Session,
    user: User,
    workspace_id: int,
    folder_id: int | None,
) -> str | None:
    """共享空间目录有效权限；非成员、RBAC 未启用或零 ACL 返回 None。"""
    if user.is_admin:
        return PERM_MANAGE

    if not is_enterprise_rbac_enabled(db):
        return None

    ws = db.query(Workspace).filter(Workspace.id == workspace_id).first()
    if not ws or ws.kind != WORKSPACE_KIND_SHARED:
        return None

    if not get_membership(db, workspace_id, user.id):
        return None

    rows = _folder_acl_rows(db, workspace_id, folder_id)
    return _tier_grant(db, user, workspace_id, rows)


def effective_file_permission(db: Session, user: User, file: FileModel) -> str | None:
    if user.is_admin:
        return PERM_MANAGE

    ws_id = file.workspace_id
    if not ws_id:
        return PERM_READ if file.user_id == user.id else None

    ws = db.query(Workspace).filter(Workspace.id == ws_id).first()
    if not ws:
        return None

    if ws.kind == WORKSPACE_KIND_PERSONAL:
        return PERM_MANAGE if file.user_id == user.id else None

    if file.folder_id is None:
        return PERM_READ if file.user_id == user.id else None

    return effective_folder_permission(db, user, ws_id, file.folder_id)


def _listable_folder_ids(db: Session, user: User, workspace_id: int) -> set[int]:
    rows = db.query(FolderModel.id).filter(FolderModel.workspace_id == workspace_id).all()
    return {
        int(r[0])
        for r in rows
        if permission_at_least(
            effective_folder_permission(db, user, workspace_id, int(r[0])),
            PERM_LIST,
        )
    }


def listable_folder_ids(db: Session, user: User, workspace_id: int) -> set[int]:
    """共享空间 RBAC 下用户可在目录树中看见的 folder id（effective >= list）。"""
    _require_rbac_enabled(db)
    if user.is_admin:
        rows = db.query(FolderModel.id).filter(FolderModel.workspace_id == workspace_id).all()
        return {int(r[0]) for r in rows}
    return _listable_folder_ids(db, user, workspace_id)


def is_zero_acl_workspace_member(db: Session, user: User, workspace_id: int) -> bool:
    """共享空间 RBAC 成员：根与各文件夹均无有效 ACL（effective 全为 None）。"""
    if not uses_enterprise_rbac_for_workspace(db, workspace_id):
        return False
    if user.is_admin:
        return False
    if not get_membership(db, workspace_id, user.id):
        return False
    if effective_folder_permission(db, user, workspace_id, None) is not None:
        return False
    rows = db.query(FolderModel.id).filter(FolderModel.workspace_id == workspace_id).all()
    for row in rows:
        if effective_folder_permission(db, user, workspace_id, int(row[0])) is not None:
            return False
    return True


def _readable_folder_ids(db: Session, user: User, workspace_id: int) -> set[int]:
    rows = db.query(FolderModel.id).filter(FolderModel.workspace_id == workspace_id).all()
    return {
        int(r[0])
        for r in rows
        if permission_at_least(
            effective_folder_permission(db, user, workspace_id, int(r[0])),
            PERM_READ,
        )
    }


def user_can_read_file(db: Session, user: User, file: FileModel) -> bool:
    _require_rbac_enabled(db)
    return permission_at_least(effective_file_permission(db, user, file), PERM_READ)


def accessible_file_ids(
    db: Session,
    user: User,
    workspace_id: int,
    *,
    member: WorkspaceMember | None = None,
) -> set[int]:
    _require_rbac_enabled(db)
    if user.is_admin:
        return all_file_ids_in_workspace(db, workspace_id)

    ws = db.query(Workspace).filter(Workspace.id == workspace_id).first()
    if not ws:
        return set()

    if ws.kind == WORKSPACE_KIND_PERSONAL:
        rows = (
            db.query(FileModel.id)
            .filter(FileModel.workspace_id == workspace_id, FileModel.user_id == user.id)
            .all()
        )
        return {int(r[0]) for r in rows}

    member = member or get_membership(db, workspace_id, user.id)
    if not member:
        return set()

    folder_ids = _readable_folder_ids(db, user, workspace_id)
    conditions = [
        (FileModel.folder_id.is_(None)) & (FileModel.user_id == user.id),
    ]
    if folder_ids:
        conditions.append(FileModel.folder_id.in_(folder_ids))
    rows = (
        db.query(FileModel.id)
        .filter(FileModel.workspace_id == workspace_id)
        .filter(or_(*conditions))
        .all()
    )
    return {int(r[0]) for r in rows}


def readable_file_ids_subquery(
    db: Session,
    user: User,
    workspace_id: int,
    *,
    member: WorkspaceMember | None = None,
):
    _require_rbac_enabled(db)
    if user.is_admin:
        return select(FileModel.id).where(FileModel.workspace_id == workspace_id)

    ws = db.query(Workspace).filter(Workspace.id == workspace_id).first()
    if not ws:
        return select(FileModel.id).where(false())

    if ws.kind == WORKSPACE_KIND_PERSONAL:
        return select(FileModel.id).where(
            FileModel.workspace_id == workspace_id,
            FileModel.user_id == user.id,
        )

    member = member or get_membership(db, workspace_id, user.id)
    if not member:
        return select(FileModel.id).where(false())

    folder_ids = _readable_folder_ids(db, user, workspace_id)
    conditions = [
        (FileModel.folder_id.is_(None)) & (FileModel.user_id == user.id),
    ]
    if folder_ids:
        conditions.append(FileModel.folder_id.in_(folder_ids))
    return select(FileModel.id).where(
        FileModel.workspace_id == workspace_id,
        or_(*conditions),
    )


def apply_readable_files_filter(
    query,
    db: Session,
    user: User,
    workspace_id: int,
    *,
    member: WorkspaceMember | None = None,
):
    return query.filter(
        FileModel.id.in_(readable_file_ids_subquery(db, user, workspace_id, member=member))
    )


def readable_file_ids_all_member_workspaces_subquery(db: Session, user: User):
    _require_rbac_enabled(db)
    ensure_personal_workspace(db, user)
    shared_on = is_shared_workspaces_enabled(db)
    rows = list_user_workspaces(db, user.id)
    workspace_ids: list[int] = []
    for ws, _role in rows:
        if not shared_on and ws.kind == WORKSPACE_KIND_SHARED:
            continue
        member = get_membership(db, ws.id, user.id)
        if user.is_admin and not member:
            workspace_ids.append(int(ws.id))
        elif shared_member_has_workspace_access(db, user, int(ws.id), member=member):
            workspace_ids.append(int(ws.id))
    if not workspace_ids:
        return select(FileModel.id).where(false())
    subqs = [readable_file_ids_subquery(db, user, ws_id) for ws_id in workspace_ids]
    if len(subqs) == 1:
        return subqs[0]
    return union_all(*subqs)


def accessible_file_ids_all_member_workspaces(db: Session, user: User) -> set[int]:
    _require_rbac_enabled(db)
    ensure_personal_workspace(db, user)
    shared_on = is_shared_workspaces_enabled(db)
    rows = list_user_workspaces(db, user.id)
    if not shared_on:
        rows = [(ws, role) for ws, role in rows if ws.kind != WORKSPACE_KIND_SHARED]
    allowed: set[int] = set()
    for ws, _role in rows:
        member = get_membership(db, ws.id, user.id)
        if user.is_admin and not member:
            member = WorkspaceMember(workspace_id=ws.id, user_id=user.id, role=ROLE_ADMIN)
        if not shared_member_has_workspace_access(db, user, ws.id, member=member):
            continue
        allowed |= accessible_file_ids(db, user, ws.id, member=member)
    return allowed
