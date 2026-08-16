# Copyright (c) 2026 徐泽宇
"""Lightweight in-process association job worker (144)."""

from __future__ import annotations

import os
import threading
import time
import uuid
import logging

from database import SessionLocal
from sqlalchemy import text
from models.workspace import Workspace
from services.kb_association_job_service import reconcile_workspace_page, run_one_association_job

_stop = threading.Event()
_thread: threading.Thread | None = None
_lock = threading.Lock()
logger = logging.getLogger(__name__)


def _reconcile_all_workspaces() -> None:
    db = SessionLocal()
    try:
        for (workspace_id,) in db.query(Workspace.id).order_by(Workspace.id).all():
            while True:
                result = reconcile_workspace_page(db, workspace_id=int(workspace_id))
                if not result.get("has_more"):
                    break
    except Exception:
        db.rollback()
        logger.exception("kb association background reconcile failed")
    finally:
        db.close()


def _loop() -> None:
    worker_id = f"kb-association:{uuid.uuid4().hex[:12]}"
    try:
        while not _stop.is_set():
            db = SessionLocal()
            # 设置 application_name 以便 delete_file 通过 pg_stat_activity 精准定位并 terminate 连接
            db.execute(text("SET application_name = :name"), {"name": worker_id})
            did_work = False
            try:
                did_work = run_one_association_job(db, worker_id=worker_id)
            except Exception:
                logger.exception("kb association worker iteration failed worker_id=%s", worker_id)
                db.rollback()
                did_work = False
            finally:
                db.close()
            try:
                idle = float(os.environ.get("KB_ASSOCIATION_IDLE_SEC", "2"))
                if not 0 < idle < 3600:
                    idle = 2.0
            except (TypeError, ValueError):
                idle = 2.0
            _stop.wait(0.2 if did_work else idle)
    finally:
        # Publish termination only after the loop has actually exited.  A
        # later start can then safely replace this generation.
        unexpected_exit = not _stop.is_set()
        if _thread is threading.current_thread():
            globals()["_thread"] = None
        if unexpected_exit:
            logger.error("kb association worker exited unexpectedly; starting replacement")
            start_association_worker()


def association_worker_health() -> dict[str, object]:
    with _lock:
        thread = _thread
        return {
            "running": bool(thread and thread.is_alive() and not _stop.is_set()),
            "stopping": bool(_stop.is_set() and thread and thread.is_alive()),
            "thread_name": thread.name if thread else None,
        }


def start_association_worker() -> None:
    global _thread
    with _lock:
        thread = _thread
        if thread and thread.is_alive():
            if not _stop.is_set():
                return
            # A timed-out stop may leave the old loop in a database call.  Do
            # not clear the stop event and start a second consumer beside it:
            # wait for the old generation to exit, otherwise it can observe
            # the newly-cleared event and permanently steal the worker slot.
            thread.join(timeout=10)
            if thread.is_alive():
                logger.error("kb association worker restart deferred: previous loop is still alive")
                return
        _stop.clear()
        threading.Thread(
            target=_reconcile_all_workspaces,
            name="kb-association-reconcile",
            daemon=True,
        ).start()
        _thread = threading.Thread(target=_loop, name="kb-association-worker", daemon=True)
        _thread.start()


def stop_association_worker() -> None:
    global _thread
    _stop.set()
    with _lock:
        thread = _thread
        if thread and thread is not threading.current_thread():
            thread.join(timeout=10)
            if thread.is_alive():
                logger.error("kb association worker did not stop within timeout")
                return
        _thread = None
