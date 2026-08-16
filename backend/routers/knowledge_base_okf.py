# Copyright (c) 2026 徐泽宇
"""OKF bundle import/export/validate routes."""

from __future__ import annotations

import shutil
import tempfile
from pathlib import Path

from fastapi import APIRouter, Depends, File, Form, HTTPException, Query, UploadFile, status
from fastapi.responses import Response
from sqlalchemy.orm import Session

from database import get_db
from middleware.auth import get_current_user
from models.user import User
from models.workspace import ROLE_CONTRIBUTOR, ROLE_CURATOR, Workspace
from schemas.okf import OkfImportResponse, OkfValidateResponse
from services.okf.errors import OkfError, OkfLimitError, OkfParseError, OkfSecurityError
from services.okf.export_service import export_okf_bundle_bytes
from services.okf.import_service import OkfImportReport, import_okf_bundle
from services.okf.paths import find_bundle_root, safe_extract_zip
from services.okf.validate import validate_bundle_root
from services.workspace_access_service import require_workspace_member, resolve_workspace_id

router = APIRouter()


def _read_upload(upload: UploadFile) -> bytes:
    data = upload.file.read()
    if not data:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="空 zip 文件")
    return data


@router.post("/okf/validate", response_model=OkfValidateResponse)
async def post_okf_validate(
    bundle: UploadFile = File(...),
    workspace_id: int | None = Form(None),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    ws_id = resolve_workspace_id(db, current_user, workspace_id)
    require_workspace_member(db, current_user, ws_id, minimum=ROLE_CONTRIBUTOR)
    data = _read_upload(bundle)
    tmp = Path(tempfile.mkdtemp(prefix="okf-validate-"))
    try:
        safe_extract_zip(data, tmp)
        root = find_bundle_root(tmp)
        result = validate_bundle_root(root)
        return OkfValidateResponse(
            conformant=result.conformant,
            errors=result.errors,
            warnings=result.warnings,
            concept_count=result.concept_count,
        )
    except OkfSecurityError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


@router.post("/okf/import", response_model=OkfImportResponse)
async def post_okf_import(
    bundle: UploadFile = File(...),
    workspace_id: int | None = Form(None),
    folder_id: int | None = Form(None),
    dry_run: bool = Form(False),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    ws_id = resolve_workspace_id(db, current_user, workspace_id)
    require_workspace_member(db, current_user, ws_id, minimum=ROLE_CURATOR)
    data = _read_upload(bundle)
    try:
        report = import_okf_bundle(
            db,
            current_user,
            data,
            workspace_id=ws_id,
            folder_id=folder_id,
            dry_run=dry_run,
        )
    except OkfLimitError as exc:
        raise HTTPException(status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE, detail=str(exc)) from exc
    except (OkfParseError, OkfSecurityError) as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc
    except OkfError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc
    return _report_to_response(report)


@router.get("/okf/export")
def get_okf_export(
    workspace_id: int | None = Query(None),
    folder_id: int | None = Query(None),
    include_sources: bool = Query(False),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    ws_id = resolve_workspace_id(db, current_user, workspace_id)
    require_workspace_member(db, current_user, ws_id, minimum=ROLE_CURATOR)
    ws = db.query(Workspace).filter(Workspace.id == ws_id).first()
    slug = (ws.slug if ws and getattr(ws, "slug", None) else None) or f"ws-{ws_id}"
    payload, filename = export_okf_bundle_bytes(
        db,
        current_user,
        workspace_id=ws_id,
        folder_id=folder_id,
        include_sources=include_sources,
        workspace_slug=slug,
    )
    return Response(
        content=payload,
        media_type="application/zip",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


def _report_to_response(report: OkfImportReport) -> OkfImportResponse:
    return OkfImportResponse(
        concepts_created=report.concepts_created,
        concepts_updated=report.concepts_updated,
        index_pages=report.index_pages,
        log_pages=report.log_pages,
        log_entries_imported=report.log_entries_imported,
        warnings=report.warnings,
        folder_id=report.folder_id,
        batches_committed=report.batches_committed,
        dry_run=report.dry_run,
    )
