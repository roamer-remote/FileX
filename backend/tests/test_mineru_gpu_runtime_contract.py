from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
GPU_DOCKERFILE = ROOT / "docker" / "Dockerfile.gpu"
CPU_DOCKERFILE = ROOT / "docker" / "Dockerfile.base"
GPU_REQUIREMENTS = ROOT / "docker" / "mineru-sidecar" / "requirements.gpu.txt"
MINERU_REQUIREMENTS = ROOT / "docker" / "mineru-sidecar" / "requirements.mineru.txt"
MINERU_RUNNER = ROOT / "docker" / "mineru-sidecar" / "mineru_runner.py"
MINERU_V4_RUNNER = ROOT / "docker" / "mineru-sidecar" / "mineru_v4_runner.py"
MINERU_ENTRYPOINT = ROOT / "docker" / "mineru-sidecar" / "entrypoint.sh"
PYTHON_COMPAT = ROOT / "docker" / "mineru-sidecar" / "sitecustomize.py"


def test_gpu_mineru_image_uses_ubuntu_2204_cuda_base() -> None:
    dockerfile = GPU_DOCKERFILE.read_text(encoding="utf-8")

    assert "ubuntu22.04" in dockerfile


def test_gpu_mineru_image_installs_python_310_mineru_compatibility_shim() -> None:
    dockerfile = GPU_DOCKERFILE.read_text(encoding="utf-8")
    shim = PYTHON_COMPAT.read_text(encoding="utf-8")

    assert "docker/mineru-sidecar/sitecustomize.py /tmp/filex-sitecustomize.py" in dockerfile
    assert "sysconfig.get_path(\"stdlib\")" in dockerfile
    assert "datetime.UTC = datetime.timezone.utc" in shim


def test_mineru_runtime_reinstalls_python_compatibility_shim() -> None:
    dockerfile = (ROOT / "docker" / "Dockerfile.mineru-sidecar").read_text(encoding="utf-8")

    assert "docker/mineru-sidecar/sitecustomize.py /tmp/filex-sitecustomize.py" in dockerfile
    assert "sysconfig.get_path(\"stdlib\")" in dockerfile


def test_gpu_mineru_requirements_pin_cuda_torch() -> None:
    assert GPU_REQUIREMENTS.is_file()
    requirements = GPU_REQUIREMENTS.read_text(encoding="utf-8")
    assert "torch-2.6.0%2Bcu118-cp310-cp310-linux_x86_64.whl" in requirements
    assert "torchvision-0.21.0%2Bcu118-cp310-cp310-linux_x86_64.whl" in requirements


def test_mineru_v4_uses_local_torch_pipeline_dependencies() -> None:
    assert "mineru[torch]==4.0.0a6" in MINERU_REQUIREMENTS.read_text(encoding="utf-8")


def test_mineru_v4_runtime_does_not_call_removed_cli_flags() -> None:
    runner = MINERU_RUNNER.read_text(encoding="utf-8")
    adapter = MINERU_V4_RUNNER.read_text(encoding="utf-8")

    assert '"/app/sidecar/mineru_v4_runner.py"' in runner
    assert 'from mineru.cli_old.common import do_parse' in adapter


def test_mineru_v4_entrypoint_uses_supported_basic_model_tier() -> None:
    entrypoint = MINERU_ENTRYPOINT.read_text(encoding="utf-8")

    assert "mineru-kit models download --tier basic --stack \"$MODEL_STACK\"" in entrypoint
    assert "mineru-kit models verify --tier basic --stack \"$MODEL_STACK\"" in entrypoint
    assert "--tier medium" not in entrypoint


def test_mineru_v4_entrypoint_requires_layout_model_before_skipping_download() -> None:
    entrypoint = MINERU_ENTRYPOINT.read_text(encoding="utf-8")

    assert '"$V4_MODEL_DIR/models/Layout/PP-DocLayoutV2"' in entrypoint
    assert '"$V4_MODEL_DIR/models/OCR/paddleocr_torch/ch_PP-OCRv6_small_det_infer.safetensors"' in entrypoint
    assert 'mineru-kit models verify --tier basic --stack "$MODEL_STACK" >/dev/null 2>&1' in entrypoint


def test_gpu_mineru_stage_installs_gpu_requirements() -> None:
    dockerfile = GPU_DOCKERFILE.read_text(encoding="utf-8")

    assert "docker/mineru-sidecar/requirements.gpu.txt" in dockerfile
    assert "-r requirements.gpu.txt" in dockerfile


def test_gpu_image_uses_isolated_python_environment() -> None:
    dockerfile = GPU_DOCKERFILE.read_text(encoding="utf-8")

    assert "python3 -m venv /opt/filex-venv" in dockerfile
    assert 'ENV PATH="/opt/filex-venv/bin:${PATH}"' in dockerfile
    assert "https://mirrors.aliyun.com/pypi/simple/" in dockerfile


def test_gpu_image_retries_large_pytorch_downloads() -> None:
    dockerfile = GPU_DOCKERFILE.read_text(encoding="utf-8")

    assert "--timeout 600 --retries 10" in dockerfile


def test_gpu_mineru_stage_keeps_common_dependencies_on_domestic_pypi_mirror() -> None:
    dockerfile = GPU_DOCKERFILE.read_text(encoding="utf-8")
    mineru_stage = dockerfile.split(
        "FROM filex-os-base-gpu AS filex-mineru-base-gpu", 1
    )[1].split("FROM filex-os-base-gpu AS filex-docling-base-gpu", 1)[0]

    assert "--index-url https://mirrors.aliyun.com/pypi/simple/" in mineru_stage
    assert "--extra-index-url ${PYTORCH_INDEX_URL}" not in mineru_stage


def test_gpu_entrypoint_rejects_unsupported_device_architecture() -> None:
    entrypoint = MINERU_ENTRYPOINT.read_text(encoding="utf-8")

    assert "torch.cuda.get_device_capability(0)" in entrypoint
    assert "torch.cuda.get_arch_list()" in entrypoint
    assert 'f"sm_{capability[0]}{capability[1]}"' in entrypoint


def test_gpu_entrypoint_accepts_sm61_with_sm60_cuda_kernel() -> None:
    entrypoint = MINERU_ENTRYPOINT.read_text(encoding="utf-8")

    assert 'arch == "sm_61"' in entrypoint
    assert '"sm_60" in arch_list' in entrypoint


def test_gpu_runner_does_not_fallback_to_cpu() -> None:
    runner = MINERU_RUNNER.read_text(encoding="utf-8")

    assert "retrying with CPU" not in runner
    assert "CPU fallback is disabled" in runner


def test_cpu_mineru_stage_does_not_install_gpu_requirements() -> None:
    assert "requirements.gpu.txt" not in CPU_DOCKERFILE.read_text(encoding="utf-8")
