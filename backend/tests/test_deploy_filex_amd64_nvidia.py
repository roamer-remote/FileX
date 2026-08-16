import os
import re
import subprocess
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
SCRIPT = ROOT / "scripts" / "deploy" / "deploy-filex-amd64-nvidia.sh"
GPU_COMPOSE = ROOT / "docker" / "docker-compose.gpu.yml"


def _compose_service_block(text: str, service: str) -> str:
    marker = f"  {service}:\n"
    start = text.index(marker)
    next_service = re.search(r"\n  [a-zA-Z0-9_-]+:\n", text[start + len(marker):])
    if next_service is None:
        return text[start:]
    return text[start:start + len(marker) + next_service.start()]


def _write_executable(path: Path, content: str) -> None:
    path.write_text(content, encoding="utf-8")
    path.chmod(0o755)


def test_gpu_overlay_grants_filex_api_gpu_for_mq_resource_monitor() -> None:
    text = GPU_COMPOSE.read_text(encoding="utf-8")
    service = _compose_service_block(text, "filex")

    assert "<<: *gpu_device" in service


def _run_gpu(
    tmp_path: Path,
    *,
    build_version: str | None = "2026-07-11-12-00-00-abcdef1",
    commit: str | None = None,
    with_token: bool = True,
    with_bamboo: bool = True,
    current_checkout: bool = True,
    repo_dir: Path | None = None,
) -> subprocess.CompletedProcess[str]:
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()
    calls = tmp_path / "calls.log"
    head = subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=ROOT, text=True).strip()
    expected_commit = commit or head
    token_file = tmp_path / "deploy.token"
    token_file.write_text("secret-token", encoding="utf-8")
    _write_executable(bin_dir / "nvidia-smi", "#!/usr/bin/env bash\nexit 0\n")
    _write_executable(
        bin_dir / "git",
        "#!/usr/bin/env bash\n"
        f"printf 'git %s\\n' \"$*\" >> {calls}\n"
        "case \"$1 $2\" in\n"
        f"  'rev-parse HEAD') echo {head!r}; exit 0 ;;\n"
        f"  'rev-parse --short=7') echo {head[:7]!r}; exit 0 ;;\n"
        f"  'rev-parse --show-toplevel') echo {str(ROOT)!r}; exit 0 ;;\n"
        "  'fetch origin'|'checkout '*|'reset --hard') exit 0 ;;\n"
        "esac\n"
        "/usr/bin/git \"$@\"\n",
    )
    _write_executable(
        bin_dir / "docker",
        "#!/usr/bin/env bash\n"
        f"printf 'docker %s\\n' \"$*\" >> {calls}\n"
        "if [[ \"$1 $2\" == \"compose version\" ]]; then exit 0; fi\n"
        "if [[ \"$1\" == \"compose\" ]]; then\n"
        f"  printf 'compose-env FILEX_SECRETS_FILE=%s\\n' \"${{FILEX_SECRETS_FILE:-}}\" >> {calls}\n"
        "fi\n"
        "if [[ \"$1\" == \"run\" && \"$*\" == *\"--gpus all\"* ]]; then exit 0; fi\n"
        "if [[ \"$*\" == *\" ps --format json\"* ]]; then\n"
        "  for svc in postgres rabbitmq redis filex-ollama filex-mineru filex-docling filex kb-indexer kb-post kb-ragas-eval kb-extract gpu-scheduler; do\n"
        "    printf '{\"Service\":\"%s\",\"Health\":\"healthy\"}\\n' \"$svc\"\n"
        "  done\n"
        "  exit 0\n"
        "fi\n"
        "if [[ \"$1 $2\" == \"compose ps\" ]]; then echo healthy; exit 0; fi\n"
        "if [[ \"$1\" == \"exec\" ]]; then exit 0; fi\n"
        "exit 0\n",
    )
    _write_executable(bin_dir / "sleep", "#!/usr/bin/env bash\nexit 0\n")
    env = {
        **os.environ,
        "PATH": f"{bin_dir}:{os.environ['PATH']}",
        "FILEX_DATA_ROOT": str(tmp_path / "data"),
        "FILEX_REPO_DIR": str(repo_dir or ROOT),
        "FILEX_BRANCH": "master",
        "bamboo_planRepository_revision": expected_commit,
        "FILEX_LICENSE_HMAC_SECRET": "secret",
    }
    if with_bamboo:
        env["BAMBOO_BUILDKEY"] = "FILEX-DEPLOY"
    args = []
    if current_checkout:
        args.append("--current-checkout")
        env["FILEX_DEPLOY_CURRENT_CHECKOUT"] = "1"
    if with_token:
        env.update(
            {
                "FILEX_BAMBOO_DEPLOY_TOKEN": "secret-token",
                "FILEX_BAMBOO_DEPLOY_TOKEN_FILE": str(token_file),
            }
        )
    if build_version is not None:
        env["FILEX_APP_BUILD_VERSION"] = build_version
    return subprocess.run(
        [str(SCRIPT), *args],
        cwd=ROOT,
        env=env,
        text=True,
        encoding="utf-8",
        errors="replace",
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        check=False,
    )


def _calls(tmp_path: Path) -> list[str]:
    path = tmp_path / "calls.log"
    return path.read_text(encoding="utf-8").splitlines() if path.exists() else []


def test_gpu_deploy_verifies_mineru_cuda_before_starting_services(tmp_path: Path) -> None:
    result = _run_gpu(tmp_path)

    assert result.returncode == 0, result.stderr
    commands = _calls(tmp_path)
    probe_index = next(i for i, command in enumerate(commands) if "torch.cuda.is_available" in command)
    start_index = next(i for i, command in enumerate(commands) if "up -d --no-build filex-ollama" in command)
    assert probe_index < start_index


def test_gpu_deploy_mineru_base_uses_fast_pytorch_index(tmp_path: Path) -> None:
    result = _run_gpu(tmp_path)

    assert result.returncode == 0, result.stderr
    commands = _calls(tmp_path)
    build = next(command for command in commands if "docker build -f docker/Dockerfile.gpu --target filex-mineru-base-gpu" in command)
    assert "--build-arg PYTORCH_INDEX_URL=https://download.pytorch.org/whl/cu118" in build


def test_gpu_current_checkout_does_not_fetch_checkout_or_reset(tmp_path: Path) -> None:
    result = _run_gpu(tmp_path)

    assert result.returncode == 0, result.stderr
    calls = "\n".join(_calls(tmp_path))
    assert "git fetch" not in calls
    assert "git checkout" not in calls
    assert "git reset" not in calls
    assert "docker build" in calls


def test_gpu_current_checkout_exports_created_secrets_file_to_compose(tmp_path: Path) -> None:
    result = _run_gpu(tmp_path)

    assert result.returncode == 0, result.stderr
    secrets = tmp_path / "data" / "secrets" / "filex.env"
    assert secrets.exists()
    assert any(
        call == f"compose-env FILEX_SECRETS_FILE={secrets}"
        for call in _calls(tmp_path)
    )


def test_gpu_default_path_exports_created_secrets_file_to_compose(tmp_path: Path) -> None:
    result = _run_gpu(tmp_path, current_checkout=False)

    assert result.returncode == 0, result.stderr
    secrets = tmp_path / "data" / "secrets" / "filex.env"
    assert secrets.exists()
    assert any(
        call == f"compose-env FILEX_SECRETS_FILE={secrets}"
        for call in _calls(tmp_path)
    )


def test_gpu_current_checkout_commit_mismatch_fails_before_build(tmp_path: Path) -> None:
    result = _run_gpu(tmp_path, commit="0" * 40)

    assert result.returncode == 32
    assert "production deploy must run in Bamboo CI/CD with protected deploy token" in result.stderr
    assert not any("docker build" in call for call in _calls(tmp_path))


def test_gpu_current_checkout_requires_protected_token_before_build(tmp_path: Path) -> None:
    result = _run_gpu(tmp_path, with_token=False)

    assert result.returncode == 32
    assert "production deploy must run in Bamboo CI/CD with protected deploy token" in result.stderr
    assert not any("docker build" in call for call in _calls(tmp_path))


def test_gpu_default_path_requires_protected_token_before_build(tmp_path: Path) -> None:
    result = _run_gpu(tmp_path, current_checkout=False, with_token=False)

    assert result.returncode == 32
    assert "production deploy must run in Bamboo CI/CD with protected deploy token" in result.stderr
    calls = "\n".join(_calls(tmp_path))
    assert "git fetch" not in calls
    assert "docker build" not in calls


def test_gpu_default_path_requires_matching_bamboo_commit_before_build(tmp_path: Path) -> None:
    result = _run_gpu(tmp_path, current_checkout=False, commit="0" * 40)

    assert result.returncode == 32
    assert "production deploy must run in Bamboo CI/CD with protected deploy token" in result.stderr
    calls = "\n".join(_calls(tmp_path))
    assert "git fetch" not in calls
    assert "docker build" not in calls


def test_gpu_default_path_requires_bamboo_job_before_build(tmp_path: Path) -> None:
    result = _run_gpu(tmp_path, current_checkout=False, with_bamboo=False)

    assert result.returncode == 32
    assert "production deploy must run in Bamboo CI/CD with protected deploy token" in result.stderr
    calls = "\n".join(_calls(tmp_path))
    assert "git fetch" not in calls
    assert "docker build" not in calls


def test_gpu_default_path_rejects_clone_before_side_effects(tmp_path: Path) -> None:
    missing_repo = tmp_path / "missing-repo"
    result = _run_gpu(tmp_path, current_checkout=False, repo_dir=missing_repo)

    assert result.returncode == 32
    assert "production deploy must run in Bamboo CI/CD with protected deploy token" in result.stderr
    calls = "\n".join(_calls(tmp_path))
    assert "git clone" not in calls
    assert "docker build" not in calls


def test_gpu_generates_full_build_version_from_current_checkout(tmp_path: Path) -> None:
    result = _run_gpu(tmp_path, build_version=None)

    assert result.returncode == 0, result.stderr
    output = result.stdout + result.stderr
    match = re.search(r"FILEX_APP_BUILD_VERSION=([0-9-]+-[0-9a-f]{7})", output)
    assert match, output
    assert re.fullmatch(r"\d{4}-\d{2}-\d{2}-\d{2}-\d{2}-\d{2}-[0-9a-f]{7}", match.group(1))
    assert any(f"VITE_APP_BUILD_VERSION={match.group(1)}" in call for call in _calls(tmp_path))


def test_gpu_invalid_build_version_fails_before_build(tmp_path: Path) -> None:
    result = _run_gpu(tmp_path, build_version="2026-06-18-abcdef1")

    assert result.returncode != 0
    assert "FILEX_APP_BUILD_VERSION" in result.stderr
    assert not any("docker build" in call for call in _calls(tmp_path))
