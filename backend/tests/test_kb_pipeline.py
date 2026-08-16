# Copyright (c) 2026 徐泽宇
"""048 pipeline schema, resolve, and settings validation."""

import pytest

from models.file import File as FileModel
from services.kb_pipeline_service import (
    normalize_route_provider,
    parse_pipeline_config,
    resolve_route_provider,
    serialize_pipeline_config,
    KbPipelineConfig,
    KbPipelineRoute,
    builtin_pipeline_routes,
)
from services.system_setting_service import (
    KEY_KB_INGESTION_PIPELINE_JSON,
    update_settings,
    invalidate_settings_cache,
)


def test_parse_pipeline_valid():
    raw = """{
      "version": 1,
      "routes": [
        {"match": {"mime_prefix": "application/pdf"}, "extract_provider": "mineru"},
        {"match": {"ext": [".docx", ".pptx"]}, "extract_provider": "markitdown"}
      ],
      "stages": {"entity_extract": false, "wiki_lint_on_index": false}
    }"""
    cfg = parse_pipeline_config(raw)
    assert cfg is not None
    assert len(cfg.routes) == 2
    assert cfg.routes[0].extract_provider == "mineru"


def test_parse_pipeline_rejects_unknown_stage():
    raw = '{"version": 1, "routes": [], "stages": {"unknown": true}}'
    with pytest.raises(ValueError, match="未知键"):
        parse_pipeline_config(raw)


def test_parse_pipeline_rejects_bad_provider():
    raw = '{"version": 1, "routes": [{"match": {"ext": [".pdf"]}, "extract_provider": "bad"}]}'
    with pytest.raises(ValueError, match="白名单"):
        parse_pipeline_config(raw)


def test_markitdown_alias_normalizes_to_legacy():
    assert normalize_route_provider("markitdown") == "legacy"


def test_eml_route_is_builtin_and_cannot_be_user_configured():
    builtins = builtin_pipeline_routes()
    assert builtins[0]["match"] == {"ext": [".eml"]}
    with pytest.raises(ValueError, match="eml.*内置"):
        parse_pipeline_config(
            '{"version":1,"routes":[{"match":{"ext":[".eml"]},"extract_provider":"mineru"}]}'
        )


def test_eml_builtin_route_wins_over_user_route():
    cfg = KbPipelineConfig(
        version=1,
        routes=(KbPipelineRoute(match={"ext": [".eml"]}, extract_provider="mineru"),),
    )
    f = FileModel(original_name="mail.eml", file_path="/tmp/mail.eml", mime_type="message/rfc822")
    assert resolve_route_provider(cfg, f) == "legacy"


def test_eml_builtin_route_uses_persisted_mime_after_display_rename(db_session):
    cfg = KbPipelineConfig(
        version=1,
        routes=(KbPipelineRoute(match={"ext": [".pdf"]}, extract_provider="mineru"),),
    )
    f = FileModel(original_name="renamed.pdf", file_path="/tmp/mail.eml", mime_type="message/rfc822")
    from services.kb_pipeline_service import resolve_extract_provider

    assert resolve_route_provider(cfg, f) == "legacy"
    assert resolve_extract_provider(db_session, f, explicit_provider="mineru") == "legacy"


def test_resolve_route_pdf_to_mineru():
    cfg = parse_pipeline_config(
        '{"version":1,"routes":[{"match":{"mime_prefix":"application/pdf"},"extract_provider":"mineru"}]}'
    )
    f = FileModel(
        filename="a.pdf",
        original_name="a.pdf",
        file_path="/tmp/a.pdf",
        file_size=1,
        mime_type="application/pdf",
        user_id=1,
    )
    assert resolve_route_provider(cfg, f) == "mineru"


def test_resolve_route_later_wins():
    cfg = KbPipelineConfig(
        version=1,
        routes=(
            KbPipelineRoute(match={"ext": [".pdf"]}, extract_provider="legacy"),
            KbPipelineRoute(match={"mime_prefix": "application/pdf"}, extract_provider="mineru"),
        ),
    )
    f = FileModel(
        filename="a.pdf",
        original_name="a.pdf",
        file_path="/tmp/a.pdf",
        file_size=1,
        mime_type="application/pdf",
        user_id=1,
    )
    assert resolve_route_provider(cfg, f) == "mineru"


def test_settings_invalid_pipeline_400(db_session):
    with pytest.raises(ValueError, match="JSON"):
        update_settings(db_session, {KEY_KB_INGESTION_PIPELINE_JSON: "{not-json"})
    invalidate_settings_cache()


def test_settings_valid_pipeline_roundtrip(db_session):
    cfg = parse_pipeline_config(
        '{"version":1,"routes":[{"match":{"mime_prefix":"application/pdf"},"extract_provider":"mineru"}]}'
    )
    assert cfg is not None
    update_settings(db_session, {KEY_KB_INGESTION_PIPELINE_JSON: serialize_pipeline_config(cfg)})
    invalidate_settings_cache()


def test_settings_rejects_eml_route_without_changing_existing_value(db_session):
    original = '{"version":1,"routes":[{"match":{"ext":[".pdf"]},"extract_provider":"legacy"}],"stages":{}}'
    update_settings(db_session, {KEY_KB_INGESTION_PIPELINE_JSON: original})
    with pytest.raises(ValueError, match="eml.*内置"):
        update_settings(
            db_session,
            {KEY_KB_INGESTION_PIPELINE_JSON: '{"version":1,"routes":[{"match":{"mime_prefix":"message/"},"extract_provider":"mineru"}]}'},
        )
    assert db_session.query(__import__("models.system_setting", fromlist=["SystemSetting"]).SystemSetting).filter_by(
        setting_key=KEY_KB_INGESTION_PIPELINE_JSON
    ).first().value == original
    invalidate_settings_cache()


def test_builtin_eml_route_is_exposed_by_system_settings_schema():
    from schemas.system_setting import SystemSettingsResponse

    payload = SystemSettingsResponse(builtin_routes=[{
        "match": {"ext": [".eml"]},
        "extract_provider": "legacy",
        "engine": "eml-parser",
        "builtin": True,
        "readonly": True,
    }])
    assert payload.builtin_routes[0]["engine"] == "eml-parser"


def test_enqueue_pdf_route_mineru(db_session, regular_user):
    from unittest.mock import patch
    from models.kb_extract_job import KbExtractJob
    from services.kb_extract_service import enqueue_extract
    from services.system_setting_service import KEY_KB_INGESTION_PIPELINE_JSON, invalidate_settings_cache, update_settings

    update_settings(
        db_session,
        {
            KEY_KB_INGESTION_PIPELINE_JSON: '{"version":1,"routes":[{"match":{"mime_prefix":"application/pdf"},"extract_provider":"mineru"}]}',
        },
    )
    invalidate_settings_cache()
    f = __import__("models.file", fromlist=["File"]).File(
        filename="x.bin",
        original_name="scan.pdf",
        file_path="/tmp/x",
        file_size=10,
        mime_type="application/pdf",
        user_id=regular_user.id,
        has_md=False,
    )
    db_session.add(f)
    db_session.commit()
    with patch("messaging.kb_extract_publisher.publish_kb_extract_job"):
        job_id = enqueue_extract(db_session, f.user_id, f.id)
    assert job_id is not None
    job = db_session.query(KbExtractJob).filter(KbExtractJob.id == job_id).first()
    assert job.provider == "mineru"
