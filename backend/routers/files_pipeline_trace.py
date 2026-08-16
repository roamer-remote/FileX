# Copyright (c) 2026 徐泽宇
"""086 read API: single-file KB pipeline trace."""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from database import get_db
from middleware.auth import get_current_user
from models.user import User
from schemas.kb_pipeline_visualization import FilePipelineTraceResponse
from services.acl_service import get_readable_file
from services.kb_pipeline_trace_service import build_file_pipeline_trace

router = APIRouter()


@router.get("/{file_id}/pipeline-trace", response_model=FilePipelineTraceResponse)
def get_file_pipeline_trace(
    file_id: int,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> FilePipelineTraceResponse:
    f = get_readable_file(db, user, file_id)
    if f is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="资料不存在")
    return build_file_pipeline_trace(db, f)
