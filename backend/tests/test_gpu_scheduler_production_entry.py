# Copyright (c) 2026 徐泽宇
"""Production-entry seams must route GPU calls through the scheduler context."""

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import patch

from services.gpu_model_lifecycle_service import GpuExecutionContext, ModelGroup


class FakeScheduler:
    def __init__(self) -> None:
        self.calls: list[tuple[str, object]] = []

    def switch_to(self, model_group, context):
        self.calls.append(("switch", (model_group, context)))

    def acquire_batch(self, model_group, job_ids, context):
        self.calls.append(("batch", (model_group, tuple(job_ids), context)))

    def execute(self, model_group, context, **kwargs):
        self.calls.append(("execute", (model_group, context)))
        return kwargs["call"]()


def test_mineru_rpc_entry_routes_through_scheduler_and_context():
    from messaging.kb_mineru_rpc import call_mineru_extract

    context = GpuExecutionContext("lease-1", "fence-1", "job-7")
    scheduler = FakeScheduler()
    with patch(
        "messaging.kb_mineru_rpc._call_mineru_extract_direct",
        return_value={"ok": True, "gpu_lease_id": "lease-1", "fencing_token": "fence-1", "gpu_job_id": "job-7"},
    ) as direct:
        result = call_mineru_extract(
            job_id=7,
            file_id=9,
            file_path="/uploads/1/doc.pdf",
            original_name="doc.pdf",
            gpu_scheduler=scheduler,  # type: ignore[arg-type]
            gpu_context=context,
        )

    assert result["ok"] is True
    assert [name for name, _ in scheduler.calls] == ["switch", "batch", "execute"]
    assert scheduler.calls[0][1][0] == ModelGroup.MINERU
    assert direct.call_args.kwargs["gpu_context"] == context


def test_raptor_summary_entry_routes_through_scheduler_and_context():
    from services import kb_raptor_service as raptor

    context = GpuExecutionContext("lease-1", "fence-1", "job-7")
    scheduler = FakeScheduler()
    with patch(
        "services.kb_raptor_service.chat_json",
        return_value={"summary": "summary"},
    ) as chat:
        result, reason = raptor._ollama_summarize_once(
            "source",
            timeout_sec=30,
            gpu_scheduler=scheduler,  # type: ignore[arg-type]
            gpu_context=context,
        )

    assert (result, reason) == ("summary", None)
    assert [name for name, _ in scheduler.calls] == ["switch", "batch", "execute"]
    assert scheduler.calls[0][1][0] == ModelGroup.RAPTOR
    assert chat.call_args.kwargs["gpu_context"] == context


def test_registry_default_mineru_entry_injects_process_scheduler():
    from models.file import File as FileModel
    from services.extract.providers import registry

    context = GpuExecutionContext("lease-1", "fence-1", "job-7")
    scheduler = FakeScheduler()
    file = FileModel(id=9, filename="doc.pdf", original_name="doc.pdf", user_id=1)
    with patch("services.gpu_scheduler_runtime.scheduler_for_job", return_value=(scheduler, context)):
        with patch("services.extract.providers.mineru_provider.extract_mineru") as extract:
            extract.return_value = object()
            result = registry.extract_with_provider(
                file,
                provider_override="mineru",
                job_id=7,
            )

    assert result is extract.return_value
    assert extract.call_args.kwargs["gpu_scheduler"] is scheduler
    assert extract.call_args.kwargs["gpu_context"] is context


def test_registry_cpu_disabled_does_not_inject_scheduler(monkeypatch):
    from models.file import File as FileModel
    from services.extract.providers import registry

    monkeypatch.setattr("config.GPU_SCHEDULER_ENABLED", False)
    file = FileModel(id=9, filename="doc.pdf", original_name="doc.pdf", user_id=1)
    with patch("services.extract.providers.mineru_provider.extract_mineru") as extract:
        extract.return_value = object()
        result = registry.extract_with_provider(
            file,
            provider_override="mineru",
            job_id=7,
        )

    assert result is extract.return_value
    assert extract.call_args.kwargs["gpu_scheduler"] is None
    assert extract.call_args.kwargs["gpu_context"] is None


def test_raptor_cpu_disabled_does_not_inject_scheduler(monkeypatch):
    from services import kb_raptor_service as raptor

    monkeypatch.setattr("config.GPU_SCHEDULER_ENABLED", False)
    with patch(
        "services.kb_raptor_service.get_kb_raptor_settings",
        return_value=SimpleNamespace(enabled=True, fail_open=False),
    ):
        with patch(
            "services.system_setting_service.get_kb_large_doc_settings",
            return_value={"char_threshold": 10**9},
        ):
            with patch("services.kb_raptor_service.build_tree", return_value=(0, None)) as build:
                raptor.maybe_build_raptor_tree(
                    None,
                    SimpleNamespace(id=7),
                    md_char_count=1000,
                    source="src",
                    fts_config="simple",
                )

    assert build.call_args.kwargs["gpu_scheduler"] is None
    assert build.call_args.kwargs["gpu_context"] is None


def test_raptor_openai_provider_does_not_start_ollama_scheduler(monkeypatch):
    from services import kb_raptor_service as raptor

    monkeypatch.setattr("config.GPU_SCHEDULER_ENABLED", True)
    with patch(
        "services.kb_raptor_service.get_kb_raptor_settings",
        return_value=SimpleNamespace(enabled=True, fail_open=False),
    ):
        with patch(
            "services.kb_raptor_service.get_kb_post_llm_runtime_config",
            return_value=SimpleNamespace(provider="openai_compatible"),
        ):
            with patch("services.gpu_scheduler_runtime.scheduler_for_job") as scheduler:
                with patch("services.kb_raptor_service.build_tree", return_value=(0, None)) as build:
                    raptor.maybe_build_raptor_tree(
                        None,
                        SimpleNamespace(id=7),
                        md_char_count=1000,
                        source="src",
                        fts_config="simple",
                        force_settings=True,
                    )

    scheduler.assert_not_called()
    assert build.call_args.kwargs["gpu_scheduler"] is None
    assert build.call_args.kwargs["gpu_context"] is None
