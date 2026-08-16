# Copyright (c) 2026 徐泽宇
"""生产环境关闭 OpenAPI / Swagger / Scalar 文档。

Authors:
    徐泽宇

Copyright:
    © 2026 徐泽宇
"""

import importlib


def test_openapi_enabled_only_in_development(monkeypatch):
    import config

    monkeypatch.delenv("FILEX_ENV", raising=False)
    importlib.reload(config)
    assert config.OPENAPI_ENABLED is False

    monkeypatch.setenv("FILEX_ENV", "production")
    importlib.reload(config)
    assert config.OPENAPI_ENABLED is False

    monkeypatch.setenv("FILEX_ENV", "development")
    importlib.reload(config)
    assert config.OPENAPI_ENABLED is True


def test_openapi_routes_absent_when_not_development(monkeypatch):
    monkeypatch.delenv("FILEX_ENV", raising=False)
    import config
    import main

    importlib.reload(config)
    importlib.reload(main)

    from fastapi.testclient import TestClient

    client = TestClient(main.app)
    assert client.get("/openapi.json").status_code == 404
    assert client.get("/docs").status_code == 404
    assert client.get("/redoc").status_code == 404


def test_openapi_routes_present_in_development(monkeypatch):
    monkeypatch.setenv("FILEX_ENV", "development")
    import config
    import main

    importlib.reload(config)
    importlib.reload(main)

    from fastapi.testclient import TestClient

    client = TestClient(main.app)
    assert client.get("/openapi.json").status_code == 200
    assert client.get("/doc").status_code == 200
