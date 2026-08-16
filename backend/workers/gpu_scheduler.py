# Copyright (c) 2026 徐泽宇
"""GPU scheduler worker：dispatch loop + filex.gpu.* consumer（164 §6）。

本 worker 是唯一 GPU owner：
- ``GpuSchedulerLoop.run_forever`` 线程按 tick 为每个 gpu_id 取得 fresh lease
  并把 queued route 发布到 ``filex.gpu.*``（先 commit 后 publish）；
- 主线程运行 scheduler 专属 consumer，claim 后复用 extract/post 执行路径，
  成功/终态后释放 lease。

``GPU_SCHEDULER_ENABLED=false`` 时拒绝启动（fail-closed），防止与旧
extract/post consumer 并行执行 GPU。
"""

from __future__ import annotations

import threading

import structlog

from config import GPU_SCHEDULER_ENABLED, RABBITMQ_URL
from database import SessionLocal, init_db
from logging_setup import setup_logging
from messaging.gpu_scheduler_consumer import run_consumer
from services.gpu_scheduler_loop import GpuSchedulerLoop

setup_logging(service_name="gpu-scheduler")
logger = structlog.get_logger("gpu_scheduler")


def main() -> None:
    if not GPU_SCHEDULER_ENABLED:
        raise SystemExit(
            "GPU_SCHEDULER_ENABLED=false: gpu-scheduler worker 拒绝启动，"
            "避免与旧 extract/post consumer 并行执行 GPU"
        )
    if not RABBITMQ_URL:
        raise SystemExit("RABBITMQ_URL 未设置，无法启动 gpu-scheduler")

    init_db(migrate=False)

    _recover_stuck_routes_on_startup()

    loop_thread = threading.Thread(
        target=GpuSchedulerLoop().run_forever,
        name="gpu-scheduler-loop",
        daemon=True,
    )
    loop_thread.start()
    logger.info("gpu-scheduler loop started (tick dispatch + heartbeat)")
    run_consumer()


def _recover_stuck_routes_on_startup() -> None:
    """启动 loop 线程前先回收上一进程留下的孤儿 route/lease。

    重启后的新进程不持有旧 fencing token，不会续期旧 lease；这里先按
    lease 心跳门控回收终态/waiting_gpu/心跳停止的 executing/published route，
    避免新 loop 被陈旧 lease 阻塞或把卡死状态带进下一轮。
    """
    from services.gpu_scheduler_loop import GpuSchedulerLoop
    from utils.timezone import naive_db_now

    db = SessionLocal()
    try:
        loop = GpuSchedulerLoop()
        recovered = loop._recover_stuck_executing_routes(db, now=naive_db_now())
        if recovered:
            logger.info("gpu-scheduler startup recovered %s orphan route(s)/lease(s)", recovered)
    except Exception:
        logger.exception("gpu-scheduler startup recovery failed")
        db.rollback()
    finally:
        db.close()


if __name__ == "__main__":
    main()
