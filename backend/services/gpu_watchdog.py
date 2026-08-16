# Copyright (c) 2026 徐泽宇
"""GPU watchdog：确认旧执行轮已退出（164 §5.5/SC-164-007）。

规格要求执行中的 lease 不因 TTL/heartbeat 停止自动回收：新 owner 只能在
收到 ``release_ack``，或 watchdog 连续两次间隔 5 秒的“旧轮已退出”确认后才
能接管。本模块提供该确认的权威探测，探测失败一律按“无法确认”（busy）处理，
保持 fail-closed。

WHB 真机（T-9）实测表明 nvidia-smi 的 “compute 进程为空”在该部署不可达：
- ``OLLAMA_KEEP_ALIVE=-1`` 让 llama-server 常驻（约 6.8GiB）；
- MinerU sidecar 启动即加载 torch/CUDA，uvicorn 进程常驻（约 120MiB）。
两者都是常驻服务进程而非执行轮进程，因此探针改为查询执行轮权威状态：
- MinerU：轮次真实跑在 filex-mineru sidecar 进程内；scheduler 崩溃后
  sidecar 可能仍在执行，必须由 sidecar 报告其 active execution 已结束；
- RAPTOR：轮次由 gpu-scheduler 进程内 consumer 执行（dispatch loop 与
  consumer 同进程、同容器），心跳停止即该进程已死，轮次不可能存活。
"""

from __future__ import annotations

import logging
from typing import Any

import httpx

logger = logging.getLogger(__name__)

SIDECAR_STATUS_TIMEOUT_SEC = 5.0


def _sidecar_status_url() -> str:
    from config import KB_EXTRACT_MINERU_URL

    base = (KB_EXTRACT_MINERU_URL or "").strip().rstrip("/")
    return f"{base}/lifecycle/status" if base else ""


def _fetch_sidecar_status(url: str) -> dict[str, Any]:
    with httpx.Client(
        timeout=httpx.Timeout(SIDECAR_STATUS_TIMEOUT_SEC, connect=3.0)
    ) as client:
        response = client.get(url)
        response.raise_for_status()
        body = response.json()
    if not isinstance(body, dict):
        raise ValueError("sidecar status response is not an object")
    return body


def gpu_round_idle(*, job_kind: str, lease: Any) -> bool:
    """Return True only when the old execution round is confirmed exited.

    - sidecar 不可达 / 超时 / 非 200 / 响应结构非法：无法确认，返回 False。
    - sidecar 仍有任意 active 执行：GPU 被执行轮占用（严格串行），返回 False。
    - RAPTOR 轮次与本进程共存亡；sidecar 无 active 执行即旧轮已退出。
    ``lease`` 保留为调用契约（日志与后续按 lease 过滤的扩展点）。
    """
    url = _sidecar_status_url()
    if not url:
        logger.warning("gpu watchdog sidecar status url unset; treating GPU as busy")
        return False
    try:
        body = _fetch_sidecar_status(url)
    except Exception as exc:
        logger.warning(
            "gpu watchdog sidecar status probe failed; treating GPU as busy: %s", exc
        )
        return False
    active = body.get("active_jobs")
    if not isinstance(active, list) or active:
        # 响应非法或仍有执行轮：不得确认。
        return False
    lease_id = getattr(lease, "id", None)
    logger.info(
        "gpu watchdog confirmed old round exited job_kind=%s lease_id=%s",
        job_kind,
        lease_id,
    )
    return True
