# Copyright (c) 2026 徐泽宇
"""Ollama embed client: /api/embed vs legacy /api/embeddings.

Authors:
    徐泽宇

Copyright:
    © 2026 徐泽宇
"""

from unittest.mock import MagicMock, patch

import httpx
import pytest

from services.kb_ollama_embed import embed_text
from services.ollama_config_service import OllamaRuntimeConfig

_TEST_CFG = OllamaRuntimeConfig(
    base_url="http://127.0.0.1:11434",
    embed_model="test-embed",
    embed_dim=2,
    chat_model="test-chat",
    timeout_sec=30.0,
    embed_batch_size=8,
    num_parallel=4,
    embed_concurrency=4,
)


def _mock_response(status: int, json_data: dict) -> MagicMock:
    r = MagicMock(spec=httpx.Response)
    r.status_code = status
    r.json.return_value = json_data
    if status >= 400:
        r.raise_for_status.side_effect = httpx.HTTPStatusError(
            "err", request=MagicMock(), response=r
        )
    else:
        r.raise_for_status.return_value = None
    return r


@patch("services.kb_ollama_embed.get_ollama_runtime_config", return_value=_TEST_CFG)
@patch("services.kb_ollama_embed.httpx.Client")
def test_prefers_api_embed(mock_client_cls, _mock_cfg):
    client = MagicMock()
    mock_client_cls.return_value.__enter__.return_value = client
    client.post.side_effect = [
        _mock_response(200, {"embeddings": [[0.1, 0.2]]}),
    ]
    assert embed_text("hello") == [0.1, 0.2]
    assert client.post.call_args[0][0].endswith("/api/embed")


@patch("services.kb_ollama_embed.get_ollama_runtime_config", return_value=_TEST_CFG)
@patch("services.kb_ollama_embed.httpx.Client")
def test_falls_back_to_api_embeddings_on_404(mock_client_cls, _mock_cfg):
    client = MagicMock()
    mock_client_cls.return_value.__enter__.return_value = client
    client.post.side_effect = [
        _mock_response(404, {}),
        _mock_response(200, {"embedding": [0.3, 0.4]}),
    ]
    assert embed_text("hello") == [0.3, 0.4]
    assert client.post.call_args_list[1][0][0].endswith("/api/embeddings")


@patch("services.kb_ollama_embed.get_ollama_runtime_config", return_value=_TEST_CFG)
@patch("services.kb_ollama_embed.httpx.Client")
def test_openai_v1_when_native_paths_404(mock_client_cls, _mock_cfg):
    client = MagicMock()
    mock_client_cls.return_value.__enter__.return_value = client
    client.get.return_value = _mock_response(200, {"models": [{"name": "nomic-embed-text"}]})
    client.post.side_effect = [
        _mock_response(404, {}),
        _mock_response(404, {}),
        _mock_response(200, {"data": [{"embedding": [0.5, 0.6]}]}),
    ]
    assert embed_text("hello") == [0.5, 0.6]
    assert client.post.call_args_list[2][0][0].endswith("/v1/embeddings")


@patch("services.kb_ollama_embed.get_ollama_runtime_config", return_value=_TEST_CFG)
@patch("services.kb_ollama_embed.httpx.Client")
def test_embedding_response_is_checked_by_capability_contract(mock_client_cls, _mock_cfg):
    client = MagicMock()
    mock_client_cls.return_value.__enter__.return_value = client
    client.post.return_value = _mock_response(200, {"embeddings": [[0.1, "bad"]]})

    with pytest.raises(Exception, match="malformed embedding response"):
        embed_text("hello")
