# Copyright (c) 2026 徐泽宇
"""HMAC signed URLs for Web preview extract-assets (105)."""

from __future__ import annotations

import base64
import hashlib
import hmac
import json
import os
import time
from collections import OrderedDict
from typing import Any

from config import EXTRACT_ASSET_HINT_CACHE_SIZE, EXTRACT_ASSET_SIGN_TTL_SECONDS, extract_asset_signing_secret
from services.kb_figure_refs import extract_asset_abs_path_for_file_id

_assets_dir_hint_by_file_id: OrderedDict[int, str] = OrderedDict()


def remember_extract_assets_dir(file_id: int, assets_dir: str) -> None:
    """Cache extract dir from ACL-checked sign request for faster path lookup."""
    if not assets_dir or not os.path.isdir(assets_dir):
        return
    _assets_dir_hint_by_file_id[file_id] = assets_dir
    _assets_dir_hint_by_file_id.move_to_end(file_id)
    while len(_assets_dir_hint_by_file_id) > EXTRACT_ASSET_HINT_CACHE_SIZE:
        _assets_dir_hint_by_file_id.popitem(last=False)


def _b64url_encode(data: bytes) -> str:
    return base64.urlsafe_b64encode(data).rstrip(b"=").decode("ascii")


def _b64url_decode(value: str) -> bytes:
    pad = "=" * (-len(value) % 4)
    return base64.urlsafe_b64decode(value + pad)


def _sign_payload_b64(payload_b64: str) -> str:
    digest = hmac.new(
        extract_asset_signing_secret(),
        payload_b64.encode("ascii"),
        hashlib.sha256,
    ).digest()
    return _b64url_encode(digest)


def build_signed_extract_asset_token(file_id: int, asset_key: str, exp: int) -> str:
    payload = {"f": file_id, "k": asset_key, "e": exp}
    payload_b64 = _b64url_encode(
        json.dumps(payload, separators=(",", ":"), sort_keys=True).encode("utf-8")
    )
    return f"{payload_b64}.{_sign_payload_b64(payload_b64)}"


def signed_extract_asset_url(file_id: int, asset_key: str, exp: int) -> str:
    token = build_signed_extract_asset_token(file_id, asset_key, exp)
    return f"/api/files/signed-extract-assets/{token}"


def sign_extract_asset_urls(
    file_id: int,
    asset_keys: list[str],
    *,
    ttl_seconds: int | None = None,
) -> tuple[list[dict[str, Any]], int]:
    ttl = ttl_seconds if ttl_seconds is not None else EXTRACT_ASSET_SIGN_TTL_SECONDS
    exp = int(time.time()) + max(1, ttl)
    items: list[dict[str, Any]] = []
    for key in asset_keys:
        items.append(
            {
                "asset_key": key,
                "url": signed_extract_asset_url(file_id, key, exp),
                "expires_at": exp,
            }
        )
    return items, exp


def verify_signed_extract_asset_token(signed_token: str) -> dict[str, Any] | None:
    parts = signed_token.split(".", 1)
    if len(parts) != 2:
        return None
    payload_b64, sig_b64 = parts
    if not payload_b64 or not sig_b64:
        return None
    expected_sig = _sign_payload_b64(payload_b64)
    if not hmac.compare_digest(sig_b64, expected_sig):
        return None
    try:
        payload = json.loads(_b64url_decode(payload_b64))
    except (ValueError, json.JSONDecodeError, UnicodeDecodeError):
        return None
    file_id = payload.get("f")
    asset_key = payload.get("k")
    exp = payload.get("e")
    if not isinstance(file_id, int) or not isinstance(asset_key, str) or not isinstance(exp, int):
        return None
    if exp < int(time.time()):
        return None
    return {"file_id": file_id, "asset_key": asset_key, "exp": exp}


def resolve_signed_extract_asset_path(file_id: int, asset_key: str) -> str | None:
    hint = _assets_dir_hint_by_file_id.get(file_id)
    return extract_asset_abs_path_for_file_id(file_id, asset_key, assets_dir_hint=hint)
