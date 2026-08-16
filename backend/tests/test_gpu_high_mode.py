# Copyright (c) 2026 徐泽宇
"""High 档常驻判定测试（164 §5.4/§11.1/SC-164-008）。"""

from __future__ import annotations

from datetime import datetime

import pytest

from services.gpu_high_mode import (
    HIGH_DEGRADATION_RUNTIME,
    HIGH_DEGRADATION_WARMUP,
    HIGH_RUNTIME_SAMPLE_SEC,
    HIGH_WARMUP_SAMPLE_SEC,
    HIGH_WARMUP_WINDOW_SEC,
    HIGH_WARMUP_WINDOW_MIN_SAMPLES,
    HIGH_WARMUP_WINDOWS_REQUIRED,
    HighModeTracker,
    combined_peak_reserved_mb,
    safe_margin_mb,
)
from services.gpu_scheduler_loop import GpuSchedulerLoop


class _FakeClock:
    def __init__(self) -> None:
        self.t = 0.0

    def __call__(self) -> float:
        return self.t

    def advance(self, seconds: float) -> None:
        self.t += seconds


def _peak_reserved() -> int:
    return combined_peak_reserved_mb()


def _sample(
    tracker: HighModeTracker,
    clock: _FakeClock,
    *,
    free_mb: int,
    total_mb: int = 40960,
    probe_ok: bool = True,
    peak_mb: int | None = None,
) -> bool:
    return tracker.record_sample(
        memory_free_mb=free_mb,
        total_memory_mb=total_mb,
        combined_peak_reserved_mb=peak_mb if peak_mb is not None else _peak_reserved(),
        process_probe_ok=probe_ok,
    )


def _run_warmup(tracker: HighModeTracker, clock: _FakeClock) -> None:
    """按规格节奏跑完连续 3 个 10 秒窗口（每秒一采样）。"""
    for _ in range(10 * HIGH_WARMUP_WINDOWS_REQUIRED + 3):
        clock.advance(HIGH_WARMUP_SAMPLE_SEC)
        _sample(tracker, clock, free_mb=30000)


def test_safe_margin_formula_uses_max_15_percent_and_2gib():
    assert safe_margin_mb(40960) == 6144
    assert safe_margin_mb(8192) == 2048
    assert safe_margin_mb(2048) == 2048


def test_combined_peak_reserved_aggregates_both_groups_and_budget():
    assert _peak_reserved() > 0
    assert _peak_reserved() >= 7168 + 6144 + 1024


def test_high_requires_three_consecutive_warmup_windows(monkeypatch):
    monkeypatch.setattr("services.gpu_high_mode.GPU_HIGH_RAPTOR_PEAK_RESERVED_MB", 7168)
    monkeypatch.setattr("services.gpu_high_mode.GPU_HIGH_MINERU_PEAK_RESERVED_MB", 6144)
    monkeypatch.setattr("services.gpu_high_mode.GPU_HIGH_KV_CACHE_BUDGET_MB", 1024)
    clock = _FakeClock()
    tracker = HighModeTracker(now=clock)

    # 前两个窗口不足（free 低于 safe+peak），不得启用 High。
    for _ in range(10 * (HIGH_WARMUP_WINDOWS_REQUIRED - 1) + 3):
        clock.advance(HIGH_WARMUP_SAMPLE_SEC)
        _sample(tracker, clock, free_mb=1000)
    assert tracker.high_eligible is False
    assert tracker.warmup_windows_ok is False

    # 之后连续 3 个完整窗口满足才启用。
    _run_warmup(tracker, clock)
    assert tracker.high_eligible is True
    assert tracker.degradation_reason is None


def test_sparse_warmup_samples_never_enable_high():
    """生产 tick 5s 级稀疏采样即使显存充足也不得启用 High（SC-164-008 每秒采样）。"""
    clock = _FakeClock()
    tracker = HighModeTracker(now=clock)

    # 5s 间隔采样跨越多个 10s 窗口：每窗口样本数 < 最低要求，fail-closed。
    for _ in range(20):
        clock.advance(5.0)
        _sample(tracker, clock, free_mb=30000)

    assert tracker.high_eligible is False
    assert tracker.warmup_windows_ok is False
    assert tracker.degradation_reason == HIGH_DEGRADATION_WARMUP
    assert HIGH_WARMUP_WINDOW_MIN_SAMPLES >= 5


def test_high_runtime_degrades_after_two_consecutive_insufficient_samples(monkeypatch):
    clock = _FakeClock()
    tracker = HighModeTracker(now=clock)
    _run_warmup(tracker, clock)
    assert tracker.high_eligible is True

    # 单次不足不降级。
    clock.advance(HIGH_RUNTIME_SAMPLE_SEC)
    _sample(tracker, clock, free_mb=1000)
    assert tracker.high_eligible is True

    # 连续 2 次不足（间隔 ≥5s）降级串行，原因码覆盖。
    clock.advance(HIGH_RUNTIME_SAMPLE_SEC)
    _sample(tracker, clock, free_mb=1000)
    assert tracker.high_eligible is False
    assert tracker.degradation_reason == HIGH_DEGRADATION_RUNTIME
    assert tracker.warmup_windows_ok is False


def test_high_runtime_recovery_restarts_warmup(monkeypatch):
    clock = _FakeClock()
    tracker = HighModeTracker(now=clock)
    _run_warmup(tracker, clock)
    assert tracker.high_eligible is True

    clock.advance(HIGH_RUNTIME_SAMPLE_SEC)
    _sample(tracker, clock, free_mb=1000)
    clock.advance(HIGH_RUNTIME_SAMPLE_SEC)
    _sample(tracker, clock, free_mb=1000)
    assert tracker.high_eligible is False

    # 降级后重新预热：一个满足窗口不立即启用。
    _run_warmup(tracker, clock)
    assert tracker.high_eligible is True


def test_probe_failure_is_fail_closed_and_resets_windows(monkeypatch):
    clock = _FakeClock()
    tracker = HighModeTracker(now=clock)
    _run_warmup(tracker, clock)
    assert tracker.high_eligible is True

    # 探针失败按不足处理（fail-closed）：连续 2 次后才降级串行。
    clock.advance(HIGH_RUNTIME_SAMPLE_SEC)
    _sample(tracker, clock, free_mb=30000, probe_ok=False)
    assert tracker.high_eligible is True
    clock.advance(HIGH_RUNTIME_SAMPLE_SEC)
    _sample(tracker, clock, free_mb=30000, probe_ok=False)
    assert tracker.high_eligible is False
    assert tracker.degradation_reason == HIGH_DEGRADATION_RUNTIME

    # 再跑完整预热才能重新启用。
    _run_warmup(tracker, clock)
    assert tracker.high_eligible is True


def test_less_than_32gib_never_enables_high(monkeypatch):
    clock = _FakeClock()
    tracker = HighModeTracker(now=clock)
    # 16GiB 总显存即使全空闲也不满足 safe + combined_peak_reserved。
    for _ in range(10 * HIGH_WARMUP_WINDOWS_REQUIRED + 3):
        clock.advance(HIGH_WARMUP_SAMPLE_SEC)
        _sample(tracker, clock, free_mb=10000, total_mb=16384)
    assert tracker.high_eligible is False
    assert tracker.warmup_windows_ok is False


def test_loop_applies_high_eligible_to_resident_mode(db_session, regular_user):
    applied: list[bool] = []
    loop = GpuSchedulerLoop(
        owner_id="scheduler-a",
        gpu_ids=["0"],
        tick_seconds=5,
        ttl_seconds=30,
        publishers={"mineru": lambda _payload: None, "raptor": lambda _payload: None},
        high_resident_enabled=True,
        high_mode_sampler=lambda: {"gpu": {"high_eligible": True}},
        resident_mode_applier=applied.append,
    )

    now = datetime(2026, 8, 1, 0, 0, 0)
    assert loop.run_once(db_session, now=now) == 0
    assert applied == [True]


def test_loop_sampling_failure_fail_closes_resident_mode(db_session, regular_user):
    applied: list[bool] = []

    def _boom() -> dict:
        raise RuntimeError("nvidia-smi unavailable")

    loop = GpuSchedulerLoop(
        owner_id="scheduler-a",
        gpu_ids=["0"],
        tick_seconds=5,
        ttl_seconds=30,
        publishers={"mineru": lambda _payload: None, "raptor": lambda _payload: None},
        high_resident_enabled=True,
        high_mode_sampler=_boom,
        resident_mode_applier=applied.append,
    )

    now = datetime(2026, 8, 1, 0, 0, 0)
    assert loop.run_once(db_session, now=now) == 0
    assert applied == [False]


def test_run_forever_starts_high_sampler_when_enabled(monkeypatch):
    import threading

    monkeypatch.setattr("services.gpu_scheduler_loop.GPU_SCHEDULER_ENABLED", True)
    started: list[dict] = []

    class _FakeThread:
        def __init__(self, **kwargs: object) -> None:
            started.append(kwargs)

        def start(self) -> None:
            pass

    monkeypatch.setattr("services.gpu_scheduler_loop.threading.Thread", _FakeThread)

    class _FakeDB:
        def close(self) -> None:
            pass

    monkeypatch.setattr("services.gpu_scheduler_loop.SessionLocal", lambda: _FakeDB())

    loop = GpuSchedulerLoop(
        owner_id="scheduler-a",
        gpu_ids=["0"],
        tick_seconds=5,
        ttl_seconds=30,
        publishers={"mineru": lambda _payload: None, "raptor": lambda _payload: None},
        high_resident_enabled=True,
        high_mode_sampler=lambda: {"gpu": {"high_eligible": True}},
        resident_mode_applier=lambda _enabled: None,
    )

    def _stop(db):  # noqa: ANN001
        raise SystemExit

    monkeypatch.setattr(loop, "run_once", _stop)
    with pytest.raises(SystemExit):
        loop.run_forever()

    sampler = [kw for kw in started if kw.get("name") == "gpu-high-sampler"]
    assert len(sampler) == 1
    assert sampler[0]["daemon"] is True
    assert sampler[0]["target"] == loop._high_sampler_forever


def test_run_forever_skips_high_sampler_when_disabled(monkeypatch):
    import threading

    monkeypatch.setattr("services.gpu_scheduler_loop.GPU_SCHEDULER_ENABLED", True)
    started: list[dict] = []

    class _FakeThread:
        def __init__(self, **kwargs: object) -> None:
            started.append(kwargs)

        def start(self) -> None:
            pass

    monkeypatch.setattr("services.gpu_scheduler_loop.threading.Thread", _FakeThread)

    class _FakeDB:
        def close(self) -> None:
            pass

    monkeypatch.setattr("services.gpu_scheduler_loop.SessionLocal", lambda: _FakeDB())

    loop = GpuSchedulerLoop(
        owner_id="scheduler-a",
        gpu_ids=["0"],
        tick_seconds=5,
        ttl_seconds=30,
        publishers={"mineru": lambda _payload: None, "raptor": lambda _payload: None},
        high_resident_enabled=False,
    )

    def _stop(db):  # noqa: ANN001
        raise SystemExit

    monkeypatch.setattr(loop, "run_once", _stop)
    with pytest.raises(SystemExit):
        loop.run_forever()

    assert all(kw.get("name") != "gpu-high-sampler" for kw in started)
