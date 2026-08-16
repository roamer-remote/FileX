# Copyright (c) 2026 徐泽宇
"""空间内资源授权与可访问 file_id（ACL-aware 列表/检索）。

Authors:
    徐泽宇

Copyright:
    © 2026 徐泽宇
"""

from __future__ import annotations

from sqlalchemy import false, select
from sqlalchemy.orm import Session

from models.file import File as FileModel
from models.folder import Folder as FolderModel
from models.resource_grant import PERM_EDIT, RESOURCE_FILE, RESOURCE_FOLDER, ResourceGrant
from models.user import User
from models.workspace import WORKSPACE_KIND_SHARED, Workspace, WorkspaceMember
from services.system_setting_service import (
    is_enterprise_rbac_cutover,
    is_enterprise_rbac_enabled,
    is_shared_workspaces_enabled,
)
from services.workspace_access_service import (
    ROLE_ADMIN,
    ROLE_VIEWER,
    get_membership,
    role_at_least,
    uses_enterprise_rbac_for_workspace,
)
from services.file_id_sets import all_file_ids_in_workspace
from services.folder_tree_service import collect_descendant_folder_ids
from services.workspace_service import ensure_personal_workspace, list_user_workspaces


class LegacyGrantDeprecatedError(ValueError):
    """enterprise_rbac_enabled 时对外 resource_grants 写入已弃用。"""


def _all_file_ids_in_workspace(db: Session, workspace_id: int) -> set[int]:
    return all_file_ids_in_workspace(db, workspace_id)


def _shared_workspace_access_blocked(db: Session, workspace_id: int) -> bool:
    """共享知识空间功能关闭时，共享库内资源对用户侧不可访问。"""
    if is_shared_workspaces_enabled(db):
        return False
    ws = db.query(Workspace).filter(Workspace.id == workspace_id).first()
    return ws is not None and ws.kind == WORKSPACE_KIND_SHARED



def accessible_file_ids(
    db: Session,
    user: User,
    workspace_id: int,
    *,
    member: WorkspaceMember | None = None,
) -> set[int]:
    if is_enterprise_rbac_enabled(db):
        from services import permission_service as ps

        if _shared_workspace_access_blocked(db, workspace_id):
            return set()
        return ps.accessible_file_ids(db, user, workspace_id, member=member)

    if user.is_admin:
        return _all_file_ids_in_workspace(db, workspace_id)
    if _shared_workspace_access_blocked(db, workspace_id):
        return set()
    member = member or get_membership(db, workspace_id, user.id)
    if not member or not role_at_least(member.role, ROLE_VIEWER):
        return set()
    allowed = _all_file_ids_in_workspace(db, workspace_id)
    grants = (
        db.query(ResourceGrant)
        .filter(
            ResourceGrant.workspace_id == workspace_id,
            ResourceGrant.grantee_user_id == user.id,
        )
        .all()
    )
    for g in grants:
        if g.resource_type == RESOURCE_FILE:
            allowed.add(int(g.resource_id))
        elif g.resource_type == RESOURCE_FOLDER:
            folder_ids = {int(g.resource_id)}
            folder_ids.update(
                collect_descendant_folder_ids(db, int(g.resource_id), workspace_id)
            )
            rows = (
                db.query(FileModel.id)
                .filter(FileModel.workspace_id == workspace_id, FileModel.folder_id.in_(folder_ids))
                .all()
            )
            allowed.update(int(r[0]) for r in rows)
    return allowed


def _workspace_read_blocked_or_denied(
    db: Session,
    user: User,
    workspace_id: int,
    *,
    member: WorkspaceMember | None = None,
) -> bool:
    if user.is_admin:
        return False
    if _shared_workspace_access_blocked(db, workspace_id):
        return True
    member = member or get_membership(db, workspace_id, user.id)
    return not member or not role_at_least(member.role, ROLE_VIEWER)


def readable_file_ids_subquery(
    db: Session,
    user: User,
    workspace_id: int,
    *,
    member: WorkspaceMember | None = None,
):
    """SQL equivalent of accessible_file_ids for a single workspace."""
    if is_enterprise_rbac_enabled(db):
        from services import permission_service as ps

        if _shared_workspace_access_blocked(db, workspace_id):
            return select(FileModel.id).where(false())
        return ps.readable_file_ids_subquery(db, user, workspace_id, member=member)

    stmt = select(FileModel.id).where(FileModel.workspace_id == workspace_id)
    if _workspace_read_blocked_or_denied(db, user, workspace_id, member=member):
        return stmt.where(false())
    return stmt


def apply_readable_files_filter(
    query,
    db: Session,
    user: User,
    workspace_id: int,
    *,
    member: WorkspaceMember | None = None,
):
    return query.filter(FileModel.id.in_(readable_file_ids_subquery(db, user, workspace_id, member=member)))


def readable_file_ids_all_member_workspaces_subquery(db: Session, user: User):
    if is_enterprise_rbac_enabled(db):
        from services import permission_service as ps

        return ps.readable_file_ids_all_member_workspaces_subquery(db, user)

    ensure_personal_workspace(db, user)
    shared_on = is_shared_workspaces_enabled(db)
    rows = list_user_workspaces(db, user.id)
    workspace_ids: list[int] = []
    for ws, _role in rows:
        if not shared_on and ws.kind == WORKSPACE_KIND_SHARED:
            continue
        member = get_membership(db, ws.id, user.id)
        if user.is_admin and not member:
            member = WorkspaceMember(workspace_id=ws.id, user_id=user.id, role=ROLE_ADMIN)
        if member and role_at_least(member.role, ROLE_VIEWER):
            workspace_ids.append(int(ws.id))
    stmt = select(FileModel.id)
    if not workspace_ids:
        return stmt.where(false())
    return stmt.where(FileModel.workspace_id.in_(workspace_ids))


def cross_workspace_kb_search_enabled(db: Session, user: User) -> bool:
    """共享空间功能开启且用户至少可访问一个共享库时，向量检索跨全部可访问空间。"""
    if not is_shared_workspaces_enabled(db):
        return False
    rows = list_user_workspaces(db, user.id)
    return any(ws.kind == WORKSPACE_KIND_SHARED for ws, _ in rows)


def accessible_file_ids_all_member_workspaces(db: Session, user: User) -> set[int]:
    """合并用户在各成员空间内可访问的文件 id（含 ACL 授权）。"""
    if is_enterprise_rbac_enabled(db):
        from services import permission_service as ps

        return ps.accessible_file_ids_all_member_workspaces(db, user)

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
        if not member or not role_at_least(member.role, ROLE_VIEWER):
            continue
        allowed |= accessible_file_ids(db, user, ws.id, member=member)
    return allowed


def create_grant(
    db: Session,
    *,
    workspace_id: int,
    resource_type: str,
    resource_id: int,
    grantee_user_id: int,
    permission: str,
    created_by_user_id: int,
    _internal_dual_write: bool = False,
) -> ResourceGrant:
    if is_enterprise_rbac_cutover(db):
        raise LegacyGrantDeprecatedError(
            "enterprise_rbac_cutover 后 resource_grants 写入已永久移除"
        )
    if uses_enterprise_rbac_for_workspace(db, workspace_id) and not _internal_dual_write:
        raise LegacyGrantDeprecatedError(
            "enterprise_rbac_enabled 时共享空间 resource_grants 对外写入已弃用，请使用目录 ACL API"
        )

    if resource_type == RESOURCE_FILE:
        if not db.query(FileModel.id).filter(
            FileModel.id == resource_id, FileModel.workspace_id == workspace_id
        ).first():
            raise ValueError("资料不存在")
    elif resource_type == RESOURCE_FOLDER:
        if not db.query(FolderModel.id).filter(
            FolderModel.id == resource_id, FolderModel.workspace_id == workspace_id
        ).first():
            raise ValueError("文件夹不存在")
    else:
        raise ValueError("resource_type 无效")
    existing = (
        db.query(ResourceGrant)
        .filter(
            ResourceGrant.workspace_id == workspace_id,
            ResourceGrant.resource_type == resource_type,
            ResourceGrant.resource_id == resource_id,
            ResourceGrant.grantee_user_id == grantee_user_id,
        )
        .first()
    )
    if existing:
        existing.permission = permission
        db.flush()
        return existing
    g = ResourceGrant(
        workspace_id=workspace_id,
        resource_type=resource_type,
        resource_id=resource_id,
        grantee_user_id=grantee_user_id,
        permission=permission,
        created_by_user_id=created_by_user_id,
    )
    db.add(g)
    db.flush()
    return g

def user_can_read_file(db: Session, user: User, file: FileModel) -> bool:
    """文件所有者可读；共享/个人空间成员按 ACL 可读空间内文件。"""
    if is_enterprise_rbac_enabled(db):
        from services import permission_service as ps

        ws_id = file.workspace_id
        if ws_id and _shared_workspace_access_blocked(db, ws_id):
            return False
        return ps.user_can_read_file(db, user, file)

    if user.is_admin:
        return True
    ws_id = file.workspace_id
    if ws_id and _shared_workspace_access_blocked(db, ws_id):
        return False
    if file.user_id == user.id:
        return True
    if not ws_id:
        return False
    member = get_membership(db, ws_id, user.id)
    allowed = accessible_file_ids(db, user, ws_id, member=member)
    return file.id in allowed


def get_readable_file(db: Session, user: User, file_id: int) -> FileModel | None:
    f = db.query(FileModel).filter(FileModel.id == file_id).first()
    if not f or not user_can_read_file(db, user, f):
        return None
    return f
