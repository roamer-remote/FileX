# Copyright (c) 2026 徐泽宇
"""后处理 LLM 运行遥测与 operation_logs 契约测试。"""

from __future__ import annotations

from services.gpu_model_lifecycle_service import GpuExecutionContext


def test_post_llm_observability_collects_model_path_and_gpu_context():
    from services.kb_post_llm_service import (
        KbPostLlmCallTelemetry,
        collect_kb_post_llm_telemetry,
        record_kb_post_llm_call,
    )

    with collect_kb_post_llm_telemetry() as calls:
        record_kb_post_llm_call(
            purpose="raptor_summary",
            provider="ollama",
            model="qwen3.5:9b",
            model_path="/root/.ollama/models/blobs/sha256-abc",
            model_path_scope="container",
            model_path_resolved=True,
            gpu_context=GpuExecutionContext("lease", "fence", "job"),
            gpu_used="unknown",
            gpu_evidence="scheduler_authorized",
        )

    assert calls == [
        KbPostLlmCallTelemetry(
            purpose="raptor_summary",
            provider="ollama",
            model="qwen3.5:9b",
            model_path="/root/.ollama/models/blobs/sha256-abc",
            gpu_used="unknown",
            gpu_evidence="scheduler_authorized",
            model_path_scope="container",
            model_path_resolved=True,
        )
    ]


def test_ollama_show_digest_without_absolute_path_is_not_marked_resolved():
    from services.kb_post_llm_service import _ollama_model_path_from_show

    assert _ollama_model_path_from_show({"modelfile": "FROM sha256:abc\nPARAMETER temperature 0"}) is None


def test_ollama_show_preserves_all_absolute_model_file_paths():
    from services.kb_post_llm_service import _ollama_model_path_from_show

    assert _ollama_model_path_from_show(
        {"modelfile": "FROM /models/base\nFROM /models/adapter\nFROM sha256:ignored"}
    ) == "/models/base|/models/adapter"


def test_post_llm_observability_detail_contains_translated_data_fields():
    from services.kb_post_llm_service import KbPostLlmCallTelemetry, format_kb_post_llm_telemetry

    fields = format_kb_post_llm_telemetry(
        [
            KbPostLlmCallTelemetry(
                purpose="entity_extract",
                provider="openai_compatible",
                model="deepseek-chat",
                model_path=None,
                gpu_used="unknown",
                gpu_evidence="remote_provider",
                model_path_scope="remote",
                model_path_resolved=False,
            )
        ]
    )

    assert fields == {
        "llm_purposes": "entity_extract",
        "llm_providers": "openai_compatible",
        "llm_models": "deepseek-chat",
        "llm_model_paths": "unknown",
        "llm_model_path_scopes": "remote",
        "llm_model_path_resolved": "false",
        "llm_gpu_used": "unknown",
        "llm_gpu_evidence": "remote_provider",
    }


def test_post_llm_observability_encodes_paths_without_losing_full_value():
    from services.kb_post_llm_service import KbPostLlmCallTelemetry, format_kb_post_llm_telemetry

    fields = format_kb_post_llm_telemetry([
        KbPostLlmCallTelemetry(
            purpose="raptor_summary",
            provider="ollama",
            model="local model",
            model_path="/root/models/blob with spaces,comma",
            gpu_used="true",
            gpu_evidence="ollama_ps_vram",
            model_path_scope="container",
            model_path_resolved=True,
        )
    ])

    assert "%2Froot%2Fmodels%2Fblob%20with%20spaces%2Ccomma" in fields["llm_model_paths"]
