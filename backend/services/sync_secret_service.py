# Copyright (c) 2026 徐泽宇
"""AES-GCM encrypt/decrypt for external sync source secrets (049 Phase B)."""

from __future__ import annotations

import hashlib
import os

from cryptography.exceptions import InvalidTag
from cryptography.hazmat.primitives.ciphers.aead import AESGCM

from config import sync_secret_key

_NONCE_LEN = 12
_TAG_LEN = 16


class SyncSecretNotConfiguredError(ValueError):
    """生产环境未配置 FILEX_SYNC_SECRET_KEY。"""


def _aesgcm_key() -> bytes:
    raw = sync_secret_key()
    if not raw:
        raise SyncSecretNotConfiguredError("FILEX_SYNC_SECRET_KEY 未配置")
    return hashlib.sha256(raw.encode("utf-8")).digest()


def sync_secret_configured() -> bool:
    return bool(sync_secret_key())


def require_sync_secret_configured() -> None:
    if not sync_secret_configured():
        raise SyncSecretNotConfiguredError("FILEX_SYNC_SECRET_KEY 未配置")


def encrypt_sync_secret(plaintext: str) -> bytes:
    """Return nonce(12) || ciphertext || tag(16)."""
    require_sync_secret_configured()
    nonce = os.urandom(_NONCE_LEN)
    aes = AESGCM(_aesgcm_key())
    ciphertext_with_tag = aes.encrypt(nonce, plaintext.encode("utf-8"), None)
    if len(ciphertext_with_tag) < _TAG_LEN:
        raise ValueError("invalid AES-GCM output")
    return nonce + ciphertext_with_tag


def decrypt_sync_secret(blob: bytes) -> str:
    if len(blob) < _NONCE_LEN + _TAG_LEN:
        raise ValueError("invalid sync secret ciphertext")
    nonce = blob[:_NONCE_LEN]
    ciphertext_with_tag = blob[_NONCE_LEN:]
    aes = AESGCM(_aesgcm_key())
    try:
        plain = aes.decrypt(nonce, ciphertext_with_tag, None)
    except InvalidTag as exc:
        raise ValueError("cannot decrypt sync secret") from exc
    return plain.decode("utf-8")


def sync_secret_preview(plaintext: str) -> str:
    if not plaintext:
        return ""
    if len(plaintext) >= 12:
        return plaintext[-4:]
    return "****"


def redact_sync_secret(text: str, *secrets: str) -> str:
    """Remove known plaintext secrets from log/error strings."""
    result = text or ""
    for secret in secrets:
        if not secret:
            continue
        result = result.replace(secret, "****")
    return result
