"""051: processing_duration_ms in KB notify payloads."""

from unittest.mock import MagicMock

from messaging.kb_index_publisher import file_index_notify_payload, publish_file_index_notify


def _mock_file(**kwargs):
    f = MagicMock()
    f.id = kwargs.get("id", 1)
    f.user_id = kwargs.get("user_id", 10)
    f.index_status = kwargs.get("index_status", "ready")
    f.chunk_count = kwargs.get("chunk_count", 3)
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


def test_file_index_notify_payload_without_duration():
    f = _mock_file()
    payload = file_index_notify_payload(f)
    assert "processing_duration_ms" not in payload


def test_file_index_notify_payload_with_duration():
    f = _mock_file()
    payload = file_index_notify_payload(f, processing_duration_ms=1234)
    assert payload["processing_duration_ms"] == 1234


def test_file_index_notify_payload_ignores_negative_duration():
    f = _mock_file()
    payload = file_index_notify_payload(f, processing_duration_ms=-1)
    assert "processing_duration_ms" not in payload


def test_publish_file_index_notify_includes_duration(monkeypatch):
    published = []

    def capture(body, **kwargs):
        published.append(body)

    monkeypatch.setattr(
        "messaging.kb_index_publisher.publish_kb_index_notify",
        capture,
    )
    f = _mock_file()
    publish_file_index_notify(f, processing_duration_ms=999)
    assert published[0]["processing_duration_ms"] == 999
    assert published[0]["user_id"] == f.user_id
