#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/../.." && pwd)"
cd "$ROOT"

CHECK_ONLY=false
for arg in "$@"; do
  case "$arg" in
    --check|--dry-run) CHECK_ONLY=true ;;
    *) echo "unsupported argument: $arg" >&2; exit 2 ;;
  esac
done

CPU_DEPLOY_SCRIPT="${FILEX_CPU_DEPLOY_SCRIPT:-$ROOT/scripts/deploy/deploy-filex-cpu.sh}"
GPU_DEPLOY_SCRIPT="${FILEX_GPU_DEPLOY_SCRIPT:-$ROOT/scripts/deploy/deploy-filex-amd64-nvidia.sh}"
DOCKER_GPU_TEST_IMAGE="${FILEX_DOCKER_GPU_TEST_IMAGE:-nvidia/cuda:12.6-runtime-ubuntu22.04}"

normalize_arch() {
  case "$(uname -m)" in
    x86_64|amd64) echo "amd64" ;;
    aarch64|arm64) echo "arm64" ;;
    *) echo "unsupported" ;;
  esac
}

ARCH="$(normalize_arch)"
HAS_NVIDIA_SMI=false
HAS_DOCKER_GPU=false
SELECTED_PATH=""

if ! command -v docker >/dev/null 2>&1 || ! docker compose version >/dev/null 2>&1; then
  echo "[detect] ARCH=$ARCH HAS_NVIDIA_SMI=$HAS_NVIDIA_SMI HAS_DOCKER_GPU=$HAS_DOCKER_GPU" >&2
  echo "Docker prerequisite missing" >&2
  exit 13
fi

if command -v nvidia-smi >/dev/null 2>&1 && nvidia-smi >/dev/null 2>&1; then
  HAS_NVIDIA_SMI=true
fi

case "$ARCH" in
  amd64)
    if $HAS_NVIDIA_SMI; then
      if docker run --rm --gpus all "$DOCKER_GPU_TEST_IMAGE" nvidia-smi >/dev/null 2>&1; then
        HAS_DOCKER_GPU=true
        SELECTED_PATH="gpu"
      else
        echo "[detect] ARCH=$ARCH HAS_NVIDIA_SMI=$HAS_NVIDIA_SMI HAS_DOCKER_GPU=$HAS_DOCKER_GPU" >&2
        echo "nvidia-container-toolkit is required for NVIDIA deployment" >&2
        exit 10
      fi
    else
      SELECTED_PATH="cpu"
    fi
    ;;
  arm64)
    if $HAS_NVIDIA_SMI; then
      echo "[detect] ARCH=$ARCH HAS_NVIDIA_SMI=$HAS_NVIDIA_SMI HAS_DOCKER_GPU=$HAS_DOCKER_GPU" >&2
      echo "ARM NVIDIA GPU is not supported by this deploy feature" >&2
      exit 11
    fi
    SELECTED_PATH="cpu"
    ;;
  *)
    echo "[detect] ARCH=$ARCH HAS_NVIDIA_SMI=$HAS_NVIDIA_SMI HAS_DOCKER_GPU=$HAS_DOCKER_GPU" >&2
    echo "unsupported architecture: $(uname -m)" >&2
    exit 12
    ;;
esac

echo "[detect] ARCH=$ARCH HAS_NVIDIA_SMI=$HAS_NVIDIA_SMI HAS_DOCKER_GPU=$HAS_DOCKER_GPU selected_path=$SELECTED_PATH" >&2

if $CHECK_ONLY; then
  exit 0
fi

case "$SELECTED_PATH" in
  cpu) "$CPU_DEPLOY_SCRIPT" ;;
  gpu) "$GPU_DEPLOY_SCRIPT" --current-checkout ;;
esac
