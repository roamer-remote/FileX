# Copyright (c) 2026 徐泽宇
"""059 P3 T-25：S2 dual-write — legacy-mappable folder_acl 镜像 resource_grants。"""

from __future__ import annotations

from sqlalchemy.orm import Session

from models.enterprise_rbac import PERM_READ, PERM_WRITE, SUBJECT_USER
from models.resource_grant import PERM_EDIT, PERM_VIEW, RESOURCE_FOLDER
from services.acl_service import create_grant
from services.system_setting_service import (
    get_enterprise_rbac_write_mode,
    is_enterprise_rbac_enabled,
)

ACL_TO_LEGACY_GRANT = {
    PERM_READ: PERM_VIEW,
    PERM_WRITE: PERM_EDIT,
}


def is_s2_dual_write_active(db: Session) -> bool:
    return is_enterprise_rbac_enabled(db) and get_enterprise_rbac_write_mode(db) == "dual"


def is_s3_new_only_active(db: Session) -> bool:
    return is_enterprise_rbac_enabled(db) and get_enterprise_rbac_write_mode(db) == "new_only"


def is_legacy_mappable_folder_acl(
    *,
    folder_id: int | None,
    subject_type: str,
    permission: str,
) -> bool:
    return (
        subject_type == SUBJECT_USER
        and folder_id is not None
        and permission in ACL_TO_LEGACY_GRANT
    )


def mirror_folder_acl_to_legacy_grant(
    db: Session,
    *,
    workspace_id: int,
    folder_id: int,
    subject_type: str,
    subject_id: int,
    permission: str,
    admin_user_id: int,
) -> None:
    if not is_s2_dual_write_active(db):
        return
    if not is_legacy_mappable_folder_acl(
        folder_id=folder_id,
        subject_type=subject_type,
        permission=permission,
    ):
        return
    legacy_perm = ACL_TO_LEGACY_GRANT[permission]
    # 忠实同步（含降级），与迁移期 max 合并语义不同。
    create_grant(
        db,
        workspace_id=workspace_id,
        resource_type=RESOURCE_FOLDER,
        resource_id=folder_id,
        grantee_user_id=subject_id,
        permission=legacy_perm,
        created_by_user_id=admin_user_id,
        _internal_dual_write=True,
    )


def folder_acl_entry_needs_rollback_warning(
    *,
    folder_id: int | None,
    subject_type: str,
    permission: str,
) -> bool:
    return not is_legacy_mappable_folder_acl(
        folder_id=folder_id,
        subject_type=subject_type,
        permission=permission,
    )
