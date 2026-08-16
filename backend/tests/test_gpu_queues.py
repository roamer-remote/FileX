"""164 §6：filex.gpu.* route 队列拓扑与消息契约。"""

from __future__ import annotations

import json

import pytest

from messaging.gpu_queues import (
    EXCHANGE_MAIN,
    QUEUE_GPU_MINERU,
    QUEUE_GPU_RAPTOR,
    ROUTING_KEY_GPU_MINERU,
    ROUTING_KEY_GPU_RAPTOR,
    declare_gpu_topology,
    parse_gpu_route_body,
    publish_gpu_route_message,
    validate_gpu_route_payload,
)


def _valid_payload(**overrides) -> dict:
    payload = {
        "job_id": 42,
        "job_kind": "mineru",
        "file_id": 7,
        "idempotency_key": "mineru:42:0",
        "attempt": 0,
        "handover_epoch": 0,
    }
    payload.update(overrides)
    return payload


def test_validate_requires_route_contract_fields():
    with pytest.raises(ValueError, match="idempotency_key"):
        validate_gpu_route_payload(
            {"job_id": 42, "job_kind": "mineru", "file_id": 7, "attempt": 0}
        )
    with pytest.raises(ValueError, match="handover_epoch"):
        validate_gpu_route_payload(_valid_payload(handover_epoch=None))
    with pytest.raises(ValueError, match="job_kind"):
        validate_gpu_route_payload(_valid_payload(job_kind="llm"))
    with pytest.raises(ValueError, match="missing fields"):
        validate_gpu_route_payload(_valid_payload(file_id=None))
    assert validate_gpu_route_payload(_valid_payload())["job_id"] == 42


def test_parse_gpu_route_body_roundtrip_and_rejects_bad_json():
    payload = _valid_payload()
    assert parse_gpu_route_body(json.dumps(payload).encode()) == payload
    with pytest.raises(ValueError):
        parse_gpu_route_body(b"not-json")
    with pytest.raises(ValueError, match="job_kind"):
        parse_gpu_route_body(json.dumps(_valid_payload(job_kind="x")).encode())


class _FakeChannel:
    def __init__(self) -> None:
        self.declared_queues: list[str] = []
        self.bound: list[tuple[str, str, str]] = []
        self.published: list[tuple[str, str, bytes]] = []

    def queue_declare(self, queue: str, **kwargs) -> None:
        self.declared_queues.append(queue)

    def queue_bind(self, queue: str, exchange: str, routing_key: str) -> None:
        self.bound.append((queue, exchange, routing_key))

    def exchange_declare(self, **kwargs) -> None:
        pass

    def basic_publish(self, exchange: str, routing_key: str, body: bytes, **kwargs) -> None:
        self.published.append((exchange, routing_key, body))


def test_declare_gpu_topology_binds_scheduler_owned_queues(monkeypatch):
    from messaging import kb_index_queues

    monkeypatch.setattr(kb_index_queues, "declare_kb_index_topology", lambda ch: None)
    channel = _FakeChannel()
    declare_gpu_topology(channel)
    assert set(channel.declared_queues) == {QUEUE_GPU_MINERU, QUEUE_GPU_RAPTOR}
    assert (QUEUE_GPU_MINERU, EXCHANGE_MAIN, ROUTING_KEY_GPU_MINERU) in channel.bound
    assert (QUEUE_GPU_RAPTOR, EXCHANGE_MAIN, ROUTING_KEY_GPU_RAPTOR) in channel.bound


def test_publish_gpu_route_message_uses_kind_routing_key(monkeypatch):
    import messaging.gpu_queues as gpu_queues

    channel = _FakeChannel()
    monkeypatch.setattr(gpu_queues, "declare_gpu_topology", lambda ch: None)
    monkeypatch.setattr(
        gpu_queues,
        "open_blocking_connection",
        lambda: _FakeConnection(channel),
    )
    publish_gpu_route_message("mineru", _valid_payload())
    publish_gpu_route_message("raptor", _valid_payload(job_kind="raptor", idempotency_key="raptor:43:0", job_id=43))
    assert [route[1] for route in channel.published] == [
        ROUTING_KEY_GPU_MINERU,
        ROUTING_KEY_GPU_RAPTOR,
    ]
    body = json.loads(channel.published[0][2].decode())
    assert body["idempotency_key"] == "mineru:42:0"

    with pytest.raises(ValueError, match="missing fields"):
        publish_gpu_route_message("mineru", {"job_id": 42})


class _FakeConnection:
    def __init__(self, channel: _FakeChannel) -> None:
        self._channel = channel

    def channel(self) -> _FakeChannel:
        return self._channel

    def close(self) -> None:
        self.is_open = False

    is_open = True
