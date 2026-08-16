# Copyright (c) 2026 徐泽宇
"""Insavlo extract provider runtime configuration."""

from __future__ import annotations

import ipaddress
from dataclasses import dataclass
from urllib.parse import urlparse

from sqlalchemy.orm import Session

from models.system_setting import SystemSetting
from services.system_setting_service import (
    DEFAULTS,
    KEY_KB_EXTRACT_INSAVLO_API_KEY,
    KEY_KB_EXTRACT_INSAVLO_BASE_URL,
    KEY_KB_EXTRACT_INSAVLO_CALLBACK_ORIGIN,
    KEY_KB_EXTRACT_INSAVLO_ENABLED,
    KEY_KB_EXTRACT_INSAVLO_SKILL_CODE,
    KEY_KB_EXTRACT_INSAVLO_TIMEOUT_MINUTES,
    KEY_KB_EXTRACT_INSAVLO_WEBHOOK_SECRET,
    KB_EXTRACT_INSAVLO_TIMEOUT_MINUTES_MAX,
    KB_EXTRACT_INSAVLO_TIMEOUT_MINUTES_MIN,
    get_fresh_public_settings_dict,
    insavlo_credential_from_stored,
)

CALLBACK_PATH = "/api/webhooks/insavlo/document-process"


@dataclass(frozen=True)
class InsavloRuntimeConfig:
    base_url: str
    api_key: str
    webhook_secret: str
    skill_code: str
    callback_origin: str
    callback_url: str
    timeout_minutes: int


def _setting_value(db: Session, key: str) -> str:
    row = db.query(SystemSetting).filter(SystemSetting.setting_key == key).first()
    if row is None:
        return DEFAULTS.get(key, "")
    return row.value or ""


def _plain_api_key(db: Session) -> str:
    return insavlo_credential_from_stored(_setting_value(db, KEY_KB_EXTRACT_INSAVLO_API_KEY))


def _plain_webhook_secret(db: Session) -> str:
    return insavlo_credential_from_stored(
        _setting_value(db, KEY_KB_EXTRACT_INSAVLO_WEBHOOK_SECRET)
    )


def _normalize_url(value: str) -> str:
    return value.strip().rstrip("/")


def _host_is_public(hostname: str) -> bool:
    try:
        ip = ipaddress.ip_address(hostname)
        return not (
            ip.is_private
            or ip.is_loopback
            or ip.is_link_local
            or ip.is_multicast
            or ip.is_reserved
            or ip.is_unspecified
        )
    except ValueError:
        pass

    if hostname.lower() in {"localhost", "metadata.google.internal"}:
        return False
    return True


def validate_url(value: str, *, require_public_host: bool) -> str:
    normalized = _normalize_url(value)
    parsed = urlparse(normalized)
    if parsed.scheme not in {"http", "https"} or not parsed.hostname:
        raise ValueError("Insavlo URL 必须为 http/https 且包含 host")
    if require_public_host and not _host_is_public(parsed.hostname):
        raise ValueError("Insavlo URL 不允许指向本机、内网或保留地址")
    return normalized


def _insavlo_public_settings(
    db: Session,
    public_settings: dict[str, str] | None,
) -> dict[str, str]:
    if public_settings is not None:
        return public_settings
    return get_fresh_public_settings_dict(db)


def validate_insavlo_settings(
    db: Session,
    *,
    public_settings: dict[str, str] | None = None,
) -> list[str]:
    settings = _insavlo_public_settings(db, public_settings)
    errors: list[str] = []
    enabled = str(settings.get(KEY_KB_EXTRACT_INSAVLO_ENABLED, "false")).lower() == "true"
    if not enabled:
        errors.append("Insavlo 未启用")
    try:
        validate_url(settings.get(KEY_KB_EXTRACT_INSAVLO_BASE_URL, ""), require_public_host=True)
    except ValueError as exc:
        errors.append(str(exc))
    try:
        validate_url(settings.get(KEY_KB_EXTRACT_INSAVLO_CALLBACK_ORIGIN, ""), require_public_host=False)
    except ValueError as exc:
        errors.append(str(exc))
    if not settings.get(KEY_KB_EXTRACT_INSAVLO_SKILL_CODE, "").strip():
        errors.append("Insavlo skill_code 未配置")
    try:
        timeout_minutes = int(
            str(settings.get(KEY_KB_EXTRACT_INSAVLO_TIMEOUT_MINUTES, "120")).strip()
        )
    except ValueError:
        timeout_minutes = 0
    if not (KB_EXTRACT_INSAVLO_TIMEOUT_MINUTES_MIN <= timeout_minutes <= KB_EXTRACT_INSAVLO_TIMEOUT_MINUTES_MAX):
        errors.append(
            f"Insavlo timeout_minutes 须在 "
            f"{KB_EXTRACT_INSAVLO_TIMEOUT_MINUTES_MIN}–{KB_EXTRACT_INSAVLO_TIMEOUT_MINUTES_MAX} 之间"
        )
    if not _plain_api_key(db):
        errors.append("Insavlo API Key 未配置")
    if not _plain_webhook_secret(db):
        errors.append("Insavlo Webhook Secret 未配置")
    return errors


def is_insavlo_runtime_ready(
    db: Session,
    *,
    public_settings: dict[str, str] | None = None,
) -> bool:
    return not validate_insavlo_settings(db, public_settings=public_settings)


def get_insavlo_runtime_config(db: Session) -> InsavloRuntimeConfig:
    settings = get_fresh_public_settings_dict(db)
    errors = validate_insavlo_settings(db, public_settings=settings)
    if errors:
        raise ValueError("；".join(errors))
    base_url = validate_url(settings[KEY_KB_EXTRACT_INSAVLO_BASE_URL], require_public_host=True)
    callback_origin = validate_url(
        settings[KEY_KB_EXTRACT_INSAVLO_CALLBACK_ORIGIN],
        require_public_host=False,
    )
    return InsavloRuntimeConfig(
        base_url=base_url,
        api_key=_plain_api_key(db),
        webhook_secret=_plain_webhook_secret(db),
        skill_code=settings[KEY_KB_EXTRACT_INSAVLO_SKILL_CODE].strip(),
        callback_origin=callback_origin,
        callback_url=f"{callback_origin}{CALLBACK_PATH}",
        timeout_minutes=int(settings[KEY_KB_EXTRACT_INSAVLO_TIMEOUT_MINUTES]),
    )
