# Copyright (c) 2026 徐泽宇
"""MinerU runtime configuration from system_settings (095)."""

from __future__ import annotations

import hashlib
import json
import math
import threading
from dataclasses import asdict, dataclass
from typing import Any

from sqlalchemy.orm import Session

from services.system_setting_service import (
    DEFAULTS,
    KEY_MINERU_FORMULA_ENABLE,
    KEY_MINERU_MIN_BATCH_FLOOR,
    KEY_MINERU_MIN_BATCH_INFERENCE_SIZE,
    KEY_MINERU_MIN_BATCH_MODE,
    KEY_MINERU_PAGE_CHUNK_ENABLED,
    KEY_MINERU_PAGE_CHUNK_PAGES,
    KEY_MINERU_PAGE_CHUNK_THRESHOLD,
    KEY_MINERU_PARSE_METHOD,
    KEY_MINERU_PARSE_TIMEOUT_SEC,
    KEY_MINERU_RPC_TIMEOUT_SEC,
    KEY_MINERU_TABLE_AUTO_ROTATE,
    KEY_MINERU_TABLE_ENABLE,
    KEY_MINERU_TABLE_ROTATE_MAX_TABLES,
    KEY_MINERU_TABLE_ROTATE_TIMEOUT_SEC,
)

RUNTIME_CONFIG_VERSION = 1

_DEFAULT_MEM_LIMIT_BYTES = 8 * 1024**3

_MINERU_DB_KEYS = (
    KEY_MINERU_MIN_BATCH_MODE,
    KEY_MINERU_MIN_BATCH_INFERENCE_SIZE,
    KEY_MINERU_MIN_BATCH_FLOOR,
    KEY_MINERU_PARSE_METHOD,
    KEY_MINERU_FORMULA_ENABLE,
    KEY_MINERU_TABLE_ENABLE,
    KEY_MINERU_PARSE_TIMEOUT_SEC,
    KEY_MINERU_RPC_TIMEOUT_SEC,
    KEY_MINERU_PAGE_CHUNK_ENABLED,
    KEY_MINERU_PAGE_CHUNK_THRESHOLD,
    KEY_MINERU_PAGE_CHUNK_PAGES,
    KEY_MINERU_TABLE_AUTO_ROTATE,
    KEY_MINERU_TABLE_ROTATE_MAX_TABLES,
    KEY_MINERU_TABLE_ROTATE_TIMEOUT_SEC,
)

_mineru_runtime_cache: MineruRuntimeConfig | None = None
_mineru_cache_lock = threading.Lock()


def invalidate_mineru_runtime_cache() -> None:
    global _mineru_runtime_cache
    with _mineru_cache_lock:
        _mineru_runtime_cache = None


@dataclass(frozen=True)
class MineruRuntimeConfig:
    min_batch_mode: str
    min_batch_inference_size: int
    min_batch_floor: int
    parse_method: str
    formula_enable: bool
    table_enable: bool
    parse_timeout_sec: int
    rpc_timeout_sec: int
    page_chunk_enabled: bool
    page_chunk_threshold: int
    page_chunk_pages: int
    table_auto_rotate: bool
    table_rotate_max_tables: int
    table_rotate_timeout_sec: int

    @property
    def config_fingerprint(self) -> str:
        return build_config_fingerprint(self)


def build_config_fingerprint(cfg: MineruRuntimeConfig) -> str:
    payload = asdict(cfg)
    stable = json.dumps(payload, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(stable.encode()).hexdigest()[:16]


def runtime_config_to_payload(cfg: MineruRuntimeConfig) -> dict[str, Any]:
    data = asdict(cfg)
    data["config_fingerprint"] = cfg.config_fingerprint
    return data


def _resolve_str(db_values: dict[str, str], key: str, default: str) -> str:
    if key in db_values:
        return db_values[key]
    return default


def _parse_bool(raw: str) -> bool:
    return str(raw).strip().lower() in ("1", "true", "yes", "on")


def _parse_runtime_from_map(db_values: dict[str, str]) -> MineruRuntimeConfig:
    mode = _resolve_str(
        db_values,
        KEY_MINERU_MIN_BATCH_MODE,
        DEFAULTS[KEY_MINERU_MIN_BATCH_MODE],
    ).lower()
    if mode not in ("fixed", "auto"):
        mode = DEFAULTS[KEY_MINERU_MIN_BATCH_MODE]

    parse_method = _resolve_str(
        db_values,
        KEY_MINERU_PARSE_METHOD,
        DEFAULTS[KEY_MINERU_PARSE_METHOD],
    ).lower()
    if parse_method not in ("auto", "txt", "ocr"):
        parse_method = DEFAULTS[KEY_MINERU_PARSE_METHOD]

    return MineruRuntimeConfig(
        min_batch_mode=mode,
        min_batch_inference_size=_parse_min_batch_size(
            _resolve_str(
                db_values,
                KEY_MINERU_MIN_BATCH_INFERENCE_SIZE,
                DEFAULTS[KEY_MINERU_MIN_BATCH_INFERENCE_SIZE],
            )
        ),
        min_batch_floor=_parse_min_batch_floor(
            _resolve_str(
                db_values,
                KEY_MINERU_MIN_BATCH_FLOOR,
                DEFAULTS[KEY_MINERU_MIN_BATCH_FLOOR],
            )
        ),
        parse_method=parse_method,
        formula_enable=_parse_bool(
            _resolve_str(
                db_values,
                KEY_MINERU_FORMULA_ENABLE,
                DEFAULTS[KEY_MINERU_FORMULA_ENABLE],
            )
        ),
        table_enable=_parse_bool(
            _resolve_str(
                db_values,
                KEY_MINERU_TABLE_ENABLE,
                DEFAULTS[KEY_MINERU_TABLE_ENABLE],
            )
        ),
        parse_timeout_sec=_parse_parse_timeout_sec(
            _resolve_str(
                db_values,
                KEY_MINERU_PARSE_TIMEOUT_SEC,
                DEFAULTS[KEY_MINERU_PARSE_TIMEOUT_SEC],
            )
        ),
        rpc_timeout_sec=_parse_rpc_timeout_sec(
            _resolve_str(
                db_values,
                KEY_MINERU_RPC_TIMEOUT_SEC,
                DEFAULTS[KEY_MINERU_RPC_TIMEOUT_SEC],
            )
        ),
        page_chunk_enabled=_parse_bool(
            _resolve_str(
                db_values,
                KEY_MINERU_PAGE_CHUNK_ENABLED,
                DEFAULTS[KEY_MINERU_PAGE_CHUNK_ENABLED],
            )
        ),
        page_chunk_threshold=_parse_page_chunk_threshold(
            _resolve_str(
                db_values,
                KEY_MINERU_PAGE_CHUNK_THRESHOLD,
                DEFAULTS[KEY_MINERU_PAGE_CHUNK_THRESHOLD],
            )
        ),
        page_chunk_pages=_parse_page_chunk_pages(
            _resolve_str(
                db_values,
                KEY_MINERU_PAGE_CHUNK_PAGES,
                DEFAULTS[KEY_MINERU_PAGE_CHUNK_PAGES],
            )
        ),
        table_auto_rotate=_parse_bool(
            _resolve_str(
                db_values,
                KEY_MINERU_TABLE_AUTO_ROTATE,
                DEFAULTS[KEY_MINERU_TABLE_AUTO_ROTATE],
            )
        ),
        table_rotate_max_tables=_parse_table_rotate_max_tables(
            _resolve_str(
                db_values,
                KEY_MINERU_TABLE_ROTATE_MAX_TABLES,
                DEFAULTS[KEY_MINERU_TABLE_ROTATE_MAX_TABLES],
            )
        ),
        table_rotate_timeout_sec=_parse_table_rotate_timeout_sec(
            _resolve_str(
                db_values,
                KEY_MINERU_TABLE_ROTATE_TIMEOUT_SEC,
                DEFAULTS[KEY_MINERU_TABLE_ROTATE_TIMEOUT_SEC],
            )
        ),
    )


def _load_config_from_db(db: Session) -> MineruRuntimeConfig:
    from services.system_setting_service import get_public_settings_dict

    settings = get_public_settings_dict(db)
    db_values = {k: str(settings[k]) for k in _MINERU_DB_KEYS if k in settings}
    return _parse_runtime_from_map(db_values)


def get_mineru_runtime_config(db: Session | None = None, *, fresh: bool = False) -> MineruRuntimeConfig:
    """Load MinerU settings from system_settings (DB-first; defaults seeded on first read)."""
    global _mineru_runtime_cache

    if not fresh:
        with _mineru_cache_lock:
            if _mineru_runtime_cache is not None:
                return _mineru_runtime_cache

    if db is None:
        from database import SessionLocal

        db = SessionLocal()
        try:
            loaded = _load_config_from_db(db)
        finally:
            db.close()
    else:
        loaded = _load_config_from_db(db)

    with _mineru_cache_lock:
        _mineru_runtime_cache = loaded
    return loaded


def resolve_effective_batch(
    page_count: int,
    mem_limit_bytes: int,
    cfg: MineruRuntimeConfig,
) -> int:
    """FR-095-002b — locked formula."""
    ceiling = cfg.min_batch_inference_size
    floor = cfg.min_batch_floor
    if cfg.min_batch_mode == "fixed":
        return ceiling

    mem_gb = mem_limit_bytes / (1024**3)
    batch = min(ceiling, max(floor, int(mem_gb * 4)))
    pages = max(0, int(page_count))
    if pages > 200:
        batch = max(floor, batch // 2)
    if pages > 400:
        batch = max(floor, batch // 2)
    return batch


def estimate_chunk_count(page_count: int, cfg: MineruRuntimeConfig) -> int:
    pages = max(0, int(page_count))
    if not cfg.page_chunk_enabled or pages <= cfg.page_chunk_threshold:
        return 1
    return max(1, math.ceil(pages / cfg.page_chunk_pages))


def resolve_effective_rpc_timeout_sec(
    cfg: MineruRuntimeConfig,
    *,
    page_count: int | None = None,
) -> float:
    """FR-095-003c."""
    chunk_count = estimate_chunk_count(page_count or 0, cfg)
    return float(
        max(
            cfg.rpc_timeout_sec,
            cfg.parse_timeout_sec * chunk_count + 120,
        )
    )


def collect_mineru_settings_warnings(settings: dict[str, str]) -> list[str]:
    """SC-095-06 soft warn when rpc timeout is shorter than worst-case chunk serial."""
    cfg = _parse_runtime_from_public(settings)
    if not cfg.page_chunk_enabled:
        return []
    chunk_est = max(1, math.ceil(cfg.page_chunk_threshold / cfg.page_chunk_pages))
    worst = cfg.parse_timeout_sec * chunk_est
    if cfg.rpc_timeout_sec < worst:
        return [
            f"mineru_rpc_timeout_sec（{cfg.rpc_timeout_sec}s）低于 worst-case 页段累计（约 {worst}s）；"
            "保存成功，运行时 kb-extract 将按 003c 公式自动延长 RPC 超时"
        ]
    return []


def _parse_runtime_from_public(settings: dict[str, str]) -> MineruRuntimeConfig:
    db_values = {k: str(settings[k]) for k in _MINERU_DB_KEYS if k in settings}
    return _parse_runtime_from_map(db_values)


def pdf_page_count(file_path: str) -> int:
    """Count PDF pages.

    Automatically resolves container-style paths (e.g. /app/uploads/...) to the
    current process's UPLOAD_DIR when running on host (kb-extract worker).
    This is needed because files.file_path may have been written by the API
    container (UPLOAD_DIR=/app/uploads) while the worker runs on the host.
    """
    from services.md_paths import resolve_upload_path
    import fitz

    resolved = resolve_upload_path(file_path) or file_path
    with fitz.open(resolved) as doc:
        return int(doc.page_count)


def _parse_min_batch_size(raw: str) -> int:
    from services.system_setting_service import MINERU_BATCH_MIN, MINERU_BATCH_MAX

    try:
        n = int(str(raw).strip())
    except ValueError:
        n = int(DEFAULTS[KEY_MINERU_MIN_BATCH_INFERENCE_SIZE])
    return max(MINERU_BATCH_MIN, min(MINERU_BATCH_MAX, n))


def _parse_min_batch_floor(raw: str) -> int:
    from services.system_setting_service import MINERU_BATCH_MIN, MINERU_BATCH_MAX

    try:
        n = int(str(raw).strip())
    except ValueError:
        n = int(DEFAULTS[KEY_MINERU_MIN_BATCH_FLOOR])
    return max(MINERU_BATCH_MIN, min(MINERU_BATCH_MAX, n))


def _parse_parse_timeout_sec(raw: str) -> int:
    from services.system_setting_service import MINERU_PARSE_TIMEOUT_MIN, MINERU_PARSE_TIMEOUT_MAX

    try:
        n = int(str(raw).strip())
    except ValueError:
        n = int(DEFAULTS[KEY_MINERU_PARSE_TIMEOUT_SEC])
    return max(MINERU_PARSE_TIMEOUT_MIN, min(MINERU_PARSE_TIMEOUT_MAX, n))


def _parse_rpc_timeout_sec(raw: str) -> int:
    from services.system_setting_service import MINERU_RPC_TIMEOUT_MIN, MINERU_RPC_TIMEOUT_MAX

    try:
        n = int(float(str(raw).strip()))
    except ValueError:
        n = int(DEFAULTS[KEY_MINERU_RPC_TIMEOUT_SEC])
    return max(MINERU_RPC_TIMEOUT_MIN, min(MINERU_RPC_TIMEOUT_MAX, n))


def _parse_page_chunk_threshold(raw: str) -> int:
    from services.system_setting_service import MINERU_PAGE_CHUNK_THRESHOLD_MIN, MINERU_PAGE_CHUNK_THRESHOLD_MAX

    try:
        n = int(str(raw).strip())
    except ValueError:
        n = int(DEFAULTS[KEY_MINERU_PAGE_CHUNK_THRESHOLD])
    return max(MINERU_PAGE_CHUNK_THRESHOLD_MIN, min(MINERU_PAGE_CHUNK_THRESHOLD_MAX, n))


def _parse_page_chunk_pages(raw: str) -> int:
    from services.system_setting_service import MINERU_CHUNK_PAGES_MIN, MINERU_CHUNK_PAGES_MAX

    try:
        n = int(str(raw).strip())
    except ValueError:
        n = int(DEFAULTS[KEY_MINERU_PAGE_CHUNK_PAGES])
    return max(MINERU_CHUNK_PAGES_MIN, min(MINERU_CHUNK_PAGES_MAX, n))


def _parse_table_rotate_max_tables(raw: str) -> int:
    try:
        n = int(str(raw).strip())
    except ValueError:
        n = int(DEFAULTS[KEY_MINERU_TABLE_ROTATE_MAX_TABLES])
    return max(1, min(64, n))


def _parse_table_rotate_timeout_sec(raw: str) -> int:
    try:
        n = int(str(raw).strip())
    except ValueError:
        n = int(DEFAULTS[KEY_MINERU_TABLE_ROTATE_TIMEOUT_SEC])
    return max(1, min(300, n))
