# Copyright (c) 2026 徐泽宇
"""kb_post_consumer 错误恢复：JOB_RUNNING 引用与 retry 路径。"""

from __future__ import annotations

from unittest.mock import MagicMock

from messaging.kb_post_consumer import _LeaseToken, _recover_handler_error
from services.kb_post_service import JOB_QUEUED, JOB_RUNNING


class TestKbPostHandlerRecover:
    def test_recover_handler_error_requeues_under_max_attempts(self, monkeypatch):
        fake_job = MagicMock()
        fake_job.status = JOB_RUNNING
        fake_job.attempts = 0
        fake_job.id = 42
        fake_job.file_id = 99
        fake_job.worker_id = "worker-42"
        fake_job.lease_generation = 1

        fake_file = MagicMock()
        fake_file.user_id = 7
        fake_db = MagicMock()
        fake_db.query.return_value.filter.return_value.first.side_effect = [fake_job, fake_file, fake_file]

        monkeypatch.setattr("messaging.kb_post_consumer.SessionLocal", lambda: fake_db)
        monkeypatch.setattr("messaging.kb_post_consumer.get_user_effective_dict", lambda *a, **k: {})
        monkeypatch.setattr("messaging.kb_post_consumer.get_kb_post_max_attempts", lambda *a, **k: 3)
        published: list[int] = []
        monkeypatch.setattr(
            "messaging.kb_post_consumer.publish_kb_post_retry",
            lambda jid, connection=None: published.append(jid),
        )
        monkeypatch.setattr("messaging.kb_post_consumer._publish_post_notify_safe", lambda *a, **k: None)
        monkeypatch.setattr("messaging.kb_post_consumer.publish_kb_post_dlq", lambda *a, **k: None)

        _recover_handler_error(42, "boom", MagicMock(), token=_LeaseToken("worker-42", 1))

        assert fake_job.status == JOB_QUEUED
        assert fake_job.attempts == 1
        assert published == [42]
        fake_db.commit.assert_called()

    def test_recover_handler_error_falls_back_when_settings_read_fails(self, monkeypatch):
        fake_job = MagicMock()
        fake_job.status = JOB_RUNNING
        fake_job.attempts = 0
        fake_job.id = 43
        fake_job.file_id = 100
        fake_job.worker_id = "worker-43"
        fake_job.lease_generation = 1

        fake_file = MagicMock()
        fake_file.user_id = 7
        fake_db = MagicMock()
        fake_db.query.return_value.filter.return_value.first.side_effect = [fake_job, fake_file, fake_file]

        monkeypatch.setattr("messaging.kb_post_consumer.SessionLocal", lambda: fake_db)
        monkeypatch.setattr(
            "messaging.kb_post_consumer.get_user_effective_dict",
            lambda *a, **k: (_ for _ in ()).throw(RuntimeError("settings unavailable")),
        )
        published: list[int] = []
        monkeypatch.setattr(
            "messaging.kb_post_consumer.publish_kb_post_retry",
            lambda jid, connection=None: published.append(jid),
        )
        monkeypatch.setattr("messaging.kb_post_consumer._publish_post_notify_safe", lambda *a, **k: None)
        monkeypatch.setattr("messaging.kb_post_consumer.publish_kb_post_dlq", lambda *a, **k: None)

        _recover_handler_error(43, "boom", MagicMock(), token=_LeaseToken("worker-43", 1))

        assert fake_job.status == JOB_QUEUED
        assert fake_job.attempts == 1
        assert published == [43]
        fake_db.commit.assert_called()
