# Copyright (c) 2026 徐泽宇
"""086 admin read API: KB pipeline topology."""

from __future__ import annotations

from typing import Literal

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from database import get_db
from middleware.auth import get_admin_user
from models.user import User
from schemas.kb_pipeline_visualization import PipelineMetricsResponse, PipelineTopologyResponse
from services.kb_pipeline_metrics_service import build_pipeline_metrics
from services.kb_pipeline_topology_service import build_pipeline_topology

router = APIRouter()


@router.get("/kb-pipeline/topology", response_model=PipelineTopologyResponse)
def get_kb_pipeline_topology(
    db: Session = Depends(get_db),
    _admin: User = Depends(get_admin_user),
) -> PipelineTopologyResponse:
    return build_pipeline_topology(db)


@router.get("/kb-pipeline/metrics", response_model=PipelineMetricsResponse)
def get_kb_pipeline_metrics(
    window: Literal["1h", "24h", "7d"] = Query("24h"),
    db: Session = Depends(get_db),
    _admin: User = Depends(get_admin_user),
) -> PipelineMetricsResponse:
    return build_pipeline_metrics(db, window=window)
