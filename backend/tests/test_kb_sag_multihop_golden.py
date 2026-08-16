# Copyright (c) 2026 徐泽宇
"""078 P3: synthetic multi-hop golden for expand_sag_events."""

from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import patch

from config import OLLAMA_EMBED_DIM
from models.file import File as FileModel
from models.kb_event import KbEvent
from models.kb_event_entity import KbEventEntity
from services.kb_sag_search_service import expand_search_items_with_sag_events
from services.kb_search_service import search_kb
from services.system_setting_service import (
    KEY_KB_SEARCH_HYBRID_ENABLED,
    KEY_KB_SEARCH_MIN_SCORE,
    KEY_KB_SAG_QUERY_LLM_ENABLED,
    invalidate_settings_cache,
    update_settings,
)
from services.workspace_service import ensure_personal_workspace
from tests.helpers.kb_chunk_seed import create_kb_chunk

_GOLDEN = Path(__file__).resolve().parent / "fixtures" / "kb_sag_multihop_golden_cases.json"


def _vec(seed: float) -> list[float]:
    v = [0.0] * OLLAMA_EMBED_DIM
    v[0] = seed
    v[1] = max(1.0 - abs(seed), 0.05)
    n = (v[0] ** 2 + v[1] ** 2) ** 0.5
    v[0] /= n
    v[1] /= n
    return v


def _add_source(db_session, user_id, tmp_path, name, md5, *, workspace_id):
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
        has_md=False,
        index_status="ready",
        page_kind="source",
        publish_status="published",
        workspace_id=workspace_id,
    )
    db_session.add(file_row)
    db_session.commit()
    db_session.refresh(file_row)
    return file_row


def _add_chunk(db_session, user_id, file_id, text, *, chunk_index=0, seed=0.5, workspace_id):
    chunk = create_kb_chunk(
        db_session,
        user_id=user_id,
        workspace_id=workspace_id,
        file_id=file_id,
        chunk_index=chunk_index,
        source="sidecar_md",
        text=text,
        char_start=0,
        char_end=len(text),
        embedding=_vec(seed),
    )
    db_session.commit()
    db_session.refresh(chunk)
    return chunk


def _add_sag_event(db_session, *, user_id, workspace_id, file_id, chunk, title, entities):
    event = KbEvent(
        user_id=user_id,
        workspace_id=workspace_id,
        file_id=file_id,
        chunk_id=int(chunk.id),
        title=title,
        summary=chunk.text[:200],
        content=chunk.text,
        extract_layer="rule",
    )
    db_session.add(event)
    db_session.flush()
    for entity_name, entity_type in entities:
        db_session.add(
            KbEventEntity(
                event_id=int(event.id),
                file_id=file_id,
                workspace_id=workspace_id,
                entity_name=entity_name,
                entity_type=entity_type,
            )
        )
    db_session.commit()
    return event


@patch("services.kb_search_service.embed_text")
def test_sag_multihop_golden_cases(mock_embed, db_session, regular_user, tmp_path):
    if not _GOLDEN.is_file():
        import pytest

        pytest.skip("no multihop golden fixture")
    cases = json.loads(_GOLDEN.read_text(encoding="utf-8"))
    update_settings(
        db_session,
        {
            KEY_KB_SEARCH_HYBRID_ENABLED: "false",
            KEY_KB_SEARCH_MIN_SCORE: "0.35",
            KEY_KB_SAG_QUERY_LLM_ENABLED: "false",
        },
    )
    invalidate_settings_cache()
    mock_embed.return_value = _vec(0.5)
    personal = ensure_personal_workspace(db_session, regular_user)

    for case in cases:
        query = case["query"]
        bridge = case["bridge_entity"]
        expect_sub = case["expect_expanded_chunk_contains"]
        file_row = _add_source(
            db_session,
            regular_user.id,
            tmp_path,
            f"{case['id']}.md",
            (case["id"] * 8)[:32].ljust(32, "a"),
            workspace_id=personal.id,
        )
        chunk_a = _add_chunk(
            db_session,
            regular_user.id,
            file_row.id,
            f"{query} seed chunk",
            chunk_index=0,
            seed=0.95,
            workspace_id=personal.id,
        )
        chunk_b = _add_chunk(
            db_session,
            regular_user.id,
            file_row.id,
            f"{bridge} {expect_sub} target chunk",
            chunk_index=1,
            seed=0.35,
            workspace_id=personal.id,
        )
        _add_sag_event(
            db_session,
            user_id=regular_user.id,
            workspace_id=personal.id,
            file_id=file_row.id,
            chunk=chunk_a,
            title="Alpha",
            entities=[(bridge, "concept")],
        )
        _add_sag_event(
            db_session,
            user_id=regular_user.id,
            workspace_id=personal.id,
            file_id=file_row.id,
            chunk=chunk_b,
            title="Beta",
            entities=[(bridge, "concept")],
        )

        primary, _, _, _ = search_kb(
            db_session,
            regular_user.id,
            query,
            workspace_id=personal.id,
            file_ids=[file_row.id],
            top_k=3,
            group_by_file=False,
        )
        primary = [row for row in primary if int(row["chunk_id"]) == chunk_a.id]
        assert len(primary) == 1, case["id"]

        merged, meta = expand_search_items_with_sag_events(
            db_session,
            regular_user,
            query,
            primary,
            allowed_file_ids={file_row.id},
            top_k=5,
            group_by_file=False,
        )
        assert meta["sag_expanded"] is True, case["id"]
        chunk_ids = {int(row["chunk_id"]) for row in merged if row.get("chunk_id") is not None}
        assert chunk_b.id in chunk_ids, case["id"]
