# Copyright (c) 2026 徐泽宇
"""Tests for GET /filex-skill-agent-update (agent scripts zip).

Authors:
    徐泽宇

Copyright:
    © 2026 徐泽宇
"""

import hashlib
import os
import subprocess
import sys
import zipfile
from io import BytesIO
from pathlib import Path

import pytest

from utils import pubmed_skill


REPOSITORY_ROOT = Path(__file__).resolve().parents[2]
VERIFY_RELEASE = REPOSITORY_ROOT / "skill" / "ding" / "scripts" / "verify-release.sh"
VERIFY_RELEASE_ZIP_SMOKE = (
    REPOSITORY_ROOT / "skill" / "ding" / "scripts" / "verify_release_zip_smoke.py"
)


def _write_verify_release_runner(tmp_path: Path) -> tuple[Path, Path]:
    log_path = tmp_path / "gates.log"
    runner = tmp_path / "gate-runner"
    runner.write_text(
        "#!/bin/sh\n"
        "printf '%s\\n' \"$1\" >> \"$FILEX_DING_VERIFY_TEST_LOG\"\n"
        "if [ \"$1\" = \"${FILEX_DING_VERIFY_FAIL_GATE:-}\" ]; then\n"
        "  exit \"${FILEX_DING_VERIFY_FAIL_CODE:-1}\"\n"
        "fi\n",
        encoding="utf-8",
    )
    runner.chmod(0o755)
    return runner, log_path


def _run_verify_release_with_test_runner(
    tmp_path: Path,
    *,
    fail_gate: str = "",
    fail_code: int = 1,
) -> tuple[subprocess.CompletedProcess[str], list[str]]:
    runner, log_path = _write_verify_release_runner(tmp_path)
    completed = subprocess.run(
        [str(VERIFY_RELEASE)],
        cwd=tmp_path,
        env={
            **os.environ,
            "FILEX_DING_VERIFY_TEST_RUNNER": str(runner),
            "FILEX_DING_VERIFY_TEST_LOG": str(log_path),
            "FILEX_DING_VERIFY_FAIL_GATE": fail_gate,
            "FILEX_DING_VERIFY_FAIL_CODE": str(fail_code),
        },
        text=True,
        capture_output=True,
        check=False,
    )
    gates = log_path.read_text(encoding="utf-8").splitlines() if log_path.exists() else []
    return completed, gates


def test_verify_release_runs_every_gate_in_deterministic_order(tmp_path):
    completed, gates = _run_verify_release_with_test_runner(tmp_path)

    assert completed.returncode == 0, completed.stderr
    assert gates == [
        "check-version",
        "skill-eval",
        "dependency-install",
        "offline-evals",
        "agent-tests",
        "mcp-tests",
        "runtime-tests",
        "zip-smoke",
        "compileall",
        "markdown-links",
    ]


def test_verify_release_preserves_child_exit_and_stops_later_gates(tmp_path):
    completed, gates = _run_verify_release_with_test_runner(
        tmp_path,
        fail_gate="mcp-tests",
        fail_code=23,
    )

    assert completed.returncode == 23
    assert gates[-1] == "mcp-tests"
    assert "runtime-tests" not in gates
    assert "zip-smoke" not in gates


def test_verify_release_readme_has_one_release_entrypoint():
    readme = (REPOSITORY_ROOT / "skill" / "ding" / "README.md").read_text(encoding="utf-8")
    release_section = readme.split("## 发布检查（每次改 skill 必做）", 1)[1]

    assert "./skill/ding/scripts/verify-release.sh" in release_section
    assert "./skill/ding/scripts/check-version.sh" not in release_section
    assert "evals/run_evals.py" not in release_section


def test_verify_release_dependency_install_bypasses_stalled_system_proxy(tmp_path):
    env_log = tmp_path / "pip-env.log"
    fake_python = tmp_path / "python"
    fake_python.write_text(
        "#!/bin/sh\n"
        "if [ \"${1:-}\" = '-m' ] && [ \"${2:-}\" = 'venv' ]; then\n"
        "  mkdir -p \"$3/bin\"\n"
        "  cp \"$0\" \"$3/bin/python\"\n"
        "  chmod +x \"$3/bin/python\"\n"
        "  exit 0\n"
        "fi\n"
        "if [ \"${1:-}\" = '-m' ] && [ \"${2:-}\" = 'pip' ]; then\n"
        "  printf 'NO_PROXY=%s ARGS=%s\\n' \"${NO_PROXY:-}\" \"$*\" >> \"$FILEX_DING_VERIFY_PIP_ENV_LOG\"\n"
        "fi\n"
        "exit 0\n",
        encoding="utf-8",
    )
    fake_python.chmod(0o755)

    completed = subprocess.run(
        [str(VERIFY_RELEASE), "--dependency-install"],
        cwd=tmp_path,
        env={
            **os.environ,
            "FILEX_DING_VERIFY_PYTHON": str(fake_python),
            "FILEX_DING_VERIFY_PIP_ENV_LOG": str(env_log),
        },
        text=True,
        capture_output=True,
        check=False,
    )

    assert completed.returncode == 0, completed.stderr
    no_proxy = env_log.read_text(encoding="utf-8")
    assert "pypi.org" in no_proxy
    assert "files.pythonhosted.org" in no_proxy
    assert "pip download" in no_proxy
    assert "pypi.tuna.tsinghua.edu.cn/simple" in no_proxy
    assert "--find-links" in no_proxy
    assert "--no-index" in no_proxy


def test_verify_release_public_zip_smoke_isolated(tmp_path):
    completed = subprocess.run(
        [sys.executable, str(VERIFY_RELEASE_ZIP_SMOKE), "--work-dir", str(tmp_path / "smoke")],
        cwd=REPOSITORY_ROOT,
        text=True,
        capture_output=True,
        check=False,
    )

    assert completed.returncode == 0, completed.stderr
    assert not (tmp_path / "smoke" / "home" / ".codex" / "mcp.json").exists()
    last_line = completed.stdout.strip().splitlines()[-1]
    assert last_line.startswith("public zip smoke PASS: ")
    assert "elapsed_ms=" in last_line
    elapsed = int(last_line.rsplit("elapsed_ms=", 1)[-1])
    assert elapsed >= 0


def test_verify_release_lists_gates_in_documented_order():
    completed = subprocess.run(
        [str(VERIFY_RELEASE), "--list"],
        cwd=REPOSITORY_ROOT,
        text=True,
        capture_output=True,
        check=False,
    )

    assert completed.returncode == 0, completed.stderr
    expected = [
        "check-version",
        "skill-eval",
        "dependency-install",
        "offline-evals",
        "agent-tests",
        "mcp-tests",
        "runtime-tests",
        "zip-smoke",
        "compileall",
        "markdown-links",
    ]
    actual = [
        line.strip().lstrip("- ").strip()
        for line in completed.stdout.splitlines()
        if line.strip().startswith("- ")
    ]
    assert actual == expected


def test_filex_skill_agent_update_zip(client, seeded_skill_db):
    r = client.get("/filex-skill-agent-update")
    assert r.status_code == 200
    assert r.headers.get("content-type", "").startswith("application/zip")
    cd = r.headers.get("content-disposition", "")
    assert "filex-skill-agent.zip" in cd
    zf = zipfile.ZipFile(BytesIO(r.content))
    names = zf.namelist()
    assert any(n.endswith("ding/agent/filex_ingest_url.py") for n in names)
    assert any("requirements.txt" in n for n in names)
    assert not any("modules/" in n for n in names)


def test_agent_zip_contains_importable_mcp_source(client, seeded_skill_db, tmp_path):
    payload = client.get("/filex-skill-agent-update").content
    with zipfile.ZipFile(BytesIO(payload)) as archive:
        assert "ding/agent/mcp_src/filex_mcp_server/server.py" in archive.namelist()
        archive.extractall(tmp_path)

    completed = subprocess.run(
        [sys.executable, "-c", "import filex_mcp_server"],
        env={**os.environ, "PYTHONPATH": str(tmp_path / "ding" / "agent" / "mcp_src")},
        check=False,
    )
    assert completed.returncode == 0


def _write_agent_zip_fixture(tmp_path: Path) -> tuple[Path, Path, Path]:
    repository_root = tmp_path / "repository"
    skill_dir = repository_root / "skill" / "ding"
    agent_dir = skill_dir / "agent"
    agent_dir.mkdir(parents=True)
    (agent_dir / "filex_ingest_url.py").write_text("print('ingest')\n", encoding="utf-8")

    mcp_dir = repository_root / "integrations" / "filex-mcp-server" / "src" / "filex_mcp_server"
    mcp_dir.mkdir(parents=True)
    (mcp_dir / "__init__.py").write_text("__version__ = 'test'\n", encoding="utf-8")
    (mcp_dir / "server.py").write_text("VALUE = 'first'\n", encoding="utf-8")
    return repository_root, skill_dir, mcp_dir


def test_agent_zip_hash_changes_when_mcp_source_changes(tmp_path):
    repository_root, skill_dir, mcp_dir = _write_agent_zip_fixture(tmp_path)
    before = pubmed_skill.build_agent_skill_zip(skill_dir, repository_root=repository_root)
    assert before is not None

    (mcp_dir / "server.py").write_text("VALUE = 'second'\n", encoding="utf-8")
    after = pubmed_skill.build_agent_skill_zip(skill_dir, repository_root=repository_root)
    assert after is not None
    assert hashlib.sha256(after).hexdigest() != hashlib.sha256(before).hexdigest()


def test_mcp_zip_entries_reject_symlink_and_traversal(tmp_path):
    repository_root, _skill_dir, mcp_dir = _write_agent_zip_fixture(tmp_path)
    outside = tmp_path / "outside.py"
    outside.write_text("VALUE = 'outside'\n", encoding="utf-8")
    (mcp_dir / "escape.py").symlink_to(outside)

    with pytest.raises(ValueError, match="symbolic link"):
        pubmed_skill._iter_mcp_agent_zip_entries(repository_root)

    (mcp_dir / "escape.py").unlink()
    with pytest.raises(ValueError, match="traversal"):
        pubmed_skill._iter_mcp_agent_zip_entries(repository_root, source_relative=Path("../outside"))


def test_mcp_zip_entries_reject_symlinked_source_directory(tmp_path):
    repository_root, _skill_dir, mcp_dir = _write_agent_zip_fixture(tmp_path)
    outside_source = tmp_path / "outside-source"
    mcp_dir.rename(outside_source)
    mcp_dir.symlink_to(outside_source, target_is_directory=True)

    with pytest.raises(ValueError, match="source directory.*symbolic link"):
        pubmed_skill._iter_mcp_agent_zip_entries(repository_root)


def test_agent_zip_uses_configured_repository_root_for_docker_layout(tmp_path, monkeypatch):
    app_dir = tmp_path / "app"
    skill_dir = app_dir / "skill" / "ding"
    agent_dir = skill_dir / "agent"
    agent_dir.mkdir(parents=True)
    (agent_dir / "filex_ingest_url.py").write_text("print('ingest')\n", encoding="utf-8")
    mcp_dir = app_dir / "integrations" / "filex-mcp-server" / "src" / "filex_mcp_server"
    mcp_dir.mkdir(parents=True)
    (mcp_dir / "__init__.py").write_text("__version__ = 'test'\n", encoding="utf-8")
    (mcp_dir / "server.py").write_text("VALUE = 'docker'\n", encoding="utf-8")
    monkeypatch.setenv("FILEX_REPOSITORY_ROOT", str(app_dir))

    payload = pubmed_skill.build_agent_skill_zip(skill_dir)

    assert payload is not None
    with zipfile.ZipFile(BytesIO(payload)) as archive:
        assert archive.read("ding/agent/mcp_src/filex_mcp_server/server.py") == b"VALUE = 'docker'\n"


def test_agent_zip_explicit_repository_root_overrides_environment(tmp_path, monkeypatch):
    configured_root, skill_dir, explicit_mcp_dir = _write_agent_zip_fixture(tmp_path / "explicit")
    environment_root, _unused_skill_dir, environment_mcp_dir = _write_agent_zip_fixture(tmp_path / "environment")
    explicit_mcp_dir.joinpath("server.py").write_text("VALUE = 'explicit'\n", encoding="utf-8")
    environment_mcp_dir.joinpath("server.py").write_text("VALUE = 'environment'\n", encoding="utf-8")
    monkeypatch.setenv("FILEX_REPOSITORY_ROOT", str(environment_root))

    payload = pubmed_skill.build_agent_skill_zip(skill_dir, repository_root=configured_root)

    assert payload is not None
    with zipfile.ZipFile(BytesIO(payload)) as archive:
        assert archive.read("ding/agent/mcp_src/filex_mcp_server/server.py") == b"VALUE = 'explicit'\n"


def test_agent_zip_rejects_arbitrary_mcp_source_environment_path(tmp_path, monkeypatch):
    repository_root, skill_dir, mcp_dir = _write_agent_zip_fixture(tmp_path)
    outside = tmp_path / "outside"
    outside.mkdir()
    (outside / "__init__.py").write_text("__version__ = 'outside'\n", encoding="utf-8")
    (outside / "server.py").write_text("VALUE = 'outside'\n", encoding="utf-8")
    monkeypatch.setenv("FILEX_REPOSITORY_ROOT", str(repository_root))
    monkeypatch.setenv("FILEX_MCP_SOURCE_DIR", str(outside))

    payload = pubmed_skill.build_agent_skill_zip(skill_dir)

    assert payload is not None
    with zipfile.ZipFile(BytesIO(payload)) as archive:
        assert archive.read("ding/agent/mcp_src/filex_mcp_server/server.py") == b"VALUE = 'first'\n"


def test_dockerfile_copies_mcp_source_to_runtime_contract():
    dockerfile = Path(__file__).resolve().parents[2] / "docker" / "Dockerfile"
    text = dockerfile.read_text(encoding="utf-8")

    assert "COPY integrations/filex-mcp-server/src/filex_mcp_server /app/integrations/filex-mcp-server/src/filex_mcp_server" in text
    assert "FILEX_REPOSITORY_ROOT=/app" in text
    assert "FILEX_MCP_SOURCE_DIR" not in text


def test_filex_skill_agent_update_503_when_not_seeded(client, db_session, monkeypatch):
    monkeypatch.setattr("main.skill_runtime.data_ready", lambda _db: False)
    r = client.get("/filex-skill-agent-update")
    assert r.status_code == 503
