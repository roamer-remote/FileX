# Copyright (c) 2026 徐泽宇
"""Tests for /api/filex-skill manifest and module runtime endpoints.

Authors:
    徐泽宇

Copyright:
    © 2026 徐泽宇
"""

import hashlib
import json

import pytest

def test_filex_skill_manifest_requires_auth(client, seeded_skill_db):
    r = client.get("/api/filex-skill/manifest")
    assert r.status_code == 401


def test_filex_skill_manifest_ok(client, active_api_key, seeded_skill_db):
    r = client.get(
        "/api/filex-skill/manifest",
        headers={"Authorization": f"Bearer {active_api_key._plaintext}"},
    )
    assert r.status_code == 200
    data = r.json()
    assert data["schema_version"] == 2
    assert "skill_version" in data
    assert "modules" in data
    assert "kb-search" in data["modules"]
    kb_module = data["modules"]["kb-search"]
    assert kb_module["requires_api_key"] is True
    assert kb_module["fallback_allowed"] is True
    assert kb_module["min_agent_version"] == "2.0.0"
    assert kb_module["depends_on"] == ["preflight", "routing"]
    assert data["modules"]["research"]["requires_api_key"] is False
    for module in data["modules"].values():
        assert module["capabilities"]


def test_filex_skill_manifest_zip_hashes_match_update_endpoints(client, active_api_key, seeded_skill_db):
    manifest = client.get(
        "/api/filex-skill/manifest",
        headers={"Authorization": f"Bearer {active_api_key._plaintext}"},
    )
    assert manifest.status_code == 200

    skill_zip = client.get("/filex-skill-update")
    assert skill_zip.status_code == 200
    agent_zip = client.get("/filex-skill-agent-update")
    assert agent_zip.status_code == 200

    data = manifest.json()
    assert data["skill_zip_sha256"] == hashlib.sha256(skill_zip.content).hexdigest()
    assert data["agent_zip_sha256"] == hashlib.sha256(agent_zip.content).hexdigest()
    assert data["agent_version"].startswith(f"{data['skill_version']}+agent.")


def test_manifest_module_contracts_match_served_content(client, active_api_key, seeded_skill_db):
    manifest = client.get(
        "/api/filex-skill/manifest",
        headers={"Authorization": f"Bearer {active_api_key._plaintext}"},
    ).json()
    for module_id, contract in manifest["modules"].items():
        response = client.get(
            contract["url"],
            headers={"Authorization": f"Bearer {active_api_key._plaintext}"},
        )
        assert response.status_code == 200, module_id
        assert contract["sha256"] == hashlib.sha256(response.content).hexdigest()
        assert contract["etag"] == response.headers["ETag"]


def test_filex_skill_manifest_agent_version_tracks_agent_zip(monkeypatch, seeded_skill_db):
    from services import skill_repository as repo

    first = b"agent zip with first MCP source"
    second = b"agent zip with second MCP source"
    monkeypatch.setattr(repo, "_build_agent_zip_bytes_from_disk", lambda: first)
    first_manifest = repo.build_manifest_dict(seeded_skill_db)
    monkeypatch.setattr(repo, "_build_agent_zip_bytes_from_disk", lambda: second)
    second_manifest = repo.build_manifest_dict(seeded_skill_db)

    assert first_manifest is not None
    assert second_manifest is not None
    assert first_manifest["agent_zip_sha256"] != second_manifest["agent_zip_sha256"]
    assert first_manifest["agent_version"] != second_manifest["agent_version"]


def test_manifest_cache_refreshes_agent_fields_after_explicit_warm(
    client, active_api_key, seeded_skill_db, monkeypatch
):
    from services import skill_cache_service as cache
    from services import skill_repository as repo

    fakeredis = pytest.importorskip("fakeredis")
    fake = fakeredis.FakeRedis(decode_responses=True)
    before = b"agent zip with old MCP source"
    after = b"agent zip with new MCP source"
    monkeypatch.setattr(cache, "_get_client", lambda: fake)
    monkeypatch.setattr(cache, "enabled", lambda: True)
    monkeypatch.setattr(repo, "_build_agent_zip_bytes_from_disk", lambda: before)
    stale_manifest = repo.build_manifest_dict(seeded_skill_db)
    assert stale_manifest is not None
    fake.set(cache.MANIFEST_KEY, json.dumps(stale_manifest))

    monkeypatch.setattr(repo, "_build_agent_zip_bytes_from_disk", lambda: after)
    assert cache.warm_all(seeded_skill_db)
    manifest = client.get(
        "/api/filex-skill/manifest",
        headers={"Authorization": f"Bearer {active_api_key._plaintext}"},
    )
    agent_zip = client.get("/filex-skill-agent-update")

    assert manifest.status_code == 200
    assert agent_zip.status_code == 200
    data = manifest.json()
    assert data["agent_zip_sha256"] == hashlib.sha256(agent_zip.content).hexdigest()
    assert data["agent_zip_sha256"] == hashlib.sha256(after).hexdigest()
    assert data["agent_version"].endswith(hashlib.sha256(after).hexdigest()[:12])


def test_manifest_redis_hit_does_not_rebuild_agent_zip(
    client, active_api_key, seeded_skill_db, monkeypatch
):
    from services import skill_cache_service as cache
    from services import skill_repository as repo

    fakeredis = pytest.importorskip("fakeredis")
    fake = fakeredis.FakeRedis(decode_responses=True)
    monkeypatch.setattr(cache, "_get_client", lambda: fake)
    monkeypatch.setattr(cache, "enabled", lambda: True)
    manifest = repo.build_manifest_dict(seeded_skill_db)
    assert manifest is not None
    fake.set(cache.MANIFEST_KEY, json.dumps(manifest))

    def fail_if_rebuilt(_skill_version):
        raise AssertionError("Redis manifest hit must not rebuild the agent zip")

    monkeypatch.setattr(repo, "build_agent_manifest_fields", fail_if_rebuilt)
    response = client.get(
        "/api/filex-skill/manifest",
        headers={"Authorization": f"Bearer {active_api_key._plaintext}"},
    )
    assert response.status_code == 200


def test_manifest_cache_rebuilds_old_schema(monkeypatch, seeded_skill_db):
    from services import skill_cache_service as cache
    from services import skill_repository as repo

    fakeredis = pytest.importorskip("fakeredis")
    fake = fakeredis.FakeRedis(decode_responses=True)
    monkeypatch.setattr(cache, "_get_client", lambda: fake)
    monkeypatch.setattr(cache, "enabled", lambda: True)
    monkeypatch.setattr(cache, "_LOCAL_MANIFEST_KEY", None)
    monkeypatch.setattr(cache, "_LOCAL_MANIFEST", None)
    fresh = repo.build_manifest_dict(seeded_skill_db)
    assert fresh is not None
    stale = dict(fresh)
    stale["schema_version"] = 1
    fake.set(cache.MANIFEST_KEY, json.dumps(stale))
    calls = 0
    original = repo.build_manifest_dict

    def rebuild(db):
        nonlocal calls
        calls += 1
        return original(db)

    monkeypatch.setattr(repo, "build_manifest_dict", rebuild)
    result = cache.get_manifest(seeded_skill_db)
    assert result is not None
    assert result["schema_version"] == 2
    assert calls >= 1


def test_manifest_cache_rebuilds_when_agent_source_fingerprint_changes(
    monkeypatch, seeded_skill_db
):
    from services import skill_cache_service as cache
    from services import skill_repository as repo

    fakeredis = pytest.importorskip("fakeredis")
    fake = fakeredis.FakeRedis(decode_responses=True)
    monkeypatch.setattr(cache, "_get_client", lambda: fake)
    monkeypatch.setattr(cache, "enabled", lambda: True)
    monkeypatch.setattr(cache, "_LOCAL_MANIFEST_KEY", None)
    monkeypatch.setattr(cache, "_LOCAL_MANIFEST", None)
    manifest = repo.build_manifest_dict(seeded_skill_db)
    assert manifest is not None
    fake.set(cache.MANIFEST_KEY, json.dumps(manifest))
    monkeypatch.setattr(repo, "agent_source_fingerprint", lambda: "changed-agent")
    calls = 0
    original = repo.build_manifest_dict

    def rebuild(db):
        nonlocal calls
        calls += 1
        return original(db)

    monkeypatch.setattr(repo, "build_manifest_dict", rebuild)
    result = cache.get_manifest(seeded_skill_db)
    assert result is not None
    assert calls >= 1


def test_filex_skill_module_ok(client, active_api_key, seeded_skill_db):
    r = client.get(
        "/api/filex-skill/modules/kb-search",
        headers={"Authorization": f"Bearer {active_api_key._plaintext}"},
    )
    assert r.status_code == 200
    assert "text/markdown" in r.headers.get("content-type", "")
    assert r.headers.get("ETag")
    assert r.headers.get("X-Skill-Version")


def test_filex_skill_module_304(client, active_api_key, seeded_skill_db):
    r1 = client.get(
        "/api/filex-skill/modules/kb-search",
        headers={"Authorization": f"Bearer {active_api_key._plaintext}"},
    )
    etag = r1.headers.get("ETag")
    r2 = client.get(
        "/api/filex-skill/modules/kb-search",
        headers={"Authorization": f"Bearer {active_api_key._plaintext}", "If-None-Match": etag},
    )
    assert r2.status_code == 304


def test_filex_skill_nested_module(tmp_path, monkeypatch, client, active_api_key, db_session):
    from models.skill_file import SkillFile
    from services.skill_repository import replace_all_from_disk
    from tests.test_skill_repository import _write_minimal_skill_tree

    skill = tmp_path / "ding"
    _write_minimal_skill_tree(skill)
    monkeypatch.setenv("FILEX_SKILL_DIR", str(skill))
    db_session.query(SkillFile).delete()
    db_session.commit()
    replace_all_from_disk(db_session, commit=True)
    r = client.get(
        "/api/filex-skill/modules/nested/x",
        headers={"Authorization": f"Bearer {active_api_key._plaintext}"},
    )
    assert r.status_code == 200
    assert b"nested module" in r.content
    manifest = client.get(
        "/api/filex-skill/manifest",
        headers={"Authorization": f"Bearer {active_api_key._plaintext}"},
    )
    assert "nested/x" in manifest.json()["modules"]


def test_filex_skill_module_unknown(client, active_api_key, seeded_skill_db):
    r = client.get(
        "/api/filex-skill/modules/no-such-module",
        headers={"Authorization": f"Bearer {active_api_key._plaintext}"},
    )
    assert r.status_code == 404


def test_filex_skill_api_reference_ok(client, active_api_key, seeded_skill_db):
    r = client.get(
        "/api/filex-skill/references/filex-agent-api",
        headers={"Authorization": f"Bearer {active_api_key._plaintext}"},
    )
    assert r.status_code == 200
    assert len(r.content) > 100


def test_filex_skill_manifest_503_when_not_seeded(client, active_api_key, db_session, monkeypatch):
    monkeypatch.setattr("routers.filex_skill.runtime.data_ready", lambda _db: False)
    r = client.get(
        "/api/filex-skill/manifest",
        headers={"Authorization": f"Bearer {active_api_key._plaintext}"},
    )
    assert r.status_code == 503
