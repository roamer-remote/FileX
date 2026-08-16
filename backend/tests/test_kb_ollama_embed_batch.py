# Copyright (c) 2026 徐泽宇
"""Ollama embed batching splits large chunk lists.

Authors:
    徐泽宇

Copyright:
    © 2026 徐泽宇
"""

from unittest.mock import MagicMock, patch

import httpx

from services.kb_ollama_embed import embed_texts
from services.ollama_config_service import OllamaRuntimeConfig


def _mock_response(status: int, json_data: dict) -> MagicMock:
    r = MagicMock(spec=httpx.Response)
    r.status_code = status
    r.json.return_value = json_data
    r.raise_for_status.return_value = None
    return r


@patch(
    "services.kb_ollama_embed.get_ollama_runtime_config",
    return_value=OllamaRuntimeConfig(
        base_url="http://ollama.test",
        embed_model="bge-test",
        embed_dim=2,
        chat_model="qwen-test",
        timeout_sec=30.0,
        embed_batch_size=2,
        num_parallel=4,
        embed_concurrency=1,
    ),
)
@patch("services.kb_ollama_embed.httpx.Client")
def test_embed_texts_batches_requests(mock_client_cls, _mock_cfg):
    client = MagicMock()
    mock_client_cls.return_value.__enter__.return_value = client
    client.post.side_effect = [
        _mock_response(200, {"embeddings": [[0.1, 0.2], [0.3, 0.4]]}),
        _mock_response(200, {"embeddings": [[0.5, 0.6], [0.7, 0.8]]}),
        _mock_response(200, {"embeddings": [[0.9, 1.0]]}),
    ]
    # 强制串行（通过 cfg.embed_concurrency=1）
    texts = ["a", "b", "c", "d", "e"]
    out = embed_texts(texts)
    assert len(out) == 5
    assert client.post.call_count == 3
    assert client.post.call_args_list[0][1]["json"]["input"] == ["a", "b"]


@patch(
    "services.kb_ollama_embed.get_ollama_runtime_config",
    return_value=OllamaRuntimeConfig(
        base_url="http://ollama.test",
        embed_model="bge-test",
        embed_dim=2,
        chat_model="qwen-test",
        timeout_sec=30.0,
        embed_batch_size=2,
        num_parallel=4,
        embed_concurrency=1,
    ),
)
@patch("services.kb_ollama_embed.httpx.Client")
def test_embed_texts_calls_heartbeat_after_each_batch(mock_client_cls, _mock_cfg):
    client = MagicMock()
    mock_client_cls.return_value.__enter__.return_value = client
    client.post.side_effect = [
        _mock_response(200, {"embeddings": [[0.1, 0.2], [0.3, 0.4]]}),
        _mock_response(200, {"embeddings": [[0.5, 0.6], [0.7, 0.8]]}),
        _mock_response(200, {"embeddings": [[0.9, 1.0]]}),
    ]
    beats: list[int] = []
    embed_texts(["a", "b", "c", "d", "e"], heartbeat_cb=lambda: beats.append(1))
    assert len(beats) == 3


@patch(
    "services.kb_ollama_embed.get_ollama_runtime_config",
    return_value=OllamaRuntimeConfig(
        base_url="http://ollama.test",
        embed_model="bge-test",
        embed_dim=2,
        chat_model="qwen-test",
        timeout_sec=30.0,
        embed_batch_size=2,
        num_parallel=4,
        embed_concurrency=1,
    ),
)
@patch("services.kb_ollama_embed.httpx.Client")
def test_embed_texts_calls_progress_cb_per_chunk(mock_client_cls, _mock_cfg):
    client = MagicMock()
    mock_client_cls.return_value.__enter__.return_value = client
    client.post.side_effect = [
        _mock_response(200, {"embeddings": [[0.1, 0.2], [0.3, 0.4]]}),
        _mock_response(200, {"embeddings": [[0.5, 0.6], [0.7, 0.8]]}),
        _mock_response(200, {"embeddings": [[0.9, 1.0]]}),
    ]
    progress: list[tuple[int, int]] = []
    embed_texts(["a", "b", "c", "d", "e"], progress_cb=lambda done, total: progress.append((done, total)))
    assert progress == [(1, 5), (2, 5), (3, 5), (4, 5), (5, 5)]


@patch(
    "services.kb_ollama_embed.get_ollama_runtime_config",
    return_value=OllamaRuntimeConfig(
        base_url="http://ollama.test",
        embed_model="bge-test",
        embed_dim=2,
        chat_model="qwen-test",
        timeout_sec=30.0,
        embed_batch_size=2,
        num_parallel=4,
        embed_concurrency=4,
    ),
)
@patch("services.kb_ollama_embed.httpx.Client")
def test_embed_texts_concurrent_path_creates_multiple_clients(mock_client_cls, _mock_cfg):
    """验证并发路径（concurrency>1 + 多批）会创建多个独立 Client，并正确收集结果。"""
    created: list[MagicMock] = []

    def _make_response_for_texts(texts: list[str]):
        # 返回一个能通过 _parse_native_vectors 的响应
        vecs = [[float(i) / 10, float(i) / 10 + 0.1] for i in range(len(texts))]
        return _mock_response(200, {"embeddings": vecs})

    def _make_client(*a, **k):
        c = MagicMock()
        inner = MagicMock()

        def _post(url, **kw):
            # 从调用参数里尽量拿到 input 长度
            payload = kw.get("json") or {}
            inp = payload.get("input") or []
            if isinstance(inp, str):
                inp = [inp]
            return _make_response_for_texts(inp if inp else ["x"])

        inner.post.side_effect = _post
        c.__enter__.return_value = inner
        created.append(inner)
        return c

    mock_client_cls.side_effect = _make_client

    texts = ["a", "b", "c", "d", "e"]  # 3 batches (batch_size=2)
    out = embed_texts(texts)
    assert len(out) == 5
    assert len(created) >= 2
    assert mock_client_cls.call_count >= 2
