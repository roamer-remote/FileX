# Copyright (c) 2026 徐泽宇
"""FileX License Key 解析、验签与 system_settings 状态（021）。

Authors:
    徐泽宇

Copyright:
    © 2026 徐泽宇
"""

from __future__ import annotations

import base64
import binascii
import hashlib
import hmac
import json
import logging
import time
from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Any

from sqlalchemy.orm import Session

from config import FILEX_ENV, LICENSE_TRIAL_DAYS, license_hmac_secret
from models.system_setting import SystemSetting
from utils.timezone import BEIJING_TZ, beijing_now

logger = logging.getLogger(__name__)

LICENSE_PREFIX = "FILEX1"
KEY_LICENSE_KEY = "license_key"
KEY_LICENSE_TRIAL_STARTED_AT = "license_trial_started_at"
MAX_PAYLOAD_BYTES = 1024

REASON_EXPIRED = "expired"
REASON_TRIAL_EXPIRED = "trial_expired"
REASON_MISSING = "missing"
REASON_INVALID_SIGNATURE = "invalid_signature"
REASON_MALFORMED = "malformed"

_LICENSE_INVALID_REASONS = frozenset({REASON_MISSING, REASON_INVALID_SIGNATURE, REASON_MALFORMED})

LICENSE_STATUS_HINT = "FileX 授权已过期，请联系管理员更新 License Key"
LICENSE_INVALID_HINT = "FileX License Key 无效，请联系管理员更新 License Key"


class LicenseError(Exception):
    """授权无效；携带 LicenseStatus 供 API 返回。"""

    def __init__(self, status: LicenseStatus):
        self.status = status
        super().__init__(status.reason or "license_invalid")


@dataclass(frozen=True)
class LicenseStatus:
    """授权状态 业务服务。

        Authors:
            徐泽宇

        Copyright:
            © 2026 徐泽宇

        Since:
            2026-06-10

        Attributes:
            valid: 有效（bool）。
            reason: 原因（str | None）。
            expires_at: 过期时间（datetime | None）。
            customer_id: 客户ID（str | None）。
            days_remaining: daysremaining（int | None）。
            in_trial: in试用（bool）。
    """
    valid: bool
    reason: str | None
    expires_at: datetime | None
    customer_id: str | None
    days_remaining: int | None
    in_trial: bool

    def to_dict(self) -> dict[str, Any]:
        return {
            "valid": self.valid,
            "reason": self.reason,
            "expires_at": _iso_expires(self.expires_at),
            "customer_id": self.customer_id,
            "days_remaining": self.days_remaining,
            "in_trial": self.in_trial,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> LicenseStatus:
        exp_raw = data.get("expires_at")
        expires_at = _parse_iso(exp_raw) if exp_raw else None
        days = data.get("days_remaining")
        return cls(
            valid=bool(data.get("valid")),
            reason=data.get("reason"),
            expires_at=expires_at,
            customer_id=data.get("customer_id"),
            days_remaining=int(days) if days is not None else None,
            in_trial=bool(data.get("in_trial")),
        )


def _iso_expires(dt: datetime | None) -> str | None:
    if dt is None:
        return None
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=BEIJING_TZ)
    return dt.astimezone(BEIJING_TZ).isoformat()


def _parse_iso(raw: str) -> datetime:
    dt = datetime.fromisoformat(str(raw).replace("Z", "+00:00"))
    if dt.tzinfo is None:
        return dt.replace(tzinfo=BEIJING_TZ)
    return dt.astimezone(BEIJING_TZ)


def _b64url_encode(data: bytes) -> str:
    return base64.urlsafe_b64encode(data).decode("ascii").rstrip("=")


def _b64url_decode(raw: str) -> bytes:
    pad = "=" * (-len(raw) % 4)
    return base64.urlsafe_b64decode(raw + pad)


def _days_remaining(expires_at: datetime | None) -> int | None:
    if expires_at is None:
        return None
    now = beijing_now()
    exp = expires_at if expires_at.tzinfo else expires_at.replace(tzinfo=BEIJING_TZ)
    delta = (exp - now).total_seconds()
    return max(0, int(delta // 86400))


def _invalid(reason: str, *, expires_at: datetime | None = None, customer_id: str | None = None) -> LicenseStatus:
    return LicenseStatus(
        valid=False,
        reason=reason,
        expires_at=expires_at,
        customer_id=customer_id,
        days_remaining=_days_remaining(expires_at) if expires_at else 0,
        in_trial=False,
    )


def _valid_from_payload(payload: dict[str, Any]) -> LicenseStatus:
    expires_at = _parse_iso(str(payload["expires_at"]))
    now = beijing_now()
    customer_id = str(payload.get("customer_id") or "")
    if now >= expires_at:
        return _invalid(REASON_EXPIRED, expires_at=expires_at, customer_id=customer_id or None)
    return LicenseStatus(
        valid=True,
        reason=None,
        expires_at=expires_at,
        customer_id=customer_id or None,
        days_remaining=_days_remaining(expires_at),
        in_trial=False,
    )


def build_license_key(
    *,
    customer_id: str,
    expires_at: datetime,
    edition: str = "standard",
    features: list[str] | None = None,
    secret: str | None = None,
) -> str:
    """签发 FILEX1 license key（运维脚本与测试用）。"""
    hmac_secret = secret if secret is not None else license_hmac_secret()
    if not hmac_secret:
        raise ValueError("FILEX_LICENSE_HMAC_SECRET 未配置")
    exp = expires_at if expires_at.tzinfo else expires_at.replace(tzinfo=BEIJING_TZ)
    payload = {
        "v": 1,
        "customer_id": customer_id,
        "expires_at": exp.astimezone(BEIJING_TZ).isoformat(),
        "edition": edition,
        "features": features or [],
    }
    payload_bytes = json.dumps(payload, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
    if len(payload_bytes) > MAX_PAYLOAD_BYTES:
        raise ValueError(f"payload 超过 {MAX_PAYLOAD_BYTES} bytes")
    payload_b64 = _b64url_encode(payload_bytes)
    sig = hmac.new(hmac_secret.encode("utf-8"), payload_b64.encode("ascii"), hashlib.sha256).digest()
    return f"{LICENSE_PREFIX}.{payload_b64}.{_b64url_encode(sig)}"


def parse_and_verify_license_key(raw: str) -> LicenseStatus:
    """验签并判断过期；不访问 DB。"""
    raw = (raw or "").strip()
    if not raw:
        return _invalid(REASON_MISSING)

    parts = raw.split(".")
    if len(parts) != 3 or parts[0] != LICENSE_PREFIX:
        return _invalid(REASON_MALFORMED)

    _, payload_b64, sig_b64 = parts
    hmac_secret = license_hmac_secret()
    if not hmac_secret:
        return _invalid(REASON_MALFORMED)

    try:
        expected_sig = hmac.new(
            hmac_secret.encode("utf-8"),
            payload_b64.encode("ascii"),
            hashlib.sha256,
        ).digest()
        actual_sig = _b64url_decode(sig_b64)
    except (ValueError, binascii.Error):
        return _invalid(REASON_MALFORMED)

    if not hmac.compare_digest(expected_sig, actual_sig):
        return _invalid(REASON_INVALID_SIGNATURE)

    try:
        payload_bytes = _b64url_decode(payload_b64)
    except binascii.Error:
        return _invalid(REASON_MALFORMED)

    if len(payload_bytes) > MAX_PAYLOAD_BYTES:
        return _invalid(REASON_MALFORMED)

    try:
        payload = json.loads(payload_bytes.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError):
        return _invalid(REASON_MALFORMED)

    if payload.get("v") != 1 or not payload.get("expires_at"):
        return _invalid(REASON_MALFORMED)

    return _valid_from_payload(payload)


def _get_or_create_setting(db: Session, key: str, default: str = "") -> SystemSetting:
    row = db.query(SystemSetting).filter(SystemSetting.setting_key == key).first()
    if row:
        return row
    row = SystemSetting(setting_key=key, value=default)
    db.add(row)
    db.flush()
    return row


def _read_setting(db: Session, key: str) -> str:
    row = db.query(SystemSetting).filter(SystemSetting.setting_key == key).first()
    return (row.value if row else "") or ""


def _ensure_trial_started(db: Session) -> datetime:
    row = _get_or_create_setting(db, KEY_LICENSE_TRIAL_STARTED_AT, "")
    if (row.value or "").strip():
        return _parse_iso(row.value.strip())
    started = beijing_now()
    row.value = started.isoformat()
    db.flush()
    logger.info("license_trial_started_at=%s", row.value)
    return started


def _is_development_exempt(license_key_raw: str) -> bool:
    return FILEX_ENV.lower() == "development" and not (license_key_raw or "").strip()


def _status_from_trial(db: Session) -> LicenseStatus:
    started = _ensure_trial_started(db)
    trial_end = started + timedelta(days=LICENSE_TRIAL_DAYS)
    now = beijing_now()
    if now < trial_end:
        return LicenseStatus(
            valid=True,
            reason=None,
            expires_at=trial_end,
            customer_id=None,
            days_remaining=_days_remaining(trial_end),
            in_trial=True,
        )
    return _invalid(REASON_TRIAL_EXPIRED, expires_at=trial_end)


def get_license_status(db: Session) -> LicenseStatus:
    """FR-105 优先级：development 豁免 → 非空 key 验签 → 试用。"""
    license_key_raw = _read_setting(db, KEY_LICENSE_KEY).strip()

    if _is_development_exempt(license_key_raw):
        return LicenseStatus(
            valid=True,
            reason=None,
            expires_at=None,
            customer_id=None,
            days_remaining=None,
            in_trial=False,
        )

    if license_key_raw:
        return parse_and_verify_license_key(license_key_raw)

    return _status_from_trial(db)


def assert_license_valid(db: Session) -> LicenseStatus:
    status = get_license_status(db)
    if not status.valid:
        raise LicenseError(status)
    return status


def activate_license(db: Session, raw_key: str, *, commit: bool = True) -> LicenseStatus:
    """验签并写入 license_key；调用方负责 invalidate_license_cache 与 operation_log。"""
    parsed = parse_and_verify_license_key(raw_key)
    if not parsed.valid:
        raise ValueError(f"无效的 License Key: {parsed.reason}")

    row = _get_or_create_setting(db, KEY_LICENSE_KEY, "")
    row.value = raw_key.strip()
    if commit:
        db.commit()
    else:
        db.flush()
    return get_license_status(db)


def license_http_code(reason: str | None) -> str:
    if reason in _LICENSE_INVALID_REASONS:
        return "license_invalid"
    return "license_expired"


def license_http_detail(code: str) -> str:
    if code == "license_invalid":
        return "FileX License Key 无效，请检查密钥或联系管理员"
    return "FileX 授权已过期，请更新 License Key"


def license_http_body(status: LicenseStatus) -> dict[str, Any]:
    code = license_http_code(status.reason)
    return {
        "detail": license_http_detail(code),
        "code": code,
        "expires_at": _iso_expires(status.expires_at),
    }


def mask_license_key(raw: str | None) -> str | None:
    raw = (raw or "").strip()
    if len(raw) < 8:
        return None
    return f"****{raw[-4:]}"


LICENSE_WORKER_SLEEP_SEC = 60


def require_license_or_wait(db: Session) -> bool:
    """Worker 消费前检查；无效则 sleep 60s 并返回 False（FR-501）。"""
    from services.license_cache_service import get_cached_status

    status = get_cached_status(db)
    if status.valid:
        return True
    logger.warning("license_invalid_worker_sleep reason=%s", status.reason)
    time.sleep(LICENSE_WORKER_SLEEP_SEC)
    return False
