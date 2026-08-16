# Copyright (c) 2026 徐泽宇
"""PostgreSQL full-text search configuration (008 zhparser).

Authors:
    徐泽宇

Copyright:
    © 2026 徐泽宇
"""

from __future__ import annotations

import logging
import threading

from sqlalchemy import text
from sqlalchemy.orm import Session

from config import KB_FTS_CONFIG, KB_FTS_LONG_QUERY_LEN
from services.system_setting_service import KEY_KB_FTS_CONFIG, get_public_settings_dict

logger = logging.getLogger(__name__)

FTS_SIMPLE = "simple"
FTS_ZH_CN = "zh_cn"
VALID_FTS_CONFIGS = frozenset({FTS_SIMPLE, FTS_ZH_CN})

_cache_lock = threading.Lock()
_zhparser_installed: bool | None = None


def invalidate_zhparser_cache() -> None:
    global _zhparser_installed
    with _cache_lock:
        _zhparser_installed = None


def zhparser_parser_ready(db: Session) -> bool:
    row = db.execute(
        text("SELECT 1 FROM pg_ts_parser WHERE prsname = 'zhparser' LIMIT 1")
    ).first()
    return row is not None


def zh_cn_fts_ready(db: Session) -> bool:
    row = db.execute(
        text("SELECT 1 FROM pg_ts_config WHERE cfgname = 'zh_cn' LIMIT 1")
    ).first()
    return row is not None


def zhparser_installed(db: Session) -> bool:
    global _zhparser_installed
    with _cache_lock:
        if _zhparser_installed is not None:
            return _zhparser_installed
    installed = zh_cn_fts_ready(db) and zhparser_parser_ready(db)
    with _cache_lock:
        _zhparser_installed = installed
    return installed


def get_configured_fts_config(
    db: Session | None,
    *,
    user_id: int | None = None,
    effective: dict[str, str] | None = None,
) -> str:
    cfg = (KB_FTS_CONFIG or FTS_ZH_CN).strip().lower()
    if effective is not None:
        raw = effective.get(KEY_KB_FTS_CONFIG, cfg)
        cfg = str(raw).strip().lower()
    elif db is not None and user_id is not None:
        from services.user_setting_service import get_user_effective_dict

        raw = get_user_effective_dict(db, user_id).get(KEY_KB_FTS_CONFIG, cfg)
        cfg = str(raw).strip().lower()
    elif db is not None:
        raw = get_public_settings_dict(db).get(KEY_KB_FTS_CONFIG, cfg)
        cfg = str(raw).strip().lower()
    if cfg not in VALID_FTS_CONFIGS:
        return FTS_ZH_CN
    return cfg


def get_effective_fts_config(
    db: Session,
    *,
    user_id: int | None = None,
    effective: dict[str, str] | None = None,
) -> str:
    cfg = get_configured_fts_config(db, user_id=user_id, effective=effective)
    if cfg == FTS_ZH_CN and not zhparser_installed(db):
        logger.warning("zhparser 未安装，FTS 降级为 simple")
        return FTS_SIMPLE
    return cfg


def should_use_plainto_for_query(query: str) -> bool:
    q = query.strip()
    if not q:
        return False
    return len(q) <= KB_FTS_LONG_QUERY_LEN


def ensure_zhparser_fts(db: Session) -> bool:
    """幂等：扩展可用且未配置 zh_cn 时创建（换 zhparser 镜像后重启 API 即可）。"""
    row = db.execute(
        text("SELECT 1 FROM pg_available_extensions WHERE name = 'zhparser' LIMIT 1")
    ).first()
    if row is None:
        return False
    db.execute(text("CREATE EXTENSION IF NOT EXISTS zhparser"))
    if not zhparser_parser_ready(db):
        logger.warning("zhparser 扩展已创建但 parser 未就绪，跳过 zh_cn 配置")
        return False
    if zh_cn_fts_ready(db):
        invalidate_zhparser_cache()
        return True
    db.execute(
        text(
            """
            CREATE TEXT SEARCH CONFIGURATION zh_cn (PARSER = zhparser);
            ALTER TEXT SEARCH CONFIGURATION zh_cn
              ADD MAPPING FOR n,v,a,i,e,l,j WITH simple;
            """
        )
    )
    db.commit()
    invalidate_zhparser_cache()
    logger.info("zhparser FTS 已就绪（zh_cn）")
    return True
