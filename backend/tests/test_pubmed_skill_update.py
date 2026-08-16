# Copyright (c) 2026 徐泽宇
"""Tests for GET /filex-skill-update (pubmed skill zip bundle).

Authors:
    徐泽宇

Copyright:
    © 2026 徐泽宇
"""

import zipfile
from io import BytesIO


def test_pubmed_skill_update_zip(client, seeded_skill_db):
    r = client.get("/filex-skill-update")
    assert r.status_code == 200
    assert r.headers.get("content-type", "").startswith("application/zip")
    cd = r.headers.get("content-disposition", "")
    assert "filex-skill.zip" in cd
    zf = zipfile.ZipFile(BytesIO(r.content))
    names = zf.namelist()
    assert any(n.endswith("SKILL.md") for n in names)
    assert any("references/" in n for n in names)


def test_pubmed_skill_update_503_when_not_seeded(client, db_session, monkeypatch):
    monkeypatch.setattr("main.skill_runtime.data_ready", lambda _db: False)
    r = client.get("/filex-skill-update")
    assert r.status_code == 503
