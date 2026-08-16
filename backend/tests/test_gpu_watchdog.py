"""GPU watchdog 探针单测（164 §5.5 / SC-164-007 T-9 修正）。"""

from types import SimpleNamespace

from services import gpu_watchdog


def _lease() -> SimpleNamespace:
    return SimpleNamespace(id="lease-1")


def test_round_idle_confirmed_when_sidecar_idle(monkeypatch):
    """sidecar 无 active 执行时确认旧轮已退出：RAPTOR 与 MinerU 均可回收。"""
    monkeypatch.setattr(
        gpu_watchdog,
        "_sidecar_status_url",
        lambda: "http://filex-mineru:8080/lifecycle/status",
    )
    monkeypatch.setattr(
        gpu_watchdog,
        "_fetch_sidecar_status",
        lambda url: {"status": "ok", "active_executions": 0, "active_jobs": []},
    )

    assert gpu_watchdog.gpu_round_idle(job_kind="raptor", lease=_lease()) is True
    assert gpu_watchdog.gpu_round_idle(job_kind="mineru", lease=_lease()) is True


def test_round_idle_blocks_when_sidecar_has_active_execution(monkeypatch):
    """sidecar 仍在执行旧 MinerU 轮：不得确认，保持 recovery_blocked。"""
    monkeypatch.setattr(
        gpu_watchdog,
        "_sidecar_status_url",
        lambda: "http://filex-mineru:8080/lifecycle/status",
    )
    monkeypatch.setattr(
        gpu_watchdog,
        "_fetch_sidecar_status",
        lambda url: {
            "status": "ok",
            "active_executions": 1,
            "active_jobs": [
                {
                    "gpu_lease_id": "lease-1",
                    "fencing_token": "token-1",
                    "gpu_job_id": "94",
                }
            ],
        },
    )

    assert gpu_watchdog.gpu_round_idle(job_kind="raptor", lease=_lease()) is False
    assert gpu_watchdog.gpu_round_idle(job_kind="mineru", lease=_lease()) is False


def test_round_idle_blocks_on_probe_failure(monkeypatch):
    """探测失败（sidecar 不可达/超时/非 200）按无法确认处理，fail-closed。"""
    monkeypatch.setattr(
        gpu_watchdog,
        "_sidecar_status_url",
        lambda: "http://filex-mineru:8080/lifecycle/status",
    )

    def _boom(url: str) -> dict:
        raise RuntimeError("connection refused")

    monkeypatch.setattr(gpu_watchdog, "_fetch_sidecar_status", _boom)
    assert gpu_watchdog.gpu_round_idle(job_kind="raptor", lease=_lease()) is False


def test_round_idle_blocks_when_sidecar_url_unset(monkeypatch):
    """sidecar URL 未配置即无法探测：不得确认。"""
    monkeypatch.setattr(gpu_watchdog, "_sidecar_status_url", lambda: "")

    assert gpu_watchdog.gpu_round_idle(job_kind="raptor", lease=_lease()) is False


def test_round_idle_blocks_on_invalid_response(monkeypatch):
    """响应缺少 active_jobs 或类型非法：不得确认。"""
    monkeypatch.setattr(
        gpu_watchdog,
        "_sidecar_status_url",
        lambda: "http://filex-mineru:8080/lifecycle/status",
    )

    for body in (
        {"status": "ok"},
        {"status": "ok", "active_jobs": "nope"},
        {"status": "ok", "active_jobs": None},
    ):
        monkeypatch.setattr(
            gpu_watchdog, "_fetch_sidecar_status", lambda url, _body=body: _body
        )
        assert gpu_watchdog.gpu_round_idle(job_kind="raptor", lease=_lease()) is False
