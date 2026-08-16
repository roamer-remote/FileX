# Copyright (c) 2026 徐泽宇
"""059 P3 T-26：S3 new_only 切档前生产就绪校验。"""

from __future__ import annotations

from sqlalchemy.orm import Session

from models.resource_grant import RESOURCE_FILE, RESOURCE_FOLDER, ResourceGrant
from models.workspace import WORKSPACE_KIND_SHARED, Workspace, WorkspaceMember
from services.rbac_dual_write_service import is_s2_dual_write_active
from services.rbac_migration_service import count_workspace_user_roles
from services.system_setting_service import (
    get_enterprise_rbac_write_mode,
    is_enterprise_rbac_enabled,
    is_shared_workspaces_enabled,
)


def detect_rbac_phase(db: Session) -> str:
    if not is_enterprise_rbac_enabled(db):
        return "S1"
    if get_enterprise_rbac_write_mode(db) == "new_only":
        return "S3"
    return "S2"


def validate_s3_readiness(
    db: Session,
    *,
    workspace_id: int | None = None,
) -> dict:
    """校验是否可安全将 write_mode 切至 new_only（或确认已处于 S3）。"""
    blockers: list[dict] = []
    warnings: list[dict] = []
    workspace_reports: list[dict] = []

    if not is_shared_workspaces_enabled(db):
        blockers.append(
            {
                "code": "shared_workspaces_disabled",
                "message": "shared_workspaces_enabled 须为 true",
            }
        )
    if not is_enterprise_rbac_enabled(db):
        blockers.append(
            {
                "code": "rbac_disabled",
                "message": "enterprise_rbac_enabled 须为 true（先完成 S2 迁移与双写期）",
            }
        )

    phase = detect_rbac_phase(db)
    if phase == "S3":
        warnings.append(
            {
                "code": "already_s3",
                "message": "已处于 S3 new_only；本报告为复检",
            }
        )
    elif phase == "S2" and not is_s2_dual_write_active(db):
        warnings.append(
            {
                "code": "unexpected_write_mode",
                "message": f"write_mode={get_enterprise_rbac_write_mode(db)!r} 非预期",
            }
        )

    q = db.query(Workspace).filter(Workspace.kind == WORKSPACE_KIND_SHARED)
    if workspace_id is not None:
        q = q.filter(Workspace.id == workspace_id)
    workspaces = q.order_by(Workspace.id).all()

    members_without_wur = 0
    file_shim_grants = 0

    for ws in workspaces:
        ws_blockers: list[dict] = []
        ws_warnings: list[dict] = []

        members = (
            db.query(WorkspaceMember)
            .filter(WorkspaceMember.workspace_id == ws.id)
            .order_by(WorkspaceMember.user_id)
            .all()
        )
        ws_members_without_wur = 0
        for member in members:
            if count_workspace_user_roles(db, workspace_id=ws.id, user_id=member.user_id) == 0:
                ws_members_without_wur += 1
                members_without_wur += 1

        if ws_members_without_wur:
            entry = {
                "code": "members_without_workspace_user_roles",
                "message": f"{ws_members_without_wur} 名成员无 workspace_user_roles",
                "workspace_id": ws.id,
                "count": ws_members_without_wur,
            }
            ws_blockers.append(entry)
            blockers.append(entry)

        grants = (
            db.query(ResourceGrant)
            .filter(ResourceGrant.workspace_id == ws.id)
            .all()
        )
        ws_folder_grants = 0
        ws_file_shim = 0
        for grant in grants:
            if grant.resource_type == RESOURCE_FOLDER:
                ws_folder_grants += 1
            elif grant.resource_type == RESOURCE_FILE:
                from models.file import File as FileModel

                f = db.query(FileModel).filter(FileModel.id == grant.resource_id).first()
                if f and f.folder_id is None:
                    ws_file_shim += 1
                    file_shim_grants += 1

        if ws_file_shim:
            ws_warnings.append(
                {
                    "code": "file_no_folder_shim",
                    "message": f"{ws_file_shim} 条未分类 file grant 仍保留 shim",
                    "count": ws_file_shim,
                }
            )

        workspace_reports.append(
            {
                "workspace_id": ws.id,
                "workspace_name": ws.name,
                "member_count": len(members),
                "members_without_wur": ws_members_without_wur,
                "resource_grant_folder_count": ws_folder_grants,
                "file_shim_grant_count": ws_file_shim,
                "blockers": ws_blockers,
                "warnings": ws_warnings,
            }
        )

    if file_shim_grants:
        warnings.append(
            {
                "code": "file_shim_grants_total",
                "message": f"共 {file_shim_grants} 条 file shim grant 需人工确认",
                "count": file_shim_grants,
            }
        )

    if phase == "S2":
        warnings.append(
            {
                "code": "s3_no_switch_off_rollback",
                "message": "切至 S3 后不可仅关开关回 S1；须跑 rbac_reverse_to_legacy 或恢复备份",
            }
        )

    ready = len(blockers) == 0 and is_enterprise_rbac_enabled(db) and is_shared_workspaces_enabled(db)

    return {
        "ready_for_new_only": ready,
        "phase": phase,
        "write_mode": get_enterprise_rbac_write_mode(db) if is_enterprise_rbac_enabled(db) else None,
        "blockers": blockers,
        "warnings": warnings,
        "summary": {
            "workspaces_checked": len(workspaces),
            "members_without_wur": members_without_wur,
            "file_shim_grants": file_shim_grants,
        },
        "workspaces": workspace_reports,
    }
