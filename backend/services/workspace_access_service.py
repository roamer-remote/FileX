# Copyright (c) 2026 徐泽宇
"""空间成员角色与资源访问判定。

Authors:
    徐泽宇

Copyright:
    © 2026 徐泽宇
"""

from __future__ import annotations

from fastapi import HTTPException, status
from sqlalchemy.orm import Session

from constants.workspace_backup_errors import (
    WORKSPACE_BACKUP_NOT_OWNER,
    WORKSPACE_BACKUP_SHARED_NOT_SUPPORTED,
)
from models.enterprise_rbac import PERM_MANAGE, PERM_WRITE
from models.file import File as FileModel
from models.folder import Folder as FolderModel
from models.user import User
from models.workspace import (
    ROLE_ADMIN,
    ROLE_CONTRIBUTOR,
    ROLE_CURATOR,
    ROLE_VIEWER,
    WORKSPACE_KIND_PERSONAL,
    WORKSPACE_KIND_SHARED,
    Workspace,
    WorkspaceMember,
)
from services.system_setting_service import is_enterprise_rbac_enabled, is_shared_workspaces_enabled
from services.workspace_service import ensure_personal_workspace

_ROLE_RANK = {
    ROLE_VIEWER: 1,
    "auditor": 1,
    ROLE_CONTRIBUTOR: 2,
    ROLE_CURATOR: 3,
    ROLE_ADMIN: 4,
}


def get_membership(db: Session, workspace_id: int, user_id: int) -> WorkspaceMember | None:
    return (
        db.query(WorkspaceMember)
        .filter(WorkspaceMember.workspace_id == workspace_id, WorkspaceMember.user_id == user_id)
        .first()
    )


def role_at_least(role: str, minimum: str) -> bool:
    return _ROLE_RANK.get(role, 0) >= _ROLE_RANK.get(minimum, 99)


def uses_enterprise_rbac_for_workspace(db: Session, workspace_id: int) -> bool:
    if not is_enterprise_rbac_enabled(db):
        return False
    ws = db.query(Workspace).filter(Workspace.id == workspace_id).first()
    return ws is not None and ws.kind == WORKSPACE_KIND_SHARED


def resolve_workspace_id(db: Session, user: User, workspace_id: int | None) -> int:
    if workspace_id is None:
        return ensure_personal_workspace(db, user).id
    ws = db.query(Workspace).filter(Workspace.id == workspace_id).first()
    if not ws:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="知识空间不存在")
    if ws.kind == WORKSPACE_KIND_SHARED and not is_shared_workspaces_enabled(db):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="共享知识空间功能未开启")
    require_workspace_member(db, user, workspace_id, minimum=ROLE_VIEWER)
    return workspace_id


def require_workspace_member(
    db: Session,
    user: User,
    workspace_id: int,
    *,
    minimum: str = ROLE_VIEWER,
) -> WorkspaceMember:
    if user.is_admin:
        ws = db.query(Workspace).filter(Workspace.id == workspace_id).first()
        if not ws:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="知识空间不存在")
        return WorkspaceMember(workspace_id=workspace_id, user_id=user.id, role=ROLE_ADMIN)
    member = get_membership(db, workspace_id, user.id)
    if not member or not role_at_least(member.role, minimum):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="无权访问该知识空间")
    return member


def can_write_file(db: Session, user: User, member: WorkspaceMember, file: FileModel) -> bool:
    if user.is_admin:
        return True
    ws_id = file.workspace_id
    if ws_id and uses_enterprise_rbac_for_workspace(db, ws_id):
        from services.permission_service import effective_file_permission, permission_at_least

        return permission_at_least(effective_file_permission(db, user, file), PERM_WRITE)
    if role_at_least(member.role, ROLE_CURATOR):
        return True
    if role_at_least(member.role, ROLE_CONTRIBUTOR):
        return file.user_id == user.id
    return False


def can_manage_folder(
    db: Session,
    user: User,
    workspace_id: int,
    folder_id: int | None,
) -> bool:
    if user.is_admin:
        return True
    if uses_enterprise_rbac_for_workspace(db, workspace_id):
        from services.permission_service import effective_folder_permission, permission_at_least

        return permission_at_least(
            effective_folder_permission(db, user, workspace_id, folder_id),
            PERM_MANAGE,
        )
    return False


def can_manage_folders(
    db: Session,
    user: User,
    member: WorkspaceMember,
    workspace_id: int,
    *,
    folder_id: int | None = None,
) -> bool:
    if user.is_admin:
        return True
    if uses_enterprise_rbac_for_workspace(db, workspace_id):
        return can_manage_folder(db, user, workspace_id, folder_id)
    return role_at_least(member.role, ROLE_CURATOR)


def can_manage_members(db: Session, user: User, workspace_id: int) -> bool:
    if user.is_admin:
        return True
    if uses_enterprise_rbac_for_workspace(db, workspace_id):
        from services.permission_service import effective_folder_permission, permission_at_least

        return permission_at_least(
            effective_folder_permission(db, user, workspace_id, None),
            PERM_MANAGE,
        )
    member = get_membership(db, workspace_id, user.id)
    return member is not None and role_at_least(member.role, ROLE_ADMIN)


def assert_can_upload_to_folder(
    db: Session,
    user: User,
    workspace_id: int,
    folder_id: int | None,
) -> None:
    require_workspace_member(db, user, workspace_id)
    if not uses_enterprise_rbac_for_workspace(db, workspace_id):
        require_workspace_member(db, user, workspace_id, minimum=ROLE_CONTRIBUTOR)
        return
    from services.permission_service import effective_folder_permission, permission_at_least

    if not permission_at_least(
        effective_folder_permission(db, user, workspace_id, folder_id),
        PERM_WRITE,
    ):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="无权上传到该目录")


def can_upload_to_folder(
    db: Session,
    user: User,
    workspace_id: int,
    folder_id: int | None,
) -> bool:
    try:
        assert_can_upload_to_folder(db, user, workspace_id, folder_id)
        return True
    except HTTPException:
        return False


def file_action_capabilities(
    db: Session,
    user: User,
    file: FileModel,
    *,
    member: WorkspaceMember | None = None,
) -> tuple[bool, bool]:
    """返回 (can_write, can_manage)，供列表/详情 API 与前端操作门控。"""
    if user.is_admin:
        return True, True
    ws_id = file.workspace_id
    if not ws_id:
        owns = file.user_id == user.id
        return owns, owns
    if member is None:
        member = get_membership(db, ws_id, user.id)
    if uses_enterprise_rbac_for_workspace(db, ws_id):
        from services.permission_service import effective_file_permission, permission_at_least

        eff = effective_file_permission(db, user, file)
        return (
            permission_at_least(eff, PERM_WRITE),
            permission_at_least(eff, PERM_MANAGE),
        )
    can_write = can_write_file(db, user, member, file) if member else False
    can_manage = file.user_id == user.id
    return can_write, can_manage


def batch_file_action_capabilities(
    db: Session,
    user: User,
    files: list[FileModel],
    *,
    workspace_id: int,
    member: WorkspaceMember,
) -> dict[int, tuple[bool, bool]]:
    if not files:
        return {}
    if user.is_admin:
        return {f.id: (True, True) for f in files}
    rbac_on = uses_enterprise_rbac_for_workspace(db, workspace_id)
    out: dict[int, tuple[bool, bool]] = {}
    if rbac_on:
        from services.permission_service import effective_file_permission, permission_at_least

        for f in files:
            eff = effective_file_permission(db, user, f)
            out[f.id] = (
                permission_at_least(eff, PERM_WRITE),
                permission_at_least(eff, PERM_MANAGE),
            )
    else:
        can_write_all = role_at_least(member.role, ROLE_CURATOR)
        can_write_owned = role_at_least(member.role, ROLE_CONTRIBUTOR)
        for f in files:
            out[f.id] = (
                can_write_all or (can_write_owned and f.user_id == user.id),
                f.user_id == user.id,
            )
    return out


def get_file_in_workspace(db: Session, file_id: int, workspace_id: int) -> FileModel | None:
    return (
        db.query(FileModel)
        .filter(FileModel.id == file_id, FileModel.workspace_id == workspace_id)
        .first()
    )


def get_folder_in_workspace(db: Session, folder_id: int, workspace_id: int) -> FolderModel | None:
    return (
        db.query(FolderModel)
        .filter(FolderModel.id == folder_id, FolderModel.workspace_id == workspace_id)
        .first()
    )


def require_personal_workspace_owner(db: Session, user: User, workspace_id: int) -> Workspace:
    """087：个人空间备份仅 owner 可用；禁止 admin 代下他人个人空间。"""
    ws = db.query(Workspace).filter(Workspace.id == workspace_id).first()
    if not ws:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="知识空间不存在")
    if ws.kind != WORKSPACE_KIND_PERSONAL:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=WORKSPACE_BACKUP_SHARED_NOT_SUPPORTED,
        )
    if ws.owner_user_id != user.id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=WORKSPACE_BACKUP_NOT_OWNER,
        )
    return ws
