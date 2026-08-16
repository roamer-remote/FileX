# Copyright (c) 2026 徐泽宇
"""FileX MinerU CPU sidecar: /health, debug /extract, kb.mineru consumer."""
from __future__ import annotations

import logging
import os
import re
import tempfile
from pathlib import Path

from fastapi import FastAPI, File, Form, HTTPException, UploadFile
from importlib import metadata as importlib_metadata

from logging_setup import setup_logging
from mineru_runner import run_mineru_pipeline
from mq_consumer import start_mq_consumer_thread

setup_logging(service_name=os.environ.get("FILEX_SERVICE_NAME") or "filex-mineru")
logger = logging.getLogger(__name__)

# MinerU 的运行时版本号（必须从本进程内 MinerU 库实际安装版本动态获取）
# 绝不是 FileX 系统版本，也不是 sidecar 应用版本。
_MINERU_VERSION: str = "unknown"
try:
    _MINERU_VERSION = importlib_metadata.version("mineru")
except importlib_metadata.PackageNotFoundError:
    pass

# Path-boundary match: /health but not /health-check or /healthz
_HEALTH_ACCESS_RE = re.compile(r'"\w+ /health(?:[?\s]| HTTP)')


class _HealthAccessLogFilter(logging.Filter):
    """Drop Docker healthcheck access lines; keep /extract and other routes."""

    def filter(self, record: logging.LogRecord) -> bool:
        return _HEALTH_ACCESS_RE.search(record.getMessage()) is None


app = FastAPI(title="filex-mineru-sidecar", version="0.1.0")

# Debug HTTP only; production path is kb.mineru MQ RPC.
MAX_EXTRACT_UPLOAD_BYTES = int(os.environ.get("MINERU_HTTP_MAX_UPLOAD_BYTES", str(50 * 1024 * 1024)))


def _pipeline_models_ready() -> bool:
    """
    与 entrypoint.sh 中的 _models_ready 逻辑保持一致，用于 /health 暴露模型就绪状态。

    full 栈检查 PDF-Extract-Kit-1.0（包括历史 pipeline 兼容链接）；light 栈
    检查 a6 的四个 ONNX 仓库。两者都要求 entrypoint 写入完成标记。

    这样运维/监控可以通过 curl /health 直观看到模型是否就绪，
    即使容器已经启动，也能发现模型不完整的情况。
    """
    models_dir = Path(os.environ.get("MINERU_MODELS_DIR", "/models"))
    marker = models_dir / ".pipeline_complete"
    if not marker.is_file():
        return False
    if os.environ.get("MINERU_MODEL_STACK", "full") == "light":
        required = (
            "PP-DocLayoutV2_onnx",
            "PP-OCRv6_small_det_onnx",
            "PP-OCRv6_small_rec_onnx",
            "PP-FormulaNet_plus-M_onnx",
        )
        return all((models_dir / name).is_dir() and any((models_dir / name).iterdir()) for name in required)
    layout_v2 = models_dir / "PDF-Extract-Kit-1.0" / "models" / "Layout" / "PP-DocLayoutV2"
    ocr_det = models_dir / "PDF-Extract-Kit-1.0" / "models" / "OCR" / "paddleocr_torch" / "ch_PP-OCRv6_small_det_infer.safetensors"
    return layout_v2.is_dir() and any(layout_v2.iterdir()) and ocr_det.is_file()


@app.on_event("startup")
def _startup() -> None:
    logging.getLogger("uvicorn.access").addFilter(_HealthAccessLogFilter())

    # 启动时打印一次模型就绪状态，方便查看容器日志就知道模型是否完整
    models_ready = _pipeline_models_ready()
    models_dir = os.environ.get("MINERU_MODELS_DIR", "/models")
    logger.info(
        "startup complete | models_ready=%s | models_dir=%s | mineru_version=%s",
        models_ready,
        models_dir,
        _MINERU_VERSION,
    )

    if (os.environ.get("RABBITMQ_URL") or "").strip():
        start_mq_consumer_thread()
        logger.info("started kb.mineru consumer thread")


@app.get("/health")
def health() -> dict[str, object]:
    """
    健康检查端点（同时供 Docker HEALTHCHECK 和人工调试使用）。

    返回字段说明：
    - status: "ok" 表示进程存活
    - mineru_version: 容器内实际安装的 MinerU 库版本（非常重要，用于排查模型兼容性）
    - sidecar_version: 本 sidecar 代码版本
    - models_ready: pipeline 模型是否完整就绪（包含 PP-DocLayoutV2 等）
    - models_dir: 当前使用的模型目录（便于确认持久化卷是否正确挂载）
    """
    models_dir = os.environ.get("MINERU_MODELS_DIR", "/models")
    return {
        "status": "ok",
        "mineru_version": _MINERU_VERSION,
        "sidecar_version": app.version,
        "models_ready": _pipeline_models_ready(),
        "models_dir": models_dir,
    }


@app.get("/lifecycle/status")
def lifecycle_status() -> dict[str, object]:
    """只读执行轮状态（GPU watchdog 探针）：报告 sidecar 当前 active 轮次。

    sidecar 进程启动即加载 torch/CUDA，且 Ollama llama-server 按
    ``OLLAMA_KEEP_ALIVE=-1`` 常驻，nvidia-smi 的 “compute 进程为空”在 WHB
    部署中不可达；scheduler 崩溃恢复时以此确认 sidecar 侧旧 MinerU 轮已退出。
    查询失败/超时由调用方按无法确认（busy）处理，保持 fail-closed。
    """
    from lifecycle_state import active_jobs

    jobs = active_jobs()
    return {
        "status": "ok",
        "active_executions": len(jobs),
        "active_jobs": jobs,
    }


def _cuda_ready() -> bool:
    if os.environ.get("MINERU_DEVICE", "cpu").lower() != "cuda":
        return False
    try:
        import torch

        return bool(torch.cuda.is_available() and torch.cuda.device_count() > 0)
    except Exception:
        return False


@app.post("/lifecycle/load")
def lifecycle_load() -> dict[str, object]:
    """Acknowledge model readiness only after the persisted model set is valid."""
    ready = _pipeline_models_ready()
    return {"accepted": ready, "detail": "models_ready" if ready else "models_not_ready"}


@app.post("/lifecycle/warmup")
def lifecycle_warmup() -> dict[str, object]:
    """Run a real CUDA health probe; CPU-only sidecars cannot claim GPU warmup."""
    if not _pipeline_models_ready() or not _cuda_ready():
        return {"healthy": False, "detail": "models_or_cuda_not_ready"}
    try:
        import torch

        probe = torch.zeros((1,), device="cuda")
        probe.add_(1)
        torch.cuda.synchronize()
        allocated = int(torch.cuda.memory_allocated())
        del probe
        return {"healthy": True, "detail": "cuda_probe_ok", "memory_allocated": allocated}
    except Exception as exc:
        return {"healthy": False, "detail": f"cuda_probe_failed:{exc}"}


@app.post("/lifecycle/unload")
def lifecycle_unload() -> dict[str, object]:
    """Confirm no parse is active and release the sidecar CUDA allocator."""
    from lifecycle_state import active_executions

    active = active_executions()
    if active:
        return {"acknowledged": False, "detail": f"active_executions:{active}"}
    if not _cuda_ready():
        return {"acknowledged": False, "detail": "cuda_not_ready"}
    try:
        import torch

        torch.cuda.empty_cache()
        torch.cuda.synchronize()
        return {"acknowledged": int(torch.cuda.memory_allocated()) == 0, "detail": "cuda_cache_released"}
    except Exception as exc:
        return {"acknowledged": False, "detail": f"cuda_release_failed:{exc}"}


@app.post("/extract")
async def extract(
    file: UploadFile = File(...),
    bypass_cache: bool = Form(False),
) -> dict:
    suffix = Path(file.filename or "document.pdf").suffix or ".pdf"
    content = await file.read()
    if len(content) > MAX_EXTRACT_UPLOAD_BYTES:
        raise HTTPException(
            status_code=413,
            detail=f"upload exceeds {MAX_EXTRACT_UPLOAD_BYTES} bytes; use kb.mineru MQ for large files",
        )
    with tempfile.NamedTemporaryFile(delete=False, suffix=suffix) as tmp:
        tmp.write(content)
        tmp_path = tmp.name
    try:
        return run_mineru_pipeline(
            tmp_path,
            file.filename or "document",
            bypass_cache=bypass_cache,
        )
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc
    finally:
        try:
            os.unlink(tmp_path)
        except OSError:
            pass
