import os
import hashlib
import subprocess
from pathlib import Path

import pytest


ROOT = Path(__file__).resolve().parents[2]
SCRIPT = ROOT / "scripts" / "deploy" / "bamboo-compose.sh"


def _sha256_text(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def _sha256_file(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _dockerfile_section(start: str, end: str) -> str:
    lines = (ROOT / "docker" / "Dockerfile.base").read_text(encoding="utf-8").splitlines(True)
    capture = False
    out: list[str] = []
    for line in lines:
        if start in line:
            capture = True
        if capture:
            out.append(line)
            if end in line:
                break
    return "".join(out)


def _fingerprints(*, has_gpu: bool = False, mineru_base_image: str = "filex/mineru-base:py3.13") -> dict[str, str]:
    first_lines = "".join(
        (ROOT / "docker" / "Dockerfile.base").read_text(encoding="utf-8").splitlines(True)[:32]
    )
    os_fp = _sha256_text(first_lines)
    app_fp = _sha256_text(
        f"{os_fp}\n{_sha256_file(ROOT / 'backend' / 'requirements.txt')}  backend/requirements.txt\n"
    )
    extract_fp = _sha256_text(
        f"{os_fp}\n"
        f"{_sha256_file(ROOT / 'backend' / 'requirements.txt')}  backend/requirements.txt\n"
        f"{_sha256_file(ROOT / 'backend' / 'requirements-extract.txt')}  backend/requirements-extract.txt\n"
        f"{_sha256_text(_dockerfile_section('AS filex-extract-base', 'pip install'))}  -\n"
    )
    if has_gpu:
        mineru_fp = _sha256_text(
            f"{_sha256_file(ROOT / 'docker' / 'Dockerfile.gpu')}  docker/Dockerfile.gpu\n"
            f"{_sha256_file(ROOT / 'docker' / 'mineru-sidecar' / 'requirements.common.txt')}  docker/mineru-sidecar/requirements.common.txt\n"
            f"{_sha256_file(ROOT / 'docker' / 'mineru-sidecar' / 'requirements.gpu.txt')}  docker/mineru-sidecar/requirements.gpu.txt\n"
            f"{_sha256_file(ROOT / 'docker' / 'mineru-sidecar' / 'sitecustomize.py')}  docker/mineru-sidecar/sitecustomize.py\n"
        )
    else:
        mineru_fp = _sha256_text(
            f"{os_fp}\n"
            f"{_sha256_file(ROOT / 'docker' / 'mineru-sidecar' / 'requirements.common.txt')}  docker/mineru-sidecar/requirements.common.txt\n"
            f"{_sha256_file(ROOT / 'docker' / 'mineru-sidecar' / 'requirements.cpu.txt')}  docker/mineru-sidecar/requirements.cpu.txt\n"
            f"{_sha256_text(_dockerfile_section('AS filex-mineru-base', 'pip install'))}  -\n"
        )
    docling_fp = _sha256_text(
        f"{os_fp}\n"
        f"{_sha256_file(ROOT / 'docker' / 'docling-sidecar' / 'requirements.txt')}  docker/docling-sidecar/requirements.txt\n"
        f"{_sha256_text(_dockerfile_section('AS filex-docling-base', 'pip install'))}  -\n"
    )
    mineru_base_identity_fp = _sha256_text(f"ref={mineru_base_image}\n")
    mineru_runtime_fp = _sha256_text(
        f"{mineru_fp}\n"
        f"{mineru_base_identity_fp}\n"
        f"{_sha256_file(ROOT / 'docker' / 'mineru-sidecar' / 'requirements.mineru.txt')}  docker/mineru-sidecar/requirements.mineru.txt\n"
        f"{_sha256_file(ROOT / 'docker' / 'Dockerfile.mineru-sidecar')}  docker/Dockerfile.mineru-sidecar\n"
        f"{_sha256_file(ROOT / 'docker' / 'mineru-sidecar' / 'main.py')}  docker/mineru-sidecar/main.py\n"
        f"{_sha256_file(ROOT / 'docker' / 'mineru-sidecar' / 'mq_consumer.py')}  docker/mineru-sidecar/mq_consumer.py\n"
        f"{_sha256_file(ROOT / 'docker' / 'mineru-sidecar' / 'lifecycle_state.py')}  docker/mineru-sidecar/lifecycle_state.py\n"
        f"{_sha256_file(ROOT / 'docker' / 'mineru-sidecar' / 'mineru_runner.py')}  docker/mineru-sidecar/mineru_runner.py\n"
        f"{_sha256_file(ROOT / 'docker' / 'mineru-sidecar' / 'mineru_v4_runner.py')}  docker/mineru-sidecar/mineru_v4_runner.py\n"
        f"{_sha256_file(ROOT / 'docker' / 'mineru-sidecar' / 'table_rotation.py')}  docker/mineru-sidecar/table_rotation.py\n"
        f"{_sha256_file(ROOT / 'docker' / 'mineru-sidecar' / 'entrypoint.sh')}  docker/mineru-sidecar/entrypoint.sh\n"
        f"{_sha256_file(ROOT / 'backend' / 'logging_setup.py')}  backend/logging_setup.py\n"
    )
    return {
        "filex.os.deps": os_fp,
        "filex.app.deps": app_fp,
        "filex.extract.deps": extract_fp,
        "filex.mineru.deps": mineru_fp,
        "filex.mineru.runtime": mineru_runtime_fp,
        "filex.docling.deps": docling_fp,
    }


def _run_bamboo(
    tmp_path: Path,
    *args: str,
    build_version: str = "2026-07-11-12-00-00-abcdef1",
    missing_base_image: bool = False,
    missing_rerank_image: bool = False,
    stale_mineru_runtime: bool = False,
    stable_deps_image: str | None = None,
    build_http_proxy: str | None = None,
    has_nvidia_smi: bool = False,
) -> subprocess.CompletedProcess[str]:
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()
    capture_file = tmp_path / "docker-args.txt"
    docker_stub = bin_dir / "docker"
    mineru_base_image = stable_deps_image or (
        "filex/mineru-base:py3.13-gpu" if has_nvidia_smi else "filex/mineru-base:py3.13"
    )
    labels = _fingerprints(has_gpu=has_nvidia_smi, mineru_base_image=mineru_base_image)
    docker_stub.write_text(
        "#!/usr/bin/env bash\n"
        f"printf '%s\\n' \"$*\" >> {capture_file}\n"
        "if [[ \"$1 $2\" == \"image inspect\" && \"$3\" == \"filex/tei-rerank:cpu-1.9.3\" && \"${FILEX_TEST_MISSING_RERANK:-0}\" == \"1\" ]]; then\n"
        "  exit 1\n"
        "fi\n"
        "if [[ \"$1 $2\" == \"image inspect\" && \"$3\" != \"filex-filex-mineru:latest\" && \"${FILEX_TEST_MISSING_BASE:-0}\" == \"1\" ]]; then\n"
        "  exit 1\n"
        "fi\n"
        "if [[ \"$1 $2\" == \"image inspect\" && \"${4:-}\" == \"--format\" ]]; then\n"
        f"  [[ \"$5\" == *'filex.os.deps'* ]] && echo '{labels['filex.os.deps']}' && exit 0\n"
        f"  [[ \"$5\" == *'filex.app.deps'* ]] && echo '{labels['filex.app.deps']}' && exit 0\n"
        f"  [[ \"$5\" == *'filex.extract.deps'* ]] && echo '{labels['filex.extract.deps']}' && exit 0\n"
        f"  [[ \"$5\" == *'filex.mineru.deps'* ]] && echo '{labels['filex.mineru.deps']}' && exit 0\n"
        "  if [[ \"$5\" == *'filex.mineru.runtime'* ]]; then\n"
        f"    [[ \"${{FILEX_TEST_STALE_MINERU_RUNTIME:-0}}\" == \"1\" ]] && echo 'stale-runtime' || echo \"${{FILEX_TEST_RUNTIME_LABEL:-{labels['filex.mineru.runtime']}}}\"\n"
        "    exit 0\n"
        "  fi\n"
        f"  [[ \"$5\" == *'filex.docling.deps'* ]] && echo '{labels['filex.docling.deps']}' && exit 0\n"
        "fi\n"
        "if [[ \"$1\" == \"pull\" || \"$1\" == \"tag\" ]]; then exit 0; fi\n",
        encoding="utf-8",
    )
    docker_stub.chmod(0o755)
    if has_nvidia_smi:
        nvidia_stub = bin_dir / "nvidia-smi"
        nvidia_stub.write_text("#!/usr/bin/env bash\nexit 0\n", encoding="utf-8")
        nvidia_stub.chmod(0o755)

    secrets_file = tmp_path / "filex.env"
    secrets_file.write_text("FILEX_SECRET_KEY=test\n", encoding="utf-8")

    env = {
        **os.environ,
        "PATH": f"{bin_dir}:{os.environ['PATH']}",
        "FILEX_SECRETS_FILE": str(secrets_file),
        "FILEX_DEPLOY_LOCK_DIR": str(tmp_path / "deploy.lock"),
        "FILEX_APP_BUILD_VERSION": build_version,
        "FILEX_TEST_MISSING_BASE": "1" if missing_base_image else "0",
        "FILEX_TEST_MISSING_RERANK": "1" if missing_rerank_image else "0",
        "FILEX_TEST_STALE_MINERU_RUNTIME": "1" if stale_mineru_runtime else "0",
        "FILEX_TEST_RUNTIME_LABEL": labels["filex.mineru.runtime"],
    }
    if stable_deps_image is not None:
        env["FILEX_MINERU_DEPS_IMAGE"] = stable_deps_image
    if build_http_proxy is not None:
        env["BUILD_HTTP_PROXY"] = build_http_proxy
    return subprocess.run(
        [str(SCRIPT), *args],
        cwd=ROOT,
        env=env,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        check=False,
    )


def test_bamboo_daily_release_does_not_build_or_restart_sidecars(tmp_path: Path) -> None:
    result = _run_bamboo(tmp_path, "build-app-and-up-workers")

    assert result.returncode == 0, result.stderr
    commands = (tmp_path / "docker-args.txt").read_text(encoding="utf-8").splitlines()
    assert commands[-1] == (
        "compose -f docker/docker-compose.yml -f docker/docker-compose.prod.yml -f docker/docker-compose.pdf-inspector.yml "
        "up -d --force-recreate --no-build filex kb-indexer kb-post kb-ragas-eval"
    )
    assert not any("mineru" in command or "docling" in command or "kb-extract" in command for command in commands)


def test_bamboo_daily_release_provisions_missing_rerank_image(tmp_path: Path) -> None:
    result = _run_bamboo(
        tmp_path,
        "build-app-and-up-workers",
        missing_rerank_image=True,
    )

    assert result.returncode == 0, result.stderr
    commands = (tmp_path / "docker-args.txt").read_text(encoding="utf-8").splitlines()
    assert "image inspect filex/tei-rerank:cpu-1.9.3" in commands
    assert "pull ghcr.io/huggingface/text-embeddings-inference:cpu-1.9.3" in commands
    assert "tag ghcr.io/huggingface/text-embeddings-inference:cpu-1.9.3 filex/tei-rerank:cpu-1.9.3" in commands


def test_bamboo_refuses_overlapping_deployment(tmp_path: Path) -> None:
    lock_dir = tmp_path / "deploy.lock"
    lock_dir.mkdir()
    (lock_dir / "pid").write_text(f"{os.getpid()}\n", encoding="utf-8")

    result = _run_bamboo(tmp_path, "build-app-and-up-workers")

    assert result.returncode == 75
    assert "已有部署正在运行" in result.stderr


def test_bamboo_build_without_target_defaults_to_app_and_extract_build(tmp_path: Path) -> None:
    result = _run_bamboo(tmp_path, "build")

    assert result.returncode == 0, result.stderr
    commands = (tmp_path / "docker-args.txt").read_text(encoding="utf-8").splitlines()
    assert commands[0] == "image inspect filex/app-base:py3.13"
    assert any(command.startswith("build --no-cache -f docker/Dockerfile --add-host host.docker.internal:host-gateway ") for command in commands)
    assert any(" -t filex/app:latest " in command for command in commands)
    assert "image inspect filex/kb-extract-base:py3.13" not in commands
    assert not any(" -t filex/kb-extract:latest " in command for command in commands)
    assert not any(" -t filex-filex-mineru:latest " in command for command in commands)
    assert not any(" -t filex-filex-docling:latest " in command for command in commands)
    assert not any(" compose " in command and " build" in command for command in commands)


def test_bamboo_build_app_and_extract(tmp_path: Path) -> None:
    result = _run_bamboo(tmp_path, "build-app-and-extract")

    assert result.returncode == 0, result.stderr
    commands = (tmp_path / "docker-args.txt").read_text(encoding="utf-8").splitlines()
    assert "image inspect filex/app-base:py3.13" in commands
    assert "image inspect filex/kb-extract-base:py3.13" in commands
    assert "image inspect filex/mineru-base:py3.13" in commands
    assert "image inspect filex/docling-base:py3.13" in commands
    assert any(" -t filex/app:latest " in command for command in commands)
    assert any(" -t filex/kb-extract:latest " in command for command in commands)
    assert any(" -t filex-filex-mineru:latest " in command for command in commands)
    assert any(" -t filex-filex-docling:latest " in command for command in commands)
    assert "image inspect filex/tei-rerank:cpu-1.9.3" in commands


def test_bamboo_gpu_direct_mineru_base_build_uses_gpu_dockerfile(tmp_path: Path) -> None:
    result = _run_bamboo(tmp_path, "build", "filex-mineru-base", has_nvidia_smi=True, missing_base_image=True)

    assert result.returncode == 0, result.stderr
    commands = (tmp_path / "docker-args.txt").read_text(encoding="utf-8").splitlines()
    assert any("-f docker/Dockerfile.gpu --target filex-mineru-base-gpu" in command for command in commands)
    assert not any("-f docker/Dockerfile.base --target filex-mineru-base" in command for command in commands)


def test_bamboo_gpu_mineru_base_build_uses_fast_pytorch_index(tmp_path: Path) -> None:
    result = _run_bamboo(tmp_path, "build-mineru", has_nvidia_smi=True, missing_base_image=True)

    assert result.returncode == 0, result.stderr
    commands = (tmp_path / "docker-args.txt").read_text(encoding="utf-8").splitlines()
    build = next(command for command in commands if "-f docker/Dockerfile.gpu --target filex-mineru-base-gpu" in command)
    assert "--build-arg PYTORCH_INDEX_URL=https://download.pytorch.org/whl/cu118" in build


def test_bamboo_gpu_build_mineru_probes_cuda_before_returning(tmp_path: Path) -> None:
    result = _run_bamboo(tmp_path, "build-mineru", has_nvidia_smi=True, missing_base_image=True)

    assert result.returncode == 0, result.stderr
    commands = (tmp_path / "docker-args.txt").read_text(encoding="utf-8").splitlines()
    assert any("torch.cuda.is_available" in command for command in commands)


def test_bamboo_gpu_verification_checks_runtime_image_and_compatible_architecture() -> None:
    script = SCRIPT.read_text(encoding="utf-8")

    assert 'filex.mineru.runtime' in script
    assert 'arch == "sm_61"' in script
    assert '"sm_60" in arch_list' in script


def test_bamboo_cpu_build_mineru_does_not_probe_cuda(tmp_path: Path) -> None:
    result = _run_bamboo(tmp_path, "build-mineru", has_nvidia_smi=False, missing_base_image=True)

    assert result.returncode == 0, result.stderr
    commands = (tmp_path / "docker-args.txt").read_text(encoding="utf-8").splitlines()
    assert any("-f docker/Dockerfile.base --target filex-mineru-base" in command for command in commands)
    assert not any("torch.cuda.is_available" in command for command in commands)


def test_bamboo_build_app_reuses_existing_base_image(tmp_path: Path) -> None:
    result = _run_bamboo(tmp_path, "build-app")

    assert result.returncode == 0, result.stderr
    commands = (tmp_path / "docker-args.txt").read_text(encoding="utf-8").splitlines()
    assert commands[0] == "image inspect filex/app-base:py3.13"
    assert 'image inspect filex/app-base:py3.13 --format {{index .Config.Labels "filex.app.deps"}}' in commands
    build = next(command for command in commands if " -t filex/app:latest " in command)
    assert build.startswith("build --no-cache -f docker/Dockerfile --add-host host.docker.internal:host-gateway ")
    assert "--build-arg APP_BASE_IMAGE=filex/app-base:py3.13" in build
    assert "--build-arg BUILD_HTTP_PROXY=" in build
    assert "--build-arg BUILD_HTTP_PROXY=http://host.docker.internal:7890" not in build


def test_bamboo_build_app_builds_base_when_missing(tmp_path: Path) -> None:
    result = _run_bamboo(tmp_path, "build-app", missing_base_image=True)

    assert result.returncode == 0, result.stderr
    commands = (tmp_path / "docker-args.txt").read_text(encoding="utf-8").splitlines()
    assert commands[0] == "image inspect filex/app-base:py3.13"
    assert any(command.startswith("build -f docker/Dockerfile.base --target filex-os-base ") for command in commands)
    assert any(command.startswith("build -f docker/Dockerfile.base --target filex-app-base ") for command in commands)
    assert any(command.startswith("build --no-cache -f docker/Dockerfile --add-host host.docker.internal:host-gateway ") for command in commands)


def test_bamboo_build_app_allows_explicit_proxy(tmp_path: Path) -> None:
    result = _run_bamboo(tmp_path, "build-app", build_http_proxy="http://host.docker.internal:7890")

    assert result.returncode == 0, result.stderr
    commands = (tmp_path / "docker-args.txt").read_text(encoding="utf-8").splitlines()
    build = next(command for command in commands if " -t filex/app:latest " in command)
    assert "--build-arg BUILD_HTTP_PROXY=http://host.docker.internal:7890" in build


def test_bamboo_up_defaults_to_no_build(tmp_path: Path) -> None:
    result = _run_bamboo(tmp_path, "up", "-d")

    assert result.returncode == 0, result.stderr
    commands = (tmp_path / "docker-args.txt").read_text(encoding="utf-8").splitlines()
    assert commands == [
        "image inspect filex/tei-rerank:cpu-1.9.3",
        "compose -f docker/docker-compose.yml -f docker/docker-compose.prod.yml -f docker/docker-compose.pdf-inspector.yml up --no-build -d"
    ]


def test_bamboo_up_respects_explicit_build_flag(tmp_path: Path) -> None:
    result = _run_bamboo(tmp_path, "up", "-d", "--build")

    assert result.returncode == 0, result.stderr
    commands = (tmp_path / "docker-args.txt").read_text(encoding="utf-8").splitlines()
    assert commands == [
        "image inspect filex/tei-rerank:cpu-1.9.3",
        "compose -f docker/docker-compose.yml -f docker/docker-compose.prod.yml -f docker/docker-compose.pdf-inspector.yml up -d --build"
    ]


def test_bamboo_up_app_workers_includes_ragas_eval_worker(tmp_path: Path) -> None:
    result = _run_bamboo(tmp_path, "up-app-workers")

    assert result.returncode == 0, result.stderr
    commands = (tmp_path / "docker-args.txt").read_text(encoding="utf-8").splitlines()
    assert commands == [
        "image inspect filex/tei-rerank:cpu-1.9.3",
        "compose -f docker/docker-compose.yml -f docker/docker-compose.prod.yml -f docker/docker-compose.pdf-inspector.yml "
        "run --rm db-migrate",
        "compose -f docker/docker-compose.yml -f docker/docker-compose.prod.yml -f docker/docker-compose.pdf-inspector.yml "
        "up -d --force-recreate --no-build filex kb-indexer kb-post kb-ragas-eval",
    ]


def test_bamboo_build_app_and_up_workers(tmp_path: Path) -> None:
    result = _run_bamboo(tmp_path, "build-app-and-up-workers")

    assert result.returncode == 0, result.stderr
    commands = (tmp_path / "docker-args.txt").read_text(encoding="utf-8").splitlines()
    assert any(" -t filex/app:latest " in command for command in commands)
    assert not any("mineru" in command or "docling" in command or "kb-extract" in command for command in commands)
    assert not any(" -t filex-filex-mineru:latest " in command for command in commands)
    assert "compose -f docker/docker-compose.yml -f docker/docker-compose.prod.yml -f docker/docker-compose.pdf-inspector.yml run --rm db-migrate" in commands
    assert "compose -f docker/docker-compose.yml -f docker/docker-compose.prod.yml -f docker/docker-compose.pdf-inspector.yml up -d --force-recreate --no-build filex kb-indexer kb-post kb-ragas-eval" in commands


def test_bamboo_build_app_and_up_workers_ignores_stale_mineru_runtime(tmp_path: Path) -> None:
    result = _run_bamboo(tmp_path, "build-app-and-up-workers", stale_mineru_runtime=True)

    assert result.returncode == 0, result.stderr
    commands = (tmp_path / "docker-args.txt").read_text(encoding="utf-8").splitlines()
    assert not any("mineru" in command or "docling" in command or "kb-extract" in command for command in commands)


@pytest.mark.parametrize("has_gpu", [False, True])
def test_bamboo_build_app_and_up_extract_workers_rebuilds_extract_only(
    tmp_path: Path, has_gpu: bool
) -> None:
    result = _run_bamboo(tmp_path, "build-app-and-up-extract-workers", has_nvidia_smi=has_gpu)

    assert result.returncode == 0, result.stderr
    commands = (tmp_path / "docker-args.txt").read_text(encoding="utf-8").splitlines()
    assert any(" -t filex/app:latest " in command for command in commands)
    assert any(" -t filex/kb-extract:latest " in command for command in commands)
    assert not any(" -t filex-filex-mineru:latest " in command for command in commands)
    assert not any(" -t filex-filex-docling:latest " in command for command in commands)
    expected = (
        "compose -f docker/docker-compose.yml -f docker/docker-compose.prod.yml "
        "-f docker/docker-compose.pdf-inspector.yml up -d --force-recreate --no-build "
        "filex kb-indexer kb-post kb-ragas-eval"
    )
    if has_gpu:
        expected = expected.replace(
            "-f docker/docker-compose.pdf-inspector.yml ",
            "-f docker/docker-compose.pdf-inspector.yml -f docker/docker-compose.gpu.yml ",
        ).replace("kb-ragas-eval", "kb-ragas-eval gpu-scheduler")
    assert f"{expected} kb-extract" in commands


def test_bamboo_gpu_build_app_and_up_workers_keeps_gpu_overlay_without_sidecar_build(tmp_path: Path) -> None:
    result = _run_bamboo(
        tmp_path,
        "build-app-and-up-workers",
        has_nvidia_smi=True,
        stale_mineru_runtime=True,
    )

    assert result.returncode == 0, result.stderr
    commands = (tmp_path / "docker-args.txt").read_text(encoding="utf-8").splitlines()
    assert any("-f docker/docker-compose.gpu.yml up" in command for command in commands)
    assert not any("mineru" in command or "docling" in command or "kb-extract" in command for command in commands)
    assert not any("torch.cuda.is_available" in command for command in commands)


def test_bamboo_always_pulls_configured_stable_mineru_deps_image(tmp_path: Path) -> None:
    stable_image = "registry.example/filex-mineru-deps:py3.13-cpu"

    result = _run_bamboo(
        tmp_path,
        "build-mineru",
        stable_deps_image=stable_image,
    )

    assert result.returncode == 0, result.stderr
    commands = (tmp_path / "docker-args.txt").read_text(encoding="utf-8").splitlines()
    assert f"pull {stable_image}" in commands
    build = next(command for command in commands if "-t filex-filex-mineru:latest" in command)
    assert f"--build-arg MINERU_BASE_IMAGE={stable_image}" in build


def test_bamboo_stable_mineru_deps_image_change_invalidates_runtime(tmp_path: Path) -> None:
    stable_image = "registry.example/filex-mineru-deps:py3.13-cpu-v2"

    result = _run_bamboo(
        tmp_path,
        "build-mineru",
        stable_deps_image=stable_image,
    )

    assert result.returncode == 0, result.stderr
    commands = (tmp_path / "docker-args.txt").read_text(encoding="utf-8").splitlines()
    assert any("-t filex-filex-mineru:latest" in command for command in commands)


def test_bamboo_compose_loads_gpu_overlay_when_nvidia_smi_exists(tmp_path: Path) -> None:
    result = _run_bamboo(tmp_path, "up", "-d", has_nvidia_smi=True)

    assert result.returncode == 0, result.stderr
    commands = (tmp_path / "docker-args.txt").read_text(encoding="utf-8").splitlines()
    assert commands == [
        "image inspect filex/tei-rerank:cpu-1.9.3",
        "compose -f docker/docker-compose.yml -f docker/docker-compose.prod.yml -f docker/docker-compose.pdf-inspector.yml "
        "-f docker/docker-compose.gpu.yml up --no-build -d"
    ]
