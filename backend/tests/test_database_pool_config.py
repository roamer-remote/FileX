# Copyright (c) 2026 徐泽宇
"""DATABASE_POOL_* 环境变量解析。"""

import importlib


def _reload_config(monkeypatch, **env):
    for key, value in env.items():
        if value is None:
            monkeypatch.delenv(key, raising=False)
        else:
            monkeypatch.setenv(key, value)
    import config

    return importlib.reload(config)


def test_database_pool_defaults(monkeypatch):
    cfg = _reload_config(
        monkeypatch,
        DATABASE_POOL_SIZE=None,
        DATABASE_MAX_OVERFLOW=None,
        DATABASE_POOL_TIMEOUT=None,
    )
    assert cfg.DATABASE_POOL_SIZE == 5
    assert cfg.DATABASE_MAX_OVERFLOW == 10
    assert cfg.DATABASE_POOL_TIMEOUT == 30.0


def test_database_pool_from_env(monkeypatch):
    cfg = _reload_config(
        monkeypatch,
        DATABASE_POOL_SIZE="12",
        DATABASE_MAX_OVERFLOW="28",
        DATABASE_POOL_TIMEOUT="45",
    )
    assert cfg.DATABASE_POOL_SIZE == 12
    assert cfg.DATABASE_MAX_OVERFLOW == 28
    assert cfg.DATABASE_POOL_TIMEOUT == 45.0


def test_database_pool_clamps_invalid(monkeypatch):
    cfg = _reload_config(
        monkeypatch,
        DATABASE_POOL_SIZE="0",
        DATABASE_MAX_OVERFLOW="-3",
        DATABASE_POOL_TIMEOUT="0",
    )
    assert cfg.DATABASE_POOL_SIZE == 1
    assert cfg.DATABASE_MAX_OVERFLOW == 0
    assert cfg.DATABASE_POOL_TIMEOUT == 1.0
