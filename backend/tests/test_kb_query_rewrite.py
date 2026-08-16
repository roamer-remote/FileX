# Copyright (c) 2026 徐泽宇
"""146 P0: Tests for query rewrite and multi-query expansion."""

from unittest.mock import patch

import pytest

from services.auth_service import create_access_token


class TestQueryUnderstandRewrittenQueries:
    """Verify query_understand API returns rewritten_queries field."""

    def test_rewritten_queries_in_response(self, client, db_session, regular_user):
        token = create_access_token(regular_user.id, regular_user.password_rev)

        with patch(
            "services.kb_post_llm_service.chat_json",
            return_value={
                "intent": "association",
                "entities": [{"name": "张三", "type": "person"}],
                "constraints": [],
                "sub_questions": [],
                "confidence": 0.95,
                "search_keywords": ["简历"],
                "rewritten_queries": ["张三 工作经历", "张三 任职", "张三 履历"],
            },
        ):
            resp = client.post(
                "/api/knowledge-base/query-understand",
                headers={"Authorization": f"Bearer {token}"},
                json={"question": "张三的工作经历"},
            )

        assert resp.status_code == 200
        data = resp.json()
        assert data["rewritten_queries"] == ["张三 工作经历", "张三 任职", "张三 履历"]

    def test_rewritten_queries_empty_on_fallback(self, client, db_session, regular_user):
        token = create_access_token(regular_user.id, regular_user.password_rev)

        with patch(
            "services.kb_post_llm_service.chat_json",
            side_effect=RuntimeError("LLM unavailable"),
        ):
            resp = client.post(
                "/api/knowledge-base/query-understand",
                headers={"Authorization": f"Bearer {token}"},
                json={"question": "测试问题"},
            )

        assert resp.status_code == 200
        data = resp.json()
        assert data["rewritten_queries"] == []

    def test_rewritten_queries_empty_on_low_confidence(self, client, db_session, regular_user):
        token = create_access_token(regular_user.id, regular_user.password_rev)

        with patch(
            "services.kb_post_llm_service.chat_json",
            return_value={"intent": "fact", "confidence": 0.3},
        ):
            resp = client.post(
                "/api/knowledge-base/query-understand",
                headers={"Authorization": f"Bearer {token}"},
                json={"question": "模糊问题"},
            )

        assert resp.status_code == 200
        data = resp.json()
        assert data["rewritten_queries"] == []

    def test_rewrite_cache_hit(self, client, db_session, regular_user):
        """Same question twice: second call should use cached rewrites if LLM returns none."""
        token = create_access_token(regular_user.id, regular_user.password_rev)

        call_count = [0]

        def mock_chat_json(prompt, **kwargs):
            call_count[0] += 1
            if call_count[0] == 1:
                return {
                    "intent": "fact",
                    "entities": [],
                    "constraints": [],
                    "sub_questions": [],
                    "confidence": 0.9,
                    "search_keywords": [],
                    "rewritten_queries": ["缓存测试查询"],
                }
            # Second call: simulate LLM returning no rewrites
            return {
                "intent": "fact",
                "entities": [],
                "constraints": [],
                "sub_questions": [],
                "confidence": 0.9,
                "search_keywords": [],
                "rewritten_queries": [],
            }

        with patch("services.kb_post_llm_service.chat_json", side_effect=mock_chat_json):
            # First call: cache populated
            resp1 = client.post(
                "/api/knowledge-base/query-understand",
                headers={"Authorization": f"Bearer {token}"},
                json={"question": "重复问题"},
            )
            # Second call: should use cache
            resp2 = client.post(
                "/api/knowledge-base/query-understand",
                headers={"Authorization": f"Bearer {token}"},
                json={"question": "重复问题"},
            )

        assert resp1.status_code == 200
        assert resp2.status_code == 200
        assert resp1.json()["rewritten_queries"] == ["缓存测试查询"]
        # Second call uses cached value even though LLM returned empty
        assert resp2.json()["rewritten_queries"] == ["缓存测试查询"]


class TestKbSearchMetaRewriteFields:
    """Verify KbSearchMeta includes rewrite-related fields."""

    def test_meta_has_rewrite_fields(self):
        from schemas.kb import KbSearchMeta

        meta = KbSearchMeta()
        assert hasattr(meta, "rewritten_queries")
        assert hasattr(meta, "rewrite_llm_ms")
        assert hasattr(meta, "query_rewrite_skipped")

    def test_meta_rewrite_fields_default_none(self):
        from schemas.kb import KbSearchMeta

        meta = KbSearchMeta()
        assert meta.rewritten_queries is None
        assert meta.rewrite_llm_ms is None
        assert meta.query_rewrite_skipped is None
