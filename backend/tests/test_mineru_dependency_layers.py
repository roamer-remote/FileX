from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
CPU_DOCKERFILE = ROOT / "docker" / "Dockerfile.base"
GPU_DOCKERFILE = ROOT / "docker" / "Dockerfile.gpu"
MINERU_RUNTIME_DOCKERFILE = ROOT / "docker" / "Dockerfile.mineru-sidecar"
COMMON_REQUIREMENTS = ROOT / "docker" / "mineru-sidecar" / "requirements.common.txt"
CPU_REQUIREMENTS = ROOT / "docker" / "mineru-sidecar" / "requirements.cpu.txt"
GPU_REQUIREMENTS = ROOT / "docker" / "mineru-sidecar" / "requirements.gpu.txt"
MINERU_REQUIREMENTS = ROOT / "docker" / "mineru-sidecar" / "requirements.mineru.txt"
COMPOSE = ROOT / "docker" / "docker-compose.yml"
GPU_COMPOSE = ROOT / "docker" / "docker-compose.gpu.yml"
DEPLOY_SCRIPT = ROOT / "scripts" / "deploy" / "bamboo-compose.sh"
NVIDIA_DEPLOY_SCRIPT = ROOT / "scripts" / "deploy" / "deploy-filex-amd64-nvidia.sh"


def test_mineru_dependency_requirement_files_split_platform_and_runtime_layers() -> None:
    common = COMMON_REQUIREMENTS.read_text(encoding="utf-8")
    cpu = CPU_REQUIREMENTS.read_text(encoding="utf-8")
    gpu = GPU_REQUIREMENTS.read_text(encoding="utf-8")
    mineru = MINERU_REQUIREMENTS.read_text(encoding="utf-8")

    assert "fastapi==" in common
    assert "torch==2.6.0" in cpu
    assert "torchvision==0.21.0" in cpu
    assert "torch-2.6.0%2Bcu118-cp310-cp310-linux_x86_64.whl" in gpu
    assert "mineru[torch]==4.0.0a6" in mineru
    assert "mineru" not in common


def test_mineru_torch_layer_bounds_huggingface_resolver_for_transformers_4() -> None:
    mineru = MINERU_REQUIREMENTS.read_text(encoding="utf-8")

    assert "transformers==4.57.6" in mineru
    assert "huggingface-hub[hf_xet]==0.36.2" in mineru


def test_cpu_mineru_base_installs_only_stable_dependency_layers() -> None:
    dockerfile = CPU_DOCKERFILE.read_text(encoding="utf-8")
    mineru_stage = dockerfile.split(
        "FROM ${FILEX_OS_BASE_IMAGE} AS filex-mineru-base", 1
    )[1].split("FROM ${FILEX_OS_BASE_IMAGE} AS filex-docling-base", 1)[0]

    assert "requirements.common.txt" in mineru_stage
    assert "requirements.cpu.txt" in mineru_stage
    assert "requirements.mineru.txt" not in mineru_stage


def test_gpu_mineru_base_installs_only_stable_dependency_layers() -> None:
    dockerfile = GPU_DOCKERFILE.read_text(encoding="utf-8")
    mineru_stage = dockerfile.split(
        "FROM filex-os-base-gpu AS filex-mineru-base-gpu", 1
    )[1].split("FROM filex-os-base-gpu AS filex-docling-base-gpu", 1)[0]

    assert "requirements.common.txt" in mineru_stage
    assert "requirements.gpu.txt" in mineru_stage
    assert "requirements.mineru.txt" not in mineru_stage


def test_mineru_runtime_installs_only_the_versioned_mineru_layer() -> None:
    dockerfile = MINERU_RUNTIME_DOCKERFILE.read_text(encoding="utf-8")

    assert "requirements.mineru.txt" in dockerfile
    assert "pip install" in dockerfile
    assert "requirements.txt" not in dockerfile


def test_deploy_fingerprints_leave_mineru_version_out_of_dependency_base() -> None:
    script = (ROOT / "scripts" / "deploy" / "bamboo-compose.sh").read_text(
        encoding="utf-8"
    )

    deps_section = script.split("mineru_deps_fingerprint() {", 1)[1].split(
        "mineru_runtime_fingerprint() {", 1
    )[0]
    runtime_section = script.split("mineru_runtime_fingerprint() {", 1)[1].split(
        "docling_deps_fingerprint() {", 1
    )[0]

    assert "requirements.common.txt" in deps_section
    assert "requirements.cpu.txt" in deps_section
    assert "requirements.gpu.txt" in deps_section
    assert "requirements.mineru.txt" not in deps_section
    assert "requirements.mineru.txt" in runtime_section
    assert "mineru_base_identity_fingerprint" in runtime_section
    assert "MINERU_DEPS_IMAGE" in script


def test_deploy_can_pull_a_stable_registry_dependency_base() -> None:
    compose = COMPOSE.read_text(encoding="utf-8")
    gpu_compose = GPU_COMPOSE.read_text(encoding="utf-8")
    deploy = DEPLOY_SCRIPT.read_text(encoding="utf-8")
    nvidia_deploy = NVIDIA_DEPLOY_SCRIPT.read_text(encoding="utf-8")

    assert "FILEX_MINERU_DEPS_IMAGE" in compose
    assert "FILEX_MINERU_DEPS_IMAGE" in gpu_compose
    assert "FILEX_MINERU_DEPS_IMAGE" in deploy
    assert "docker pull" in deploy
    assert "mineru_base_identity_fp" in nvidia_deploy
    assert "FILEX_MINERU_DEPS_IMAGE" in nvidia_deploy
