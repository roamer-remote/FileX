import os
import subprocess
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
SCRIPT = ROOT / "scripts" / "deploy" / "deploy-auto.sh"


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


def _run_auto(
    tmp_path: Path,
    *,
    arch: str = "x86_64",
    nvidia: bool = False,
    docker_gpu: bool = False,
    include_docker: bool = True,
    extra_env: dict[str, str] | None = None,
    args: list[str] | None = None,
) -> subprocess.CompletedProcess[str]:
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()
    calls = tmp_path / "calls.log"
    _write_executable(bin_dir / "uname", f"#!/usr/bin/env bash\nprintf '%s\\n' {arch!r}\n")
    if nvidia:
        _write_executable(bin_dir / "nvidia-smi", "#!/usr/bin/env bash\nexit 0\n")
    docker_script = (
        "#!/usr/bin/env bash\n"
        f"printf 'docker %s\\n' \"$*\" >> {calls}\n"
        + ("exit 127\n" if not include_docker else "")
        + "if [[ \"$1 $2\" == \"compose version\" ]]; then exit 0; fi\n"
        + "if [[ \"$1\" == \"run\" && \"$*\" == *\"--gpus all\"* ]]; then\n"
        + f"  exit {0 if docker_gpu else 1}\n"
        + "fi\n"
        + "exit 0\n"
    )
    _write_executable(bin_dir / "docker", docker_script)
    cpu_script = tmp_path / "deploy-filex-cpu.sh"
    gpu_script = tmp_path / "deploy-filex-amd64-nvidia.sh"
    _write_executable(cpu_script, "#!/usr/bin/env bash\nprintf 'cpu %s\\n' \"$*\" >> " + str(calls) + "\n")
    _write_executable(gpu_script, "#!/usr/bin/env bash\nprintf 'gpu %s\\n' \"$*\" >> " + str(calls) + "\n")
    env = {
        **os.environ,
        "PATH": f"{bin_dir}:{os.environ['PATH']}",
        "FILEX_CPU_DEPLOY_SCRIPT": str(cpu_script),
        "FILEX_GPU_DEPLOY_SCRIPT": str(gpu_script),
        **_authorized_env(tmp_path),
    }
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


def test_amd64_without_nvidia_routes_to_cpu(tmp_path: Path) -> None:
    result = _run_auto(tmp_path, arch="x86_64", nvidia=False)

    assert result.returncode == 0, result.stderr
    assert any(call.startswith("cpu ") for call in _calls(tmp_path))
    assert not any(call.startswith("gpu ") for call in _calls(tmp_path))
    assert "ARCH=amd64" in result.stderr


def test_arm64_without_nvidia_routes_to_cpu(tmp_path: Path) -> None:
    result = _run_auto(tmp_path, arch="aarch64", nvidia=False)

    assert result.returncode == 0, result.stderr
    assert any(call.startswith("cpu ") for call in _calls(tmp_path))
    assert not any(call.startswith("gpu ") for call in _calls(tmp_path))
    assert "ARCH=arm64" in result.stderr


def test_amd64_with_working_docker_gpu_routes_to_gpu_current_checkout(tmp_path: Path) -> None:
    result = _run_auto(tmp_path, arch="x86_64", nvidia=True, docker_gpu=True)

    assert result.returncode == 0, result.stderr
    assert any(call == "gpu --current-checkout" for call in _calls(tmp_path))
    assert not any(call.startswith("cpu ") for call in _calls(tmp_path))


def test_amd64_with_nvidia_but_missing_docker_gpu_fails_without_cpu_fallback(tmp_path: Path) -> None:
    result = _run_auto(tmp_path, arch="x86_64", nvidia=True, docker_gpu=False)

    assert result.returncode == 10
    assert "nvidia-container-toolkit" in result.stderr
    assert not any(call.startswith("cpu ") or call.startswith("gpu ") for call in _calls(tmp_path))


def test_arm64_with_nvidia_is_unsupported(tmp_path: Path) -> None:
    result = _run_auto(tmp_path, arch="aarch64", nvidia=True)

    assert result.returncode == 11
    assert "ARM NVIDIA GPU" in result.stderr
    assert not any(call.startswith("cpu ") or call.startswith("gpu ") for call in _calls(tmp_path))


def test_unknown_architecture_fails(tmp_path: Path) -> None:
    result = _run_auto(tmp_path, arch="riscv64", nvidia=False)

    assert result.returncode == 12
    assert "unsupported architecture" in result.stderr
    assert not any(call.startswith("cpu ") or call.startswith("gpu ") for call in _calls(tmp_path))


def test_missing_docker_fails_before_routing(tmp_path: Path) -> None:
    result = _run_auto(tmp_path, arch="x86_64", include_docker=False)

    assert result.returncode == 13
    assert "Docker prerequisite missing" in result.stderr
    assert not any(call.startswith("cpu ") or call.startswith("gpu ") for call in _calls(tmp_path))


def test_plain_production_env_does_not_authorize_deploy(tmp_path: Path) -> None:
    result = _run_auto(
        tmp_path,
        arch="x86_64",
        extra_env={
            "FILEX_DEPLOY_CONTEXT": "production",
            "BAMBOO_BUILDKEY": "",
            "bamboo_planRepository_revision": "",
            "FILEX_BAMBOO_DEPLOY_TOKEN": "",
        },
    )

    assert result.returncode == 32
    assert "production deploy must run in Bamboo CI/CD with protected deploy token" in result.stderr
    assert not any(call.startswith("cpu ") or call.startswith("gpu ") for call in _calls(tmp_path))


def test_check_mode_runs_preflight_without_routing_or_authorization(tmp_path: Path) -> None:
    result = _run_auto(
        tmp_path,
        arch="x86_64",
        extra_env={"BAMBOO_BUILDKEY": "", "FILEX_BAMBOO_DEPLOY_TOKEN": ""},
        args=["--check"],
    )

    assert result.returncode == 0, result.stderr
    assert "selected_path=cpu" in result.stderr
    assert not any(call.startswith("cpu ") or call.startswith("gpu ") for call in _calls(tmp_path))
