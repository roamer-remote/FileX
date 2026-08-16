# Copyright (c) 2026 徐泽宇
"""Concrete Ollama/MinerU lifecycle operation tests."""

from __future__ import annotations

from services.gpu_concrete_lifecycle import MineruConcreteLifecycle, OllamaConcreteLifecycle
from services.gpu_model_lifecycle_service import GpuExecutionContext


class Response:
    def __init__(self, body=None):
        self.body = body or {}

    def raise_for_status(self):
        return None

    def json(self):
        return self.body


def test_ollama_lifecycle_requires_gpu_vram_and_confirms_unload(monkeypatch):
    lifecycle = OllamaConcreteLifecycle(base_url="http://ollama", model="qwen:9b")
    context = GpuExecutionContext("lease-1", "fence-1", "job-1")
    ps = [{"name": "qwen:9b", "size_vram": 1024}]
    captured: list[tuple[dict, dict | None]] = []

    def fake_post(payload, *, headers=None):
        captured.append((payload, headers))
        return Response()

    monkeypatch.setattr(lifecycle, "_post", fake_post)
    monkeypatch.setattr(lifecycle, "_ps", lambda: list(ps))

    assert lifecycle.load(context).accepted is True
    assert lifecycle.warmup(context).healthy is True
    # lease/fencing/job 上下文必须作为 HTTP 头传递，不能放进 Ollama 的
    # context 字段（Ollama 只接受 []int token 列表，dict 会 400；WHB 实测）。
    for payload, headers in captured:
        assert "context" not in payload
        assert headers == {
            "X-FileX-GPU-Lease-ID": "lease-1",
            "X-FileX-Fencing-Token": "fence-1",
            "X-FileX-GPU-Job-ID": "job-1",
        }
    ps.clear()
    assert lifecycle.unload(context).acknowledged is True


def test_ollama_warmup_rejects_cpu_only_runner(monkeypatch):
    lifecycle = OllamaConcreteLifecycle(base_url="http://ollama", model="qwen:9b")
    context = GpuExecutionContext("lease-1", "fence-1", "job-1")
    monkeypatch.setattr(lifecycle, "_post", lambda _payload, **_kwargs: Response())
    monkeypatch.setattr(lifecycle, "_ps", lambda: [{"name": "qwen:9b", "size_vram": 0}])

    result = lifecycle.warmup(context)
    assert result.healthy is False
    assert result.detail == "ollama_warmup_not_on_gpu"


def test_ollama_lifecycle_uses_task_model_from_system_settings_context(monkeypatch):
    lifecycle = OllamaConcreteLifecycle(base_url="http://ollama", model="env:qwen")
    context = GpuExecutionContext("lease-1", "fence-1", "job-1", model="db:qwen")
    captured: list[dict] = []

    def fake_post(payload, *, headers=None):
        captured.append(payload)
        return Response()

    monkeypatch.setattr(lifecycle, "_post", fake_post)
    monkeypatch.setattr(lifecycle, "_ps", lambda: [{"name": "db:qwen", "size_vram": 1024}])

    assert lifecycle.load(context).accepted is True
    assert captured[0]["model"] == "db:qwen"


def test_mineru_lifecycle_requires_sidecar_ack(monkeypatch):
    lifecycle = MineruConcreteLifecycle(
        base_url="http://mineru",
        ollama_base_url="http://ollama",
        chat_model="qwen:9b",
        embed_model="bge:latest",
    )
    context = GpuExecutionContext("lease-1", "fence-1", "job-1")
    responses = {
        "load": {"accepted": True},
        "warmup": {"healthy": True},
        "unload": {"acknowledged": True},
    }
    monkeypatch.setattr(lifecycle, "_ollama_unload", lambda model: None)
    monkeypatch.setattr(lifecycle, "_ollama_ps", lambda: [])
    monkeypatch.setattr(lifecycle, "_call", lambda action, _context: responses[action])

    assert lifecycle.load(context).accepted is True
    assert lifecycle.warmup(context).healthy is True
    assert lifecycle.unload(context).acknowledged is True


def test_mineru_load_unloads_resident_ollama_models_before_sidecar(monkeypatch):
    """冷启动（scheduler 状态 none）下 MinerU load 必须先卸载常驻 Ollama 模型，
    否则 8GiB Low 档 MinerU 加载 OOM（WHB T-9 实测 CUDA out of memory）。"""
    lifecycle = MineruConcreteLifecycle(
        base_url="http://mineru",
        ollama_base_url="http://ollama",
        chat_model="qwen:9b",
        embed_model="bge:latest",
    )
    context = GpuExecutionContext("lease-1", "fence-1", "job-1")
    unloaded: list[str] = []
    ps = [{"name": "qwen:9b"}, {"name": "bge:latest"}]
    sidecar_calls: list[str] = []

    def fake_unload(model):
        unloaded.append(model)
        ps[:] = [m for m in ps if m["name"] != model]

    monkeypatch.setattr(lifecycle, "_ollama_unload", fake_unload)
    monkeypatch.setattr(lifecycle, "_ollama_ps", lambda: list(ps))

    def fake_call(action, _context):
        sidecar_calls.append(action)
        return {"accepted": True}

    monkeypatch.setattr(lifecycle, "_call", fake_call)

    ack = lifecycle.load(context)
    assert ack.accepted is True
    assert sorted(unloaded) == ["bge:latest", "qwen:9b"]
    assert sidecar_calls == ["load"]


def test_mineru_lifecycle_uses_task_chat_and_embed_models(monkeypatch):
    lifecycle = MineruConcreteLifecycle(
        base_url="http://mineru",
        ollama_base_url="http://ollama",
        chat_model="env:qwen",
        embed_model="env:bge",
    )
    context = GpuExecutionContext(
        "lease-1",
        "fence-1",
        "job-1",
        model="db:qwen",
        embed_model="db:bge",
    )
    unloaded: list[str] = []
    ps = [{"name": "db:qwen"}, {"name": "db:bge"}]

    def fake_unload(model):
        unloaded.append(model)
        ps[:] = [item for item in ps if item["name"] != model]

    monkeypatch.setattr(lifecycle, "_ollama_unload", fake_unload)
    monkeypatch.setattr(lifecycle, "_ollama_ps", lambda: list(ps))
    monkeypatch.setattr(lifecycle, "_call", lambda _action, _context: {"accepted": True})

    assert lifecycle.load(context).accepted is True
    assert sorted(unloaded) == ["db:bge", "db:qwen"]


def test_mineru_load_fails_closed_when_ollama_still_resident(monkeypatch):
    """Ollama 模型未确认离驻留时，MinerU load 必须 fail-closed（不调用 sidecar）。"""
    lifecycle = MineruConcreteLifecycle(
        base_url="http://mineru",
        ollama_base_url="http://ollama",
        chat_model="qwen:9b",
        embed_model="bge:latest",
    )
    context = GpuExecutionContext("lease-1", "fence-1", "job-1")
    monkeypatch.setattr(lifecycle, "_ollama_unload", lambda model: None)
    monkeypatch.setattr(
        lifecycle,
        "_ollama_ps",
        lambda: [{"name": "qwen:9b"}, {"name": "bge:latest"}],
    )
    sidecar_calls: list[str] = []
    monkeypatch.setattr(
        lifecycle,
        "_call",
        lambda action, _context: sidecar_calls.append(action) or {"accepted": True},
    )

    ack = lifecycle.load(context)
    assert ack.accepted is False
    assert ack.detail == "ollama_release_not_confirmed"
    assert sidecar_calls == []
