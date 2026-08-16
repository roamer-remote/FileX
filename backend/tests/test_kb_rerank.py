# Copyright (c) 2026 徐泽宇
"""KB rerank HTTP client.

Authors:
    徐泽宇

Copyright:
    © 2026 徐泽宇
"""

from unittest.mock import MagicMock, patch

import httpx

from services.kb_rerank_service import _parse_rerank_response, rerank_hits


def test_parse_tei_style_response():
    data = [{"index": 1, "score": 0.9}, {"index": 0, "score": 0.1}]
    ranked = _parse_rerank_response(data, 2)
    assert ranked[0] == (1, 0.9)


@patch("services.kb_rerank_service.KB_RERANK_URL", "http://rerank.test/rerank")
@patch("services.kb_rerank_service.httpx.Client")
def test_rerank_hits_reorders(mock_client_cls):
    mock_resp = MagicMock()
    mock_resp.json.return_value = [{"index": 1, "score": 0.95}, {"index": 0, "score": 0.05}]
    mock_resp.raise_for_status = MagicMock()
    mock_client_cls.return_value.__enter__.return_value.post.return_value = mock_resp
    items = [{"text": "a", "score": 0.5}, {"text": "b", "score": 0.4}]
    out, applied = rerank_hits("q", items, top_k=2)
    assert applied is True
    assert out[0]["text"] == "b"


@patch("services.kb_rerank_service.KB_RERANK_URL", "http://rerank.test/rerank")
@patch("services.kb_rerank_service.httpx.Client")
def test_rerank_hits_caps_batch_for_tei(mock_client_cls):
    mock_resp = MagicMock()
    mock_resp.json.return_value = [{"index": 0, "score": 0.9}]
    mock_resp.raise_for_status = MagicMock()
    post = mock_client_cls.return_value.__enter__.return_value.post
    post.return_value = mock_resp
    items = [{"text": f"doc{i}", "score": 1.0 - i * 0.01} for i in range(50)]
    out, applied = rerank_hits("q", items, top_k=10)
    assert applied is True
    assert len(out) == 10
    body = post.call_args.kwargs.get("json") or post.call_args[1]["json"]
    assert len(body["texts"]) == 32


@patch("services.kb_rerank_service.KB_RERANK_URL", "")
def test_rerank_passthrough_when_disabled():
    items = [{"text": "a", "score": 0.5}]
    out, applied = rerank_hits("q", items, top_k=1)
    assert applied is False
