from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import patch

from pika.exceptions import ChannelClosedByBroker, ChannelWrongStateError

from messaging.gpu_queues import QUEUE_GPU_MINERU
from services import rabbitmq_status_service as svc


class _FakeChannel:
    def __init__(self) -> None:
        self._poisoned = False

    def exchange_declare(self, **kwargs: object) -> None:
        pass

    def queue_bind(self, **kwargs: object) -> None:
        pass

    def queue_declare(self, queue: str, passive: bool = False, **kwargs: object):
        if passive and queue == QUEUE_GPU_MINERU:
            self._poisoned = True
            raise ChannelClosedByBroker(404, "NOT_FOUND - no queue 'filex.gpu.mineru'")
        if passive and self._poisoned:
            raise ChannelWrongStateError("Channel is closed.")
        return SimpleNamespace(method=SimpleNamespace(message_count=0, consumer_count=0))


class _FakeConnection:
    def __init__(self) -> None:
        self.is_open = True
        self.channels: list[_FakeChannel] = []

    def channel(self) -> _FakeChannel:
        ch = _FakeChannel()
        self.channels.append(ch)
        return ch

    def close(self) -> None:
        self.is_open = False


def test_missing_gpu_queue_does_not_poison_mq_status_channel() -> None:
    conn = _FakeConnection()

    with patch.object(svc, "RABBITMQ_URL", "amqp://filebox:filebox@rabbitmq:5672/"):
        with patch.object(svc, "open_blocking_connection", return_value=conn):
            with patch("services.system_resource_service.collect_system_resources", return_value=None):
                payload = svc._build_mq_status_payload(
                    now="2026-08-02T00:00:00+08:00",
                    broker_display="amqp://filebox:****@rabbitmq:5672/",
                    empty_queues=[],
                    monitored=svc.MONITORED_QUEUES,
                    active_tasks=[],
                    backlog_map={},
                    user_scoped=False,
                    gpu_observability=None,
                )

    assert payload["connected"] is True
    assert payload["error"] is None
    by_label = {q["label"]: q for q in payload["queues"]}
    assert by_label["gpu_mineru"]["online"] is False
    assert by_label["gpu_raptor"]["online"] is True
    assert len(conn.channels) >= 2
