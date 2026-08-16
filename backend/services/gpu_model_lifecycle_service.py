# Copyright (c) 2026 徐泽宇
"""唯一 GPU scheduler adapter 的模型组生命周期契约。

T-2 只负责模型组的互斥生命周期，不直接实现 Ollama 或 MinerU 的网络调用。
真实 adapter 必须返回可验证的 load/warmup/release ack；没有 release ack 时，
切换停在 recovery_blocked，绝不加载另一个模型组。
"""

from __future__ import annotations

from dataclasses import dataclass, replace
from enum import StrEnum
import logging
import time
from threading import RLock
from typing import Callable, Protocol

logger = logging.getLogger(__name__)


GPU_OOM_MARKERS = (
    "out of memory",
    "out_of_memory",
    "cuda error",
    "insufficient memory",
    "allocation failed",
    "alloc failed",
    "vram exhausted",
    "cuda oom",
)


def is_gpu_oom_error(exc: BaseException) -> bool:
    """判定异常是否为 GPU 显存不足（CUDA OOM / Ollama 500 / MinerU RPC detail）。"""
    text = f"{exc.__class__.__name__}: {exc}".lower()
    response = getattr(exc, "response", None)
    if response is not None:
        try:
            text += " " + str(getattr(response, "text", "") or "").lower()
        except Exception:
            pass
    return any(marker in text for marker in GPU_OOM_MARKERS)


def _memory_summary(snapshot: object) -> str:
    if not isinstance(snapshot, dict):
        return "memory_unavailable"
    gpu = snapshot.get("gpu") if isinstance(snapshot.get("gpu"), dict) else {}
    return (
        "gpu_index=%s total_mb=%s used_mb=%s free_mb=%s capability=%s reason_code=%s"
        % (
            gpu.get("gpu_index"),
            gpu.get("memory_total_mb"),
            gpu.get("memory_used_mb"),
            gpu.get("memory_free_mb"),
            gpu.get("capability"),
            gpu.get("reason_code"),
        )
    )


def _reprobe_system_resources() -> dict:
    """失效 2 秒 TTL 缓存并重新采样 GPU/系统资源（spec §8/§11.1）。"""
    from services.system_resource_service import collect_system_resources, reset_system_resource_cache

    reset_system_resource_cache()
    return collect_system_resources()

class ModelGroup(StrEnum):
    NONE = "none"
    RAPTOR = "raptor"
    MINERU = "mineru"
    SWITCHING = "switching"


class ModelGroupStatus(StrEnum):
    UNLOADED = "unloaded"
    LOADING = "loading"
    WARMING = "warming"
    RUNNING = "running"
    RECOVERY_BLOCKED = "recovery_blocked"
    FAILED = "failed"


@dataclass(frozen=True)
class GpuExecutionContext:
    """授权 GPU 调用的不可变上下文，必须贯穿 adapter/sidecar。"""

    gpu_lease_id: str
    fencing_token: str
    job_id: str
    # 当前任务从 runtime settings 解析出的 Ollama 模型；不再依赖进程启动时常量。
    model: str | None = None
    embed_model: str | None = None

    def __post_init__(self) -> None:
        if not self.gpu_lease_id.strip() or not self.fencing_token.strip() or not self.job_id.strip():
            raise ValueError("gpu_lease_id, fencing_token and job_id are required")

    @property
    def owner_key(self) -> tuple[str, str]:
        return self.gpu_lease_id, self.fencing_token


@dataclass(frozen=True)
class LoadAck:
    accepted: bool
    detail: str = ""


@dataclass(frozen=True)
class WarmupAck:
    healthy: bool
    detail: str = ""


@dataclass(frozen=True)
class ReleaseAck:
    acknowledged: bool
    detail: str = ""


class ModelGroupAdapter(Protocol):
    model_group: ModelGroup

    def load(self, context: GpuExecutionContext) -> LoadAck: ...

    def warmup(self, context: GpuExecutionContext) -> WarmupAck: ...

    def unload(self, context: GpuExecutionContext) -> ReleaseAck: ...

    def execute(self, context: GpuExecutionContext, **kwargs: object) -> object: ...


class RaptorOllamaAdapter(ModelGroupAdapter, Protocol):
    """RAPTOR 只能通过 scheduler adapter 控制 Ollama。"""

    model_group: ModelGroup.RAPTOR


class MineruAuthorizedRpcAdapter(ModelGroupAdapter, Protocol):
    """MinerU sidecar 只能接受带 lease/token/job 的授权 RPC。"""

    model_group: ModelGroup.MINERU


class RaptorOllamaConcreteAdapter:
    """把 Ollama 执行函数接入 scheduler 的 concrete adapter。"""

    model_group = ModelGroup.RAPTOR

    def __init__(
        self,
        *,
        execute_fn: Callable[..., object],
        load_fn: Callable[[GpuExecutionContext], LoadAck],
        warmup_fn: Callable[[GpuExecutionContext], WarmupAck],
        unload_fn: Callable[[GpuExecutionContext], ReleaseAck],
    ) -> None:
        self._execute_fn = execute_fn
        self._load_fn = load_fn
        self._warmup_fn = warmup_fn
        self._unload_fn = unload_fn

    def load(self, context: GpuExecutionContext) -> LoadAck:
        return self._load_fn(context)

    def warmup(self, context: GpuExecutionContext) -> WarmupAck:
        return self._warmup_fn(context)

    def unload(self, context: GpuExecutionContext) -> ReleaseAck:
        return self._unload_fn(context)

    def execute(self, context: GpuExecutionContext, **kwargs: object) -> object:
        return self._execute_fn(context=context, **kwargs)


class MineruAuthorizedRpcConcreteAdapter:
    """把带授权上下文的 MinerU RPC 函数接入 scheduler 的 concrete adapter。"""

    model_group = ModelGroup.MINERU

    def __init__(
        self,
        *,
        execute_fn: Callable[..., object],
        load_fn: Callable[[GpuExecutionContext], LoadAck],
        warmup_fn: Callable[[GpuExecutionContext], WarmupAck],
        unload_fn: Callable[[GpuExecutionContext], ReleaseAck],
    ) -> None:
        self._execute_fn = execute_fn
        self._load_fn = load_fn
        self._warmup_fn = warmup_fn
        self._unload_fn = unload_fn

    def load(self, context: GpuExecutionContext) -> LoadAck:
        return self._load_fn(context)

    def warmup(self, context: GpuExecutionContext) -> WarmupAck:
        return self._warmup_fn(context)

    def unload(self, context: GpuExecutionContext) -> ReleaseAck:
        return self._unload_fn(context)

    def execute(self, context: GpuExecutionContext, **kwargs: object) -> object:
        return self._execute_fn(context=context, **kwargs)


@dataclass(frozen=True)
class ModelGroupState:
    model_group: ModelGroup = ModelGroup.NONE
    status: ModelGroupStatus = ModelGroupStatus.UNLOADED
    previous_group: ModelGroup = ModelGroup.NONE
    error: str | None = None
    batch_job_ids: tuple[str, ...] = ()
    context: GpuExecutionContext | None = None


@dataclass(frozen=True)
class ModelBatch:
    model_group: ModelGroup
    job_ids: tuple[str, ...]


class ModelLifecycleError(RuntimeError):
    """模型组没有达到可安全运行状态。"""


class GpuWaitingError(ModelLifecycleError):
    """GPU 生命周期暂不可用；调用方必须保持任务等待而不是回退执行。"""

    reason_code = "gpu_waiting_lifecycle_unavailable"


class GpuOomError(ModelLifecycleError):
    """GPU 显存不足；模型组已释放并重新探测显存，调用方按最多一次受控重试处理。"""

    reason_code = "gpu_oom_release_reprobe"
    max_controlled_retries = 1


def validate_authorized_result(context: GpuExecutionContext, result: object) -> None:
    """Fail-closed validator for adapter results carrying GPU authorization."""
    if not isinstance(result, dict):
        raise ModelLifecycleError("scheduler execution returned a non-object result")
    if (
        result.get("gpu_lease_id") != context.gpu_lease_id
        or result.get("fencing_token") != context.fencing_token
        or str(result.get("gpu_job_id")) != context.job_id
    ):
        raise ModelLifecycleError("scheduler execution authorization context mismatch")


class GpuModelSchedulerAdapter:
    """持有模型切换边界的唯一 scheduler adapter。"""

    def __init__(
        self,
        *,
        raptor: RaptorOllamaAdapter,
        mineru: MineruAuthorizedRpcAdapter,
        max_batch_jobs: int = 5,
        allow_resident_groups: bool = False,
        state_store: object | None = None,
    ) -> None:
        if max_batch_jobs < 1:
            raise ValueError("max_batch_jobs must be positive")
        if raptor.model_group != ModelGroup.RAPTOR or mineru.model_group != ModelGroup.MINERU:
            raise ValueError("adapters must declare their model group")
        self._adapters: dict[ModelGroup, ModelGroupAdapter] = {
            ModelGroup.RAPTOR: raptor,
            ModelGroup.MINERU: mineru,
        }
        self._max_batch_jobs = max_batch_jobs
        self._allow_resident_groups = bool(allow_resident_groups)
        self._resident: set[ModelGroup] = set()
        self._state = ModelGroupState()
        self._lock = RLock()
        self._state_store = state_store

    @property
    def state(self) -> ModelGroupState:
        return self._state

    @property
    def resident_groups(self) -> tuple[ModelGroup, ...]:
        with self._lock:
            return tuple(self._resident)

    def set_resident_mode(self, enabled: bool) -> None:
        """High 档常驻开关：开启后跨组切换不再卸载已驻留组。"""
        with self._lock:
            self._allow_resident_groups = bool(enabled)
            if not self._allow_resident_groups:
                self._resident = set()

    def switch_to(self, model_group: ModelGroup, context: GpuExecutionContext) -> ModelGroupState:
        """释放旧组、确认 ack、加载并预热新组；任一门禁失败都不进入 running。"""
        with self._lock:
            if model_group not in (ModelGroup.RAPTOR, ModelGroup.MINERU):
                raise ValueError("model_group must be RAPTOR or MINERU")
            if self._state.status == ModelGroupStatus.RUNNING and self._state.model_group == model_group:
                if self._state.context is None or self._state.context.owner_key != context.owner_key:
                    raise ModelLifecycleError("execution context does not own the running model group")
                return self._state

            previous_group = self._state.model_group
            keep_previous_resident = (
                self._allow_resident_groups
                and previous_group in self._adapters
                and previous_group in self._resident
                and previous_group != model_group
            )
            target_resident = self._allow_resident_groups and model_group in self._resident
            switch_started_at = time.monotonic()
            self._notify_switch_started(model_group)
            self._state = ModelGroupState(
                model_group=ModelGroup.SWITCHING,
                status=ModelGroupStatus.LOADING,
                previous_group=previous_group,
                context=context,
            )
            if previous_group in self._adapters and not keep_previous_resident:
                try:
                    release_ack = self._adapters[previous_group].unload(context)
                except Exception as exc:
                    return self._fail_release(previous_group, context, exc)
                if not release_ack.acknowledged:
                    return self._fail_release(
                        previous_group,
                        context,
                        ModelLifecycleError(release_ack.detail or "release_ack_missing"),
                    )

            if not target_resident:
                adapter = self._adapters[model_group]
                self._state = replace(self._state, model_group=model_group, status=ModelGroupStatus.LOADING)
                try:
                    load_ack = adapter.load(context)
                except Exception as exc:
                    return self._fail_transition(model_group, context, exc)
                if not load_ack.accepted:
                    return self._fail_transition(
                        model_group,
                        context,
                        ModelLifecycleError(load_ack.detail or "load_failed"),
                    )

                self._state = replace(self._state, status=ModelGroupStatus.WARMING)
                try:
                    warmup_ack = adapter.warmup(context)
                except Exception as exc:
                    return self._fail_transition(model_group, context, exc)
                if not warmup_ack.healthy:
                    return self._fail_transition(
                        model_group,
                        context,
                        ModelLifecycleError(warmup_ack.detail or "warmup_failed"),
                    )
                self._resident.add(model_group)
            else:
                # 已驻留组切换：不重新 load/warmup。
                self._state = replace(self._state, model_group=model_group)

            self._state = replace(
                self._state,
                status=ModelGroupStatus.RUNNING,
                error=None,
                batch_job_ids=(),
                context=context,
            )
            self._notify_switch_finished(model_group, switch_started_at)
            return self._state

    def _fail_release(
        self, previous_group: ModelGroup, context: GpuExecutionContext, exc: Exception
    ) -> ModelGroupState:
        detail = str(exc) or exc.__class__.__name__
        self._notify_failure("release", detail)
        self._state = ModelGroupState(
            model_group=ModelGroup.SWITCHING,
            status=ModelGroupStatus.RECOVERY_BLOCKED,
            previous_group=previous_group,
            error=detail,
            context=context,
        )
        raise GpuWaitingError(f"model release failed: {detail}") from exc

    def _fail_transition(
        self, model_group: ModelGroup, context: GpuExecutionContext, exc: Exception
    ) -> ModelGroupState:
        detail = str(exc) or exc.__class__.__name__
        if is_gpu_oom_error(exc):
            kind = "oom"
        elif self._state.status == ModelGroupStatus.WARMING:
            kind = "warmup"
        else:
            kind = "load"
        self._notify_failure(kind, detail)
        # 常驻集合只保留已完成 load/warmup 且被 High 判定验证过的组；任一次
        # 加载/预热失败都必须失效，下次 switch_to 重新走 load/warmup。
        self._resident.discard(model_group)
        self._state = ModelGroupState(
            model_group=model_group,
            status=ModelGroupStatus.FAILED,
            error=detail,
            context=context,
        )
        self._reprobe_and_log("model_transition_failed", model_group, context, detail)
        if is_gpu_oom_error(exc):
            raise GpuOomError(f"model transition failed (oom): {detail}") from exc
        raise GpuWaitingError(f"model transition failed: {detail}") from exc

    def _reprobe_and_log(
        self,
        event: str,
        model_group: ModelGroup,
        context: GpuExecutionContext,
        detail: str,
        release_detail: str = "",
    ) -> dict:
        """释放/失败后重新探测显存并记录 GPU、模型组、显存、任务与异常摘要。"""
        try:
            snapshot = _reprobe_system_resources()
        except Exception as probe_exc:
            logger.error(
                "gpu resource reprobe failed event=%s model_group=%s lease=%s token=%s job=%s error=%s",
                event,
                model_group,
                context.gpu_lease_id,
                context.fencing_token,
                context.job_id,
                probe_exc,
            )
            snapshot = {}
        logger.error(
            "gpu %s model_group=%s lease=%s token=%s job=%s release=%s memory=%s error=%s",
            event,
            model_group,
            context.gpu_lease_id,
            context.fencing_token,
            context.job_id,
            release_detail or "n/a",
            _memory_summary(snapshot),
            detail,
        )
        return snapshot

    def _handle_execute_oom(
        self, model_group: ModelGroup, context: GpuExecutionContext, exc: Exception
    ) -> object:
        """执行期 OOM：释放当前模型组 → 重新探测显存 → 置 FAILED 并抛 GpuOomError。"""
        detail = str(exc) or exc.__class__.__name__
        self._notify_failure("oom", detail)
        release_detail = ""
        try:
            ack = self._adapters[model_group].unload(context)
            release_detail = ack.detail or ("released" if ack.acknowledged else "release_ack_missing")
        except Exception as release_exc:
            release_detail = f"unload_failed:{release_exc}"
        self._resident.discard(model_group)
        self._state = ModelGroupState(
            model_group=model_group,
            status=ModelGroupStatus.FAILED,
            previous_group=model_group,
            error=detail,
            context=context,
        )
        snapshot = self._reprobe_and_log("execution_oom", model_group, context, detail, release_detail)
        raise GpuOomError(
            f"model_group={model_group} lease={context.gpu_lease_id} job={context.job_id} "
            f"release={release_detail} memory={_memory_summary(snapshot)} error={detail}"
        ) from exc

    def _notify_switch_started(self, model_group: ModelGroup) -> None:
        if self._state_store is None:
            return
        try:
            self._state_store.record_switch_started(str(model_group))
        except Exception:
            logger.warning("gpu_scheduler_state switch_started notify failed", exc_info=True)

    def _notify_switch_finished(self, model_group: ModelGroup, switch_started_at: float) -> None:
        if self._state_store is None:
            return
        try:
            duration_ms = int((time.monotonic() - switch_started_at) * 1000)
            self._state_store.record_switch_finished(str(model_group), duration_ms)
        except Exception:
            logger.warning("gpu_scheduler_state switch_finished notify failed", exc_info=True)

    def _notify_failure(self, kind: str, reason: str) -> None:
        if self._state_store is None:
            return
        try:
            self._state_store.record_failure(kind, reason)
        except Exception:
            logger.warning("gpu_scheduler_state failure notify failed", exc_info=True)

    def acquire_batch(
        self,
        model_group: ModelGroup,
        job_ids: list[str] | tuple[str, ...],
        context: GpuExecutionContext,
    ) -> ModelBatch:
        """同组任务复用驻留模型；不同组或未预热完成时拒绝执行。"""
        with self._lock:
            ids = tuple(job_ids)
            if not ids:
                raise ValueError("job_ids must not be empty")
            if len(ids) > self._max_batch_jobs:
                raise ModelLifecycleError("model batch exceeds configured limit")
            if self._state.status != ModelGroupStatus.RUNNING or self._state.model_group != model_group:
                raise ModelLifecycleError("model group is not running")
            if self._state.context is None or self._state.context.owner_key != context.owner_key:
                raise ModelLifecycleError("execution context does not own the model group")
            if len(set(ids)) != len(ids):
                raise ValueError("job_ids must be unique")
            self._state = replace(self._state, batch_job_ids=ids)
            return ModelBatch(model_group=model_group, job_ids=ids)

    def execute(self, model_group: ModelGroup, context: GpuExecutionContext, **kwargs: object) -> object:
        """实际 GPU 调用的唯一入口，执行前重新校验 owner context。"""
        with self._lock:
            if self._state.status != ModelGroupStatus.RUNNING or self._state.model_group != model_group:
                raise ModelLifecycleError("model group is not running")
            if self._state.context is None or self._state.context.owner_key != context.owner_key:
                raise ModelLifecycleError("execution context does not own the model group")
            if context.job_id not in self._state.batch_job_ids:
                raise ModelLifecycleError("job must acquire a model batch before execution")
            validator = kwargs.pop("_validate_result", None)
            try:
                result = self._adapters[model_group].execute(context, **kwargs)
                if callable(validator):
                    validator(context, result)
                return result
            except Exception as exc:
                if not is_gpu_oom_error(exc):
                    raise
                return self._handle_execute_oom(model_group, context, exc)
