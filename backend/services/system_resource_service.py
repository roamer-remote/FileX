# Copyright (c) 2026 徐泽宇
"""Lightweight host CPU/GPU resource snapshot for MQ monitor."""

from __future__ import annotations

import os
import subprocess
import threading
import time
from copy import deepcopy
from typing import Any

from services.gpu_high_mode import (
    HIGH_DEGRADATION_RUNTIME,
    combined_peak_reserved_mb,
    get_high_mode_tracker,
)

_PROC_STAT_LOCK = threading.Lock()
_LAST_PROC_STAT: tuple[int, int] | None = None
_NVIDIA_SMI_TIMEOUT_SEC = 0.35
_RESOURCE_CACHE_TTL_SEC = 2.0
_RESOURCE_CACHE_LOCK = threading.Lock()
_RESOURCE_CACHE: tuple[float, dict[str, Any]] | None = None

GPU_CAPABILITY_HIGH = "high"
GPU_CAPABILITY_MEDIUM = "medium"
GPU_CAPABILITY_LOW = "low"
GPU_CAPABILITY_CPU_ONLY = "cpu_only"

GPU_REASON_NO_CUDA = "cpu_only_no_cuda"
GPU_REASON_PROBE_FAILED = "cpu_only_probe_failed"
GPU_REASON_INSUFFICIENT_MEMORY = "cpu_only_insufficient_memory"
GPU_DEGRADATION_HIGH_WARMUP_REQUIRED = "high_warmup_required"
GPU_PROCESS_PROBE_OK = "ok"
GPU_PROCESS_PROBE_FAILED = "failed"
GPU_PROCESS_PROBE_NOT_RUN = "not_run"


def _read_proc_stat_totals() -> tuple[int, int] | None:
    """Return (idle, total) jiffies from /proc/stat when available."""
    try:
        with open("/proc/stat", "r", encoding="utf-8") as f:
            first = f.readline().strip()
    except OSError:
        return None
    parts = first.split()
    if not parts or parts[0] != "cpu":
        return None
    try:
        values = [int(v) for v in parts[1:]]
    except ValueError:
        return None
    if len(values) < 4:
        return None
    idle = values[3] + (values[4] if len(values) > 4 else 0)
    return idle, sum(values)


def _cpu_percent_from_proc_samples(previous: tuple[int, int], current: tuple[int, int]) -> float | None:
    prev_idle, prev_total = previous
    idle, total = current
    total_delta = total - prev_total
    idle_delta = idle - prev_idle
    if total_delta <= 0:
        return None
    pct = (1 - idle_delta / total_delta) * 100
    return round(max(0.0, min(100.0, pct)), 1)


def _loadavg_cpu_percent() -> float | None:
    try:
        load1, _load5, _load15 = os.getloadavg()
    except (AttributeError, OSError):
        return None
    cpu_count = os.cpu_count() or 1
    return round(max(0.0, min(100.0, load1 / cpu_count * 100)), 1)


def _cpu_percent() -> float | None:
    global _LAST_PROC_STAT
    current = _read_proc_stat_totals()
    if current is None:
        return _loadavg_cpu_percent()
    with _PROC_STAT_LOCK:
        previous = _LAST_PROC_STAT
        _LAST_PROC_STAT = current
    if previous is None:
        return _loadavg_cpu_percent()
    pct = _cpu_percent_from_proc_samples(previous, current)
    return pct if pct is not None else _loadavg_cpu_percent()


def _parse_nvidia_smi(output: str) -> dict[str, Any]:
    line = next((ln.strip() for ln in output.splitlines() if ln.strip()), "")
    if not line:
        return {"available": False, "capability": GPU_CAPABILITY_CPU_ONLY, "reason_code": GPU_REASON_PROBE_FAILED}
    parts = [part.strip() for part in line.split(",")]
    if len(parts) < 6:
        return {"available": False, "capability": GPU_CAPABILITY_CPU_ONLY, "reason_code": GPU_REASON_PROBE_FAILED}
    try:
        gpu_index = int(parts[0])
        util_percent = float(parts[2])
        memory_used_mb = int(float(parts[3]))
        memory_total_mb = int(float(parts[4]))
        memory_free_mb = int(float(parts[5]))
    except ValueError:
        return {"available": False, "capability": GPU_CAPABILITY_CPU_ONLY, "reason_code": GPU_REASON_PROBE_FAILED}
    snapshot = {
        "available": True,
        "gpu_index": gpu_index,
        "name": parts[1],
        "util_percent": round(max(0.0, min(100.0, util_percent)), 1),
        "memory_used_mb": max(0, memory_used_mb),
        "memory_total_mb": max(0, memory_total_mb),
        "memory_free_mb": max(0, memory_free_mb),
    }
    if len(parts) >= 7 and parts[6] not in {"N/A", "[N/A]", ""}:
        snapshot["compute_capability"] = parts[6]
    return _with_gpu_capability(snapshot)


def _parse_nvidia_processes(output: str) -> list[dict[str, Any]]:
    processes: list[dict[str, Any]] = []
    for line in output.splitlines():
        parts = [part.strip() for part in line.split(",")]
        if len(parts) < 3:
            continue
        try:
            processes.append({"pid": int(parts[0]), "name": parts[1], "memory_used_mb": int(float(parts[2]))})
        except ValueError:
            continue
    return processes


def _cuda_probe() -> dict[str, Any]:
    """Probe the runtime that will actually execute torch CUDA workloads."""
    try:
        import torch
    except (ImportError, OSError):
        return {"available": False, "reason_code": GPU_REASON_PROBE_FAILED}
    try:
        if not torch.cuda.is_available():
            return {"available": False, "reason_code": GPU_REASON_PROBE_FAILED}
        index = int(torch.cuda.current_device())
        props = torch.cuda.get_device_properties(index)
        return {
            "available": True,
            "gpu_index": index,
            "compute_capability": f"{props.major}.{props.minor}",
        }
    except (RuntimeError, AttributeError, TypeError, ValueError):
        return {"available": False, "reason_code": GPU_REASON_PROBE_FAILED}


def _with_gpu_capability(snapshot: dict[str, Any]) -> dict[str, Any]:
    """Attach the canonical capability enum and CPU-only reason code."""
    if not snapshot.get("available"):
        snapshot.setdefault("capability", GPU_CAPABILITY_CPU_ONLY)
        snapshot.setdefault("reason_code", GPU_REASON_PROBE_FAILED)
        snapshot["gpu_usable"] = False
        return snapshot
    total_mb = snapshot.get("memory_total_mb")
    if not isinstance(total_mb, int) or total_mb < 8192:
        snapshot["capability"] = GPU_CAPABILITY_CPU_ONLY
        snapshot["reason_code"] = GPU_REASON_INSUFFICIENT_MEMORY
    elif total_mb < 16384:
        snapshot["capability"] = GPU_CAPABILITY_LOW
        snapshot["reason_code"] = None
    elif total_mb < 32768:
        snapshot["capability"] = GPU_CAPABILITY_MEDIUM
        snapshot["reason_code"] = None
    else:
        safe_margin_mb = max(int(total_mb * 0.15), 2048)
        snapshot["safe_margin_mb"] = safe_margin_mb
        snapshot["high_eligible"] = bool(
            snapshot.get("warmup_windows_ok")
            and isinstance(snapshot.get("combined_peak_reserved_mb"), int)
            and isinstance(snapshot.get("memory_free_mb"), int)
            and snapshot.get("process_probe_status") == GPU_PROCESS_PROBE_OK
            and snapshot["memory_free_mb"] >= safe_margin_mb + snapshot["combined_peak_reserved_mb"]
        )
        snapshot["capability"] = GPU_CAPABILITY_HIGH if snapshot["high_eligible"] else GPU_CAPABILITY_MEDIUM
        snapshot["reason_code"] = None
        if not snapshot["high_eligible"]:
            snapshot["degradation_reason"] = GPU_DEGRADATION_HIGH_WARMUP_REQUIRED
    snapshot["gpu_usable"] = snapshot["capability"] != GPU_CAPABILITY_CPU_ONLY
    return snapshot


def _gpu_snapshot() -> dict[str, Any]:
    try:
        completed = subprocess.run(
            [
                "nvidia-smi",
                "--query-gpu=index,name,utilization.gpu,memory.used,memory.total,memory.free,compute_cap",
                "--format=csv,noheader,nounits",
            ],
            check=True,
            capture_output=True,
            text=True,
            timeout=_NVIDIA_SMI_TIMEOUT_SEC,
        )
    except FileNotFoundError:
        return {"available": False, "gpu_usable": False, "capability": GPU_CAPABILITY_CPU_ONLY, "reason_code": GPU_REASON_NO_CUDA}
    except (OSError, subprocess.SubprocessError):
        return {"available": False, "gpu_usable": False, "capability": GPU_CAPABILITY_CPU_ONLY, "reason_code": GPU_REASON_PROBE_FAILED}
    snapshot = _parse_nvidia_smi(completed.stdout)
    if not snapshot.get("available"):
        return snapshot
    cuda = _cuda_probe()
    if not cuda.get("available"):
        snapshot["gpu_usable"] = False
        snapshot["capability"] = GPU_CAPABILITY_CPU_ONLY
        snapshot["reason_code"] = cuda.get("reason_code", GPU_REASON_PROBE_FAILED)
        return snapshot
    snapshot.update({key: value for key, value in cuda.items() if key != "available"})
    try:
        process_result = subprocess.run(
            [
                "nvidia-smi",
                "--query-compute-apps=pid,process_name,used_memory",
                "--format=csv,noheader,nounits",
            ],
            check=True,
            capture_output=True,
            text=True,
            timeout=_NVIDIA_SMI_TIMEOUT_SEC,
        )
        snapshot["processes"] = _parse_nvidia_processes(process_result.stdout)
        snapshot["process_probe_status"] = GPU_PROCESS_PROBE_OK
    except (OSError, subprocess.SubprocessError):
        snapshot["processes"] = []
        snapshot["process_probe_status"] = GPU_PROCESS_PROBE_FAILED
    snapshot["combined_peak_reserved_mb"] = combined_peak_reserved_mb()
    tracker = get_high_mode_tracker()
    tracker.record_sample(
        memory_free_mb=int(snapshot.get("memory_free_mb") or 0),
        total_memory_mb=int(snapshot.get("memory_total_mb") or 0),
        combined_peak_reserved_mb=snapshot["combined_peak_reserved_mb"],
        process_probe_ok=snapshot.get("process_probe_status") == GPU_PROCESS_PROBE_OK,
    )
    snapshot["warmup_windows_ok"] = tracker.warmup_windows_ok
    snapshot = _with_gpu_capability(snapshot)
    if not tracker.high_eligible and tracker.degradation_reason == HIGH_DEGRADATION_RUNTIME:
        # 运行中连续 2 次不足已降级：原因码覆盖为运行中显存不足。
        snapshot["degradation_reason"] = HIGH_DEGRADATION_RUNTIME
    return snapshot


def reset_system_resource_cache() -> None:
    global _RESOURCE_CACHE
    with _RESOURCE_CACHE_LOCK:
        _RESOURCE_CACHE = None


def _collect_system_resources_uncached() -> dict[str, Any]:
    return {
        "cpu_percent": _cpu_percent(),
        "gpu": _gpu_snapshot(),
    }


def collect_system_resources(*, now: float | None = None) -> dict[str, Any]:
    global _RESOURCE_CACHE
    sampled_at = time.monotonic() if now is None else now
    with _RESOURCE_CACHE_LOCK:
        cached = _RESOURCE_CACHE
        if cached is not None and sampled_at - cached[0] < _RESOURCE_CACHE_TTL_SEC:
            return deepcopy(cached[1])

    snapshot = _collect_system_resources_uncached()
    with _RESOURCE_CACHE_LOCK:
        _RESOURCE_CACHE = (sampled_at, deepcopy(snapshot))
    return snapshot
