# Copyright (c) 2026 徐泽宇
"""Background MQ metrics watcher: 周期性向 WebSocket 推送 MQ 状态（含心跳刷新 updated_at）。

Authors:
    徐泽宇

Copyright:
    © 2026 徐泽宇
"""

from __future__ import annotations

import logging
import threading

from config import MQ_STATUS_WATCH_INTERVAL_SEC, RABBITMQ_URL
from messaging.mq_ws_manager import mq_ws_manager
from services.rabbitmq_status_service import mq_status_global_fingerprint

logger = logging.getLogger(__name__)

_stop = threading.Event()
_thread: threading.Thread | None = None
_wake = threading.Event()
_lock = threading.Lock()
_last_fingerprint: str | None = None


def note_status_sent_global() -> None:
    global _last_fingerprint
    with _lock:
        _last_fingerprint = mq_status_global_fingerprint()


def request_refresh() -> None:
    global _last_fingerprint
    with _lock:
        _last_fingerprint = None
    _wake.set()


def _poll_and_broadcast(*, heartbeat: bool = False) -> None:
    """heartbeat=True 时即使指标未变也推送（刷新 updated_at，供界面「上次更新」）。"""
    global _last_fingerprint
    if not mq_ws_manager.has_connections():
        return
    fp = mq_status_global_fingerprint()
    with _lock:
        if not heartbeat and fp == _last_fingerprint:
            return
        _last_fingerprint = fp
    mq_ws_manager.broadcast_personalized_sync()


def _run() -> None:
    logger.info("mq status watcher started (interval=%ss)", MQ_STATUS_WATCH_INTERVAL_SEC)
    while not _stop.is_set():
        try:
            if mq_ws_manager.has_connections() and RABBITMQ_URL:
                _poll_and_broadcast(heartbeat=True)
        except Exception:
            logger.exception("mq status watcher poll error")
        if _wake.wait(timeout=MQ_STATUS_WATCH_INTERVAL_SEC):
            _wake.clear()
            try:
                if mq_ws_manager.has_connections() and RABBITMQ_URL:
                    _poll_and_broadcast(heartbeat=True)
            except Exception:
                logger.exception("mq status watcher refresh poll error")
    logger.info("mq status watcher stopped")


def start_mq_status_watcher() -> None:
    global _thread
    if _thread and _thread.is_alive():
        return
    _stop.clear()
    _thread = threading.Thread(target=_run, name="mq-status-watcher", daemon=True)
    _thread.start()


def stop_mq_status_watcher() -> None:
    _stop.set()
    _wake.set()
    if _thread:
        _thread.join(timeout=5)
