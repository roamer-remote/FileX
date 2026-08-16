"""187-P2 T-1: correction overlay lifecycle and idempotency contract."""

import hashlib
import pytest
from concurrent.futures import ThreadPoolExecutor
from uuid import uuid4

from models.file import File
from models.kb_index_job import KbIndexJob
from models.kb_chunk import KbChunk
from models.user import User
from database import SessionLocal
from services.auth_service import create_access_token
from services.kb_correction_overlay_service import (
    create_correction_overlay,
    queue_correction_overlay_reindex,
    complete_correction_overlay_reindex,
    transition_correction_overlay,
)
from services.kb_index_service import resolve_index_job_text


def test_overlay_is_idempotent_and_preserves_original_source(db_session, regular_user):
    file = File(
        user_id=regular_user.id,
        filename="source.md",
        original_name="source.md",
        file_path="source.md",
        file_size=12,
        mime_type="text/markdown",
        index_source_hash="source-hash-v1",
    )
    db_session.add(file)
    db_session.commit()

    first = create_correction_overlay(
        db_session,
        file_id=file.id,
        source_hash="source-hash-v1",
        overlay_version=1,
        actor_id=regular_user.id,
        workspace_id=file.workspace_id,
        content="corrected text",
        reason="fix typo",
        idempotency_key="overlay-request-1",
    )
    second = create_correction_overlay(
        db_session,
        file_id=file.id,
        source_hash="source-hash-v1",
        overlay_version=1,
        actor_id=regular_user.id,
        workspace_id=file.workspace_id,
        content="corrected text",
        reason="fix typo",
        idempotency_key="overlay-request-1",
    )

    assert first.id == second.id
    assert first.state == "DRAFT"
    assert first.source_hash == file.index_source_hash
    assert first.content_hash


def test_overlay_state_machine_rejects_invalid_transition(db_session, regular_user):
    file = File(
        user_id=regular_user.id,
        filename="source-2.md",
        original_name="source-2.md",
        file_path="source-2.md",
        file_size=12,
        mime_type="text/markdown",
        index_source_hash="source-hash-v1",
    )
    db_session.add(file)
    db_session.commit()
    overlay = create_correction_overlay(
        db_session,
        file_id=file.id,
        source_hash="source-hash-v1",
        overlay_version=1,
        actor_id=regular_user.id,
        workspace_id=file.workspace_id,
        content="corrected text",
        reason="fix typo",
        idempotency_key="overlay-request-2",
    )

    transition_correction_overlay(db_session, overlay.id, "ACTIVE")
    with pytest.raises(ValueError, match="invalid correction overlay transition"):
        transition_correction_overlay(db_session, overlay.id, "DRAFT")


def test_overlay_rejects_stale_original_source_hash(db_session, regular_user):
    file = File(
        user_id=regular_user.id,
        filename="source-3.md",
        original_name="source-3.md",
        file_path="source-3.md",
        file_size=12,
        mime_type="text/markdown",
        index_source_hash="source-hash-v1",
    )
    db_session.add(file)
    db_session.commit()

    with pytest.raises(ValueError, match="source hash does not match"):
        create_correction_overlay(
            db_session,
            file_id=file.id,
            source_hash="stale-hash",
            overlay_version=1,
            actor_id=regular_user.id,
            workspace_id=file.workspace_id,
            content="corrected text",
            reason="fix typo",
            idempotency_key="overlay-request-3",
        )


def test_overlay_write_requires_file_owner_or_admin(db_session, regular_user, admin_user):
    file = File(
        user_id=admin_user.id,
        filename="source-6.md",
        original_name="source-6.md",
        file_path="source-6.md",
        file_size=12,
        mime_type="text/markdown",
        index_source_hash="source-hash-v1",
    )
    db_session.add(file)
    db_session.commit()

    with pytest.raises(ValueError, match="overlay write requires file owner or admin"):
        create_correction_overlay(
            db_session,
            file_id=file.id,
            source_hash="source-hash-v1",
            overlay_version=1,
            actor_id=regular_user.id,
            workspace_id=file.workspace_id,
            content="corrected text",
            reason="fix typo",
            idempotency_key="overlay-request-6",
        )


def test_overlay_reindex_is_idempotent_and_failure_keeps_overlay_active(db_session, regular_user):
    file = File(
        user_id=regular_user.id,
        filename="source-4.md",
        original_name="source-4.md",
        file_path="source-4.md",
        file_size=12,
        mime_type="text/markdown",
        index_source_hash="source-hash-v1",
    )
    db_session.add(file)
    db_session.commit()
    overlay = create_correction_overlay(
        db_session,
        file_id=file.id,
        source_hash="source-hash-v1",
        overlay_version=1,
        actor_id=regular_user.id,
        workspace_id=file.workspace_id,
        content="corrected text",
        reason="fix typo",
        idempotency_key="overlay-request-4",
    )
    transition_correction_overlay(db_session, overlay.id, "ACTIVE")

    first = queue_correction_overlay_reindex(db_session, overlay.id, strategy_version="p2-v1")
    second = queue_correction_overlay_reindex(db_session, overlay.id, strategy_version="p2-v1")
    assert first.id == second.id
    assert first.status == "queued"
    assert first.correction_overlay_id == overlay.id
    assert first.request_key == f"overlay:{overlay.id}:p2-v1"

    complete_correction_overlay_reindex(db_session, overlay.id, success=False, error="worker failed")
    db_session.refresh(overlay)
    assert overlay.state == "ACTIVE"
    assert overlay.reindex_status == "FAILED"
    assert db_session.get(type(first), first.id).status == "error"


def test_revoking_overlay_cancels_queued_reindex(db_session, regular_user):
    file = File(
        user_id=regular_user.id,
        filename="source-5.md",
        original_name="source-5.md",
        file_path="source-5.md",
        file_size=12,
        mime_type="text/markdown",
        index_source_hash="source-hash-v1",
    )
    db_session.add(file)
    db_session.commit()
    overlay = create_correction_overlay(
        db_session,
        file_id=file.id,
        source_hash="source-hash-v1",
        overlay_version=1,
        actor_id=regular_user.id,
        workspace_id=file.workspace_id,
        content="corrected text",
        reason="fix typo",
        idempotency_key="overlay-request-5",
    )
    transition_correction_overlay(db_session, overlay.id, "ACTIVE")
    job = queue_correction_overlay_reindex(db_session, overlay.id, strategy_version="p2-v1")

    transition_correction_overlay(db_session, overlay.id, "REVOKED")
    db_session.refresh(overlay)
    assert overlay.reindex_status == "CANCELLED"
    assert db_session.get(type(job), job.id).status == "cancelled"


def test_correction_api_enforces_acl_and_returns_reindex_contract(client, db_session, regular_user, admin_user):
    file = File(
        user_id=admin_user.id,
        filename="source-api.md",
        original_name="source-api.md",
        file_path="source-api.md",
        file_size=12,
        mime_type="text/markdown",
        index_source_hash="source-hash-v1",
    )
    db_session.add(file)
    db_session.commit()
    owner_headers = {
        "Authorization": f"Bearer {create_access_token(admin_user.id, admin_user.password_rev)}"
    }
    denied_headers = {
        "Authorization": f"Bearer {create_access_token(regular_user.id, regular_user.password_rev)}"
    }

    denied = client.post(
        f"/api/knowledge-base/files/{file.id}/corrections",
        headers=denied_headers,
        json={
            "source_hash": "source-hash-v1",
            "content": "corrected text",
            "reason": "fix typo",
            "idempotency_key": "api-overlay-denied",
        },
    )
    assert denied.status_code == 404

    created = client.post(
        f"/api/knowledge-base/files/{file.id}/corrections",
        headers=owner_headers,
        json={
            "source_hash": "source-hash-v1",
            "content": "corrected text",
            "reason": "fix typo",
            "idempotency_key": "api-overlay-1",
        },
    )
    assert created.status_code == 200, created.text
    assert created.json()["state"] == "DRAFT"
    overlay_id = created.json()["id"]
    activated = client.post(
        f"/api/knowledge-base/corrections/{overlay_id}/activate",
        headers=owner_headers,
    )
    assert activated.status_code == 200, activated.text
    assert activated.json()["state"] == "ACTIVE"
    queued = client.post(
        f"/api/knowledge-base/corrections/{overlay_id}/reindex",
        headers=owner_headers,
        json={"strategy_version": "p2-v1"},
    )
    assert queued.status_code == 200, queued.text
    queued_again = client.post(
        f"/api/knowledge-base/corrections/{overlay_id}/reindex",
        headers=owner_headers,
        json={"strategy_version": "p2-v1"},
    )
    assert queued_again.status_code == 200, queued_again.text
    assert queued_again.json()["job_id"] == queued.json()["job_id"]
    assert db_session.get(KbIndexJob, queued.json()["job_id"]).user_id == admin_user.id


def test_overlay_index_job_uses_overlay_content(db_session, regular_user):
    file = File(
        user_id=regular_user.id,
        filename="source-content.md",
        original_name="source-content.md",
        file_path="source-content.md",
        file_size=12,
        mime_type="text/markdown",
        index_source_hash="source-hash-v1",
    )
    db_session.add(file)
    db_session.commit()
    overlay = create_correction_overlay(
        db_session,
        file_id=file.id,
        source_hash="source-hash-v1",
        overlay_version=1,
        actor_id=regular_user.id,
        workspace_id=file.workspace_id,
        content="overlay-only content",
        reason="fix typo",
        idempotency_key="overlay-content-1",
    )
    transition_correction_overlay(db_session, overlay.id, "ACTIVE")
    job = queue_correction_overlay_reindex(db_session, overlay.id, strategy_version="p2-v1")

    text, source = resolve_index_job_text(db_session, file, job)
    assert text == "overlay-only content"
    assert source == "correction_overlay"


def test_overlay_consumer_failure_rolls_back_old_chunks(db_session, regular_user, monkeypatch):
    from messaging.kb_index_consumer import _handle_job

    worker_db = SessionLocal()
    from services.workspace_service import ensure_personal_workspace

    owner = User(
        username=f"overlay-worker-{regular_user.id}",
        password_hash="test-password-hash",
        password_rev=0,
        primary_department_id=regular_user.primary_department_id,
    )
    worker_db.add(owner)
    worker_db.flush()
    workspace = ensure_personal_workspace(worker_db, owner)
    worker_db.commit()
    file = File(
        user_id=owner.id,
        filename="source-rollback.md",
        original_name="source-rollback.md",
        file_path="source-rollback.md",
        file_size=12,
        mime_type="text/markdown",
        workspace_id=workspace.id,
        index_source_hash="source-hash-v1",
        source_sha256=hashlib.sha256(b"old source").hexdigest(),
        index_status="ready",
        chunk_count=1,
    )
    worker_db.add(file)
    worker_db.flush()
    old_chunk = KbChunk(
        user_id=owner.id,
        workspace_id=file.workspace_id,
        file_id=file.id,
        chunk_index=0,
        source="old",
        text="old indexed content",
        char_start=0,
        char_end=20,
    )
    worker_db.add(old_chunk)
    worker_db.commit()
    overlay = create_correction_overlay(
        worker_db,
        file_id=file.id,
        source_hash=file.source_sha256,
        overlay_version=1,
        actor_id=owner.id,
        workspace_id=file.workspace_id,
        content="new indexed content",
        reason="fix typo",
        idempotency_key="overlay-rollback-1",
    )
    transition_correction_overlay(worker_db, overlay.id, "ACTIVE")
    job = queue_correction_overlay_reindex(
        worker_db,
        overlay.id,
        strategy_id="parent-child",
        strategy_version="parent-child-v1",
    )
    assert job.strategy_id == "parent-child"
    assert job.strategy_version == "parent-child-v1"
    job_id = job.id

    def fake_run(db, job_obj, *, effective=None, resume_after_deadlock=False):
        db.query(KbChunk).filter(KbChunk.file_id == job_obj.file_id).delete()
        job_obj.status = "error"
        job_obj.last_error = "synthetic embed failure"

    monkeypatch.setattr("messaging.kb_index_consumer.run_index_job", fake_run)
    monkeypatch.setattr(
        "messaging.kb_index_consumer.reconcile_superseded_running_jobs",
        lambda *args, **kwargs: False,
    )
    monkeypatch.setattr("messaging.kb_index_consumer.publish_kb_index_retry", lambda *args, **kwargs: None)
    monkeypatch.setattr("messaging.kb_index_consumer.publish_file_index_notify", lambda *args, **kwargs: None)
    try:
        _handle_job(worker_db, job_id)
        assert worker_db.query(KbChunk).filter(KbChunk.id == old_chunk.id).count() == 1
        worker_overlay = worker_db.get(type(overlay), overlay.id)
        assert worker_overlay.reindex_status == "FAILED"
    finally:
        worker_db.close()


def test_overlay_reindex_concurrent_requests_create_one_job(regular_user):
    from services.workspace_service import ensure_personal_workspace

    setup_db = SessionLocal()
    try:
        owner = User(
            username=f"overlay-race-{uuid4().hex[:12]}",
            password_hash="test-password-hash",
            password_rev=0,
            primary_department_id=regular_user.primary_department_id,
        )
        setup_db.add(owner)
        setup_db.flush()
        workspace = ensure_personal_workspace(setup_db, owner)
        file = File(
            user_id=owner.id,
            workspace_id=workspace.id,
            filename="source-race.md",
            original_name="source-race.md",
            file_path="source-race.md",
            file_size=12,
            mime_type="text/markdown",
            index_source_hash="source-hash-v1",
        )
        setup_db.add(file)
        setup_db.flush()
        overlay = create_correction_overlay(
            setup_db,
            file_id=file.id,
            source_hash="source-hash-v1",
            overlay_version=1,
            actor_id=owner.id,
            workspace_id=workspace.id,
            content="race content",
            reason="fix typo",
            idempotency_key=f"overlay-race-{uuid4().hex}",
        )
        transition_correction_overlay(setup_db, overlay.id, "ACTIVE")
        overlay_id = overlay.id
    finally:
        setup_db.close()

    def submit_one() -> int:
        db = SessionLocal()
        try:
            return queue_correction_overlay_reindex(
                db,
                overlay_id,
                strategy_version="p2-race-v1",
            ).id
        finally:
            db.close()

    with ThreadPoolExecutor(max_workers=2) as pool:
        results = list(pool.map(lambda _item: submit_one(), range(2)))

    verify_db = SessionLocal()
    try:
        assert len(set(results)) == 1
        assert verify_db.query(KbIndexJob).filter(
            KbIndexJob.request_key == f"overlay:{overlay_id}:p2-race-v1"
        ).count() == 1
    finally:
        verify_db.close()


def test_overlay_index_success_atomically_replaces_old_chunk(
    db_session,
    regular_user,
    tmp_path,
    monkeypatch,
):
    from config import OLLAMA_EMBED_DIM
    from services.kb_index_service import run_index_job

    source_path = tmp_path / "source-success.md"
    source_path.write_text("original content", encoding="utf-8")
    file = File(
        user_id=regular_user.id,
        filename="source-success.md",
        original_name="source-success.md",
        file_path=str(source_path),
        file_size=16,
        mime_type="text/markdown",
        has_md=True,
        md_file_path=str(source_path),
        source_sha256=hashlib.sha256(b"original content").hexdigest(),
        index_source_hash="source-hash-v1",
        index_status="ready",
        chunk_count=1,
    )
    db_session.add(file)
    db_session.flush()
    old_chunk = KbChunk(
        user_id=regular_user.id,
        workspace_id=file.workspace_id,
        file_id=file.id,
        chunk_index=0,
        source="old",
        text="old indexed content",
        char_start=0,
        char_end=20,
    )
    db_session.add(old_chunk)
    db_session.commit()
    overlay = create_correction_overlay(
        db_session,
        file_id=file.id,
        source_hash=file.source_sha256,
        overlay_version=1,
        actor_id=regular_user.id,
        workspace_id=file.workspace_id,
        content="corrected overlay content",
        reason="fix typo",
        idempotency_key="overlay-success-1",
    )
    transition_correction_overlay(db_session, overlay.id, "ACTIVE")
    job = queue_correction_overlay_reindex(
        db_session,
        overlay.id,
        strategy_id="parent-child",
        strategy_version="parent-child-v1",
    )

    monkeypatch.setattr("services.kb_index_service._notify_file_index", lambda *args, **kwargs: None)
    monkeypatch.setattr(
        "services.kb_embed_cache_service.embed_texts",
        lambda texts, **kwargs: [[0.02] * OLLAMA_EMBED_DIM for _ in texts],
    )
    run_index_job(db_session, job)
    db_session.commit()
    db_session.refresh(overlay)

    assert job.status == "done"
    assert overlay.reindex_status == "SUCCEEDED"
    chunks = db_session.query(KbChunk).filter(KbChunk.file_id == file.id).all()
    assert chunks
    assert all(chunk.text != "old indexed content" for chunk in chunks)
    assert any("corrected overlay content" in chunk.text for chunk in chunks)
    assert all(chunk.content_meta["strategy_provenance"]["source_hash"] == file.source_sha256 for chunk in chunks)
    roles = {chunk.content_meta["strategy_provenance"]["strategy"]["id"] for chunk in chunks}
    assert roles == {"parent-child"}
    child_chunks = [
        chunk for chunk in chunks
        if chunk.content_meta["strategy_provenance"]["parent_chunk_id"]
    ]
    assert child_chunks
