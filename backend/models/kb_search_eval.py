# Copyright (c) 2026 徐泽宇
"""RAGAS online evaluation ORM model."""

from __future__ import annotations

from sqlalchemy import Column, DateTime, Float, ForeignKey, Integer, String, Text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.sql import func

from database import Base


class KbSearchEval(Base):
    __tablename__ = "kb_search_eval"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False, index=True)
    workspace_id = Column(Integer, nullable=True, index=True)
    agent_run_id = Column(String(36), nullable=True, index=True)
    search_trace_id = Column(String(64), nullable=True, index=True)

    # 样本类型：answer=正常合成回答样本；recall_no_hit=召回质量样本
    #（no_final_answer，用 no-hit 文案当 answer、evidence 当 contexts）。
    sample_type = Column(String(32), nullable=False, server_default="answer", index=True)

    query_hash = Column(String(64), nullable=False, index=True)
    query_preview = Column(String(512), nullable=False)
    answer_hash = Column(String(64), nullable=False, index=True)
    answer_preview = Column(String(512), nullable=False)

    context_count = Column(Integer, nullable=False, server_default="0")
    context_file_ids_json = Column(JSONB, nullable=False, server_default="[]")
    context_chunk_ids_json = Column(JSONB, nullable=False, server_default="[]")

    faithfulness_score = Column(Float, nullable=True)
    context_precision_score = Column(Float, nullable=True)
    metric_provider = Column(String(32), nullable=False, server_default="ragas")
    metric_version = Column(String(255), nullable=True)
    metric_variant = Column(String(255), nullable=True)
    llm_provider = Column(String(64), nullable=True)
    llm_model = Column(String(128), nullable=True)

    status = Column(String(16), nullable=False, server_default="pending", index=True)
    error_code = Column(String(64), nullable=True)
    error_message = Column(Text, nullable=True)
    duration_ms = Column(Integer, nullable=True)
    queue_duration_ms = Column(Integer, nullable=True)
    faithfulness_duration_ms = Column(Integer, nullable=True)
    context_precision_duration_ms = Column(Integer, nullable=True)
    failure_stage = Column(String(32), nullable=True, index=True)
    context_budget_version = Column(String(16), nullable=True)
    source_context_count = Column(Integer, nullable=True)
    selected_context_count = Column(Integer, nullable=True)
    selected_context_chars = Column(Integer, nullable=True)
    created_at = Column(DateTime, server_default=func.now(), index=True)
    evaluated_at = Column(DateTime, nullable=True, index=True)
