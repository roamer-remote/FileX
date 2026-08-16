# Copyright (c) 2026 徐泽宇
"""pdf-inspector 开关迁移到系统参数表（默认关闭）+ redis 缓存。

Authors:
    徐泽宇

Copyright:
    © 2026 徐泽宇
"""

from unittest.mock import patch

from services.system_setting_service import (
    KEY_KB_PDF_INSPECTOR_ENABLED,
    get_kb_pdf_inspector_enabled,
    update_settings,
)


def test_admin_get_pdf_inspector_default_off(client, admin_jwt_token):
    headers = {"Authorization": f"Bearer {admin_jwt_token}"}
    r = client.get("/api/admin/system-settings", headers=headers)
    assert r.status_code == 200, r.text
    assert r.json()["kb_pdf_inspector_enabled"] is False


def test_admin_put_pdf_inspector_roundtrip(client, admin_jwt_token):
    headers = {"Authorization": f"Bearer {admin_jwt_token}"}
    r_put = client.put(
        "/api/admin/system-settings",
        headers=headers,
        json={"kb_pdf_inspector_enabled": True},
    )
    assert r_put.status_code == 200, r_put.text
    assert r_put.json()["kb_pdf_inspector_enabled"] is True

    r_get = client.get("/api/admin/system-settings", headers=headers)
    assert r_get.status_code == 200, r_get.text
    assert r_get.json()["kb_pdf_inspector_enabled"] is True


def test_admin_put_invalid_pdf_inspector(client, admin_jwt_token):
    headers = {"Authorization": f"Bearer {admin_jwt_token}"}
    r = client.put(
        "/api/admin/system-settings",
        headers=headers,
        json={"kb_pdf_inspector_enabled": "not-a-bool"},
    )
    assert r.status_code == 422, r.text


def test_get_kb_pdf_inspector_enabled_default_off(db_session):
    assert get_kb_pdf_inspector_enabled(db_session) is False


def test_get_kb_pdf_inspector_enabled_after_update(db_session):
    update_settings(db_session, {KEY_KB_PDF_INSPECTOR_ENABLED: "true"})
    assert get_kb_pdf_inspector_enabled(db_session) is True


def test_switch_service_default_off_without_db():
    from services.pdf_inspector_switch_service import get_pdf_inspector_enabled

    with patch("services.pdf_inspector_switch_service.enabled", return_value=False):
        assert get_pdf_inspector_enabled(db=None) is False


def test_switch_service_reads_db_when_available(db_session):
    from services.pdf_inspector_switch_service import get_pdf_inspector_enabled

    update_settings(db_session, {KEY_KB_PDF_INSPECTOR_ENABLED: "true"})
    with patch("services.pdf_inspector_switch_service.enabled", return_value=False):
        assert get_pdf_inspector_enabled(db=db_session) is True


def test_switch_service_redis_hit():
    from services.pdf_inspector_switch_service import get_pdf_inspector_enabled

    fake_client = type("FakeRedis", (), {"get": lambda self, k: "true"})()
    with patch("services.pdf_inspector_switch_service.enabled", return_value=True), patch(
        "services.pdf_inspector_switch_service._get_client", return_value=fake_client
    ):
        assert get_pdf_inspector_enabled(db=None) is True


def test_switch_service_redis_miss_falls_back_to_db(db_session):
    from services.pdf_inspector_switch_service import get_pdf_inspector_enabled

    update_settings(db_session, {KEY_KB_PDF_INSPECTOR_ENABLED: "true"})
    fake_client = type("FakeRedis", (), {"get": lambda self, k: None})()
    with patch("services.pdf_inspector_switch_service.enabled", return_value=True), patch(
        "services.pdf_inspector_switch_service._get_client", return_value=fake_client
    ):
        assert get_pdf_inspector_enabled(db=db_session) is True
