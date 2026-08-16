# Copyright (c) 2026 徐泽宇
"""Concrete GPU lifecycle operations for Ollama and the MinerU sidecar."""

from __future__ import annotations

import time
from typing import Any

import httpx

from config import (
    KB_EXTRACT_MINERU_URL,
    OLLAMA_BASE_URL,
    OLLAMA_CHAT_MODEL,
    OLLAMA_EMBED_MODEL,
)
from services.gpu_model_lifecycle_service import (
    GpuExecutionContext,
    LoadAck,
    ModelGroup,
    ReleaseAck,
    WarmupAck,
)
from services.gpu_scheduler_runtime import RuntimeLifecycleOperations


def _headers(context: GpuExecutionContext) -> dict[str, str]:
    return {
        "X-FileX-GPU-Lease-ID": context.gpu_lease_id,
        "X-FileX-Fencing-Token": context.fencing_token,
        "X-FileX-GPU-Job-ID": context.job_id,
    }


class OllamaConcreteLifecycle:
    def __init__(self, *, base_url: str = OLLAMA_BASE_URL, model: str = OLLAMA_CHAT_MODEL) -> None:
        self.base_url = base_url.rstrip("/")
        self.model = model
        self.timeout = httpx.Timeout(30.0, connect=5.0)

    def _model_for_context(self, context: GpuExecutionContext) -> str:
        return (context.model or self.model).strip()

    def _post(
        self,
        payload: dict[str, Any],
        *,
        headers: dict[str, str] | None = None,
    ) -> httpx.Response:
        with httpx.Client(timeout=self.timeout) as client:
            return client.post(
                f"{self.base_url}/api/generate",
                json=payload,
                headers=headers,
            )

    def _ps(self) -> list[dict[str, Any]]:
        with httpx.Client(timeout=self.timeout) as client:
            response = client.get(f"{self.base_url}/api/ps")
            response.raise_for_status()
            body = response.json()
        models = body.get("models") if isinstance(body, dict) else None
        return models if isinstance(models, list) else []

    def load(self, context: GpuExecutionContext) -> LoadAck:
        try:
            model = self._model_for_context(context)
            response = self._post(
                {
                    "model": model,
                    "prompt": "",
                    "stream": False,
                    "keep_alive": "10m",
                    "options": {"num_predict": 1},
                },
                headers=_headers(context),
            )
            response.raise_for_status()
            return LoadAck(True, "ollama_load_ack")
        except Exception as exc:
            return LoadAck(False, f"ollama_load_failed:{exc}")

    def warmup(self, context: GpuExecutionContext) -> WarmupAck:
        try:
            model = self._model_for_context(context)
            response = self._post(
                {
                    "model": model,
                    "prompt": "Reply with exactly: READY",
                    "stream": False,
                    "keep_alive": "10m",
                    "options": {"num_predict": 1},
                },
                headers=_headers(context),
            )
            response.raise_for_status()
            loaded = next((m for m in self._ps() if m.get("name") == model), None)
            if not loaded or int(loaded.get("size_vram") or 0) <= 0:
                return WarmupAck(False, "ollama_warmup_not_on_gpu")
            return WarmupAck(True, "ollama_warmup_gpu_ack")
        except Exception as exc:
            return WarmupAck(False, f"ollama_warmup_failed:{exc}")

    def unload(self, context: GpuExecutionContext) -> ReleaseAck:
        try:
            model = self._model_for_context(context)
            response = self._post(
                {
                    "model": model,
                    "prompt": "",
                    "stream": False,
                    "keep_alive": 0,
                },
                headers=_headers(context),
            )
            response.raise_for_status()
            deadline = time.monotonic() + 5.0
            while time.monotonic() < deadline:
                if not any(m.get("name") == model for m in self._ps()):
                    return ReleaseAck(True, "ollama_release_ack")
                time.sleep(0.1)
            return ReleaseAck(False, "ollama_release_not_confirmed")
        except Exception as exc:
            return ReleaseAck(False, f"ollama_release_failed:{exc}")

    def operations(self) -> RuntimeLifecycleOperations:
        return RuntimeLifecycleOperations(
            model_group=ModelGroup.RAPTOR,
            load=self.load,
            warmup=self.warmup,
            unload=self.unload,
        )


class MineruConcreteLifecycle:
    def __init__(
        self,
        *,
        base_url: str = KB_EXTRACT_MINERU_URL,
        ollama_base_url: str = OLLAMA_BASE_URL,
        chat_model: str = OLLAMA_CHAT_MODEL,
        embed_model: str = OLLAMA_EMBED_MODEL,
    ) -> None:
        self.base_url = base_url.rstrip("/")
        self.ollama_base_url = ollama_base_url.rstrip("/")
        self.chat_model = chat_model
        self.embed_model = embed_model
        self.timeout = httpx.Timeout(30.0, connect=5.0)

    def _models_for_context(self, context: GpuExecutionContext) -> tuple[str, str]:
        return (
            (context.model or self.chat_model).strip(),
            (context.embed_model or self.embed_model).strip(),
        )

    def _ollama_ps(self) -> list[dict[str, Any]]:
        with httpx.Client(timeout=self.timeout) as client:
            response = client.get(f"{self.ollama_base_url}/api/ps")
            response.raise_for_status()
            body = response.json()
        models = body.get("models") if isinstance(body, dict) else None
        return models if isinstance(models, list) else []

    def _ollama_unload(self, model: str) -> None:
        with httpx.Client(timeout=self.timeout) as client:
            response = client.post(
                f"{self.ollama_base_url}/api/generate",
                json={"model": model, "prompt": "", "stream": False, "keep_alive": 0},
            )
            response.raise_for_status()

    def _ensure_ollama_released(self, context: GpuExecutionContext) -> str | None:
        """让 Ollama 常驻模型（chat+embed）离驻留并确认；失败返回原因，成功返回 None。

        GPU 调度器冷启动时 in-memory 状态为 none，switch_to 不会触发 RAPTOR
        unload；若 Ollama 模型已按 OLLAMA_KEEP_ALIVE=-1 常驻，MinerU 直接加载
        会 OOM（WHB T-9 实测 CUDA out of memory）。因此在 MinerU load 前先执行
        可验证的 Ollama 释放，保证 8GiB Low 档严格串行互斥（spec §5.3）。
        """
        targets = self._models_for_context(context)
        for model in targets:
            if not model.strip():
                continue
            try:
                self._ollama_unload(model)
            except Exception as exc:
                return f"ollama_release_failed:{exc}"
        deadline = time.monotonic() + 5.0
        while time.monotonic() < deadline:
            try:
                loaded = {str(m.get("name") or "") for m in self._ollama_ps()}
            except Exception as exc:
                return f"ollama_release_failed:{exc}"
            if not any(model in loaded for model in targets if model.strip()):
                return None
            time.sleep(0.1)
        return "ollama_release_not_confirmed"

    def _call(self, action: str, context: GpuExecutionContext) -> dict[str, Any]:
        with httpx.Client(timeout=self.timeout) as client:
            response = client.post(
                f"{self.base_url}/lifecycle/{action}",
                headers=_headers(context),
                json={
                    "gpu_lease_id": context.gpu_lease_id,
                    "fencing_token": context.fencing_token,
                    "gpu_job_id": context.job_id,
                },
            )
            response.raise_for_status()
            body = response.json()
        if not isinstance(body, dict):
            raise RuntimeError("MinerU lifecycle returned a non-object response")
        return body

    def load(self, context: GpuExecutionContext) -> LoadAck:
        release_error = self._ensure_ollama_released(context)
        if release_error is not None:
            return LoadAck(False, release_error)
        try:
            body = self._call("load", context)
            return LoadAck(bool(body.get("accepted")), str(body.get("detail") or "mineru_load_ack"))
        except Exception as exc:
            return LoadAck(False, f"mineru_load_failed:{exc}")

    def warmup(self, context: GpuExecutionContext) -> WarmupAck:
        try:
            body = self._call("warmup", context)
            return WarmupAck(bool(body.get("healthy")), str(body.get("detail") or "mineru_warmup_ack"))
        except Exception as exc:
            return WarmupAck(False, f"mineru_warmup_failed:{exc}")

    def unload(self, context: GpuExecutionContext) -> ReleaseAck:
        try:
            body = self._call("unload", context)
            return ReleaseAck(bool(body.get("acknowledged")), str(body.get("detail") or "mineru_release_ack"))
        except Exception as exc:
            return ReleaseAck(False, f"mineru_release_failed:{exc}")

    def operations(self) -> RuntimeLifecycleOperations:
        return RuntimeLifecycleOperations(
            model_group=ModelGroup.MINERU,
            load=self.load,
            warmup=self.warmup,
            unload=self.unload,
        )


def build_concrete_lifecycle_operations() -> tuple[RuntimeLifecycleOperations | None, RuntimeLifecycleOperations | None]:
    """Build both concrete adapters only when their endpoints are configured."""
    if not OLLAMA_BASE_URL.strip() or not KB_EXTRACT_MINERU_URL.strip():
        return None, None
    return OllamaConcreteLifecycle().operations(), MineruConcreteLifecycle().operations()
