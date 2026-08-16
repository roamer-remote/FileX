# Copyright (c) 2026 徐泽宇
"""auth 中间件模块。

Authors:
    徐泽宇
"""

import hashlib
from datetime import datetime

from fastapi import Depends, HTTPException, Query, status
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from jose import JWTError, jwt
from sqlalchemy.orm import Session

from config import SECRET_KEY, ALGORITHM, API_KEY_PREFIX
from database import get_db
from models.user import User
from models.api_key import ApiKey

security = HTTPBearer()
security_optional = HTTPBearer(auto_error=False)

FILE_STREAM_AUTH_REQUIRED_DETAIL = "下载或预览需要登录凭证或有效的 API Key（fb_ 开头）"

# 有效 fb_ 密钥且密钥上架，但 users.is_active 为假时返回（与「无效密钥」区分）
API_KEY_USER_INACTIVE_DETAIL = "用户账号已经停用！请联系管理员"

# GET /api/external/api-key-status：valid=false 时供智能体转述，勿盲重试
API_KEY_STATUS_HINTS: dict[str, str] = {
    "missing_authorization": (
        "未提供 Bearer。请在智能体宿主配置 FILEX_API_KEY（Hermes：~/.hermes/.env）"
        "与 FILEX_ORIGIN，并确保沙箱/终端可读取环境变量。"
    ),
    "not_api_key": "请使用 fb_ 前缀的 API Key，勿用登录 JWT。",
    "invalid_api_key": "密钥无效或不完整；请在 FileX「API 密钥」reveal 全文后更新配置。",
    "api_key_inactive": "密钥已下架；请在 FileX 上架该密钥或新建密钥。",
    "user_inactive": "所属账号已停用；请联系管理员启用账号。",
    "license_expired": "FileX 授权已过期，请联系管理员更新 License Key",
    "license_invalid": "FileX License Key 无效，请联系管理员更新 License Key",
}


def api_key_status_hint(reason: str | None) -> str | None:
    if not reason:
        return None
    return API_KEY_STATUS_HINTS.get(reason)


def _decode_jwt(token: str) -> dict | None:
    try:
        return jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
    except (JWTError, ValueError):
        return None


def _user_from_jwt(token: str, db: Session) -> User | None:
    """JWT 合法且 pwd_rev 与数据库一致时返回用户；否则返回 None（含密码变更后旧 Token 失效）。"""
    payload = _decode_jwt(token)
    if not payload:
        return None
    sub = payload.get("sub")
    if sub is None:
        return None
    try:
        user_id = int(sub)
    except (TypeError, ValueError):
        return None
    user = db.query(User).filter(User.id == user_id).first()
    if user is None:
        return None
    raw_rev = payload.get("pwd_rev", 0)
    try:
        token_rev = int(raw_rev)
    except (TypeError, ValueError):
        token_rev = 0
    if token_rev != int(user.password_rev or 0):
        return None
    if not user.is_active:
        return None
    return user


def _resolve_api_key_auth(
    key: str, db: Session, *, update_last_used: bool = True,
) -> tuple[User | None, str]:
    """解析 API Key。返回 (user, reason)：reason 为 '' 表示成功；
    'invalid' 表示哈希不匹配或用户行缺失；
    'api_key_inactive' 表示密钥存在但已下架；
    'user_inactive' 表示密钥有效但所属用户已停用。

    仅在 reason 为空（成功）且 update_last_used 为 True 时写入 ApiKey.last_used_at。"""
    key = (key or "").strip()
    if not key.startswith(API_KEY_PREFIX):
        return None, "invalid"
    key_hash = hashlib.sha256(key.encode()).hexdigest()
    api_key = db.query(ApiKey).filter(ApiKey.key_hash == key_hash).first()
    if api_key is None:
        return None, "invalid"
    if not api_key.is_active:
        return None, "api_key_inactive"
    user = db.query(User).filter(User.id == api_key.user_id).first()
    if user is None:
        return None, "invalid"
    if not user.is_active:
        return None, "user_inactive"
    if update_last_used:
        from utils.timezone import beijing_now

        api_key.last_used_at = beijing_now().replace(tzinfo=None)
        db.commit()
    return user, ""


def _get_user_from_api_key(key: str, db: Session) -> User | None:
    """Try to authenticate using an API key (starts with fb_). 可选用户场景：停用账户与无效密钥均返回 None。"""
    user, reason = _resolve_api_key_auth(key, db, update_last_used=True)
    if reason:
        return None
    return user


def resolve_bearer_or_query_token(
    *,
    credentials: HTTPAuthorizationCredentials | None,
    token: str | None,
) -> str | None:
    """Authorization 头优先，其次 ?token=；均无或空白则 None。"""
    if credentials is not None and (credentials.credentials or "").strip():
        return credentials.credentials.strip()
    if token is not None and token.strip():
        return token.strip()
    return None


def get_file_stream_user(
    token: str | None = Query(None, description="JWT 或 fb_ API Key（与 Authorization 二选一）"),
    credentials: HTTPAuthorizationCredentials | None = Depends(security_optional),
    db: Session = Depends(get_db),
) -> User:
    """文件下载/预览/缩略图：必须带有效 JWT 或 API Key，禁止无凭证访问。"""
    raw = resolve_bearer_or_query_token(credentials=credentials, token=token)
    if not raw:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=FILE_STREAM_AUTH_REQUIRED_DETAIL,
        )
    user = user_from_url_query_token(raw, db)
    if user is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="无效的凭证",
        )
    return user


def user_from_url_query_token(token: str, db: Session) -> User | None:
    """与 get_current_user 相同来源：JWT（含 pwd_rev）或 API Key，用于 ?token= 下载/预览。"""
    user = _user_from_jwt(token, db)
    if user is not None:
        return user
    _u, reason = _resolve_api_key_auth(token, db, update_last_used=True)
    if reason == "user_inactive":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=API_KEY_USER_INACTIVE_DETAIL,
        )
    return _u


def get_current_user(
    credentials: HTTPAuthorizationCredentials = Depends(security),
    db: Session = Depends(get_db),
) -> User:
    token = credentials.credentials

    user = _user_from_jwt(token, db)
    if user is not None:
        return user

    _u, reason = _resolve_api_key_auth(token, db, update_last_used=True)
    if reason == "user_inactive":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=API_KEY_USER_INACTIVE_DETAIL,
        )
    if _u is not None:
        return _u

    raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="无效的凭证")


def get_admin_user(current_user: User = Depends(get_current_user)) -> User:
    if not current_user.is_admin:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="需要管理员权限")
    return current_user


def get_api_key_user(
    credentials: HTTPAuthorizationCredentials = Depends(security),
    db: Session = Depends(get_db),
) -> User:
    """只接受 API Key 认证（用于外部 REST API）。"""
    raw = (credentials.credentials or "").strip()
    if not raw.startswith(API_KEY_PREFIX):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="外部 API 仅支持 API Key（须 fb_ 开头），不能使用 Web 登录 JWT",
        )
    user, reason = _resolve_api_key_auth(raw, db, update_last_used=True)
    if reason == "user_inactive":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=API_KEY_USER_INACTIVE_DETAIL,
        )
    if reason == "api_key_inactive":
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="API 密钥已下架，请在网站「API 密钥」页重新上架或创建新密钥",
        )
    if user is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="无效的 API 密钥（请确认使用创建时复制的完整 fb_ 密钥，而非列表中的前缀）",
        )
    return user


def build_api_key_status(credentials: str, db: Session) -> dict:
    """供 GET /api/external/api-key-status：恒为业务层 JSON，不抛 HTTPException。

    返回字段：valid, reason（invalid 时）, username, user_id（按 valid 与 reason 填充）。"""
    from services.license_cache_service import get_cached_status
    from services.license_service import license_http_code

    license_status = get_cached_status(db)
    if not license_status.valid:
        code = license_http_code(license_status.reason)
        reason = "license_invalid" if code == "license_invalid" else "license_expired"
        return {
            "valid": False,
            "reason": reason,
            "hint": api_key_status_hint(reason),
            "username": None,
            "user_id": None,
        }

    credentials = (credentials or "").strip()
    if not credentials.startswith(API_KEY_PREFIX):
        reason = "not_api_key"
        return {
            "valid": False,
            "reason": reason,
            "hint": api_key_status_hint(reason),
            "username": None,
            "user_id": None,
        }
    user, reason = _resolve_api_key_auth(credentials, db, update_last_used=False)
    if reason == "api_key_inactive":
        r = "api_key_inactive"
        return {
            "valid": False,
            "reason": r,
            "hint": api_key_status_hint(r),
            "username": None,
            "user_id": None,
        }
    if reason == "user_inactive":
        key_hash = hashlib.sha256(credentials.encode()).hexdigest()
        api_key = db.query(ApiKey).filter(
            ApiKey.key_hash == key_hash,
            ApiKey.is_active == True,
        ).first()
        owner = (
            db.query(User).filter(User.id == api_key.user_id).first()
            if api_key is not None
            else None
        )
        r = "user_inactive"
        return {
            "valid": False,
            "reason": r,
            "hint": api_key_status_hint(r),
            "username": owner.username if owner else None,
            "user_id": owner.id if owner else None,
        }
    if reason == "invalid" or user is None:
        r = "invalid_api_key"
        return {
            "valid": False,
            "reason": r,
            "hint": api_key_status_hint(r),
            "username": None,
            "user_id": None,
        }
    return {
        "valid": True,
        "reason": None,
        "hint": None,
        "username": user.username,
        "user_id": user.id,
    }


def get_optional_user(
    credentials: HTTPAuthorizationCredentials | None = Depends(
        HTTPBearer(auto_error=False)
    ),
    db: Session = Depends(get_db),
) -> User | None:
    if credentials is None:
        return None
    token = credentials.credentials

    user = _user_from_jwt(token, db)
    if user is not None:
        return user

    return _get_user_from_api_key(token, db)
