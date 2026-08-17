#!/usr/bin/env bash
# Bamboo 生产部署（自动检测 CPU/GPU，版本号未设时自动生成）：
#
#   cd /root/docker/important/FileX/product
#
#   # 仅更新 API/前端（最常用，版本号自动生成 yyyy-mm-dd-hh-mm-ss-<sha>）
#   ./scripts/deploy/bamboo-compose.sh build-app-and-up-workers
#
#   # 全量构建 + 启动（版本号可手动指定，未设则自动生成）
#   ./scripts/deploy/bamboo-compose.sh build
#   ./scripts/deploy/bamboo-compose.sh up -d --no-build filex kb-indexer kb-post kb-ragas-eval kb-extract filex-mineru filex-docling
#
# Bamboo CI/CD 或终端均可直接调用：
#   ./scripts/deploy/bamboo-compose.sh build-app-and-up-workers
set -euo pipefail
export DOCKER_BUILDKIT=1

# ── GPU / 架构自动检测 ──────────────────────────────────────────
ARCH="$(uname -m)"
HAS_GPU=false
if command -v nvidia-smi >/dev/null 2>&1 && nvidia-smi >/dev/null 2>&1; then
  HAS_GPU=true
fi
echo "[detect] ARCH=$ARCH HAS_GPU=$HAS_GPU" >&2

# filex/app 镜像的 API/Worker 容器；partial up 必须全部一起，避免任一消费者代码落后。
APP_WORKER_SERVICES=(filex kb-indexer kb-post kb-ragas-eval)
if $HAS_GPU; then
  # 164 §6：GPU 部署时一并启动 gpu-scheduler（同一 filex/app 镜像）。
  APP_WORKER_SERVICES+=(gpu-scheduler)
fi

ROOT="$(cd "$(dirname "$0")/../.." && pwd)"
cd "$ROOT"

DOCLING_DEPS_IMAGE=""
if $HAS_GPU; then
  DEPENDENCY_IMAGES_FILE="$ROOT/docker/dependency-images.env"
  if [[ ! -f "$DEPENDENCY_IMAGES_FILE" ]]; then
    echo "ERROR: 缺少仓库内 GPU 依赖镜像配置: $DEPENDENCY_IMAGES_FILE" >&2
    exit 1
  fi
  # shellcheck disable=SC1090
  source "$DEPENDENCY_IMAGES_FILE"
  : "${FILEX_DOCLING_DEPS_IMAGE:?配置文件未设置 FILEX_DOCLING_DEPS_IMAGE}"
  DOCLING_DEPS_IMAGE="$FILEX_DOCLING_DEPS_IMAGE"
  export FILEX_DOCLING_DEPS_IMAGE
fi

# 同一主机只允许一个部署流程，避免多个部署重试任务并发占用 BuildKit。
# FILEX_DEPLOY_LOCK_DIR 可由测试或不同部署根目录覆盖；默认目录不落在项目仓库内。
DEPLOY_LOCK_DIR="${FILEX_DEPLOY_LOCK_DIR:-/tmp/filex-bamboo-compose.lock}"
DEPLOY_LOCK_ACQUIRED=false

release_deploy_lock() {
  if $DEPLOY_LOCK_ACQUIRED; then
    rm -f "$DEPLOY_LOCK_DIR/pid"
    rmdir "$DEPLOY_LOCK_DIR" 2>/dev/null || true
  fi
}

acquire_deploy_lock() {
  local lock_pid=""
  mkdir -p "$(dirname "$DEPLOY_LOCK_DIR")"
  if mkdir "$DEPLOY_LOCK_DIR" 2>/dev/null; then
    printf '%s\n' "$$" > "$DEPLOY_LOCK_DIR/pid"
    DEPLOY_LOCK_ACQUIRED=true
    trap release_deploy_lock EXIT
    return 0
  fi

  if [[ -f "$DEPLOY_LOCK_DIR/pid" ]]; then
    read -r lock_pid < "$DEPLOY_LOCK_DIR/pid" || true
  fi
  if [[ "$lock_pid" =~ ^[0-9]+$ ]] && kill -0 "$lock_pid" 2>/dev/null; then
    echo "ERROR: 已有部署正在运行 (pid=${lock_pid}, lock=${DEPLOY_LOCK_DIR})" >&2
    exit 75
  fi

  echo "[deploy-lock] 清理已退出进程遗留的部署锁: $DEPLOY_LOCK_DIR" >&2
  rm -f "$DEPLOY_LOCK_DIR/pid"
  rmdir "$DEPLOY_LOCK_DIR" 2>/dev/null || {
    echo "ERROR: 无法回收部署锁，请确认没有其他部署正在初始化: $DEPLOY_LOCK_DIR" >&2
    exit 75
  }
  if ! mkdir "$DEPLOY_LOCK_DIR" 2>/dev/null; then
    echo "ERROR: 无法获取部署锁，另一个部署可能刚刚启动: $DEPLOY_LOCK_DIR" >&2
    exit 75
  fi
  printf '%s\n' "$$" > "$DEPLOY_LOCK_DIR/pid"
  DEPLOY_LOCK_ACQUIRED=true
  trap release_deploy_lock EXIT
}

acquire_deploy_lock

SECRETS_FILE="${FILEX_SECRETS_FILE:-/root/docker/important/FileX/secrets/filex.env}"
BUILD_VERSION_RE='^[0-9]{4}-[0-9]{2}-[0-9]{2}-[0-9]{2}-[0-9]{2}-[0-9]{2}-[0-9a-f]{7}$'
# 版本号：已设则校验格式，未设则自动生成（yyyy-mm-dd-hh-mm-ss-<7位hex>）
require_build_version() {
  if [[ -z "${FILEX_APP_BUILD_VERSION:-}" ]]; then
    local build_date build_sha
    build_date="$(TZ=Asia/Shanghai date +%Y-%m-%d-%H-%M-%S)"
    build_sha="$(git rev-parse --short=7 HEAD)"
    export FILEX_APP_BUILD_VERSION="${build_date}-${build_sha}"
    echo "[auto-version] FILEX_APP_BUILD_VERSION=${FILEX_APP_BUILD_VERSION}" >&2
    return 0
  fi
  if [[ ! "${FILEX_APP_BUILD_VERSION}" =~ $BUILD_VERSION_RE ]]; then
    echo "ERROR: FILEX_APP_BUILD_VERSION 格式非法: ${FILEX_APP_BUILD_VERSION}" >&2
    echo "须匹配 yyyy-mm-dd-hh-mm-ss-<7位十六进制>" >&2
    exit 1
  fi
}

if [[ ! -f "$SECRETS_FILE" ]]; then
  echo "ERROR: 缺少生产密钥文件: $SECRETS_FILE" >&2
  echo "请一次性创建: mkdir -p $(dirname "$SECRETS_FILE") && cp scripts/deploy/filex-secrets.env.example $SECRETS_FILE" >&2
  exit 1
fi

compose() {
  local -a files=(
    -f docker/docker-compose.yml
    -f docker/docker-compose.prod.yml
    -f docker/docker-compose.pdf-inspector.yml
  )
  if $HAS_GPU && [[ -f docker/docker-compose.gpu.yml ]]; then
    files+=(-f docker/docker-compose.gpu.yml)
  fi
  if [[ -f docker/docker-compose.override.yml ]]; then
    files+=(-f docker/docker-compose.override.yml)
  fi
  docker compose "${files[@]}" "$@"
}

OS_BASE_IMAGE="filex/os-base:${FILEX_BASE_VERSION:-py3.13}"
APP_BASE_IMAGE="filex/app-base:${FILEX_BASE_VERSION:-py3.13}"
APP_IMAGE="filex/app:${FILEX_VERSION:-latest}"
EXTRACT_BASE_IMAGE="filex/kb-extract-base:${FILEX_BASE_VERSION:-py3.13}"
EXTRACT_IMAGE="filex/kb-extract:${FILEX_VERSION:-latest}"
MINERU_BASE_IMAGE="filex/mineru-base:${FILEX_BASE_VERSION:-py3.13}"
MINERU_IMAGE="filex-filex-mineru:${FILEX_VERSION:-latest}"
DOCLING_BASE_IMAGE="filex/docling-base:${FILEX_BASE_VERSION:-py3.13}"
DOCLING_IMAGE="filex-filex-docling:${FILEX_VERSION:-latest}"
if $HAS_GPU; then
  MINERU_BASE_IMAGE="filex/mineru-base:${FILEX_BASE_VERSION:-py3.13}-gpu"
  DOCLING_BASE_IMAGE="filex/docling-base:${FILEX_BASE_VERSION:-py3.13}-gpu"
fi
MINERU_DEPS_IMAGE="${FILEX_MINERU_DEPS_IMAGE:-}"
if [[ -n "$DOCLING_DEPS_IMAGE" ]]; then
  DOCLING_BASE_IMAGE="$DOCLING_DEPS_IMAGE"
fi
RERANK_SOURCE_IMAGE="${FILEX_RERANK_SOURCE_IMAGE:-ghcr.io/huggingface/text-embeddings-inference:cpu-1.9.3}"
RERANK_IMAGE="filex/tei-rerank:cpu-1.9.3"
PYTHON_313_IMAGE="${FILEX_PYTHON_313_IMAGE:-docker.m.daocloud.io/library/python:3.13-slim}"
NODE_20_IMAGE="${FILEX_NODE_20_IMAGE:-docker.m.daocloud.io/library/node:20-alpine}"
BUILD_HTTP_PROXY="${BUILD_HTTP_PROXY:-}"
MINERU_GPU_PYTORCH_INDEX_URL="${MINERU_GPU_PYTORCH_INDEX_URL:-${PYTORCH_INDEX_URL:-https://download.pytorch.org/whl/cu118}}"

# 由 ensure_app_base 设置：当 app-base 因依赖变更而重建时为 true，
# build_app 据此决定是否 --no-cache 以确保使用新依赖层。
APP_BASE_REBUILT=false

os_deps_fingerprint() {
  sed -n '1,32p' docker/Dockerfile.base | sha256sum | awk '{print $1}'
}

app_deps_fingerprint() {
  {
    sed -n '/AS filex-app-base/,/pip install/p' docker/Dockerfile.base | sha256sum
    os_deps_fingerprint
    sha256sum backend/requirements.txt
  } | sha256sum | awk '{print $1}'
}

extract_deps_fingerprint() {
  {
    os_deps_fingerprint
    sha256sum backend/requirements.txt backend/requirements-extract.txt
    sed -n '/AS filex-extract-base/,/pip install/p' docker/Dockerfile.base | sha256sum
  } | sha256sum | awk '{print $1}'
}

mineru_deps_fingerprint() {
  if $HAS_GPU; then
    sha256sum \
      docker/Dockerfile.gpu \
      docker/mineru-sidecar/requirements.common.txt \
      docker/mineru-sidecar/requirements.gpu.txt \
      docker/mineru-sidecar/sitecustomize.py | sha256sum | awk '{print $1}'
    return 0
  fi
  {
    os_deps_fingerprint
    sha256sum \
      docker/mineru-sidecar/requirements.common.txt \
      docker/mineru-sidecar/requirements.cpu.txt
    sed -n '/AS filex-mineru-base/,/pip install/p' docker/Dockerfile.base | sha256sum
  } | sha256sum | awk '{print $1}'
}

mineru_runtime_fingerprint() {
  {
    mineru_deps_fingerprint
    mineru_base_identity_fingerprint
    sha256sum docker/mineru-sidecar/requirements.mineru.txt
    sha256sum \
      docker/Dockerfile.mineru-sidecar \
      docker/mineru-sidecar/main.py \
      docker/mineru-sidecar/mq_consumer.py \
      docker/mineru-sidecar/lifecycle_state.py \
      docker/mineru-sidecar/mineru_runner.py \
      docker/mineru-sidecar/mineru_v4_runner.py \
      docker/mineru-sidecar/table_rotation.py \
      docker/mineru-sidecar/entrypoint.sh \
      backend/logging_setup.py
  } | sha256sum | awk '{print $1}'
}

mineru_base_identity_fingerprint() {
  {
    printf 'ref=%s\n' "${MINERU_BASE_IMAGE}"
    if [[ -n "$MINERU_DEPS_IMAGE" ]]; then
      docker image inspect "$MINERU_DEPS_IMAGE" --format '{{.Id}}' 2>/dev/null || true
    fi
  } | sha256sum | awk '{print $1}'
}

docling_base_identity_fingerprint() {
  {
    printf 'ref=%s\n' "$DOCLING_BASE_IMAGE"
    if [[ -n "$DOCLING_DEPS_IMAGE" ]]; then
      docker image inspect "$DOCLING_DEPS_IMAGE" --format '{{.Id}}' 2>/dev/null || true
    fi
  } | sha256sum | awk '{print $1}'
}

docling_deps_fingerprint() {
  if $HAS_GPU; then
    {
      sed -n '/^FROM ${CUDA_BASE_IMAGE} AS filex-os-base-gpu/,/^FROM filex-os-base-gpu AS filex-mineru-base-gpu/p' docker/Dockerfile.gpu
      sed -n '/^FROM filex-os-base-gpu AS filex-docling-base-gpu/,$p' docker/Dockerfile.gpu
      sha256sum docker/docling-sidecar/requirements.txt
    } | sha256sum | awk '{print $1}'
    return 0
  fi
  {
    os_deps_fingerprint
    sha256sum docker/docling-sidecar/requirements.txt
    sed -n '/AS filex-docling-base/,/pip install/p' docker/Dockerfile.base | sha256sum
  } | sha256sum | awk '{print $1}'
}

build_os_base() {
  local fp
  fp="$(os_deps_fingerprint)"
  docker build \
    -f docker/Dockerfile.base \
    --target filex-os-base \
    -t "$OS_BASE_IMAGE" \
    --build-arg "PYTHON_IMAGE=$PYTHON_313_IMAGE" \
    --label "filex.os.deps=$fp" \
    .
}

ensure_os_base() {
  local fp stored
  fp="$(os_deps_fingerprint)"
  if docker image inspect "$OS_BASE_IMAGE" >/dev/null 2>&1; then
    stored="$(docker image inspect "$OS_BASE_IMAGE" --format '{{index .Config.Labels "filex.os.deps"}}' 2>/dev/null || true)"
    if [[ "$stored" == "$fp" ]]; then
      echo "复用 OS 基础镜像（依赖未变）: $OS_BASE_IMAGE"
      return 0
    fi
    echo "OS 底层已变更，重建 os-base (旧=${stored:-none} 新=$fp)" >&2
  else
    echo "OS 基础镜像不存在，开始构建: $OS_BASE_IMAGE" >&2
  fi
  build_os_base
}

build_app_base() {
  local fp
  fp="$(app_deps_fingerprint)"
  ensure_os_base
  docker build \
    -f docker/Dockerfile.base \
    --target filex-app-base \
    -t "$APP_BASE_IMAGE" \
    --build-arg "FILEX_OS_BASE_IMAGE=$OS_BASE_IMAGE" \
    --label "filex.app.deps=$fp" \
    .
}

ensure_app_base() {
  local fp stored
  fp="$(app_deps_fingerprint)"
  if docker image inspect "$APP_BASE_IMAGE" >/dev/null 2>&1; then
    stored="$(docker image inspect "$APP_BASE_IMAGE" --format '{{index .Config.Labels "filex.app.deps"}}' 2>/dev/null || true)"
    if [[ "$stored" == "$fp" ]]; then
      echo "复用 app 基础镜像（依赖未变）: $APP_BASE_IMAGE"
      APP_BASE_REBUILT=false
      return 0
    fi
    echo "app 依赖已变更，重建 app-base (旧=${stored:-none} 新=$fp)" >&2
  else
    echo "app 基础镜像不存在，开始构建: $APP_BASE_IMAGE" >&2
  fi
  build_app_base
  APP_BASE_REBUILT=true
}

build_app() {
  # 始终 --no-cache：app 镜像只做 COPY（backend + frontend dist），无 pip install，
  # 避免 Docker 层缓存误用旧源码导致 Pydantic schema / 路由等 Python 文件不更新。
  docker build \
    --no-cache \
    -f docker/Dockerfile \
    --add-host host.docker.internal:host-gateway \
    -t "$APP_IMAGE" \
    --build-arg "APP_BASE_IMAGE=$APP_BASE_IMAGE" \
    --build-arg "NODE_IMAGE=$NODE_20_IMAGE" \
    --build-arg "PYTHON_IMAGE=$PYTHON_313_IMAGE" \
    --build-arg "BUILD_HTTP_PROXY=$BUILD_HTTP_PROXY" \
    --build-arg "VITE_APP_BUILD_VERSION=$FILEX_APP_BUILD_VERSION" \
    .
}

build_extract_base() {
  local fp
  fp="$(extract_deps_fingerprint)"
  ensure_os_base
  docker build \
    -f docker/Dockerfile.base \
    --target filex-extract-base \
    -t "$EXTRACT_BASE_IMAGE" \
    --build-arg "FILEX_OS_BASE_IMAGE=$OS_BASE_IMAGE" \
    --label "filex.extract.deps=$fp" \
    .
}

ensure_extract_base() {
  local fp stored
  fp="$(extract_deps_fingerprint)"
  if docker image inspect "$EXTRACT_BASE_IMAGE" >/dev/null 2>&1; then
    stored="$(docker image inspect "$EXTRACT_BASE_IMAGE" --format '{{index .Config.Labels "filex.extract.deps"}}' 2>/dev/null || true)"
    if [[ "$stored" == "$fp" ]]; then
      echo "复用 extract 基础镜像（依赖未变）: $EXTRACT_BASE_IMAGE"
      return 0
    fi
    echo "extract 依赖已变更，重建 extract-base (旧=${stored:-none} 新=$fp)" >&2
  else
    echo "extract 基础镜像不存在，开始构建: $EXTRACT_BASE_IMAGE" >&2
  fi
  build_extract_base
}

build_extract() {
  docker build \
    -f docker/Dockerfile.extract \
    -t "$EXTRACT_IMAGE" \
    --build-arg "EXTRACT_BASE_IMAGE=$EXTRACT_BASE_IMAGE" \
    .
}

build_mineru_base() {
  local fp
  fp="$(mineru_deps_fingerprint)"
  ensure_os_base
  docker build \
    -f docker/Dockerfile.base \
    --target filex-mineru-base \
    -t "$MINERU_BASE_IMAGE" \
    --build-arg "FILEX_OS_BASE_IMAGE=$OS_BASE_IMAGE" \
    --label "filex.mineru.deps=$fp" \
    .
}

build_mineru() {
  local fp
  fp="$(mineru_runtime_fingerprint)"
  docker build \
    -f docker/Dockerfile.mineru-sidecar \
    --target mineru-runtime \
    -t "$MINERU_IMAGE" \
    --build-arg "MINERU_BASE_IMAGE=$MINERU_BASE_IMAGE" \
    --label "filex.mineru.runtime=$fp" \
    .
  verify_mineru_gpu_runtime
}

verify_mineru_gpu_runtime() {
  if ! $HAS_GPU; then
    return 0
  fi

  local expected_runtime actual_runtime
  expected_runtime="$(mineru_runtime_fingerprint)"
  actual_runtime="$(docker image inspect "$MINERU_IMAGE" --format '{{index .Config.Labels "filex.mineru.runtime"}}' 2>/dev/null || true)"
  if [[ -z "$actual_runtime" || "$actual_runtime" != "$expected_runtime" ]]; then
    echo "ERROR: MinerU runtime 镜像与当前源码不一致；不会启动或替换 filex-mineru" >&2
    echo "       expected=$expected_runtime actual=${actual_runtime:-missing}" >&2
    return 1
  fi

  echo "验证 MinerU CUDA 运行时..." >&2
  if ! docker run --rm --gpus all --entrypoint python3 "$MINERU_IMAGE" -c '
import torch
from mineru.cli.main import app

assert torch.cuda.is_available(), "CUDA is unavailable"
assert torch.cuda.device_count() > 0, "no CUDA devices are visible"
capability = torch.cuda.get_device_capability(0)
arch = f"sm_{capability[0]}{capability[1]}"
arch_list = torch.cuda.get_arch_list()
# The cu118 wheel exposes sm_60 for Pascal and its kernels run on sm_61.
if arch not in arch_list and not (arch == "sm_61" and "sm_60" in arch_list):
    raise RuntimeError(
        f"GPU architecture {arch} is not compiled into this PyTorch wheel; "
        "refusing a CPU fallback"
    )
print(f"MinerU CUDA ready: {torch.cuda.get_device_name(0)}")
'; then
    echo "ERROR: MinerU GPU 镜像未通过 CUDA 运行时校验；不会启动或替换 filex-mineru" >&2
    return 1
  fi
}

build_docling_base() {
  local fp
  fp="$(docling_deps_fingerprint)"
  ensure_os_base
  docker build \
    -f docker/Dockerfile.base \
    --target filex-docling-base \
    -t "$DOCLING_BASE_IMAGE" \
    --build-arg "FILEX_OS_BASE_IMAGE=$OS_BASE_IMAGE" \
    --label "filex.docling.deps=$fp" \
    .
}

build_docling() {
  docker build \
    -f docker/Dockerfile.docling-sidecar \
    --target docling-runtime \
    -t "$DOCLING_IMAGE" \
    --build-arg "DOCLING_BASE_IMAGE=$DOCLING_BASE_IMAGE" \
    .
}

# ── GPU base 镜像构建（Dockerfile.gpu，仅 HAS_GPU=true 时调用）──
build_mineru_gpu_base() {
  local fp
  fp="$(mineru_deps_fingerprint)"
  docker build \
    -f docker/Dockerfile.gpu \
    --target filex-mineru-base-gpu \
    -t "$MINERU_BASE_IMAGE" \
    --build-arg "PYTORCH_INDEX_URL=$MINERU_GPU_PYTORCH_INDEX_URL" \
    --label "filex.mineru.deps=$fp" \
    .
}

build_docling_gpu_base() {
  local fp
  fp="$(docling_deps_fingerprint)"
  docker build \
    -f docker/Dockerfile.gpu \
    --target filex-docling-base-gpu \
    -t "$DOCLING_BASE_IMAGE" \
    --label "filex.docling.deps=$fp" \
    .
}

ensure_mineru_base() {
  local fp stored
  fp="$(mineru_deps_fingerprint)"
  if [[ -n "$MINERU_DEPS_IMAGE" ]]; then
    echo "拉取 MinerU 稳定依赖基础镜像: $MINERU_DEPS_IMAGE" >&2
    docker pull "$MINERU_DEPS_IMAGE"
    MINERU_BASE_IMAGE="$MINERU_DEPS_IMAGE"
    return 0
  fi
  if docker image inspect "$MINERU_BASE_IMAGE" >/dev/null 2>&1; then
    stored="$(docker image inspect "$MINERU_BASE_IMAGE" --format '{{index .Config.Labels "filex.mineru.deps"}}' 2>/dev/null || true)"
    if [[ "$stored" == "$fp" ]]; then
      echo "复用 MinerU 基础镜像（依赖未变）: $MINERU_BASE_IMAGE"
      return 0
    fi
    echo "MinerU 依赖已变更，重建基础镜像 (旧=${stored:-none} 新=$fp)" >&2
  else
    echo "MinerU 基础镜像不存在，开始构建: $MINERU_BASE_IMAGE" >&2
  fi
  if $HAS_GPU; then
    build_mineru_gpu_base
  else
    build_mineru_base
  fi
}

ensure_mineru_runtime_image() {
  local fp stored
  ensure_mineru_base
  fp="$(mineru_runtime_fingerprint)"
  if docker image inspect "$MINERU_IMAGE" >/dev/null 2>&1; then
    stored="$(docker image inspect "$MINERU_IMAGE" --format '{{index .Config.Labels "filex.mineru.runtime"}}' 2>/dev/null || true)"
    if [[ "$stored" == "$fp" ]]; then
      echo "复用 MinerU 运行镜像（sidecar 代码未变）: $MINERU_IMAGE"
      return 0
    fi
    echo "MinerU 运行镜像已过期，重建 (旧=${stored:-none} 新=$fp)" >&2
  else
    echo "MinerU 运行镜像不存在，开始构建: $MINERU_IMAGE" >&2
  fi
  build_mineru
}

ensure_docling_base() {
  local fp stored
  fp="$(docling_deps_fingerprint)"
  if [[ -n "$DOCLING_DEPS_IMAGE" ]]; then
    echo "拉取 Docling 稳定依赖基础镜像: $DOCLING_DEPS_IMAGE" >&2
    docker pull "$DOCLING_DEPS_IMAGE"
    DOCLING_BASE_IMAGE="$DOCLING_DEPS_IMAGE"
    return 0
  fi
  if docker image inspect "$DOCLING_BASE_IMAGE" >/dev/null 2>&1; then
    stored="$(docker image inspect "$DOCLING_BASE_IMAGE" --format '{{index .Config.Labels "filex.docling.deps"}}' 2>/dev/null || true)"
    if [[ "$stored" == "$fp" ]]; then
      echo "复用 Docling 基础镜像（依赖未变）: $DOCLING_BASE_IMAGE"
      return 0
    fi
    echo "Docling 依赖已变更，重建基础镜像 (旧=${stored:-none} 新=$fp)" >&2
  else
    echo "Docling 基础镜像不存在，开始构建: $DOCLING_BASE_IMAGE" >&2
  fi
  if $HAS_GPU; then
    build_docling_gpu_base
  else
    build_docling_base
  fi
}

ensure_rerank_image() {
  if docker image inspect "$RERANK_IMAGE" >/dev/null 2>&1; then
    echo "复用 TEI rerank 镜像: $RERANK_IMAGE"
    return 0
  fi
  echo "拉取并标记 TEI rerank: $RERANK_SOURCE_IMAGE -> $RERANK_IMAGE" >&2
  docker pull "$RERANK_SOURCE_IMAGE"
  docker tag "$RERANK_SOURCE_IMAGE" "$RERANK_IMAGE"
}

ensure_image() {
  local image="$1"
  local builder="$2"
  if docker image inspect "$image" >/dev/null 2>&1; then
    echo "复用已存在基础镜像: $image"
  else
    "$builder"
  fi
}

build_targets() {
  local compose_targets=()
  local target
  for target in "$@"; do
    case "$target" in
      filex-os-base)
        build_os_base
        ;;
      app-base)
        build_os_base
        build_app_base
        ;;
      filex)
        ensure_app_base
        build_app
        ;;
      kb-extract-base)
        build_os_base
        build_extract_base
        ;;
      kb-extract)
        ensure_extract_base
        build_extract
        ;;
      filex-mineru-base)
        ensure_mineru_base
        ;;
      filex-mineru)
        ensure_mineru_base
        build_mineru
        ;;
      filex-docling-base)
        ensure_docling_base
        ;;
      filex-docling)
        ensure_docling_base
        build_docling
        ;;
      *)
        compose_targets+=("$target")
        ;;
    esac
  done
  if [[ "${#compose_targets[@]}" -gt 0 ]]; then
    compose build "${compose_targets[@]}"
  fi
}

build_app_and_extract() {
  ensure_app_base
  build_app
  ensure_extract_base
  build_extract
  ensure_mineru_base
  build_mineru
  ensure_docling_base
  build_docling
  ensure_rerank_image
}

needs_db_migration() {
  local arg
  for arg in "$@"; do
    case "$arg" in
      -*) ;;
      filex|kb-indexer|kb-post|kb-ragas-eval|kb-extract|gpu-scheduler) return 0 ;;
    esac
  done
  return 1
}

run_alembic_upgrade() {
  echo "部署前执行 db-migrate（避免 kb-indexer 先于 schema 升级启动）..." >&2
  compose run --rm db-migrate
}

compose_up() {
  local has_build_flag=0
  local arg
  # kb-rerank is an implicit dependency of app workers.  The Compose image name
  # is a local tag, so provision it before Compose falls back to a registry pull.
  ensure_rerank_image
  for arg in "$@"; do
    if [[ "$arg" == "--build" || "$arg" == "--no-build" ]]; then
      has_build_flag=1
      break
    fi
  done
  if needs_db_migration "$@"; then
    run_alembic_upgrade
  fi
  if [[ "$has_build_flag" -eq 1 ]]; then
    compose up "$@"
  else
    compose up --no-build "$@"
  fi
}

case "${1:-}" in
  build)
    require_build_version
    if [[ "$#" -eq 1 ]]; then
      echo "默认：build-app-and-up-workers (仅 filex / kb-indexer / kb-post / kb-ragas-eval；不重建 extract/mineru/docling)" >&2
      ensure_app_base
      build_app
      compose_up -d --force-recreate --no-build "${APP_WORKER_SERVICES[@]}"
      exit 0
    fi
    shift
    if [[ "${1:-}" == "all" ]]; then
      build_targets filex-os-base app-base filex kb-extract-base kb-extract filex-mineru-base filex-mineru filex-docling-base filex-docling postgres
      exit 0
    fi
    build_targets "$@"
    ;;
  build-app)
    require_build_version
    ensure_app_base
    build_app
    ;;
  build-app-and-extract)
    require_build_version
    build_app_and_extract
    ;;
  build-extract)
    require_build_version
    ensure_extract_base
    build_extract
    ;;
  build-mineru)
    ensure_mineru_base
    build_mineru
    ;;
  build-docling)
    ensure_docling_base
    build_docling
    ;;
  build-core)
    ensure_os_base
    ensure_app_base
    ensure_extract_base
    ensure_mineru_base
    ensure_docling_base
    ensure_rerank_image
    compose build postgres
    ;;
  up)
    shift
    compose_up "$@"
    ;;
  up-app-workers)
    shift
    compose_up -d --force-recreate --no-build "${APP_WORKER_SERVICES[@]}" "$@"
    ;;
  build-app-and-up-workers)
    require_build_version
    ensure_app_base
    build_app
    compose_up -d --force-recreate --no-build "${APP_WORKER_SERVICES[@]}"
    ;;
  build-app-and-up-extract-workers)
    require_build_version
    ensure_app_base
    build_app
    ensure_extract_base
    build_extract
    compose_up -d --force-recreate --no-build "${APP_WORKER_SERVICES[@]}" kb-extract
    ;;
  *)
    compose "$@"
    ;;
esac
