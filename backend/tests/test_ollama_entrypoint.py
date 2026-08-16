import os
import subprocess
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
ENTRYPOINT = ROOT / "docker" / "scripts" / "ollama-entrypoint.sh"


def _write_executable(path: Path, content: str) -> None:
    path.write_text(content, encoding="utf-8")
    path.chmod(0o755)


def _run_entrypoint(tmp_path: Path, *, require_gpu: bool) -> subprocess.CompletedProcess[str]:
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()
    serve_count = tmp_path / "serve-count"
    _write_executable(
        bin_dir / "ollama",
        "#!/bin/sh\n"
        f"count_file={serve_count}\n"
        "case \"$1\" in\n"
        "  serve)\n"
        "    count=$(cat \"$count_file\" 2>/dev/null || echo 0)\n"
        "    count=$((count + 1))\n"
        "    echo \"$count\" > \"$count_file\"\n"
        "    sleep 0.1\n"
        "    ;;\n"
        "  list|show|run) exit 0 ;;\n"
        "  ps)\n"
        "    count=$(cat \"$count_file\" 2>/dev/null || echo 0)\n"
        "    if [ \"$count\" -eq 1 ]; then\n"
        "      printf '%s\\n' 'qwen3.5:9b id 5.6 GB 100% CPU 4096 Forever'\n"
        "    else\n"
        "      printf '%s\\n' 'qwen3.5:9b id 5.6 GB 100% GPU 4096 Forever'\n"
        "    fi\n"
        "    ;;\n"
        "esac\n",
    )
    env = {
        **os.environ,
        "PATH": f"{bin_dir}:{os.environ['PATH']}",
        "OLLAMA_PULL_MODELS": "qwen3.5:9b",
        "OLLAMA_REQUIRE_GPU": "1" if require_gpu else "0",
        "OLLAMA_GPU_WARM_MODEL": "qwen3.5:9b",
        "OLLAMA_GPU_START_RETRIES": "2",
    }
    return subprocess.run(
        ["sh", str(ENTRYPOINT)],
        cwd=ROOT,
        env=env,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        check=False,
        timeout=10,
    )


def test_gpu_entrypoint_restarts_ollama_when_warm_model_falls_back_to_cpu(tmp_path: Path) -> None:
    result = _run_entrypoint(tmp_path, require_gpu=True)

    assert result.returncode == 0, result.stderr
    assert "GPU validation failed on attempt 1/2; restarting Ollama" in result.stderr
    assert "qwen3.5:9b is running on GPU" in result.stdout


def test_cpu_entrypoint_does_not_run_gpu_warmup_or_restart(tmp_path: Path) -> None:
    result = _run_entrypoint(tmp_path, require_gpu=False)

    assert result.returncode == 0, result.stderr
    assert "GPU validation" not in result.stderr
