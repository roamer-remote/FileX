# Copyright (c) 2026 徐泽宇
"""Default runtime must never claim unverified model lifecycle success."""

from __future__ import annotations

import pytest

from services.gpu_scheduler_runtime import GpuSchedulerRuntime
from services.gpu_scheduler_runtime import RuntimeLifecycleOperations
from services.gpu_model_lifecycle_service import (
    GpuExecutionContext,
    ModelGroup,
    ModelLifecycleError,
    LoadAck,
    ReleaseAck,
    WarmupAck,
)


def test_unconfigured_runtime_fails_closed_before_gpu_execution():
    runtime = GpuSchedulerRuntime()
    context = runtime.context_for_job("job-1")

    assert runtime.lifecycle_configured is False
    with pytest.raises(ModelLifecycleError, match="transition failed"):
        runtime.scheduler.switch_to(ModelGroup.MINERU, context)

    assert runtime.scheduler.state.error == "runtime_lifecycle_unconfigured"


def test_runtime_context_uses_single_owner_but_distinct_jobs():
    runtime = GpuSchedulerRuntime()
    first = runtime.context_for_job("job-1")
    second = runtime.context_for_job("job-2")

    assert first.owner_key == second.owner_key
    assert first.job_id != second.job_id


def test_runtime_context_carries_task_models_from_runtime_settings():
    runtime = GpuSchedulerRuntime()

    context = runtime.context_for_job(
        "job-1",
        model="db:qwen",
        embed_model="db:bge",
    )

    assert context.model == "db:qwen"
    assert context.embed_model == "db:bge"


def test_configured_runtime_passes_real_lifecycle_acks_to_scheduler():
    calls: list[str] = []

    def operations(group):
        return RuntimeLifecycleOperations(
            model_group=group,
            load=lambda _ctx: (calls.append(f"{group}:load"), LoadAck(True))[1],
            warmup=lambda _ctx: (calls.append(f"{group}:warmup"), WarmupAck(True))[1],
            unload=lambda _ctx: (calls.append(f"{group}:unload"), ReleaseAck(True))[1],
        )

    runtime = GpuSchedulerRuntime(
        raptor_operations=operations(ModelGroup.RAPTOR),
        mineru_operations=operations(ModelGroup.MINERU),
    )
    context = runtime.context_for_job("job-1")
    runtime.scheduler.switch_to(ModelGroup.RAPTOR, context)
    runtime.scheduler.acquire_batch(ModelGroup.RAPTOR, ["job-1"], context)
    runtime.scheduler.execute(ModelGroup.RAPTOR, context, call=lambda: {"ok": True})

    assert runtime.lifecycle_configured is True
    assert calls == ["raptor:load", "raptor:warmup"]


def test_scheduler_for_job_returns_none_when_disabled(monkeypatch):
    monkeypatch.setattr("config.GPU_SCHEDULER_ENABLED", False)

    from services.gpu_scheduler_runtime import scheduler_for_job

    assert scheduler_for_job(1) == (None, None)


def test_scheduler_for_job_resolves_task_models_from_db_runtime(monkeypatch):
    from services.gpu_scheduler_runtime import scheduler_for_job
    from services.ollama_config_service import OllamaRuntimeConfig

    runtime = GpuSchedulerRuntime()
    monkeypatch.setattr("config.GPU_SCHEDULER_ENABLED", True)
    monkeypatch.setattr("services.gpu_scheduler_runtime.get_gpu_scheduler_runtime", lambda: runtime)
    monkeypatch.setattr(
        "services.ollama_config_service.get_ollama_runtime_config",
        lambda _db, fresh=False: OllamaRuntimeConfig(
            base_url="http://ollama",
            embed_model="db:bge",
            embed_dim=1024,
            chat_model="db:qwen",
            timeout_sec=120,
            embed_batch_size=8,
        ),
    )

    _, context = scheduler_for_job(7, db=object())

    assert context is not None
    assert context.model == "db:qwen"
    assert context.embed_model == "db:bge"


def test_scheduler_for_job_db_models_override_environment_models(db_session, monkeypatch):
    from services.gpu_scheduler_runtime import scheduler_for_job
    from services.system_setting_service import (
        KEY_OLLAMA_CHAT_MODEL,
        KEY_OLLAMA_EMBED_MODEL,
        update_settings,
    )

    update_settings(
        db_session,
        {
            KEY_OLLAMA_CHAT_MODEL: "db:qwen",
            KEY_OLLAMA_EMBED_MODEL: "db:bge",
        },
    )
    monkeypatch.setenv("OLLAMA_CHAT_MODEL", "env:qwen")
    monkeypatch.setenv("OLLAMA_EMBED_MODEL", "env:bge")
    runtime = GpuSchedulerRuntime()
    monkeypatch.setattr("config.GPU_SCHEDULER_ENABLED", True)
    monkeypatch.setattr("services.gpu_scheduler_runtime.get_gpu_scheduler_runtime", lambda: runtime)

    _, context = scheduler_for_job(8, db=db_session)

    assert context is not None
    assert context.model == "db:qwen"
    assert context.embed_model == "db:bge"
