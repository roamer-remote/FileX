# Copyright (c) 2026 徐泽宇
"""036: per-user KB preference overrides."""

from unittest.mock import patch

import pytest

from services.system_setting_service import (
    KEY_KB_SEARCH_MIN_SCORE,
    invalidate_settings_cache,
    update_settings,
)
from services.user_setting_service import (
    USER_SETTING_KEYS,
    get_user_effective_dict,
    get_user_overrides_dict,
    reset_user_settings,
    update_user_settings,
)


def _auth_headers(jwt_token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {jwt_token}"}


def test_user_preferences_inherit_system_defaults(client, jwt_token, db_session, regular_user):
    headers = _auth_headers(jwt_token)
    r = client.get("/api/settings/user-preferences", headers=headers)
    assert r.status_code == 200, r.text
    body = r.json()
    assert len(body["effective"]) == len(USER_SETTING_KEYS)
    assert body["overrides"] == {}
    assert set(body["inherited_keys"]) == set(USER_SETTING_KEYS)
    assert "workspace_backup_max_mb" not in body["effective"]
    system_eff = get_user_effective_dict(db_session, regular_user.id)
    assert body["effective"][KEY_KB_SEARCH_MIN_SCORE] == float(system_eff[KEY_KB_SEARCH_MIN_SCORE])


def test_put_single_override(client, jwt_token, db_session):
    headers = _auth_headers(jwt_token)
    r = client.put(
        "/api/settings/user-preferences",
        headers=headers,
        json={"kb_search_min_score": 0.55},
    )
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["overrides"] == {"kb_search_min_score": "0.55"}
    assert body["effective"]["kb_search_min_score"] == 0.55
    assert KEY_KB_SEARCH_MIN_SCORE in body["inherited_keys"] or "kb_search_min_score" not in body["inherited_keys"]
    assert "kb_search_min_score" not in body["inherited_keys"]


def test_reset_clears_overrides(client, jwt_token):
    headers = _auth_headers(jwt_token)
    client.put(
        "/api/settings/user-preferences",
        headers=headers,
        json={"kb_search_min_score": 0.55},
    )
    r = client.post("/api/settings/user-preferences/reset", headers=headers, json={})
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["overrides"] == {}
    assert set(body["inherited_keys"]) == set(USER_SETTING_KEYS)


def test_put_unknown_key_rejected(client, jwt_token):
    headers = _auth_headers(jwt_token)
    r = client.put(
        "/api/settings/user-preferences",
        headers=headers,
        json={"max_upload_size_mb": 99},
    )
    assert r.status_code in (400, 422), r.text


def test_reset_unknown_keys_rejected(client, jwt_token):
    headers = _auth_headers(jwt_token)
    r = client.post(
        "/api/settings/user-preferences/reset",
        headers=headers,
        json={"keys": ["max_upload_size_mb"]},
    )
    assert r.status_code == 400, r.text


def test_admin_system_change_followed_by_unoverridden_user(client, jwt_token, db_session, regular_user):
    headers = _auth_headers(jwt_token)
    invalidate_settings_cache()
    update_settings(db_session, {KEY_KB_SEARCH_MIN_SCORE: "0.25"})
    r1 = client.get("/api/settings/user-preferences", headers=headers)
    assert r1.json()["effective"]["kb_search_min_score"] == 0.25

    update_user_settings(db_session, regular_user.id, {KEY_KB_SEARCH_MIN_SCORE: 0.6})
    invalidate_settings_cache()
    update_settings(db_session, {KEY_KB_SEARCH_MIN_SCORE: "0.3"})
    eff = get_user_effective_dict(db_session, regular_user.id)
    assert eff[KEY_KB_SEARCH_MIN_SCORE] == "0.6"

    reset_user_settings(db_session, regular_user.id, [KEY_KB_SEARCH_MIN_SCORE])
    eff2 = get_user_effective_dict(db_session, regular_user.id)
    assert eff2[KEY_KB_SEARCH_MIN_SCORE] == "0.3"


def test_clipboard_uses_user_effective(client, jwt_token, db_session, regular_user):
    headers = _auth_headers(jwt_token)
    update_user_settings(db_session, regular_user.id, {"kb_voice_notify_enabled": False})
    r = client.get("/api/settings/clipboard", headers=headers)
    assert r.status_code == 200, r.text
    assert r.json()["kb_voice_notify_enabled"] is False


def test_redis_cache_invalidate_on_update(db_session, regular_user):
    from services.user_settings_cache_service import (
        get_cached_user_overrides,
        invalidate_user_settings_cache,
        warm_user_settings_cache,
    )

    warm_user_settings_cache(db_session, regular_user.id)
    update_user_settings(db_session, regular_user.id, {KEY_KB_SEARCH_MIN_SCORE: 0.42})
    overrides = get_cached_user_overrides(db_session, regular_user.id)
    assert overrides[KEY_KB_SEARCH_MIN_SCORE] == "0.42"
    invalidate_user_settings_cache(regular_user.id)
    reset_user_settings(db_session, regular_user.id, None)
    overrides2 = get_cached_user_overrides(db_session, regular_user.id)
    assert KEY_KB_SEARCH_MIN_SCORE not in overrides2


def test_search_kb_loads_effective_once(db_session, regular_user, monkeypatch):
    calls = {"n": 0}
    real = get_user_effective_dict

    def counted(db, user_id):
        calls["n"] += 1
        return real(db, user_id)

    monkeypatch.setattr("services.kb_search_service.get_user_effective_dict", counted)
    from services.kb_search_service import search_kb

    try:
        search_kb(db_session, regular_user.id, "test query", top_k=1)
    except Exception:
        pass
    assert calls["n"] == 1


def test_different_users_different_min_score(db_session, regular_user, admin_user):
    update_user_settings(db_session, regular_user.id, {KEY_KB_SEARCH_MIN_SCORE: 0.8})
    update_user_settings(db_session, admin_user.id, {KEY_KB_SEARCH_MIN_SCORE: 0.1})
    a = get_user_effective_dict(db_session, regular_user.id)
    b = get_user_effective_dict(db_session, admin_user.id)
    assert a[KEY_KB_SEARCH_MIN_SCORE] == "0.8"
    assert b[KEY_KB_SEARCH_MIN_SCORE] == "0.1"


def test_sparse_put_equal_system_value(client, jwt_token, db_session, regular_user):
    eff = get_user_effective_dict(db_session, regular_user.id)
    default_score = float(eff[KEY_KB_SEARCH_MIN_SCORE])
    headers = _auth_headers(jwt_token)
    r = client.put(
        "/api/settings/user-preferences",
        headers=headers,
        json={"kb_search_min_score": default_score},
    )
    assert r.status_code == 200, r.text
    assert r.json()["overrides"] == {}


def test_sparse_put_clears_override_when_reverted_to_system(client, jwt_token, db_session, regular_user):
    from services.system_setting_service import DEFAULTS, _parse_kb_search_min_score, get_public_settings_dict

    headers = _auth_headers(jwt_token)
    client.put(
        "/api/settings/user-preferences",
        headers=headers,
        json={"kb_search_min_score": 0.55},
    )
    system = get_public_settings_dict(db_session)
    default_score = _parse_kb_search_min_score(
        system.get(KEY_KB_SEARCH_MIN_SCORE, DEFAULTS[KEY_KB_SEARCH_MIN_SCORE])
    )
    r = client.put(
        "/api/settings/user-preferences",
        headers=headers,
        json={"kb_search_min_score": default_score},
    )
    assert r.status_code == 200, r.text
    assert r.json()["overrides"] == {}


def test_kb_search_default_top_k_user_effective(db_session, regular_user, admin_user):
    from services.system_setting_service import get_kb_search_default_top_k

    update_user_settings(db_session, regular_user.id, {"kb_search_default_top_k": 12})
    update_user_settings(db_session, admin_user.id, {"kb_search_default_top_k": 20})
    eff_a = get_user_effective_dict(db_session, regular_user.id)
    eff_b = get_user_effective_dict(db_session, admin_user.id)
    assert get_kb_search_default_top_k(db_session, effective=eff_a) == 12
    assert get_kb_search_default_top_k(db_session, effective=eff_b) == 20


def test_search_kb_uses_user_default_top_k(db_session, regular_user, monkeypatch):
    from config import OLLAMA_EMBED_DIM
    from services.kb_search_service import search_kb

    update_user_settings(db_session, regular_user.id, {"kb_search_default_top_k": 15})
    monkeypatch.setattr("services.kb_search_service.embed_text", lambda q: [0.1] * OLLAMA_EMBED_DIM)
    _, _, k, _ = search_kb(db_session, regular_user.id, "test query", top_k=None)
    assert k == 15


def test_build_user_preferences_payload_single_overrides_load(db_session, regular_user, monkeypatch):
    from services.user_setting_service import build_user_preferences_payload

    calls = {"n": 0}
    real = get_user_overrides_dict

    def counted(db, uid):
        calls["n"] += 1
        return real(db, uid)

    monkeypatch.setattr("services.user_setting_service.get_user_overrides_dict", counted)
    build_user_preferences_payload(db_session, regular_user.id)
    assert calls["n"] == 1


# 153: per-user override of voice playback TTL — inherit / override / revert to system
def test_user_voice_playback_ttl_inherits_system_default(client, jwt_token, db_session, regular_user):
    from services.system_setting_service import (
        KEY_KB_VOICE_NOTIFY_PLAYBACK_TTL_SECONDS,
        invalidate_settings_cache,
    )

    invalidate_settings_cache()
    headers = {"Authorization": f"Bearer {jwt_token}"}
    r = client.get("/api/settings/user-preferences", headers=headers)
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["effective"][KEY_KB_VOICE_NOTIFY_PLAYBACK_TTL_SECONDS] == 120
    assert body["overrides"] == {}
    assert KEY_KB_VOICE_NOTIFY_PLAYBACK_TTL_SECONDS in body["inherited_keys"]


def test_user_voice_playback_ttl_override_and_revert(client, jwt_token, db_session, regular_user):
    from services.system_setting_service import (
        KEY_KB_VOICE_NOTIFY_PLAYBACK_TTL_SECONDS,
        invalidate_settings_cache,
    )

    invalidate_settings_cache()
    headers = {"Authorization": f"Bearer {jwt_token}"}

    r_put = client.put(
        "/api/settings/user-preferences",
        headers=headers,
        json={"kb_voice_notify_playback_ttl_seconds": 60},
    )
    assert r_put.status_code == 200, r_put.text
    body = r_put.json()
    assert body["overrides"][KEY_KB_VOICE_NOTIFY_PLAYBACK_TTL_SECONDS] == "60"
    assert body["effective"][KEY_KB_VOICE_NOTIFY_PLAYBACK_TTL_SECONDS] == 60
    assert KEY_KB_VOICE_NOTIFY_PLAYBACK_TTL_SECONDS not in body["inherited_keys"]

    # revert to system value should clear the override
    r_revert = client.put(
        "/api/settings/user-preferences",
        headers=headers,
        json={"kb_voice_notify_playback_ttl_seconds": 120},
    )
    assert r_revert.status_code == 200, r_revert.text
    body2 = r_revert.json()
    assert KEY_KB_VOICE_NOTIFY_PLAYBACK_TTL_SECONDS not in body2["overrides"]
    assert body2["effective"][KEY_KB_VOICE_NOTIFY_PLAYBACK_TTL_SECONDS] == 120
    assert KEY_KB_VOICE_NOTIFY_PLAYBACK_TTL_SECONDS in body2["inherited_keys"]


def test_user_voice_playback_ttl_rejects_out_of_range(client, jwt_token):
    headers = {"Authorization": f"Bearer {jwt_token}"}
    r = client.put(
        "/api/settings/user-preferences",
        headers=headers,
        json={"kb_voice_notify_playback_ttl_seconds": 3601},
    )
    assert r.status_code == 422, r.text
