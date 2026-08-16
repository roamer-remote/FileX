"""GPU 调度观测状态存储测试（164 §9）。"""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import text
from sqlalchemy.orm import sessionmaker

from services.gpu_scheduler_state_store import GpuSchedulerStateStore


def _make_store(engine) -> GpuSchedulerStateStore:
    return GpuSchedulerStateStore(session_factory=sessionmaker(bind=engine))


def _clear_state(engine) -> None:
    with engine.begin() as conn:
        conn.execute(text("DELETE FROM gpu_scheduler_state"))


def test_store_records_switch_start_finish_and_failure(engine, db_session):
    _clear_state(engine)
    store = _make_store(engine)
    t0 = datetime(2026, 8, 1, 10, 0, 0)

    assert store.record_switch_started("mineru", now=t0)
    state = store.read_state()
    assert state["model_group"] == "switching"
    assert state["model_status"] == "loading"
    assert state["switch_started_at"] is not None

    assert store.record_switch_finished("mineru", 1234, now=datetime(2026, 8, 1, 10, 0, 2))
    state = store.read_state()
    assert state["model_group"] == "mineru"
    assert state["model_status"] == "running"
    assert state["last_switch_duration_ms"] == 1234
    assert state["switch_finished_at"] is not None

    assert store.record_failure("oom", "CUDA out of memory", now=datetime(2026, 8, 1, 10, 0, 3))
    state = store.read_state()
    assert state["model_status"] == "failed"
    assert state["last_failure_kind"] == "oom"
    assert state["last_failure_reason"] == "CUDA out of memory"
    assert state["last_failure_at"] is not None


def test_store_upsert_keeps_single_row_and_reason_truncated(engine, db_session):
    _clear_state(engine)
    store = _make_store(engine)

    store.record_switch_started("raptor")
    store.record_switch_finished("raptor", 999)
    store.record_failure("load", "x" * 5000)

    with engine.begin() as conn:
        count = conn.execute(text("SELECT COUNT(*) FROM gpu_scheduler_state")).scalar()
    assert count == 1
    state = store.read_state()
    assert len(state["last_failure_reason"]) == 2000
