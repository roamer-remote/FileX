# Copyright (c) 2026 徐泽宇
"""Extract provider registry.

Authors:
    徐泽宇

Copyright:
    © 2026 徐泽宇
"""

from unittest.mock import patch

from models.file import File as FileModel
from services.extract.base import ExtractResult
from services.extract.providers.registry import extract_with_provider, get_extract_provider_name
from services.gpu_model_lifecycle_service import GpuWaitingError
from services.system_setting_service import KEY_KB_EXTRACT_PROVIDER, update_settings


def test_default_provider_legacy(db_session):
    assert get_extract_provider_name(db_session) == "legacy"


def test_insavlo_provider_can_be_selected(db_session):
    update_settings(db_session, {KEY_KB_EXTRACT_PROVIDER: "insavlo"})
    assert get_extract_provider_name(db_session) == "insavlo"


@patch("services.extract.providers.registry._legacy_extract")
def test_insavlo_placeholder_does_not_fallback_to_legacy(mock_legacy, db_session, regular_user, tmp_path):
    pdf = tmp_path / "a.pdf"
    pdf.write_bytes(b"%PDF-1.4")
    f = FileModel(
        filename="a",
        original_name="a.pdf",
        file_path=str(pdf),
        file_size=4,
        mime_type="application/pdf",
        user_id=regular_user.id,
    )

    import pytest

    with pytest.raises(RuntimeError, match="Insavlo provider submission"):
        extract_with_provider(f, db_session, provider_override="insavlo")

    mock_legacy.assert_not_called()


@patch("services.extract.providers.registry._legacy_extract")
def test_docling_fallback_to_legacy(mock_legacy, db_session, regular_user, tmp_path):
    update_settings(db_session, {KEY_KB_EXTRACT_PROVIDER: "docling"})
    pdf = tmp_path / "a.pdf"
    pdf.write_bytes(b"%PDF-1.4")
    f = FileModel(
        filename="a",
        original_name="a.pdf",
        file_path=str(pdf),
        file_size=4,
        mime_type="application/pdf",
        user_id=regular_user.id,
    )
    mock_legacy.return_value = ExtractResult(text="ok", engine="legacy")
    r = extract_with_provider(f, db_session)
    assert r.text == "ok"
    mock_legacy.assert_called_once()
    assert r.fallback_from == "docling"


@patch("services.extract.providers.registry._legacy_extract")
def test_liteparse_fallback_to_legacy(mock_legacy, db_session, regular_user, tmp_path):
    update_settings(db_session, {KEY_KB_EXTRACT_PROVIDER: "liteparse"})
    pdf = tmp_path / "a.pdf"
    pdf.write_bytes(b"%PDF-1.4")
    f = FileModel(
        filename="a",
        original_name="a.pdf",
        file_path=str(pdf),
        file_size=4,
        mime_type="application/pdf",
        user_id=regular_user.id,
    )
    mock_legacy.return_value = ExtractResult(text="ok", engine="legacy")

    with patch(
        "services.extract.providers.liteparse_provider.extract_liteparse",
        side_effect=RuntimeError("liteparse down"),
    ):
        r = extract_with_provider(f, db_session)

    assert r.text == "ok"
    mock_legacy.assert_called_once()
    assert r.fallback_from == "liteparse"


@patch("services.extract.providers.registry._legacy_extract")
def test_mineru_gpu_waiting_does_not_fallback_to_legacy(mock_legacy, regular_user, tmp_path):
    pdf = tmp_path / "a.pdf"
    pdf.write_bytes(b"%PDF-1.4")
    f = FileModel(
        filename="a",
        original_name="a.pdf",
        file_path=str(pdf),
        file_size=4,
        mime_type="application/pdf",
        user_id=regular_user.id,
    )
    with patch(
        "services.extract.providers.mineru_provider.extract_mineru",
        side_effect=GpuWaitingError("lifecycle unavailable"),
    ):
        import pytest

        with pytest.raises(GpuWaitingError, match="lifecycle unavailable"):
            extract_with_provider(f, provider_override="mineru")

    mock_legacy.assert_not_called()


@patch("services.extract.providers.registry._legacy_extract")
def test_mineru_generic_failure_fails_closed_when_gpu_scheduler_enabled(
    mock_legacy, db_session, regular_user, tmp_path, monkeypatch
):
    monkeypatch.setattr("config.GPU_SCHEDULER_ENABLED", True)
    pdf = tmp_path / "gpu.pdf"
    pdf.write_bytes(b"%PDF-1.4")
    f = FileModel(
        filename="gpu",
        original_name="gpu.pdf",
        file_path=str(pdf),
        file_size=4,
        mime_type="application/pdf",
        user_id=regular_user.id,
    )
    with patch(
        "services.extract.providers.mineru_provider.extract_mineru",
        side_effect=RuntimeError("sidecar down"),
    ):
        import pytest

        with pytest.raises(GpuWaitingError, match="mineru gpu execution failed"):
            extract_with_provider(f, db_session, provider_override="mineru")

    mock_legacy.assert_not_called()


@patch("services.extract.providers.registry._legacy_extract")
def test_mineru_generic_failure_falls_back_when_gpu_scheduler_disabled(
    mock_legacy, db_session, regular_user, tmp_path, monkeypatch
):
    monkeypatch.setattr("config.GPU_SCHEDULER_ENABLED", False)
    pdf = tmp_path / "legacy.pdf"
    pdf.write_bytes(b"%PDF-1.4")
    f = FileModel(
        filename="legacy",
        original_name="legacy.pdf",
        file_path=str(pdf),
        file_size=4,
        mime_type="application/pdf",
        user_id=regular_user.id,
    )
    mock_legacy.return_value = ExtractResult(text="fallback ok", engine="legacy")
    with patch(
        "services.extract.providers.mineru_provider.extract_mineru",
        side_effect=RuntimeError("sidecar down"),
    ):
        result = extract_with_provider(f, db_session, provider_override="mineru")

    assert result.text == "fallback ok"
    assert result.fallback_from == "mineru"
    mock_legacy.assert_called_once()


def test_extract_mineru_mq_disabled_fails_closed_for_scheduled_gpu(
    regular_user, tmp_path, monkeypatch
):
    import services.extract.providers.mineru_provider as mineru_provider

    monkeypatch.setattr(mineru_provider, "KB_EXTRACT_MINERU_USE_MQ", False)
    monkeypatch.setattr("config.GPU_SCHEDULER_ENABLED", True)
    pdf = tmp_path / "mq.pdf"
    pdf.write_bytes(b"%PDF-1.4")
    f = FileModel(
        filename="mq",
        original_name="mq.pdf",
        file_path=str(pdf),
        file_size=4,
        mime_type="application/pdf",
        user_id=regular_user.id,
    )

    import pytest

    with pytest.raises(GpuWaitingError, match="mineru_mq_disabled_for_scheduled_gpu"):
        mineru_provider.extract_mineru(f, gpu_scheduler=object(), gpu_context=object())
