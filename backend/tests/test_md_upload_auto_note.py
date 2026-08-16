# Copyright (c) 2026 徐泽宇
"""上传 Markdown / 纯文本文件时自动写入资料笔记。

Authors:
    徐泽宇

Copyright:
    © 2026 徐泽宇
"""

import os
from unittest.mock import patch

from services.md_paths import md_note_path, okf_sidecar_path
from services.md_note_service import is_markdown_upload
from services.okf.frontmatter import split_frontmatter


def _sidecar_path(data: dict) -> str:
    return okf_sidecar_path(data["workspace_id"], data["okf_concept_path"])


def test_is_markdown_upload_by_extension_and_mime():
    assert is_markdown_upload("notes.md")
    assert is_markdown_upload("readme.markdown")
    assert is_markdown_upload("notes.txt")
    assert is_markdown_upload("x.bin", "text/markdown")
    assert is_markdown_upload("plain.bin", "text/plain")
    assert not is_markdown_upload("paper.pdf")


def test_upload_md_auto_attaches_sidecar_note(client, jwt_token, regular_user):
    body = "# Title\n\nHello **world**.\n"
    r = client.post(
        "/api/files/upload",
        headers={"Authorization": f"Bearer {jwt_token}"},
        files={"file": ("auto_note.md", body.encode("utf-8"), "text/markdown")},
    )
    assert r.status_code == 200
    data = r.json()
    assert data["has_md"] is True
    assert data["md_has_content"] is True

    file_id = data["id"]
    note_path = _sidecar_path(data)
    assert os.path.isfile(note_path)
    meta, saved_body = split_frontmatter(open(note_path, encoding="utf-8").read())
    assert meta["type"] == "FileX Source"
    assert meta["title"] == "auto_note"
    assert meta["resource"] == f"filex://files/{file_id}"
    assert meta["filex"]["file_id"] == file_id
    assert saved_body == body


def test_upload_txt_auto_attaches_sidecar(client, jwt_token):
    body = b"line one\nline two\n"
    with patch("services.kb_index_service.publish_index_job"):
        r = client.post(
            "/api/files/upload",
            headers={"Authorization": f"Bearer {jwt_token}"},
            files={"file": ("plain.txt", body, "text/plain")},
        )
    assert r.status_code == 200
    data = r.json()
    assert data["has_md"] is True
    assert data["md_has_content"] is True

    file_id = data["id"]
    note_path = _sidecar_path(data)
    assert os.path.isfile(note_path)
    meta, saved_body = split_frontmatter(open(note_path, encoding="utf-8").read())
    assert meta["type"] == "FileX Source"
    assert saved_body == body.decode("utf-8")


def test_upload_accepts_okf_form_metadata(client, jwt_token):
    body = "# Body\n\nCustom upload.\n"
    r = client.post(
        "/api/files/upload",
        headers={"Authorization": f"Bearer {jwt_token}"},
        data={
            "okf_title": "Custom Source",
            "okf_type": "Research Note",
            "okf_description": "Uploaded with caller-provided OKF fields",
            "okf_tags": '["alpha", "beta"]',
            "okf_concept_path": "sources/research/custom-source",
        },
        files={"file": ("custom_source.md", body.encode("utf-8"), "text/markdown")},
    )
    assert r.status_code == 200
    data = r.json()
    assert data["okf_concept_path"] == "sources/research/custom-source"
    assert data["okf_type"] == "Research Note"
    assert data["tags"] == ["alpha", "beta"]

    note_path = _sidecar_path(data)
    meta, saved_body = split_frontmatter(open(note_path, encoding="utf-8").read())
    assert meta["type"] == "Research Note"
    assert meta["title"] == "Custom Source"
    assert meta["description"] == "Uploaded with caller-provided OKF fields"
    assert meta["tags"] == ["alpha", "beta"]
    assert saved_body == body


def test_external_upload_txt_creates_okf_sidecar(client, active_api_key):
    r = client.post(
        "/api/external/files",
        headers={"Authorization": f"Bearer {active_api_key._plaintext}"},
        files={"file": ("agent_plain.txt", b"agent raw text", "text/plain")},
    )
    assert r.status_code == 200
    data = r.json()
    assert data["has_md"] is True
    assert data.get("md_has_content") is True
    assert data["okf_concept_path"].startswith("sources/")
    note_path = _sidecar_path(data)
    meta, saved_body = split_frontmatter(open(note_path, encoding="utf-8").read())
    assert meta["type"] == "FileX Source"
    assert saved_body == "agent raw text\n"


def test_upload_pdf_creates_okf_empty_body_shell(client, jwt_token, db_session):
    """SC-111-001: 非 Markdown 上传先落合法 OKF 壳，body 为空；须入队提取而非 hash skip。"""
    from models.kb_extract_job import KbExtractJob

    pdf_bytes = b"%PDF-1.4\n%\xe2\xe3\xcf\xd3\n1 0 obj<<>>endobj\ntrailer<<>>\n%%EOF\n"
    with patch("services.kb_extract_service.publish_extract_job"), patch(
        "services.kb_index_service.publish_index_job"
    ):
        r = client.post(
            "/api/files/upload",
            headers={"Authorization": f"Bearer {jwt_token}"},
            files={"file": ("paper.pdf", pdf_bytes, "application/pdf")},
        )
    assert r.status_code == 200, r.text
    data = r.json()
    assert data["has_md"] is True
    assert data["md_has_content"] is False
    assert data["okf_concept_path"].startswith("sources/")
    assert data["extract_status"] == "pending"

    note_path = _sidecar_path(data)
    assert os.path.isfile(note_path)
    meta, body = split_frontmatter(open(note_path, encoding="utf-8").read())
    assert meta["type"] == "FileX Source"
    assert meta["filex"]["file_id"] == data["id"]
    assert body == ""

    jobs = db_session.query(KbExtractJob).filter(KbExtractJob.file_id == data["id"]).all()
    assert len(jobs) == 1
    assert jobs[0].status == "queued"


def test_upload_png_enqueues_extract_not_hash_skip(client, jwt_token, db_session):
    """111 回归：图片上传空 OKF 壳不得因空 body hash 误判 extract ready。"""
    from models.kb_extract_job import KbExtractJob

    png_bytes = b"\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR\x00\x00\x00\x01\x00\x00\x00\x01\x08\x02\x00\x00\x00\x90wS\xde\x00\x00\x00\x0cIDATx\x9cc\xf8\x0f\x00\x00\x01\x01\x00\x05\x18\xd8N\x00\x00\x00\x00IEND\xaeB`\x82"
    with patch("services.kb_extract_service.publish_extract_job"), patch(
        "services.kb_index_service.publish_index_job"
    ):
        r = client.post(
            "/api/files/upload",
            headers={"Authorization": f"Bearer {jwt_token}"},
            files={"file": ("photo.png", png_bytes, "image/png")},
        )
    assert r.status_code == 200, r.text
    data = r.json()
    assert data["has_md"] is True
    assert data["md_has_content"] is False
    assert data["extract_status"] == "pending"
    assert db_session.query(KbExtractJob).filter(KbExtractJob.file_id == data["id"]).count() == 1


def test_upload_md_with_existing_okf_frontmatter_preserves_tags(client, jwt_token):
    """SC-111-004: 上传已含 OKF frontmatter 的 .md，frontmatter 标签同步到 file_tags。"""
    raw = (
        "---\n"
        "type: Research Note\n"
        "title: Pre Authored\n"
        "tags: [xray, yankee]\n"
        "okf_version: '0.1'\n"
        "---\n"
        "# Pre authored body\n"
    )
    with patch("services.kb_index_service.publish_index_job"):
        r = client.post(
            "/api/files/upload",
            headers={"Authorization": f"Bearer {jwt_token}"},
            files={"file": ("pre_authored.md", raw.encode("utf-8"), "text/markdown")},
        )
    assert r.status_code == 200, r.text
    data = r.json()
    assert data["okf_type"] == "Research Note"
    assert data["tags"] == ["xray", "yankee"]

    note_path = _sidecar_path(data)
    meta, body = split_frontmatter(open(note_path, encoding="utf-8").read())
    assert meta["type"] == "Research Note"
    assert meta["title"] == "Pre Authored"
    assert meta["tags"] == ["xray", "yankee"]
    assert meta["resource"] == f"filex://files/{data['id']}"
    assert "# Pre authored body" in body


def test_upload_md5_dedup_does_not_backfill_legacy_okf(client, jwt_token, db_session):
    """SC-111-015: MD5 命中既有记录直接返回，不回填历史 body-only OKF。"""
    from models.file import File as FileModel

    content = b"# duplicate content\n"
    with patch("services.kb_index_service.publish_index_job"):
        first = client.post(
            "/api/files/upload",
            headers={"Authorization": f"Bearer {jwt_token}"},
            files={"file": ("dup.md", content, "text/markdown")},
        )
    assert first.status_code == 200
    first_data = first.json()
    file_id = first_data["id"]

    # 模拟历史 body-only 笔记（无 frontmatter），sidecar 仍在 .md_notes/
    note_path = md_note_path(file_id)
    legacy_body = "legacy body without frontmatter\n"
    with open(note_path, "w", encoding="utf-8") as fh:
        fh.write(legacy_body)
    f = db_session.query(FileModel).filter(FileModel.id == file_id).one()
    f.md_file_path = note_path
    db_session.flush()

    with patch("services.kb_index_service.publish_index_job"):
        second = client.post(
            "/api/files/upload",
            headers={"Authorization": f"Bearer {jwt_token}"},
            files={"file": ("dup_again.md", content, "text/markdown")},
        )
    assert second.status_code == 200
    second_data = second.json()
    assert second_data["id"] == file_id
    assert second_data.get("deduplicated") is True

    # 去重命中不应 backfill OKF，笔记仍为 body-only
    assert open(note_path, encoding="utf-8").read() == legacy_body
