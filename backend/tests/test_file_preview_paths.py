# Copyright (c) 2026 徐泽宇
"""Preview/download stream paths when DB stores host absolute uploads paths."""

from __future__ import annotations

from models.file import File as FileModel
from messaging.kb_extract_publisher import file_extract_notify_payload
from services.file_response import file_to_schema


PPTX_MIME = "application/vnd.openxmlformats-officedocument.presentationml.presentation"


def test_download_rebases_host_file_path(client, db_session, regular_user, jwt_token, tmp_path, monkeypatch):
    upload = tmp_path / "uploads"
    user_dir = upload / "1" / "2026-06"
    user_dir.mkdir(parents=True)
    pdf = user_dir / "abc_test.pdf"
    pdf.write_bytes(b"%PDF-1.4 minimal")

    monkeypatch.setattr("services.md_paths.UPLOAD_DIR", str(upload))

    f = FileModel(
        filename="abc_test.pdf",
        original_name="report.pdf",
        file_path="/Users/host/FileX/backend/uploads/1/2026-06/abc_test.pdf",
        file_size=pdf.stat().st_size,
        mime_type="application/pdf",
        user_id=regular_user.id,
    )
    db_session.add(f)
    db_session.commit()
    db_session.refresh(f)

    download = client.get(f"/api/files/{f.id}/download", params={"token": jwt_token})
    assert download.status_code == 200
    assert download.content == pdf.read_bytes()

    preview = client.get(f"/api/files/{f.id}/preview", params={"token": jwt_token})
    assert preview.status_code == 200
    assert preview.content == pdf.read_bytes()


def make_pptx_record(db_session, regular_user, src):
    f = FileModel(
        filename=src.name,
        original_name=src.name,
        file_path=str(src),
        file_size=src.stat().st_size,
        mime_type=PPTX_MIME,
        user_id=regular_user.id,
    )
    db_session.add(f)
    db_session.commit()
    db_session.refresh(f)
    return f


def test_pptx_preview_streams_pdf_while_download_keeps_original(
    client, db_session, regular_user, jwt_token, tmp_path, monkeypatch
):
    pptx = tmp_path / "deck.pptx"
    pptx.write_bytes(b"original-pptx")
    converted = tmp_path / "converted.pdf"
    converted.write_bytes(b"%PDF-1.4 preview")
    f = make_pptx_record(db_session, regular_user, pptx)

    monkeypatch.setattr("services.office_preview_pdf_service.UPLOAD_DIR", str(tmp_path / "uploads"))
    monkeypatch.setattr("services.office_preview_pdf_service.convert_to_pdf", lambda _src: str(converted))

    preview = client.get(f"/api/files/{f.id}/preview", params={"token": jwt_token})
    assert preview.status_code == 200
    assert preview.content == b"%PDF-1.4 preview"
    assert (preview.headers.get("content-type") or "").startswith("application/pdf")

    download = client.get(f"/api/files/{f.id}/download", params={"token": jwt_token})
    assert download.status_code == 200
    assert download.content == b"original-pptx"


def test_pptx_preview_conversion_failure_returns_503_without_cache(
    client, db_session, regular_user, jwt_token, tmp_path, monkeypatch
):
    pptx = tmp_path / "broken.pptx"
    pptx.write_bytes(b"broken-pptx")
    f = make_pptx_record(db_session, regular_user, pptx)
    upload = tmp_path / "uploads"

    def fail_convert(_src):
        raise RuntimeError("conversion failed")

    monkeypatch.setattr("services.office_preview_pdf_service.UPLOAD_DIR", str(upload))
    monkeypatch.setattr("services.office_preview_pdf_service.convert_to_pdf", fail_convert)

    preview = client.get(f"/api/files/{f.id}/preview", params={"token": jwt_token})

    assert preview.status_code == 503
    assert "暂无法预览" in preview.text
    assert not (upload / ".preview_pdf" / f"{f.id}.pdf").exists()


def test_file_schema_reports_pdf_preview_mime_for_pptx(db_session, regular_user, tmp_path):
    pptx = tmp_path / "schema-deck.pptx"
    pptx.write_bytes(b"pptx")
    f = make_pptx_record(db_session, regular_user, pptx)

    schema = file_to_schema(
        db_session,
        f,
        regular_user.username,
        tags=[],
        tag_anchors=[],
    )

    assert schema.preview_mime_type == "application/pdf"


def test_extract_notify_payload_reports_pdf_preview_mime_for_pptx(
    db_session, regular_user, tmp_path
):
    pptx = tmp_path / "notify-deck.pptx"
    pptx.write_bytes(b"pptx")
    f = make_pptx_record(db_session, regular_user, pptx)

    payload = file_extract_notify_payload(f)

    assert payload["preview_mime_type"] == "application/pdf"
