# Copyright (c) 2026 徐泽宇
"""Tests for /api/admin/skill (read-only preview + disk sync).

Authors:
    徐泽宇

Copyright:
    © 2026 徐泽宇
"""

from models.skill_file import SkillFile


def test_list_requires_auth(client):
    r = client.get("/api/admin/skill/files")
    assert r.status_code == 401


def test_list_forbidden_for_regular_user(client, jwt_token, seeded_skill_db):
    r = client.get("/api/admin/skill/files", headers={"Authorization": f"Bearer {jwt_token}"})
    assert r.status_code == 403


def test_list_ok_for_admin(client, admin_jwt_token, seeded_skill_db):
    r = client.get("/api/admin/skill/files", headers={"Authorization": f"Bearer {admin_jwt_token}"})
    assert r.status_code == 200
    data = r.json()
    assert data["writable"] is False
    assert data["data_ready"] is True
    assert data["skill_version"]
    ids = {f["file_id"] for f in data["files"]}
    assert "bootstrap" in ids
    assert "module:kb-search" in ids
    assert "api-ref" in ids


def test_get_file_ok(client, admin_jwt_token, seeded_skill_db):
    r = client.get(
        "/api/admin/skill/files/bootstrap",
        headers={"Authorization": f"Bearer {admin_jwt_token}"},
    )
    assert r.status_code == 200
    assert r.json()["file_id"] == "bootstrap"
    assert "content" in r.json()


def test_put_removed(client, admin_jwt_token, seeded_skill_db):
    r = client.get(
        "/api/admin/skill/files/module:kb-search",
        headers={"Authorization": f"Bearer {admin_jwt_token}"},
    )
    etag = r.json()["etag"]
    r2 = client.put(
        "/api/admin/skill/files/module:kb-search",
        headers={"Authorization": f"Bearer {admin_jwt_token}", "If-Match": etag},
        json={"content": "# edited\n"},
    )
    assert r2.status_code == 405


def test_list_includes_references_group(tmp_path, monkeypatch, client, admin_jwt_token, db_session):
    from services.skill_repository import replace_all_from_disk
    from tests.test_skill_repository import _write_minimal_skill_tree

    skill = tmp_path / "ding"
    _write_minimal_skill_tree(skill)
    monkeypatch.setenv("FILEX_SKILL_DIR", str(skill))
    db_session.query(SkillFile).delete()
    db_session.commit()
    replace_all_from_disk(db_session, commit=True)
    r = client.get("/api/admin/skill/files", headers={"Authorization": f"Bearer {admin_jwt_token}"})
    assert r.status_code == 200
    groups = {f["group"] for f in r.json()["files"]}
    assert "references" in groups


def test_get_nested_module_file(client, admin_jwt_token, tmp_path, monkeypatch, db_session):
    from services.skill_repository import replace_all_from_disk
    from tests.test_skill_repository import _write_minimal_skill_tree

    skill = tmp_path / "ding"
    _write_minimal_skill_tree(skill)
    monkeypatch.setenv("FILEX_SKILL_DIR", str(skill))
    db_session.query(SkillFile).delete()
    db_session.commit()
    replace_all_from_disk(db_session, commit=True)
    r = client.get(
        "/api/admin/skill/files/module:nested/x",
        headers={"Authorization": f"Bearer {admin_jwt_token}"},
    )
    assert r.status_code == 200


def test_sync_from_disk_full_mirror(client, admin_jwt_token, seeded_skill_db):
    db = seeded_skill_db
    db.query(SkillFile).filter(SkillFile.file_id == "module:url-ingest").delete()
    db.commit()
    r0 = client.get("/api/admin/skill/files", headers={"Authorization": f"Bearer {admin_jwt_token}"})
    assert r0.status_code == 200
    r1 = client.post(
        "/api/admin/skill/sync-from-disk",
        headers={"Authorization": f"Bearer {admin_jwt_token}"},
    )
    assert r1.status_code == 200
    body = r1.json()
    assert body["data_ready"] is True
    assert "module:url-ingest" in body["synced"]
