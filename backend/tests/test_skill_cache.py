# Copyright (c) 2026 徐泽宇
"""Tests for skill Redis cache (fakeredis).

Authors:
    徐泽宇

Copyright:
    © 2026 徐泽宇
"""

import json

import pytest

fakeredis = pytest.importorskip("fakeredis")


def test_cache_warm_and_get(seeded_skill_db, monkeypatch):
    from services import skill_cache_service as cache
    from services import skill_repository as repo

    fake = fakeredis.FakeRedis(decode_responses=True)
    monkeypatch.setattr(cache, "_get_client", lambda: fake)
    monkeypatch.setattr(cache, "enabled", lambda: True)
    assert cache.warm_all(seeded_skill_db)
    manifest = cache.get_manifest(seeded_skill_db)
    assert manifest and manifest.get("skill_version")
    payload = cache.get_file(seeded_skill_db, "bootstrap")
    assert payload and payload.get("content")
    raw = fake.get("filex:skill:manifest")
    assert raw and json.loads(raw)
