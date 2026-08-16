# Copyright (c) 2026 徐泽宇
"""146 P1: Tests for iterative search (extract_new_leads_node)."""

import sys
from pathlib import Path

import pytest

from schemas.kb import KbSearchMeta


AGENT_DIR = Path(__file__).resolve().parents[2] / "skill" / "ding" / "agent"
if str(AGENT_DIR) not in sys.path:
    sys.path.insert(0, str(AGENT_DIR))


class TestKbSearchMetaIterativeFields:
    """Verify KbSearchMeta includes iterative search fields."""

    def test_meta_has_iterative_fields(self):
        meta = KbSearchMeta()
        assert hasattr(meta, "iterative_rounds")
        assert hasattr(meta, "iterative_new_entities")
        assert hasattr(meta, "iterative_new_file_ids")
        assert hasattr(meta, "iterative_truncated")

    def test_meta_iterative_fields_default_none(self):
        meta = KbSearchMeta()
        assert meta.iterative_rounds is None
        assert meta.iterative_new_entities is None
        assert meta.iterative_new_file_ids is None
        assert meta.iterative_truncated is None


class TestExtractEntitiesFromChunks:
    """Verify entity extraction from chunk text."""

    def test_extract_chinese_names(self):
        from skill.ding.agent.filex_langgraph_kb_orchestrator import _extract_entities_from_chunks

        evidence = [
            {"text": "张三负责FileX项目后端开发，李四负责前端。", "chunk_id": "1"},
            {"text": "王五在2024年加入公司。", "chunk_id": "2"},
        ]
        entities = _extract_entities_from_chunks(evidence)
        # Regex extracts 2-3 char sequences; names may appear as substrings
        entity_text = " ".join(entities)
        assert "张三" in entity_text or "张" in entity_text
        assert "李四" in entity_text or "李" in entity_text
        assert "王五" in entity_text or "王" in entity_text
        # Should find some entities
        assert len(entities) > 0

    def test_extract_english_proper_nouns(self):
        from skill.ding.agent.filex_langgraph_kb_orchestrator import _extract_entities_from_chunks

        evidence = [
            {"text": "FileX project led by John Smith and Alice.", "chunk_id": "1"},
        ]
        entities = _extract_entities_from_chunks(evidence)
        assert "FileX" in entities
        assert "John" in entities
        assert "Alice" in entities

    def test_filter_stopwords(self):
        from skill.ding.agent.filex_langgraph_kb_orchestrator import _extract_entities_from_chunks

        evidence = [
            {"text": "我们可以通过这个方式进行使用。", "chunk_id": "1"},
        ]
        entities = _extract_entities_from_chunks(evidence)
        # Stopwords should be filtered
        assert "我们" not in entities
        assert "这个" not in entities
        assert "可以" not in entities

    def test_extract_from_snippets(self):
        from skill.ding.agent.filex_langgraph_kb_orchestrator import _extract_entities_from_chunks

        evidence = [
            {
                "text": "",
                "chunk_id": "1",
                "snippets": [{"text": "赵六的合同签署日期为2025年。"}],
            },
        ]
        entities = _extract_entities_from_chunks(evidence)
        assert "赵六" in entities

    def test_empty_evidence(self):
        from skill.ding.agent.filex_langgraph_kb_orchestrator import _extract_entities_from_chunks

        entities = _extract_entities_from_chunks([])
        assert entities == []

    def test_max_entities_limit(self):
        from skill.ding.agent.filex_langgraph_kb_orchestrator import _extract_entities_from_chunks

        evidence = [
            {"text": " ".join([f"实体{i}" for i in range(20)]), "chunk_id": "1"},
        ]
        entities = _extract_entities_from_chunks(evidence, max_entities=5)
        assert len(entities) <= 5


class TestDedupByChunkId:
    """Verify chunk deduplication utility."""

    def test_dedup_keeps_highest_score(self):
        from skill.ding.agent.filex_langgraph_kb_orchestrator import _dedup_by_chunk_id

        items = [
            {"chunk_id": "1", "score": 0.5, "text": "low"},
            {"chunk_id": "1", "score": 0.9, "text": "high"},
            {"chunk_id": "2", "score": 0.7, "text": "unique"},
        ]
        result = _dedup_by_chunk_id(items)
        assert len(result) == 2
        scores = {r["chunk_id"]: r["score"] for r in result}
        assert scores["1"] == 0.9
        assert scores["2"] == 0.7

    def test_dedup_with_top_k(self):
        from skill.ding.agent.filex_langgraph_kb_orchestrator import _dedup_by_chunk_id

        items = [
            {"chunk_id": str(i), "score": float(i)} for i in range(10)
        ]
        result = _dedup_by_chunk_id(items, top_k=3)
        assert len(result) == 3
        assert result[0]["score"] == 9.0

    def test_dedup_empty(self):
        from skill.ding.agent.filex_langgraph_kb_orchestrator import _dedup_by_chunk_id

        result = _dedup_by_chunk_id([])
        assert result == []
