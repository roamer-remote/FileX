# Copyright (c) 2026 徐泽宇
"""share_service 业务逻辑模块。

Authors:
    徐泽宇
"""

import hashlib
import secrets
from datetime import timedelta

from sqlalchemy.orm import Session

from models.share_link import ShareLink
from models.file import File
from utils.timezone import naive_db_now


def _hash_password(password: str) -> str:
    salt = secrets.token_hex(16)
    pwd_hash = hashlib.pbkdf2_hmac("sha256", password.encode(), salt.encode(), 100000).hex()
    return f"{salt}${pwd_hash}"


def _verify_password(plain_password: str, hashed_password: str) -> bool:
    try:
        salt, pwd_hash = hashed_password.split("$", 1)
        computed = hashlib.pbkdf2_hmac("sha256", plain_password.encode(), salt.encode(), 100000).hex()
        return secrets.compare_digest(computed, pwd_hash)
    except (ValueError, AttributeError):
        return False


def generate_token() -> str:
    return secrets.token_urlsafe(32)


def create_share_link(
    db: Session,
    file_id: int,
    user_id: int,
    expires_in_hours: int | None = None,
    password: str | None = None,
    max_downloads: int | None = None,
) -> ShareLink:
    file = db.query(File).filter(File.id == file_id).first()
    if not file:
        raise ValueError("资料不存在")
    if file.user_id != user_id:
        raise ValueError("无权分享该资料")

    token = generate_token()
    expires_at = (
        None
        if expires_in_hours is None
        else naive_db_now() + timedelta(hours=expires_in_hours)
    )

    share = ShareLink(
        file_id=file_id,
        token=token,
        password_hash=_hash_password(password) if password else None,
        expires_at=expires_at,
        max_downloads=max_downloads,
        created_by=user_id,
    )
    db.add(share)
    db.commit()
    db.refresh(share)
    return share


def get_share_by_token(db: Session, token: str) -> ShareLink | None:
    share = db.query(ShareLink).filter(ShareLink.token == token).first()
    if not share:
        return None
    if share.expires_at is not None and share.expires_at < naive_db_now():
        return None
    if share.max_downloads and share.download_count >= share.max_downloads:
        return None
    return share


def verify_share_password(share: ShareLink, password: str) -> bool:
    if not share.password_hash:
        return True
    return _verify_password(password, share.password_hash)


SHARE_VERIFY_COOKIE = "filex_share_verified"
SHARE_VERIFY_MAX_AGE_SEC = 900


def share_verify_cookie_value(token: str) -> str:
    from config import SECRET_KEY

    return hashlib.sha256(f"{SECRET_KEY}:{token}".encode()).hexdigest()[:32]


def is_share_download_verified(token: str, cookie_value: str | None) -> bool:
    if not cookie_value:
        return False
    expected = share_verify_cookie_value(token)
    return secrets.compare_digest(cookie_value, expected)


def set_share_download_cookie(response, token: str) -> None:
    response.set_cookie(
        key=SHARE_VERIFY_COOKIE,
        value=share_verify_cookie_value(token),
        max_age=SHARE_VERIFY_MAX_AGE_SEC,
        httponly=True,
        samesite="lax",
        path=f"/api/share/{token}",
    )


def increment_download(db: Session, share: ShareLink):
    share.download_count += 1
    db.commit()
