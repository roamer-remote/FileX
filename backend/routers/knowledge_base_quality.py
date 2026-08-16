# Copyright (c) 2026 徐泽宇
"""Read-only quality workbench projection for 187-P1."""

from __future__ import annotations

import json
import re
import uuid

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from sqlalchemy.orm import Session

from database import get_db
from middleware.auth import get_current_user
from models.agent_run import AgentRun, AgentRunEvent
from models.file import File as FileModel
from models.kb_chunk import KbChunk
from models.kb_extract_job import KbExtractJob
from models.kb_search_audit_log import KbSearchAuditLog
from models.operation_log import OperationLog
from models.user import User
from schemas.kb_quality_workbench import (
    BoundedFailureEvent,
    ProjectionState,
    QualityWorkbenchCorrelation,
    QualityWorkbenchJobOption,
    QualityWorkbenchOptionsResponse,
    QualityWorkbenchResponse,
    QualityWorkbenchTraceOption,
)
from services.acl_service import readable_file_ids_subquery
from services.kb_quality_manifest_service import ManifestReadError, build_extraction_manifest
from services.kb_quality_workbench_service import (
    TERMINAL_TRACE_STATUSES,
    build_bounded_quality_workbench_response,
    project_agent_quality_summary,
    quality_workbench_query_hash,
    select_quality_trace,
)
from services.rag_quality_failure_service import project_failure_event
from schemas.kb_retrieval_trace import RetrievalTrace

router = APIRouter()


@router.get("/quality-workbench/options", response_model=QualityWorkbenchOptionsResponse)
def get_quality_workbench_options(
    file_id: int = Query(..., gt=0),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Return only proven file/job/trace choices for the read-only workbench."""

    file_row = db.query(FileModel).filter(FileModel.id == file_id).first()
    if file_row is None or file_row.workspace_id is None:
        raise HTTPException(status_code=404, detail="资料不存在")
    visible = (
        db.query(FileModel.id)
        .filter(FileModel.id == file_id)
        .filter(
            FileModel.id.in_(
                readable_file_ids_subquery(db, current_user, int(file_row.workspace_id))
            )
        )
        .first()
    )
    if visible is None:
        raise HTTPException(status_code=404, detail="资料不存在")

    # 解析任务的可见性继承已通过的资料 ACL，不再按 job 所属用户缩小历史选项。
    jobs = (
        db.query(KbExtractJob)
        .filter(KbExtractJob.file_id == file_id)
        .order_by(KbExtractJob.id.desc())
        .limit(50)
        .all()
    )
    job_by_id = {int(job.id): job for job in jobs}
    traces_by_job: dict[int, list[QualityWorkbenchTraceOption]] = {
        job_id: [] for job_id in job_by_id
    }
    audit_rows = (
        db.query(KbSearchAuditLog)
        .filter(
            KbSearchAuditLog.workspace_id == int(file_row.workspace_id),
            KbSearchAuditLog.user_id == int(current_user.id),
            KbSearchAuditLog.trace_payload.isnot(None),
        )
        .order_by(KbSearchAuditLog.id.desc())
        .limit(250)
        .all()
    )
    trace_rows: list[tuple[int, int, QualityWorkbenchTraceOption]] = []
    for audit_row in audit_rows:
        try:
            candidate = RetrievalTrace.model_validate(json.loads(audit_row.trace_payload))
        except (TypeError, ValueError):
            continue
        candidate_job_id = candidate.job_id
        if candidate_job_id not in job_by_id or file_id not in candidate.final_file_ids:
            continue
        if audit_row.trace_id and audit_row.trace_id != candidate.trace_id:
            continue
        status = str(audit_row.status or candidate.status).lower()
        if status not in TERMINAL_TRACE_STATUSES:
            continue
        option = QualityWorkbenchTraceOption(
            trace_id=candidate.trace_id,
            status=status,
            query_hash=(
                audit_row.query_hash
                if audit_row.query_hash and re.fullmatch(r"[0-9a-f]{16}", audit_row.query_hash)
                else None
            ),
            created_at=audit_row.created_at,
            finished_at=audit_row.finished_at or candidate.finished_at,
        )
        trace_rows.append((int(candidate_job_id), int(audit_row.id), option))

    trace_rows.sort(
        key=lambda item: (
            item[2].finished_at is not None,
            str(item[2].finished_at or ""),
            str(item[2].created_at or ""),
            item[1],
        ),
        reverse=True,
    )
    seen_trace_ids: set[tuple[int, str]] = set()
    for job_id, _audit_id, option in trace_rows:
        trace_key = (job_id, option.trace_id)
        if trace_key in seen_trace_ids:
            continue
        seen_trace_ids.add(trace_key)
        traces_by_job[job_id].append(option)

    jobs_payload = [
        QualityWorkbenchJobOption(
            job_id=int(job.id),
            status=str(job.status),
            provider=job.provider,
            created_at=job.created_at,
            updated_at=job.updated_at,
            traces=traces_by_job[int(job.id)][:50],
        )
        for job in jobs
    ]
    return QualityWorkbenchOptionsResponse(file_id=file_id, jobs=jobs_payload)


@router.get("/quality-workbench", response_model=QualityWorkbenchResponse)
def get_quality_workbench(
    request: Request,
    file_id: int = Query(..., gt=0),
    job_id: int | None = Query(default=None, gt=0),
    query: str | None = Query(default=None, max_length=256),
    trace_id: str | None = Query(default=None, min_length=32, max_length=64, pattern=r"^[0-9a-f]+$"),
    version: str | None = Query(default=None, max_length=128),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    if version is not None and version != "187.1":
        raise HTTPException(status_code=400, detail="quality_workbench_version_unsupported")
    file_row = db.query(FileModel).filter(FileModel.id == file_id).first()
    if file_row is None or file_row.workspace_id is None:
        raise HTTPException(status_code=404, detail="资料不存在")
    visible = (
        db.query(FileModel.id)
        .filter(FileModel.id == file_id)
        .filter(
            FileModel.id.in_(
                readable_file_ids_subquery(db, current_user, int(file_row.workspace_id))
            )
        )
        .first()
    )
    if visible is None:
        raise HTTPException(status_code=404, detail="资料不存在")

    selected_job = None
    if job_id is not None:
        selected_job = (
            db.query(KbExtractJob)
            .filter(KbExtractJob.id == job_id, KbExtractJob.file_id == file_id)
            .first()
        )
        if selected_job is None:
            raise HTTPException(status_code=404, detail="解析任务不存在")

    extraction = ProjectionState(state="missing")
    selected_job_id = int(selected_job.id) if selected_job is not None else None
    if selected_job_id is not None:
        try:
            manifest = build_extraction_manifest(db, file_id, selected_job_id)
            extraction = ProjectionState(state="present", data=manifest.model_dump(mode="json"))
        except ManifestReadError as exc:
            extraction = ProjectionState(state="unknown")

    retrieval_trace: RetrievalTrace | None = None
    trace_query = db.query(KbSearchAuditLog).filter(
        KbSearchAuditLog.workspace_id == int(file_row.workspace_id),
        KbSearchAuditLog.user_id == int(current_user.id),
        KbSearchAuditLog.trace_payload.isnot(None),
    )
    if selected_job_id is None:
        trace_query = None
    elif trace_id is not None:
        trace_query = trace_query.filter(KbSearchAuditLog.trace_id == trace_id)
    elif query is not None:
        trace_query = trace_query.filter(
            KbSearchAuditLog.query_hash == quality_workbench_query_hash(query)
        )
    trace_candidates: list[dict[str, object]] = []
    for audit_row in (trace_query.limit(50) if trace_query is not None else []):
        try:
            candidate = RetrievalTrace.model_validate(json.loads(audit_row.trace_payload))
        except (TypeError, ValueError):
            continue
        if file_id not in candidate.final_file_ids or candidate.job_id != selected_job_id:
            continue
        candidate_data = candidate.model_dump(mode="python")
        candidate_data.update(
            {
                "id": audit_row.id,
                "file_id": file_id,
                "status": audit_row.status or candidate.status,
                "finished_at": audit_row.finished_at or candidate.finished_at,
                "created_at": audit_row.created_at,
            }
        )
        trace_candidates.append(candidate_data)
    selected_candidate = select_quality_trace(
        trace_candidates,
        file_id=file_id,
        job_id=selected_job_id,
        trace_id=trace_id,
    ) if selected_job_id is not None else None
    if selected_candidate is not None:
        retrieval_trace = RetrievalTrace.model_validate(selected_candidate)

    request_scope_id = (
        retrieval_trace.request_scope
        if retrieval_trace is not None
        else (getattr(request.state, "request_id", None) or uuid.uuid4().hex)
    )
    retrieval = ProjectionState(state="missing")
    evidence = ProjectionState(state="missing")
    answer = ProjectionState(state="missing")
    compatibility = None
    if retrieval_trace is not None:
        retrieval_data = retrieval_trace.model_dump(mode="json")
        retrieval_data["final_file_ids"] = [file_id] if file_id in retrieval_trace.final_file_ids else []
        retrieval_data["final_chunk_ids"] = []
        retrieval = ProjectionState(
            state="present" if not retrieval_trace.truncated else "partial",
            data=retrieval_data,
        )
        if retrieval_trace.final_chunk_ids:
            chunk_rows = (
                db.query(
                    KbChunk.id,
                    KbChunk.file_id,
                    KbChunk.chunk_index,
                    KbChunk.heading_path,
                    KbChunk.block_type,
                    KbChunk.content_kind,
                    KbChunk.loc_type,
                    KbChunk.loc_start,
                    KbChunk.loc_end,
                    KbChunk.loc_label,
                )
                .filter(
                    KbChunk.file_id == file_id,
                    KbChunk.id.in_(retrieval_trace.final_chunk_ids),
                    KbChunk.id.in_(
                        db.query(KbChunk.id).filter(
                            KbChunk.file_id.in_(
                                readable_file_ids_subquery(db, current_user, int(file_row.workspace_id))
                            )
                        )
                    ),
                )
                .all()
            )
            source_locations = [
                {
                    "chunk_id": int(row.id),
                    "file_id": int(row.file_id),
                    "chunk_index": row.chunk_index,
                    "heading_path": row.heading_path,
                    "block_type": row.block_type,
                    "content_kind": row.content_kind,
                    "loc_type": row.loc_type,
                    "loc_start": row.loc_start,
                    "loc_end": row.loc_end,
                    "loc_label": row.loc_label,
                }
                for row in chunk_rows
            ]
            visible_chunk_ids = [int(row.id) for row in chunk_rows]
            retrieval.data["final_file_ids"] = [file_id]
            retrieval.data["final_chunk_ids"] = visible_chunk_ids
            evidence = ProjectionState(
                state="partial",
                data={
                    "chunk_ids": visible_chunk_ids,
                    "file_ids": [file_id],
                    "coverage": retrieval_trace.counts.get("final_results", 0),
                    "source_locations": source_locations,
                },
            )
        if retrieval_trace.agent_run_id:
            run = (
                db.query(AgentRun)
                .filter(
                    AgentRun.id == retrieval_trace.agent_run_id,
                    AgentRun.user_id == int(current_user.id),
                )
                .first()
            )
            if run is not None:
                event_rows = db.query(AgentRunEvent.meta_json).filter(
                    AgentRunEvent.run_id == run.id
                ).all()
                trace_linked = any(
                    isinstance(meta, dict) and meta.get("trace_id") == retrieval_trace.trace_id
                    for (meta,) in event_rows
                )
                if trace_linked:
                    projected = project_agent_quality_summary(run.summary_json, file_id=file_id)
                    if projected is not None:
                        evidence_data, answer_data = projected
                        evidence = ProjectionState(
                            state="partial" if retrieval_trace.truncated else "present",
                            data={
                                **evidence_data,
                                "chunk_ids": [int(row.id) for row in chunk_rows],
                                "file_ids": [file_id],
                                "source_locations": source_locations,
                            },
                        )
                        answer = ProjectionState(state="present", data=answer_data)
        compatibility = retrieval_trace.compatibility or None
        versions = {
            "schema_version": "187.1",
            "requested_version": version,
            "retrieval_trace_schema": retrieval_trace.schema_version,
            "parser_version": None,
            "model_version": (retrieval_trace.compatibility or {}).get("embedding_model"),
            "chunk_version": (retrieval_trace.compatibility or {}).get("chunk_fingerprint"),
            "index_version": (retrieval_trace.compatibility or {}).get("index_version"),
            "embedding_model": (retrieval_trace.compatibility or {}).get("embedding_model"),
        }
    else:
        versions = {
            "parser_version": None,
            "model_version": None,
            "chunk_version": None,
            "index_version": None,
            "schema_version": "187.1",
            "requested_version": version,
        }
    correlation = QualityWorkbenchCorrelation(
        file_id=file_id,
        job_id=selected_job_id,
        trace_id=retrieval_trace.trace_id if retrieval_trace is not None else trace_id,
        query_hash=quality_workbench_query_hash(query) if query is not None else None,
        request_scope_id=str(request_scope_id)[:64],
        versions=versions,
    )
    failures: list[BoundedFailureEvent] = []
    if selected_job_id is not None:
        failure_rows = (
            db.query(OperationLog.detail)
            .filter(
                OperationLog.action == "rag_quality_failure",
                OperationLog.target_type == "file",
                OperationLog.target_id == file_id,
            )
            .all()
        )
        for (detail,) in failure_rows:
            event = project_failure_event(detail)
            if event is None or event.job_id != selected_job_id:
                continue
            if trace_id is not None and event.trace_id != trace_id:
                continue
            failures.append(
                BoundedFailureEvent.model_validate(
                    event.model_dump(exclude={"schema_version"})
                )
            )
    return build_bounded_quality_workbench_response(
        correlation=correlation,
        extraction=extraction,
        retrieval=retrieval,
        evidence=evidence,
        answer=answer,
        failures=failures,
        compatibility=compatibility,
    )
