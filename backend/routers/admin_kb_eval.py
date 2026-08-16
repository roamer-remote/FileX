# Copyright (c) 2026 徐泽宇
"""Admin API for RAGAS online evaluation dashboard."""

from __future__ import annotations

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from database import get_db
from middleware.auth import get_admin_user
from models.user import User
from services.kb_eval_service import (
    DEFAULT_LOW_SCORE_THRESHOLD,
    is_ragas_online_eval_enabled,
    query_eval_samples,
    query_eval_summary,
    query_eval_trend,
    ragas_online_eval_sample_rate,
    ragas_online_eval_timeout_seconds,
)

router = APIRouter()


def _status_filter(
    status_filter: str | None = Query(
        None,
        pattern="^(pending|running|succeeded|failed|skipped)$",
        description="评估状态筛选",
    ),
) -> str | None:
    return status_filter


def _sample_type_filter(
    sample_type: str | None = Query(
        None,
        pattern="^(answer|recall_no_hit)$",
        description="样本类型筛选：answer=正常回答样本；recall_no_hit=召回质量样本",
    ),
) -> str | None:
    return sample_type


@router.get("/kb-search-eval/summary")
def get_kb_search_eval_summary(
    days: int = Query(7, ge=1, le=90),
    workspace_id: int | None = Query(None, ge=1),
    user_id: int | None = Query(None, ge=1),
    status_filter: str | None = Depends(_status_filter),
    db: Session = Depends(get_db),
    _admin: User = Depends(get_admin_user),
) -> dict:
    data = query_eval_summary(
        db,
        days=days,
        workspace_id=workspace_id,
        user_id=user_id,
        status_filter=status_filter,
    )
    data["enabled"] = is_ragas_online_eval_enabled(db)
    data["sample_rate"] = ragas_online_eval_sample_rate(db)
    data["timeout_seconds"] = ragas_online_eval_timeout_seconds(db)
    return data


@router.get("/kb-search-eval/trend")
def get_kb_search_eval_trend(
    days: int = Query(7, ge=1, le=90),
    granularity: str = Query("day", pattern="^(hour|day)$"),
    workspace_id: int | None = Query(None, ge=1),
    user_id: int | None = Query(None, ge=1),
    status_filter: str | None = Depends(_status_filter),
    db: Session = Depends(get_db),
    _admin: User = Depends(get_admin_user),
) -> dict:
    return {
        "days": days,
        "granularity": granularity,
        "points": query_eval_trend(
            db,
            days=days,
            granularity=granularity,
            workspace_id=workspace_id,
            user_id=user_id,
            status_filter=status_filter,
        ),
    }


@router.get("/kb-search-eval/samples")
def get_kb_search_eval_samples(
    days: int = Query(7, ge=1, le=90),
    workspace_id: int | None = Query(None, ge=1),
    user_id: int | None = Query(None, ge=1),
    status_filter: str | None = Depends(_status_filter),
    sample_type: str | None = Depends(_sample_type_filter),
    low_score_threshold: float | None = Query(DEFAULT_LOW_SCORE_THRESHOLD, ge=0.0, le=1.0),
    limit: int = Query(50, ge=1, le=200),
    db: Session = Depends(get_db),
    _admin: User = Depends(get_admin_user),
) -> dict:
    items = query_eval_samples(
        db,
        days=days,
        workspace_id=workspace_id,
        user_id=user_id,
        status_filter=status_filter,
        sample_type=sample_type,
        low_score_threshold=low_score_threshold,
        limit=limit,
    )
    return {"items": items, "total": len(items)}
