# Copyright (c) 2026 徐泽宇
"""High 档（32GiB+）启用与运行中降级判定（164 §5.4/§11.1/SC-164-008）。

采样规则与规格一致：
- 安全余量 ``safe_margin = max(15% * total, 2GiB)``；
- High 启用条件固定为 ``available_after_warmup >= safe_margin + combined_peak_reserved``；
- 预热阶段每秒采样，10 秒为一个窗口，窗口内所有采样满足且进程探针为 ok 记为
  一个满足窗口；连续 3 个满足窗口后才允许 High；
- High 运行中每 5 秒采样，连续 2 次不足即降级串行（``degradation_reason``
  ``high_runtime_insufficient_memory``），并回到预热阶段重新评估；
- 进程探针失败按不足处理（fail-closed），未完成预热窗口或探针非 ok 不得宣告 High。
"""

from __future__ import annotations

import threading
import time
from collections import deque
from typing import Callable

from config import (
    GPU_HIGH_KV_CACHE_BUDGET_MB,
    GPU_HIGH_MINERU_PEAK_RESERVED_MB,
    GPU_HIGH_RAPTOR_PEAK_RESERVED_MB,
)

HIGH_WARMUP_SAMPLE_SEC = 1.0
HIGH_WARMUP_WINDOW_SEC = 10.0
HIGH_WARMUP_WINDOW_MIN_SAMPLES = 8
HIGH_WARMUP_WINDOWS_REQUIRED = 3
HIGH_RUNTIME_SAMPLE_SEC = 5.0
HIGH_RUNTIME_DEGRADE_STREAK = 2
HIGH_TOTAL_MEMORY_MIN_MB = 32 * 1024

HIGH_DEGRADATION_WARMUP = "high_warmup_required"
HIGH_DEGRADATION_RUNTIME = "high_runtime_insufficient_memory"


def safe_margin_mb(total_memory_mb: int) -> int:
    """``max(total * 15%, 2GiB)`` 安全余量。"""
    return max(int(total_memory_mb * 0.15), 2048)


def combined_peak_reserved_mb() -> int:
    """RAPTOR + MinerU 组合峰值预留 + 并发/KV cache 预算。"""
    return (
        GPU_HIGH_RAPTOR_PEAK_RESERVED_MB
        + GPU_HIGH_MINERU_PEAK_RESERVED_MB
        + GPU_HIGH_KV_CACHE_BUDGET_MB
    )


class HighModeTracker:
    """有状态 High 档判定器：预热窗口累计、运行中降级与重新评估。"""

    def __init__(self, *, now: Callable[[], float] | None = None) -> None:
        self._now = now or time.monotonic
        self._lock = threading.Lock()
        self._warmup_window: deque[tuple[float, bool]] = deque()
        self._warmup_ok_windows = 0
        self._last_runtime_sample_t: float | None = None
        self._runtime_bad_streak = 0
        self._eligible = False
        self._degradation_reason: str | None = HIGH_DEGRADATION_WARMUP

    @property
    def high_eligible(self) -> bool:
        with self._lock:
            return self._eligible

    @property
    def warmup_windows_ok(self) -> bool:
        with self._lock:
            return self._eligible or self._warmup_ok_windows >= HIGH_WARMUP_WINDOWS_REQUIRED

    @property
    def degradation_reason(self) -> str | None:
        with self._lock:
            return self._degradation_reason

    def record_sample(
        self,
        *,
        memory_free_mb: int,
        total_memory_mb: int,
        combined_peak_reserved_mb: int,
        process_probe_ok: bool,
    ) -> bool:
        """记录一次显存/探针采样，返回当前是否 High eligible。"""
        now = self._now()
        safe = safe_margin_mb(total_memory_mb)
        sufficient = (
            process_probe_ok
            and total_memory_mb >= HIGH_TOTAL_MEMORY_MIN_MB
            and memory_free_mb >= safe + combined_peak_reserved_mb
        )
        with self._lock:
            if not self._eligible:
                self._warmup_step(now=now, sufficient=sufficient, probe_ok=process_probe_ok)
                return self._eligible
            self._runtime_step(now=now, sufficient=sufficient)
            return self._eligible

    def _warmup_step(self, *, now: float, sufficient: bool, probe_ok: bool) -> None:
        if self._warmup_window and now - self._warmup_window[-1][0] < HIGH_WARMUP_SAMPLE_SEC:
            # 同一采样秒内的重复调用忽略，保持每秒一采样。
            return
        self._warmup_window.append((now, sufficient))
        while self._warmup_window and now - self._warmup_window[0][0] > HIGH_WARMUP_WINDOW_SEC:
            self._warmup_window.popleft()
        if not probe_ok:
            # 探针失败 fail-closed：连续窗口清零，不宣告 High。
            self._warmup_ok_windows = 0
            self._degradation_reason = HIGH_DEGRADATION_WARMUP
            return
        window_seconds = now - self._warmup_window[0][0] if self._warmup_window else 0.0
        if window_seconds < HIGH_WARMUP_WINDOW_SEC:
            # 窗口未满；若窗口内已出现不足样本，连续窗口清零并重启窗口，
            # 避免旧不足样本残留污染后续窗口。
            if any(not ok for _, ok in self._warmup_window):
                self._warmup_ok_windows = 0
                self._degradation_reason = HIGH_DEGRADATION_WARMUP
                self._warmup_window.clear()
            return
        if (
            len(self._warmup_window) < HIGH_WARMUP_WINDOW_MIN_SAMPLES
            or not all(ok for _, ok in self._warmup_window)
        ):
            # 采样密度不足（生产接线未按 1s 采样）或窗口内存在不足样本：
            # fail-closed，窗口不计数并清空，避免稀疏采样放大判定粒度。
            self._warmup_ok_windows = 0
            self._degradation_reason = HIGH_DEGRADATION_WARMUP
            self._warmup_window.clear()
            return
        # 一个完整满足窗口：清理后累计连续窗口。
        self._warmup_ok_windows += 1
        self._warmup_window.clear()
        if self._warmup_ok_windows >= HIGH_WARMUP_WINDOWS_REQUIRED:
            self._eligible = True
            self._degradation_reason = None
            self._last_runtime_sample_t = None
            self._runtime_bad_streak = 0

    def _runtime_step(self, *, now: float, sufficient: bool) -> None:
        if self._last_runtime_sample_t is not None and now - self._last_runtime_sample_t < HIGH_RUNTIME_SAMPLE_SEC:
            return
        self._last_runtime_sample_t = now
        if sufficient:
            self._runtime_bad_streak = 0
            return
        self._runtime_bad_streak += 1
        if self._runtime_bad_streak >= HIGH_RUNTIME_DEGRADE_STREAK:
            self._eligible = False
            self._degradation_reason = HIGH_DEGRADATION_RUNTIME
            self._warmup_ok_windows = 0
            self._warmup_window.clear()
            self._last_runtime_sample_t = None
            self._runtime_bad_streak = 0


_HIGH_MODE_TRACKER: HighModeTracker | None = None
_HIGH_MODE_LOCK = threading.Lock()


def get_high_mode_tracker() -> HighModeTracker:
    global _HIGH_MODE_TRACKER
    with _HIGH_MODE_LOCK:
        if _HIGH_MODE_TRACKER is None:
            _HIGH_MODE_TRACKER = HighModeTracker()
        return _HIGH_MODE_TRACKER


def reset_high_mode_tracker() -> None:
    global _HIGH_MODE_TRACKER
    with _HIGH_MODE_LOCK:
        _HIGH_MODE_TRACKER = HighModeTracker()
