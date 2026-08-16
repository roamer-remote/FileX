# Copyright (c) 2026 徐泽宇
"""072 P2: GET /api/knowledge-base/retrieval-hints."""

from services.kb_retrieval_hints_service import (
    QueryType,
    classify_query_type,
    parse_dual_entity_question,
    suggest_retrieval_hints,
)


def test_classify_tag_topic_and_struct_relation():
    assert classify_query_type("相邻标签共现的主题") == QueryType.TAG_TOPIC
    assert classify_query_type("A 和 B 什么关系") == QueryType.STRUCT_RELATION


def test_parse_dual_entity_question():
    assert parse_dual_entity_question("资料A与资料B什么关系") == ("资料A", "资料B")
    assert parse_dual_entity_question("这篇涉及哪些主题") is None


def test_suggest_retrieval_hints_tag_topic(client, jwt_token):
    r = client.get(
        "/api/knowledge-base/retrieval-hints",
        headers={"Authorization": f"Bearer {jwt_token}"},
        params={"query": "相邻标签共现主题"},
    )
    assert r.status_code == 200
    data = r.json()
    assert data["query_type"] == "tag_topic"
    assert data["primary_path"] == "search"
    assert data["search_params"]["expand_tag_cooc"] is True
    assert data["search_params"]["wiki_context_depth"] == 1
    assert data["use_query_cache_allowed"] is False
    assert "no-store" in r.headers.get("cache-control", "")


def test_suggest_retrieval_hints_struct_relation_dual_entity(client, jwt_token):
    r = client.get(
        "/api/knowledge-base/retrieval-hints",
        headers={"Authorization": f"Bearer {jwt_token}"},
        params={"query": "资料A和资料B什么关系"},
    )
    assert r.status_code == 200
    data = r.json()
    assert data["query_type"] == "struct_relation"
    assert data["primary_path"] == "wiki-path"
    assert data["struct_relation_mode"] == "dual_entity"


def test_suggest_retrieval_hints_struct_relation_single_entity():
    data = suggest_retrieval_hints("这篇的出链有哪些")
    assert data["query_type"] == "struct_relation"
    assert data["primary_path"] == "wiki-explain"
    assert data["struct_relation_mode"] == "single_entity"
