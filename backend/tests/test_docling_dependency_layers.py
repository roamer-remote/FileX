from pathlib import Path
import re


ROOT = Path(__file__).resolve().parents[2]
NVIDIA_DEPLOY = ROOT / "scripts" / "deploy" / "deploy-filex-amd64-nvidia.sh"
BAMBOO_DEPLOY = ROOT / "scripts" / "deploy" / "bamboo-compose.sh"
DEPENDENCY_IMAGES = ROOT / "docker" / "dependency-images.env"


def test_gpu_docling_fingerprint_does_not_hash_mineru_stage() -> None:
    script = NVIDIA_DEPLOY.read_text(encoding="utf-8")
    section = re.search(
        r"docling_gpu_fp\(\)\s*\{(?P<body>.*?)\n\}", script, re.DOTALL
    )
    assert section is not None
    section = section.group("body")

    assert "filex-docling-base-gpu" in section
    assert "filex-docling-base-gpu" in section
    assert "mineru_gpu_fp" not in section
    assert "docker/mineru-sidecar" not in section


def test_nvidia_deploy_can_pull_stable_docling_dependency_image() -> None:
    script = NVIDIA_DEPLOY.read_text(encoding="utf-8")
    config = DEPENDENCY_IMAGES.read_text(encoding="utf-8")

    assert 'source "$DEPENDENCY_IMAGES_FILE"' in script
    assert "ghcr.io/roamer-remote/filex-docling-deps:" in config
    assert "docker pull \"$DOCLING_GPU_TAG\"" in script
    assert "docling_base_identity_fp" in script


def test_bamboo_deploy_can_pull_stable_docling_dependency_image() -> None:
    script = BAMBOO_DEPLOY.read_text(encoding="utf-8")

    assert 'source "$DEPENDENCY_IMAGES_FILE"' in script
    assert "docker pull \"$DOCLING_DEPS_IMAGE\"" in script
    assert "docling_base_identity_fingerprint" in script


def test_gpu_docling_base_pins_a_cuda_torch_before_python_dependencies() -> None:
    dockerfile = (ROOT / "docker" / "Dockerfile.gpu").read_text(encoding="utf-8")
    docling_stage = dockerfile.split(
        "FROM filex-os-base-gpu AS filex-docling-base-gpu", 1
    )[1]

    assert "torch==2.6.0" in docling_stage
    assert "https://download.pytorch.org/whl/cu118" in docling_stage
