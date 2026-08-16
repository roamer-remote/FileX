# Copyright (c) 2026 徐泽宇
"""078 P3: GET sag-events / chunk sag-event API + ACL."""

from config import OLLAMA_EMBED_DIM
from models.file import File as FileModel
from models.kb_chunk import KbChunk
from models.kb_event import KbEvent
from models.kb_event_entity import KbEventEntity


def _vec(seed: float) -> list[float]:
    return [seed] * OLLAMA_EMBED_DIM


def _seed_file_with_sag(db_session, user, *, other_user=None):
    owner = user
    f = FileModel(
        filename="sag.md",
        original_name="sag-doc.pdf",
        file_path="/tmp/sag",
        file_size=1,
        mime_type="application/pdf",
        user_id=owner.id,
        index_status="ready",
        chunk_count=2,
    )
    db_session.add(f)
    db_session.commit()
    chunks = []
    for idx, text in enumerate(["alpha chunk body", "beta chunk body"]):
        ch = KbChunk(
            user_id=owner.id,
            file_id=f.id,
            chunk_index=idx,
            source="sidecar_md",
            text=text,
            char_start=0,
            char_end=len(text),
            embedding=_vec(0.1 + idx * 0.1),
            embedding_model="test-model",
        )
        db_session.add(ch)
        db_session.flush()
        chunks.append(ch)
    event = KbEvent(
        user_id=owner.id,
        workspace_id=None,
        file_id=f.id,
        chunk_id=int(chunks[0].id),
        title="Alpha event",
        summary="alpha summary",
        content=chunks[0].text,
        extract_layer="rule",
    )
    db_session.add(event)
    db_session.flush()
    db_session.add(
        KbEventEntity(
            event_id=int(event.id),
            file_id=f.id,
            workspace_id=None,
            entity_name="BridgeEntity",
            entity_type="concept",
        )
    )
    db_session.commit()
    return f, chunks, event


def test_list_sag_events_own_file(client, db_session, regular_user, jwt_token):
    f, chunks, event = _seed_file_with_sag(db_session, regular_user)
    r = client.get(
        f"/api/knowledge-base/files/{f.id}/sag-events",
        headers={"Authorization": f"Bearer {jwt_token}"},
    )
    assert r.status_code == 200
    body = r.json()
    assert body["file_id"] == f.id
    assert body["original_name"] == "sag-doc.pdf"
    assert body["total"] == 1
    assert len(body["items"]) == 1
    item = body["items"][0]
    assert item["id"] == event.id
    assert item["chunk_id"] == chunks[0].id
    assert item["chunk_index"] == 0
    assert item["title"] == "Alpha event"
    assert item["entities"][0]["entity_name"] == "BridgeEntity"


def test_get_chunk_sag_event(client, db_session, regular_user, jwt_token):
    f, chunks, event = _seed_file_with_sag(db_session, regular_user)
    r = client.get(
        f"/api/knowledge-base/files/{f.id}/chunks/{chunks[0].id}/sag-event",
        headers={"Authorization": f"Bearer {jwt_token}"},
    )
    assert r.status_code == 200
    body = r.json()
    assert body["id"] == event.id
    assert body["chunk_index"] == 0
    assert body["summary"] == "alpha summary"


def test_get_chunk_sag_event_missing(client, db_session, regular_user, jwt_token):
    f, chunks, _ = _seed_file_with_sag(db_session, regular_user)
    r = client.get(
        f"/api/knowledge-base/files/{f.id}/chunks/{chunks[1].id}/sag-event",
        headers={"Authorization": f"Bearer {jwt_token}"},
    )
    assert r.status_code == 404


def test_sag_events_404_other_user(client, db_session, regular_user, admin_user, jwt_token):
    f, _, _ = _seed_file_with_sag(db_session, admin_user)
    r_list = client.get(
        f"/api/knowledge-base/files/{f.id}/sag-events",
        headers={"Authorization": f"Bearer {jwt_token}"},
    )
    assert r_list.status_code == 404
    r_get = client.get(
        f"/api/knowledge-base/files/{f.id}/chunks/1/sag-event",
        headers={"Authorization": f"Bearer {jwt_token}"},
    )
    assert r_get.status_code == 404
