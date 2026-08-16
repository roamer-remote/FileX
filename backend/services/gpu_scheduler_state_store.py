"""GPU 调度观测状态持久化（164 §9 可观测性）。

gpu-scheduler worker 在模型组切换/失败时把最新状态写入单行表
``gpu_scheduler_state``；管理端 admin/mq-status 读取后展示。观测写入
必须 fail-open：任何数据库异常只记录日志，绝不阻塞调度主流程。
"""

from __future__ import annotations

import logging
import threading
from datetime import datetime
from typing import Any, Callable

logger = logging.getLogger(__name__)

STATE_ROW_ID = 1


def _iso(value: datetime | None) -> str | None:
    return value.isoformat() if value is not None else None


class GpuSchedulerStateStore:
    """读写单行 GPU 调度观测状态（best-effort）。"""

    def __init__(self, session_factory: Callable[[], Any] | None = None) -> None:
        self._session_factory = session_factory
        self._lock = threading.Lock()

    def _session(self) -> Any:
        if self._session_factory is not None:
            return self._session_factory()
        from database import SessionLocal

        return SessionLocal()

    def _upsert(self, values: dict[str, Any]) -> bool:
        try:
            from models.gpu_scheduler import GpuSchedulerState
            from utils.timezone import naive_db_now

            with self._lock:
                db = self._session()
                try:
                    row = db.get(GpuSchedulerState, STATE_ROW_ID)
                    if row is None:
                        row = GpuSchedulerState(
                            id=STATE_ROW_ID,
                            **values,
                            updated_at=naive_db_now(),
                        )
                        db.add(row)
                    else:
                        for key, value in values.items():
                            setattr(row, key, value)
                    db.commit()
                    return True
                except Exception:
                    db.rollback()
                    raise
                finally:
                    db.close()
        except Exception as exc:  # 观测写入 fail-open
            logger.warning("gpu_scheduler_state upsert skipped: %s", exc)
            return False

    def record_switch_started(self, model_group: str, now: datetime | None = None) -> bool:
        from utils.timezone import naive_db_now

        return self._upsert(
            {
                "model_group": "switching",
                "model_status": "loading",
                "switch_started_at": now or naive_db_now(),
                "switch_finished_at": None,
                "last_switch_duration_ms": None,
            }
        )

    def record_switch_finished(
        self, model_group: str, duration_ms: int, now: datetime | None = None
    ) -> bool:
        from utils.timezone import naive_db_now

        return self._upsert(
            {
                "model_group": str(model_group),
                "model_status": "running",
                "switch_finished_at": now or naive_db_now(),
                "last_switch_duration_ms": int(duration_ms),
            }
        )

    def record_failure(self, kind: str, reason: str, now: datetime | None = None) -> bool:
        from utils.timezone import naive_db_now

        return self._upsert(
            {
                "model_status": "failed",
                "last_failure_kind": str(kind),
                "last_failure_reason": str(reason)[:2000],
                "last_failure_at": now or naive_db_now(),
            }
        )

    def read_state(self, db: Any | None = None) -> dict[str, Any]:
        try:
            from models.gpu_scheduler import GpuSchedulerState

            own_session = db is None
            if db is None:
                db = self._session()
            try:
                row = db.get(GpuSchedulerState, STATE_ROW_ID)
                if row is None:
                    return {
                        "model_group": "none",
                        "model_status": "unloaded",
                        "switch_started_at": None,
                        "switch_finished_at": None,
                        "last_switch_duration_ms": None,
                        "last_failure_kind": None,
                        "last_failure_reason": None,
                        "last_failure_at": None,
                        "updated_at": None,
                    }
                return {
                    "model_group": row.model_group,
                    "model_status": row.model_status,
                    "switch_started_at": _iso(row.switch_started_at),
                    "switch_finished_at": _iso(row.switch_finished_at),
                    "last_switch_duration_ms": row.last_switch_duration_ms,
                    "last_failure_kind": row.last_failure_kind,
                    "last_failure_reason": row.last_failure_reason,
                    "last_failure_at": _iso(row.last_failure_at),
                    "updated_at": _iso(row.updated_at),
                }
            finally:
                if own_session:
                    db.close()
        except Exception as exc:
            logger.warning("gpu_scheduler_state read skipped: %s", exc)
            return {}
