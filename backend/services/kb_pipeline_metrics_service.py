# Copyright (c) 2026 徐泽宇
"""086 Phase 2: KB pipeline runtime metrics aggregation."""

from __future__ import annotations

import time
from collections import defaultdict
from datetime import datetime, timedelta
from typing import Literal

from sqlalchemy.orm import Session

from models.operation_log import OperationLog
from models.user import User
from schemas.kb_pipeline_visualization import (
    PipelineKpiMetric,
    PipelineMetricsResponse,
    PipelineOcrAggStat,
    PipelineQueueMetric,
    PipelineRecentEvent,
    PipelineStageAvgMs,
    ProviderFailureStat,
)
from services.kb_pipeline_log_service import (
    ACTION_KB_EXTRACT_DONE,
    ACTION_KB_EXTRACT_ERROR,
    ACTION_KB_EXTRACT_FALLBACK,
    ACTION_KB_INDEX_DONE,
    ACTION_KB_INDEX_ERROR,
    ALL_PIPELINE_ACTIONS,
)
from services.rabbitmq_status_service import get_mq_status
from utils.timezone import naive_db_now, to_beijing_time

MetricsWindow = Literal["1h", "24h", "7d"]

WINDOW_DELTAS: dict[str, timedelta] = {
    "1h": timedelta(hours=1),
    "24h": timedelta(hours=24),
    "7d": timedelta(days=7),
}

QUEUE_MONITOR_LABELS = frozenset({"extract_main", "index_main", "extract_dlq", "index_dlq"})
QUEUE_DEPTH_WARN = 50
FAIL_RATE_WARN = 0.15
FAIL_RATE_MIN_SAMPLES = 5
METRICS_CACHE_TTL_SEC = 30

_EXTRACT_FAILURE_ACTIONS = frozenset(
    {ACTION_KB_EXTRACT_ERROR, ACTION_KB_EXTRACT_FALLBACK},
)
_INDEX_FAILURE_ACTIONS = frozenset({ACTION_KB_INDEX_ERROR})

_cache: dict[tuple[str, int], tuple[float, PipelineMetricsResponse]] = {}


def parse_detail_kv(detail: str | None) -> dict[str, str]:
    out: dict[str, str] = {}
    if not detail:
        return out
    for part in detail.split():
        if "=" in part:
            key, value = part.split("=", 1)
            out[key] = value
    return out


def _parse_int_field(detail: str | None, field: str) -> int | None:
    raw = parse_detail_kv(detail).get(field)
    if raw is None:
        return None
    try:
        return int(raw)
    except ValueError:
        return None


def _avg_ms(values: list[int]) -> float | None:
    if not values:
        return None
    return round(sum(values) / len(values), 1)


def _window_start(window: MetricsWindow) -> datetime:
    delta = WINDOW_DELTAS.get(window, WINDOW_DELTAS["24h"])
    return naive_db_now() - delta


def _logs_base_query(db: Session, window: MetricsWindow):
    return db.query(OperationLog).filter(OperationLog.created_at >= _window_start(window))


def _count_actions(db: Session, window: MetricsWindow, actions: frozenset[str]) -> int:
    return (
        _logs_base_query(db, window)
        .filter(OperationLog.action.in_(sorted(actions)))
        .count()
    )


def _collect_provider_stats(
    db: Session,
    window: MetricsWindow,
) -> list[ProviderFailureStat]:
    rows = (
        _logs_base_query(db, window)
        .filter(
            OperationLog.action.in_(
                sorted(
                    _EXTRACT_FAILURE_ACTIONS
                    | _INDEX_FAILURE_ACTIONS
                    | {ACTION_KB_EXTRACT_DONE, ACTION_KB_INDEX_DONE},
                ),
            ),
        )
        .all()
    )
    failures: dict[str, int] = defaultdict(int)
    successes: dict[str, int] = defaultdict(int)
    for row in rows:
        provider = parse_detail_kv(row.detail).get("provider") or "unknown"
        if row.action in _EXTRACT_FAILURE_ACTIONS or row.action in _INDEX_FAILURE_ACTIONS:
            failures[provider] += 1
        elif row.action in {ACTION_KB_EXTRACT_DONE, ACTION_KB_INDEX_DONE}:
            successes[provider] += 1

    providers = sorted(set(failures) | set(successes))
    stats: list[ProviderFailureStat] = []
    for provider in providers:
        fail_count = failures.get(provider, 0)
        ok_count = successes.get(provider, 0)
        total = fail_count + ok_count
        rate = round(fail_count / total, 4) if total else 0.0
        stats.append(
            ProviderFailureStat(
                provider=provider,
                failure_count=fail_count,
                success_count=ok_count,
                failure_rate=rate,
            ),
        )
    stats.sort(key=lambda item: (-item.failure_count, item.provider))
    return stats


def _collect_avg_stage_ms(db: Session, window: MetricsWindow) -> PipelineStageAvgMs:
    extract_rows = (
        _logs_base_query(db, window)
        .filter(OperationLog.action == ACTION_KB_EXTRACT_DONE)
        .all()
    )
    index_rows = (
        _logs_base_query(db, window)
        .filter(OperationLog.action == ACTION_KB_INDEX_DONE)
        .all()
    )
    provider_ms: list[int] = []
    extract_persist_ms: list[int] = []
    for row in extract_rows:
        parsed = _parse_int_field(row.detail, "provider_ms")
        if parsed is not None:
            provider_ms.append(parsed)
        parsed = _parse_int_field(row.detail, "persist_ms")
        if parsed is not None:
            extract_persist_ms.append(parsed)

    embed_ms: list[int] = []
    index_persist_ms: list[int] = []
    post_index_ms: list[int] = []
    for row in index_rows:
        for field, bucket in (
            ("embed_ms", embed_ms),
            ("persist_ms", index_persist_ms),
            ("post_index_ms", post_index_ms),
        ):
            parsed = _parse_int_field(row.detail, field)
            if parsed is not None:
                bucket.append(parsed)

    return PipelineStageAvgMs(
        extract_provider_ms=_avg_ms(provider_ms),
        extract_persist_ms=_avg_ms(extract_persist_ms),
        index_embed_ms=_avg_ms(embed_ms),
        index_persist_ms=_avg_ms(index_persist_ms),
        index_post_ms=_avg_ms(post_index_ms),
    )


def _collect_recent_events(db: Session, limit: int = 50) -> list[PipelineRecentEvent]:
    rows = (
        db.query(OperationLog, User.username)
        .outerjoin(User, OperationLog.user_id == User.id)
        .filter(OperationLog.action.in_(sorted(ALL_PIPELINE_ACTIONS)))
        .order_by(OperationLog.id.desc())
        .limit(limit)
        .all()
    )
    events: list[PipelineRecentEvent] = []
    for log, username in rows:
        events.append(
            PipelineRecentEvent(
                id=log.id,
                action=log.action,
                user_id=log.user_id,
                username=username or "",
                target_id=log.target_id,
                detail=log.detail,
                created_at=to_beijing_time(log.created_at).isoformat() if log.created_at else "",
                log_deep_link=f"/admin/logs?tab=logs&user_id={log.user_id}",
            ),
        )
    return events


def _collect_ocr_telemetry(db: Session, window: MetricsWindow) -> list[PipelineOcrAggStat]:
    rows = (
        _logs_base_query(db, window)
        .filter(OperationLog.action == ACTION_KB_EXTRACT_DONE)
        .all()
    )
    counts: dict[str, int] = defaultdict(int)
    for row in rows:
        parsed = parse_detail_kv(row.detail)
        for field in ("ocr_engine", "ocr_quality"):
            value = parsed.get(field)
            if value:
                counts[f"{field}:{value}"] += 1
        if parsed.get("ocr_review_recommended", "").lower() == "true":
            counts["ocr_review_recommended:true"] += 1
    return [
        PipelineOcrAggStat(key=key, count=count)
        for key, count in sorted(counts.items(), key=lambda item: (-item[1], item[0]))
    ]


def _queue_metrics() -> list[PipelineQueueMetric]:
    payload = get_mq_status()
    queues: list[PipelineQueueMetric] = []
    for queue in payload.get("queues", []):
        label = str(queue.get("label", ""))
        if label not in QUEUE_MONITOR_LABELS:
            continue
        count = int(queue.get("message_count") or 0)
        warning = label.endswith("_dlq") and count > 0
        if not warning and label in {"extract_main", "index_main"}:
            warning = count >= QUEUE_DEPTH_WARN
        queues.append(
            PipelineQueueMetric(
                name=str(queue.get("name", "")),
                label=label,
                message_count=count,
                warning=warning,
            ),
        )
    order = {label: idx for idx, label in enumerate(sorted(QUEUE_MONITOR_LABELS))}
    queues.sort(key=lambda item: order.get(item.label, 99))
    return queues


def build_pipeline_metrics(db: Session, *, window: MetricsWindow = "24h") -> PipelineMetricsResponse:
    cache_key = window
    now = time.monotonic()
    cached = _cache.get(cache_key)
    if cached and now - cached[0] < METRICS_CACHE_TTL_SEC:
        response = cached[1].model_copy(deep=True)
        response.cached = True
        return response

    queues = _queue_metrics()
    extract_failures = _count_actions(db, window, _EXTRACT_FAILURE_ACTIONS)
    index_failures = _count_actions(db, window, _INDEX_FAILURE_ACTIONS)
    extract_done = _count_actions(db, window, frozenset({ACTION_KB_EXTRACT_DONE}))
    index_done = _count_actions(db, window, frozenset({ACTION_KB_INDEX_DONE}))
    provider_stats = _collect_provider_stats(db, window)
    ocr_telemetry = _collect_ocr_telemetry(db, window)
    avg_stage_ms = _collect_avg_stage_ms(db, window)
    recent_events = _collect_recent_events(db)

    dlq_total = sum(q.message_count for q in queues if q.label.endswith("_dlq"))
    extract_depth = next((q.message_count for q in queues if q.label == "extract_main"), 0)
    index_depth = next((q.message_count for q in queues if q.label == "index_main"), 0)

    warnings: list[str] = []
    if dlq_total > 0:
        warnings.append("dlq_nonzero")
    if extract_depth >= QUEUE_DEPTH_WARN:
        warnings.append("extract_queue_backlog")
    if index_depth >= QUEUE_DEPTH_WARN:
        warnings.append("index_queue_backlog")

    high_fail_providers = [
        stat.provider
        for stat in provider_stats
        if (stat.failure_count + stat.success_count) >= FAIL_RATE_MIN_SAMPLES
        and stat.failure_rate >= FAIL_RATE_WARN
    ]
    if high_fail_providers:
        warnings.append("provider_failure_rate")

    kpis = [
        PipelineKpiMetric(
            key="extract_queue_depth",
            value=extract_depth,
            warning=extract_depth >= QUEUE_DEPTH_WARN,
            deep_link="/admin/mq",
        ),
        PipelineKpiMetric(
            key="index_queue_depth",
            value=index_depth,
            warning=index_depth >= QUEUE_DEPTH_WARN,
            deep_link="/admin/mq",
        ),
        PipelineKpiMetric(
            key="extract_done_24h",
            value=extract_done,
            deep_link="/admin/logs?tab=logs",
        ),
        PipelineKpiMetric(
            key="index_done_24h",
            value=index_done,
            deep_link="/admin/logs?tab=logs",
        ),
        PipelineKpiMetric(
            key="extract_failures_24h",
            value=extract_failures,
            warning=extract_failures > 0,
            deep_link="/admin/logs?tab=logs",
        ),
        PipelineKpiMetric(
            key="index_failures_24h",
            value=index_failures,
            warning=index_failures > 0,
            deep_link="/admin/logs?tab=logs",
        ),
        PipelineKpiMetric(
            key="dlq_total",
            value=dlq_total,
            warning=dlq_total > 0,
            deep_link="/admin/mq",
        ),
    ]

    generated_at = to_beijing_time(naive_db_now()).isoformat()
    response = PipelineMetricsResponse(
        window=window,
        generated_at=generated_at,
        cached=False,
        queues=queues,
        kpis=kpis,
        provider_failures=provider_stats,
        ocr_telemetry=ocr_telemetry,
        avg_stage_ms=avg_stage_ms,
        recent_events=recent_events,
        warnings=warnings,
    )
    _cache[cache_key] = (now, response.model_copy(deep=True))
    return response


def reset_pipeline_metrics_cache() -> None:
    _cache.clear()
