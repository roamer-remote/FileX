# Copyright (c) 2026 徐泽宇
"""RAGAS online evaluation backend contract tests."""

from __future__ import annotations

from datetime import timedelta
from pathlib import Path
from uuid import uuid4

from fastapi import status
from sqlalchemy.orm import sessionmaker

from models.kb_search_eval import KbSearchEval
from models.operation_log import OperationLog
from models.user import User
from services.auth_service import hash_password
from services.enterprise_rbac_seed import get_unassigned_department_id
from services.kb_eval_service import (
    RagasEvalResult,
    _score_with_ragas,
    query_eval_trend,
    run_ragas_online_eval,
)
from services.system_setting_service import (
    KEY_KB_POST_LLM_BASE_URL,
    KEY_KB_POST_LLM_MODEL,
    KEY_KB_POST_LLM_PROVIDER,
    update_settings,
)
from utils.timezone import naive_db_now


def _result(
    *,
    faithfulness: float = 0.8,
    context_precision: float | None = 0.7,
    status: str = "succeeded",
) -> RagasEvalResult:
    return RagasEvalResult(
        status=status,
        faithfulness_score=faithfulness,
        context_precision_score=context_precision,
        metric_version="ragas-test Faithfulness LLMContextPrecisionWithoutReference",
        metric_variant="faithfulness+context_precision_without_reference",
        llm_provider="openai_compatible",
        llm_model="test-model",
    )


def test_run_ragas_online_eval_stores_hashes_previews_scores_and_operation_log(
    db_session, regular_user
):
    query = "用户完整问题不应长期明文保存" * 40
    answer = "完整回答也只能保存 preview" * 40

    record = run_ragas_online_eval(
        db_session,
        user_id=regular_user.id,
        workspace_id=123,
        query=query,
        answer=answer,
        contexts=["context one", "context two"],
        context_file_ids=[10, 11],
        context_chunk_ids=[100, 101],
        agent_run_id="run-1",
        evaluator=lambda *_args, **_kwargs: _result(faithfulness=0.91, context_precision=0.82),
    )

    db_session.refresh(record)
    assert record.status == "succeeded"
    assert record.metric_provider == "ragas"
    assert record.metric_variant == "faithfulness+context_precision_without_reference"
    assert record.faithfulness_score == 0.91
    assert record.context_precision_score == 0.82
    assert record.query_hash
    assert record.answer_hash
    assert len(record.query_preview) <= 512
    assert len(record.answer_preview) <= 512
    assert not hasattr(record, "query")
    assert not hasattr(record, "answer")
    assert record.context_file_ids_json == [10, 11]
    assert record.context_chunk_ids_json == [100, 101]
    assert record.context_count == 2
    assert record.duration_ms is not None
    assert record.evaluated_at is not None

    log = (
        db_session.query(OperationLog)
        .filter(OperationLog.action == "ragas_online_eval")
        .order_by(OperationLog.id.desc())
        .first()
    )
    assert log is not None
    assert log.target_type == "kb_search_eval"
    assert log.target_id == record.id
    assert "status=succeeded" in (log.detail or "")
    assert "faithfulness=0.91" in (log.detail or "")
    assert "context_precision=0.82" in (log.detail or "")


def test_run_ragas_online_eval_records_sample_type(db_session, regular_user):
    """sample_type 落库并写入操作日志；默认 answer。"""
    record = run_ragas_online_eval(
        db_session,
        user_id=regular_user.id,
        workspace_id=7,
        query="问题",
        answer="资料库未找到可核实依据。",
        contexts=["上下文"],
        sample_type="recall_no_hit",
        evaluator=lambda *_args, **_kwargs: _result(faithfulness=0.5, context_precision=0.6),
    )
    db_session.refresh(record)
    assert record.sample_type == "recall_no_hit"

    log = (
        db_session.query(OperationLog)
        .filter(OperationLog.action == "ragas_online_eval")
        .order_by(OperationLog.id.desc())
        .first()
    )
    assert "sample_type=recall_no_hit" in (log.detail or "")

    # 默认值 answer
    record2 = run_ragas_online_eval(
        db_session,
        user_id=regular_user.id,
        workspace_id=7,
        query="问题2",
        answer="回答2",
        contexts=["上下文2"],
        evaluator=lambda *_args, **_kwargs: _result(),
    )
    db_session.refresh(record2)
    assert record2.sample_type == "answer"


def test_run_ragas_online_eval_commits_running_record_before_scoring(
    engine,
):
    RealSession = sessionmaker(bind=engine)
    username = f"ragas_visible_{uuid4().hex[:12]}"
    run_id = str(uuid4())
    visible_during_scoring: list[tuple[str, str]] = []
    record_status: str | None = None
    record_id: int | None = None

    def evaluator(db, query, answer, contexts, timeout_seconds):
        del db, query, answer, contexts, timeout_seconds
        other = RealSession()
        try:
            row = (
                other.query(KbSearchEval)
                .filter(KbSearchEval.agent_run_id == run_id)
                .one()
            )
            visible_during_scoring.append((row.status, row.query_preview))
        finally:
            other.close()
        return _result()

    service_db = RealSession()
    try:
        user = User(
            username=username,
            password_hash=hash_password("password123"),
            is_admin=False,
            is_active=True,
            password_rev=0,
            primary_department_id=get_unassigned_department_id(service_db),
        )
        service_db.add(user)
        service_db.commit()
        service_db.refresh(user)

        record = run_ragas_online_eval(
            service_db,
            user_id=user.id,
            workspace_id=None,
            query="什么是北斗协作",
            answer="北斗协作是一个协作概念。",
            contexts=["北斗协作上下文。"],
            agent_run_id=run_id,
            evaluator=evaluator,
        )
        record_status = record.status if record is not None else None
        record_id = record.id if record is not None else None
    finally:
        service_db.rollback()
        if record_id is not None:
            service_db.query(OperationLog).filter(
                OperationLog.action == "ragas_online_eval",
                OperationLog.target_type == "kb_search_eval",
                OperationLog.target_id == record_id,
            ).delete(synchronize_session=False)
        service_db.query(KbSearchEval).filter(KbSearchEval.agent_run_id == run_id).delete(
            synchronize_session=False
        )
        service_db.query(User).filter(User.username == username).delete(
            synchronize_session=False
        )
        service_db.commit()
        service_db.close()

    assert visible_during_scoring == [("running", "什么是北斗协作")]
    assert record_status == "succeeded"


def test_run_ragas_online_eval_marks_failure_and_still_writes_operation_log(
    db_session, regular_user
):
    def boom(*_args, **_kwargs):
        raise TimeoutError("ragas timed out")

    record = run_ragas_online_eval(
        db_session,
        user_id=regular_user.id,
        workspace_id=None,
        query="问题",
        answer="回答",
        contexts=["上下文"],
        context_file_ids=[],
        context_chunk_ids=[],
        evaluator=boom,
    )

    db_session.refresh(record)
    assert record.status == "failed"
    assert record.error_code == "TimeoutError"
    assert "ragas timed out" in (record.error_message or "")

    log = (
        db_session.query(OperationLog)
        .filter(OperationLog.action == "ragas_online_eval", OperationLog.target_id == record.id)
        .first()
    )
    assert log is not None
    assert "status=failed" in (log.detail or "")


def test_run_ragas_online_eval_skips_empty_answer_or_contexts(db_session, regular_user):
    before = db_session.query(KbSearchEval).count()

    assert (
        run_ragas_online_eval(
            db_session,
            user_id=regular_user.id,
            workspace_id=1,
            query="问题",
            answer="",
            contexts=["上下文"],
            context_file_ids=[],
            context_chunk_ids=[],
            evaluator=lambda *_args, **_kwargs: _result(),
        )
        is None
    )
    assert (
        run_ragas_online_eval(
            db_session,
            user_id=regular_user.id,
            workspace_id=1,
            query="问题",
            answer="回答",
            contexts=[],
            context_file_ids=[],
            context_chunk_ids=[],
            evaluator=lambda *_args, **_kwargs: _result(),
        )
        is None
    )

    assert db_session.query(KbSearchEval).count() == before


def test_admin_kb_search_eval_routes_require_admin(client, jwt_token):
    headers = {"Authorization": f"Bearer {jwt_token}"}

    resp = client.get("/api/admin/kb-search-eval/summary", headers=headers)

    assert resp.status_code == status.HTTP_403_FORBIDDEN


def test_admin_kb_search_eval_summary_trend_and_samples(
    client, admin_jwt_token, db_session, regular_user
):
    now = naive_db_now()
    rows = [
        KbSearchEval(
            user_id=regular_user.id,
            workspace_id=1,
            query_hash="q1",
            query_preview="preview q1",
            answer_hash="a1",
            answer_preview="preview a1",
            context_count=2,
            context_file_ids_json=[1],
            context_chunk_ids_json=[101],
            faithfulness_score=0.9,
            context_precision_score=0.8,
            metric_provider="ragas",
            metric_version="ragas-test",
            metric_variant="faithfulness+context_precision_without_reference",
            llm_provider="openai_compatible",
            llm_model="test-model",
            status="succeeded",
            duration_ms=100,
            created_at=now - timedelta(days=1),
            evaluated_at=now - timedelta(days=1),
        ),
        KbSearchEval(
            user_id=regular_user.id,
            workspace_id=1,
            query_hash="q2",
            query_preview="preview q2",
            answer_hash="a2",
            answer_preview="preview a2",
            context_count=1,
            context_file_ids_json=[2],
            context_chunk_ids_json=[201],
            faithfulness_score=0.4,
            context_precision_score=0.5,
            metric_provider="ragas",
            metric_version="ragas-test",
            metric_variant="faithfulness+context_precision_without_reference",
            llm_provider="openai_compatible",
            llm_model="test-model",
            status="succeeded",
            duration_ms=120,
            created_at=now,
            evaluated_at=now,
        ),
        KbSearchEval(
            user_id=regular_user.id,
            workspace_id=1,
            query_hash="q3",
            query_preview="preview q3",
            answer_hash="a3",
            answer_preview="preview a3",
            context_count=1,
            context_file_ids_json=[],
            context_chunk_ids_json=[],
            metric_provider="ragas",
            metric_version="ragas-test",
            metric_variant="faithfulness+context_precision_without_reference",
            llm_provider="openai_compatible",
            llm_model="test-model",
            status="failed",
            error_code="RuntimeError",
            error_message="boom",
            duration_ms=20,
            created_at=now,
            evaluated_at=now,
        ),
    ]
    db_session.add_all(rows)
    db_session.commit()

    headers = {"Authorization": f"Bearer {admin_jwt_token}"}
    summary = client.get("/api/admin/kb-search-eval/summary", headers=headers).json()
    assert summary["total_count"] == 3
    assert summary["succeeded_count"] == 2
    assert summary["failed_count"] == 1
    assert summary["failure_rate"] == 1 / 3
    assert summary["avg_faithfulness"] == 0.65
    assert summary["avg_context_precision"] == 0.65

    trend = client.get(
        "/api/admin/kb-search-eval/trend",
        headers=headers,
        params={"granularity": "day", "days": 7},
    ).json()
    assert trend["granularity"] == "day"
    assert trend["points"]
    assert {"bucket", "avg_faithfulness", "avg_context_precision", "sample_count", "failure_rate", "pending_count", "running_count", "failed_count", "skipped_count", "failure_stage_counts"} <= set(
        trend["points"][0]
    )
    assert sum(point["failed_count"] for point in trend["points"]) == 1
    assert sum(
        point["failure_stage_counts"].get("unknown", 0) for point in trend["points"]
    ) == 1

    samples = client.get(
        "/api/admin/kb-search-eval/samples",
        headers=headers,
        params={"low_score_threshold": 0.7, "status_filter": "succeeded"},
    ).json()
    assert samples["total"] == 1
    assert samples["items"][0]["query_preview"] == "preview q2"
    assert "query" not in samples["items"][0]
    assert "answer" not in samples["items"][0]


def test_query_eval_trend_uses_postgresql_date_trunc_without_timescale(db_session, regular_user):
    now = naive_db_now()
    db_session.add(
        KbSearchEval(
            user_id=regular_user.id,
            workspace_id=1,
            query_hash="q",
            query_preview="q",
            answer_hash="a",
            answer_preview="a",
            context_count=1,
            context_file_ids_json=[],
            context_chunk_ids_json=[],
            faithfulness_score=0.75,
            context_precision_score=0.5,
            metric_provider="ragas",
            metric_version="ragas-test",
            metric_variant="faithfulness+context_precision_without_reference",
            llm_provider="openai_compatible",
            llm_model="test-model",
            status="succeeded",
            created_at=now,
            evaluated_at=now,
        )
    )
    db_session.commit()

    points = query_eval_trend(db_session, days=7, granularity="day")

    assert points
    assert points[-1]["avg_faithfulness"] == 0.75


def test_requirements_declare_ragas_runtime_dependencies():
    requirements = (Path(__file__).resolve().parents[1] / "requirements.txt").read_text()

    assert "ragas>=" in requirements
    assert "langchain-openai>=" in requirements
    assert "langchain-core>=" in requirements


def test_ragas_metric_dependencies_are_importable():
    import pytest

    pytest.importorskip("ragas", reason="RAGAS is an optional online-evaluation dependency")
    from ragas import SingleTurnSample
    from ragas.metrics import Faithfulness, LLMContextPrecisionWithoutReference
    from ragas.llms import LangchainLLMWrapper
    from langchain_openai import ChatOpenAI

    assert SingleTurnSample is not None
    assert Faithfulness is not None
    assert LLMContextPrecisionWithoutReference is not None
    assert LangchainLLMWrapper is not None
    assert ChatOpenAI is not None


def test_score_with_ragas_reports_unconfigured_llm_before_import_skip(db_session):
    update_settings(
        db_session,
        {
            KEY_KB_POST_LLM_PROVIDER: "openai_compatible",
            KEY_KB_POST_LLM_BASE_URL: "https://llm.example.com/v1",
            KEY_KB_POST_LLM_MODEL: "deepseek-chat",
        },
    )

    result = _score_with_ragas(db_session, "问题", "回答", ["上下文"], 1.0)

    assert result.status == "skipped"
    assert result.metric_version.startswith("ragas ")
    assert result.metric_variant == "ragas_llm_unconfigured"


def test_summary_includes_skipped_count(client, admin_jwt_token, db_session, regular_user):
    db_session.add(
        KbSearchEval(
            user_id=regular_user.id,
            workspace_id=1,
            query_hash="qs",
            query_preview="skipped query",
            answer_hash="as",
            answer_preview="skipped answer",
            context_count=1,
            context_file_ids_json=[],
            context_chunk_ids_json=[],
            metric_provider="ragas",
            metric_version="ragas-test",
            metric_variant="ragas_llm_unconfigured",
            llm_provider="openai_compatible",
            llm_model="",
            status="skipped",
        )
    )
    db_session.commit()

    resp = client.get(
        "/api/admin/kb-search-eval/summary",
        headers={"Authorization": f"Bearer {admin_jwt_token}"},
    )

    assert resp.status_code == status.HTTP_200_OK
    assert resp.json()["skipped_count"] == 1


def test_completed_rag_answer_endpoint_enqueues_eval(
    client, active_api_key, db_session, regular_user, monkeypatch
):
    calls: list[dict] = []

    def fake_enqueue(db, **kwargs):
        calls.append(kwargs)

    monkeypatch.setattr("routers.knowledge_base.enqueue_ragas_online_eval", fake_enqueue)

    resp = client.post(
        "/api/knowledge-base/ragas-eval",
        headers={"Authorization": f"Bearer {active_api_key._plaintext}"},
        json={
            "query": "什么是 RAG？",
            "answer": "RAG 是检索增强生成。",
            "contexts": ["RAG 是 retrieval augmented generation。"],
            "context_file_ids": [],
            "context_chunk_ids": [],
            "agent_run_id": "run-1",
            "search_trace_id": "trace-1",
        },
    )

    assert resp.status_code == status.HTTP_202_ACCEPTED
    assert resp.json()["accepted"] is True
    assert calls
    assert calls[0]["user_id"] == regular_user.id
    assert calls[0]["query"] == "什么是 RAG？"
    assert calls[0]["answer"] == "RAG 是检索增强生成。"
    assert calls[0]["contexts"] == ["RAG 是 retrieval augmented generation。"]


def test_ragas_eval_rejects_web_jwt(client, jwt_token):
    """普通 Web JWT 调用 ragas-eval 应被拒绝（仅接受 API Key）。"""
    resp = client.post(
        "/api/knowledge-base/ragas-eval",
        headers={"Authorization": f"Bearer {jwt_token}"},
        json={
            "query": "问题",
            "answer": "回答",
            "contexts": ["上下文"],
        },
    )
    assert resp.status_code == status.HTTP_401_UNAUTHORIZED


def test_ragas_eval_rejects_oversize_single_context(client, active_api_key):
    """单条 context 超过单项长度上限应返回 422。"""
    from schemas.kb import KbRagasEvalSubmitRequest

    oversize = "x" * (KbRagasEvalSubmitRequest.MAX_CONTEXT_ITEM_CHARS + 1)
    resp = client.post(
        "/api/knowledge-base/ragas-eval",
        headers={"Authorization": f"Bearer {active_api_key._plaintext}"},
        json={
            "query": "问题",
            "answer": "回答",
            "contexts": [oversize],
        },
    )
    assert resp.status_code == status.HTTP_422_UNPROCESSABLE_ENTITY


def test_ragas_eval_rejects_oversize_total_contexts(client, active_api_key):
    """contexts 总字符数超过上限应返回 422。"""
    from schemas.kb import KbRagasEvalSubmitRequest

    per_item = KbRagasEvalSubmitRequest.MAX_CONTEXT_ITEM_CHARS
    count = (KbRagasEvalSubmitRequest.MAX_CONTEXT_TOTAL_CHARS // per_item) + 1
    contexts = ["x" * per_item for _ in range(count)]
    total = sum(len(c) for c in contexts)
    assert total > KbRagasEvalSubmitRequest.MAX_CONTEXT_TOTAL_CHARS
    resp = client.post(
        "/api/knowledge-base/ragas-eval",
        headers={"Authorization": f"Bearer {active_api_key._plaintext}"},
        json={
            "query": "问题",
            "answer": "回答",
            "contexts": contexts,
        },
    )
    assert resp.status_code == status.HTTP_422_UNPROCESSABLE_ENTITY


def test_ragas_eval_drops_inaccessible_file_and_chunk_ids(
    client, active_api_key, db_session, regular_user, monkeypatch
):
    """越权 / 不存在的 file_id 与 chunk_id 应被过滤为空。"""
    calls: list[dict] = []

    def fake_enqueue(db, **kwargs):
        calls.append(kwargs)

    monkeypatch.setattr("routers.knowledge_base.enqueue_ragas_online_eval", fake_enqueue)

    resp = client.post(
        "/api/knowledge-base/ragas-eval",
        headers={"Authorization": f"Bearer {active_api_key._plaintext}"},
        json={
            "query": "问题",
            "answer": "回答",
            "contexts": ["上下文"],
            "context_file_ids": [999999, 888888],
            "context_chunk_ids": [777777],
        },
    )

    assert resp.status_code == status.HTTP_202_ACCEPTED
    assert calls
    assert calls[0]["context_file_ids"] == []
    assert calls[0]["context_chunk_ids"] == []


def test_ragas_eval_context_provenance_never_pairs_chunk_with_other_file():
    from types import SimpleNamespace

    from routers.knowledge_base import _build_ragas_eval_contexts

    contexts = _build_ragas_eval_contexts(
        [
            SimpleNamespace(text="from file 10", file_id=10, chunk_id=200, rank=0),
            SimpleNamespace(text="from chunk only", file_id=None, chunk_id=200, rank=1),
        ],
        ["from file 10", "from chunk only"],
        valid_file_ids={10, 20},
        chunk_file_ids={100: 10, 200: 20},
    )

    # The first item cannot claim chunk 200 as evidence for file 10; the
    # second derives its file from the verified chunk instead.
    assert [(item.file_id, item.chunk_id) for item in contexts] == [(10, None), (20, 200)]


def test_ragas_eval_submit_passes_sample_type(client, active_api_key, monkeypatch):
    """sample_type 透传到 enqueue_ragas_online_eval。"""
    calls: list[dict] = []

    def fake_enqueue(db, **kwargs):
        calls.append(kwargs)

    monkeypatch.setattr("routers.knowledge_base.enqueue_ragas_online_eval", fake_enqueue)

    resp = client.post(
        "/api/knowledge-base/ragas-eval",
        headers={"Authorization": f"Bearer {active_api_key._plaintext}"},
        json={
            "query": "问题",
            "answer": "资料库未找到可核实依据。",
            "contexts": ["上下文"],
            "sample_type": "recall_no_hit",
        },
    )

    assert resp.status_code == status.HTTP_202_ACCEPTED
    assert calls[0]["sample_type"] == "recall_no_hit"


def test_ragas_eval_submit_defaults_sample_type_to_answer(client, active_api_key, monkeypatch):
    """未传 sample_type 时透传 None，由后端归一化为 answer。"""
    calls: list[dict] = []

    def fake_enqueue(db, **kwargs):
        calls.append(kwargs)

    monkeypatch.setattr("routers.knowledge_base.enqueue_ragas_online_eval", fake_enqueue)

    resp = client.post(
        "/api/knowledge-base/ragas-eval",
        headers={"Authorization": f"Bearer {active_api_key._plaintext}"},
        json={
            "query": "问题",
            "answer": "回答",
            "contexts": ["上下文"],
        },
    )

    assert resp.status_code == status.HTTP_202_ACCEPTED
    # schema 层把 None 归一化为 answer
    assert calls[0]["sample_type"] == "answer"


def test_ragas_eval_submit_builds_context_provenance_items(client, active_api_key, monkeypatch):
    """评测入口必须按每条 context 保留来源，而不是猜测平行数组对齐。"""
    calls: list[dict] = []

    def fake_enqueue(db, **kwargs):
        calls.append(kwargs)

    monkeypatch.setattr("routers.knowledge_base.enqueue_ragas_online_eval", fake_enqueue)

    resp = client.post(
        "/api/knowledge-base/ragas-eval",
        headers={"Authorization": f"Bearer {active_api_key._plaintext}"},
        json={
            "query": "问题",
            "answer": "回答",
            "contexts": ["上下文一", "上下文二"],
            "context_items": [
                {"text": "上下文一", "file_id": 10, "chunk_id": 100, "rank": 0},
                {"text": "上下文二", "file_id": None, "chunk_id": None, "rank": 1},
            ],
        },
    )

    assert resp.status_code == status.HTTP_202_ACCEPTED
    assert [(item.text, item.file_id, item.chunk_id, item.rank) for item in calls[0]["eval_contexts"]] == [
        ("上下文一", None, None, 0),
        ("上下文二", None, None, 1),
    ]


def test_ragas_eval_rejects_unknown_sample_type(client, active_api_key):
    """未知 sample_type 应返回 422。"""
    resp = client.post(
        "/api/knowledge-base/ragas-eval",
        headers={"Authorization": f"Bearer {active_api_key._plaintext}"},
        json={
            "query": "问题",
            "answer": "回答",
            "contexts": ["上下文"],
            "sample_type": "bogus",
        },
    )
    assert resp.status_code == status.HTTP_422_UNPROCESSABLE_ENTITY


def test_enqueue_ragas_online_eval_noop_when_disabled(monkeypatch):
    """KB_RAGAS_ONLINE_EVAL_ENABLED=false 时不创建任何 durable job。"""
    from services import kb_eval_service
    from services.kb_eval_service import enqueue_ragas_online_eval

    monkeypatch.setattr(kb_eval_service, "is_ragas_online_eval_enabled", lambda db: False)
    created: list[dict] = []
    monkeypatch.setattr(
        kb_eval_service,
        "create_ragas_eval_job",
        lambda db, **kwargs: created.append(kwargs),
    )

    from unittest.mock import MagicMock
    db_mock = MagicMock()
    enqueue_ragas_online_eval(
        db_mock,
        user_id=1,
        workspace_id=1,
        query="问题",
        answer="回答",
        contexts=["上下文"],
    )
    assert created == []


def test_enqueue_ragas_online_eval_creates_durable_pending_job(monkeypatch):
    """开启时只创建 pending eval/job，Web 进程不得提交评分线程。"""
    from services import kb_eval_service
    from services.kb_eval_service import enqueue_ragas_online_eval
    from services.kb_ragas_eval_queue_service import RagasEvalContext

    monkeypatch.setattr(kb_eval_service, "is_ragas_online_eval_enabled", lambda db: True)
    monkeypatch.setattr(kb_eval_service, "ragas_online_eval_sample_rate", lambda db: 1.0)
    created: list[dict] = []
    monkeypatch.setattr(
        kb_eval_service,
        "create_ragas_eval_job",
        lambda db, **kwargs: created.append(kwargs),
        raising=False,
    )

    from unittest.mock import MagicMock
    db_mock = MagicMock()
    enqueue_ragas_online_eval(
        db_mock,
        user_id=1,
        workspace_id=1,
        query="问题",
        answer="回答",
        contexts=["上下文"],
        eval_contexts=[RagasEvalContext(text="上下文", file_id=1, chunk_id=2, rank=0)],
    )
    assert len(created) == 1
    assert created[0]["contexts"] == [
        RagasEvalContext(text="上下文", file_id=1, chunk_id=2, rank=0)
    ]
    assert not hasattr(kb_eval_service, "_ragas_eval_pool")


def test_execute_ragas_eval_job_does_not_call_llm_after_deadline(monkeypatch):
    """总 deadline 已耗尽时，不得启动 Faithfulness 的 HTTP 调用。"""
    from services import kb_eval_service

    job = type(
        "Job",
        (),
        {
            "id": 7,
            "worker_id": "worker-a",
            "lease_generation": 1,
            "payload_json": {"query": "q", "answer": "a", "contexts": [{"text": "c"}]},
        },
    )()
    finished: list[dict] = []
    monkeypatch.setattr(
        kb_eval_service,
        "get_ragas_llm_runtime_config",
        lambda db, fresh: type(
            "Cfg",
            (),
            {
                "provider": "ollama",
                "base_url": "http://ollama",
                "model": "model",
                "api_key": None,
                "timeout_seconds": 90,
                "is_configured": True,
                "unconfigured_reason": None,
            },
        )(),
        raising=False,
    )
    monkeypatch.setattr(
        kb_eval_service,
        "effective_ragas_metric_timeout",
        lambda db, job, timeout: 0.0,
        raising=False,
    )
    monkeypatch.setattr(
        kb_eval_service,
        "finish_ragas_eval_job",
        lambda db, **kwargs: finished.append(kwargs) or True,
        raising=False,
    )

    from unittest.mock import MagicMock

    kb_eval_service.execute_ragas_eval_job(MagicMock(), job)

    assert len(finished) == 1
    assert finished[0] == {
        "job_id": 7,
        "worker_id": "worker-a",
        "lease_generation": 1,
        "status": "failed",
        "error_code": "TimeoutError",
        "error_message": "RAGAS total evaluation deadline exhausted",
        "failure_stage": "faithfulness",
        "metric_version": kb_eval_service._ragas_version_label(),
        "metric_variant": "faithfulness+context_precision_without_reference",
    }


def test_ragas_eval_system_settings_keys_known():
    """新增的 3 个 RAGAS key 已注册到 KNOWN_KEYS 和 DEFAULTS。"""
    from services.system_setting_service import (
        KEY_KB_RAGAS_ONLINE_EVAL_ENABLED,
        KEY_KB_RAGAS_ONLINE_EVAL_SAMPLE_RATE,
        KEY_KB_RAGAS_ONLINE_EVAL_TIMEOUT_SECONDS,
        KNOWN_KEYS,
        DEFAULTS,
    )
    assert KEY_KB_RAGAS_ONLINE_EVAL_ENABLED in KNOWN_KEYS
    assert KEY_KB_RAGAS_ONLINE_EVAL_SAMPLE_RATE in KNOWN_KEYS
    assert KEY_KB_RAGAS_ONLINE_EVAL_TIMEOUT_SECONDS in KNOWN_KEYS
    assert DEFAULTS[KEY_KB_RAGAS_ONLINE_EVAL_ENABLED] == "false"
    assert DEFAULTS[KEY_KB_RAGAS_ONLINE_EVAL_SAMPLE_RATE] == "1.0"
    assert DEFAULTS[KEY_KB_RAGAS_ONLINE_EVAL_TIMEOUT_SECONDS] == "600"




def test_ragas_eval_getter_clamps_values(db_session):
    """RAGAS eval getter 函数对越界/非法值正确 clamp。"""
    from services.kb_eval_service import (
        get_ragas_eval_sample_rate,
        get_ragas_eval_timeout_seconds,
        invalidate_ragas_eval_runtime_cache,
    )
    from services.system_setting_service import update_settings

    # 越界 sample_rate → clamp to [0, 1]
    update_settings(db_session, {"kb_ragas_online_eval_sample_rate": "5.0"})
    invalidate_ragas_eval_runtime_cache()
    rate = get_ragas_eval_sample_rate(db_session)
    assert 0.0 <= rate <= 1.0, f"sample rate {rate} not clamped"

    # timeout 上限放宽到 3000 秒
    update_settings(db_session, {"kb_ragas_online_eval_timeout_seconds": "3000"})
    invalidate_ragas_eval_runtime_cache()
    timeout = get_ragas_eval_timeout_seconds(db_session)
    assert timeout == 3000.0

    # 越界 timeout → clamp to [1, 3000]
    update_settings(db_session, {"kb_ragas_online_eval_timeout_seconds": "9999"})
    invalidate_ragas_eval_runtime_cache()
    timeout_high = get_ragas_eval_timeout_seconds(db_session)
    assert timeout_high == 3000.0

    # 非法 timeout 值 → fallback to default
    update_settings(db_session, {"kb_ragas_online_eval_timeout_seconds": "abc"})
    invalidate_ragas_eval_runtime_cache()
    timeout2 = get_ragas_eval_timeout_seconds(db_session)
    assert timeout2 == 600.0
