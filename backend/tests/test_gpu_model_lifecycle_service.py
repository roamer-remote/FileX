# Copyright (c) 2026 徐泽宇
"""T-2 model-group lifecycle and scheduler-adapter contract tests."""

from __future__ import annotations

import pytest
from concurrent.futures import ThreadPoolExecutor

from services.gpu_model_lifecycle_service import (
    GpuExecutionContext,
    GpuModelSchedulerAdapter,
    GpuOomError,
    GpuWaitingError,
    LoadAck,
    MineruAuthorizedRpcAdapter,
    ModelGroup,
    ModelGroupStatus,
    ModelLifecycleError,
    ReleaseAck,
    RaptorOllamaAdapter,
    WarmupAck,
    validate_authorized_result,
)


@pytest.fixture(autouse=True)
def _fake_resource_reprobe(monkeypatch):
    """T-7：OOM/加载失败后的显存重探在单测中用固定快照替代，避免真实 nvidia-smi。"""
    monkeypatch.setattr(
        "services.gpu_model_lifecycle_service._reprobe_system_resources",
        lambda: {
            "gpu": {
                "gpu_index": 0,
                "memory_total_mb": 8192,
                "memory_used_mb": 4096,
                "memory_free_mb": 4096,
                "capability": "low",
                "reason_code": None,
            }
        },
    )


class FakeAdapter:
    def __init__(self, model_group: ModelGroup, *, release_ok: bool = True, load_ok: bool = True, warmup_ok: bool = True):
        self.model_group = model_group
        self.release_ok = release_ok
        self.load_ok = load_ok
        self.warmup_ok = warmup_ok
        self.calls: list[tuple[str, GpuExecutionContext]] = []

    def load(self, context: GpuExecutionContext) -> LoadAck:
        self.calls.append(("load", context))
        return LoadAck(self.load_ok, "load_failed" if not self.load_ok else "")

    def warmup(self, context: GpuExecutionContext) -> WarmupAck:
        self.calls.append(("warmup", context))
        return WarmupAck(self.warmup_ok, "warmup_failed" if not self.warmup_ok else "")

    def unload(self, context: GpuExecutionContext) -> ReleaseAck:
        self.calls.append(("unload", context))
        return ReleaseAck(self.release_ok, "release_ack_missing" if not self.release_ok else "")

    def execute(self, context: GpuExecutionContext, **kwargs: object) -> object:
        self.calls.append(("execute", context))
        callback = kwargs.get("call")
        return callback() if callable(callback) else {"context": context}


def _adapter(
    *,
    raptor: FakeAdapter | None = None,
    mineru: FakeAdapter | None = None,
    state_store: object | None = None,
) -> tuple[GpuModelSchedulerAdapter, FakeAdapter, FakeAdapter]:
    raptor = raptor or FakeAdapter(ModelGroup.RAPTOR)
    mineru = mineru or FakeAdapter(ModelGroup.MINERU)
    scheduler = GpuModelSchedulerAdapter(
        raptor=raptor,  # type: ignore[arg-type]
        mineru=mineru,  # type: ignore[arg-type]
        state_store=state_store,
    )
    return scheduler, raptor, mineru


class FakeStateStore:
    """记录观测回调调用，验证 §9 状态写入点。"""

    def __init__(self) -> None:
        self.events: list[tuple[str, object]] = []

    def record_switch_started(self, model_group: str, now=None) -> None:
        self.events.append(("switch_started", model_group))

    def record_switch_finished(self, model_group: str, duration_ms: int, now=None) -> None:
        self.events.append(("switch_finished", (model_group, duration_ms)))

    def record_failure(self, kind: str, reason: str, now=None) -> None:
        self.events.append(("failure", (kind, reason)))


def test_switch_requires_release_ack_and_warmup_before_running():
    scheduler, raptor, mineru = _adapter()
    context = GpuExecutionContext("lease-1", "fence-1", "job-1")

    assert scheduler.switch_to(ModelGroup.RAPTOR, context).status == ModelGroupStatus.RUNNING
    state = scheduler.switch_to(ModelGroup.MINERU, context)

    assert state.model_group == ModelGroup.MINERU
    assert state.status == ModelGroupStatus.RUNNING
    assert [name for name, _ in raptor.calls] == ["load", "warmup", "unload"]
    assert [name for name, _ in mineru.calls] == ["load", "warmup"]
    assert all(call_context == context for _, call_context in raptor.calls + mineru.calls)


def test_state_store_notified_on_switch_success():
    store = FakeStateStore()
    scheduler, _, _ = _adapter(state_store=store)
    context = GpuExecutionContext("lease-1", "fence-1", "job-1")

    scheduler.switch_to(ModelGroup.RAPTOR, context)

    assert store.events[0][0] == "switch_started"
    assert store.events[0][1] == "raptor"
    assert store.events[1][0] == "switch_finished"
    kind, (model_group, duration_ms) = store.events[1]
    assert model_group == "raptor"
    assert isinstance(duration_ms, int) and duration_ms >= 0


def test_state_store_notified_on_warmup_failure():
    store = FakeStateStore()
    scheduler, _, _ = _adapter(
        mineru=FakeAdapter(ModelGroup.MINERU, warmup_ok=False),
        state_store=store,
    )
    context = GpuExecutionContext("lease-1", "fence-1", "job-1")

    with pytest.raises(ModelLifecycleError, match="warmup"):
        scheduler.switch_to(ModelGroup.MINERU, context)

    assert ("switch_started", "mineru") in store.events
    assert store.events[-1][0] == "failure"
    assert store.events[-1][1][0] == "warmup"
    assert "warmup_failed" in store.events[-1][1][1]


def test_state_store_notified_on_release_failure():
    store = FakeStateStore()
    scheduler, _, _ = _adapter(
        raptor=FakeAdapter(ModelGroup.RAPTOR, release_ok=False),
        state_store=store,
    )
    context = GpuExecutionContext("lease-1", "fence-1", "job-1")
    scheduler.switch_to(ModelGroup.RAPTOR, context)

    with pytest.raises(ModelLifecycleError, match="release"):
        scheduler.switch_to(ModelGroup.MINERU, context)

    assert store.events[-1][0] == "failure"
    assert store.events[-1][1][0] == "release"


def test_state_store_notified_on_execute_oom():
    store = FakeStateStore()
    scheduler, _, _ = _adapter(
        raptor=OomExplodingAdapter(ModelGroup.RAPTOR),
        state_store=store,
    )
    context = GpuExecutionContext("lease-1", "fence-1", "job-1")
    scheduler.switch_to(ModelGroup.RAPTOR, context)
    scheduler.acquire_batch(ModelGroup.RAPTOR, ["job-1"], context)

    with pytest.raises(GpuOomError):
        scheduler.execute(ModelGroup.RAPTOR, context, call=lambda: {"ok": True})

    assert store.events[-1][0] == "failure"
    assert store.events[-1][1][0] == "oom"
    assert "out of memory" in store.events[-1][1][1]


def test_missing_release_ack_blocks_switch_and_does_not_load_target():
    scheduler, raptor, mineru = _adapter(raptor=FakeAdapter(ModelGroup.RAPTOR, release_ok=False))
    context = GpuExecutionContext("lease-1", "fence-1", "job-1")
    scheduler.switch_to(ModelGroup.RAPTOR, context)

    with pytest.raises(ModelLifecycleError, match="release"):
        scheduler.switch_to(ModelGroup.MINERU, context)

    assert scheduler.state.status == ModelGroupStatus.RECOVERY_BLOCKED
    assert scheduler.state.model_group == ModelGroup.SWITCHING
    assert [name for name, _ in mineru.calls] == []


def test_failed_warmup_never_enters_running():
    scheduler, _, mineru = _adapter(mineru=FakeAdapter(ModelGroup.MINERU, warmup_ok=False))
    context = GpuExecutionContext("lease-1", "fence-1", "job-1")

    with pytest.raises(ModelLifecycleError, match="warmup"):
        scheduler.switch_to(ModelGroup.MINERU, context)

    assert scheduler.state.status == ModelGroupStatus.FAILED
    assert scheduler.state.model_group == ModelGroup.MINERU
    assert [name for name, _ in mineru.calls] == ["load", "warmup"]


def test_same_group_batch_is_reused_and_limited():
    scheduler, _, _ = _adapter()
    context = GpuExecutionContext("lease-1", "fence-1", "job-1")
    scheduler.switch_to(ModelGroup.RAPTOR, context)

    batch = scheduler.acquire_batch(ModelGroup.RAPTOR, ["job-1", "job-2"], context)
    assert batch.model_group == ModelGroup.RAPTOR
    assert batch.job_ids == ("job-1", "job-2")
    assert scheduler.state.batch_job_ids == batch.job_ids

    with pytest.raises(ModelLifecycleError, match="limit"):
        scheduler.acquire_batch(ModelGroup.RAPTOR, [f"job-{i}" for i in range(6)], context)

    with pytest.raises(ModelLifecycleError, match="not running"):
        scheduler.acquire_batch(ModelGroup.MINERU, ["job-3"], context)


def test_adapter_rejects_invalid_model_group_pair():
    with pytest.raises(ValueError, match="declare their model group"):
        GpuModelSchedulerAdapter(
            raptor=FakeAdapter(ModelGroup.MINERU),  # type: ignore[arg-type]
            mineru=FakeAdapter(ModelGroup.MINERU),  # type: ignore[arg-type]
        )


def test_protocol_contracts_are_importable_for_real_adapters():
    assert RaptorOllamaAdapter
    assert MineruAuthorizedRpcAdapter


def test_context_requires_non_empty_lease_token_and_job():
    with pytest.raises(ValueError, match="required"):
        GpuExecutionContext("", "fence-1", "job-1")


def test_context_is_bound_to_running_group_and_execution():
    scheduler, _, _ = _adapter()
    owner = GpuExecutionContext("lease-1", "fence-1", "job-1")
    stale = GpuExecutionContext("lease-2", "fence-2", "job-2")
    scheduler.switch_to(ModelGroup.RAPTOR, owner)

    with pytest.raises(ModelLifecycleError, match="context"):
        scheduler.switch_to(ModelGroup.RAPTOR, stale)
    with pytest.raises(ModelLifecycleError, match="context"):
        scheduler.acquire_batch(ModelGroup.RAPTOR, ["job-2"], stale)
    with pytest.raises(ModelLifecycleError, match="context"):
        scheduler.execute(ModelGroup.RAPTOR, stale, call=lambda: {"ok": True})


def test_adapter_exception_is_fail_closed():
    class ExplodingAdapter(FakeAdapter):
        def warmup(self, context: GpuExecutionContext) -> WarmupAck:
            self.calls.append(("warmup", context))
            raise TimeoutError("warmup timeout")

    scheduler, _, _ = _adapter(mineru=ExplodingAdapter(ModelGroup.MINERU))
    context = GpuExecutionContext("lease-1", "fence-1", "job-1")

    with pytest.raises(ModelLifecycleError, match="warmup timeout"):
        scheduler.switch_to(ModelGroup.MINERU, context)
    assert scheduler.state.status == ModelGroupStatus.FAILED
    assert scheduler.state.error == "warmup timeout"


def test_concurrent_switches_are_serialized():
    scheduler, raptor, mineru = _adapter()
    context = GpuExecutionContext("lease-1", "fence-1", "job-1")

    with ThreadPoolExecutor(max_workers=2) as pool:
        states = list(
            pool.map(
                lambda group: scheduler.switch_to(group, context),
                [ModelGroup.RAPTOR, ModelGroup.MINERU],
            )
        )

    assert scheduler.state.status == ModelGroupStatus.RUNNING
    assert scheduler.state.model_group == states[-1].model_group
    assert [name for name, _ in raptor.calls + mineru.calls].count("load") == 2
    assert [name for name, _ in raptor.calls + mineru.calls].count("warmup") == 2


def test_execute_validator_rejects_forged_authorization_result():
    scheduler, _, _ = _adapter()
    context = GpuExecutionContext("lease-1", "fence-1", "job-1")
    scheduler.switch_to(ModelGroup.MINERU, context)
    scheduler.acquire_batch(ModelGroup.MINERU, ["job-1"], context)

    with pytest.raises(ModelLifecycleError, match="authorization"):
        scheduler.execute(
            ModelGroup.MINERU,
            context,
            call=lambda: {"ok": True},
            _validate_result=validate_authorized_result,
        )


def test_same_owner_job_must_be_registered_in_batch_before_execute():
    scheduler, _, _ = _adapter()
    owner_job = GpuExecutionContext("lease-1", "fence-1", "job-1")
    other_job = GpuExecutionContext("lease-1", "fence-1", "job-2")
    scheduler.switch_to(ModelGroup.RAPTOR, owner_job)

    with pytest.raises(ModelLifecycleError, match="acquire a model batch"):
        scheduler.execute(ModelGroup.RAPTOR, other_job, call=lambda: {"ok": True})

    scheduler.acquire_batch(ModelGroup.RAPTOR, ["job-2"], other_job)
    assert scheduler.execute(ModelGroup.RAPTOR, other_job, call=lambda: {"ok": True}) == {"ok": True}


class OomExplodingAdapter(FakeAdapter):
    def __init__(self, model_group: ModelGroup, *, message: str = "CUDA error: out of memory"):
        super().__init__(model_group)
        self.message = message

    def execute(self, context: GpuExecutionContext, **kwargs: object) -> object:
        self.calls.append(("execute", context))
        raise RuntimeError(self.message)


def test_execute_oom_releases_reprobes_and_raises_gpu_oom():
    scheduler, raptor, _ = _adapter(raptor=OomExplodingAdapter(ModelGroup.RAPTOR))
    context = GpuExecutionContext("lease-1", "fence-1", "job-1")
    scheduler.switch_to(ModelGroup.RAPTOR, context)
    scheduler.acquire_batch(ModelGroup.RAPTOR, ["job-1"], context)

    with pytest.raises(GpuOomError) as excinfo:
        scheduler.execute(ModelGroup.RAPTOR, context, call=lambda: {"ok": True})

    assert "out of memory" in str(excinfo.value)
    assert "lease-1" in str(excinfo.value)
    assert "job-1" in str(excinfo.value)
    assert "total_mb=8192" in str(excinfo.value)
    assert [name for name, _ in raptor.calls] == ["load", "warmup", "execute", "unload"]
    assert scheduler.state.status == ModelGroupStatus.FAILED
    assert scheduler.state.error is not None
    assert scheduler.resident_groups == ()


def test_execute_oom_clears_resident_group_and_reloads_on_next_switch():
    scheduler, _, mineru = _adapter(mineru=OomExplodingAdapter(ModelGroup.MINERU))
    scheduler.set_resident_mode(True)
    context = GpuExecutionContext("lease-1", "fence-1", "job-1")
    scheduler.switch_to(ModelGroup.MINERU, context)
    assert scheduler.resident_groups == (ModelGroup.MINERU,)
    scheduler.acquire_batch(ModelGroup.MINERU, ["job-1"], context)

    with pytest.raises(GpuOomError):
        scheduler.execute(ModelGroup.MINERU, context, call=lambda: {"ok": True})

    assert scheduler.resident_groups == ()
    # OOM 后常驻失效：下一次 switch_to 必须重新 load/warmup。
    scheduler.switch_to(ModelGroup.MINERU, context)
    assert scheduler.state.status == ModelGroupStatus.RUNNING
    assert [name for name, _ in mineru.calls].count("load") == 2
    assert [name for name, _ in mineru.calls].count("warmup") == 2


def test_execute_non_oom_exception_keeps_running_state_without_unload():
    def _boom() -> object:
        raise RuntimeError("boom")

    scheduler, raptor, _ = _adapter()
    context = GpuExecutionContext("lease-1", "fence-1", "job-1")
    scheduler.switch_to(ModelGroup.RAPTOR, context)
    scheduler.acquire_batch(ModelGroup.RAPTOR, ["job-1"], context)

    with pytest.raises(RuntimeError, match="boom"):
        scheduler.execute(ModelGroup.RAPTOR, context, call=_boom)

    assert scheduler.state.status == ModelGroupStatus.RUNNING
    assert [name for name, _ in raptor.calls] == ["load", "warmup", "execute"]


def test_switch_load_oom_raises_gpu_oom_and_reprobes():
    class LoadOomAdapter(FakeAdapter):
        def load(self, context: GpuExecutionContext) -> LoadAck:
            self.calls.append(("load", context))
            raise RuntimeError("CUDA out of memory")

    scheduler, _, _ = _adapter(mineru=LoadOomAdapter(ModelGroup.MINERU))
    context = GpuExecutionContext("lease-1", "fence-1", "job-1")

    with pytest.raises(GpuOomError, match="out of memory"):
        scheduler.switch_to(ModelGroup.MINERU, context)

    assert scheduler.state.status == ModelGroupStatus.FAILED
    assert scheduler.state.model_group == ModelGroup.MINERU


def test_switch_warmup_failure_reprobes_and_keeps_waiting_error():
    scheduler, _, _ = _adapter(mineru=FakeAdapter(ModelGroup.MINERU, warmup_ok=False))
    context = GpuExecutionContext("lease-1", "fence-1", "job-1")

    with pytest.raises(GpuWaitingError, match="warmup"):
        scheduler.switch_to(ModelGroup.MINERU, context)

    assert scheduler.state.status == ModelGroupStatus.FAILED
    assert scheduler.resident_groups == ()
