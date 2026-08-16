from __future__ import annotations

import json
from unittest.mock import patch
import pytest
from pydantic import ValidationError

from main import app
from models.file import File as FileModel
from models.agent_run import AgentRun, AgentRunEvent
from models.kb_chunk import KbChunk
from models.kb_extract_job import KbExtractJob
from models.kb_index_job import KbIndexJob
from models.kb_search_audit_log import KbSearchAuditLog
from models.operation_log import OperationLog
from models.user import User
from services.kb_pipeline_log_service import ACTION_KB_EXTRACT_DONE, format_kb_pipeline_detail
from services.rag_quality_failure_service import build_failure_event, persist_failure_event, project_failure_event
from services.workspace_service import ensure_personal_workspace, get_personal_workspace

from schemas.kb_quality_workbench import (
    BoundedFailureEvent,
    ProjectionState,
    QualityWorkbenchCorrelation,
    QualityWorkbenchResponse,
)
from services.kb_quality_workbench_service import (
    build_bounded_quality_workbench_response,
    quality_workbench_query_hash,
    select_quality_trace,
)
from datetime import datetime, timedelta, timezone


def test_quality_workbench_route_is_registered_in_application() -> None:
    routes = set(app.openapi().get("paths", {}))
    assert "/api/knowledge-base/quality-workbench" in routes


def test_quality_workbench_response_accepts_partial_and_bounded_sections() -> None:
    response = QualityWorkbenchResponse(
        correlation=QualityWorkbenchCorrelation(
            file_id=807,
            job_id=42,
            trace_id="0123456789abcdef0123456789abcdef",
            query_hash="0123456789abcdef",
            request_scope_id="scope-1",
            versions={"schema_version": "187.1"},
        ),
        extraction=ProjectionState(state="present", data={"file_id": 807, "job_id": 42}),
        retrieval=ProjectionState(
            state="partial",
            data={"trace_id": "0123456789abcdef0123456789abcdef"},
        ),
        evidence=ProjectionState(state="missing"),
        answer=ProjectionState(state="unknown"),
        truncated=True,
        truncated_sections=["retrieval"],
    )

    dumped = response.model_dump(mode="json")

    assert dumped["schema_version"] == "187.1"
    assert dumped["retrieval"]["state"] == "partial"
    assert dumped["truncated_sections"] == ["retrieval"]


def test_quality_workbench_response_rejects_invalid_projection_state() -> None:
    with pytest.raises(ValidationError):
        ProjectionState(state="not-a-state")


@pytest.mark.parametrize("state", ["unknown", "missing", "forbidden"])
def test_quality_workbench_projection_absence_states_cannot_carry_data(state: str) -> None:
    with pytest.raises(ValidationError):
        ProjectionState(state=state, data={"secret": "must not pass"})


@pytest.mark.parametrize("state", ["present", "partial"])
def test_quality_workbench_projection_data_states_require_data(state: str) -> None:
    with pytest.raises(ValidationError):
        ProjectionState(state=state)


def test_quality_workbench_failure_event_is_bounded_and_typed() -> None:
    event = BoundedFailureEvent(
        event_key="a" * 32,
        stage="retrieval",
        reason="timeout",
        provider="ollama",
        file_id=807,
        job_id=42,
        request_id="request-1",
        trace_id="0123456789abcdef0123456789abcdef",
        model_version="m1",
        occurred_at="2026-08-14T10:00:00+08:00",
        retryable=True,
        summary="timeout",
    )
    assert len(event.summary) == 7
    with pytest.raises(ValidationError):
        BoundedFailureEvent(
            event_key="not-hex",
            stage="retrieval",
            reason="timeout",
            file_id=807,
            job_id=42,
            request_id="request-1",
            occurred_at="2026-08-14T10:00:00+08:00",
            retryable=True,
            summary="timeout",
        )


def test_quality_workbench_failure_events_are_ordered_before_the_fifty_item_bound() -> None:
    response = build_bounded_quality_workbench_response(
        correlation=QualityWorkbenchCorrelation(
            file_id=807,
            job_id=42,
            request_scope_id="scope-1",
            versions={"schema_version": "187.1"},
        ),
        extraction=ProjectionState(state="missing"),
        retrieval=ProjectionState(state="missing"),
        evidence=ProjectionState(state="missing"),
        answer=ProjectionState(state="missing"),
        failures=[
            BoundedFailureEvent(
                event_key=f"{index:032x}",
                stage="retrieval",
                reason="timeout",
                file_id=807,
                job_id=42,
                request_id="scope-1",
                occurred_at="2026-08-14T10:00:00+08:00",
                retryable=True,
                summary="timeout",
            )
            for index in range(3)
        ],
    )

    assert [event.event_key for event in response.failures] == [f"{index:032x}" for index in (2, 1, 0)]


def test_quality_workbench_correlation_keeps_trace_and_query_hash_bounded() -> None:
    correlation = QualityWorkbenchCorrelation(
        file_id=807,
        job_id=None,
        trace_id=None,
        query_hash=None,
        request_scope_id="scope-1",
        versions={"schema_version": "187.1"},
    )

    assert correlation.file_id == 807
    assert correlation.job_id is None
    assert correlation.query_hash is None
    with pytest.raises(ValidationError):
        QualityWorkbenchCorrelation(
            file_id=807,
            request_scope_id="scope-1",
            trace_id="x" + "0" * 32,
        )


def test_quality_workbench_query_hash_is_stable_and_redacts_query_content() -> None:
    assert quality_workbench_query_hash("  What is RAG?  ") == quality_workbench_query_hash(
        "  What is RAG?  "
    )
    assert len(quality_workbench_query_hash("What is RAG?")) == 16
    assert "RAG" not in quality_workbench_query_hash("What is RAG?")


def test_select_quality_trace_requires_exact_scope_and_uses_terminal_recency() -> None:
    traces = [
        {
            "id": 2,
            "file_id": 42,
            "job_id": 7,
            "trace_id": "b" * 32,
            "finished_at": None,
            "created_at": "2026-08-14T10:00:00+08:00",
            "status": "running",
        },
        {
            "id": 1,
            "file_id": 42,
            "job_id": 7,
            "trace_id": "a" * 32,
            "finished_at": "2026-08-14T09:00:00+08:00",
            "created_at": "2026-08-14T08:00:00+08:00",
            "status": "done",
        },
        {
            "id": 3,
            "file_id": 99,
            "job_id": 7,
            "trace_id": "c" * 32,
            "finished_at": "2026-08-14T11:00:00+08:00",
            "created_at": "2026-08-14T10:00:00+08:00",
            "status": "done",
        },
    ]

    assert select_quality_trace(traces, file_id=42, job_id=7) == traces[1]
    assert select_quality_trace(traces, file_id=42, job_id=7, trace_id="a" * 32) == traces[1]
    assert select_quality_trace(traces, file_id=42, job_id=7, trace_id="c" * 32) is None


def test_quality_workbench_bounded_response_marks_sections_partial_in_contract_order() -> None:
    response = build_bounded_quality_workbench_response(
        correlation=QualityWorkbenchCorrelation(
            file_id=42,
            job_id=7,
            request_scope_id="scope-1",
            versions={"schema_version": "187.1"},
        ),
        extraction=ProjectionState(state="present", data={"payload": "x" * 20_000}),
        retrieval=ProjectionState(state="present", data={"payload": "x" * 20_000}),
        evidence=ProjectionState(state="present", data={"payload": "x" * 20_000}),
        answer=ProjectionState(state="present", data={"payload": "x" * 20_000}),
        failures=[
            BoundedFailureEvent(
                event_key=f"{index:032x}",
                stage="retrieval",
                reason="timeout",
                file_id=42,
                job_id=7,
                request_id="scope-1",
                occurred_at="2026-08-14T10:00:00+08:00",
                retryable=True,
                summary="x" * 240,
            )
            for index in range(51)
        ],
    )

    encoded = response.model_dump_json().encode("utf-8")
    assert len(encoded) <= 64 * 1024
    assert response.truncated is True
    assert response.truncated_sections == sorted(
        response.truncated_sections,
        key=("retrieval", "evidence", "answer", "extraction", "failures").index,
    )
    assert "failures" in response.truncated_sections
    assert response.retrieval.state == "partial"


def test_quality_workbench_route_is_registered_under_knowledge_base() -> None:
    routes = set(app.openapi().get("paths", {}))
    assert "/api/knowledge-base/quality-workbench" in routes


def test_quality_workbench_api_applies_file_acl(client, db_session, regular_user, jwt_token) -> None:
    workspace = get_personal_workspace(db_session, regular_user.id)
    assert workspace is not None
    visible_file = FileModel(
        user_id=regular_user.id,
        workspace_id=workspace.id,
        filename="visible.txt",
        original_name="visible.txt",
        file_path="/tmp/visible.txt",
        file_size=1,
        mime_type="text/plain",
        md5_hash="a" * 32,
        has_md=False,
    )
    db_session.add(visible_file)
    db_session.flush()
    response = client.get(
        "/api/knowledge-base/quality-workbench",
        params={"file_id": visible_file.id},
        headers={"Authorization": f"Bearer {jwt_token}"},
    )
    assert response.status_code == 200
    assert response.json()["extraction"]["state"] == "missing"

    hidden_user = User(
        username="hidden-user",
        password_hash="not-used",
        is_active=True,
        primary_department_id=regular_user.primary_department_id,
    )
    db_session.add(hidden_user)
    db_session.flush()
    hidden_workspace = ensure_personal_workspace(db_session, hidden_user)
    hidden_file = FileModel(
        user_id=hidden_user.id,
        workspace_id=hidden_workspace.id,
        filename="hidden.txt",
        original_name="hidden.txt",
        file_path="/tmp/hidden.txt",
        file_size=1,
        mime_type="text/plain",
        md5_hash="b" * 32,
        has_md=False,
    )
    db_session.add(hidden_file)
    db_session.flush()
    denied = client.get(
        "/api/knowledge-base/quality-workbench",
        params={"file_id": hidden_file.id},
        headers={"Authorization": f"Bearer {jwt_token}"},
    )
    assert denied.status_code == 404


def test_quality_workbench_options_are_file_scoped_extract_jobs_with_linked_traces(
    client, db_session, regular_user, jwt_token
) -> None:
    workspace = get_personal_workspace(db_session, regular_user.id)
    assert workspace is not None
    file_row = FileModel(
        user_id=regular_user.id,
        workspace_id=workspace.id,
        filename="options.txt",
        original_name="options.txt",
        file_path="/tmp/options.txt",
        file_size=1,
        mime_type="text/plain",
        md5_hash="7" * 32,
        has_md=False,
    )
    db_session.add(file_row)
    db_session.flush()
    done_job = KbExtractJob(
        user_id=regular_user.id,
        file_id=file_row.id,
        status="done",
        provider="mineru",
    )
    error_job = KbExtractJob(
        user_id=regular_user.id,
        file_id=file_row.id,
        status="error",
        provider="legacy",
    )
    db_session.add_all([done_job, error_job])
    db_session.flush()
    index_job = KbIndexJob(
        user_id=regular_user.id,
        file_id=file_row.id,
        status="done",
    )
    db_session.add(index_job)
    db_session.flush()
    foreign_file = FileModel(
        user_id=regular_user.id,
        workspace_id=workspace.id,
        filename="foreign-options.txt",
        original_name="foreign-options.txt",
        file_path="/tmp/foreign-options.txt",
        file_size=1,
        mime_type="text/plain",
        md5_hash="8" * 32,
        has_md=False,
    )
    db_session.add(foreign_file)
    db_session.flush()
    foreign_job = KbExtractJob(
        user_id=regular_user.id,
        file_id=foreign_file.id,
        status="done",
        provider="foreign",
    )
    db_session.add(foreign_job)
    db_session.flush()
    trace_id = "7" * 32
    db_session.add(
        KbSearchAuditLog(
            user_id=regular_user.id,
            workspace_id=workspace.id,
            query="private query must not be returned",
            hit_file_ids=f"[{file_row.id}]",
            top_k=8,
            trace_id=trace_id,
            query_hash=quality_workbench_query_hash("private query must not be returned"),
            trace_payload=json.dumps(
                {
                    "schema_version": "187.1",
                    "trace_id": trace_id,
                    "request_scope": "options-scope",
                    "user_id": regular_user.id,
                    "workspace_id": workspace.id,
                    "job_id": done_job.id,
                    "status": "completed",
                    "final_file_ids": [file_row.id],
                }
            ),
            status="completed",
        )
    )
    db_session.add(
        KbSearchAuditLog(
            user_id=regular_user.id,
            workspace_id=workspace.id,
            query="cross-job trace",
            hit_file_ids=f"[{file_row.id}]",
            top_k=8,
            trace_id="9" * 32,
            query_hash=quality_workbench_query_hash("cross-job trace"),
            trace_payload=json.dumps(
                {
                    "schema_version": "187.1",
                    "trace_id": "9" * 32,
                    "request_scope": "cross-job-scope",
                    "user_id": regular_user.id,
                    "workspace_id": workspace.id,
                    "job_id": foreign_job.id,
                    "status": "completed",
                    "final_file_ids": [file_row.id],
                }
            ),
            status="completed",
        )
    )
    db_session.add(
        KbSearchAuditLog(
            user_id=regular_user.id + 999,
            workspace_id=workspace.id,
            query="other user's query",
            hit_file_ids=f"[{file_row.id}]",
            top_k=8,
            trace_id="8" * 32,
            query_hash=quality_workbench_query_hash("other user's query"),
            trace_payload=json.dumps(
                {
                    "schema_version": "187.1",
                    "trace_id": "8" * 32,
                    "request_scope": "hidden-options-scope",
                    "user_id": regular_user.id + 999,
                    "workspace_id": workspace.id,
                    "job_id": done_job.id,
                    "status": "completed",
                    "final_file_ids": [file_row.id],
                }
            ),
            status="completed",
        )
    )
    db_session.flush()

    response = client.get(
        "/api/knowledge-base/quality-workbench/options",
        params={"file_id": file_row.id},
        headers={"Authorization": f"Bearer {jwt_token}"},
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["file_id"] == file_row.id
    assert [item["job_id"] for item in payload["jobs"]] == [error_job.id, done_job.id]
    assert index_job.id not in [item["job_id"] for item in payload["jobs"]]
    assert payload["jobs"][0]["traces"] == []
    assert payload["jobs"][1]["traces"][0]["trace_id"] == trace_id
    assert all(
        option["trace_id"] != "9" * 32
        for job_option in payload["jobs"]
        for option in job_option["traces"]
    )
    assert "query" not in payload["jobs"][1]["traces"][0]


def test_quality_workbench_api_keeps_extraction_manifest_on_requested_job(
    client, db_session, regular_user, jwt_token
) -> None:
    workspace = get_personal_workspace(db_session, regular_user.id)
    assert workspace is not None
    file_row = FileModel(
        user_id=regular_user.id,
        workspace_id=workspace.id,
        filename="job-scoped.txt",
        original_name="job-scoped.txt",
        file_path="/tmp/job-scoped.txt",
        file_size=1,
        mime_type="text/plain",
        md5_hash="c" * 32,
        has_md=False,
    )
    db_session.add(file_row)
    db_session.flush()
    job = KbExtractJob(
        user_id=regular_user.id,
        file_id=file_row.id,
        status="completed",
        provider="test",
        attempts=1,
    )
    db_session.add(job)
    db_session.flush()
    first_job = KbExtractJob(user_id=regular_user.id, file_id=file_row.id, status="done")
    second_job = KbExtractJob(user_id=regular_user.id, file_id=file_row.id, status="done")
    db_session.add_all([first_job, second_job])
    db_session.flush()
    db_session.add_all(
        [
            OperationLog(
                user_id=regular_user.id,
                action=ACTION_KB_EXTRACT_DONE,
                target_type="file",
                target_id=file_row.id,
                detail=format_kb_pipeline_detail(
                    job_id=first_job.id,
                    provider="first-provider",
                    engine="first-engine",
                    provider_ms=1,
                    persist_ms=2,
                    side_effects_ms=3,
                ),
            ),
            OperationLog(
                user_id=regular_user.id,
                action=ACTION_KB_EXTRACT_DONE,
                target_type="file",
                target_id=file_row.id,
                detail=format_kb_pipeline_detail(
                    job_id=second_job.id,
                    provider="second-provider",
                    engine="second-engine",
                    provider_ms=4,
                    persist_ms=5,
                    side_effects_ms=6,
                ),
            ),
        ]
    )
    db_session.flush()
    persist_failure_event(
        db_session,
        regular_user.id,
        build_failure_event(
            stage="retrieval",
            reason="timeout",
            file_id=file_row.id,
            job_id=first_job.id,
            request_id="request-1",
            trace_id="a" * 32,
            summary="retrieval timeout",
        ),
    )

    response = client.get(
        "/api/knowledge-base/quality-workbench",
        params={"file_id": file_row.id, "job_id": first_job.id, "trace_id": "a" * 32},
        headers={"Authorization": f"Bearer {jwt_token}"},
    )
    assert response.status_code == 200
    payload = response.json()
    assert payload["correlation"]["job_id"] == first_job.id
    assert payload["extraction"]["data"]["job_id"] == first_job.id
    assert payload["extraction"]["data"]["engine"] == "first-engine"
    assert payload["retrieval"]["state"] == "missing"
    assert len(payload["failures"]) == 1
    assert payload["failures"][0]["job_id"] == first_job.id

    without_job = client.get(
        "/api/knowledge-base/quality-workbench",
        params={"file_id": file_row.id},
        headers={"Authorization": f"Bearer {jwt_token}"},
    )
    assert without_job.status_code == 200
    without_job_payload = without_job.json()
    assert without_job_payload["correlation"]["job_id"] is None
    assert without_job_payload["extraction"]["state"] == "missing"
    assert without_job_payload["retrieval"]["state"] == "missing"
    assert without_job_payload["failures"] == []

    unsupported = client.get(
        "/api/knowledge-base/quality-workbench",
        params={"file_id": file_row.id, "version": "187.0"},
        headers={"Authorization": f"Bearer {jwt_token}"},
    )
    assert unsupported.status_code == 400


def test_quality_workbench_api_projects_acl_filtered_persisted_retrieval_trace(
    client, db_session, regular_user, jwt_token
) -> None:
    workspace = get_personal_workspace(db_session, regular_user.id)
    assert workspace is not None
    file_row = FileModel(
        user_id=regular_user.id,
        workspace_id=workspace.id,
        filename="trace.txt",
        original_name="trace.txt",
        file_path="/tmp/trace.txt",
        file_size=1,
        mime_type="text/plain",
        md5_hash="d" * 32,
        has_md=False,
    )
    db_session.add(file_row)
    db_session.flush()
    job = KbExtractJob(
        user_id=regular_user.id,
        file_id=file_row.id,
        status="completed",
        provider="test",
        attempts=1,
    )
    db_session.add(job)
    db_session.flush()
    chunk = KbChunk(
            user_id=regular_user.id,
            workspace_id=workspace.id,
            file_id=file_row.id,
            chunk_index=0,
            source="main_md",
            text="trace source",
            char_start=0,
            char_end=12,
            loc_type="page",
            loc_start=3,
            loc_end=3,
            loc_label="p. 3",
        )
    db_session.add(chunk)
    db_session.flush()
    trace_id = "e" * 32
    db_session.add(
        KbSearchAuditLog(
            user_id=regular_user.id,
            workspace_id=workspace.id,
            query="what is rag",
            hit_file_ids=f"[{file_row.id}]",
            top_k=8,
            trace_id=trace_id,
            request_scope="scope-real",
            query_hash=quality_workbench_query_hash("what is rag"),
            trace_payload='{"schema_version":"187.1","trace_id":"%s","request_scope":"scope-real","user_id":%d,"workspace_id":%d,"job_id":%d,"query_normalized":"what is rag","counts":{"final_results":1},"final_file_ids":[%d],"final_chunk_ids":[%d],"expansion_ids":[],"expansion_summary":{},"timings_ms":{},"cache_hit":false,"fallback_mode":null,"fallback_reason":null,"compatibility":{"provider":"pgvector","index_version":"idx-1"},"truncated":false}'
            % (trace_id, regular_user.id, workspace.id, job.id, file_row.id, chunk.id),
        )
    )
    db_session.flush()

    response = client.get(
        "/api/knowledge-base/quality-workbench",
        params={"file_id": file_row.id, "job_id": job.id, "trace_id": trace_id, "query": "what is rag"},
        headers={"Authorization": f"Bearer {jwt_token}"},
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["correlation"]["request_scope_id"] == "scope-real"
    assert payload["retrieval"]["state"] == "present"
    assert payload["retrieval"]["data"]["trace_id"] == trace_id
    assert payload["evidence"]["state"] == "partial"
    assert payload["evidence"]["data"]["chunk_ids"] == [chunk.id]
    assert payload["answer"]["state"] == "missing"
    assert payload["compatibility"]["index_version"] == "idx-1"


def test_quality_workbench_trace_lookup_does_not_cross_search_owner(
    client, db_session, regular_user, jwt_token
) -> None:
    workspace = get_personal_workspace(db_session, regular_user.id)
    assert workspace is not None
    file_row = FileModel(
        user_id=regular_user.id,
        workspace_id=workspace.id,
        filename="owner-trace.txt",
        original_name="owner-trace.txt",
        file_path="/tmp/owner-trace.txt",
        file_size=1,
        mime_type="text/plain",
        md5_hash="f" * 32,
        has_md=False,
    )
    db_session.add(file_row)
    db_session.flush()
    trace_id = "1" * 32
    db_session.add(
        KbSearchAuditLog(
            user_id=regular_user.id + 999,
            workspace_id=workspace.id,
            query="private query",
            hit_file_ids=f"[{file_row.id}]",
            top_k=8,
            trace_id=trace_id,
            request_scope="other-user-scope",
            query_hash=quality_workbench_query_hash("private query"),
            trace_payload=json.dumps({
                "schema_version": "187.1", "trace_id": trace_id,
                "request_scope": "other-user-scope", "user_id": regular_user.id + 999,
                "workspace_id": workspace.id, "final_file_ids": [file_row.id],
            }),
        )
    )
    db_session.flush()
    response = client.get(
        "/api/knowledge-base/quality-workbench",
        params={"file_id": file_row.id, "trace_id": trace_id},
        headers={"Authorization": f"Bearer {jwt_token}"},
    )
    assert response.status_code == 200
    assert response.json()["retrieval"]["state"] == "missing"


def test_quality_workbench_projects_existing_agent_coverage_and_answer_summary(
    client, db_session, regular_user, jwt_token
) -> None:
    workspace = get_personal_workspace(db_session, regular_user.id)
    assert workspace is not None
    file_row = FileModel(
        user_id=regular_user.id,
        workspace_id=workspace.id,
        filename="answer-trace.txt",
        original_name="answer-trace.txt",
        file_path="/tmp/answer-trace.txt",
        file_size=1,
        mime_type="text/plain",
        md5_hash="0" * 32,
        has_md=False,
    )
    db_session.add(file_row)
    db_session.flush()
    job = KbExtractJob(
        user_id=regular_user.id,
        file_id=file_row.id,
        status="completed",
        provider="test",
        attempts=1,
    )
    db_session.add(job)
    db_session.flush()
    trace_id = "2" * 32
    run = AgentRun(
        user_id=regular_user.id,
        question_preview="what is rag",
        status="completed",
        expires_at=datetime.now(timezone.utc) + timedelta(days=1),
        summary_json={
            "router_kind": "kb_answer",
            "confidence": 0.91,
            "coverage_receipt": {
                "version": "2.0",
                "answerable": True,
                "selected_file_ids": [file_row.id],
                "covered_file_ids": [file_row.id],
                "dimensions": [{"id": "fact", "status": "covered", "reason_codes": []}],
            },
        },
    )
    db_session.add(run)
    db_session.flush()
    db_session.add(
        AgentRunEvent(
            run_id=run.id,
            seq=1,
            layer="tool",
            node_id="kb_search",
            label="资料库检索",
            phase="end",
            meta_json={"trace_id": trace_id},
        )
    )
    db_session.add(
        KbSearchAuditLog(
            user_id=regular_user.id,
            workspace_id=workspace.id,
            query="what is rag",
            hit_file_ids=f"[{file_row.id}]",
            top_k=8,
            trace_id=trace_id,
            request_scope="scope-answer",
            query_hash=quality_workbench_query_hash("what is rag"),
            trace_payload=json.dumps({
                "schema_version": "187.1", "trace_id": trace_id,
                "request_scope": "scope-answer", "user_id": regular_user.id,
                "workspace_id": workspace.id, "job_id": job.id, "agent_run_id": run.id,
                "final_file_ids": [file_row.id], "final_chunk_ids": [902],
            }),
        )
    )
    db_session.flush()

    response = client.get(
        "/api/knowledge-base/quality-workbench",
        params={"file_id": file_row.id, "job_id": job.id, "trace_id": trace_id, "query": "what is rag"},
        headers={"Authorization": f"Bearer {jwt_token}"},
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["evidence"]["state"] == "present"
    assert payload["evidence"]["data"]["answerable"] is True
    assert payload["answer"]["state"] == "present"
    assert payload["answer"]["data"]["confidence"] == 0.91


def test_quality_workbench_http_contract_stays_200_and_bounded_for_large_trace(
    client, db_session, regular_user, jwt_token
) -> None:
    workspace = get_personal_workspace(db_session, regular_user.id)
    assert workspace is not None
    file_row = FileModel(
        user_id=regular_user.id,
        workspace_id=workspace.id,
        filename="large-trace.txt",
        original_name="large-trace.txt",
        file_path="/tmp/large-trace.txt",
        file_size=1,
        mime_type="text/plain",
        md5_hash="1" * 32,
        has_md=False,
    )
    db_session.add(file_row)
    db_session.flush()
    job = KbExtractJob(
        user_id=regular_user.id,
        file_id=file_row.id,
        status="completed",
        provider="test",
        attempts=1,
    )
    db_session.add(job)
    db_session.flush()
    trace_id = "3" * 32
    db_session.add(
        KbSearchAuditLog(
            user_id=regular_user.id,
            workspace_id=workspace.id,
            query="large",
            hit_file_ids=f"[{file_row.id}]",
            top_k=8,
            trace_id=trace_id,
            request_scope="scope-large",
            query_hash=quality_workbench_query_hash("large"),
            trace_payload=json.dumps({
                "schema_version": "187.1", "trace_id": trace_id,
                "request_scope": "scope-large", "user_id": regular_user.id,
                "workspace_id": workspace.id, "job_id": job.id, "final_file_ids": [file_row.id],
                "final_chunk_ids": list(range(100)),
                "expansion_summary": {"large": "x" * 100_000},
            }),
        )
    )
    db_session.flush()

    response = client.get(
        "/api/knowledge-base/quality-workbench",
        params={"file_id": file_row.id, "job_id": job.id, "trace_id": trace_id},
        headers={"Authorization": f"Bearer {jwt_token}"},
    )

    assert response.status_code == 200
    assert len(response.content) <= 64 * 1024
    assert response.json()["truncated"] is True
    assert "retrieval" in response.json()["truncated_sections"]


def test_search_failure_persists_acl_checked_retrieval_quality_event(
    client, db_session, regular_user, jwt_token
) -> None:
    workspace = get_personal_workspace(db_session, regular_user.id)
    assert workspace is not None
    file_row = FileModel(
        user_id=regular_user.id,
        workspace_id=workspace.id,
        filename="retrieval-failure.txt",
        original_name="retrieval-failure.txt",
        file_path="/tmp/retrieval-failure.txt",
        file_size=1,
        mime_type="text/plain",
        md5_hash="2" * 32,
        has_md=False,
    )
    db_session.add(file_row)
    db_session.flush()
    job = KbExtractJob(
        user_id=regular_user.id,
        file_id=file_row.id,
        status="completed",
        provider="test",
        attempts=1,
    )
    db_session.add(job)
    db_session.flush()

    with patch("routers.knowledge_base.search_kb", side_effect=ValueError("bad retrieval")):
        response = client.post(
            "/api/knowledge-base/search",
            headers={"Authorization": f"Bearer {jwt_token}"},
            json={
                "query": "retrieval failure",
                "return_search_trace": True,
                "quality_job_id": job.id,
            },
        )

    assert response.status_code == 400
    failure = (
        db_session.query(OperationLog)
        .filter(OperationLog.action == "rag_quality_failure", OperationLog.target_id == file_row.id)
        .one()
    )
    event = project_failure_event(failure.detail)
    assert event is not None
    assert event.stage == "retrieval"
    assert event.reason == "unknown"
    assert event.job_id == job.id
