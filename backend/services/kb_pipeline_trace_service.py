# Copyright (c) 2026 徐泽宇
"""086 Phase 1: single-file KB pipeline trace."""

from __future__ import annotations

import logging
import os
from datetime import datetime

from sqlalchemy.orm import Session

from models.file import File as FileModel
from models.kb_extract_job import KbExtractJob
from models.kb_index_job import KbIndexJob
from models.kb_post_job import KbPostJob
from models.operation_log import OperationLog
from schemas.kb_pipeline_visualization import FilePipelineTraceResponse, PipelineTraceStep
from services.kb_quality_manifest_service import (
    ManifestReadError,
    build_extraction_manifest,
)
from services.kb_pipeline_log_service import (
    ACTION_KB_EXTRACT_DONE,
    ACTION_KB_INDEX_DONE,
    ACTION_KB_INDEX_ERROR,
    ACTION_KB_INDEX_SKIP,
    ACTION_KB_POST_DONE,
    ACTION_KB_POST_ERROR,
    ACTION_KB_POST_SKIP,
)
from services.kb_pipeline_service import resolve_extract_provider
from services.md_paths import md_note_path, resolve_concept_sidecar_path, resolve_upload_path
from services.system_setting_service import get_kb_extract_provider
from utils.timezone import BEIJING_TZ, to_beijing_time

logger = logging.getLogger(__name__)

_INDEX_PERF_INT_KEYS = (
    "embed_ms",
    "persist_ms",
)
_POST_PERF_INT_KEYS = (
    "post_index_ms",
    "post_entity_ms",
    "post_sag_ms",
    "post_raptor_ms",
)


def _step_status_from_file_status(status: str) -> str:
    normalized = (status or "").lower()
    if normalized in {"ready", "indexed", "done"}:
        return "finish"
    if normalized in {"failed", "error"}:
        return "error"
    if normalized in {"skipped", "not_needed"}:
        return "skip"
    if normalized in {"pending", "queued", "extracting", "indexing", "running", "waiting_webhook"}:
        return "process"
    return "wait"


def _pick_error(*values: str | None) -> str | None:
    for value in values:
        if value and str(value).strip():
            return str(value).strip()
    return None


def _admin_logs_deep_link(user_id: int) -> str:
    return f"/admin/logs?tab=logs&user_id={user_id}"


def _latest_extract_job(db: Session, file_id: int) -> KbExtractJob | None:
    return (
        db.query(KbExtractJob)
        .filter(KbExtractJob.file_id == file_id)
        .order_by(KbExtractJob.id.desc())
        .first()
    )


def _latest_post_job(db: Session, file_id: int) -> KbPostJob | None:
    return (
        db.query(KbPostJob)
        .filter(KbPostJob.file_id == file_id)
        .order_by(KbPostJob.id.desc())
        .first()
    )


def _post_run_in_progress(f: FileModel, post_job: KbPostJob | None) -> bool:
    file_status = (f.kb_post_status or "").lower()
    if file_status in {"queued", "running"}:
        return True
    if post_job is not None and post_job.status in {"queued", "running"}:
        return True
    return False


_POST_TERMINAL_LOG_ACTIONS = (
    ACTION_KB_POST_DONE,
    ACTION_KB_POST_SKIP,
    ACTION_KB_POST_ERROR,
)


def _get_post_log_detail_for_job(db: Session, file_id: int, job_id: int) -> dict[str, str]:
    rows = (
        db.query(OperationLog.detail)
        .filter(
            OperationLog.target_id == file_id,
            OperationLog.action.in_(_POST_TERMINAL_LOG_ACTIONS),
        )
        .order_by(OperationLog.id.desc())
        .all()
    )
    job_id_str = str(job_id)
    for (detail,) in rows:
        kv = _parse_detail_kv(detail)
        if kv.get("job_id") == job_id_str:
            return kv
    return {}


def _get_extract_engine_for_job(
    db: Session,
    file_id: int,
    job_id: int | None,
) -> str | None:
    """解析该文件最近一次提取完成日志中实际执行的 engine（如 pdf-inspector / mineru / docling）。

    ``engine`` 表示真正完成正文提取的引擎，可能与入队时的 ``provider``（计划路由）不同，
    例如 pdf-inspector 快路径接管 mineru 时：``engine=pdf-inspector``、``provider=mineru``。
    """
    if job_id is None:
        return None
    rows = (
        db.query(OperationLog.detail)
        .filter(
            OperationLog.target_id == file_id,
            OperationLog.action == ACTION_KB_EXTRACT_DONE,
        )
        .order_by(OperationLog.id.desc())
        .all()
    )
    job_id_str = str(job_id)
    for (detail,) in rows:
        kv = _parse_detail_kv(detail)
        if kv.get("job_id") == job_id_str:
            engine = (kv.get("engine") or "").strip()
            return engine or None
    return None


def _resolve_post_perf(
    db: Session,
    f: FileModel,
    post_job: KbPostJob | None,
) -> dict[str, str]:
    if _post_run_in_progress(f, post_job):
        return {}
    if post_job is not None:
        if post_job.status == "error":
            return {}
        if post_job.status == "done":
            return _get_post_log_detail_for_job(db, f.id, post_job.id)
        return {}
    return {}


def _latest_index_job(db: Session, file_id: int) -> KbIndexJob | None:
    return (
        db.query(KbIndexJob)
        .filter(KbIndexJob.file_id == file_id)
        .order_by(KbIndexJob.id.desc())
        .first()
    )


def _trace_provider(
    db: Session,
    f: FileModel,
    extract_job: KbExtractJob | None,
    global_default: str,
) -> str:
    """Prefer enqueue-time job.provider (048); fallback current route resolve."""
    if extract_job is not None and extract_job.provider:
        return str(extract_job.provider).strip()
    routed = resolve_extract_provider(db, f)
    return routed or global_default


def _parse_detail_kv(detail: str | None) -> dict[str, str]:
    """解析 operation_log.detail 的 key=value 形式。"""
    if not detail:
        return {}
    kv: dict[str, str] = {}
    for part in (detail or "").split():
        if "=" in part:
            k, v = part.split("=", 1)
            kv[k] = v
    return kv


def _optional_int_from_detail_kv(kv: dict[str, str], key: str) -> int | None:
    raw = kv.get(key)
    if raw is None:
        return None
    try:
        return int(raw)
    except ValueError:
        logger.debug("kb_pipeline_trace invalid %s=%r", key, raw)
        return None


_INDEX_TERMINAL_LOG_ACTIONS = (
    ACTION_KB_INDEX_DONE,
    ACTION_KB_INDEX_SKIP,
    ACTION_KB_INDEX_ERROR,
)


def _index_run_in_progress(f: FileModel, index_job: KbIndexJob | None) -> bool:
    """重新检索 / 排队中时不应展示上一轮索引的耗时与完成时间。"""
    file_status = (f.index_status or "").lower()
    if file_status in {"pending", "indexing"}:
        return True
    if index_job is not None and index_job.status in {"queued", "running"}:
        return True
    return False


def _get_latest_index_perf(db: Session, file_id: int) -> dict[str, str]:
    """取该文件最近一次 KB 索引完成的 detail（无 job 行时的兜底）。"""
    row = (
        db.query(OperationLog.detail)
        .filter(
            OperationLog.target_id == file_id,
            OperationLog.action == ACTION_KB_INDEX_DONE,
        )
        .order_by(OperationLog.id.desc())
        .first()
    )
    return _parse_detail_kv(row[0] if row else None)


def _get_index_log_detail_for_job(
    db: Session,
    file_id: int,
    job_id: int,
    *,
    actions: tuple[str, ...] = _INDEX_TERMINAL_LOG_ACTIONS,
) -> dict[str, str]:
    rows = (
        db.query(OperationLog.detail)
        .filter(
            OperationLog.target_id == file_id,
            OperationLog.action.in_(actions),
        )
        .order_by(OperationLog.id.desc())
        .all()
    )
    job_id_str = str(job_id)
    for (detail,) in rows:
        kv = _parse_detail_kv(detail)
        if kv.get("job_id") == job_id_str:
            return kv
    return {}


def _resolve_index_perf(
    db: Session,
    f: FileModel,
    index_job: KbIndexJob | None,
) -> dict[str, str]:
    """仅在与当前 index job 一致的终态日志上展示效率字段，避免 reindex 排队时沿用旧数据。"""
    if _index_run_in_progress(f, index_job):
        return {}
    if index_job is not None:
        if index_job.status == "error":
            return {}
        if index_job.status == "done":
            return _get_index_log_detail_for_job(
                db,
                f.id,
                index_job.id,
                actions=(ACTION_KB_INDEX_DONE,),
            )
        return {}
    return _get_latest_index_perf(db, f.id)


def _notes_occurred_at(f: FileModel, *, has_md: bool) -> str | None:
    """笔记落盘时间：优先 .md_notes 文件 mtime，否则 extracted_at。"""
    if not has_md:
        if f.has_md and f.extracted_at:
            return to_beijing_time(f.extracted_at).isoformat()
        return None
    path = resolve_concept_sidecar_path(f) or md_note_path(f.id)
    if os.path.isfile(path):
        try:
            mtime = os.path.getmtime(path)
            return datetime.fromtimestamp(mtime, tz=BEIJING_TZ).isoformat()
        except OSError:
            logger.debug("kb_pipeline_trace md mtime failed file_id=%s", f.id)
    if f.extracted_at:
        return to_beijing_time(f.extracted_at).isoformat()
    return None


def build_file_pipeline_trace(db: Session, f: FileModel) -> FilePipelineTraceResponse:
    global_default = get_kb_extract_provider(db)
    extract_job = _latest_extract_job(db, f.id)
    index_job = _latest_index_job(db, f.id)
    extraction_manifest = None
    extraction_manifest_error = None
    if extract_job is not None:
        try:
            extraction_manifest = build_extraction_manifest(db, f.id, int(extract_job.id))
        except ManifestReadError as exc:
            extraction_manifest_error = exc.code
    has_md = resolve_concept_sidecar_path(f) is not None
    trace_provider = _trace_provider(db, f, extract_job, global_default)

    upload_at = to_beijing_time(f.created_at).isoformat() if f.created_at else None
    steps: list[PipelineTraceStep] = [
        PipelineTraceStep(
            key="upload",
            title="上传 / 入库",
            status="finish",
            detail=f.filename,
            occurred_at=upload_at,
        ),
    ]

    extract_status = _step_status_from_file_status(f.extract_status)
    extract_provider = trace_provider
    extract_engine = _get_extract_engine_for_job(
        db,
        f.id,
        extract_job.id if extract_job is not None else None,
    )
    extract_error = _pick_error(
        f.extract_error,
        extract_job.last_error if extract_job else None,
    )
    extract_detail_parts: list[str] = []
    if extract_engine:
        extract_detail_parts.append(f"engine={extract_engine}")
    extract_detail_parts.append(f"provider={extract_provider}")
    extract_detail_parts.append(f"status={f.extract_status}")
    if extract_job is not None:
        extract_detail_parts.append(f"job_id={extract_job.id}")
    steps.append(
        PipelineTraceStep(
            key="extract",
            title="正文提取",
            status=extract_status,
            detail="; ".join(extract_detail_parts),
            error_message=extract_error,
            log_deep_link=_admin_logs_deep_link(f.user_id) if extract_status == "error" else None,
            occurred_at=to_beijing_time(f.extracted_at).isoformat() if f.extracted_at else None,
        )
    )

    notes_status = "finish" if has_md else ("skip" if f.extract_status == "not_needed" else "wait")
    steps.append(
        PipelineTraceStep(
            key="notes",
            title="笔记 (.md_notes)",
            status=notes_status,
            detail="已生成 Markdown 笔记" if has_md else "等待提取完成",
            occurred_at=_notes_occurred_at(f, has_md=has_md),
        )
    )

    index_status = _step_status_from_file_status(f.index_status)
    index_error = _pick_error(
        f.index_error,
        index_job.last_error if index_job else None,
    )
    index_in_progress = _index_run_in_progress(f, index_job)
    index_detail_parts = [f"status={f.index_status}", f"chunks={f.chunk_count or 0}"]
    if index_job is not None:
        index_detail_parts.append(f"job_id={index_job.id}")
        index_detail_parts.append(f"job_status={index_job.status}")
        if index_job.force:
            index_detail_parts.append("force=true")

    # 与当前 job 对齐的索引完成日志；reindex 进行中不展示上一轮耗时
    index_perf = _resolve_index_perf(db, f, index_job)
    if index_perf:
        for k in _INDEX_PERF_INT_KEYS:
            if k in index_perf:
                index_detail_parts.append(f"{k}={index_perf[k]}ms")
        if "large_pdf" in index_perf:
            index_detail_parts.append(f"large_pdf={index_perf['large_pdf']}")

    index_step = PipelineTraceStep(
        key="index",
        title="向量索引",
        status=index_status,
        detail="; ".join(index_detail_parts),
        error_message=index_error,
        log_deep_link=_admin_logs_deep_link(f.user_id) if index_status == "error" else None,
        occurred_at=(
            to_beijing_time(f.indexed_at).isoformat()
            if f.indexed_at and not index_in_progress
            else None
        ),
    )
    # 结构化填充效率字段（供 UI/监控直接读取）
    for key in _INDEX_PERF_INT_KEYS:
        val = _optional_int_from_detail_kv(index_perf, key)
        if val is not None:
            setattr(index_step, key, val)
    if "large_pdf" in index_perf:
        index_step.large_pdf = index_perf["large_pdf"].lower() in {"1", "true", "yes"}

    steps.append(index_step)

    post_job = _latest_post_job(db, f.id)
    post_status = _step_status_from_file_status(f.kb_post_status or "pending")
    post_error = _pick_error(f.kb_post_error, post_job.last_error if post_job else None)
    post_in_progress = _post_run_in_progress(f, post_job)
    post_detail_parts = [f"status={f.kb_post_status or 'pending'}"]
    if post_job is not None:
        post_detail_parts.append(f"job_id={post_job.id}")
        post_detail_parts.append(f"job_status={post_job.status}")
    post_perf = _resolve_post_perf(db, f, post_job)
    if post_perf:
        for k in _POST_PERF_INT_KEYS:
            if k in post_perf:
                post_detail_parts.append(f"{k}={post_perf[k]}ms")
        if "post_skip_reason" in post_perf:
            post_detail_parts.append(f"post_skip_reason={post_perf['post_skip_reason']}")
    post_step = PipelineTraceStep(
        key="post",
        title="后处理 (entity/SAG/RAPTOR)",
        status=post_status,
        detail="; ".join(post_detail_parts),
        error_message=post_error,
        log_deep_link=_admin_logs_deep_link(f.user_id) if post_status == "error" else None,
        occurred_at=(
            to_beijing_time(f.kb_post_at).isoformat()
            if f.kb_post_at and not post_in_progress
            else None
        ),
    )
    for key in _POST_PERF_INT_KEYS:
        val = _optional_int_from_detail_kv(post_perf, key)
        if val is not None:
            setattr(post_step, key, val)
    if "post_skip_reason" in post_perf:
        post_step.post_skip_reason = post_perf["post_skip_reason"]
    steps.append(post_step)

    return FilePipelineTraceResponse(
        file_id=f.id,
        filename=f.filename,
        trace_provider=trace_provider,
        global_default_provider=global_default,
        chunk_count=int(f.chunk_count or 0),
        has_md_notes=has_md,
        steps=steps,
        extraction_manifest=extraction_manifest,
        extraction_manifest_error=extraction_manifest_error,
    )
