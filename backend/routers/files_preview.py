# Copyright (c) 2026 徐泽宇
"""files_preview HTTP 路由模块。

Authors:
    徐泽宇
"""

import logging
import os

from fastapi import APIRouter, Depends, HTTPException, Query, status
from fastapi.responses import FileResponse
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from config import EXTRACT_ASSET_SIGN_MAX_KEYS
from database import get_db
from middleware.auth import get_current_user, get_file_stream_user
from models.file import File as FileModel
from models.user import User
from services.extract.content_list_persist import extract_assets_dir_for_file
from services.extract_asset_signing import (
    remember_extract_assets_dir,
    resolve_signed_extract_asset_path,
    sign_extract_asset_urls,
    verify_signed_extract_asset_token,
)
from services.file_service import existing_thumbnail_path, thumbnail_media_type
from services.kb_figure_refs import is_safe_extract_asset_key
from services.acl_service import get_readable_file as acl_get_readable_file
from services.md_paths import resolve_upload_path
from services.office_normalize_service import (
    ensure_office_normalized,
    is_legacy_office_file,
    normalized_file_exists,
    preview_path_and_mime,
)
from services.office_preview_pdf_service import should_preview_as_pdf

logger = logging.getLogger(__name__)

router = APIRouter()


class ExtractAssetSignRequest(BaseModel):
    asset_keys: list[str] = Field(default_factory=list)


class SignedExtractAssetItem(BaseModel):
    asset_key: str
    url: str
    expires_at: int


class ExtractAssetSignResponse(BaseModel):
    items: list[SignedExtractAssetItem]
    expires_at: int


def _get_file_for_stream(db: Session, file_id: int, user: User) -> FileModel | None:
    return acl_get_readable_file(db, user, file_id)


def _resolve_disk_path(path: str | None) -> str | None:
    return resolve_upload_path(path) if path else None


@router.get("/signed-extract-assets/{signed_token}")
def download_signed_extract_asset(signed_token: str):
    """Web 预览专用：验签后读盘，无 DB / ACL（105）。"""
    claims = verify_signed_extract_asset_token(signed_token)
    if not claims:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="无效或已过期的签名")
    abs_path = resolve_signed_extract_asset_path(claims["file_id"], claims["asset_key"])
    if not abs_path or not os.path.isfile(abs_path):
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="资产不存在")
    media_type = thumbnail_media_type(abs_path)
    return FileResponse(
        abs_path,
        media_type=media_type,
        filename=os.path.basename(abs_path),
        headers={
            "Content-Disposition": "inline",
            "X-File-Id": str(claims["file_id"]),
            "Cache-Control": "private, max-age=300",
        },
    )


@router.post("/{file_id}/extract-assets/sign", response_model=ExtractAssetSignResponse)
def sign_extract_assets(
    file_id: int,
    body: ExtractAssetSignRequest,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    raw_keys = [str(k).strip() for k in body.asset_keys if str(k).strip()]
    if not raw_keys:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="asset_keys 不能为空")
    invalid_keys = [k for k in raw_keys if not is_safe_extract_asset_key(k)]
    if invalid_keys:
        preview = ", ".join(invalid_keys[:5])
        suffix = "…" if len(invalid_keys) > 5 else ""
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"非法 asset_key: {preview}{suffix}",
        )
    if len(raw_keys) > EXTRACT_ASSET_SIGN_MAX_KEYS:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"单次最多签发 {EXTRACT_ASSET_SIGN_MAX_KEYS} 个 asset_key",
        )
    seen: set[str] = set()
    asset_keys: list[str] = []
    for key in raw_keys:
        if key in seen:
            continue
        seen.add(key)
        asset_keys.append(key)

    f = _get_file_for_stream(db, file_id, user)
    if not f:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="资料不存在")

    remember_extract_assets_dir(file_id, extract_assets_dir_for_file(f))
    items, expires_at = sign_extract_asset_urls(file_id, asset_keys)
    return ExtractAssetSignResponse(
        items=[SignedExtractAssetItem(**item) for item in items],
        expires_at=expires_at,
    )


@router.get("/{file_id}/download")
def download_file(
    file_id: int,
    workspace_id: int | None = Query(None),
    db: Session = Depends(get_db),
    user: User = Depends(get_file_stream_user),
):
    f = _get_file_for_stream(db, file_id, user)
    if not f:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="资料不存在")
    stream_path = _resolve_disk_path(f.file_path)
    if not stream_path or not os.path.isfile(stream_path):
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="资料已不存在")
    filename = f.original_name
    return FileResponse(
        stream_path,
        media_type="application/octet-stream",
        filename=filename,
        headers={"X-File-Id": str(file_id)},
    )


@router.get("/{file_id}/preview")
def preview_file(
    file_id: int,
    workspace_id: int | None = Query(None),
    db: Session = Depends(get_db),
    user: User = Depends(get_file_stream_user),
):
    f = _get_file_for_stream(db, file_id, user)
    if not f:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="资料不存在")
    if not f.mime_type:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="未知资料类型，无法预览")

    if is_legacy_office_file(f) and not should_preview_as_pdf(f) and not normalized_file_exists(f):
        try:
            ensure_office_normalized(f)
            db.commit()
        except Exception as exc:
            logger.warning("preview normalize failed file_id=%s: %s", file_id, exc)
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail="旧版 Office 文档暂无法预览，请稍后重试或下载原件",
            ) from exc

    try:
        stream_path, media_type = preview_path_and_mime(f)
    except Exception as exc:
        logger.warning("preview prepare failed file_id=%s: %s", file_id, exc, exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Office 文档暂无法预览，请稍后重试或下载原件",
        ) from exc
    stream_path = _resolve_disk_path(stream_path) or stream_path
    if not stream_path or not os.path.isfile(stream_path):
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="预览内容不存在")
    if not media_type:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="未知资料类型，无法预览")

    return FileResponse(
        stream_path,
        media_type=media_type,
        headers={
            "Content-Disposition": "inline",
            "X-File-Id": str(file_id),
        },
    )




@router.get("/{file_id}/extract-assets/{asset_key}")
def download_extract_asset(
    file_id: int,
    asset_key: str,
    db: Session = Depends(get_db),
    user: User = Depends(get_file_stream_user),
):
    from services.kb_figure_refs import extract_asset_abs_path_for_key

    f = _get_file_for_stream(db, file_id, user)
    if not f:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="资料不存在")
    abs_path = extract_asset_abs_path_for_key(f, asset_key)
    if not abs_path:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="资产不存在")
    media_type = thumbnail_media_type(abs_path)
    return FileResponse(
        abs_path,
        media_type=media_type,
        filename=os.path.basename(abs_path),
        headers={
            "Content-Disposition": "inline",
            "X-File-Id": str(file_id),
        },
    )

@router.get("/{file_id}/thumbnail")
def file_thumbnail(
    file_id: int,
    db: Session = Depends(get_db),
    user: User = Depends(get_file_stream_user),
):
    f = _get_file_for_stream(db, file_id, user)
    if not f:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="资料不存在")
    file_path = _resolve_disk_path(f.file_path) or f.file_path
    tp = existing_thumbnail_path(file_path)
    if not tp or not os.path.isfile(tp):
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="无缩略图")
    return FileResponse(tp, media_type=thumbnail_media_type(tp))
