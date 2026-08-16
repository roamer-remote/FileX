# Copyright (c) 2026 徐泽宇
"""FileX Docling sidecar: /health, debug /extract, kb.docling consumer."""
from __future__ import annotations

import logging
import os
import re
import tempfile
from pathlib import Path

from fastapi import FastAPI, File, Form, HTTPException, UploadFile

from docling_runner import run_docling_pipeline
from logging_setup import setup_logging
from mq_consumer import start_mq_consumer_thread

setup_logging(service_name=os.environ.get("FILEX_SERVICE_NAME") or "filex-docling")
logger = logging.getLogger(__name__)

_HEALTH_ACCESS_RE = re.compile(r'"\w+ /health(?:[?\s]| HTTP)')


class _HealthAccessLogFilter(logging.Filter):
    def filter(self, record: logging.LogRecord) -> bool:
        return _HEALTH_ACCESS_RE.search(record.getMessage()) is None


app = FastAPI(title="filex-docling-sidecar", version="0.1.0")

MAX_EXTRACT_UPLOAD_BYTES = int(os.environ.get("DOCLING_HTTP_MAX_UPLOAD_BYTES", str(50 * 1024 * 1024)))


@app.on_event("startup")
def _startup() -> None:
    logging.getLogger("uvicorn.access").addFilter(_HealthAccessLogFilter())
    if (os.environ.get("RABBITMQ_URL") or "").strip():
        start_mq_consumer_thread()
        logger.info("started kb.docling consumer thread")


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok"}


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
            detail=f"upload exceeds {MAX_EXTRACT_UPLOAD_BYTES} bytes; use kb.docling MQ for large files",
        )
    with tempfile.NamedTemporaryFile(delete=False, suffix=suffix) as tmp:
        tmp.write(content)
        tmp_path = tmp.name
    try:
        return run_docling_pipeline(
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
