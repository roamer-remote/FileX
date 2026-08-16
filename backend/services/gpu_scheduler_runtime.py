# Copyright (c) 2026 徐泽宇
"""Process-local scheduler owner bridge used until the T-3 durable lease.

The process owns one scheduler instance and derives a per-job context from the
same owner lease/token. T-3 will replace the owner identity with PostgreSQL
lease/fencing; production GPU calls already use the same injection boundary.
"""

from __future__ import annotations

import threading
import uuid
from dataclasses import dataclass
import logging
from typing import Callable

from services.gpu_model_lifecycle_service import (
    GpuExecutionContext,
    GpuModelSchedulerAdapter,
    LoadAck,
    ModelGroup,
    ReleaseAck,
    WarmupAck,
)

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class RuntimeLifecycleOperations:
    """真实模型生命周期操作；未配置时 runtime 必须拒绝 GPU 执行。"""

    model_group: ModelGroup
    load: Callable[[GpuExecutionContext], LoadAck]
    warmup: Callable[[GpuExecutionContext], WarmupAck]
    unload: Callable[[GpuExecutionContext], ReleaseAck]


class _RuntimeAdapter:
    def __init__(self, model_group: ModelGroup, operations: RuntimeLifecycleOperations | None) -> None:
        self.model_group = model_group
        if operations is not None and operations.model_group != model_group:
            raise ValueError("lifecycle operations model group mismatch")
        self._operations = operations

    def load(self, context: GpuExecutionContext) -> LoadAck:
        if self._operations is None:
            return LoadAck(False, "runtime_lifecycle_unconfigured")
        return self._operations.load(context)

    def warmup(self, context: GpuExecutionContext) -> WarmupAck:
        if self._operations is None:
            return WarmupAck(False, "runtime_lifecycle_unconfigured")
        return self._operations.warmup(context)

    def unload(self, context: GpuExecutionContext) -> ReleaseAck:
        if self._operations is None:
            return ReleaseAck(False, "runtime_lifecycle_unconfigured")
        return self._operations.unload(context)

    def execute(self, _context: GpuExecutionContext, **kwargs: object) -> object:
        call = kwargs.get("call")
        if not callable(call):
            raise RuntimeError("scheduler execution callback is required")
        return call()


class GpuSchedulerRuntime:
    """Single process owner; durable cross-process fencing belongs to T-3."""

    def __init__(
        self,
        *,
        raptor_operations: RuntimeLifecycleOperations | None = None,
        mineru_operations: RuntimeLifecycleOperations | None = None,
        resident_groups_enabled: bool = False,
        state_store: object | None = None,
    ) -> None:
        self.lifecycle_configured = raptor_operations is not None and mineru_operations is not None
        if not self.lifecycle_configured:
            logger.warning(
                "gpu_scheduler lifecycle unconfigured; GPU model handover is disabled fail-closed"
            )
        self._owner_lease_id = f"process-{uuid.uuid4()}"
        self._fencing_token = str(uuid.uuid4())
        self.scheduler = GpuModelSchedulerAdapter(
            raptor=_RuntimeAdapter(ModelGroup.RAPTOR, raptor_operations),  # type: ignore[arg-type]
            mineru=_RuntimeAdapter(ModelGroup.MINERU, mineru_operations),  # type: ignore[arg-type]
            allow_resident_groups=bool(resident_groups_enabled),
            state_store=state_store,
        )

    def set_resident_groups(self, enabled: bool) -> None:
        """按 High 档判定结果动态启停双模型组常驻。"""
        self.scheduler.set_resident_mode(enabled)

    def context_for_job(
        self,
        job_id: int | str,
        *,
        model: str | None = None,
        embed_model: str | None = None,
    ) -> GpuExecutionContext:
        return GpuExecutionContext(
            gpu_lease_id=self._owner_lease_id,
            fencing_token=self._fencing_token,
            job_id=str(job_id),
            model=model,
            embed_model=embed_model,
        )


_RUNTIME: GpuSchedulerRuntime | None = None
_RUNTIME_LOCK = threading.Lock()


def get_gpu_scheduler_runtime() -> GpuSchedulerRuntime:
    global _RUNTIME
    with _RUNTIME_LOCK:
        if _RUNTIME is None:
            from services.gpu_concrete_lifecycle import build_concrete_lifecycle_operations
            from services.gpu_scheduler_state_store import GpuSchedulerStateStore

            raptor_operations, mineru_operations = build_concrete_lifecycle_operations()
            _RUNTIME = GpuSchedulerRuntime(
                raptor_operations=raptor_operations,
                mineru_operations=mineru_operations,
                state_store=GpuSchedulerStateStore(),
            )
        return _RUNTIME


def scheduler_for_job(
    job_id: int | str,
    *,
    db=None,
) -> tuple[GpuModelSchedulerAdapter | None, GpuExecutionContext | None]:
    from config import GPU_SCHEDULER_ENABLED

    if not GPU_SCHEDULER_ENABLED:
        return None, None
    runtime = get_gpu_scheduler_runtime()
    model = None
    embed_model = None
    if db is not None:
        from services.ollama_config_service import get_ollama_runtime_config

        ollama = get_ollama_runtime_config(db, fresh=True)
        model = ollama.chat_model
        embed_model = ollama.embed_model
    return runtime.scheduler, runtime.context_for_job(
        job_id,
        model=model,
        embed_model=embed_model,
    )
