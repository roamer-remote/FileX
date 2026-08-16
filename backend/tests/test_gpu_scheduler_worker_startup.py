# Copyright (c) 2026 徐泽宇
"""gpu-scheduler worker 启动路径回归（164 T-9 发布暴露：SessionLocal 未导入）。"""

from __future__ import annotations

from unittest.mock import patch


def test_worker_module_imports_session_local() -> None:
    """worker 模块必须可直接导入并引用 database.SessionLocal，杜绝启动 NameError。"""
    from workers import gpu_scheduler

    assert gpu_scheduler.SessionLocal is not None


def test_recover_stuck_routes_on_startup_runs_with_fake_session() -> None:
    """启动恢复函数在正常/异常路径都不抛 NameError，并正确关闭会话。"""
    from workers.gpu_scheduler import _recover_stuck_routes_on_startup

    class FakeSession:
        def __init__(self) -> None:
            self.closed = False

        def rollback(self) -> None:
            pass

        def close(self) -> None:
            self.closed = True

    session = FakeSession()
    with patch("workers.gpu_scheduler.SessionLocal", return_value=session), patch(
        "services.gpu_scheduler_loop.GpuSchedulerLoop"
    ) as loop_cls:
        loop_cls.return_value._recover_stuck_executing_routes.return_value = 0
        _recover_stuck_routes_on_startup()
    assert session.closed
