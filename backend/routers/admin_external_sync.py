# Copyright (c) 2026 徐泽宇
"""Admin API: external sync sources (049 T-7)."""

from __future__ import annotations

import logging
import threading
import uuid

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from database import SessionLocal, get_db
from middleware.auth import get_admin_user
from models.kb_external_sync import KbExternalSyncSource
from models.user import User
from schemas.external_sync import (
    ExternalSyncRotateSecretRequest,
    ExternalSyncSourceCreateRequest,
    ExternalSyncSourceResponse,
    ExternalSyncSourceUpdateRequest,
    ExternalSyncSyncNowResponse,
    ExternalSyncTestConnectionResponse,
    ExternalSyncWorkspaceOption,
)
from services.kb_external_sync.admin_service import (
    encrypt_source_secret,
    list_manageable_workspace_options,
    require_manageable_workspace,
    source_to_response,
    validate_delete_policy,
    validate_shared_source_membership,
)
from services.kb_external_sync.notion_client import NotionClientError
from services.kb_external_sync.notion_runner import SourceNotRunnableError, run_notion_sync, test_notion_connection
from services.log_service import log_operation
from services.sync_secret_service import decrypt_sync_secret, redact_sync_secret

logger = logging.getLogger(__name__)

router = APIRouter()



def _notion_db_title(raw: object) -> str | None:
    if not raw:
        return None
    if isinstance(raw, list):
        parts: list[str] = []
        for item in raw:
            if isinstance(item, dict):
                parts.append(str(item.get("plain_text") or ""))
        joined = "".join(parts).strip()
        return joined or None
    return str(raw)

DELETE_POLICY_HINT = "源端删除的页面不会自动删除本站资料，仅停止同步并标记为远端已删"


def _get_source_or_404(db: Session, source_id: int) -> KbExternalSyncSource:
    source = db.get(KbExternalSyncSource, source_id)
    if source is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="同步源不存在")
    return source


def _safe_client_error(exc: Exception, *secrets: str) -> HTTPException:
    msg = redact_sync_secret(str(exc), *secrets)
    code = status.HTTP_502_BAD_GATEWAY
    if isinstance(exc, NotionClientError) and exc.status_code:
        if exc.status_code == 401:
            code = status.HTTP_400_BAD_REQUEST
        elif exc.status_code == 404:
            code = status.HTTP_400_BAD_REQUEST
    return HTTPException(status_code=code, detail=msg)


@router.get("/workspaces", response_model=list[ExternalSyncWorkspaceOption])
def list_workspace_options(
    db: Session = Depends(get_db),
    admin: User = Depends(get_admin_user),
):
    return list_manageable_workspace_options(db, admin)


@router.get("/sources", response_model=list[ExternalSyncSourceResponse])
def list_sources(
    db: Session = Depends(get_db),
    _admin: User = Depends(get_admin_user),
):
    rows = db.query(KbExternalSyncSource).order_by(KbExternalSyncSource.id.desc()).all()
    return [source_to_response(row) for row in rows]


@router.post("/sources", response_model=ExternalSyncSourceResponse, status_code=status.HTTP_201_CREATED)
def create_source(
    body: ExternalSyncSourceCreateRequest,
    db: Session = Depends(get_db),
    admin: User = Depends(get_admin_user),
):
    if body.provider != "notion":
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="MVP 仅支持 notion")
    require_manageable_workspace(db, admin, body.workspace_id)
    validate_shared_source_membership(db, admin, body.workspace_id)
    policy = validate_delete_policy(body.delete_policy)
    ciphertext = encrypt_source_secret(body.secret.strip())
    source = KbExternalSyncSource(
        workspace_id=body.workspace_id,
        user_id=admin.id,
        provider=body.provider,
        is_active=body.is_active,
        delete_policy=policy,
        config_public_json=body.config_public_json or {},
        secret_ciphertext=ciphertext,
    )
    db.add(source)
    db.commit()
    db.refresh(source)
    log_operation(
        db,
        admin.id,
        "创建外部同步源",
        "external_sync_source",
        source.id,
        f"provider={source.provider} workspace_id={source.workspace_id}",
    )
    return source_to_response(source, preview_plain=body.secret.strip())


@router.put("/sources/{source_id}", response_model=ExternalSyncSourceResponse)
def update_source(
    source_id: int,
    body: ExternalSyncSourceUpdateRequest,
    db: Session = Depends(get_db),
    admin: User = Depends(get_admin_user),
):
    source = _get_source_or_404(db, source_id)
    if body.workspace_id is not None:
        require_manageable_workspace(db, admin, body.workspace_id)
        validate_shared_source_membership(db, admin, body.workspace_id)
        source.workspace_id = body.workspace_id
    if body.config_public_json is not None:
        source.config_public_json = body.config_public_json
    if body.delete_policy is not None:
        source.delete_policy = validate_delete_policy(body.delete_policy)
    if body.is_active is not None:
        source.is_active = body.is_active
    db.commit()
    db.refresh(source)
    log_operation(db, admin.id, "更新外部同步源", "external_sync_source", source.id, DELETE_POLICY_HINT)
    return source_to_response(source)


@router.post("/sources/{source_id}/rotate-secret", response_model=ExternalSyncSourceResponse)
def rotate_secret(
    source_id: int,
    body: ExternalSyncRotateSecretRequest,
    db: Session = Depends(get_db),
    admin: User = Depends(get_admin_user),
):
    source = _get_source_or_404(db, source_id)
    plain = body.secret.strip()
    source.secret_ciphertext = encrypt_source_secret(plain)
    db.commit()
    db.refresh(source)
    log_operation(db, admin.id, "轮换外部同步凭据", "external_sync_source", source.id, "secret rotated")
    return source_to_response(source, preview_plain=plain)


@router.post("/sources/{source_id}/test-connection", response_model=ExternalSyncTestConnectionResponse)
def test_connection(
    source_id: int,
    db: Session = Depends(get_db),
    admin: User = Depends(get_admin_user),
):
    source = _get_source_or_404(db, source_id)
    if not source.secret_ciphertext:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="同步源未配置凭据")
    plain = decrypt_sync_secret(source.secret_ciphertext)
    try:
        meta = test_notion_connection(db, source.id)
    except (NotionClientError, ValueError) as exc:
        safe = _safe_client_error(exc, plain)
        log_operation(
            db,
            admin.id,
            "测试外部同步连接",
            "external_sync_source",
            source.id,
            redact_sync_secret(str(exc), plain),
        )
        db.commit()
        raise safe from exc
    log_operation(
        db,
        admin.id,
        "测试外部同步连接",
        "external_sync_source",
        source.id,
        f"database_id={meta.get('database_id')}",
    )
    db.commit()
    return ExternalSyncTestConnectionResponse(
        ok=True,
        database_id=str(meta.get("database_id") or ""),
        title=_notion_db_title(meta.get("title")),
    )


@router.post("/sources/{source_id}/sync-now", response_model=ExternalSyncSyncNowResponse, status_code=status.HTTP_202_ACCEPTED)
def sync_now(
    source_id: int,
    db: Session = Depends(get_db),
    admin: User = Depends(get_admin_user),
):
    source = _get_source_or_404(db, source_id)
    run_id = uuid.uuid4().hex

    def _run() -> None:
        session = SessionLocal()
        try:
            run_notion_sync(session, source_id)
        except Exception:
            logger.exception("external sync run_id=%s source_id=%s failed", run_id, source_id)
        finally:
            session.close()

    threading.Thread(target=_run, name=f"ext-sync-{run_id}", daemon=True).start()
    log_operation(db, admin.id, "触发外部同步", "external_sync_source", source.id, f"run_id={run_id}")
    db.commit()
    return ExternalSyncSyncNowResponse(run_id=run_id)


@router.get("/meta/delete-policy-hint")
def delete_policy_hint():
    return {"hint": DELETE_POLICY_HINT}
