# Copyright (c) 2026 徐泽宇
"""api_keys HTTP 路由模块。

Authors:
    徐泽宇
"""

import hashlib
import secrets

from fastapi import APIRouter, Body, Depends, HTTPException, Response, status
from pydantic import BaseModel
from sqlalchemy.orm import Session

from config import API_KEY_PREFIX, API_KEY_BYTES
from database import get_db
from middleware.auth import get_current_user
from models.user import User
from models.api_key import ApiKey
from services.log_service import log_operation
from utils.timezone import to_beijing_time
from utils.api_key_secret import encrypt_api_key_plaintext, decrypt_api_key_plaintext

router = APIRouter()


class ApiKeyCreateResponse(BaseModel):
    """API密钥创建响应 API 路由辅助类型。

        Authors:
            徐泽宇

        Copyright:
            © 2026 徐泽宇

        Since:
            2026-05-02

        Attributes:
            id: ID（int）。
            name: 名称（str）。
            prefix: 前缀（str）。
            plain_text_key: 纯文本文本密钥（str）。
            created_at: 创建时间（str）。
    """
    id: int
    name: str
    prefix: str
    plain_text_key: str
    created_at: str


class ApiKeyItem(BaseModel):
    """API密钥条目 API 路由辅助类型。

        Authors:
            徐泽宇

        Copyright:
            © 2026 徐泽宇

        Since:
            2026-05-06

        Attributes:
            id: ID（int）。
            name: 名称（str）。
            prefix: 前缀（str）。
            created_at: 创建时间（str）。
            last_used_at: lastused时间（str | None）。
            is_active: 是否启用（bool）。
            can_reveal: can揭示（bool）。
    """
    id: int
    name: str
    prefix: str
    created_at: str
    last_used_at: str | None = None
    is_active: bool
    can_reveal: bool

    class Config:
        """Pydantic 模型配置。

            Authors:
                徐泽宇

            Copyright:
                © 2026 徐泽宇

            Since:
                2026-05-02

            Attributes:
                from_attributes: fromattributes常量。
        """
        from_attributes = True


class CreateApiKeyRequest(BaseModel):
    """创建API密钥请求 API 路由辅助类型。

        Authors:
            徐泽宇

        Copyright:
            © 2026 徐泽宇

        Since:
            2026-05-06

        Attributes:
            name: 名称（str）。
    """
    name: str


class ApiKeyPatchRequest(BaseModel):
    """API密钥补丁请求 API 路由辅助类型。

        Authors:
            徐泽宇

        Copyright:
            © 2026 徐泽宇

        Since:
            2026-05-06

        Attributes:
            is_active: 是否启用（bool）。
    """
    is_active: bool


class ApiKeyRevealResponse(BaseModel):
    """API密钥揭示响应 API 路由辅助类型。

        Authors:
            徐泽宇

        Copyright:
            © 2026 徐泽宇

        Since:
            2026-05-07

        Attributes:
            plain_text_key: 纯文本文本密钥（str）。
    """
    plain_text_key: str


class ApiKeyRevealRequest(BaseModel):
    """API密钥揭示请求 API 路由辅助类型。

        Authors:
            徐泽宇

        Copyright:
            © 2026 徐泽宇

        Since:
            2026-05-02

        Attributes:
            preview: 预览（bool）。
    """
    preview: bool = False


@router.post("", response_model=ApiKeyCreateResponse)
def create_api_key(
    body: CreateApiKeyRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Create a new API key; plaintext returned once in response for client to copy (not stored in logs)."""
    plain_key = API_KEY_PREFIX + secrets.token_urlsafe(API_KEY_BYTES)
    key_hash = hashlib.sha256(plain_key.encode()).hexdigest()
    prefix = plain_key[:8]  # varchar(8)
    secret_enc = encrypt_api_key_plaintext(plain_key)

    api_key = ApiKey(
        key_hash=key_hash,
        key_secret_encrypted=secret_enc,
        name=body.name,
        prefix=prefix,
        user_id=current_user.id,
    )
    db.add(api_key)
    db.commit()
    db.refresh(api_key)

    log_operation(db, current_user.id, "创建 API Key", "api_key", api_key.id, f"创建 API Key: {body.name}")

    return ApiKeyCreateResponse(
        id=api_key.id,
        name=api_key.name,
        prefix=api_key.prefix,
        plain_text_key=plain_key,
        created_at=to_beijing_time(api_key.created_at).isoformat() if api_key.created_at else "",
    )


@router.get("", response_model=list[ApiKeyItem])
def list_api_keys(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    keys = (
        db.query(ApiKey)
        .filter(ApiKey.user_id == current_user.id)
        .order_by(ApiKey.created_at.desc())
        .all()
    )
    result = []
    for k in keys:
        is_active = bool(k.is_active) if k.is_active is not None else True
        result.append(
            ApiKeyItem(
                id=k.id,
                name=k.name,
                prefix=k.prefix,
                created_at=to_beijing_time(k.created_at).isoformat() if k.created_at else "",
                last_used_at=to_beijing_time(k.last_used_at).isoformat() if k.last_used_at else None,
                is_active=is_active,
                can_reveal=bool(k.key_secret_encrypted),
            )
        )
    return result


@router.patch("/{key_id}", response_model=ApiKeyItem)
def patch_api_key(
    key_id: int,
    body: ApiKeyPatchRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    key = db.query(ApiKey).filter(ApiKey.id == key_id, ApiKey.user_id == current_user.id).first()
    if not key:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="API Key 不存在")

    key.is_active = body.is_active
    db.commit()
    db.refresh(key)

    state = "上架" if body.is_active else "下架"
    log_operation(db, current_user.id, "更新 API Key", "api_key", key_id, f"{state} API Key: {key.name}")

    is_active = bool(key.is_active) if key.is_active is not None else True
    return ApiKeyItem(
        id=key.id,
        name=key.name,
        prefix=key.prefix,
        created_at=to_beijing_time(key.created_at).isoformat() if key.created_at else "",
        last_used_at=to_beijing_time(key.last_used_at).isoformat() if key.last_used_at else None,
        is_active=is_active,
        can_reveal=bool(key.key_secret_encrypted),
    )


@router.delete("/{key_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_api_key(
    key_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    key = db.query(ApiKey).filter(ApiKey.id == key_id, ApiKey.user_id == current_user.id).first()
    if not key:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="API Key 不存在")

    detail_name = key.name
    db.delete(key)
    db.commit()

    log_operation(db, current_user.id, "删除 API Key", "api_key", key_id, f"删除 API Key: {detail_name}")

    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.post("/{key_id}/reveal", response_model=ApiKeyRevealResponse)
def reveal_api_key(
    key_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
    body: ApiKeyRevealRequest = Body(default_factory=ApiKeyRevealRequest),
):
    key = db.query(ApiKey).filter(ApiKey.id == key_id, ApiKey.user_id == current_user.id).first()
    if not key:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="API Key 不存在")
    if not key.key_secret_encrypted:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="该密钥在加密存储功能上线前创建，无法再次解密。请下架后重新创建密钥",
        )
    try:
        plain = decrypt_api_key_plaintext(key.key_secret_encrypted)
    except ValueError:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="无法解密密钥，请确认 FILEX_SECRET_KEY 未变更，或重新创建密钥",
        )

    if hashlib.sha256(plain.encode()).hexdigest() != key.key_hash:
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="密钥校验不一致")

    preview = bool(body.preview)
    if preview:
        log_operation(db, current_user.id, "预览 API Key", "api_key", key_id, f"Tooltip 预览 API Key: {key.name}")
    else:
        log_operation(db, current_user.id, "复制 API Key", "api_key", key_id, f"解密并复制 API Key: {key.name}")

    return ApiKeyRevealResponse(plain_text_key=plain)
