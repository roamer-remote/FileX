# Copyright (c) 2026 徐泽宇
"""086 KB pipeline visualization read APIs."""

from __future__ import annotations

import os

from fastapi import status

from models.file import File as FileModel
from models.kb_extract_job import KbExtractJob
from models.kb_index_job import KbIndexJob
from services.md_paths import md_note_path
from models.kb_post_job import KbPostJob
from services.kb_pipeline_log_service import (
    ACTION_KB_EXTRACT_DONE,
    ACTION_KB_INDEX_DONE,
    ACTION_KB_INDEX_SKIP,
    ACTION_KB_POST_DONE,
    ACTION_KB_POST_SKIP,
    log_kb_pipeline_event,
)
from services.system_setting_service import (
    KEY_KB_EXTRACT_PROVIDER,
    KEY_KB_INGESTION_PIPELINE_JSON,
    update_settings,
)


def test_admin_topology_requires_admin(client, jwt_token):
    resp = client.get(
        "/api/admin/kb-pipeline/topology",
        headers={"Authorization": f"Bearer {jwt_token}"},
    )
    assert resp.status_code == status.HTTP_403_FORBIDDEN


def test_admin_topology_returns_routes(client, admin_jwt_token, db_session):
    update_settings(
        db_session,
        {
            KEY_KB_INGESTION_PIPELINE_JSON: (
                '{"version":1,"routes":[{"match":{"mime_prefix":"application/pdf"},'
                '"extract_provider":"mineru"}],"stages":{"entity_extract":true,"wiki_lint_on_index":false}}'
            ),
            KEY_KB_EXTRACT_PROVIDER: "legacy",
        },
    )
    resp = client.get(
        "/api/admin/kb-pipeline/topology",
        headers={"Authorization": f"Bearer {admin_jwt_token}"},
    )
    assert resp.status_code == status.HTTP_200_OK
    data = resp.json()
    assert any(node["id"] == "kb_extract" for node in data["nodes"])
    assert data["effective_routes"][0]["extract_provider"] == "mineru"
    assert data["stages"]["entity_extract"] is True
    assert data["global_default_provider"] == "legacy"
    mineru = next(node for node in data["nodes"] if node["id"] == "mineru")
    assert mineru["highlight"] is True
    edge_pairs = {(edge["source"], edge["target"]) for edge in data["edges"]}
    assert ("kb_extract", "mineru") in edge_pairs
    assert ("kb_extract", "docling") in edge_pairs
    assert ("mineru", "docling") not in edge_pairs


def test_file_pipeline_trace_prefers_job_provider_over_current_route(
    client, jwt_token, db_session, regular_user, tmp_path,
):
    file_path = tmp_path / "demo.pdf"
    file_path.write_bytes(b"%PDF-1.4")
    f = FileModel(
        user_id=regular_user.id,
        filename="demo.pdf",
        original_name="demo.pdf",
        file_path=str(file_path),
        file_size=8,
        mime_type="application/pdf",
        extract_status="ready",
        index_status="skipped",
    )
    db_session.add(f)
    db_session.commit()
    db_session.refresh(f)

    job = KbExtractJob(
        user_id=regular_user.id,
        file_id=f.id,
        status="done",
        provider="mineru",
    )
    db_session.add(job)
    db_session.commit()
    db_session.refresh(job)

    resp = client.get(
        f"/api/files/{f.id}/pipeline-trace",
        headers={"Authorization": f"Bearer {jwt_token}"},
    )
    assert resp.status_code == status.HTTP_200_OK
    data = resp.json()
    assert data["trace_provider"] == "mineru"
    assert data["extraction_manifest"] is None
    assert data["extraction_manifest_error"] == "terminal_log_missing"
    extract_step = next(step for step in data["steps"] if step["key"] == "extract")
    assert "provider=mineru" in extract_step["detail"]


def test_file_pipeline_trace_extract_step_shows_actual_engine_on_fast_path(
    client, jwt_token, db_session, regular_user, tmp_path,
):
    """pdf-inspector 快路径接管 mineru 时，正文提取步骤应展示实际 engine 而非仅 provider。"""
    file_path = tmp_path / "fast.pdf"
    file_path.write_bytes(b"%PDF-1.4")
    f = FileModel(
        user_id=regular_user.id,
        filename="fast.pdf",
        original_name="fast.pdf",
        file_path=str(file_path),
        file_size=8,
        mime_type="application/pdf",
        extract_status="ready",
        index_status="skipped",
    )
    db_session.add(f)
    db_session.commit()
    db_session.refresh(f)

    job = KbExtractJob(
        user_id=regular_user.id,
        file_id=f.id,
        status="done",
        provider="mineru",
    )
    db_session.add(job)
    db_session.commit()
    db_session.refresh(job)

    log_kb_pipeline_event(
        db_session,
        regular_user.id,
        ACTION_KB_EXTRACT_DONE,
        f.id,
        detail=(
            f"engine=pdf-inspector index_enqueued=true job_id={job.id} "
            "ocr_engine=none ocr_used=false pdf_class=text_layer "
            "persist_ms=4 provider=mineru provider_ms=1475 side_effects_ms=36 "
            "text_layer_page_count=15"
        ),
    )
    db_session.commit()

    resp = client.get(
        f"/api/files/{f.id}/pipeline-trace",
        headers={"Authorization": f"Bearer {jwt_token}"},
    )
    assert resp.status_code == status.HTTP_200_OK
    data = resp.json()
    assert data["trace_provider"] == "mineru"
    assert data["extraction_manifest"]["status"] == "done"
    assert data["extraction_manifest"]["job_id"] == job.id
    extract_step = next(step for step in data["steps"] if step["key"] == "extract")
    assert "engine=pdf-inspector" in extract_step["detail"]
    assert "provider=mineru" in extract_step["detail"]


def test_file_pipeline_trace_failed_extract_includes_log_link(
    client, jwt_token, db_session, regular_user, tmp_path,
):
    file_path = tmp_path / "bad.pdf"
    file_path.write_bytes(b"%PDF-1.4")
    f = FileModel(
        user_id=regular_user.id,
        filename="bad.pdf",
        original_name="bad.pdf",
        file_path=str(file_path),
        file_size=8,
        mime_type="application/pdf",
        extract_status="failed",
        extract_error="extract boom",
        index_status="skipped",
    )
    db_session.add(f)
    db_session.commit()
    db_session.refresh(f)

    resp = client.get(
        f"/api/files/{f.id}/pipeline-trace",
        headers={"Authorization": f"Bearer {jwt_token}"},
    )
    assert resp.status_code == status.HTTP_200_OK
    extract_step = next(step for step in resp.json()["steps"] if step["key"] == "extract")
    assert extract_step["error_message"] == "extract boom"
    assert extract_step["log_deep_link"] == f"/admin/logs?tab=logs&user_id={regular_user.id}"


def test_file_pipeline_trace_404_when_unreadable(client, jwt_token, db_session, admin_user):
    f = FileModel(
        user_id=admin_user.id,
        filename="secret.pdf",
        original_name="secret.pdf",
        file_path="/tmp/secret.pdf",
        file_size=1,
        mime_type="application/pdf",
    )
    db_session.add(f)
    db_session.commit()
    db_session.refresh(f)

    resp = client.get(
        f"/api/files/{f.id}/pipeline-trace",
        headers={"Authorization": f"Bearer {jwt_token}"},
    )
    assert resp.status_code == status.HTTP_404_NOT_FOUND


def test_file_pipeline_trace_returns_steps(client, jwt_token, db_session, regular_user, tmp_path):
    upload_dir = tmp_path / "uploads"
    upload_dir.mkdir()
    file_path = upload_dir / "demo.pdf"
    file_path.write_bytes(b"%PDF-1.4")

    f = FileModel(
        user_id=regular_user.id,
        filename="demo.pdf",
        original_name="demo.pdf",
        file_path=str(file_path),
        file_size=8,
        mime_type="application/pdf",
        extract_status="ready",
        index_status="ready",
        chunk_count=12,
    )
    db_session.add(f)
    db_session.commit()
    db_session.refresh(f)

    md_path = md_note_path(f.id)
    os.makedirs(os.path.dirname(md_path), exist_ok=True)
    with open(md_path, "w", encoding="utf-8") as handle:
        handle.write("# demo")

    job = KbExtractJob(
        user_id=regular_user.id,
        file_id=f.id,
        status="done",
        provider="mineru",
    )
    db_session.add(job)
    db_session.commit()

    resp = client.get(
        f"/api/files/{f.id}/pipeline-trace",
        headers={"Authorization": f"Bearer {jwt_token}"},
    )
    assert resp.status_code == status.HTTP_200_OK
    data = resp.json()
    assert data["file_id"] == f.id
    assert data["trace_provider"] == "mineru"
    assert data["has_md_notes"] is True
    assert data["chunk_count"] == 12
    keys = [step["key"] for step in data["steps"]]
    assert keys == ["upload", "extract", "notes", "index", "post"]
    extract_step = next(step for step in data["steps"] if step["key"] == "extract")
    assert "mineru" in extract_step["detail"]
    notes_step = next(step for step in data["steps"] if step["key"] == "notes")
    assert notes_step["occurred_at"] is not None
    assert "+08:00" in notes_step["occurred_at"]


def test_file_pipeline_trace_post_running_shows_process(
    client, jwt_token, db_session, regular_user, tmp_path,
):
    file_path = tmp_path / "post.pdf"
    file_path.write_bytes(b"%PDF-1.4")
    f = FileModel(
        user_id=regular_user.id,
        filename="post.pdf",
        original_name="post.pdf",
        file_path=str(file_path),
        file_size=8,
        mime_type="application/pdf",
        extract_status="ready",
        index_status="ready",
        kb_post_status="running",
        chunk_count=5,
    )
    db_session.add(f)
    db_session.commit()

    resp = client.get(
        f"/api/files/{f.id}/pipeline-trace",
        headers={"Authorization": f"Bearer {jwt_token}"},
    )
    assert resp.status_code == status.HTTP_200_OK
    post_step = next(step for step in resp.json()["steps"] if step["key"] == "post")
    assert post_step["status"] == "process"


def test_file_pipeline_trace_notes_occurred_at_fallback_extracted_at(
    client, jwt_token, db_session, regular_user, tmp_path, monkeypatch,
):
    from datetime import datetime

    upload = tmp_path / "uploads"
    upload.mkdir()
    monkeypatch.setattr("services.md_paths.UPLOAD_DIR", str(upload))
    monkeypatch.setattr("config.UPLOAD_DIR", str(upload))

    file_path = upload / "note.png"
    file_path.write_bytes(b"png")
    f = FileModel(
        user_id=regular_user.id,
        filename="note.png",
        original_name="note.png",
        file_path=str(file_path),
        file_size=3,
        mime_type="image/png",
        extract_status="ready",
        index_status="ready",
        has_md=True,
        extracted_at=datetime(2026, 7, 2, 17, 1, 6),
    )
    db_session.add(f)
    db_session.commit()
    db_session.refresh(f)

    resp = client.get(
        f"/api/files/{f.id}/pipeline-trace",
        headers={"Authorization": f"Bearer {jwt_token}"},
    )
    assert resp.status_code == status.HTTP_200_OK
    notes_step = next(step for step in resp.json()["steps"] if step["key"] == "notes")
    assert notes_step["occurred_at"] is not None
    assert "17:01:06" in notes_step["occurred_at"]


def test_file_pipeline_trace_index_perf_from_operation_log(
    client, jwt_token, db_session, regular_user, tmp_path,
):
    file_path = tmp_path / "big.pdf"
    file_path.write_bytes(b"%PDF-1.4")
    f = FileModel(
        user_id=regular_user.id,
        filename="big.pdf",
        original_name="big.pdf",
        file_path=str(file_path),
        file_size=8,
        mime_type="application/pdf",
        extract_status="ready",
        index_status="ready",
        chunk_count=2470,
    )
    db_session.add(f)
    db_session.commit()
    db_session.refresh(f)

    log_kb_pipeline_event(
        db_session,
        regular_user.id,
        ACTION_KB_INDEX_DONE,
        f.id,
        detail=(
            "job_id=1771 chunk_count=2470 source=sidecar_md "
            "embed_ms=984 persist_ms=5509 large_pdf=true"
        ),
    )
    db_session.commit()

    resp = client.get(
        f"/api/files/{f.id}/pipeline-trace",
        headers={"Authorization": f"Bearer {jwt_token}"},
    )
    assert resp.status_code == status.HTTP_200_OK
    index_step = next(step for step in resp.json()["steps"] if step["key"] == "index")
    assert index_step["embed_ms"] == 984
    assert index_step["persist_ms"] == 5509
    assert index_step.get("post_index_ms") is None
    assert index_step["large_pdf"] is True
    assert "embed_ms=984ms" in index_step["detail"]


def test_file_pipeline_trace_index_post_skip_reason(
    client, jwt_token, db_session, regular_user, tmp_path,
):
    file_path = tmp_path / "big.pdf"
    file_path.write_bytes(b"%PDF-1.4")
    f = FileModel(
        user_id=regular_user.id,
        filename="big.pdf",
        original_name="big.pdf",
        file_path=str(file_path),
        file_size=8,
        mime_type="application/pdf",
        extract_status="ready",
        index_status="ready",
        chunk_count=100,
    )
    db_session.add(f)
    db_session.commit()
    db_session.refresh(f)

    post_job = KbPostJob(user_id=regular_user.id, file_id=f.id, status="done")
    db_session.add(post_job)
    db_session.flush()
    f.kb_post_status = "skipped"
    log_kb_pipeline_event(
        db_session,
        regular_user.id,
        ACTION_KB_POST_SKIP,
        f.id,
        detail=f"job_id={post_job.id} post_skip_reason=large_doc_post_skipped",
    )
    db_session.commit()

    resp = client.get(
        f"/api/files/{f.id}/pipeline-trace",
        headers={"Authorization": f"Bearer {jwt_token}"},
    )
    assert resp.status_code == status.HTTP_200_OK
    post_step = next(step for step in resp.json()["steps"] if step["key"] == "post")
    assert post_step["post_skip_reason"] == "large_doc_post_skipped"
    assert "post_skip_reason=large_doc_post_skipped" in post_step["detail"]


def test_file_pipeline_trace_index_post_stage_timings(
    client, jwt_token, db_session, regular_user, tmp_path,
):
    file_path = tmp_path / "big.pdf"
    file_path.write_bytes(b"%PDF-1.4")
    f = FileModel(
        user_id=regular_user.id,
        filename="big.pdf",
        original_name="big.pdf",
        file_path=str(file_path),
        file_size=8,
        mime_type="application/pdf",
        extract_status="ready",
        index_status="ready",
        chunk_count=100,
    )
    db_session.add(f)
    db_session.commit()
    db_session.refresh(f)

    post_job = KbPostJob(user_id=regular_user.id, file_id=f.id, status="done")
    db_session.add(post_job)
    db_session.flush()
    f.kb_post_status = "ready"
    log_kb_pipeline_event(
        db_session,
        regular_user.id,
        ACTION_KB_POST_DONE,
        f.id,
        detail=(
            f"job_id={post_job.id} post_entity_ms=0 post_index_ms=22 "
            "post_raptor_ms=1 post_sag_ms=0 post_skip_reason=large_doc_post_skipped"
        ),
    )
    db_session.commit()

    resp = client.get(
        f"/api/files/{f.id}/pipeline-trace",
        headers={"Authorization": f"Bearer {jwt_token}"},
    )
    assert resp.status_code == status.HTTP_200_OK
    post_step = next(step for step in resp.json()["steps"] if step["key"] == "post")
    assert post_step["post_entity_ms"] == 0
    assert post_step["post_sag_ms"] == 0
    assert post_step["post_raptor_ms"] == 1
    assert post_step["post_index_ms"] == 22
    assert "post_entity_ms=0ms" in post_step["detail"]


def test_file_pipeline_trace_reindex_pending_hides_stale_perf(
    client, jwt_token, db_session, regular_user, tmp_path,
):
    """重新检索排队中：不展示上一轮 KB 索引完成的耗时与 indexed_at。"""
    from datetime import datetime

    file_path = tmp_path / "reindex.pdf"
    file_path.write_bytes(b"%PDF-1.4")
    f = FileModel(
        user_id=regular_user.id,
        filename="reindex.pdf",
        original_name="reindex.pdf",
        file_path=str(file_path),
        file_size=8,
        mime_type="application/pdf",
        extract_status="ready",
        index_status="pending",
        chunk_count=2470,
        indexed_at=datetime(2026, 6, 1, 12, 0, 0),
    )
    db_session.add(f)
    db_session.commit()
    db_session.refresh(f)

    log_kb_pipeline_event(
        db_session,
        regular_user.id,
        ACTION_KB_INDEX_DONE,
        f.id,
        detail="job_id=10 chunk_count=2470 embed_ms=984 persist_ms=5509 post_index_ms=22",
    )
    db_session.add(
        KbIndexJob(
            user_id=regular_user.id,
            file_id=f.id,
            status="queued",
            force=True,
        )
    )
    db_session.commit()
    db_session.refresh(f)
    new_job = (
        db_session.query(KbIndexJob)
        .filter(KbIndexJob.file_id == f.id)
        .order_by(KbIndexJob.id.desc())
        .first()
    )

    resp = client.get(
        f"/api/files/{f.id}/pipeline-trace",
        headers={"Authorization": f"Bearer {jwt_token}"},
    )
    assert resp.status_code == status.HTTP_200_OK
    index_step = next(step for step in resp.json()["steps"] if step["key"] == "index")
    assert index_step["status"] == "process"
    assert index_step["embed_ms"] is None
    assert index_step["persist_ms"] is None
    assert index_step["post_index_ms"] is None
    assert index_step["occurred_at"] is None
    assert f"job_id={new_job.id}" in index_step["detail"]
    assert "job_status=queued" in index_step["detail"]
    assert "force=true" in index_step["detail"]
    assert "embed_ms=" not in index_step["detail"]


def test_file_pipeline_trace_index_perf_matches_latest_done_job(
    client, jwt_token, db_session, regular_user, tmp_path,
):
    file_path = tmp_path / "done.pdf"
    file_path.write_bytes(b"%PDF-1.4")
    f = FileModel(
        user_id=regular_user.id,
        filename="done.pdf",
        original_name="done.pdf",
        file_path=str(file_path),
        file_size=8,
        mime_type="application/pdf",
        extract_status="ready",
        index_status="ready",
        chunk_count=12,
    )
    db_session.add(f)
    db_session.commit()
    db_session.refresh(f)

    log_kb_pipeline_event(
        db_session,
        regular_user.id,
        ACTION_KB_INDEX_DONE,
        f.id,
        detail="job_id=1 chunk_count=12 embed_ms=100",
    )
    job = KbIndexJob(user_id=regular_user.id, file_id=f.id, status="done", force=True)
    db_session.add(job)
    db_session.commit()
    db_session.refresh(job)

    log_kb_pipeline_event(
        db_session,
        regular_user.id,
        ACTION_KB_INDEX_DONE,
        f.id,
        detail=f"job_id={job.id} chunk_count=12 embed_ms=222 persist_ms=333",
    )
    db_session.commit()

    resp = client.get(
        f"/api/files/{f.id}/pipeline-trace",
        headers={"Authorization": f"Bearer {jwt_token}"},
    )
    assert resp.status_code == status.HTTP_200_OK
    index_step = next(step for step in resp.json()["steps"] if step["key"] == "index")
    assert index_step["embed_ms"] == 222
    assert index_step["persist_ms"] == 333
    assert "embed_ms=100" not in index_step["detail"]


def test_file_pipeline_trace_skip_job_does_not_show_prior_done_perf(
    client, jwt_token, db_session, regular_user, tmp_path,
):
    file_path = tmp_path / "skip.pdf"
    file_path.write_bytes(b"%PDF-1.4")
    f = FileModel(
        user_id=regular_user.id,
        filename="skip.pdf",
        original_name="skip.pdf",
        file_path=str(file_path),
        file_size=8,
        mime_type="application/pdf",
        extract_status="ready",
        index_status="ready",
        chunk_count=8,
    )
    db_session.add(f)
    db_session.commit()
    db_session.refresh(f)

    log_kb_pipeline_event(
        db_session,
        regular_user.id,
        ACTION_KB_INDEX_DONE,
        f.id,
        detail="job_id=5 chunk_count=8 embed_ms=999",
    )
    skip_job = KbIndexJob(user_id=regular_user.id, file_id=f.id, status="done")
    db_session.add(skip_job)
    db_session.commit()
    db_session.refresh(skip_job)

    log_kb_pipeline_event(
        db_session,
        regular_user.id,
        ACTION_KB_INDEX_SKIP,
        f.id,
        detail=f"job_id={skip_job.id} reason=manual_override",
    )
    db_session.commit()

    resp = client.get(
        f"/api/files/{f.id}/pipeline-trace",
        headers={"Authorization": f"Bearer {jwt_token}"},
    )
    assert resp.status_code == status.HTTP_200_OK
    index_step = next(step for step in resp.json()["steps"] if step["key"] == "index")
    assert index_step["embed_ms"] is None
    assert "embed_ms=" not in index_step["detail"]
