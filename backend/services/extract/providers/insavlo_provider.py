# Copyright (c) 2026 徐泽宇
"""Insavlo extract provider: submit one file and return remote transaction metadata.

The Insavlo provider does **not** wait for extraction results. It submits the
file to Insavlo ``document_process/upload_and_process`` and returns the remote
``transaction_id`` / ``file_id`` so the caller (``run_extract_job``) can persist
them atomically and move the job to ``waiting_webhook``. Result write-back is
handled later by the webhook receiver (feature 044 stage 4).

Failure semantics: this provider never falls back to legacy extraction. Any
submission error is raised so the caller marks the job/file failed with a clear
``extract_error``.
"""

from __future__ import annotations

import logging
import os
from dataclasses import dataclass
from datetime import datetime
from typing import Any

import httpx
from sqlalchemy.orm import Session

from config import KB_EXTRACT_INSAVLO_HTTP_TIMEOUT_SEC, KB_EXTRACT_INSAVLO_MAX_FILE_BYTES
from models.file import File as FileModel
from services.extract.policy import get_extension_from_file
from services.file_service import get_extension
from utils.timezone import naive_db_now

logger = logging.getLogger(__name__)

INSAVLO_SUPPORTED_EXTENSIONS = frozenset({"pdf", "jpg", "jpeg", "png", "doc", "docx"})

INSAVLO_UPLOAD_PATH = "/document_process/upload_and_process"


@dataclass(frozen=True)
class InsavloSubmission:
    transaction_id: str
    file_id: str | None
    skill_code: str
    submitted_at: datetime


class InsavloSubmissionError(RuntimeError):
    """Raised when Insavlo submission cannot complete (config/format/HTTP/supplier)."""


def _file_extension(f: FileModel) -> str:
    return get_extension_from_file(f) or get_extension(f.original_name or f.filename or "")


def _validate_file(f: FileModel) -> None:
    ext = _file_extension(f)
    if ext not in INSAVLO_SUPPORTED_EXTENSIONS:
        raise InsavloSubmissionError(
            f"Insavlo 不支持该文件类型（.{ext or '未知'}），仅支持 "
            f"{', '.join(sorted(INSAVLO_SUPPORTED_EXTENSIONS))}"
        )
    # 以磁盘实际大小为权威（紧接就要 open 源文件上传）；DB file_size 仅作回退，
    # 避免「DB 偏小、磁盘超大」绕过本地 50 MiB 预检（stage3 review Major #1）。
    size = 0
    if f.file_path:
        try:
            size = os.path.getsize(f.file_path)
        except OSError:
            size = 0
    if size <= 0:
        size = int(f.file_size or 0)
    if size <= 0:
        raise InsavloSubmissionError("Insavlo 提交失败：文件大小为 0 或无法读取")
    if size > KB_EXTRACT_INSAVLO_MAX_FILE_BYTES:
        max_mb = KB_EXTRACT_INSAVLO_MAX_FILE_BYTES // (1024 * 1024)
        raise InsavloSubmissionError(
            f"Insavlo 单文件上限 {max_mb} MiB，当前文件 {size} 字节超出限制"
        )
    if not f.file_path or not os.path.isfile(f.file_path):
        raise InsavloSubmissionError(f"Insavlo 提交失败：源文件不存在 {f.file_path}")


def _parse_submission_response(payload: dict[str, Any], skill_code: str) -> InsavloSubmission:
    if not payload.get("success", False):
        msg = payload.get("error") or payload.get("message") or "Insavlo 返回 success=false"
        raise InsavloSubmissionError(f"Insavlo 提交失败：{msg}")
    transaction_id = str(payload.get("transaction_id") or "").strip()
    if not transaction_id:
        raise InsavloSubmissionError("Insavlo 响应缺少 transaction_id")
    files = payload.get("files") or []
    remote_file_id: str | None = None
    if isinstance(files, list) and files:
        first = files[0]
        if isinstance(first, dict):
            remote_file_id = str(first.get("file_id") or "").strip() or None
    return InsavloSubmission(
        transaction_id=transaction_id,
        file_id=remote_file_id,
        skill_code=skill_code,
        submitted_at=naive_db_now(),
    )


def submit_insavlo_extract(
    f: FileModel,
    db: Session,
    *,
    job_id: int | None = None,
) -> InsavloSubmission:
    """Submit one file to Insavlo and return remote transaction metadata.

    Pre-flight checks (format / size / runtime readiness) run before any HTTP
    call. The HTTP request targets ``{base_url}/document_process/upload_and_process``
    with ``files[]``, ``skill_code`` and ``callback_url`` form fields, using the
    decrypted Bearer API key. On any failure the function raises
    ``InsavloSubmissionError`` so the caller writes a clear ``extract_error``
    without legacy fallback.
    """
    from services.insavlo_config_service import (
        get_insavlo_runtime_config,
        is_insavlo_runtime_ready,
    )

    if not is_insavlo_runtime_ready(db):
        raise InsavloSubmissionError(
            "Insavlo 提取不可用：管理员配置未启用或不完整，请联系管理员"
        )

    _validate_file(f)

    cfg = get_insavlo_runtime_config(db)
    url = f"{cfg.base_url}{INSAVLO_UPLOAD_PATH}"
    original_name = f.original_name or f.filename or "document"

    timeout = max(30.0, float(KB_EXTRACT_INSAVLO_HTTP_TIMEOUT_SEC))
    try:
        with open(f.file_path, "rb") as fh:
            files = {"files[]": (original_name, fh)}
            data = {
                "skill_code": cfg.skill_code,
                "callback_url": cfg.callback_url,
            }
            with httpx.Client(timeout=timeout) as client:
                resp = client.post(
                    url,
                    files=files,
                    data=data,
                    headers={"Authorization": f"Bearer {cfg.api_key}"},
                )
    except OSError as exc:
        logger.warning("insavlo submit open file failed file_id=%s: %s", f.id, exc)
        raise InsavloSubmissionError(f"Insavlo 提交失败：无法读取源文件 ({exc})") from exc
    except httpx.HTTPError as exc:
        logger.warning("insavlo submit http error file_id=%s: %s", f.id, exc)
        raise InsavloSubmissionError(f"Insavlo 提交请求失败：{exc}") from exc

    if resp.status_code >= 400:
        body_preview = resp.text[:500] if resp.text else ""
        logger.warning(
            "insavlo submit http %s file_id=%s body=%s",
            resp.status_code,
            f.id,
            body_preview,
        )
        raise InsavloSubmissionError(
            f"Insavlo 提交失败：HTTP {resp.status_code} {body_preview}".rstrip()
        )

    try:
        payload = resp.json()
    except ValueError as exc:
        raise InsavloSubmissionError("Insavlo 响应不是合法 JSON") from exc

    submission = _parse_submission_response(payload, cfg.skill_code)
    logger.info(
        "insavlo submit ok file_id=%s job_id=%s transaction_id=%s remote_file_id=%s",
        f.id,
        job_id,
        submission.transaction_id,
        submission.file_id,
    )
    return submission
