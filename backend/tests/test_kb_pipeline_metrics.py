# Copyright (c) 2026 徐泽宇
"""086 Phase 2: KB pipeline metrics API tests."""

from __future__ import annotations

from datetime import datetime, timedelta
from unittest.mock import patch

from fastapi import status

from models.operation_log import OperationLog
from services.kb_pipeline_log_service import (
    ACTION_KB_EXTRACT_DONE,
    ACTION_KB_EXTRACT_ERROR,
    ACTION_KB_INDEX_DONE,
    ACTION_KB_INDEX_ERROR,
    format_kb_pipeline_detail,
)
from services.kb_pipeline_metrics_service import reset_pipeline_metrics_cache
from utils.timezone import naive_db_now


def test_admin_pipeline_metrics_requires_admin(client, jwt_token):
    reset_pipeline_metrics_cache()
    resp = client.get(
        "/api/admin/kb-pipeline/metrics",
        headers={"Authorization": f"Bearer {jwt_token}"},
    )
    assert resp.status_code == status.HTTP_403_FORBIDDEN


@patch("services.kb_pipeline_metrics_service.get_mq_status")
def test_admin_pipeline_metrics_aggregates_logs_and_queues(
    mock_mq,
    client,
    admin_jwt_token,
    db_session,
    regular_user,
):
    reset_pipeline_metrics_cache()
    mock_mq.return_value = {
        "queues": [
            {"name": "kb.extract", "label": "extract_main", "message_count": 3},
            {"name": "kb.index", "label": "index_main", "message_count": 0},
            {"name": "kb.extract.dlq", "label": "extract_dlq", "message_count": 1},
            {"name": "kb.index.dlq", "label": "index_dlq", "message_count": 0},
        ],
    }

    now = naive_db_now()
    rows = [
        OperationLog(
            user_id=regular_user.id,
            action=ACTION_KB_EXTRACT_DONE,
            target_type="file",
            target_id=101,
            detail=format_kb_pipeline_detail(provider="mineru", provider_ms=1200, persist_ms=80),
            created_at=now - timedelta(minutes=10),
        ),
        OperationLog(
            user_id=regular_user.id,
            action=ACTION_KB_EXTRACT_ERROR,
            target_type="file",
            target_id=102,
            detail=format_kb_pipeline_detail(provider="mineru", reason="boom"),
            created_at=now - timedelta(minutes=5),
        ),
        OperationLog(
            user_id=regular_user.id,
            action=ACTION_KB_INDEX_DONE,
            target_type="file",
            target_id=101,
            detail=format_kb_pipeline_detail(embed_ms=900, persist_ms=40, post_index_ms=15),
            created_at=now - timedelta(minutes=2),
        ),
        OperationLog(
            user_id=regular_user.id,
            action=ACTION_KB_INDEX_ERROR,
            target_type="file",
            target_id=103,
            detail=format_kb_pipeline_detail(provider="legacy", reason="index_fail"),
            created_at=now - timedelta(minutes=1),
        ),
    ]
    db_session.add_all(rows)
    db_session.commit()

    resp = client.get(
        "/api/admin/kb-pipeline/metrics?window=24h",
        headers={"Authorization": f"Bearer {admin_jwt_token}"},
    )
    assert resp.status_code == status.HTTP_200_OK
    data = resp.json()
    assert data["window"] == "24h"
    assert data["warnings"]
    assert "dlq_nonzero" in data["warnings"]

    kpi_map = {item["key"]: item for item in data["kpis"]}
    assert kpi_map["extract_done_24h"]["value"] == 1
    assert kpi_map["index_done_24h"]["value"] == 1
    assert kpi_map["extract_failures_24h"]["value"] == 1
    assert kpi_map["index_failures_24h"]["value"] == 1
    assert kpi_map["dlq_total"]["value"] == 1
    assert kpi_map["extract_queue_depth"]["value"] == 3

    mineru = next(item for item in data["provider_failures"] if item["provider"] == "mineru")
    assert mineru["failure_count"] == 1
    assert mineru["success_count"] == 1

    assert data["avg_stage_ms"]["extract_provider_ms"] == 1200.0
    assert data["avg_stage_ms"]["index_embed_ms"] == 900.0
    assert len(data["recent_events"]) >= 4
    assert data["recent_events"][0]["action"] in {
        ACTION_KB_INDEX_ERROR,
        ACTION_KB_INDEX_DONE,
        ACTION_KB_EXTRACT_ERROR,
        ACTION_KB_EXTRACT_DONE,
    }


@patch("services.kb_pipeline_metrics_service.get_mq_status")
def test_admin_pipeline_metrics_ocr_telemetry(
    mock_mq,
    client,
    admin_jwt_token,
    db_session,
    regular_user,
):
    reset_pipeline_metrics_cache()
    mock_mq.return_value = {"queues": []}
    now = naive_db_now()
    db_session.add_all(
        [
            OperationLog(
                user_id=regular_user.id,
                action=ACTION_KB_EXTRACT_DONE,
                target_type="file",
                target_id=201,
                detail=format_kb_pipeline_detail(
                    provider="legacy",
                    ocr_engine="rapidocr",
                    ocr_quality="low",
                    ocr_review_recommended=True,
                ),
                created_at=now - timedelta(minutes=3),
            ),
            OperationLog(
                user_id=regular_user.id,
                action=ACTION_KB_EXTRACT_DONE,
                target_type="file",
                target_id=202,
                detail=format_kb_pipeline_detail(
                    provider="mineru",
                    ocr_engine="mineru-paddle",
                ),
                created_at=now - timedelta(minutes=2),
            ),
        ],
    )
    db_session.commit()

    resp = client.get(
        "/api/admin/kb-pipeline/metrics?window=24h",
        headers={"Authorization": f"Bearer {admin_jwt_token}"},
    )
    assert resp.status_code == status.HTTP_200_OK
    telemetry = {item["key"]: item["count"] for item in resp.json()["ocr_telemetry"]}
    assert telemetry.get("ocr_engine:rapidocr") == 1
    assert telemetry.get("ocr_engine:mineru-paddle") == 1
    assert telemetry.get("ocr_quality:low") == 1
    assert telemetry.get("ocr_review_recommended:true") == 1


@patch("services.kb_pipeline_metrics_service.get_mq_status")
def test_admin_pipeline_metrics_cache_flag(mock_mq, client, admin_jwt_token, db_session):
    reset_pipeline_metrics_cache()
    mock_mq.return_value = {"queues": []}
    headers = {"Authorization": f"Bearer {admin_jwt_token}"}
    first = client.get("/api/admin/kb-pipeline/metrics", headers=headers)
    second = client.get("/api/admin/kb-pipeline/metrics", headers=headers)
    assert first.status_code == status.HTTP_200_OK
    assert second.status_code == status.HTTP_200_OK
    assert first.json()["cached"] is False
    assert second.json()["cached"] is True
