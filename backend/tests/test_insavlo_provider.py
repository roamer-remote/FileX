# Copyright (c) 2026 徐泽宇
"""044 stage 3: Insavlo provider submission."""

from __future__ import annotations

from datetime import datetime
from unittest.mock import MagicMock, patch

import pytest

from config import KB_EXTRACT_INSAVLO_MAX_FILE_BYTES
from models.file import File as FileModel
from services.extract.providers.insavlo_provider import (
    InsavloSubmission,
    InsavloSubmissionError,
    INSAVLO_SUPPORTED_EXTENSIONS,
    _parse_submission_response,
    submit_insavlo_extract,
)
from services.system_setting_service import (
    KEY_KB_EXTRACT_INSAVLO_API_KEY,
    KEY_KB_EXTRACT_INSAVLO_BASE_URL,
    KEY_KB_EXTRACT_INSAVLO_CALLBACK_ORIGIN,
    KEY_KB_EXTRACT_INSAVLO_ENABLED,
    KEY_KB_EXTRACT_INSAVLO_SKILL_CODE,
    KEY_KB_EXTRACT_INSAVLO_TIMEOUT_MINUTES,
    KEY_KB_EXTRACT_INSAVLO_WEBHOOK_SECRET,
    update_settings,
)


def _configure_insavlo(db_session):
    update_settings(
        db_session,
        {
            KEY_KB_EXTRACT_INSAVLO_ENABLED: "true",
            KEY_KB_EXTRACT_INSAVLO_BASE_URL: "https://demo.insavlo.com/insavlo/public-api/",
            KEY_KB_EXTRACT_INSAVLO_CALLBACK_ORIGIN: "https://ding.yyyou.top/",
            KEY_KB_EXTRACT_INSAVLO_SKILL_CODE: "filex-md",
            KEY_KB_EXTRACT_INSAVLO_API_KEY: "insavlo-api-key",
            KEY_KB_EXTRACT_INSAVLO_WEBHOOK_SECRET: "insavlo-webhook-secret",
            KEY_KB_EXTRACT_INSAVLO_TIMEOUT_MINUTES: "72",
        },
    )


def _pdf(regular_user, tmp_path, name="invoice.pdf", size=100):
    path = tmp_path / name
    path.write_bytes(b"%PDF-1.4" + b"x" * max(0, size - 8))
    f = FileModel(
        filename=name,
        original_name=name,
        file_path=str(path),
        file_size=size,
        mime_type="application/pdf",
        user_id=regular_user.id,
        has_md=False,
    )
    return f


def test_parse_submission_response_success():
    sub = _parse_submission_response(
        {
            "success": True,
            "transaction_id": "tx-1",
            "files": [{"file_id": "remote-1", "original_filename": "invoice.pdf"}],
        },
        skill_code="filex-md",
    )
    assert sub.transaction_id == "tx-1"
    assert sub.file_id == "remote-1"
    assert sub.skill_code == "filex-md"
    assert isinstance(sub.submitted_at, datetime)


def test_parse_submission_response_missing_file_id_is_ok():
    sub = _parse_submission_response(
        {"success": True, "transaction_id": "tx-2"},
        skill_code="filex-md",
    )
    assert sub.file_id is None


def test_parse_submission_response_success_false_raises():
    with pytest.raises(InsavloSubmissionError, match="bad skill"):
        _parse_submission_response({"success": False, "error": "bad skill"}, skill_code="x")


def test_parse_submission_response_missing_transaction_id_raises():
    with pytest.raises(InsavloSubmissionError, match="transaction_id"):
        _parse_submission_response({"success": True}, skill_code="x")


def test_supported_extensions_match_spec():
    assert INSAVLO_SUPPORTED_EXTENSIONS == frozenset({"pdf", "jpg", "jpeg", "png", "doc", "docx"})


def test_submit_rejects_unsupported_extension(db_session, regular_user, tmp_path):
    _configure_insavlo(db_session)
    path = tmp_path / "note.txt"
    path.write_bytes(b"hello")
    f = FileModel(
        filename="note.txt",
        original_name="note.txt",
        file_path=str(path),
        file_size=5,
        mime_type="text/plain",
        user_id=regular_user.id,
    )
    db_session.add(f)
    db_session.commit()
    db_session.refresh(f)
    with pytest.raises(InsavloSubmissionError, match="不支持该文件类型"):
        submit_insavlo_extract(f, db_session)


def test_submit_rejects_oversize_file(db_session, regular_user, tmp_path):
    _configure_insavlo(db_session)
    f = _pdf(regular_user, tmp_path, size=KB_EXTRACT_INSAVLO_MAX_FILE_BYTES + 1)
    db_session.add(f)
    db_session.commit()
    db_session.refresh(f)
    with pytest.raises(InsavloSubmissionError, match="MiB"):
        submit_insavlo_extract(f, db_session)


def test_submit_rejects_oversize_file_on_disk_even_when_db_size_small(db_session, regular_user, tmp_path):
    # Stage3 review Major #1: DB file_size 偏小但磁盘实际超大时仍应本地拒绝。
    _configure_insavlo(db_session)
    big = KB_EXTRACT_INSAVLO_MAX_FILE_BYTES + 1
    path = tmp_path / "big.pdf"
    path.write_bytes(b"%PDF-1.4" + b"x" * (big - 8))
    f = FileModel(
        filename="big.pdf",
        original_name="big.pdf",
        file_path=str(path),
        file_size=100,  # DB 偏小（陈旧）
        mime_type="application/pdf",
        user_id=regular_user.id,
    )
    db_session.add(f)
    db_session.commit()
    db_session.refresh(f)
    with pytest.raises(InsavloSubmissionError, match="MiB"):
        submit_insavlo_extract(f, db_session)


def test_submit_rejects_missing_source_file(db_session, regular_user, tmp_path):
    _configure_insavlo(db_session)
    f = FileModel(
        filename="ghost.pdf",
        original_name="ghost.pdf",
        file_path=str(tmp_path / "ghost.pdf"),
        file_size=100,
        mime_type="application/pdf",
        user_id=regular_user.id,
    )
    db_session.add(f)
    db_session.commit()
    db_session.refresh(f)
    with pytest.raises(InsavloSubmissionError, match="源文件不存在"):
        submit_insavlo_extract(f, db_session)


def test_submit_rejects_when_runtime_not_ready(db_session, regular_user, tmp_path):
    # 未配置 Insavlo，runtime 未就绪
    update_settings(db_session, {KEY_KB_EXTRACT_INSAVLO_ENABLED: "false"})
    f = _pdf(regular_user, tmp_path)
    db_session.add(f)
    db_session.commit()
    db_session.refresh(f)
    with pytest.raises(InsavloSubmissionError, match="未启用或不完整"):
        submit_insavlo_extract(f, db_session)


def _mock_httpx_ok():
    mock_client_cls = MagicMock()
    mock_resp = MagicMock()
    mock_resp.status_code = 200
    mock_resp.json.return_value = {
        "success": True,
        "transaction_id": "40b3ba73-3ecf-4bc1-8594-ed0216a72a33",
        "files_count": 1,
        "files": [{"file_id": "1e85997205ce4dbf96064bcf7abed782", "original_filename": "invoice.pdf"}],
        "message": "1 file(s) uploaded and processing started successfully",
    }
    mock_resp.text = '{"success": true}'
    mock_client_cls.return_value.__enter__.return_value.post.return_value = mock_resp
    return mock_client_cls


def test_submit_success_returns_submission_metadata(db_session, regular_user, tmp_path):
    _configure_insavlo(db_session)
    f = _pdf(regular_user, tmp_path)
    db_session.add(f)
    db_session.commit()
    db_session.refresh(f)

    with patch("services.extract.providers.insavlo_provider.httpx.Client", _mock_httpx_ok()):
        submission = submit_insavlo_extract(f, db_session, job_id=99)

    assert isinstance(submission, InsavloSubmission)
    assert submission.transaction_id == "40b3ba73-3ecf-4bc1-8594-ed0216a72a33"
    assert submission.file_id == "1e85997205ce4dbf96064bcf7abed782"
    assert submission.skill_code == "filex-md"


def test_submit_success_posts_callback_url_and_bearer(db_session, regular_user, tmp_path):
    _configure_insavlo(db_session)
    f = _pdf(regular_user, tmp_path)
    db_session.add(f)
    db_session.commit()
    db_session.refresh(f)

    mock_client_cls = _mock_httpx_ok()
    with patch("services.extract.providers.insavlo_provider.httpx.Client", mock_client_cls):
        submit_insavlo_extract(f, db_session)

    post = mock_client_cls.return_value.__enter__.return_value.post
    assert post.called
    args, kwargs = post.call_args
    assert args[0] == "https://demo.insavlo.com/insavlo/public-api/document_process/upload_and_process"
    assert kwargs["data"]["skill_code"] == "filex-md"
    assert kwargs["data"]["callback_url"] == "https://ding.yyyou.top/api/webhooks/insavlo/document-process"
    assert kwargs["headers"]["Authorization"] == "Bearer insavlo-api-key"
    assert "files[]" in kwargs["files"]


def test_submit_http_4xx_raises_without_fallback(db_session, regular_user, tmp_path):
    _configure_insavlo(db_session)
    f = _pdf(regular_user, tmp_path)
    db_session.add(f)
    db_session.commit()
    db_session.refresh(f)

    mock_client_cls = MagicMock()
    mock_resp = MagicMock()
    mock_resp.status_code = 422
    mock_resp.text = "skill_code invalid"
    mock_client_cls.return_value.__enter__.return_value.post.return_value = mock_resp

    with patch("services.extract.providers.insavlo_provider.httpx.Client", mock_client_cls):
        with pytest.raises(InsavloSubmissionError, match="HTTP 422"):
            submit_insavlo_extract(f, db_session)


def test_submit_supplier_success_false_raises(db_session, regular_user, tmp_path):
    _configure_insavlo(db_session)
    f = _pdf(regular_user, tmp_path)
    db_session.add(f)
    db_session.commit()
    db_session.refresh(f)

    mock_client_cls = MagicMock()
    mock_resp = MagicMock()
    mock_resp.status_code = 200
    mock_resp.json.return_value = {"success": False, "error": "unsupported skill_code"}
    mock_resp.text = '{"success": false}'
    mock_client_cls.return_value.__enter__.return_value.post.return_value = mock_resp

    with patch("services.extract.providers.insavlo_provider.httpx.Client", mock_client_cls):
        with pytest.raises(InsavloSubmissionError, match="unsupported skill_code"):
            submit_insavlo_extract(f, db_session)


def test_submit_http_transport_error_raises(db_session, regular_user, tmp_path):
    _configure_insavlo(db_session)
    f = _pdf(regular_user, tmp_path)
    db_session.add(f)
    db_session.commit()
    db_session.refresh(f)

    mock_client_cls = MagicMock()
    mock_client_cls.return_value.__enter__.return_value.post.side_effect = __import__(
        "httpx"
    ).ConnectError("connection refused")

    with patch("services.extract.providers.insavlo_provider.httpx.Client", mock_client_cls):
        with pytest.raises(InsavloSubmissionError, match="提交请求失败"):
            submit_insavlo_extract(f, db_session)


def test_submit_does_not_fallback_to_legacy_on_failure(db_session, regular_user, tmp_path):
    _configure_insavlo(db_session)
    f = _pdf(regular_user, tmp_path)
    db_session.add(f)
    db_session.commit()
    db_session.refresh(f)

    mock_client_cls = MagicMock()
    mock_resp = MagicMock()
    mock_resp.status_code = 500
    mock_resp.text = "internal"
    mock_client_cls.return_value.__enter__.return_value.post.return_value = mock_resp

    with (
        patch("services.extract.providers.insavlo_provider.httpx.Client", mock_client_cls),
        patch("services.extract.providers.registry._legacy_extract") as mock_legacy,
    ):
        with pytest.raises(InsavloSubmissionError):
            submit_insavlo_extract(f, db_session)
        mock_legacy.assert_not_called()
