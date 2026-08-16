# Copyright (c) 2026 徐泽宇
"""Re-extract with per-job provider override.

Authors:
    徐泽宇

Copyright:
    © 2026 徐泽宇
"""

from unittest.mock import patch

import pytest

from models.file import File as FileModel
from models.kb_extract_job import KbExtractJob
from services.extract.base import ExtractResult
from services.extract.providers.registry import extract_with_provider
from services.kb_extract_service import JOB_QUEUED, enqueue_extract


@pytest.fixture
def pdf_file(db_session, regular_user, tmp_path):
    pdf = tmp_path / "doc.pdf"
    pdf.write_bytes(b"%PDF-1.4")
    f = FileModel(
        filename="doc",
        original_name="doc.pdf",
        file_path=str(pdf),
        file_size=8,
        mime_type="application/pdf",
        user_id=regular_user.id,
        has_md=False,
    )
    db_session.add(f)
    db_session.commit()
    db_session.refresh(f)
    return f


def test_reextract_clears_extract_metadata_on_enqueue(db_session, regular_user, tmp_path, monkeypatch):
    from pathlib import Path
    from services.md_paths import md_note_path

    md_dir = tmp_path / ".md_notes"
    md_dir.mkdir()
    monkeypatch.setattr("services.md_paths.UPLOAD_DIR", str(tmp_path))
    monkeypatch.setattr("services.md_paths.MD_DIR", str(md_dir))
    pdf = tmp_path / "doc.pdf"
    pdf.write_bytes(b"%PDF-1.4")
    f = FileModel(
        filename="doc",
        original_name="doc.pdf",
        file_path=str(pdf),
        file_size=8,
        mime_type="application/pdf",
        user_id=regular_user.id,
        has_md=True,
        extract_engine="mineru",
    )
    db_session.add(f)
    db_session.commit()
    note = Path(md_note_path(f.id))
    note.parent.mkdir(parents=True, exist_ok=True)
    note.write_text("# old\n", encoding="utf-8")
    f.md_file_path = str(note)
    db_session.commit()

    with patch("messaging.kb_extract_publisher.publish_kb_extract_job"):
        job_id = enqueue_extract(
            db_session,
            f.user_id,
            f.id,
            provider="docling",
            for_reextract=True,
            bypass_mineru_cache=True,
        )
    db_session.commit()
    db_session.refresh(f)

    assert job_id is not None
    assert f.extract_engine is None
    assert f.extracted_at is None
    assert f.extract_status in ("pending", "extracting")


def test_enqueue_extract_persists_provider(db_session, pdf_file):
    with patch("messaging.kb_extract_publisher.publish_kb_extract_job"):
        job_id = enqueue_extract(db_session, pdf_file.user_id, pdf_file.id, provider="liteparse")
    db_session.commit()
    assert job_id is not None
    job = db_session.query(KbExtractJob).filter(KbExtractJob.id == job_id).first()
    assert job is not None
    assert job.provider == "liteparse"


@patch("services.extract.providers.registry._legacy_extract")
def test_provider_override_ignores_global(mock_legacy, db_session, regular_user, tmp_path):
    from services.system_setting_service import KEY_KB_EXTRACT_PROVIDER, update_settings

    update_settings(db_session, {KEY_KB_EXTRACT_PROVIDER: "legacy"})
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
    mock_legacy.return_value = ExtractResult(text="legacy", engine="legacy")

    with patch(
        "services.extract.providers.liteparse_provider.extract_liteparse",
        return_value=ExtractResult(text="lp", engine="liteparse+rapidocr"),
    ) as mock_lp:
        r = extract_with_provider(f, db_session, provider_override="liteparse")

    assert r.text == "lp"
    mock_lp.assert_called_once()
    mock_legacy.assert_not_called()


def test_reextract_invalid_provider(client, db_session, regular_user, jwt_token, pdf_file):
    r = client.post(
        f"/api/knowledge-base/files/{pdf_file.id}/reextract",
        json={"provider": "unknown-engine"},
        headers={"Authorization": f"Bearer {jwt_token}"},
    )
    assert r.status_code == 400


def test_reextract_stores_mineru_provider(client, db_session, regular_user, jwt_token, pdf_file):
    with patch("services.kb_extract_service.publish_extract_job") as mock_pub:
        r = client.post(
            f"/api/knowledge-base/files/{pdf_file.id}/reextract",
            json={"provider": "mineru", "force": True},
            headers={"Authorization": f"Bearer {jwt_token}"},
        )
    assert r.status_code == 200
    mock_pub.assert_called_once()
    job = (
        db_session.query(KbExtractJob)
        .filter(KbExtractJob.file_id == pdf_file.id, KbExtractJob.status == JOB_QUEUED)
        .order_by(KbExtractJob.id.desc())
        .first()
    )
    assert job is not None
    assert job.provider == "mineru"


def test_reextract_stores_docling_provider(client, db_session, regular_user, jwt_token, pdf_file):
    with patch("services.kb_extract_service.publish_extract_job") as mock_pub:
        r = client.post(
            f"/api/knowledge-base/files/{pdf_file.id}/reextract",
            json={"provider": "docling"},
            headers={"Authorization": f"Bearer {jwt_token}"},
        )
    assert r.status_code == 200
    mock_pub.assert_called_once()
    job = (
        db_session.query(KbExtractJob)
        .filter(KbExtractJob.file_id == pdf_file.id, KbExtractJob.status == JOB_QUEUED)
        .order_by(KbExtractJob.id.desc())
        .first()
    )
    assert job is not None
    assert job.provider == "docling"


def test_reextract_stores_insavlo_provider(client, db_session, regular_user, jwt_token, pdf_file):
    with patch("services.kb_extract_service.publish_extract_job") as mock_pub:
        r = client.post(
            f"/api/knowledge-base/files/{pdf_file.id}/reextract",
            json={"provider": "insavlo"},
            headers={"Authorization": f"Bearer {jwt_token}"},
        )
    assert r.status_code == 200
    mock_pub.assert_called_once()
    job = (
        db_session.query(KbExtractJob)
        .filter(KbExtractJob.file_id == pdf_file.id, KbExtractJob.status == JOB_QUEUED)
        .order_by(KbExtractJob.id.desc())
        .first()
    )
    assert job is not None
    assert job.provider == "insavlo"


def test_reextract_stores_provider_on_job(client, db_session, regular_user, jwt_token, pdf_file):
    with patch("services.kb_extract_service.publish_extract_job") as mock_pub:
        r = client.post(
            f"/api/knowledge-base/files/{pdf_file.id}/reextract",
            json={"provider": "legacy"},
            headers={"Authorization": f"Bearer {jwt_token}"},
        )
    assert r.status_code == 200
    mock_pub.assert_called_once()
    job = (
        db_session.query(KbExtractJob)
        .filter(KbExtractJob.file_id == pdf_file.id, KbExtractJob.status == JOB_QUEUED)
        .order_by(KbExtractJob.id.desc())
        .first()
    )
    assert job is not None
    assert job.provider == "legacy"

def test_reextract_without_provider_uses_effective_default(client, db_session, regular_user, jwt_token, pdf_file):
    from services.system_setting_service import KEY_KB_EXTRACT_PROVIDER, update_settings

    update_settings(db_session, {KEY_KB_EXTRACT_PROVIDER: "mineru"})
    with patch("services.kb_extract_service.publish_extract_job") as mock_pub:
        r = client.post(
            f"/api/knowledge-base/files/{pdf_file.id}/reextract",
            json={},
            headers={"Authorization": f"Bearer {jwt_token}"},
        )
    assert r.status_code == 200
    mock_pub.assert_called_once()
    job = (
        db_session.query(KbExtractJob)
        .filter(KbExtractJob.file_id == pdf_file.id, KbExtractJob.status == JOB_QUEUED)
        .order_by(KbExtractJob.id.desc())
        .first()
    )
    assert job is not None
    assert job.provider is None


def test_reextract_without_provider_creates_mineru_route_when_default_is_mineru(
    client, db_session, regular_user, jwt_token, pdf_file
):
    from services.system_setting_service import KEY_KB_EXTRACT_PROVIDER, update_settings
    from models.gpu_scheduler import GpuSchedulerOutbox

    update_settings(db_session, {KEY_KB_EXTRACT_PROVIDER: "mineru"})
    with patch("services.kb_extract_service.publish_extract_job") as mock_pub:
        r = client.post(
            f"/api/knowledge-base/files/{pdf_file.id}/reextract",
            json={},
            headers={"Authorization": f"Bearer {jwt_token}"},
        )
    assert r.status_code == 200
    mock_pub.assert_called_once()
    job = (
        db_session.query(KbExtractJob)
        .filter(KbExtractJob.file_id == pdf_file.id, KbExtractJob.status == JOB_QUEUED)
        .order_by(KbExtractJob.id.desc())
        .first()
    )
    assert job is not None
    # 运行时默认语义保持不变：job.provider 仍为 None，但必须建立 mineru durable route。
    assert job.provider is None
    route = (
        db_session.query(GpuSchedulerOutbox)
        .filter_by(job_kind="mineru", job_id=str(job.id))
        .first()
    )
    assert route is not None
    assert route.state == "queued"


def test_reextract_explicit_overrides_pipeline_and_settings(db_session, regular_user, tmp_path):
    from services.system_setting_service import (
        KEY_KB_EXTRACT_PROVIDER,
        KEY_KB_INGESTION_PIPELINE_JSON,
        invalidate_settings_cache,
        update_settings,
    )

    update_settings(
        db_session,
        {
            KEY_KB_EXTRACT_PROVIDER: "mineru",
            KEY_KB_INGESTION_PIPELINE_JSON: (
                '{"version":1,"routes":[{"match":{"mime_prefix":"application/pdf"},'
                '"extract_provider":"mineru"}]}'
            ),
        },
    )
    invalidate_settings_cache()
    pdf = tmp_path / "doc.pdf"
    pdf.write_bytes(b"%PDF-1.4")
    f = FileModel(
        filename="doc",
        original_name="doc.pdf",
        file_path=str(pdf),
        file_size=8,
        mime_type="application/pdf",
        user_id=regular_user.id,
        has_md=False,
    )
    db_session.add(f)
    db_session.commit()

    with patch("messaging.kb_extract_publisher.publish_kb_extract_job"):
        job_id = enqueue_extract(
            db_session,
            f.user_id,
            f.id,
            provider="docling",
            for_reextract=True,
        )
    assert job_id is not None
    job = db_session.get(KbExtractJob, job_id)
    assert job is not None
    assert job.provider == "docling"


def test_should_force_index_after_force_reextract(db_session, pdf_file):
    from services.kb_index_service import should_force_index_after_extract

    job = KbExtractJob(user_id=pdf_file.user_id, file_id=pdf_file.id, bypass_mineru_cache=True)
    assert should_force_index_after_extract(pdf_file, job) is True


def test_should_force_index_when_reextract_on_indexed_file(db_session, pdf_file):
    from services.kb_index_service import should_force_index_after_extract

    pdf_file.chunk_count = 12
    pdf_file.index_pipeline_fingerprint = "deadbeef"
    job = KbExtractJob(user_id=pdf_file.user_id, file_id=pdf_file.id, provider="mineru")
    assert should_force_index_after_extract(pdf_file, job) is True


def test_should_not_force_index_on_first_extract(db_session, pdf_file):
    from services.kb_index_service import should_force_index_after_extract

    job = KbExtractJob(user_id=pdf_file.user_id, file_id=pdf_file.id, provider="mineru")
    assert should_force_index_after_extract(pdf_file, job) is False


@patch("services.kb_index_service.publish_index_job")
@patch("services.extract.providers.registry.extract_with_provider")
def test_run_extract_job_reextract_enqueues_force_index(
    mock_extract, _mock_publish, db_session, regular_user, tmp_path, monkeypatch
):
    from services.kb_extract_service import run_extract_job
    from services.kb_index_service import STATUS_READY
    from models.kb_index_job import KbIndexJob

    md_dir = tmp_path / ".md_notes"
    md_dir.mkdir()
    monkeypatch.setattr("services.md_paths.UPLOAD_DIR", str(tmp_path))
    monkeypatch.setattr("services.md_paths.MD_DIR", str(md_dir))
    pdf = tmp_path / "doc.pdf"
    pdf.write_bytes(b"%PDF-1.4")
    f = FileModel(
        filename="doc",
        original_name="doc.pdf",
        file_path=str(pdf),
        file_size=8,
        mime_type="application/pdf",
        user_id=regular_user.id,
        has_md=True,
        chunk_count=5,
        index_status=STATUS_READY,
        index_pipeline_fingerprint="abc123",
        kb_index_manual_override=True,
    )
    db_session.add(f)
    db_session.commit()
    job = KbExtractJob(
        user_id=f.user_id,
        file_id=f.id,
        status=JOB_QUEUED,
        provider="mineru",
        bypass_mineru_cache=True,
    )
    db_session.add(job)
    db_session.commit()

    mock_extract.return_value = ExtractResult(text="# new note\n\ncontent", engine="mineru")

    run_extract_job(db_session, job)

    index_job = (
        db_session.query(KbIndexJob)
        .filter(KbIndexJob.file_id == f.id)
        .order_by(KbIndexJob.id.desc())
        .first()
    )
    assert index_job is not None
    assert index_job.force is True
    db_session.refresh(f)
    assert f.kb_index_manual_override is False
    assert f.index_pipeline_fingerprint is None
