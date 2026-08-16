# Copyright (c) 2026 徐泽宇
"""One-shot MinerU provider auto-enable at kb-extract startup (032 PR-C / P-08)."""

from __future__ import annotations

import logging
import urllib.error
import urllib.request

from sqlalchemy.orm import Session

from config import FILEX_ENABLE_MINERU_PROVIDER, KB_EXTRACT_MINERU_URL
from services.system_setting_service import (
    KEY_KB_EXTRACT_PROVIDER,
    get_kb_extract_provider,
    invalidate_settings_cache,
    update_settings,
)

logger = logging.getLogger(__name__)


def _sidecar_healthy() -> bool:
    """HTTP GET /health for one-shot auto-enable only (P-08).

    Uses urllib (compose 内网直连，无代理需求). Failure returns False and
    skips provider switch; kb-extract startup is never blocked.
    """
    base = (KB_EXTRACT_MINERU_URL or "").strip().rstrip("/")
    if not base:
        logger.warning("mineru auto-enable skipped: KB_EXTRACT_MINERU_URL unset")
        return False
    url = f"{base}/health"
    try:
        with urllib.request.urlopen(url, timeout=5) as resp:
            if resp.status != 200:
                return False
            body = resp.read(256).decode("utf-8", errors="replace")
            return "ok" in body.lower()
    except (urllib.error.URLError, TimeoutError, OSError) as exc:
        logger.warning("mineru auto-enable sidecar health failed: %s", exc)
        return False


def maybe_auto_enable_mineru_provider(db: Session) -> bool:
    """Startup hook: legacy → mineru when env enabled and sidecar healthy."""
    if not FILEX_ENABLE_MINERU_PROVIDER:
        return False
    current = get_kb_extract_provider(db)
    if current != "legacy":
        logger.info("mineru auto-enable skipped: kb_extract_provider=%s", current)
        return False
    if not _sidecar_healthy():
        return False
    update_settings(db, {KEY_KB_EXTRACT_PROVIDER: "mineru"})
    db.commit()
    invalidate_settings_cache()
    logger.info("mineru auto-enable applied: kb_extract_provider legacy -> mineru")
    return True
