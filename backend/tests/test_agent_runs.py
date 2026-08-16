# Copyright (c) 2026 徐泽宇
"""Tests for 107 agent run trace API."""

from __future__ import annotations

import asyncio
import threading
import time
import uuid
from datetime import datetime, timedelta

import pytest
from fastapi import status

from models.agent_run import AgentRun
from services.agent_run_service import (
    agent_run_retention_days,
    purge_expired_agent_runs,
    sanitize_meta_json,
    stream_hub,
    truncate_question_preview,
)
from tests.conftest import _create_user, _create_api_key


class TestAgentRunHelpers:
    def test_truncate_question_preview(self):
        assert len(truncate_question_preview("a" * 200)) <= 120

    def test_sanitize_meta_strips_forbidden(self):
        out = sanitize_meta_json({"file_id": 1, "query": "secret", "hit_count": 3})
        assert out == {"file_id": 1, "hit_count": 3}
        assert "query" not in (out or {})

    def test_sanitize_meta_keeps_search_trace_summary(self):
        summary = {"hit_count": 2, "vector": {"merged_unique": 10}}
        out = sanitize_meta_json({"search_trace_summary": summary, "query": "secret"})
        assert out == {"search_trace_summary": summary}

    def test_agent_run_retention_days_reads_system_setting(self, db_session, monkeypatch):
        monkeypatch.delenv("AGENT_RUN_RETENTION_DAYS", raising=False)
        from services.system_setting_service import (
            KEY_AGENT_RUN_RETENTION_DAYS,
            update_settings,
        )

        update_settings(db_session, {KEY_AGENT_RUN_RETENTION_DAYS: "45"})
        assert agent_run_retention_days(db_session) == 45


class TestAgentRunAPI:
    def test_create_and_list_with_api_key(self, client, active_api_key, jwt_token):
        resp = client.post(
            "/api/agent-runs",
            headers={"Authorization": f"Bearer {active_api_key._plaintext}"},
            json={"question_preview": "报销上限是多少", "thread_id": "ding:t1"},
        )
        assert resp.status_code == status.HTTP_201_CREATED
        run_id = resp.json()["run_id"]
        assert run_id

        listed = client.get(
            "/api/agent-runs",
            headers={"Authorization": f"Bearer {jwt_token}"},
        )
        assert listed.status_code == status.HTTP_200_OK
        assert listed.json()["total"] >= 1
        assert any(item["id"] == run_id for item in listed.json()["items"])

    def test_other_user_gets_404(self, client, db_session, active_api_key):
        other = _create_user(db_session, "other107")
        other_key = _create_api_key(db_session, other, is_active=True)

        created = client.post(
            "/api/agent-runs",
            headers={"Authorization": f"Bearer {active_api_key._plaintext}"},
            json={"question_preview": "私有问题"},
        )
        run_id = created.json()["run_id"]

        denied = client.get(
            f"/api/agent-runs/{run_id}",
            headers={"Authorization": f"Bearer {other_key._plaintext}"},
        )
        assert denied.status_code == status.HTTP_404_NOT_FOUND

    def test_server_assigns_monotonic_seq(self, client, active_api_key):
        created = client.post(
            "/api/agent-runs",
            headers={"Authorization": f"Bearer {active_api_key._plaintext}"},
            json={"question_preview": "seq test"},
        )
        run_id = created.json()["run_id"]
        cid1 = str(uuid.uuid4())
        cid2 = str(uuid.uuid4())
        batch = client.post(
            f"/api/agent-runs/{run_id}/events",
            headers={"Authorization": f"Bearer {active_api_key._plaintext}"},
            json={
                "events": [
                    {
                        "client_event_id": cid1,
                        "layer": "kb",
                        "node_id": "initial_search",
                        "label": "检索",
                        "phase": "start",
                    },
                    {
                        "client_event_id": cid2,
                        "layer": "kb",
                        "node_id": "initial_search",
                        "label": "检索",
                        "phase": "end",
                        "duration_ms": 10,
                    },
                ]
            },
        )
        assert batch.status_code == status.HTTP_200_OK
        seqs = [row["seq"] for row in batch.json()["assigned"]]
        assert seqs == [1, 2]

    def test_parallel_span_pairing(self, client, active_api_key, jwt_token):
        created = client.post(
            "/api/agent-runs",
            headers={"Authorization": f"Bearer {active_api_key._plaintext}"},
            json={"question_preview": "parallel md"},
        )
        run_id = created.json()["run_id"]
        parent = str(uuid.uuid4())
        span_a = str(uuid.uuid4())
        span_b = str(uuid.uuid4())
        client.post(
            f"/api/agent-runs/{run_id}/events",
            headers={"Authorization": f"Bearer {active_api_key._plaintext}"},
            json={
                "events": [
                    {
                        "client_event_id": parent,
                        "layer": "kb",
                        "node_id": "assess",
                        "label": "评估",
                        "phase": "end",
                    },
                    {
                        "client_event_id": str(uuid.uuid4()),
                        "parent_client_event_id": parent,
                        "task_key": "get_md:file_id=1",
                        "span_id": span_a,
                        "layer": "kb",
                        "node_id": "get_md_worker",
                        "label": "读文档",
                        "phase": "start",
                    },
                    {
                        "client_event_id": str(uuid.uuid4()),
                        "parent_client_event_id": parent,
                        "task_key": "get_md:file_id=2",
                        "span_id": span_b,
                        "layer": "kb",
                        "node_id": "get_md_worker",
                        "label": "读文档",
                        "phase": "start",
                    },
                ]
            },
        )
        detail = client.get(
            f"/api/agent-runs/{run_id}",
            headers={"Authorization": f"Bearer {jwt_token}"},
        )
        workers = [e for e in detail.json()["events"] if e["node_id"] == "get_md_worker"]
        assert len(workers) == 2
        keys = {w["task_key"] for w in workers}
        assert keys == {"get_md:file_id=1", "get_md:file_id=2"}

    def test_meta_forbidden_not_persisted(self, client, active_api_key, jwt_token):
        created = client.post(
            "/api/agent-runs",
            headers={"Authorization": f"Bearer {active_api_key._plaintext}"},
            json={"question_preview": "meta"},
        )
        run_id = created.json()["run_id"]
        client.post(
            f"/api/agent-runs/{run_id}/events",
            headers={"Authorization": f"Bearer {active_api_key._plaintext}"},
            json={
                "events": [
                    {
                        "client_event_id": str(uuid.uuid4()),
                        "layer": "tool",
                        "node_id": "search",
                        "label": "检索",
                        "phase": "end",
                        "meta": {"hit_count": 2, "query": "不应落库"},
                    }
                ]
            },
        )
        detail = client.get(
            f"/api/agent-runs/{run_id}",
            headers={"Authorization": f"Bearer {jwt_token}"},
        )
        meta = detail.json()["events"][0]["meta_json"]
        assert meta.get("hit_count") == 2
        assert "query" not in (meta or {})

    def test_poll_delta(self, client, active_api_key, jwt_token):
        created = client.post(
            "/api/agent-runs",
            headers={"Authorization": f"Bearer {active_api_key._plaintext}"},
            json={"question_preview": "poll"},
        )
        run_id = created.json()["run_id"]
        client.post(
            f"/api/agent-runs/{run_id}/events",
            headers={"Authorization": f"Bearer {active_api_key._plaintext}"},
            json={
                "events": [
                    {
                        "client_event_id": str(uuid.uuid4()),
                        "layer": "router",
                        "node_id": "classify",
                        "label": "理解",
                        "phase": "start",
                    }
                ]
            },
        )
        delta = client.get(
            f"/api/agent-runs/{run_id}/events?since_seq=0",
            headers={"Authorization": f"Bearer {jwt_token}"},
        )
        assert delta.status_code == status.HTTP_200_OK
        assert len(delta.json()["events"]) >= 1

    def test_purge_expired_runs(self, client, db_session, regular_user, jwt_token):
        expired = AgentRun(
            user_id=int(regular_user.id),
            question_preview="过期运行",
            status="completed",
            expires_at=datetime.utcnow() - timedelta(days=1),
        )
        db_session.add(expired)
        db_session.commit()
        run_id = expired.id

        assert purge_expired_agent_runs(db_session) >= 1

        gone = client.get(
            f"/api/agent-runs/{run_id}",
            headers={"Authorization": f"Bearer {jwt_token}"},
        )
        assert gone.status_code == status.HTTP_404_NOT_FOUND

    def test_stream_replays_persisted_events(self, client, active_api_key, jwt_token):
        created = client.post(
            "/api/agent-runs",
            headers={"Authorization": f"Bearer {active_api_key._plaintext}"},
            json={"question_preview": "stream replay"},
        )
        run_id = created.json()["run_id"]
        client.post(
            f"/api/agent-runs/{run_id}/events",
            headers={"Authorization": f"Bearer {active_api_key._plaintext}"},
            json={
                "events": [
                    {
                        "client_event_id": str(uuid.uuid4()),
                        "layer": "router",
                        "node_id": "classify",
                        "label": "理解意图",
                        "phase": "start",
                    }
                ]
            },
        )
        client.patch(
            f"/api/agent-runs/{run_id}",
            headers={"Authorization": f"Bearer {active_api_key._plaintext}"},
            json={"status": "completed"},
        )

        body = ""
        with client.stream(
            "GET",
            f"/api/agent-runs/{run_id}/stream",
            headers={"Authorization": f"Bearer {jwt_token}"},
        ) as resp:
            assert resp.status_code == status.HTTP_200_OK
            for chunk in resp.iter_bytes(chunk_size=4096):
                body += chunk.decode("utf-8", errors="ignore")
                if "classify" in body:
                    break
                if len(body) > 16_000:
                    break

        assert "classify" in body

    def test_batch_delete_runs(self, client, active_api_key, jwt_token):
        created_ids: list[str] = []
        for i in range(2):
            resp = client.post(
                "/api/agent-runs",
                headers={"Authorization": f"Bearer {active_api_key._plaintext}"},
                json={"question_preview": f"delete test {i}"},
            )
            assert resp.status_code == status.HTTP_201_CREATED
            created_ids.append(resp.json()["run_id"])

        deleted = client.post(
            "/api/agent-runs/delete",
            headers={"Authorization": f"Bearer {jwt_token}"},
            json={"ids": created_ids},
        )
        assert deleted.status_code == status.HTTP_200_OK
        assert deleted.json()["deleted"] == 2

        for run_id in created_ids:
            detail = client.get(
                f"/api/agent-runs/{run_id}",
                headers={"Authorization": f"Bearer {jwt_token}"},
            )
            assert detail.status_code == status.HTTP_404_NOT_FOUND

    def test_batch_delete_other_user_runs_ignored(self, client, db_session, active_api_key, jwt_token):
        other = _create_user(db_session, "other107del")
        other_key = _create_api_key(db_session, other, is_active=True)

        mine = client.post(
            "/api/agent-runs",
            headers={"Authorization": f"Bearer {active_api_key._plaintext}"},
            json={"question_preview": "mine"},
        ).json()["run_id"]
        theirs = client.post(
            "/api/agent-runs",
            headers={"Authorization": f"Bearer {other_key._plaintext}"},
            json={"question_preview": "theirs"},
        ).json()["run_id"]

        deleted = client.post(
            "/api/agent-runs/delete",
            headers={"Authorization": f"Bearer {jwt_token}"},
            json={"ids": [mine, theirs]},
        )
        assert deleted.status_code == status.HTTP_200_OK
        assert deleted.json()["deleted"] == 1

        assert (
            client.get(
                f"/api/agent-runs/{mine}",
                headers={"Authorization": f"Bearer {jwt_token}"},
            ).status_code
            == status.HTTP_404_NOT_FOUND
        )
        assert (
            client.get(
                f"/api/agent-runs/{theirs}",
                headers={"Authorization": f"Bearer {other_key._plaintext}"},
            ).status_code
            == status.HTTP_200_OK
        )


    # ── 134 admin agent run records ──

    def test_admin_all_users_sees_all_runs(
        self, client, db_session, active_api_key, admin_jwt_token, jwt_token
    ):
        """Admin with all_users=true returns runs from all users."""
        other = _create_user(db_session, "other134a")
        other_key = _create_api_key(db_session, other, is_active=True)
        # create a run as regular user (via active_api_key = regular_user)
        client.post(
            "/api/agent-runs",
            headers={"Authorization": f"Bearer {active_api_key._plaintext}"},
            json={"question_preview": "问题A"},
        )
        # create a run as other user
        client.post(
            "/api/agent-runs",
            headers={"Authorization": f"Bearer {other_key._plaintext}"},
            json={"question_preview": "问题B"},
        )
        # admin sees all
        resp = client.get(
            "/api/agent-runs?all_users=true",
            headers={"Authorization": f"Bearer {admin_jwt_token}"},
        )
        assert resp.status_code == status.HTTP_200_OK
        data = resp.json()
        assert data["total"] >= 2
        usernames = {item.get("username") for item in data["items"]}
        assert len(usernames) >= 2

    def test_admin_filter_by_user_id(
        self, client, db_session, active_api_key, admin_jwt_token
    ):
        """Admin can filter runs by a specific user_id."""
        other = _create_user(db_session, "other134b")
        other_key = _create_api_key(db_session, other, is_active=True)
        client.post(
            "/api/agent-runs",
            headers={"Authorization": f"Bearer {other_key._plaintext}"},
            json={"question_preview": "其他用户的问题"},
        )
        resp = client.get(
            f"/api/agent-runs?user_id={other.id}",
            headers={"Authorization": f"Bearer {admin_jwt_token}"},
        )
        assert resp.status_code == status.HTTP_200_OK
        data = resp.json()
        assert data["total"] >= 1
        for item in data["items"]:
            assert item.get("username") == other.username

    def test_regular_user_ignores_all_users(
        self, client, db_session, active_api_key, jwt_token
    ):
        """Non-admin passing all_users=true still only sees own runs."""
        other = _create_user(db_session, "other134c")
        other_key = _create_api_key(db_session, other, is_active=True)
        client.post(
            "/api/agent-runs",
            headers={"Authorization": f"Bearer {other_key._plaintext}"},
            json={"question_preview": "不应该看到的问题"},
        )
        client.post(
            "/api/agent-runs",
            headers={"Authorization": f"Bearer {active_api_key._plaintext}"},
            json={"question_preview": "我的问题"},
        )
        resp = client.get(
            "/api/agent-runs?all_users=true",
            headers={"Authorization": f"Bearer {jwt_token}"},
        )
        assert resp.status_code == status.HTTP_200_OK
        data = resp.json()
        assert data["total"] >= 1
        for item in data["items"]:
            assert item.get("username") == "testuser"

    def test_regular_user_ignores_user_id(
        self, client, db_session, active_api_key, jwt_token
    ):
        """Non-admin passing user_id is ignored, only own runs returned."""
        other = _create_user(db_session, "other134d")
        other_key = _create_api_key(db_session, other, is_active=True)
        client.post(
            "/api/agent-runs",
            headers={"Authorization": f"Bearer {other_key._plaintext}"},
            json={"question_preview": "不应该看到的问题2"},
        )
        client.post(
            "/api/agent-runs",
            headers={"Authorization": f"Bearer {active_api_key._plaintext}"},
            json={"question_preview": "我的问题2"},
        )
        resp = client.get(
            f"/api/agent-runs?user_id={other.id}",
            headers={"Authorization": f"Bearer {jwt_token}"},
        )
        assert resp.status_code == status.HTTP_200_OK
        data = resp.json()
        for item in data["items"]:
            assert item.get("username") == "testuser"

    def test_admin_delete_other_user_run(
        self, client, db_session, active_api_key, admin_jwt_token
    ):
        """Admin can delete another user's run."""
        other = _create_user(db_session, "other134del")
        other_key = _create_api_key(db_session, other, is_active=True)
        created = client.post(
            "/api/agent-runs",
            headers={"Authorization": f"Bearer {other_key._plaintext}"},
            json={"question_preview": "待删除的运行记录"},
        )
        run_id = created.json()["run_id"]

        resp = client.post(
            "/api/agent-runs/delete",
            headers={"Authorization": f"Bearer {admin_jwt_token}"},
            json={"ids": [run_id]},
        )
        assert resp.status_code == status.HTTP_200_OK
        assert resp.json()["deleted"] == 1


class TestStreamHub:
    @pytest.mark.asyncio
    async def test_publish_from_other_thread_wakes_subscriber(self):
        run_id = str(uuid.uuid4())
        q = stream_hub.subscribe(run_id)
        payload = {"type": "event", "event": {"seq": 99}}

        def publish_later() -> None:
            time.sleep(0.05)
            stream_hub.publish(run_id, payload)

        threading.Thread(target=publish_later, daemon=True).start()
        try:
            msg = await asyncio.wait_for(q.get(), timeout=2.0)
        finally:
            stream_hub.unsubscribe(run_id, q)
        assert msg == payload


class TestKbSearchAgentTrace:
    def test_trace_kb_search_service(self, db_session, regular_user, active_api_key):
        from services.agent_run_service import trace_kb_search

        url = trace_kb_search(
            db_session,
            regular_user,
            thread_id=f"hermes-{uuid.uuid4().hex[:8]}",
            question_preview="报销流程",
            hit_count=2,
            api_key_id=int(active_api_key.id),
        )
        assert url
        assert "/agent/runs/" in url

    def test_trace_kb_search_reuses_session_run(self, db_session, regular_user, active_api_key):
        from models.agent_run import AgentRunEvent
        from services.agent_run_service import trace_kb_search

        tid = f"session-{uuid.uuid4().hex[:8]}"
        url1 = trace_kb_search(
            db_session,
            regular_user,
            thread_id=tid,
            question_preview="北斗协作",
            hit_count=1,
            api_key_id=int(active_api_key.id),
        )
        url2 = trace_kb_search(
            db_session,
            regular_user,
            thread_id=tid,
            question_preview="徐泽宇",
            hit_count=3,
            api_key_id=int(active_api_key.id),
        )
        assert url1 == url2
        run_id = url1.rsplit("/", 1)[-1]
        events = (
            db_session.query(AgentRunEvent)
            .filter(AgentRunEvent.run_id == run_id)
            .order_by(AgentRunEvent.seq.asc())
            .all()
        )
        assert len(events) == 4
        assert events[0].phase == "start"
        assert events[1].phase == "end"
        assert events[0].task_key != events[2].task_key
        assert events[0].span_id == events[1].span_id

    def test_ensure_session_run_endpoint(self, client, active_api_key):
        tid = f"ensure-{uuid.uuid4().hex[:8]}"
        headers = {"Authorization": f"Bearer {active_api_key._plaintext}"}
        first = client.post(
            "/api/agent-runs/ensure",
            headers=headers,
            json={"question_preview": "问句 A", "thread_id": tid},
        )
        assert first.status_code == status.HTTP_200_OK
        assert first.json()["created"] is True
        run_id = first.json()["run_id"]

        second = client.post(
            "/api/agent-runs/ensure",
            headers=headers,
            json={"question_preview": "问句 B", "thread_id": tid},
        )
        assert second.status_code == status.HTTP_200_OK
        assert second.json()["created"] is False
        assert second.json()["run_id"] == run_id

    def test_trace_kb_search_invalid_agent_run_id_skips_trace(
        self, db_session, regular_user, active_api_key
    ):
        from models.agent_run import AgentRun
        from services.agent_run_service import trace_kb_search

        before = db_session.query(AgentRun).count()
        url = trace_kb_search(
            db_session,
            regular_user,
            thread_id=f"tid-{uuid.uuid4().hex[:8]}",
            question_preview="无效 run",
            hit_count=0,
            api_key_id=int(active_api_key.id),
            agent_run_id="00000000-0000-0000-0000-000000000099",
        )
        assert url is None
        assert db_session.query(AgentRun).count() == before

    def test_trace_kb_search_explicit_agent_run_id_appends_to_run(
        self, db_session, regular_user, active_api_key
    ):
        from models.agent_run import AgentRunEvent
        from schemas.agent_run import AgentRunCreateRequest
        from services.agent_run_service import ensure_session_run, trace_kb_search

        run, _ = ensure_session_run(
            db_session,
            regular_user,
            AgentRunCreateRequest(question_preview="根问句", thread_id="explicit-tid"),
            api_key_id=int(active_api_key.id),
        )
        url = trace_kb_search(
            db_session,
            regular_user,
            thread_id="other-thread-should-not-matter",
            question_preview="子检索",
            hit_count=2,
            api_key_id=int(active_api_key.id),
            agent_run_id=run.id,
            search_trace_id="trace-explicit",
        )
        assert url.endswith(run.id)
        events = (
            db_session.query(AgentRunEvent)
            .filter(AgentRunEvent.run_id == run.id)
            .order_by(AgentRunEvent.seq.asc())
            .all()
        )
        assert len(events) == 2
        assert events[0].phase == "start"
        assert events[1].meta_json["hit_count"] == 2
        assert events[1].meta_json["trace_id"] == "trace-explicit"

    def test_ensure_session_run_marks_expired_running_as_failed(
        self, db_session, regular_user, active_api_key
    ):
        from datetime import timedelta

        from models.agent_run import AgentRun
        from schemas.agent_run import AgentRunCreateRequest
        from services.agent_run_service import ensure_session_run
        from utils.timezone import beijing_now

        tid = f"expired-{uuid.uuid4().hex[:8]}"
        stale = AgentRun(
            user_id=int(regular_user.id),
            api_key_id=int(active_api_key.id),
            thread_id=tid,
            question_preview="过期",
            status="running",
            expires_at=beijing_now().replace(tzinfo=None) - timedelta(hours=1),
        )
        db_session.add(stale)
        db_session.commit()
        stale_id = stale.id

        run, created = ensure_session_run(
            db_session,
            regular_user,
            AgentRunCreateRequest(question_preview="新问句", thread_id=tid),
            api_key_id=int(active_api_key.id),
        )
        assert created is True
        assert run.id != stale_id
        db_session.refresh(stale)
        assert stale.status == "failed"
        assert stale.finished_at is not None

    def test_search_with_agent_thread_id_creates_run(
        self, client, active_api_key, jwt_token, monkeypatch
    ):
        def fake_search_kb(*args, **kwargs):
            return [], "test-model", 3, {}

        monkeypatch.setattr("routers.knowledge_base.search_kb", fake_search_kb)
        monkeypatch.setattr(
            "services.kb_search_wiki_hint.build_wiki_context_hint",
            lambda *a, **k: None,
        )

        thread_id = f"hermes-{uuid.uuid4().hex[:8]}"
        resp = client.post(
            "/api/knowledge-base/search",
            headers={"Authorization": f"Bearer {active_api_key._plaintext}"},
            json={
                "query": "报销流程",
                "agent_thread_id": thread_id,
                "top_k": 3,
            },
        )
        assert resp.status_code == status.HTTP_200_OK
        data = resp.json()
        assert data.get("agent_trace_view_url")
        assert "/agent/runs/" in data["agent_trace_view_url"]
        assert "查看本次处理流程" in data.get("agent_notice", "")

    def test_search_without_thread_id_still_creates_run(
        self, client, active_api_key, jwt_token, monkeypatch
    ):
        def fake_search_kb(*args, **kwargs):
            return [], "test-model", 3, {}

        monkeypatch.setattr("routers.knowledge_base.search_kb", fake_search_kb)
        monkeypatch.setattr(
            "services.kb_search_wiki_hint.build_wiki_context_hint",
            lambda *a, **k: None,
        )

        resp = client.post(
            "/api/knowledge-base/search",
            headers={"Authorization": f"Bearer {active_api_key._plaintext}"},
            json={"query": "北斗协作", "top_k": 3},
        )
        assert resp.status_code == status.HTTP_200_OK
        data = resp.json()
        assert data.get("agent_trace_view_url")
        assert "/agent/runs/" in data["agent_trace_view_url"]

        listed = client.get(
            "/api/agent-runs",
            headers={"Authorization": f"Bearer {jwt_token}"},
        )
        assert listed.status_code == status.HTTP_200_OK
        assert listed.json()["total"] >= 1
