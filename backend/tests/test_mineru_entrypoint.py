import os
import subprocess
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
ENTRYPOINT = ROOT / "docker" / "mineru-sidecar" / "entrypoint.sh"


def _prepare_ready_models(tmp_path: Path) -> tuple[Path, Path]:
    models_dir = tmp_path / "models"
    pipeline_dir = models_dir / "pipeline"
    layout_dir = pipeline_dir / "models" / "Layout" / "PP-DocLayoutV2"
    ocr_dir = pipeline_dir / "models" / "OCR" / "paddleocr_torch"
    layout_dir.mkdir(parents=True)
    ocr_dir.mkdir(parents=True)
    (layout_dir / "config.json").write_text("{}\n", encoding="utf-8")
    (ocr_dir / "ch_PP-OCRv6_small_det_infer.safetensors").write_bytes(b"ready")
    (models_dir / ".pipeline_complete").write_text("ok\n", encoding="utf-8")
    config_json = models_dir / "mineru.json"
    config_json.write_text('{"models-dir":{"pipeline":"pipeline","vlm":""}}\n', encoding="utf-8")
    return models_dir, config_json


def _run_entrypoint(
    tmp_path: Path,
    *,
    device: str = "cpu",
    cuda_probe_exit: int = 0,
) -> subprocess.CompletedProcess[str]:
    models_dir, config_json = _prepare_ready_models(tmp_path)

    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()
    python_stub = bin_dir / "python3"
    probe_count = tmp_path / "python-call-count"
    python_stub.write_text(
        "#!/usr/bin/env bash\n"
        f"count_file={probe_count}\n"
        "count=0\n"
        "[[ -f $count_file ]] && count=$(cat $count_file)\n"
        "count=$((count + 1))\n"
        "printf '%s' $count > $count_file\n"
        "if [[ ${MINERU_DEVICE:-cpu} == cuda && $count -eq 2 ]]; then\n"
        f"  exit {cuda_probe_exit}\n"
        "fi\n"
        "printf '9.8.7\\n'\n",
        encoding="utf-8",
    )
    python_stub.chmod(0o755)
    uvicorn_stub = bin_dir / "uvicorn"
    uvicorn_stub.write_text("#!/usr/bin/env bash\nprintf 'uvicorn %s\\n' \"$*\"\n", encoding="utf-8")
    uvicorn_stub.chmod(0o755)
    mineru_kit_stub = bin_dir / "mineru-kit"
    mineru_kit_stub.write_text("#!/usr/bin/env bash\nexit 0\n", encoding="utf-8")
    mineru_kit_stub.chmod(0o755)

    return subprocess.run(
        ["sh", str(ENTRYPOINT)],
        cwd=ROOT,
        env={
            **os.environ,
            "PATH": f"{bin_dir}:{os.environ['PATH']}",
            "MINERU_MODELS_DIR": str(models_dir),
            "MINERU_TOOLS_CONFIG_JSON": str(config_json),
            "MINERU_DEVICE": device,
        },
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        check=False,
    )


def test_entrypoint_prints_installed_mineru_version_on_startup(tmp_path: Path) -> None:
    result = _run_entrypoint(tmp_path)

    assert result.returncode == 0, result.stderr
    assert "[entrypoint] mineru version: 9.8.7" in result.stdout
    assert "complete MinerU 4 basic models found; skip download" in result.stdout
    assert "uvicorn main:app --host 0.0.0.0 --port 8080" in result.stdout


def test_entrypoint_rejects_cuda_device_without_a_working_cuda_runtime(tmp_path: Path) -> None:
    result = _run_entrypoint(tmp_path, device="cuda", cuda_probe_exit=1)

    assert result.returncode == 78
    assert "MINERU_DEVICE=cuda requires a visible GPU with a supported PyTorch kernel" in result.stderr


def test_entrypoint_does_not_require_torch_for_cpu_device(tmp_path: Path) -> None:
    result = _run_entrypoint(tmp_path, device="cpu", cuda_probe_exit=1)

    assert result.returncode == 0, result.stderr
