# Copyright (c) 2026 徐泽宇
"""auth_service 业务逻辑模块。

Authors:
    徐泽宇
"""

import hashlib
import secrets
from datetime import datetime, timedelta

from jose import jwt
from sqlalchemy.orm import Session

from config import SECRET_KEY, ALGORITHM, ACCESS_TOKEN_EXPIRE_MINUTES
from models.user import User
from services.enterprise_rbac_seed import get_unassigned_department_id


def hash_password(password: str) -> str:
    salt = secrets.token_hex(16)
    pwd_hash = hashlib.pbkdf2_hmac("sha256", password.encode(), salt.encode(), 100000).hex()
    return f"{salt}${pwd_hash}"


def verify_password(plain_password: str, hashed_password: str) -> bool:
    try:
        salt, pwd_hash = hashed_password.split("$", 1)
        computed = hashlib.pbkdf2_hmac("sha256", plain_password.encode(), salt.encode(), 100000).hex()
        return secrets.compare_digest(computed, pwd_hash)
    except (ValueError, AttributeError):
        return False


def create_access_token(user_id: int, password_rev: int) -> str:
    expire = datetime.utcnow() + timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES)
    to_encode = {"sub": str(user_id), "exp": expire, "pwd_rev": int(password_rev)}
    return jwt.encode(to_encode, SECRET_KEY, algorithm=ALGORITHM)


def create_user(
    db: Session,
    username: str,
    password: str,
    *,
    is_admin: bool,
    commit: bool = True,
) -> User:
    existing = db.query(User).filter(User.username == username).first()
    if existing:
        raise ValueError("用户名已存在")

    user = User(
        username=username,
        password_hash=hash_password(password),
        is_admin=is_admin,
        primary_department_id=get_unassigned_department_id(db),
    )
    db.add(user)
    if commit:
        db.commit()
        db.refresh(user)
    else:
        db.flush()
    return user


def bind_wechat(
    db: Session,
    user: User,
    openid: str,
    unionid: str | None = None,
    wechat_nickname: str | None = None,
    *,
    commit: bool = True,
) -> None:
    existing = db.query(User).filter(User.wechat_openid == openid).first()
    if existing and existing.id != user.id:
        raise ValueError("该微信账号已绑定到其他用户")
    user.wechat_openid = openid
    user.wechat_unionid = unionid
    user.wechat_nickname = wechat_nickname
    db.add(user)
    if commit:
        db.commit()
        db.refresh(user)


def change_password(db: Session, user: User, current_password: str, new_password: str) -> None:
    if not verify_password(current_password, user.password_hash):
        raise ValueError("当前密码错误")
    user.password_hash = hash_password(new_password)
    user.password_rev = int(user.password_rev or 0) + 1
    db.commit()


def admin_set_user_password(db: Session, target: User, new_password: str, *, commit: bool = True) -> None:
    """管理员为目标用户设置新密码（递增 password_rev，使旧 JWT 失效）。"""
    target.password_hash = hash_password(new_password)
    target.password_rev = int(target.password_rev or 0) + 1
    if commit:
        db.commit()
        db.refresh(target)


def record_user_login(db: Session, user: User, *, commit: bool = True) -> None:
    from utils.timezone import beijing_now

    user.last_login_at = beijing_now().replace(tzinfo=None)
    db.add(user)
    if commit:
        db.commit()
        db.refresh(user)


def authenticate_user(db: Session, username: str, password: str) -> User:
    user = db.query(User).filter(User.username == username).first()
    if not user or not verify_password(password, user.password_hash):
        raise ValueError("用户名或密码错误")
    if not user.is_active:
        raise ValueError("账号已停用")
    return user
