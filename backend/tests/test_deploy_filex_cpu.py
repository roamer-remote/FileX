import os
import re
import shutil
import subprocess
from pathlib import Path

import pytest


ROOT = Path(__file__).resolve().parents[2]
SCRIPT = ROOT / "scripts" / "deploy" / "deploy-filex-cpu.sh"


def _write_executable(path: Path, content: str) -> None:
    path.write_text(content, encoding="utf-8")
    path.chmod(0o755)


def _authorized_env(tmp_path: Path) -> dict[str, str]:
    token_file = tmp_path / "deploy.token"
    token_file.write_text("secret-token", encoding="utf-8")
    head = subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=ROOT, text=True).strip()
    return {
        "BAMBOO_BUILDKEY": "FILEX-DEPLOY",
        "bamboo_planRepository_revision": head,
        "FILEX_BAMBOO_DEPLOY_TOKEN": "secret-token",
        "FILEX_BAMBOO_DEPLOY_TOKEN_FILE": str(token_file),
    }


def _run_cpu(
    tmp_path: Path,
    *,
    arch: str = "x86_64",
    authorized: bool = True,
    args: list[str] | None = None,
    build_version: str | None = "2026-07-11-12-00-00-abcdef1",
    binfmt_ok: bool = True,
    tei_arch: str = "amd64/linux",
    unhealthy_service: str | None = None,
    filex_http_ok: bool = True,
    extra_env: dict[str, str] | None = None,
) -> subprocess.CompletedProcess[str]:
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()
    calls = tmp_path / "calls.log"
    secrets = tmp_path / "filex.env"
    secrets.write_text("FILEX_SECRET_KEY=test\n", encoding="utf-8")
    _write_executable(bin_dir / "uname", f"#!/usr/bin/env bash\nprintf '%s\\n' {arch!r}\n")
    _write_executable(
        bin_dir / "docker",
        "#!/usr/bin/env bash\n"
        f"printf 'docker %s\\n' \"$*\" >> {calls}\n"
        "if [[ \"$1 $2\" == \"compose version\" ]]; then exit 0; fi\n"
        "if [[ \"$1 $2 $3 $4 $5\" == \"run --rm --platform linux/amd64\"* ]]; then\n"
        f"  {'echo x86_64; exit 0' if binfmt_ok else 'echo aarch64; exit 0'}\n"
        "fi\n"
        "if [[ \"$1 $2\" == \"image inspect\" && \"$3\" == \"filex/tei-rerank:cpu-1.9.3\" ]]; then\n"
        f"  echo {tei_arch!r}; exit 0\n"
        "fi\n"
        "if [[ \"$*\" == *\" ps \"* ]]; then\n"
        + (
            f"  if [[ \"$*\" == *\" ps {unhealthy_service}\"* ]]; then echo exited; exit 0; fi\n"
            if unhealthy_service
            else ""
        )
        +
        "  echo healthy; exit 0\n"
        "fi\n"
        "exit 0\n",
    )
    _write_executable(
        bin_dir / "curl",
        "#!/usr/bin/env bash\n"
        f"printf 'curl %s\\n' \"$*\" >> {calls}\n"
        f"exit {0 if filex_http_ok else 7}\n",
    )
    _write_executable(bin_dir / "sleep", "#!/usr/bin/env bash\nexit 0\n")
    env = {
        **os.environ,
        "PATH": f"{bin_dir}:{os.environ['PATH']}",
        "FILEX_SECRETS_FILE": str(secrets),
        "FILEX_DATA_ROOT": str(tmp_path / "data"),
        "FILEX_DEPLOY_HEALTH_ATTEMPTS": "1",
    }
    if authorized:
        env.update(_authorized_env(tmp_path))
    if build_version is not None:
        env["FILEX_APP_BUILD_VERSION"] = build_version
    if extra_env:
        env.update(extra_env)
    return subprocess.run(
        [str(SCRIPT), *(args or [])],
        cwd=ROOT,
        env=env,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        check=False,
    )


def _calls(tmp_path: Path) -> list[str]:
    path = tmp_path / "calls.log"
    return path.read_text(encoding="utf-8").splitlines() if path.exists() else []


def test_production_compose_uses_same_data_root_and_secrets_contract_as_cpu_script() -> None:
    compose = (ROOT / "docker" / "docker-compose.yml").read_text(encoding="utf-8")
    prod = (ROOT / "docker" / "docker-compose.prod.yml").read_text(encoding="utf-8")
    hardcoded_data_root = "/root/important/FileX/product/"

    assert hardcoded_data_root not in compose
    for relative_path in [
        "redis/data",
        "ollama",
        "postgres/data",
        "rerank_data",
        "uploads",
        "logs",
        "mineru/models",
        "mineru/cache",
        "docling/models",
        "docling/cache",
    ]:
        assert f"${{FILEX_DATA_ROOT:-/root/important/FileX/product}}/{relative_path}" in compose

    assert "${FILEX_SECRETS_FILE:-/root/docker/important/FileX/secrets/filex.env}" in prod
    assert "- /root/docker/important/FileX/secrets/filex.env" not in prod


def test_production_compose_config_resolves_custom_data_root_and_secrets(tmp_path: Path) -> None:
    if shutil.which("docker") is None:
        pytest.skip("docker CLI is not available")

    data_root = tmp_path / "data"
    secrets = tmp_path / "filex.env"
    secrets.write_text("FILEX_SECRET_KEY=test\n", encoding="utf-8")
    env = {
        **os.environ,
        "FILEX_DATA_ROOT": str(data_root),
        "FILEX_SECRETS_FILE": str(secrets),
    }

    result = subprocess.run(
        [
            "docker",
            "compose",
            "-f",
            "docker/docker-compose.yml",
            "-f",
            "docker/docker-compose.prod.yml",
            "-f",
            "docker/docker-compose.pdf-inspector.yml",
            "-f",
            "docker/docker-compose.arm64.yml",
            "config",
        ],
        cwd=ROOT,
        env=env,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        check=False,
    )

    assert result.returncode == 0, result.stderr
    assert str(data_root / "uploads") in result.stdout
    assert str(data_root / "postgres" / "data") in result.stdout
    assert str(secrets) in result.stdout
    assert "/root/important/FileX/product/" not in result.stdout
    assert "/root/docker/important/FileX/secrets/filex.env" not in result.stdout


def test_cpu_direct_deploy_requires_bamboo_authorization(tmp_path: Path) -> None:
    result = _run_cpu(tmp_path, authorized=False)

    assert result.returncode == 32
    assert "production deploy must run in Bamboo CI/CD with protected deploy token" in result.stderr
    assert not any(" build " in call or " run --rm --no-deps db-migrate" in call for call in _calls(tmp_path))


def test_cpu_check_mode_does_not_build_or_start_services_without_authorization(tmp_path: Path) -> None:
    result = _run_cpu(tmp_path, authorized=False, args=["--check"])

    assert result.returncode == 0, result.stderr
    assert "check_only=true" in result.stderr
    assert not any(" build " in call or " up -d" in call or "db-migrate" in call for call in _calls(tmp_path))


def test_cpu_invalid_build_version_fails_before_docker_build(tmp_path: Path) -> None:
    result = _run_cpu(tmp_path, build_version="2026-06-18-abcdef1")

    assert result.returncode == 1
    assert "FILEX_APP_BUILD_VERSION" in result.stderr
    assert not any(" build " in call for call in _calls(tmp_path))


def test_cpu_generates_build_version_from_current_checkout(tmp_path: Path) -> None:
    result = _run_cpu(tmp_path, build_version=None, extra_env={"TZ": "Asia/Shanghai"})

    assert result.returncode == 0, result.stderr
    match = re.search(r"FILEX_APP_BUILD_VERSION=([0-9-]+-[0-9a-f]{7})", result.stderr)
    assert match, result.stderr
    assert re.fullmatch(r"\d{4}-\d{2}-\d{2}-\d{2}-\d{2}-\d{2}-[0-9a-f]{7}", match.group(1))
    assert any(f"VITE_APP_BUILD_VERSION={match.group(1)}" in call for call in _calls(tmp_path))


def test_cpu_amd64_uses_base_compose_without_arm_overlay(tmp_path: Path) -> None:
    result = _run_cpu(tmp_path, arch="x86_64")

    assert result.returncode == 0, result.stderr
    calls = "\n".join(_calls(tmp_path))
    assert "docker-compose.arm64.yml" not in calls
    assert "postgres rabbitmq redis filex-ollama kb-rerank" in calls
    assert "run --rm --no-deps db-migrate" in calls
    for service in ("filex", "kb-indexer", "kb-post", "kb-extract", "filex-mineru", "filex-docling"):
        assert f" ps {service}" in calls


def test_cpu_builds_app_base_before_app_image_on_empty_cache(tmp_path: Path) -> None:
    result = _run_cpu(tmp_path, arch="x86_64")

    assert result.returncode == 0, result.stderr
    commands = _calls(tmp_path)
    os_base = next(command for command in commands if "--target filex-os-base" in command)
    app_base = next(command for command in commands if "--target filex-app-base" in command)
    app_build = next(command for command in commands if " -f docker/Dockerfile " in command)
    assert " -t filex/os-base:py3.13 " in os_base
    assert " -t filex/app-base:py3.13 " in app_base
    assert "--build-arg FILEX_OS_BASE_IMAGE=filex/os-base:py3.13" in app_base
    assert "--build-arg APP_BASE_IMAGE=filex/app-base:py3.13" in app_build
    assert commands.index(os_base) < commands.index(app_base) < commands.index(app_build)


def test_cpu_infra_unhealthy_fails_before_migration(tmp_path: Path) -> None:
    result = _run_cpu(tmp_path, unhealthy_service="postgres")

    assert result.returncode == 40
    assert "service unhealthy: postgres" in result.stderr
    assert not any("db-migrate" in call for call in _calls(tmp_path))


def test_cpu_business_unhealthy_fails_with_service_name(tmp_path: Path) -> None:
    result = _run_cpu(tmp_path, unhealthy_service="kb-indexer")

    assert result.returncode == 40
    assert "service unhealthy: kb-indexer" in result.stderr


def test_cpu_filex_http_unavailable_fails(tmp_path: Path) -> None:
    result = _run_cpu(tmp_path, filex_http_ok=False)

    assert result.returncode == 41
    assert "filex HTTP health unavailable" in result.stderr


def test_cpu_arm64_uses_arm_overlay_and_verifies_tei_amd64_image(tmp_path: Path) -> None:
    result = _run_cpu(tmp_path, arch="aarch64")

    assert result.returncode == 0, result.stderr
    calls = "\n".join(_calls(tmp_path))
    assert "docker-compose.arm64.yml" in calls
    assert "pull --platform linux/amd64 ghcr.io/huggingface/text-embeddings-inference:cpu-1.9.3" in calls
    assert "tag ghcr.io/huggingface/text-embeddings-inference:cpu-1.9.3 filex/tei-rerank:cpu-1.9.3" in calls


def test_cpu_arm64_binfmt_failure_exits_20(tmp_path: Path) -> None:
    result = _run_cpu(tmp_path, arch="aarch64", binfmt_ok=False)

    assert result.returncode == 20
    assert "tonistiigi/binfmt --install amd64" in result.stderr


def test_cpu_arm64_tei_wrong_architecture_exits_20(tmp_path: Path) -> None:
    result = _run_cpu(tmp_path, arch="aarch64", tei_arch="arm64/linux")

    assert result.returncode == 20
    assert "kb-rerank linux/amd64 image unavailable" in result.stderr
