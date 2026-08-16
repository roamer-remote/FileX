import json
import os
import runpy
import subprocess
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]


def test_renovate_opens_manual_review_pr_for_mineru_only() -> None:
    config = json.loads((ROOT / "renovate.json").read_text(encoding="utf-8"))

    assert config["enabledManagers"] == ["pip_requirements"]
    assert config["automerge"] is False

    assert config["packageRules"][0] == {
        "description": "Disable generic Python dependency PRs; this repo only auto-opens MinerU PRs.",
        "matchManagers": ["pip_requirements"],
        "enabled": False,
    }

    rule = next(
        rule
        for rule in config["packageRules"]
        if rule.get("matchFileNames") == ["docker/mineru-sidecar/requirements.mineru.txt"]
    )
    assert rule["matchPackageNames"] == ["mineru"]
    assert rule["groupName"] == "MinerU sidecar"
    assert rule["rangeStrategy"] == "pin"
    assert rule["automerge"] is False
    assert "mineru" in rule["labels"]


def test_mineru_version_checker_reports_current_when_pin_matches_latest(tmp_path: Path) -> None:
    requirements = tmp_path / "requirements.mineru.txt"
    requirements.write_text("mineru[core]==3.4.0\n", encoding="utf-8")
    pypi = tmp_path / "mineru.json"
    pypi.write_text(json.dumps({"info": {"version": "3.4.0"}}), encoding="utf-8")

    result = subprocess.run(
        [
            sys.executable,
            str(ROOT / "scripts" / "check-mineru-version.py"),
            "--requirements",
            str(requirements),
            "--pypi-json",
            pypi.as_uri(),
            "--fail-when-outdated",
        ],
        cwd=ROOT,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        check=False,
    )

    assert result.returncode == 0, result.stderr
    assert "current=3.4.0 latest=3.4.0 status=current" in result.stdout


def test_mineru_version_checker_fails_when_pin_is_outdated(tmp_path: Path) -> None:
    requirements = tmp_path / "requirements.mineru.txt"
    requirements.write_text("mineru[core]==2.5.4\n", encoding="utf-8")
    pypi = tmp_path / "mineru.json"
    pypi.write_text(json.dumps({"info": {"version": "3.4.0"}}), encoding="utf-8")

    result = subprocess.run(
        [
            sys.executable,
            str(ROOT / "scripts" / "check-mineru-version.py"),
            "--requirements",
            str(requirements),
            "--pypi-json",
            pypi.as_uri(),
            "--fail-when-outdated",
        ],
        cwd=ROOT,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        check=False,
    )

    assert result.returncode == 1
    assert "current=2.5.4 latest=3.4.0 status=outdated" in result.stdout


def test_mineru_version_checker_module_exposes_pin_parser() -> None:
    module = runpy.run_path(str(ROOT / "scripts" / "check-mineru-version.py"))
    parse_pin = module["parse_mineru_pin"]

    assert parse_pin("fastapi==0.115.6\nmineru[core]==2.5.4\n") == "2.5.4"


def test_update_mineru_local_updates_pin_and_rebuilds_only_mineru(tmp_path: Path) -> None:
    requirements = tmp_path / "requirements.txt"
    requirements.write_text("fastapi==0.115.6\nmineru[core]==2.5.4\npika==1.3.2\n", encoding="utf-8")

    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()
    docker_log = tmp_path / "docker.log"
    docker_stub = bin_dir / "docker"
    docker_stub.write_text(
        "#!/usr/bin/env bash\n"
        f"printf '%s\\n' \"$*\" >> {docker_log}\n"
        "if [[ \"$*\" == *'exec filex-mineru python -m pip show mineru'* ]]; then\n"
        "  printf 'Name: mineru\\nVersion: 4.0.0a5\\n'\n"
        "fi\n",
        encoding="utf-8",
    )
    docker_stub.chmod(0o755)

    env = {
        **os.environ,
        "PATH": f"{bin_dir}:{os.environ['PATH']}",
        "FILEX_MINERU_REQUIREMENTS_FILE": str(requirements),
    }
    result = subprocess.run(
        [str(ROOT / "scripts" / "update_minerU.sh"), "--version", "4.0.0a5"],
        cwd=ROOT,
        env=env,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        check=False,
    )

    assert result.returncode == 0, result.stderr
    assert "mineru[core]==4.0.0a5" in requirements.read_text(encoding="utf-8")
    commands = docker_log.read_text(encoding="utf-8").splitlines()
    assert commands == [
        "compose -p filex -f docker/docker-compose.yml -f docker/docker-compose.local.yml --profile build-base build filex-mineru-base",
        "compose -p filex -f docker/docker-compose.yml -f docker/docker-compose.local.yml up -d --build filex-mineru",
        "exec filex-mineru python -m pip show mineru",
    ]


def test_update_mineru_local_supports_no_build_mode(tmp_path: Path) -> None:
    requirements = tmp_path / "requirements.txt"
    requirements.write_text("mineru[core]==2.5.4\n", encoding="utf-8")

    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()
    docker_log = tmp_path / "docker.log"
    docker_stub = bin_dir / "docker"
    docker_stub.write_text("#!/usr/bin/env bash\n" f"printf '%s\\n' \"$*\" >> {docker_log}\n", encoding="utf-8")
    docker_stub.chmod(0o755)

    env = {
        **os.environ,
        "PATH": f"{bin_dir}:{os.environ['PATH']}",
        "FILEX_MINERU_REQUIREMENTS_FILE": str(requirements),
    }
    result = subprocess.run(
        [str(ROOT / "scripts" / "update_minerU.sh"), "--version", "4.0.0a5", "--no-build"],
        cwd=ROOT,
        env=env,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        check=False,
    )

    assert result.returncode == 0, result.stderr
    assert "mineru[core]==4.0.0a5" in requirements.read_text(encoding="utf-8")
    assert not docker_log.exists()


def test_update_mineru_migrates_a6_from_removed_basic_extra(tmp_path: Path) -> None:
    requirements = tmp_path / "requirements.txt"
    requirements.write_text("mineru[basic]==4.0.0a5\n", encoding="utf-8")

    env = {**os.environ, "FILEX_MINERU_REQUIREMENTS_FILE": str(requirements)}
    result = subprocess.run(
        [str(ROOT / "scripts" / "update_minerU.sh"), "--version", "4.0.0a6", "--no-build"],
        cwd=ROOT,
        env=env,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        check=False,
    )

    assert result.returncode == 0, result.stderr
    assert requirements.read_text(encoding="utf-8") == "mineru[torch]==4.0.0a6\n"
