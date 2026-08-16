"""051: notify fanout must forward processing_duration_ms to WebSocket."""

from messaging.kb_index_notify import notify_payload_to_ws_event


def test_notify_payload_to_ws_event_includes_processing_duration_ms():
    payload = {
        "user_id": 1,
        "type": "kb_index_updated",
        "file_id": 42,
        "index_status": "ready",
        "processing_duration_ms": 3200,
    }
    event = notify_payload_to_ws_event(payload)
    assert event["processing_duration_ms"] == 3200
    assert "user_id" not in event


def test_notify_payload_to_ws_event_omits_duration_when_absent():
    payload = {
        "user_id": 1,
        "type": "kb_index_updated",
        "file_id": 42,
        "index_status": "indexing",
    }
    event = notify_payload_to_ws_event(payload)
    assert "processing_duration_ms" not in event


def test_notify_payload_to_ws_event_post_partial_does_not_default_chunk_count():
    payload = {
        "user_id": 1,
        "type": "kb_post_updated",
        "file_id": 42,
        "kb_post_status": "running",
    }
    event = notify_payload_to_ws_event(payload)
    assert event["type"] == "kb_post_updated"
    assert event["kb_post_status"] == "running"
    assert "chunk_count" not in event
    assert "index_status" not in event
    assert "md_has_content" not in event
