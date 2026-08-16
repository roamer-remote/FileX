# Copyright (c) 2026 徐泽宇
"""生产环境密钥校验。"""

import pytest

from config import validate_production_secrets, _DEFAULT_SECRET_KEY


def test_validate_production_secrets_allows_development_default(monkeypatch):
    monkeypatch.setenv("FILEX_ENV", "development")
    monkeypatch.delenv("FILEX_SECRET_KEY", raising=False)
    validate_production_secrets()


def test_validate_production_secrets_rejects_default_in_production(monkeypatch):
    monkeypatch.delenv("FILEX_ENV", raising=False)
    monkeypatch.setenv("FILEX_SECRET_KEY", _DEFAULT_SECRET_KEY)
    with pytest.raises(RuntimeError, match="FILEX_SECRET_KEY"):
        validate_production_secrets()


def test_validate_production_secrets_allows_custom_key(monkeypatch):
    monkeypatch.delenv("FILEX_ENV", raising=False)
    monkeypatch.setenv("FILEX_SECRET_KEY", "custom-production-secret")
    validate_production_secrets()
