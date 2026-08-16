# Copyright (c) 2026 徐泽宇
"""077 P0: SAG event extract service + fingerprint + ACL."""

from __future__ import annotations

from unittest.mock import patch

import pytest

from models.file import File as FileModel
from models.kb_chunk import KbChunk
from models.kb_event import KbEvent
from models.kb_event_entity import KbEventEntity
from services.kb_index_fingerprint import compute_file_fingerprint
from services.kb_index_service import delete_chunks_for_file
from services.kb_sag_event_extract_service import (
    delete_sag_events_for_file,
    rebuild_sag_events_for_file,
)
from services.system_setting_service import (
    KEY_KB_SAG_EVENT_EXTRACT_ENABLED,
    KEY_KB_SAG_EVENT_EXTRACT_MODE,
    KEY_KB_SAG_EVENT_PROMPT_VERSION,
    invalidate_settings_cache,
    is_kb_sag_event_extract_enabled,
    update_settings,
)
from services.workspace_service import ensure_personal_workspace


@pytest.fixture(autouse=True)
def _reset_sag_settings(db_session):
    update_settings(
        db_session,
        {
            KEY_KB_SAG_EVENT_EXTRACT_ENABLED: "false",
            KEY_KB_SAG_EVENT_EXTRACT_MODE: "rule",
            KEY_KB_SAG_EVENT_PROMPT_VERSION: "1",
        },
    )
    invalidate_settings_cache()
    yield


def _add_file(db_session, user_id, tmp_path, name, md5, **extra):
    path = tmp_path / name
    path.write_text("x", encoding="utf-8")
    file_row = FileModel(
        user_id=user_id,
        filename=name,
        original_name=name,
        file_path=str(path),
        file_size=1,
        mime_type="text/plain",
        md5_hash=md5,
        index_status="ready",
        page_kind="source",
        **extra,
    )
    db_session.add(file_row)
    db_session.commit()
    db_session.refresh(file_row)
    return file_row


def _add_chunk(db_session, user_id, file_id, text, *, chunk_index=0, heading_path=None):
    chunk = KbChunk(
        user_id=user_id,
        file_id=file_id,
        chunk_index=chunk_index,
        source="sidecar_md",
        text=text,
        heading_path=heading_path,
        char_start=0,
        char_end=len(text),
    )
    db_session.add(chunk)
    db_session.commit()
    db_session.refresh(chunk)
    return chunk


def test_default_disabled_no_events(db_session, regular_user, tmp_path):
    assert is_kb_sag_event_extract_enabled(db_session) is False
    file_row = _add_file(db_session, regular_user.id, tmp_path, "sag-off.txt", "md5-sag-off")
    _add_chunk(db_session, regular_user.id, file_row.id, "Alpha mentions Beta.")
    count = rebuild_sag_events_for_file(db_session, file_row)
    db_session.commit()
    assert count == 0
    assert db_session.query(KbEvent).filter(KbEvent.file_id == file_row.id).count() == 0


def test_rule_extract_one_event_per_chunk(db_session, regular_user, tmp_path):
    update_settings(db_session, {KEY_KB_SAG_EVENT_EXTRACT_ENABLED: "true"})
    invalidate_settings_cache()
    file_row = _add_file(db_session, regular_user.id, tmp_path, "sag-on.txt", "md5-sag-on")
    chunk_a = _add_chunk(
        db_session,
        regular_user.id,
        file_row.id,
        "Revenue grew 20%.",
        chunk_index=0,
        heading_path="Finance/Q1",
    )
    chunk_b = _add_chunk(
        db_session,
        regular_user.id,
        file_row.id,
        "Costs dropped in March.",
        chunk_index=1,
        heading_path="Finance/Q2",
    )
    count = rebuild_sag_events_for_file(db_session, file_row)
    db_session.commit()
    assert count == 2
    events = (
        db_session.query(KbEvent)
        .filter(KbEvent.file_id == file_row.id)
        .order_by(KbEvent.chunk_id)
        .all()
    )
    assert len(events) == 2
    assert {event.chunk_id for event in events} == {chunk_a.id, chunk_b.id}
    assert events[0].extract_layer == "rule"
    assert events[0].title == "Q1"
    entities = db_session.query(KbEventEntity).filter(KbEventEntity.file_id == file_row.id).all()
    assert entities
    assert all(entity.file_id == file_row.id for entity in entities)


def test_reindex_clears_old_events(db_session, regular_user, tmp_path):
    update_settings(db_session, {KEY_KB_SAG_EVENT_EXTRACT_ENABLED: "true"})
    invalidate_settings_cache()
    file_row = _add_file(db_session, regular_user.id, tmp_path, "sag-reindex.txt", "md5-sag-reindex")
    old_chunk = _add_chunk(db_session, regular_user.id, file_row.id, "Old chunk text.")
    rebuild_sag_events_for_file(db_session, file_row)
    db_session.commit()
    old_event_id = db_session.query(KbEvent.id).filter(KbEvent.chunk_id == old_chunk.id).scalar()
    assert old_event_id

    delete_chunks_for_file(db_session, file_row.id)
    new_chunk = _add_chunk(db_session, regular_user.id, file_row.id, "New chunk text.")
    rebuild_sag_events_for_file(db_session, file_row)
    db_session.commit()

    assert db_session.query(KbEvent).filter(KbEvent.id == old_event_id).count() == 0
    assert db_session.query(KbEvent).filter(KbEvent.chunk_id == new_chunk.id).count() == 1


def test_fingerprint_bump_on_sag_enabled(db_session, regular_user, tmp_path):
    md_path = tmp_path / "sag-fp.txt"
    md_path.write_text("# Title\n\nBody paragraph.", encoding="utf-8")
    file_row = _add_file(
        db_session,
        regular_user.id,
        tmp_path,
        "sag-fp.txt",
        "md5-sag-fp",
        has_md=True,
        md_file_path=str(md_path),
    )
    fp_disabled, _ = compute_file_fingerprint(db_session, file_row)
    update_settings(db_session, {KEY_KB_SAG_EVENT_EXTRACT_ENABLED: "true"})
    invalidate_settings_cache()
    fp_enabled, payload = compute_file_fingerprint(db_session, file_row)
    assert fp_disabled != fp_enabled
    assert payload["sag_extract_enabled"] is True


def test_fingerprint_bump_on_prompt_version(db_session, regular_user, tmp_path):
    md_path = tmp_path / "sag-prompt.txt"
    md_path.write_text("# Title\n\nBody paragraph.", encoding="utf-8")
    file_row = _add_file(
        db_session,
        regular_user.id,
        tmp_path,
        "sag-prompt.txt",
        "md5-sag-prompt",
        has_md=True,
        md_file_path=str(md_path),
    )
    fp_v1, _ = compute_file_fingerprint(db_session, file_row)
    update_settings(db_session, {KEY_KB_SAG_EVENT_PROMPT_VERSION: "2"})
    invalidate_settings_cache()
    fp_v2, payload = compute_file_fingerprint(db_session, file_row)
    assert fp_v1 != fp_v2
    assert payload["sag_prompt_version"] == 2


def test_acl_fields_match_file_owner(db_session, regular_user, admin_user, tmp_path):
    update_settings(db_session, {KEY_KB_SAG_EVENT_EXTRACT_ENABLED: "true"})
    invalidate_settings_cache()
    ws = ensure_personal_workspace(db_session, regular_user)
    file_row = _add_file(
        db_session,
        regular_user.id,
        tmp_path,
        "sag-acl.txt",
        "md5-sag-acl",
        workspace_id=ws.id,
    )
    _add_chunk(
        db_session,
        regular_user.id,
        file_row.id,
        "Private event text.",
        heading_path="Team/Project",
    )
    rebuild_sag_events_for_file(db_session, file_row)
    db_session.commit()

    event = db_session.query(KbEvent).filter(KbEvent.file_id == file_row.id).one()
    assert event.user_id == regular_user.id
    assert event.workspace_id == ws.id
    assert event.user_id != admin_user.id

    entities = db_session.query(KbEventEntity).filter(KbEventEntity.file_id == file_row.id).all()
    assert entities
    assert all(entity.file_id == file_row.id for entity in entities)
    assert all(entity.workspace_id == ws.id for entity in entities)


def test_delete_sag_events_for_file(db_session, regular_user, tmp_path):
    update_settings(db_session, {KEY_KB_SAG_EVENT_EXTRACT_ENABLED: "true"})
    invalidate_settings_cache()
    file_row = _add_file(db_session, regular_user.id, tmp_path, "sag-del.txt", "md5-sag-del")
    _add_chunk(db_session, regular_user.id, file_row.id, "Delete me.")
    rebuild_sag_events_for_file(db_session, file_row)
    db_session.commit()
    assert db_session.query(KbEvent).filter(KbEvent.file_id == file_row.id).count() == 1

    delete_sag_events_for_file(db_session, file_row.id)
    db_session.commit()
    assert db_session.query(KbEvent).filter(KbEvent.file_id == file_row.id).count() == 0
    assert db_session.query(KbEventEntity).filter(KbEventEntity.file_id == file_row.id).count() == 0


@patch("services.kb_sag_event_extract_service._ollama_chat_json")
def test_ollama_mode_uses_json_extract(mock_ollama, db_session, regular_user, tmp_path):
    mock_ollama.return_value = {
        "title": "Launch Event",
        "summary": "Product launched.",
        "content": "We launched the product in April.",
        "entities": [{"name": "Product X", "type": "concept"}],
    }
    update_settings(
        db_session,
        {
            KEY_KB_SAG_EVENT_EXTRACT_ENABLED: "true",
            KEY_KB_SAG_EVENT_EXTRACT_MODE: "ollama",
        },
    )
    invalidate_settings_cache()
    file_row = _add_file(db_session, regular_user.id, tmp_path, "sag-ollama.txt", "md5-sag-ollama")
    _add_chunk(db_session, regular_user.id, file_row.id, "We launched the product in April.")
    rebuild_sag_events_for_file(db_session, file_row)
    db_session.commit()

    event = db_session.query(KbEvent).filter(KbEvent.file_id == file_row.id).one()
    assert event.extract_layer == "ollama"
    assert event.title == "Launch Event"
    names = {
        row.entity_name
        for row in db_session.query(KbEventEntity).filter(KbEventEntity.file_id == file_row.id)
    }
    assert "Product X" in names
