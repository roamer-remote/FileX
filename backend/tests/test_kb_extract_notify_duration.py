"""051: extract notify payload inherits processing_duration_ms."""

import json
import logging
from unittest.mock import MagicMock, patch

import pytest

from messaging.kb_extract_publisher import file_extract_notify_payload, publish_file_extract_notify
from models.file import File as FileModel
from models.kb_extract_job import KbExtractJob
from services.kb_extract_service import JOB_QUEUED


@pytest.fixture
def sample_file(db_session, regular_user):
    f = FileModel(
        filename="x.bin",
        original_name="paper.pdf",
        file_path="/tmp/unused.bin",
        file_size=10,
        mime_type="application/pdf",
        user_id=regular_user.id,
        has_md=False,
    )
    db_session.add(f)
    db_session.commit()
    db_session.refresh(f)
    return f


def _mock_file(**kwargs):
    f = MagicMock()
    f.id = kwargs.get("id", 1)
    f.user_id = kwargs.get("user_id", 10)
    f.index_status = kwargs.get("index_status", "ready")
    f.chunk_count = kwargs.get("chunk_count", 0)
    f.index_error = kwargs.get("index_error", None)
    f.extract_status = kwargs.get("extract_status", "ready")
    f.extract_error = kwargs.get("extract_error", None)
    f.has_md = kwargs.get("has_md", True)
    f.md_file_path = kwargs.get("md_file_path", "/tmp/f.md")
    f.extracted_at = kwargs.get("extracted_at", None)
    f.extract_engine = kwargs.get("extract_engine", None)
    f.mime_type = kwargs.get("mime_type", "text/plain")
    f.original_name = kwargs.get("original_name", "doc.pdf")
    return f


def test_file_extract_notify_payload_inherits_duration():
    f = _mock_file()
    payload = file_extract_notify_payload(f, processing_duration_ms=500)
    assert payload["type"] == "kb_extract_updated"
    assert payload["processing_duration_ms"] == 500


def test_publish_file_extract_notify_includes_duration(monkeypatch):
    published = []

    def capture(body, **kwargs):
        published.append(body)

    monkeypatch.setattr(
        "messaging.kb_extract_publisher.publish_kb_index_notify",
        capture,
    )
    f = _mock_file()
    publish_file_extract_notify(f, processing_duration_ms=1500)
    assert published[0]["processing_duration_ms"] == 1500
    assert published[0]["type"] == "kb_extract_updated"


@patch("messaging.kb_extract_consumer._handle_job")
@patch("messaging.kb_extract_consumer.require_license_or_wait", return_value=True)
def test_on_message_logs_chinese_task_timing(
    _mock_license,
    mock_handle,
    db_session,
    sample_file,
    caplog,
):
    from messaging.kb_extract_consumer import _on_message

    job = KbExtractJob(user_id=sample_file.user_id, file_id=sample_file.id, status=JOB_QUEUED)
    db_session.add(job)
    db_session.commit()

    class _Method:
        delivery_tag = 1

    class _Channel:
        connection = object()

        def basic_ack(self, delivery_tag: int) -> None:
            pass

    caplog.set_level(logging.INFO, logger="messaging.kb_extract_consumer")
    _on_message(
        _Channel(),
        _Method(),
        None,
        json.dumps({"job_id": job.id}).encode("utf-8"),
    )
    mock_handle.assert_called_once()
    messages = [r.message for r in caplog.records if "提取消费者" in r.message]
    assert any("接到提取任务" in m and "开始时间=" in m for m in messages)
    assert any("提取任务结束" in m and "结束时间=" in m and "耗时=" in m for m in messages)
