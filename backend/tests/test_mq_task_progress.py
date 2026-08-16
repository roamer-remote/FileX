# Copyright (c) 2026 徐泽宇
"""MQ task progress registry and notify consumer (FR-122-003 B1)."""

from __future__ import annotations

import json
from unittest.mock import MagicMock, patch

from messaging import kb_index_notify
from messaging.mq_task_progress import (
    clear_progress,
    get_progress,
    merge_task_progress,
    merge_task_progress_list,
    prune_stale_progress,
    set_progress,
)
from models.file import File as FileModel
from models.kb_post_job import KbPostJob
from services.kb_post_service import JOB_QUEUED
from services.rabbitmq_status_service import (
    attach_active_task_models,
    list_kb_post_queued_jobs,
    mq_status_to_user_payload,
)


def test_mq_task_progress_merge_by_file_id():
    clear_progress(42)
    set_progress(
        42,
        kind="kb_index",
        progress_stage="向量嵌入",
        progress_pct=40,
        progress_detail="4/10",
    )
    task = {"kind": "kb_index", "file_id": 42, "filename": "a.pdf", "username": "u1"}
    merged = merge_task_progress(task)
    assert merged["progress_stage"] == "向量嵌入"
    assert merged["progress_pct"] == 40
    assert merged["progress_detail"] == "4/10"
    clear_progress(42)


def test_mq_task_progress_kind_mismatch_skips_merge():
    clear_progress(7)


def test_active_tasks_include_model_for_post_and_cpu_extract_paths(db_session):
    from types import SimpleNamespace

    tasks = [
        {"kind": "kb_post", "file_id": 1, "progress_stage": "RAPTOR"},
        {"kind": "kb_index", "file_id": 2, "progress_stage": "向量嵌入"},
        {"kind": "kb_mineru", "file_id": 3},
    ]
    with patch(
        "services.kb_post_llm_service.get_kb_post_llm_runtime_config",
        return_value=SimpleNamespace(model="deepseek-v4-flash:0731-cloud"),
    ), patch(
        "services.ollama_config_service.get_ollama_runtime_config",
        return_value=SimpleNamespace(embed_model="bge-m3"),
    ):
        enriched = attach_active_task_models(db_session, tasks)

    assert [task["model"] for task in enriched] == [
        "deepseek-v4-flash:0731-cloud",
        "bge-m3",
        "MinerU",
    ]
    set_progress(7, kind="kb_post", progress_stage="RAPTOR", progress_pct=10)
    task = {"kind": "kb_index", "file_id": 7, "filename": "b.pdf"}
    assert merge_task_progress(task) == task
    clear_progress(7)


def test_mq_status_user_payload_includes_progress():
    status = {
        "connected": True,
        "error": None,
        "updated_at": "2026-01-01T00:00:00+08:00",
        "broker_display": "amqp://x",
        "queues": [
            {
                "name": "kb.index.main",
                "label": "index_main",
                "online": True,
                "message_count": 0,
                "consumer_count": 1,
                "consumer_busy": True,
                "jobs_pending": 0,
                "backlog_total": 1,
            }
        ],
        "active_tasks": [
            {
                "kind": "kb_index",
                "file_id": 99,
                "filename": "c.pdf",
                "progress_stage": "向量嵌入",
                "progress_pct": 55,
                "progress_detail": "11/20",
            }
        ],
        "system_resources": {
            "cpu_percent": 42.5,
            "gpu": {
                "available": True,
                "name": "NVIDIA RTX 4090",
                "util_percent": 86.0,
                "memory_used_mb": 18841,
                "memory_total_mb": 24564,
            },
        },
    }
    user = mq_status_to_user_payload(status)
    task = user["active_tasks"][0]
    assert task["progress_stage"] == "向量嵌入"
    assert task["progress_pct"] == 55
    assert task["progress_detail"] == "11/20"
    assert "username" not in task
    assert "system_resources" not in user


@patch("messaging.mq_status_watcher.request_refresh")
@patch("messaging.kb_index_notify.kb_index_ws_manager")
@patch("messaging.kb_index_notify.kb_ws_notify_replay_buffer")
def test_progress_notify_updates_registry_without_ws(_mock_buffer, _mock_ws, _mock_refresh):
    ch = MagicMock()
    method = MagicMock(delivery_tag=1)
    body = json.dumps(
        {
            "type": "kb_index_progress",
            "user_id": 1,
            "file_id": 100,
            "kind": "kb_index",
            "progress_stage": "向量嵌入",
            "progress_pct": 20,
            "progress_detail": "2/10",
        }
    ).encode()
    kb_index_notify._on_notify(ch, method, None, body)
    merged = merge_task_progress_list(
        [{"kind": "kb_index", "file_id": 100, "filename": "x.pdf"}]
    )
    assert merged[0]["progress_pct"] == 20
    _mock_ws.broadcast_sync.assert_not_called()
    _mock_refresh.assert_called()
    clear_progress(100)


def test_admin_list_mq_post_queued_jobs(client, admin_jwt_token, db_session, regular_user):
    f = FileModel(
        filename="post-q.bin",
        original_name="post-q.pdf",
        file_path="/tmp/post-q.bin",
        file_size=1,
        mime_type="application/pdf",
        user_id=regular_user.id,
    )
    db_session.add(f)
    db_session.flush()
    db_session.add(KbPostJob(user_id=regular_user.id, file_id=f.id, status=JOB_QUEUED))
    db_session.commit()

    res = client.get("/api/admin/mq/post-queued-jobs", headers={"Authorization": f"Bearer {admin_jwt_token}"})
    assert res.status_code == 200
    data = res.json()
    ours = [x for x in data["items"] if x["filename"] == "post-q.bin"]
    assert len(ours) == 1
    assert ours[0]["username"] == regular_user.username


def test_list_kb_post_queued_jobs_owner_scope(db_session, regular_user):
    f = FileModel(
        filename="post-scope.bin",
        original_name="post-scope.pdf",
        file_path="/tmp/post-scope.bin",
        file_size=1,
        mime_type="application/pdf",
        user_id=regular_user.id,
    )
    db_session.add(f)
    db_session.flush()
    db_session.add(KbPostJob(user_id=regular_user.id, file_id=f.id, status=JOB_QUEUED))
    db_session.commit()

    payload = list_kb_post_queued_jobs(db_session, owner_user_id=int(regular_user.id))
    assert payload["total"] >= 1
    assert all("username" not in item for item in payload["items"])


def test_prune_stale_progress_removes_orphan_registry():
    clear_progress(999)
    set_progress(999, kind="kb_index", progress_stage="向量嵌入", progress_pct=10)
    prune_stale_progress(set())
    assert get_progress(999) is None


def test_mq_progress_notify_throttle_interval():
    from messaging import mq_progress_notify as mp

    mp._throttle_state.clear()
    with patch.object(mp.time, "monotonic", side_effect=[0.0, 0.4]):
        assert mp._should_publish(1, 10, "向量嵌入") is True
        assert mp._should_publish(1, 12, "向量嵌入") is False
    mp._throttle_state.clear()


def test_mq_progress_notify_throttle_pct_delta():
    from messaging import mq_progress_notify as mp

    mp._throttle_state.clear()
    with patch.object(mp.time, "monotonic", side_effect=[0.0, 0.2]):
        assert mp._should_publish(2, 10, "向量嵌入") is True
        assert mp._should_publish(2, 16, "向量嵌入") is True
    mp._throttle_state.clear()


def test_mq_progress_notify_stage_change_immediate():
    from messaging import mq_progress_notify as mp

    mp._throttle_state.clear()
    with patch.object(mp.time, "monotonic", side_effect=[0.0, 0.1]):
        assert mp._should_publish(3, 10, "向量嵌入") is True
        assert mp._should_publish(3, 10, "写入向量") is True
    mp._throttle_state.clear()


@patch("messaging.kb_index_publisher.publish_kb_index_progress_notify")
def test_maybe_publish_index_progress_respects_throttle(mock_publish):
    from messaging import mq_progress_notify as mp

    mp._throttle_state.clear()
    with patch.object(mp.time, "monotonic", side_effect=[0.0, 0.2, 1.2]):
        mp.maybe_publish_index_progress(
            user_id=1,
            file_id=4,
            progress_stage="向量嵌入",
            progress_pct=10,
        )
        mp.maybe_publish_index_progress(
            user_id=1,
            file_id=4,
            progress_stage="向量嵌入",
            progress_pct=11,
        )
        mp.maybe_publish_index_progress(
            user_id=1,
            file_id=4,
            progress_stage="向量嵌入",
            progress_pct=12,
        )
    assert mock_publish.call_count == 2
    mp._throttle_state.clear()
