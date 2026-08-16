# Copyright (c) 2026 徐泽宇
"""用途专用的 LLM 输出契约；transport 层不得把这些结果继续当裸 dict 使用。"""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field


class LlmEntity(BaseModel):
    name: str = Field(min_length=1, max_length=256)
    type: Literal["person", "org", "metric", "concept", "location", "other"] = "concept"


class LlmRelation(BaseModel):
    source: str = Field(min_length=1, max_length=256)
    relation: str = Field(default="related_to", min_length=1, max_length=64)
    target: str | None = Field(default=None, max_length=256)


class EntityExtractionOutput(BaseModel):
    entities: list[LlmEntity] = Field(default_factory=list)
    relations: list[LlmRelation] = Field(default_factory=list)


class SagEventExtractionOutput(BaseModel):
    title: str = ""
    summary: str = ""
    content: str = ""
    entities: list[LlmEntity] = Field(default_factory=list)


class RaptorSummaryOutput(BaseModel):
    summary: str = ""


class FulltextCitationCandidate(BaseModel):
    file_index: int = Field(ge=0)
    excerpt: str = ""


class FulltextFileAnalysis(BaseModel):
    file_index: int = Field(ge=0)
    key_facts: list[str] = Field(default_factory=list)


class FulltextSubAnswer(BaseModel):
    question: str = ""
    answer: str = ""
    citations: list[FulltextCitationCandidate] = Field(default_factory=list)


class FulltextReasoningOutput(BaseModel):
    file_analysis: list[FulltextFileAnalysis] = Field(default_factory=list)
    sub_answers: list[FulltextSubAnswer] = Field(default_factory=list)
    conclusion: Literal["肯定", "否定", "不确定"] = "不确定"
    reasoning: str = ""
    citations: list[FulltextCitationCandidate] = Field(default_factory=list)
    missing_evidence: list[str] = Field(default_factory=list)
    confidence: float = Field(default=0.0, ge=0.0, le=1.0)
