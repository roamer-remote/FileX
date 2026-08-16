# Copyright (c) 2026 徐泽宇
"""外部 API 与分享来源：可选的分享令牌校验，防止错用他人 API Key 处理他人分享文件。

Authors:
    徐泽宇

Copyright:
    © 2026 徐泽宇
"""

from fastapi import HTTPException, status
from sqlalchemy.orm import Session

from models.file import File as FileModel
from models.user import User
from services.share_service import get_share_by_token, verify_share_password


def validate_optional_share_context(
    db: Session,
    share_token: str | None,
    current_user: User,
    content_md5_hex: str,
    *,
    share_password: str | None = None,
) -> None:
    """
    若请求携带分享令牌，则必须同时满足：
    - 令牌有效且未过期、未超下载次数；
    - 若分享设置了密码，须通过 X-FileX-Share-Password 校验；
    - 分享对应文件的拥有者与当前 API Key 用户一致；
    - 库中该文件须已记录 MD5，且与请求体/上传内容 MD5 一致。

    若未携带令牌，则不额外校验（兼容既有脚本；无法推断字节来源）。
    """
    if not share_token or not share_token.strip():
        return

    token = share_token.strip()
    share = get_share_by_token(db, token)
    if not share:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="分享链接无效或已过期",
        )

    if share.password_hash:
        pwd = (share_password or "").strip()
        if not pwd:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="该分享链接需要密码",
            )
        if not verify_share_password(share, pwd):
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="分享密码错误",
            )

    file_row = db.query(FileModel).filter(FileModel.id == share.file_id).first()
    if not file_row:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="分享对应的资料不存在",
        )

    if file_row.user_id != current_user.id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="API 密钥必须与分享资料所有者一致；不能使用他人密钥处理他人分享的资料",
        )

    expected = (file_row.md5_hash or "").strip().lower()
    got = content_md5_hex.strip().lower()
    if not expected:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="分享资料尚未记录 MD5，无法校验内容一致性",
        )
    if got != expected:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="资料内容与分享链接对应的资料不一致（MD5 不匹配）",
        )
