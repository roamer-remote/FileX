import os
from pathlib import Path
import shutil
import subprocess
from tempfile import NamedTemporaryFile

import pytest
import yaml


ROOT = Path(__file__).resolve().parents[2]
SCRIPT = ROOT / "scripts" / "deploy" / "bamboo-compose.sh"


def test_local_extract_defaults_configure_inspector_runtime() -> None:
    compose = (ROOT / "docker" / "docker-compose.local.yml").read_text(encoding="utf-8")

    # pdf-inspector 开关由系统参数表下发（默认关闭），不再由环境变量控制。
    assert "KB_PDF_INSPECTOR_ENABLED" not in compose
    assert "KB_PDF_INSPECTOR_MODE: ${KB_PDF_INSPECTOR_MODE:-extract}" in compose


def test_bamboo_compose_always_loads_pdf_inspector_overlay() -> None:
    script = SCRIPT.read_text(encoding="utf-8")

    assert "docker/docker-compose.pdf-inspector.yml" in script
    assert "-f docker/docker-compose.pdf-inspector.yml" in script


def test_direct_cpu_and_gpu_deployers_load_the_same_overlay() -> None:
    cpu = (ROOT / "scripts/deploy/deploy-filex-cpu.sh").read_text(encoding="utf-8")
    gpu = (ROOT / "scripts/deploy/deploy-filex-amd64-nvidia.sh").read_text(encoding="utf-8")

    assert "docker/docker-compose.pdf-inspector.yml" in cpu
    assert "docker/docker-compose.pdf-inspector.yml" in gpu


def test_pdf_inspector_overlay_defaults_configure_runtime_and_overridable() -> None:
    overlay = (ROOT / "docker" / "docker-compose.pdf-inspector.yml").read_text(encoding="utf-8")

    assert "KB_PDF_INSPECTOR_ENABLED" not in overlay
    assert "KB_PDF_INSPECTOR_MODE: ${KB_PDF_INSPECTOR_MODE:-extract}" in overlay
    assert "KB_PDF_INSPECTOR_TIMEOUT_SEC: ${KB_PDF_INSPECTOR_TIMEOUT_SEC:-120}" in overlay


def test_gpu_overlay_targets_gpu_scheduler_with_inspector_runtime() -> None:
    gpu_overlay = (ROOT / "docker" / "docker-compose.gpu.yml").read_text(encoding="utf-8")

    # GPU 调度部署下 mineru 提取由 gpu-scheduler 执行，与 kb-extract 一致下发
    # pdf-inspector 运行时参数；开关本身由系统参数表控制（默认关闭）。
    assert "KB_PDF_INSPECTOR_ENABLED" not in gpu_overlay
    assert "KB_PDF_INSPECTOR_MODE: ${KB_PDF_INSPECTOR_MODE:-extract}" in gpu_overlay
    assert "KB_PDF_INSPECTOR_TIMEOUT_SEC: ${KB_PDF_INSPECTOR_TIMEOUT_SEC:-120}" in gpu_overlay


def test_app_base_requirements_include_pdf_inspector_for_gpu_scheduler() -> None:
    # gpu-scheduler 使用 filex/app 基础镜像（装 requirements.txt）。GPU 调度下
    # 它才是 mineru 提取的实际执行者，必须在 app 基础镜像中携带 pdf-inspector。
    requirements = (ROOT / "backend" / "requirements.txt").read_text(encoding="utf-8")
    assert "pdf-inspector==" in requirements


def test_extract_deployment_entrypoint_builds_and_recreates_extract() -> None:
    script = SCRIPT.read_text(encoding="utf-8")

    assert "build-app-and-up-extract-workers)" in script
    assert "ensure_extract_base" in script
    assert 'compose_up -d --force-recreate --no-build "${APP_WORKER_SERVICES[@]}" kb-extract' in script


def _render_production_compose(*, gpu: bool, overrides: dict[str, str] | None = None) -> str:
    if shutil.which("docker") is None:
        pytest.skip("docker is unavailable")

    files = [
        "-f",
        "docker/docker-compose.yml",
        "-f",
        "docker/docker-compose.prod.yml",
        "-f",
        "docker/docker-compose.pdf-inspector.yml",
    ]
    if gpu:
        files.extend(["-f", "docker/docker-compose.gpu.yml"])
    with NamedTemporaryFile("w", encoding="utf-8") as secrets:
        secrets.write(
            "FILEX_SECRET_KEY=test\n"
            "KB_PDF_INSPECTOR_MODE=disabled\n"
            "KB_PDF_INSPECTOR_TIMEOUT_SEC=17\n"
        )
        secrets.flush()
        env = {key: value for key, value in os.environ.items() if not key.startswith("KB_PDF_INSPECTOR_")}
        env["FILEX_SECRETS_FILE"] = secrets.name
        env.update(overrides or {})
        result = subprocess.run(
            ["docker", "compose", *files, "config"],
            cwd=ROOT,
            env=env,
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            check=False,
        )

    assert result.returncode == 0, result.stderr
    return result.stdout


@pytest.mark.parametrize("gpu", [False, True])
def test_production_compose_renders_inspector_for_cpu_and_gpu(gpu: bool) -> None:
    rendered = _render_production_compose(gpu=gpu)
    services = yaml.safe_load(rendered)["services"]
    extract_environment = services["kb-extract"]["environment"]

    # pdf-inspector 开关由系统参数表控制（默认关闭），不再由环境变量下发。
    assert "KB_PDF_INSPECTOR_ENABLED" not in extract_environment
    assert extract_environment["KB_PDF_INSPECTOR_MODE"] == "extract"
    assert extract_environment["KB_PDF_INSPECTOR_TIMEOUT_SEC"] == "120"
    if gpu:
        scheduler_environment = services["gpu-scheduler"]["environment"]
        assert "KB_PDF_INSPECTOR_ENABLED" not in scheduler_environment
        assert scheduler_environment["KB_PDF_INSPECTOR_MODE"] == "extract"
        assert scheduler_environment["KB_PDF_INSPECTOR_TIMEOUT_SEC"] == "120"
        target_services = ("filex-mineru", "gpu-scheduler")
        for service_name in target_services:
            devices = services[service_name]["deploy"]["resources"]["reservations"]["devices"]
            assert any(
                device.get("driver") == "nvidia"
                and device.get("count") == 1
                and "gpu" in device.get("capabilities", [])
                for device in devices
            )
    else:
        for service_name in ("filex-mineru",):
            deploy = services[service_name].get("deploy", {})
            devices = deploy.get("resources", {}).get("reservations", {}).get("devices", [])
            assert not any(device.get("driver") == "nvidia" for device in devices)


@pytest.mark.parametrize("gpu", [False, True])
def test_production_compose_accepts_ci_environment_overrides(gpu: bool) -> None:
    rendered = _render_production_compose(
        gpu=gpu,
        overrides={
            "KB_PDF_INSPECTOR_MODE": "disabled",
            "KB_PDF_INSPECTOR_TIMEOUT_SEC": "17",
        },
    )
    extract_environment = yaml.safe_load(rendered)["services"]["kb-extract"]["environment"]

    assert "KB_PDF_INSPECTOR_ENABLED" not in extract_environment
    assert extract_environment["KB_PDF_INSPECTOR_MODE"] == "disabled"
    assert extract_environment["KB_PDF_INSPECTOR_TIMEOUT_SEC"] == "17"
