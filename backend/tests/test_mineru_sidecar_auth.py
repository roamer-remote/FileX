# Copyright (c) 2026 徐泽宇
"""164 §6：MinerU sidecar 授权 RPC 契约（缺少 lease/token/job 必须拒绝，回包回传同一上下文）。"""

from __future__ import annotations

import importlib.util
import json
import sys
import types
from pathlib import Path

import pytest

SIDECAR_DIR = Path(__file__).resolve().parents[2] / "docker" / "mineru-sidecar"


def _load_mq_consumer():
    spec = importlib.util.spec_from_file_location(
        "mineru_sidecar_mq_consumer",
        SIDECAR_DIR / "mq_consumer.py",
    )
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


@pytest.fixture(autouse=True)
def _sidecar_path():
    if str(SIDECAR_DIR) not in sys.path:
        sys.path.insert(0, str(SIDECAR_DIR))
    yield
    sys.modules.pop("mineru_sidecar_mq_consumer", None)


@pytest.fixture
def fake_runner():
    runner = types.SimpleNamespace()
    runner.SUPPORTED_RUNTIME_CONFIG_VERSION = 1
    calls: list[dict] = []

    def run_mineru_pipeline(*_args, **_kwargs):
        calls.append({"args": _args, "kwargs": dict(_kwargs)})
        return {"ok": True, "text": "parsed"}

    runner.run_mineru_pipeline = run_mineru_pipeline
    runner.calls = calls
    previous = sys.modules.get("mineru_runner")
    sys.modules["mineru_runner"] = runner
    yield runner
    if previous is None:
        sys.modules.pop("mineru_runner", None)
    else:
        sys.modules["mineru_runner"] = previous


def test_gpu_handle_message_rejects_missing_authorization_context(monkeypatch):
    monkeypatch.setenv("MINERU_DEVICE", "cuda")
    module = _load_mq_consumer()
    body = json.dumps({"file_path": "/uploads/a.pdf", "original_name": "a.pdf"}).encode()
    with pytest.raises(ValueError, match="mineru_authorization_context_missing"):
        module._handle_message(body)


def test_cpu_handle_message_allows_legacy_without_authorization_context(fake_runner):
    module = _load_mq_consumer()
    body = json.dumps({"file_path": "/tmp/1/doc.pdf", "original_name": "doc.pdf"}).encode()

    result = module._handle_message(body)

    assert result["text"] == "parsed"
    assert "gpu_lease_id" not in result
    assert "fencing_token" not in result
    assert "gpu_job_id" not in result


def test_handle_message_rejects_partial_authorization_context():
    module = _load_mq_consumer()
    body = json.dumps(
        {
            "file_path": "/uploads/a.pdf",
            "original_name": "a.pdf",
            "gpu_lease_id": "lease-1",
            "fencing_token": "",
            "gpu_job_id": "job-7",
        }
    ).encode()
    with pytest.raises(ValueError, match="mineru_authorization_context_missing"):
        module._handle_message(body)


def test_handle_message_echoes_authorization_context_in_reply(fake_runner):
    module = _load_mq_consumer()
    body = json.dumps(
        {
            "file_path": "/tmp/1/doc.pdf",
            "original_name": "doc.pdf",
            "file_id": 9,
            "job_id": 7,
            "gpu_lease_id": "lease-1",
            "fencing_token": "fence-1",
            "gpu_job_id": "job-7",
        }
    ).encode()

    result = module._handle_message(body)

    assert result["gpu_lease_id"] == "lease-1"
    assert result["fencing_token"] == "fence-1"
    assert result["gpu_job_id"] == "job-7"
    assert result["text"] == "parsed"
    assert fake_runner.calls[0]["args"][0] == "/tmp/1/doc.pdf"
    assert fake_runner.calls[0]["kwargs"]["file_id"] == 9
    assert fake_runner.calls[0]["kwargs"]["job_id"] == 7


def test_missing_authorization_is_non_retryable():
    module = _load_mq_consumer()
    assert module._is_retryable(ValueError("mineru_authorization_context_missing")) is False
