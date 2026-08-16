"""Runtime lifecycle gate for GPU model handover in the MinerU sidecar."""

from __future__ import annotations

import threading

_LOCK = threading.Lock()
_ACTIVE_JOBS: dict[str, dict[str, str]] = {}


def begin_execution(*, gpu_lease_id: str, fencing_token: str, gpu_job_id: str) -> None:
    """Record one active authorized MinerU execution round.

    gpu-scheduler 崩溃后本进程可能仍在执行旧轮；调度重启后的 watchdog 通过
    /lifecycle/status 读取本状态确认旧轮是否已退出（164 §5.5），不能依赖
    nvidia-smi 进程采样（本进程启动即加载 torch/CUDA，永远存在）。
    """
    key = str(gpu_job_id or gpu_lease_id)
    with _LOCK:
        _ACTIVE_JOBS[key] = {
            "gpu_lease_id": str(gpu_lease_id),
            "fencing_token": str(fencing_token),
            "gpu_job_id": str(gpu_job_id),
        }


def end_execution(gpu_job_id: str) -> None:
    with _LOCK:
        _ACTIVE_JOBS.pop(str(gpu_job_id), None)


def active_executions() -> int:
    with _LOCK:
        return len(_ACTIVE_JOBS)


def active_jobs() -> list[dict[str, str]]:
    """Return sorted active round contexts for the GPU watchdog probe."""
    with _LOCK:
        return sorted(
            _ACTIVE_JOBS.values(),
            key=lambda item: item["gpu_job_id"],
        )
