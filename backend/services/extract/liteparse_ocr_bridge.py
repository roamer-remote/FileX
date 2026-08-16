# Copyright (c) 2026 徐泽宇
"""LiteParse OCR API bridge: POST /ocr -> RapidOCR (see OCR_API_SPEC.md).

Authors:
    徐泽宇

Copyright:
    © 2026 徐泽宇
"""

from __future__ import annotations

import logging
import threading

from fastapi import FastAPI, File, Form, UploadFile
from fastapi.responses import JSONResponse

from config import KB_EXTRACT_LITEPARSE_OCR_HOST, KB_EXTRACT_LITEPARSE_OCR_PORT
from services.extract.ocr import ocr_image_bytes_for_liteparse

logger = logging.getLogger(__name__)

app = FastAPI(title="FileX LiteParse OCR Bridge", docs_url=None, redoc_url=None)

_bridge_thread: threading.Thread | None = None
_bridge_started = False


@app.post("/ocr", response_model=None)
async def ocr_endpoint(
    file: UploadFile = File(...),
    language: str = Form("en"),
):
    data = await file.read()
    if not data:
        return JSONResponse(status_code=400, content={"error": "missing or empty file"})
    try:
        results = ocr_image_bytes_for_liteparse(data, language=language)
        return {"results": results}
    except Exception as exc:
        logger.exception("liteparse ocr bridge failed")
        return JSONResponse(status_code=500, content={"error": str(exc)[:500]})


def _run_uvicorn() -> None:
    import uvicorn

    uvicorn.run(
        app,
        host=KB_EXTRACT_LITEPARSE_OCR_HOST,
        port=KB_EXTRACT_LITEPARSE_OCR_PORT,
        log_level="warning",
        access_log=False,
    )


def _ocr_port_in_use() -> bool:
    import socket

    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.settimeout(0.3)
        return sock.connect_ex((KB_EXTRACT_LITEPARSE_OCR_HOST, KB_EXTRACT_LITEPARSE_OCR_PORT)) == 0


def start_liteparse_ocr_bridge() -> None:
    """Start OCR bridge in a daemon thread (idempotent)."""
    global _bridge_thread, _bridge_started
    if _bridge_started and _bridge_thread is not None and _bridge_thread.is_alive():
        return
    if _ocr_port_in_use():
        logger.info(
            "liteparse OCR bridge already listening on http://%s:%s/ocr — reusing",
            KB_EXTRACT_LITEPARSE_OCR_HOST,
            KB_EXTRACT_LITEPARSE_OCR_PORT,
        )
        _bridge_started = True
        return
    _bridge_thread = threading.Thread(target=_run_uvicorn, name="liteparse-ocr-bridge", daemon=True)
    _bridge_thread.start()
    _bridge_started = True
    logger.info(
        "liteparse OCR bridge listening on http://%s:%s/ocr",
        KB_EXTRACT_LITEPARSE_OCR_HOST,
        KB_EXTRACT_LITEPARSE_OCR_PORT,
    )
