# Copyright (c) 2026 徐泽宇
"""FileX 日志：structlog + 标准库 logging，支持结构化 JSON、控制台、滚动文件与请求关联 ID。

环境变量：
  FILEX_LOG_LEVEL        DEBUG | INFO | WARNING | ERROR（默认 INFO）
  FILEX_LOG_FORMAT       console | json（未设时：production→json，否则 console）
  FILEX_LOG_DIR          设置后写入滚动文件 {service}.log / {service}.error.log
  FILEX_LOG_MAX_BYTES    单文件上限，默认 10485760（10MB）
  FILEX_LOG_BACKUP_COUNT 保留份数，默认 10
  FILEX_SERVICE_NAME     服务名写入每条日志（默认 filex；kb-indexer 可传参覆盖）
  FILEX_LOG_HTTP         1/true 时由应用中间件记录 HTTP（并压低 uvicorn.access 噪音）
  FILEX_LOG_TIMEZONE     日志时区（默认 Asia/Shanghai）；仅 FILEX_LOG_UTC=1 时用 UTC
  FILEX_LOG_UTC          1 强制 UTC（默认关闭，使用东八区）

Authors:
    徐泽宇

Copyright:
    © 2026 徐泽宇
"""

from __future__ import annotations

import logging
import logging.handlers
import os
import sys
from datetime import datetime, timezone
from pathlib import Path
from zoneinfo import ZoneInfo

import structlog

DEFAULT_LOG_TIMEZONE = "Asia/Shanghai"

_CONFIGURED = False


def _resolve_level() -> tuple[int, str]:
    level_name = (os.environ.get("FILEX_LOG_LEVEL") or "INFO").upper()
    level = getattr(logging, level_name, logging.INFO)
    return level, level_name


def _resolve_format() -> str:
    explicit = (os.environ.get("FILEX_LOG_FORMAT") or "").strip().lower()
    if explicit in ("json", "console"):
        return explicit
    env = (os.environ.get("FILEX_ENV") or "").strip().lower()
    return "json" if env == "production" else "console"


def http_access_via_app() -> bool:
    raw = (os.environ.get("FILEX_LOG_HTTP") or "1").strip().lower()
    return raw not in ("0", "false", "no", "off")


def _use_log_utc() -> bool:
    return (os.environ.get("FILEX_LOG_UTC") or "").strip().lower() in ("1", "true", "yes")


def _log_timezone_name() -> str:
    if _use_log_utc():
        return "UTC"
    return (
        os.environ.get("FILEX_LOG_TIMEZONE")
        or os.environ.get("TZ")
        or DEFAULT_LOG_TIMEZONE
    ).strip()


def _add_log_timestamp(
    _logger: logging.Logger,
    _method_name: str,
    event_dict: structlog.types.EventDict,
) -> structlog.types.EventDict:
    """显式按配置时区写 timestamp，避免 structlog TimeStamper 在未设 TZ 时仍输出 UTC(Z)。"""
    if _use_log_utc():
        event_dict["timestamp"] = (
            datetime.now(timezone.utc).isoformat(timespec="microseconds").replace("+00:00", "Z")
        )
    else:
        tz = ZoneInfo(_log_timezone_name())
        event_dict["timestamp"] = datetime.now(tz).isoformat(timespec="microseconds")
    return event_dict


def _third_party_levels(root_level: int) -> None:
    logging.getLogger("uvicorn.error").setLevel(root_level)
    if http_access_via_app():
        logging.getLogger("uvicorn.access").setLevel(logging.WARNING)
    else:
        logging.getLogger("uvicorn.access").setLevel(logging.INFO)
    logging.getLogger("watchfiles.main").setLevel(logging.WARNING)
    logging.getLogger("alembic").setLevel(logging.WARNING)
    logging.getLogger("alembic.runtime").setLevel(logging.WARNING)
    logging.getLogger("sqlalchemy.engine").setLevel(
        logging.DEBUG if root_level <= logging.DEBUG else logging.WARNING
    )
    for name in ("pika", "pika.adapters", "pika.channel", "pika.connection", "pika.callback"):
        logging.getLogger(name).setLevel(logging.WARNING)
    logging.getLogger("httpx").setLevel(logging.WARNING)
    logging.getLogger("httpcore").setLevel(logging.WARNING)


def setup_logging(*, service_name: str | None = None) -> None:
    """初始化全局日志（幂等，可多次调用）。"""
    global _CONFIGURED

    level, level_name = _resolve_level()
    log_format = _resolve_format()
    service = (service_name or os.environ.get("FILEX_SERVICE_NAME") or "filex").strip()

    shared_processors: list[structlog.types.Processor] = [
        structlog.contextvars.merge_contextvars,
        structlog.processors.add_log_level,
        structlog.stdlib.add_logger_name,
        structlog.stdlib.PositionalArgumentsFormatter(),
        _add_log_timestamp,
        structlog.processors.StackInfoRenderer(),
        structlog.processors.format_exc_info,
        structlog.processors.UnicodeDecoder(),
    ]

    structlog.configure(
        processors=[
            *shared_processors,
            structlog.stdlib.ProcessorFormatter.wrap_for_formatter,
        ],
        logger_factory=structlog.stdlib.LoggerFactory(),
        wrapper_class=structlog.stdlib.BoundLogger,
        cache_logger_on_first_use=True,
    )

    renderer: structlog.types.Processor
    if log_format == "json":
        renderer = structlog.processors.JSONRenderer()
    else:
        renderer = structlog.dev.ConsoleRenderer(colors=sys.stderr.isatty())

    formatter = structlog.stdlib.ProcessorFormatter(
        foreign_pre_chain=shared_processors,
        processors=[
            structlog.stdlib.ProcessorFormatter.remove_processors_meta,
            renderer,
        ],
    )

    root = logging.getLogger()
    if not _CONFIGURED:
        root.handlers.clear()
    root.setLevel(level)

    if not any(
        isinstance(h, logging.StreamHandler) and getattr(h, "stream", None) is sys.stdout
        for h in root.handlers
    ):
        stdout_handler = logging.StreamHandler(sys.stdout)
        stdout_handler.setFormatter(formatter)
        root.addHandler(stdout_handler)

    log_dir_raw = (os.environ.get("FILEX_LOG_DIR") or "").strip()
    if log_dir_raw:
        log_dir = Path(log_dir_raw)
        log_dir.mkdir(parents=True, exist_ok=True)
        max_bytes = int(os.environ.get("FILEX_LOG_MAX_BYTES") or "10485760")
        backup_count = int(os.environ.get("FILEX_LOG_BACKUP_COUNT") or "10")
        log_prefix = service.replace("/", "_")
        app_log = log_dir / f"{log_prefix}.log"
        err_log = log_dir / f"{log_prefix}.error.log"

        if not any(
            isinstance(h, logging.handlers.RotatingFileHandler)
            and getattr(h, "baseFilename", "") == str(app_log.resolve())
            for h in root.handlers
        ):
            file_handler = logging.handlers.RotatingFileHandler(
                app_log,
                maxBytes=max_bytes,
                backupCount=backup_count,
                encoding="utf-8",
            )
            file_handler.setFormatter(formatter)
            root.addHandler(file_handler)

            error_handler = logging.handlers.RotatingFileHandler(
                err_log,
                maxBytes=max_bytes,
                backupCount=backup_count,
                encoding="utf-8",
            )
            error_handler.setLevel(logging.ERROR)
            error_handler.setFormatter(formatter)
            root.addHandler(error_handler)

    _third_party_levels(level)
    structlog.contextvars.clear_contextvars()
    structlog.contextvars.bind_contextvars(service=service)

    _CONFIGURED = True
    structlog.get_logger("filex").info(
        "logging_ready",
        level=level_name,
        format=log_format,
        service=service,
        log_dir=log_dir_raw or None,
        http_middleware=http_access_via_app(),
        log_timezone=_log_timezone_name(),
        log_utc=_use_log_utc(),
    )
