# Copyright (c) 2026 徐泽宇
"""SC-048-001: no pipeline config behaves like master."""

from unittest.mock import patch

import pytest

from config import OLLAMA_EMBED_DIM
from models.file import File as FileModel
from models.kb_chunk import KbChunk
from models.kb_extract_job import KbExtractJob
from services.kb_extract_service import enqueue_extract
from services.kb_pipeline_service import resolve_extract_provider
from services.kb_search_service import search_kb
from services.system_setting_service import (
    KEY_KB_EXTRACT_PROVIDER,
    KEY_KB_INGESTION_PIPELINE_JSON,
    KEY_KB_SEARCH_HYBRID_ENABLED,
    get_kb_ingestion_pipeline_json,
    invalidate_settings_cache,
    update_settings,
)


def _vec(a: float = 1.0) -> list[float]:
    v = [0.0] * OLLAMA_EMBED_DIM
    v[0] = a
    return v


@pytest.fixture(autouse=True)
def clear_pipeline(db_session):
    update_settings(
        db_session,
        {
            KEY_KB_INGESTION_PIPELINE_JSON: "",
            KEY_KB_EXTRACT_PROVIDER: "legacy",
            KEY_KB_SEARCH_HYBRID_ENABLED: "false",
        },
    )
    invalidate_settings_cache()
    assert get_kb_ingestion_pipeline_json(db_session) == ""


@patch("services.kb_search_service.embed_text")
def test_search_no_config_golden(mock_embed, db_session, regular_user):
    mock_embed.return_value = _vec(0.9)
    f = FileModel(
        filename="a",
        original_name="回归.pdf",
        file_path="/tmp/a",
        file_size=1,
        mime_type="application/pdf",
        user_id=regular_user.id,
        index_status="ready",
    )
    db_session.add(f)
    db_session.commit()
    db_session.add(
        KbChunk(
            user_id=regular_user.id,
            file_id=f.id,
            chunk_index=0,
            source="sidecar_md",
            text="报销制度",
            char_start=0,
            char_end=4,
            embedding=_vec(0.95),
            embedding_model="test",
        )
    )
    db_session.commit()

    items, _, k, meta = search_kb(db_session, regular_user.id, "报销", top_k=5, debug=True)
    assert k == 5
    assert len(items) >= 1
    assert items[0]["file_id"] == f.id
    assert meta.get("debug_funnel") is not None


def test_enqueue_no_config_uses_global_provider(db_session, regular_user):
    update_settings(db_session, {KEY_KB_EXTRACT_PROVIDER: "legacy"})
    invalidate_settings_cache()
    f = FileModel(
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
    assert resolve_extract_provider(db_session, f) == "legacy"

    with patch("messaging.kb_extract_publisher.publish_kb_extract_job"):
        job_id = enqueue_extract(db_session, f.user_id, f.id)
    assert job_id is not None
    job = db_session.query(KbExtractJob).filter(KbExtractJob.id == job_id).first()
    assert job.provider == "legacy"


def test_no_config_should_rebuild_entity_edges(db_session):
    from services.kb_pipeline_service import should_rebuild_entity_edges_after_index

    assert should_rebuild_entity_edges_after_index(db_session) is True


def test_pipeline_entity_extract_false_disables_rebuild(db_session):
    from services.kb_pipeline_service import should_rebuild_entity_edges_after_index

    update_settings(
        db_session,
        {
            KEY_KB_INGESTION_PIPELINE_JSON: '{"version":1,"routes":[],"stages":{"entity_extract":false}}',
        },
    )
    invalidate_settings_cache()
    assert should_rebuild_entity_edges_after_index(db_session) is False
