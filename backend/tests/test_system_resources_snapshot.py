# Copyright (c) 2026 徐泽宇
"""System resource snapshot tests for MQ factory monitor."""

from __future__ import annotations

import subprocess

from services.system_resource_service import (
    _cpu_percent_from_proc_samples,
    _parse_nvidia_smi,
    collect_system_resources,
    reset_system_resource_cache,
)


def test_cpu_percent_from_proc_samples():
    previous = (100, 1000)
    current = (150, 1100)

    assert _cpu_percent_from_proc_samples(previous, current) == 50.0


def test_parse_nvidia_smi_snapshot():
    payload = _parse_nvidia_smi("0, NVIDIA RTX 4090, 86, 18841, 24564, 5723, 8.9\n")

    assert payload == {
        "available": True,
        "gpu_index": 0,
        "name": "NVIDIA RTX 4090",
        "util_percent": 86.0,
        "memory_used_mb": 18841,
        "memory_total_mb": 24564,
        "memory_free_mb": 5723,
        "compute_capability": "8.9",
        "capability": "medium",
        "reason_code": None,
        "gpu_usable": True,
    }


def test_parse_nvidia_smi_processes_and_low_free_high_gpu(monkeypatch):
    from services import system_resource_service as resources

    monkeypatch.setattr(resources, "_cuda_probe", lambda: {"available": True, "gpu_index": 0})
    monkeypatch.setattr(
        resources.subprocess,
        "run",
        lambda *args, **kwargs: type("Result", (), {"stdout": "0, NVIDIA RTX 4090, 86, 39000, 40960, 1000, 8.9\n"})(),
    )
    payload = resources._gpu_snapshot()

    assert payload["capability"] == "medium"
    assert payload["high_eligible"] is False
    assert payload["degradation_reason"] == "high_warmup_required"
    assert payload["process_probe_status"] == "ok"


def test_process_probe_failure_is_explicit_and_blocks_high():
    from services.system_resource_service import _with_gpu_capability

    payload = _with_gpu_capability(
        {
            "available": True,
            "memory_total_mb": 40960,
            "memory_free_mb": 30000,
            "warmup_windows_ok": True,
            "combined_peak_reserved_mb": 4000,
            "process_probe_status": "failed",
        }
    )

    assert payload["process_probe_status"] == "failed"
    assert payload["high_eligible"] is False
    assert payload["capability"] == "medium"


def test_process_probe_failure_is_recorded_by_gpu_snapshot(monkeypatch):
    from services import system_resource_service as resources

    calls = 0

    def _run(*args, **kwargs):
        nonlocal calls
        calls += 1
        if calls == 1:
            return type("Result", (), {"stdout": "0, NVIDIA RTX 4090, 10, 1000, 40960, 39960, 8.9\n"})()
        raise subprocess.SubprocessError("process query failed")

    monkeypatch.setattr(resources, "_cuda_probe", lambda: {"available": True, "gpu_index": 0})
    monkeypatch.setattr(resources.subprocess, "run", _run)

    payload = resources._gpu_snapshot()

    assert payload["process_probe_status"] == "failed"
    assert payload["processes"] == []
    assert payload["high_eligible"] is False
    assert payload["capability"] == "medium"


def test_gpu_is_not_usable_when_cuda_probe_fails(monkeypatch):
    from services import system_resource_service as resources

    monkeypatch.setattr(resources, "_cuda_probe", lambda: {"available": False, "reason_code": "cpu_only_probe_failed"})
    monkeypatch.setattr(
        resources.subprocess,
        "run",
        lambda *args, **kwargs: type("Result", (), {"stdout": "0, NVIDIA RTX 4090, 86, 18841, 24564, 5723, 8.9\n"})(),
    )

    payload = resources._gpu_snapshot()

    assert payload["available"] is True
    assert payload["gpu_usable"] is False
    assert payload["capability"] == "cpu_only"
    assert payload["reason_code"] == "cpu_only_probe_failed"


def test_parse_nvidia_smi_processes():
    from services.system_resource_service import _parse_nvidia_processes

    assert _parse_nvidia_processes("123, ollama, 4096\n456, python, 2048\n") == [
        {"pid": 123, "name": "ollama", "memory_used_mb": 4096},
        {"pid": 456, "name": "python", "memory_used_mb": 2048},
    ]


def test_gpu_capability_uses_cpu_only_reason_for_small_cuda_device():
    payload = _parse_nvidia_smi("0, NVIDIA GTX 1080, 12, 2048, 8191, 6143, 6.1\n")

    assert payload["capability"] == "cpu_only"
    assert payload["reason_code"] == "cpu_only_insufficient_memory"


def test_gpu_capability_uses_no_cuda_reason_when_nvidia_smi_is_missing(monkeypatch):
    reset_system_resource_cache()

    def _raise(*_args, **_kwargs):
        raise FileNotFoundError("nvidia-smi")

    monkeypatch.setattr("services.system_resource_service.subprocess.run", _raise)

    snapshot = collect_system_resources()

    assert snapshot["gpu"] == {
        "available": False,
        "gpu_usable": False,
        "capability": "cpu_only",
        "reason_code": "cpu_only_no_cuda",
    }
    reset_system_resource_cache()


def test_collect_system_resources_gpu_unavailable_on_nvidia_smi_failure(monkeypatch):
    reset_system_resource_cache()
    monkeypatch.setattr("services.system_resource_service._read_proc_stat_totals", lambda: None)
    monkeypatch.setattr("services.system_resource_service._loadavg_cpu_percent", lambda: 12.5)

    def _raise(*_args, **_kwargs):
        raise subprocess.TimeoutExpired(cmd="nvidia-smi", timeout=0.35)

    monkeypatch.setattr("services.system_resource_service.subprocess.run", _raise)

    snapshot = collect_system_resources()

    assert snapshot["cpu_percent"] == 12.5
    assert snapshot["gpu"] == {
        "available": False,
        "gpu_usable": False,
        "capability": "cpu_only",
        "reason_code": "cpu_only_probe_failed",
    }
    reset_system_resource_cache()


def test_collect_system_resources_uses_ttl_cache(monkeypatch):
    reset_system_resource_cache()
    calls = {"cpu": 0, "gpu": 0}

    def _cpu():
        calls["cpu"] += 1
        return 24.0

    def _gpu():
        calls["gpu"] += 1
        return {"available": False, "gpu_usable": False, "capability": "cpu_only", "reason_code": "cpu_only_no_cuda"}

    monkeypatch.setattr("services.system_resource_service._cpu_percent", _cpu)
    monkeypatch.setattr("services.system_resource_service._gpu_snapshot", _gpu)

    first = collect_system_resources(now=10.0)
    second = collect_system_resources(now=11.0)

    assert first == {
        "cpu_percent": 24.0,
        "gpu": {"available": False, "gpu_usable": False, "capability": "cpu_only", "reason_code": "cpu_only_no_cuda"},
    }
    assert second == first
    assert calls == {"cpu": 1, "gpu": 1}
    reset_system_resource_cache()
