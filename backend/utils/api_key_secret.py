# Copyright (c) 2026 徐泽宇
"""Encrypt API key plaintext at rest so owners can reveal it later (requires SECRET_KEY).

Authors:
    徐泽宇

Copyright:
    © 2026 徐泽宇
"""
import base64
import hashlib

from cryptography.fernet import Fernet, InvalidToken

from config import SECRET_KEY


def _fernet() -> Fernet:
    digest = hashlib.sha256((SECRET_KEY + "|filebox-api-key-secret-v1").encode("utf-8")).digest()
    return Fernet(base64.urlsafe_b64encode(digest))


def encrypt_api_key_plaintext(plain: str) -> str:
    return _fernet().encrypt(plain.encode("utf-8")).decode("ascii")


def decrypt_api_key_plaintext(ciphertext: str) -> str:
    try:
        return _fernet().decrypt(ciphertext.encode("ascii")).decode("utf-8")
    except InvalidToken as e:
        raise ValueError("cannot decrypt API key secret") from e
