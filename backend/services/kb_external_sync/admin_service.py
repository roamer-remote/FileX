# Copyright (c) 2026 徐泽宇
"""Admin helpers for external sync sources (049 T-7)."""

from __future__ import annotations

from fastapi import HTTPException, status
from sqlalchemy.orm import Session

from models.kb_enums import ExternalSyncDeletePolicy
from models.kb_external_sync import KbExternalSyncSource
from models.user import User
from models.workspace import WORKSPACE_KIND_SHARED, Workspace
from services.sync_secret_service import (
    SyncSecretNotConfiguredError,
    encrypt_sync_secret,
    require_sync_secret_configured,
    sync_secret_preview,
)
from services.system_setting_service import is_shared_workspaces_enabled
from services.workspace_access_service import ROLE_CURATOR, get_membership, role_at_least
from services.workspace_service import ensure_personal_workspace, list_user_workspaces
from utils.timezone import to_beijing_time


def list_manageable_workspace_options(db: Session, admin: User) -> list[dict]:
    ensure_personal_workspace(db, admin)
    shared_on = is_shared_workspaces_enabled(db)
    rows = list_user_workspaces(db, admin.id)
    out: list[dict] = []
    for ws, role in rows:
        if ws.kind == WORKSPACE_KIND_SHARED:
            if not shared_on:
                continue
            if not role_at_least(role, ROLE_CURATOR):
                continue
        out.append({"id": ws.id, "name": ws.name, "kind": ws.kind})
    return out


def require_manageable_workspace(db: Session, admin: User, workspace_id: int) -> Workspace:
    allowed = {item["id"] for item in list_manageable_workspace_options(db, admin)}
    if workspace_id not in allowed:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="无权在该知识空间配置外部同步")
    ws = db.get(Workspace, workspace_id)
    if ws is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="知识空间不存在")
    if ws.kind == WORKSPACE_KIND_SHARED and not is_shared_workspaces_enabled(db):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="共享知识空间功能未开启")
    return ws


def validate_delete_policy(value: str) -> str:
    policy = (value or "").strip()
    if policy != ExternalSyncDeletePolicy.keep_file.value:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="delete_policy 仅支持 keep_file")
    return policy


def require_sync_secret_or_400() -> None:
    try:
        require_sync_secret_configured()
    except SyncSecretNotConfiguredError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc


def encrypt_source_secret(plaintext: str) -> bytes:
    require_sync_secret_or_400()
    return encrypt_sync_secret(plaintext)


def source_to_response(source: KbExternalSyncSource, *, preview_plain: str | None = None) -> dict:
    preview = sync_secret_preview(preview_plain) if preview_plain else "****"
    return {
        "id": source.id,
        "workspace_id": source.workspace_id,
        "user_id": source.user_id,
        "provider": source.provider,
        "is_active": bool(source.is_active),
        "delete_policy": source.delete_policy,
        "config_public_json": source.config_public_json or {},
        "secret_preview": preview,
        "last_sync_at": to_beijing_time(source.last_sync_at).isoformat() if source.last_sync_at else None,
        "created_at": to_beijing_time(source.created_at).isoformat() if source.created_at else None,
        "updated_at": to_beijing_time(source.updated_at).isoformat() if source.updated_at else None,
    }


def validate_shared_source_membership(db: Session, admin: User, workspace_id: int) -> None:
    ws = db.get(Workspace, workspace_id)
    if ws and ws.kind == WORKSPACE_KIND_SHARED:
        member = get_membership(db, workspace_id, admin.id)
        if not member or not role_at_least(member.role, ROLE_CURATOR):
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="须为共享空间 curator 及以上成员")
