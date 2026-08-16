# Copyright (c) 2026 徐泽宇
"""Unit tests for skill_repository disk mirror.

Authors:
    徐泽宇

Copyright:
    © 2026 徐泽宇
"""

import zipfile
from io import BytesIO

from models.skill_file import SkillFile
from services.skill_repository import (
    build_manifest_dict,
    build_zip_bytes,
    get_head,
    is_data_ready,
    replace_all_from_disk,
)
from utils.pubmed_skill import build_pubmed_skill_zip, resolve_pubmed_skill_dir, scan_skill_disk


def _write_minimal_skill_tree(skill_dir) -> None:
    skill_dir.mkdir(parents=True, exist_ok=True)
    (skill_dir / "SKILL.md").write_text("# bootstrap\n", encoding="utf-8")
    (skill_dir / "skill.version").write_text("9.9.9-test\n", encoding="utf-8")
    (skill_dir / "skill.meta.json").write_text('{"bootstrap_min_version":"2.0.0"}\n', encoding="utf-8")
    ref_dir = skill_dir / "references"
    ref_dir.mkdir()
    (ref_dir / "filex-agent-api.md").write_text("# api\n", encoding="utf-8")
    (ref_dir / "extra.md").write_text("# extra ref\n", encoding="utf-8")
    nested = skill_dir / "modules" / "nested"
    nested.mkdir(parents=True)
    (nested / "x.md").write_text("# nested module\n", encoding="utf-8")
    (skill_dir / "modules" / "flat.md").write_text("# flat\n", encoding="utf-8")
    agent = skill_dir / "agent"
    agent.mkdir()
    (agent / "foo.py").write_text("print(1)\n", encoding="utf-8")
    (agent / "readme.md").write_text("# agent only\n", encoding="utf-8")
    cache = skill_dir / "agent" / "__pycache__"
    cache.mkdir()
    (cache / "foo.pyc").write_bytes(b"\x00\x01")


def test_replace_all_from_disk_populates(seeded_skill_db):
    db = seeded_skill_db
    assert is_data_ready(db)
    manifest = build_manifest_dict(db)
    assert manifest is not None
    assert "kb-search" in manifest["modules"]


def test_replace_overwrites_content(seeded_skill_db):
    db = seeded_skill_db
    row = get_head(db, "module:kb-search")
    assert row is not None
    row.content = "# stale\n"
    db.flush()
    replace_all_from_disk(db, commit=False)
    db.refresh(row)
    assert "# stale" not in row.content


def test_replace_removes_stale_module_row(seeded_skill_db):
    db = seeded_skill_db
    db.add(
        SkillFile(
            file_id="module:ghost-removed-by-test",
            kind="markdown",
            label="modules/ghost.md",
            relative_path="modules/ghost.md",
            content="# ghost\n",
            content_sha256="0" * 64,
            etag='"0000000000000000"',
            revision=1,
        )
    )
    db.flush()
    result = replace_all_from_disk(db, commit=False)
    assert "module:ghost-removed-by-test" in result["removed"]
    assert get_head(db, "module:ghost-removed-by-test") is None


def test_scan_includes_modules_without_registry(seeded_skill_db):
    skill_dir = resolve_pubmed_skill_dir()
    assert skill_dir is not None
    ids = {e.file_id for e in scan_skill_disk(skill_dir)}
    assert "module:url-ingest" in ids
    assert "bootstrap" in ids


def test_scan_recursive_includes_and_excludes(tmp_path):
    skill = tmp_path / "ding"
    _write_minimal_skill_tree(skill)
    entries = scan_skill_disk(skill)
    ids = {e.file_id for e in entries}
    rels = {e.relative_path for e in entries}
    assert "path:references/extra.md" in ids
    assert "module:nested/x" in ids
    assert "module:flat" in ids
    assert not any(r.startswith("agent/") for r in rels)


def test_build_zip_includes_references_extra(tmp_path):
    skill = tmp_path / "ding"
    _write_minimal_skill_tree(skill)
    data = build_pubmed_skill_zip(skill)
    assert data is not None
    zf = zipfile.ZipFile(BytesIO(data))
    names = zf.namelist()
    assert "ding/references/extra.md" in names
    assert "ding/modules/nested/x.md" in names


def test_build_zip_excludes_maintainer_eval_artifacts(tmp_path):
    skill = tmp_path / "ding"
    _write_minimal_skill_tree(skill)
    evals = skill / "evals" / "results"
    evals.mkdir(parents=True)
    (evals / "benchmark.json").write_text("{}\n", encoding="utf-8")

    data = build_pubmed_skill_zip(skill)
    assert data is not None
    names = zipfile.ZipFile(BytesIO(data)).namelist()
    assert "ding/evals/results/benchmark.json" not in names
    assert "ding/SKILL.md" in names


def test_build_zip_excludes_case_variant_eval_artifacts(tmp_path):
    skill = tmp_path / "ding"
    _write_minimal_skill_tree(skill)
    evals = skill / "Evals" / "results"
    evals.mkdir(parents=True)
    (evals / "benchmark.json").write_text("{}\n", encoding="utf-8")

    data = build_pubmed_skill_zip(skill)
    assert data is not None
    names = zipfile.ZipFile(BytesIO(data)).namelist()
    assert "ding/Evals/results/benchmark.json" not in names


def test_replace_skills_only_bootstrap_does_not_wipe_modules(seeded_skill_db, tmp_path, monkeypatch):
    db = seeded_skill_db
    before = db.query(SkillFile).count()
    assert before > 1
    minimal = tmp_path / "ding"
    minimal.mkdir()
    (minimal / "SKILL.md").write_text("# only bootstrap\n", encoding="utf-8")
    monkeypatch.setenv("FILEX_SKILL_DIR", str(minimal))
    result = replace_all_from_disk(db, commit=False)
    assert result["reason"] == "scan_no_modules"
    assert result["removed"] == []
    assert db.query(SkillFile).count() == before


def test_replace_from_disk_includes_path_files(tmp_path, monkeypatch, db_session):
    skill = tmp_path / "ding"
    _write_minimal_skill_tree(skill)
    monkeypatch.setenv("FILEX_SKILL_DIR", str(skill))
    db_session.query(SkillFile).delete()
    db_session.flush()
    result = replace_all_from_disk(db_session, commit=False)
    assert "path:references/extra.md" in result["synced"]
    assert get_head(db_session, "module:nested/x") is not None
    z = build_zip_bytes(db_session)
    assert z is not None
    names = zipfile.ZipFile(BytesIO(z)).namelist()
    assert "ding/references/extra.md" in names
