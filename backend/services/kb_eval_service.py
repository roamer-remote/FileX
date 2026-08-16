# Copyright (c) 2026 徐泽宇
"""RAGAS online evaluation service for completed RAG answers."""

from __future__ import annotations

import asyncio
import hashlib
import importlib.metadata
import logging
import os
import random
import threading
import time
from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Any, Callable, Literal

from sqlalchemy import case, func as sa_func
from sqlalchemy.orm import Session

from models.kb_search_eval import KbSearchEval
from services.log_service import log_operation
from services.kb_ragas_eval_queue_service import (
    RagasEvalContext,
    create_ragas_eval_job,
    effective_ragas_metric_timeout,
    finish_ragas_eval_job,
    heartbeat_ragas_eval_job,
)
from services.kb_ragas_llm_service import get_ragas_llm_runtime_config
from services.system_setting_service import (
    get_public_settings_dict,
    KEY_KB_RAGAS_ONLINE_EVAL_ENABLED,
    KEY_KB_RAGAS_ONLINE_EVAL_SAMPLE_RATE,
    KEY_KB_RAGAS_ONLINE_EVAL_TIMEOUT_SECONDS,
    KEY_KB_RAGAS_EVAL_CONTEXT_MAX_CHARS_PER_ITEM,
    KEY_KB_RAGAS_EVAL_CONTEXT_MAX_COUNT,
    KEY_KB_RAGAS_EVAL_CONTEXT_MAX_TOTAL_CHARS,
    DEFAULTS,
)
from utils.timezone import naive_db_now

logger = logging.getLogger(__name__)

EvalStatus = Literal["pending", "running", "succeeded", "failed", "skipped"]
Evaluator = Callable[[Session, str, str, list[str], float], "RagasEvalResult"]

ACTION_RAGAS_ONLINE_EVAL = "ragas_online_eval"
DEFAULT_LOW_SCORE_THRESHOLD = 0.7
DEFAULT_TIMEOUT_SECONDS = 600.0
MAX_TIMEOUT_SECONDS = 3000.0
MAX_PREVIEW_CHARS = 512
SAMPLE_TYPE_ANSWER = "answer"
SAMPLE_TYPE_RECALL_NO_HIT = "recall_no_hit"
_ALLOWED_SAMPLE_TYPES = {SAMPLE_TYPE_ANSWER, SAMPLE_TYPE_RECALL_NO_HIT}
def _normalize_sample_type(value: str | None) -> str:
    """归一化样本类型：None 或空 -> answer；未知值降级为 answer 并告警。"""
    if not value:
        return SAMPLE_TYPE_ANSWER
    if value in _ALLOWED_SAMPLE_TYPES:
        return value
    logger.warning("ragas eval unknown sample_type=%r, falling back to answer", value)
    return SAMPLE_TYPE_ANSWER


@dataclass(frozen=True)
class RagasEvalResult:
    status: EvalStatus
    faithfulness_score: float | None
    context_precision_score: float | None
    metric_version: str
    metric_variant: str
    llm_provider: str | None
    llm_model: str | None
    error_code: str | None = None
    error_message: str | None = None


_ragas_eval_cache_lock = threading.Lock()
_ragas_eval_cache: dict[str, Any] | None = None


def _bool_env(name: str, default: bool = False) -> bool:
    raw = os.environ.get(name)
    if raw is None:
        return default
    return raw.strip().lower() in {"1", "true", "yes", "on"}


def _float_env(name: str, default: float) -> float:
    try:
        return float((os.environ.get(name) or "").strip())
    except ValueError:
        return default


def invalidate_ragas_eval_runtime_cache() -> None:
    global _ragas_eval_cache
    with _ragas_eval_cache_lock:
        _ragas_eval_cache = None


def _load_ragas_eval_settings(db: Session) -> dict[str, str]:
    global _ragas_eval_cache
    with _ragas_eval_cache_lock:
        if _ragas_eval_cache is not None:
            return dict(_ragas_eval_cache)
    try:
        settings = get_public_settings_dict(db)
    except Exception:
        logger.warning("Failed to read RAGAS eval system settings, using DEFAULTS", exc_info=True)
        settings = {}
    result = {
        "enabled": settings.get(KEY_KB_RAGAS_ONLINE_EVAL_ENABLED, DEFAULTS[KEY_KB_RAGAS_ONLINE_EVAL_ENABLED]),
        "sample_rate": settings.get(KEY_KB_RAGAS_ONLINE_EVAL_SAMPLE_RATE, DEFAULTS[KEY_KB_RAGAS_ONLINE_EVAL_SAMPLE_RATE]),
        "timeout": settings.get(KEY_KB_RAGAS_ONLINE_EVAL_TIMEOUT_SECONDS, DEFAULTS[KEY_KB_RAGAS_ONLINE_EVAL_TIMEOUT_SECONDS]),
    }
    with _ragas_eval_cache_lock:
        if _ragas_eval_cache is None:
            _ragas_eval_cache = result
    return dict(result)


def get_ragas_eval_enabled(db: Session) -> bool:
    settings = _load_ragas_eval_settings(db)
    raw = settings["enabled"]
    if raw and raw != DEFAULTS[KEY_KB_RAGAS_ONLINE_EVAL_ENABLED]:
        return raw.strip().lower() in {"1", "true", "yes", "on"}
    # Fallback to env var when system setting equals default (not explicitly set)
    return _bool_env("KB_RAGAS_ONLINE_EVAL_ENABLED", False)


def get_ragas_eval_sample_rate(db: Session) -> float:
    settings = _load_ragas_eval_settings(db)
    raw = settings["sample_rate"]
    if raw and raw != DEFAULTS[KEY_KB_RAGAS_ONLINE_EVAL_SAMPLE_RATE]:
        try:
            return max(0.0, min(1.0, float(raw.strip())))
        except ValueError:
            pass
    return max(0.0, min(1.0, _float_env("KB_RAGAS_ONLINE_EVAL_SAMPLE_RATE", 1.0)))


def get_ragas_eval_timeout_seconds(db: Session) -> float:
    settings = _load_ragas_eval_settings(db)
    raw = settings["timeout"]
    if raw and raw != DEFAULTS[KEY_KB_RAGAS_ONLINE_EVAL_TIMEOUT_SECONDS]:
        try:
            return max(1.0, min(MAX_TIMEOUT_SECONDS, float(raw.strip())))
        except ValueError:
            pass
    return max(1.0, min(MAX_TIMEOUT_SECONDS, _float_env("KB_RAGAS_ONLINE_EVAL_TIMEOUT_SECONDS", DEFAULT_TIMEOUT_SECONDS)))


def is_ragas_online_eval_enabled(db: Session | None = None) -> bool:
    if db is not None:
        return get_ragas_eval_enabled(db)
    from database import SessionLocal
    db2 = SessionLocal()
    try:
        return get_ragas_eval_enabled(db2)
    finally:
        db2.close()


def ragas_online_eval_sample_rate(db: Session | None = None) -> float:
    if db is not None:
        return get_ragas_eval_sample_rate(db)
    from database import SessionLocal
    db2 = SessionLocal()
    try:
        return get_ragas_eval_sample_rate(db2)
    finally:
        db2.close()


def ragas_online_eval_timeout_seconds(db: Session | None = None) -> float:
    if db is not None:
        return get_ragas_eval_timeout_seconds(db)
    from database import SessionLocal
    db2 = SessionLocal()
    try:
        return get_ragas_eval_timeout_seconds(db2)
    finally:
        db2.close()


def _ragas_context_budget_settings(db: Session) -> tuple[int, int, int]:
    """Read validated admin settings used to freeze the queue payload budget."""
    settings = get_public_settings_dict(db)

    def _bounded(key: str, lower: int, upper: int) -> int:
        try:
            value = int(str(settings.get(key, DEFAULTS[key])).strip())
        except (TypeError, ValueError):
            value = int(DEFAULTS[key])
        return max(lower, min(upper, value))

    return (
        _bounded(KEY_KB_RAGAS_EVAL_CONTEXT_MAX_COUNT, 1, 20),
        _bounded(KEY_KB_RAGAS_EVAL_CONTEXT_MAX_CHARS_PER_ITEM, 200, 4000),
        _bounded(KEY_KB_RAGAS_EVAL_CONTEXT_MAX_TOTAL_CHARS, 1000, 40000),
    )


def _preview(text: str) -> str:
    return (text or "").strip()[:MAX_PREVIEW_CHARS]


def _hash(text: str) -> str:
    return hashlib.sha256((text or "").encode("utf-8")).hexdigest()


def _clamp_score(value: float | None) -> float | None:
    if value is None:
        return None
    return round(max(0.0, min(1.0, float(value))), 4)


def enqueue_ragas_online_eval(
    db: Session,
    *,
    user_id: int,
    workspace_id: int | None,
    query: str,
    answer: str,
    contexts: list[str],
    eval_contexts: list[RagasEvalContext] | None = None,
    context_file_ids: list[int] | None = None,
    context_chunk_ids: list[int] | None = None,
    agent_run_id: str | None = None,
    search_trace_id: str | None = None,
    sample_type: str | None = None,
) -> None:
    """Fail-open durable enqueue for a completed target RAG answer."""
    if not is_ragas_online_eval_enabled(db):
        return
    if random.random() > ragas_online_eval_sample_rate(db):
        return
    if not _preview(answer) or not [c for c in contexts if _preview(c)]:
        return

    norm_sample_type = _normalize_sample_type(sample_type)
    resolved_contexts = eval_contexts or [
        RagasEvalContext(text=text, file_id=None, chunk_id=None, rank=rank)
        for rank, text in enumerate(contexts)
    ]
    try:
        max_count, max_chars_per_item, max_total_chars = _ragas_context_budget_settings(db)
        create_ragas_eval_job(
            db,
            user_id=user_id,
            workspace_id=workspace_id,
            query=query,
            answer=answer,
            contexts=resolved_contexts,
            agent_run_id=agent_run_id,
            search_trace_id=search_trace_id,
            sample_type=norm_sample_type,
            max_count=max_count,
            max_chars_per_item=max_chars_per_item,
            max_total_chars=max_total_chars,
            total_budget_seconds=min(ragas_online_eval_timeout_seconds(db), 300.0),
        )
        db.commit()
    except Exception:
        db.rollback()
        logger.exception("ragas online eval durable enqueue failed")


def run_ragas_online_eval(
    db: Session,
    *,
    user_id: int,
    workspace_id: int | None,
    query: str,
    answer: str,
    contexts: list[str],
    context_file_ids: list[int] | None = None,
    context_chunk_ids: list[int] | None = None,
    agent_run_id: str | None = None,
    search_trace_id: str | None = None,
    sample_type: str | None = None,
    evaluator: Evaluator | None = None,
) -> KbSearchEval | None:
    """Create, evaluate, and persist one RAGAS online evaluation record."""
    clean_answer = _preview(answer)
    clean_contexts = [c for c in contexts if _preview(c)]
    if not clean_answer or not clean_contexts:
        return None

    norm_sample_type = _normalize_sample_type(sample_type)
    started = time.perf_counter()
    now = naive_db_now()
    record = KbSearchEval(
        user_id=user_id,
        workspace_id=workspace_id,
        agent_run_id=(agent_run_id or None),
        search_trace_id=(search_trace_id or None),
        sample_type=norm_sample_type,
        query_hash=_hash(query),
        query_preview=_preview(query),
        answer_hash=_hash(answer),
        answer_preview=clean_answer,
        context_count=len(clean_contexts),
        context_file_ids_json=[int(v) for v in (context_file_ids or [])[:50]],
        context_chunk_ids_json=[int(v) for v in (context_chunk_ids or [])[:100]],
        metric_provider="ragas",
        status="running",
        created_at=now,
    )
    db.add(record)
    db.flush()
    db.commit()
    db.refresh(record)

    evaluator = evaluator or _score_with_ragas
    try:
        result = evaluator(
            db,
            query,
            answer,
            clean_contexts,
            ragas_online_eval_timeout_seconds(db),
        )
    except Exception as exc:
        result = RagasEvalResult(
            status="failed",
            faithfulness_score=None,
            context_precision_score=None,
            metric_version=_ragas_version_label(),
            metric_variant="faithfulness+context_precision_without_reference",
            llm_provider=None,
            llm_model=None,
            error_code=type(exc).__name__,
            error_message=str(exc)[:1000],
        )

    record.status = result.status
    record.faithfulness_score = _clamp_score(result.faithfulness_score)
    record.context_precision_score = _clamp_score(result.context_precision_score)
    record.metric_version = result.metric_version
    record.metric_variant = result.metric_variant
    record.llm_provider = result.llm_provider
    record.llm_model = result.llm_model
    record.error_code = result.error_code
    record.error_message = result.error_message
    record.duration_ms = int((time.perf_counter() - started) * 1000)
    record.evaluated_at = naive_db_now()
    db.commit()
    db.refresh(record)

    _write_eval_operation_log(db, record)
    return record


def _write_eval_operation_log(db: Session, record: KbSearchEval) -> None:
    detail = " ".join(
        [
            f"status={record.status}",
            f"faithfulness={record.faithfulness_score}",
            f"context_precision={record.context_precision_score}",
            f"duration_ms={record.duration_ms}",
            f"queue_duration_ms={record.queue_duration_ms}",
            f"faithfulness_duration_ms={record.faithfulness_duration_ms}",
            f"context_precision_duration_ms={record.context_precision_duration_ms}",
            f"failure_stage={record.failure_stage or '-'}",
            f"context_budget_version={record.context_budget_version or '-'}",
            f"selected_context_count={record.selected_context_count}",
            f"selected_context_chars={record.selected_context_chars}",
            f"workspace_id={record.workspace_id}",
            f"context_count={record.context_count}",
            f"sample_type={record.sample_type}",
            f"error_code={record.error_code or '-'}",
            f"metric_variant={record.metric_variant or '-'}",
            f"llm_provider={record.llm_provider or '-'}",
            f"llm_model={record.llm_model or '-'}",
        ]
    )
    try:
        log_operation(
            db,
            int(record.user_id),
            ACTION_RAGAS_ONLINE_EVAL,
            "kb_search_eval",
            int(record.id),
            detail,
        )
    except Exception:
        db.rollback()
        logger.warning("ragas online eval operation log failed", exc_info=True)


def _ragas_version_label() -> str:
    try:
        version = importlib.metadata.version("ragas")
    except importlib.metadata.PackageNotFoundError:
        version = "not-installed"
    return f"ragas {version} Faithfulness LLMContextPrecisionWithoutReference"


def _run_async(coro: Any) -> Any:
    try:
        asyncio.get_running_loop()
    except RuntimeError:
        return asyncio.run(coro)
    thread_result: dict[str, Any] = {}

    def _target() -> None:
        try:
            thread_result["value"] = asyncio.run(coro)
        except Exception as exc:
            thread_result["error"] = exc

    t = threading.Thread(target=_target)
    t.start()
    t.join()
    if "error" in thread_result:
        raise thread_result["error"]
    return thread_result.get("value")


def _finish_ragas_job(
    db: Session,
    job: Any,
    **kwargs: Any,
) -> None:
    """Write a fenced terminal result and commit only when this worker owns it."""
    kwargs.setdefault("metric_version", _ragas_version_label())
    kwargs.setdefault("metric_variant", "faithfulness+context_precision_without_reference")
    if finish_ragas_eval_job(
        db,
        job_id=job.id,
        worker_id=job.worker_id,
        lease_generation=job.lease_generation,
        **kwargs,
    ):
        # The fenced terminal transition (including payload cleanup) is durable
        # before best-effort observability so log failure cannot resurrect a job.
        db.commit()
        eval_id = getattr(job, "eval_id", None)
        if eval_id is not None:
            record = db.get(KbSearchEval, eval_id)
            if record is not None:
                _write_eval_operation_log(db, record)
        db.commit()


def _is_ragas_transient_error(exc: Exception) -> bool:
    message = str(exc).lower()
    return "429" in message or "connection" in message or "connect" in message


def _start_ragas_heartbeat(job: Any) -> tuple[threading.Event, threading.Thread]:
    """Keep the liveness timestamp fresh without extending fixed lease/deadline."""
    stopped = threading.Event()

    def _heartbeat_loop() -> None:
        from database import SessionLocal

        while not stopped.wait(30.0):
            heartbeat_db = SessionLocal()
            try:
                owned = heartbeat_ragas_eval_job(
                    heartbeat_db,
                    job_id=job.id,
                    worker_id=job.worker_id,
                    lease_generation=job.lease_generation,
                )
                heartbeat_db.commit()
                if not owned:
                    return
            except Exception:
                heartbeat_db.rollback()
                logger.warning("RAGAS job heartbeat failed", exc_info=True)
            finally:
                heartbeat_db.close()

    thread = threading.Thread(target=_heartbeat_loop, name=f"ragas-heartbeat-{job.id}", daemon=True)
    thread.start()
    return stopped, thread


def execute_ragas_eval_job(db: Session, job: Any) -> None:
    """Execute one claimed job without ever exceeding its immutable deadline."""
    cfg = get_ragas_llm_runtime_config(db, fresh=True)
    if not cfg.is_configured:
        _finish_ragas_job(
            db,
            job,
            status="skipped",
            error_code="ragas_llm_unconfigured",
            error_message=cfg.unconfigured_reason or "RAGAS LLM is not configured",
            failure_stage="queue",
        )
        return

    payload = job.payload_json if isinstance(job.payload_json, dict) else {}
    contexts = [
        str(item.get("text") or "")
        for item in payload.get("contexts", [])
        if isinstance(item, dict) and str(item.get("text") or "").strip()
    ]
    query = str(payload.get("query") or "")
    answer = str(payload.get("answer") or "")
    if not query or not answer or not contexts:
        _finish_ragas_job(
            db,
            job,
            status="skipped",
            error_code="ragas_eval_payload_invalid",
            error_message="RAGAS queue payload has no query, answer, or contexts",
            failure_stage="queue",
        )
        return

    timeout = effective_ragas_metric_timeout(db, job, cfg.timeout_seconds)
    if timeout <= 0:
        _finish_ragas_job(
            db,
            job,
            status="failed",
            error_code="TimeoutError",
            error_message="RAGAS total evaluation deadline exhausted",
            failure_stage="faithfulness",
        )
        return

    try:
        from ragas import SingleTurnSample
        from ragas.llms import LangchainLLMWrapper
        from ragas.metrics import Faithfulness, LLMContextPrecisionWithoutReference
        from langchain_openai import ChatOpenAI
    except Exception as exc:
        _finish_ragas_job(
            db,
            job,
            status="skipped",
            error_code=type(exc).__name__,
            error_message=str(exc)[:1000],
            failure_stage="queue",
        )
        return

    sample = SingleTurnSample(user_input=query, response=answer, retrieved_contexts=contexts)
    heartbeat_stop, heartbeat_thread = _start_ragas_heartbeat(job)

    def _stop_heartbeat() -> None:
        heartbeat_stop.set()
        heartbeat_thread.join(timeout=1.0)

    def _metric_llm(metric_timeout: float) -> Any:
        return LangchainLLMWrapper(
            ChatOpenAI(
                base_url=(f"{cfg.base_url.rstrip('/')}/v1" if cfg.provider == "ollama" else cfg.base_url),
                api_key=cfg.api_key or "ollama",
                model=cfg.model,
                timeout=metric_timeout,
                temperature=0,
            )
        )

    def _score(metric_type: Any, stage: str) -> tuple[float | None, int, Exception | None]:
        duration_ms = 0
        for retry_index in range(2):
            metric_timeout = effective_ragas_metric_timeout(db, job, cfg.timeout_seconds)
            if metric_timeout <= 0:
                return None, duration_ms, TimeoutError("RAGAS total evaluation deadline exhausted")
            owns_lease = heartbeat_ragas_eval_job(
                db,
                job_id=job.id,
                worker_id=job.worker_id,
                lease_generation=job.lease_generation,
            )
            if not owns_lease:
                db.rollback()
                return None, duration_ms, RuntimeError("RAGAS evaluation worker lease lost")
            db.commit()
            started = time.perf_counter()
            try:
                metric = metric_type(llm=_metric_llm(metric_timeout))
                score = _run_async(
                    asyncio.wait_for(metric.single_turn_ascore(sample), timeout=metric_timeout)
                )
                duration_ms += int((time.perf_counter() - started) * 1000)
                return float(score), duration_ms, None
            except Exception as exc:
                duration_ms += int((time.perf_counter() - started) * 1000)
                if retry_index == 0 and _is_ragas_transient_error(exc):
                    continue
                return None, duration_ms, exc
        return None, duration_ms, RuntimeError(f"{stage} retry loop exhausted")

    faithfulness, faithfulness_ms, faithfulness_error = _score(Faithfulness, "faithfulness")
    if faithfulness_error is not None:
        _stop_heartbeat()
        _finish_ragas_job(
            db,
            job,
            status="failed",
            error_code=("TimeoutError" if isinstance(faithfulness_error, TimeoutError) else type(faithfulness_error).__name__),
            error_message=str(faithfulness_error)[:1000],
            failure_stage="faithfulness",
            faithfulness_duration_ms=faithfulness_ms,
            llm_provider=cfg.provider,
            llm_model=cfg.model,
        )
        return

    precision, precision_ms, precision_error = _score(
        LLMContextPrecisionWithoutReference, "context_precision"
    )
    if precision_error is not None:
        _stop_heartbeat()
        _finish_ragas_job(
            db,
            job,
            status="failed",
            error_code=("TimeoutError" if isinstance(precision_error, TimeoutError) else type(precision_error).__name__),
            error_message=str(precision_error)[:1000],
            failure_stage="context_precision",
            faithfulness_score=faithfulness,
            faithfulness_duration_ms=faithfulness_ms,
            context_precision_duration_ms=precision_ms,
            llm_provider=cfg.provider,
            llm_model=cfg.model,
        )
        return

    _stop_heartbeat()
    _finish_ragas_job(
        db,
        job,
        status="succeeded",
        faithfulness_score=faithfulness,
        context_precision_score=precision,
        faithfulness_duration_ms=faithfulness_ms,
        context_precision_duration_ms=precision_ms,
        llm_provider=cfg.provider,
        llm_model=cfg.model,
    )


def _score_with_ragas(
    db: Session,
    query: str,
    answer: str,
    contexts: list[str],
    timeout_seconds: float,
) -> RagasEvalResult:
    """Run real RAGAS metrics when installed; otherwise record explicit skipped."""
    cfg = get_ragas_llm_runtime_config(db, fresh=True)
    if not cfg.is_configured:
        return RagasEvalResult(
            status="skipped",
            faithfulness_score=None,
            context_precision_score=None,
            metric_version=_ragas_version_label(),
            metric_variant="ragas_llm_unconfigured",
            llm_provider=cfg.provider,
            llm_model=cfg.model or None,
            error_code="ragas_llm_unconfigured",
            error_message=cfg.unconfigured_reason or "RAGAS LLM is not configured",
        )

    try:
        from ragas import SingleTurnSample
        from ragas.llms import LangchainLLMWrapper
        from ragas.metrics import Faithfulness, LLMContextPrecisionWithoutReference
        from langchain_openai import ChatOpenAI
    except Exception as exc:
        return RagasEvalResult(
            status="skipped",
            faithfulness_score=None,
            context_precision_score=None,
            metric_version=_ragas_version_label(),
            metric_variant="ragas_dependency_unavailable",
            llm_provider=cfg.provider,
            llm_model=cfg.model,
            error_code=type(exc).__name__,
            error_message=str(exc)[:1000],
        )

    sample = SingleTurnSample(user_input=query, response=answer, retrieved_contexts=contexts)
    llm = LangchainLLMWrapper(
        ChatOpenAI(
            base_url=f"{cfg.base_url.rstrip('/')}/v1" if cfg.provider == "ollama" else cfg.base_url,
            api_key=cfg.api_key or "ollama",
            model=cfg.model,
            timeout=timeout_seconds,
            temperature=0,
        )
    )
    faithfulness = Faithfulness(llm=llm)
    context_precision = LLMContextPrecisionWithoutReference(llm=llm)

    async def _score() -> tuple[float, float]:
        return (
            await faithfulness.single_turn_ascore(sample),
            await context_precision.single_turn_ascore(sample),
        )

    try:
        faith_score, precision_score = _run_async(
            asyncio.wait_for(_score(), timeout=timeout_seconds)
        )
    except Exception as exc:
        return RagasEvalResult(
            status="failed",
            faithfulness_score=None,
            context_precision_score=None,
            metric_version=_ragas_version_label(),
            metric_variant="faithfulness+context_precision_without_reference",
            llm_provider=cfg.provider,
            llm_model=cfg.model,
            error_code=type(exc).__name__,
            error_message=str(exc)[:1000],
        )
    return RagasEvalResult(
        status="succeeded",
        faithfulness_score=float(faith_score),
        context_precision_score=float(precision_score),
        metric_version=_ragas_version_label(),
        metric_variant="faithfulness+context_precision_without_reference",
        llm_provider=cfg.provider,
        llm_model=cfg.model,
    )


def _cutoff(days: int) -> datetime:
    return naive_db_now() - timedelta(days=max(1, min(90, int(days))))


def _base_query(
    db: Session,
    *,
    days: int = 7,
    workspace_id: int | None = None,
    user_id: int | None = None,
    status_filter: str | None = None,
):
    q = db.query(KbSearchEval).filter(KbSearchEval.created_at >= _cutoff(days))
    if workspace_id is not None:
        q = q.filter(KbSearchEval.workspace_id == workspace_id)
    if user_id is not None:
        q = q.filter(KbSearchEval.user_id == user_id)
    if status_filter:
        q = q.filter(KbSearchEval.status == status_filter)
    return q


def query_eval_summary(
    db: Session,
    *,
    days: int = 7,
    workspace_id: int | None = None,
    user_id: int | None = None,
    status_filter: str | None = None,
) -> dict[str, Any]:
    q = _base_query(
        db,
        days=days,
        workspace_id=workspace_id,
        user_id=user_id,
        status_filter=status_filter,
    )
    row = q.with_entities(
        sa_func.count(),
        sa_func.sum(case((KbSearchEval.status == "succeeded", 1), else_=0)),
        sa_func.sum(case((KbSearchEval.status == "failed", 1), else_=0)),
        sa_func.sum(case((KbSearchEval.status == "skipped", 1), else_=0)),
        sa_func.sum(case((KbSearchEval.status == "pending", 1), else_=0)),
        sa_func.sum(case((KbSearchEval.status == "running", 1), else_=0)),
        sa_func.sum(case((KbSearchEval.sample_type == SAMPLE_TYPE_RECALL_NO_HIT, 1), else_=0)),
        sa_func.avg(KbSearchEval.faithfulness_score),
        sa_func.avg(KbSearchEval.context_precision_score),
    ).one()
    total = int(row[0] or 0)
    succeeded = int(row[1] or 0)
    failed = int(row[2] or 0)
    skipped = int(row[3] or 0)
    pending = int(row[4] or 0)
    running = int(row[5] or 0)
    recall_no_hit_count = int(row[6] or 0)
    return {
        "days": days,
        "total_count": total,
        "succeeded_count": succeeded,
        "failed_count": failed,
        "skipped_count": skipped,
        "pending_count": pending,
        "running_count": running,
        "recall_no_hit_count": recall_no_hit_count,
        "failure_rate": (failed / total) if total else 0.0,
        "avg_faithfulness": round(float(row[7]), 4) if row[7] is not None else None,
        "avg_context_precision": round(float(row[8]), 4) if row[8] is not None else None,
    }


def query_eval_trend(
    db: Session,
    *,
    days: int = 7,
    granularity: str = "day",
    workspace_id: int | None = None,
    user_id: int | None = None,
    status_filter: str | None = None,
) -> list[dict[str, Any]]:
    unit = "hour" if granularity == "hour" else "day"
    bucket = sa_func.date_trunc(unit, KbSearchEval.created_at).label("bucket")
    failure_count = sa_func.sum(case((KbSearchEval.status == "failed", 1), else_=0))
    pending_count = sa_func.sum(case((KbSearchEval.status == "pending", 1), else_=0))
    running_count = sa_func.sum(case((KbSearchEval.status == "running", 1), else_=0))
    skipped_count = sa_func.sum(case((KbSearchEval.status == "skipped", 1), else_=0))
    q = _base_query(
        db,
        days=days,
        workspace_id=workspace_id,
        user_id=user_id,
        status_filter=status_filter,
    )
    rows = (
        q.with_entities(
            bucket,
            sa_func.avg(KbSearchEval.faithfulness_score).label("avg_faithfulness"),
            sa_func.avg(KbSearchEval.context_precision_score).label("avg_context_precision"),
            sa_func.count(KbSearchEval.id).label("sample_count"),
            failure_count.label("failure_count"),
            pending_count.label("pending_count"),
            running_count.label("running_count"),
            skipped_count.label("skipped_count"),
        )
        .group_by(bucket)
        .order_by(bucket)
        .all()
    )
    failure_rows = (
        q.filter(KbSearchEval.status == "failed")
        .with_entities(bucket, KbSearchEval.failure_stage, sa_func.count(KbSearchEval.id))
        .group_by(bucket, KbSearchEval.failure_stage)
        .all()
    )
    failure_stages: dict[str, dict[str, int]] = {}
    for failed_bucket, stage, count in failure_rows:
        key = failed_bucket.isoformat() if failed_bucket else ""
        failure_stages.setdefault(key, {})[stage or "unknown"] = int(count or 0)
    out: list[dict[str, Any]] = []
    for row in rows:
        sample_count = int(row.sample_count or 0)
        failed = int(row.failure_count or 0)
        out.append(
            {
                "bucket": row.bucket.isoformat() if row.bucket else "",
                "avg_faithfulness": round(float(row.avg_faithfulness), 4)
                if row.avg_faithfulness is not None
                else None,
                "avg_context_precision": round(float(row.avg_context_precision), 4)
                if row.avg_context_precision is not None
                else None,
                "sample_count": sample_count,
                "failure_rate": (failed / sample_count) if sample_count else 0.0,
                "pending_count": int(row.pending_count or 0),
                "running_count": int(row.running_count or 0),
                "failed_count": failed,
                "skipped_count": int(row.skipped_count or 0),
                "failure_stage_counts": failure_stages.get(
                    row.bucket.isoformat() if row.bucket else "", {}
                ),
            }
        )
    return out


def query_eval_samples(
    db: Session,
    *,
    days: int = 7,
    workspace_id: int | None = None,
    user_id: int | None = None,
    status_filter: str | None = None,
    sample_type: str | None = None,
    low_score_threshold: float | None = DEFAULT_LOW_SCORE_THRESHOLD,
    limit: int = 50,
) -> list[dict[str, Any]]:
    q = _base_query(
        db,
        days=days,
        workspace_id=workspace_id,
        user_id=user_id,
        status_filter=status_filter,
    )
    if sample_type:
        q = q.filter(KbSearchEval.sample_type == sample_type)
    if low_score_threshold is not None:
        q = q.filter(
            (KbSearchEval.faithfulness_score < low_score_threshold)
            | (KbSearchEval.context_precision_score < low_score_threshold)
            | (KbSearchEval.status.in_(["failed", "skipped"]))
        )
    rows = q.order_by(KbSearchEval.created_at.desc()).limit(max(1, min(200, limit))).all()
    return [
        {
            "id": row.id,
            "user_id": row.user_id,
            "workspace_id": row.workspace_id,
            "agent_run_id": row.agent_run_id,
            "search_trace_id": row.search_trace_id,
            "sample_type": row.sample_type,
            "query_hash": row.query_hash,
            "query_preview": row.query_preview,
            "answer_hash": row.answer_hash,
            "answer_preview": row.answer_preview,
            "context_count": row.context_count,
            "context_file_ids": row.context_file_ids_json or [],
            "context_chunk_ids": row.context_chunk_ids_json or [],
            "faithfulness_score": row.faithfulness_score,
            "context_precision_score": row.context_precision_score,
            "metric_provider": row.metric_provider,
            "metric_version": row.metric_version,
            "metric_variant": row.metric_variant,
            "llm_provider": row.llm_provider,
            "llm_model": row.llm_model,
            "status": row.status,
            "error_code": row.error_code,
            "error_message": row.error_message,
            "duration_ms": row.duration_ms,
            "queue_duration_ms": row.queue_duration_ms,
            "faithfulness_duration_ms": row.faithfulness_duration_ms,
            "context_precision_duration_ms": row.context_precision_duration_ms,
            "failure_stage": row.failure_stage,
            "context_budget_version": row.context_budget_version,
            "source_context_count": row.source_context_count,
            "selected_context_count": row.selected_context_count,
            "selected_context_chars": row.selected_context_chars,
            "created_at": row.created_at.isoformat() if row.created_at else None,
            "evaluated_at": row.evaluated_at.isoformat() if row.evaluated_at else None,
        }
        for row in rows
    ]


# Backward-compatible names for the experimental draft API.
def query_eval_trends(
    db: Session,
    *,
    hours: int = 168,
    metric: str = "faithfulness",
    granularity: str = "hour",
) -> list[dict[str, Any]]:
    del metric
    return query_eval_trend(db, days=max(1, int(hours / 24)), granularity=granularity)


def query_recent_evals(
    db: Session,
    *,
    limit: int = 50,
    min_score: float | None = None,
) -> list[dict[str, Any]]:
    return query_eval_samples(db, limit=limit, low_score_threshold=min_score)
