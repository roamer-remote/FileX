#!/usr/bin/env bash
# ============================================================
# deploy-filex-amd64-nvidia.sh
# FileX 全流程部署脚本（amd64 + NVIDIA GPU）
#
# 完全独立于 bamboo-compose.sh——不走 --gpu 参数，
# 直接构建 GPU base 镜像 + 使用 docker compose 叠加 GPU overlay。
#
# 适用：吴杭彬的 NVIDIA GPU 生产服务器
#
# 支持 Bamboo CI/CD 或终端直接执行；正式执行前仍会校验 Docker、GPU、密钥和健康状态。
# 人工预检：
#   chmod +x scripts/deploy/deploy-filex-amd64-nvidia.sh
#   ./scripts/deploy/deploy-filex-amd64-nvidia.sh --check
# ============================================================
set -euo pipefail

# ── 配置（可通过环境变量覆盖） ──────────────────────────────────

REPO_DIR="${FILEX_REPO_DIR:-/root/important/FileX/product}"
DATA_ROOT="${FILEX_DATA_ROOT:-/root/important/FileX/product}"
BRANCH="${FILEX_BRANCH:-master}"
FILEX_VERSION="${FILEX_VERSION:-latest}"
FILEX_BASE_VERSION="${FILEX_BASE_VERSION:-py3.13}"
CURRENT_CHECKOUT=false
if [[ "${FILEX_DEPLOY_CURRENT_CHECKOUT:-0}" == "1" ]]; then
  CURRENT_CHECKOUT=true
fi
CHECK_ONLY=false
for arg in "$@"; do
  case "$arg" in
    --current-checkout) CURRENT_CHECKOUT=true ;;
    --check|--dry-run) CHECK_ONLY=true ;;
    *) echo "不支持的参数: $arg" >&2; exit 2 ;;
  esac
done
BUILD_VERSION_RE='^[0-9]{4}-[0-9]{2}-[0-9]{2}-[0-9]{2}-[0-9]{2}-[0-9]{2}-[0-9a-f]{7}$'

DEPENDENCY_IMAGES_FILE="$(cd "$(dirname "$0")/../.." && pwd)/docker/dependency-images.env"
if [[ ! -f "$DEPENDENCY_IMAGES_FILE" ]]; then
  echo "缺少仓库内 GPU 依赖镜像配置: $DEPENDENCY_IMAGES_FILE" >&2
  exit 1
fi
# shellcheck disable=SC1090
source "$DEPENDENCY_IMAGES_FILE"
: "${FILEX_DOCLING_DEPS_IMAGE:?配置文件未设置 FILEX_DOCLING_DEPS_IMAGE}"

# 镜像标签
OS_CPU_TAG="filex/os-base:${FILEX_BASE_VERSION}"
OS_GPU_TAG="filex/os-base:${FILEX_BASE_VERSION}-gpu"
APP_BASE_TAG="filex/app-base:${FILEX_BASE_VERSION}"
APP_TAG="filex/app:${FILEX_VERSION}"
EXTRACT_BASE_TAG="filex/kb-extract-base:${FILEX_BASE_VERSION}"
EXTRACT_TAG="filex/kb-extract:${FILEX_VERSION}"
MINERU_GPU_TAG="filex/mineru-base:${FILEX_BASE_VERSION}-gpu"
MINERU_RUNTIME_TAG="filex-filex-mineru:${FILEX_VERSION}"
DOCLING_GPU_TAG="filex/docling-base:${FILEX_BASE_VERSION}-gpu"
DOCLING_RUNTIME_TAG="filex-filex-docling:${FILEX_VERSION}"
PY_313="docker.m.daocloud.io/library/python:3.13-slim"
NODE_20="docker.m.daocloud.io/library/node:20-alpine"
MINERU_GPU_PYTORCH_INDEX_URL="${MINERU_GPU_PYTORCH_INDEX_URL:-${PYTORCH_INDEX_URL:-https://download.pytorch.org/whl/cu118}}"
MINERU_DEPS_IMAGE="${FILEX_MINERU_DEPS_IMAGE:-}"
if [[ -n "$MINERU_DEPS_IMAGE" ]]; then
  MINERU_GPU_TAG="$MINERU_DEPS_IMAGE"
fi
DOCLING_DEPS_IMAGE="$FILEX_DOCLING_DEPS_IMAGE"
export FILEX_DOCLING_DEPS_IMAGE="$DOCLING_DEPS_IMAGE"
DOCLING_GPU_TAG="$DOCLING_DEPS_IMAGE"

# 颜色
RED='\033[0;31m'; GREEN='\033[0;32m'; YELLOW='\033[1;33m'; CYAN='\033[0;36m'; NC='\033[0m'
log()  { echo -e "${CYAN}[$(date +%H:%M:%S)]${NC} $*"; }
ok()   { echo -e "${GREEN}[OK]${NC} $*"; }
warn() { echo -e "${YELLOW}[WARN]${NC} $*" >&2; }
die()  { echo -e "${RED}[ERR]${NC} $*" >&2; exit 1; }

# ── 1. 环境校验 ────────────────────────────────────────────────

log "=============================================="
log " FileX GPU 部署（amd64 + NVIDIA）"
log "=============================================="
log ""
log "=== Step 1/7: 环境校验 ==="

command -v git    >/dev/null 2>&1 || die "git 未安装"
command -v docker >/dev/null 2>&1 || die "docker 未安装"
docker compose version >/dev/null 2>&1 || die "docker compose 不可用（需要 Docker 20.10+）"

if ! nvidia-smi >/dev/null 2>&1; then
  die "nvidia-smi 不可用，请先安装 NVIDIA 驱动"
fi
ok "NVIDIA 驱动正常"

if ! docker run --rm --gpus all nvidia/cuda:12.6-runtime-ubuntu22.04 nvidia-smi >/dev/null 2>&1; then
  die "nvidia-container-toolkit 未安装或未生效。请执行:
    sudo apt-get install -y nvidia-container-toolkit
    sudo systemctl restart docker
    docker run --rm --gpus all nvidia/cuda:12.6-runtime-ubuntu22.04 nvidia-smi"
fi
ok "nvidia-container-toolkit 正常"

if $CHECK_ONLY; then
  ok "check_only=true"
  exit 0
fi

# ── 2. 拉取代码 ────────────────────────────────────────────────

log ""
log "=== Step 2/7: 拉取代码 ==="

if $CURRENT_CHECKOUT; then
  ROOT="$(git rev-parse --show-toplevel)"
  REPO_DIR="$ROOT"
  DATA_ROOT="${FILEX_DATA_ROOT:-$ROOT}"
  cd "$ROOT"
  ok "使用当前 checkout: $ROOT @ $(git rev-parse --short=7 HEAD)"
elif [[ -d "$REPO_DIR/.git" ]]; then
  log "仓库已存在，更新: $REPO_DIR"
  cd "$REPO_DIR"
  git fetch origin
  git checkout "$BRANCH"
  git reset --hard "origin/$BRANCH"
  ok "代码已更新到 $BRANCH @ $(git rev-parse --short HEAD)"
else
  echo "production checkout not found: $REPO_DIR" >&2
  exit 32
fi

ROOT="$REPO_DIR"
cd "$ROOT"

if [[ -z "${FILEX_APP_BUILD_VERSION:-}" ]]; then
  export FILEX_APP_BUILD_VERSION="$(TZ=Asia/Shanghai date +%Y-%m-%d-%H-%M-%S)-$(git rev-parse --short=7 HEAD)"
  log "FILEX_APP_BUILD_VERSION=$FILEX_APP_BUILD_VERSION"
elif [[ ! "$FILEX_APP_BUILD_VERSION" =~ $BUILD_VERSION_RE ]]; then
  die "FILEX_APP_BUILD_VERSION 格式非法: $FILEX_APP_BUILD_VERSION"
else
  log "FILEX_APP_BUILD_VERSION=$FILEX_APP_BUILD_VERSION"
fi

# ── 3. 目录与密钥 ──────────────────────────────────────────────

log ""
log "=== Step 3/7: 目录与密钥 ==="

mkdir -p "$DATA_ROOT/uploads" \
         "$DATA_ROOT/logs" \
         "$DATA_ROOT/redis/data" \
         "$DATA_ROOT/mineru/models" \
         "$DATA_ROOT/mineru/cache" \
         "$DATA_ROOT/docling/models" \
         "$DATA_ROOT/docling/cache" \
         "$DATA_ROOT/ollama" \
         "$DATA_ROOT/rerank_data/model" \
         "$DATA_ROOT/postgres/data"
ok "数据目录已就绪"

SECRETS_FILE="${FILEX_SECRETS_FILE:-$DATA_ROOT/secrets/filex.env}"
if [[ ! -f "$SECRETS_FILE" ]]; then
  mkdir -p "$(dirname "$SECRETS_FILE")"
  if [[ -n "${FILEX_LICENSE_HMAC_SECRET:-}" ]]; then
    cat > "$SECRETS_FILE" <<EOF
FILEX_LICENSE_HMAC_SECRET=$FILEX_LICENSE_HMAC_SECRET
FILEX_ASSET_SIGNING_SECRET=${FILEX_ASSET_SIGNING_SECRET:-$FILEX_LICENSE_HMAC_SECRET}
EOF
  elif [[ ! -t 0 ]]; then
    die "FILEX_LICENSE_HMAC_SECRET 未设置，非交互环境无法创建密钥文件"
  else
    warn "FILEX_LICENSE_HMAC_SECRET 未设置"
    read -rsp "请输入 FILEX_LICENSE_HMAC_SECRET: " HMAC_SECRET
    echo
    cat > "$SECRETS_FILE" <<EOF
FILEX_LICENSE_HMAC_SECRET=$HMAC_SECRET
FILEX_ASSET_SIGNING_SECRET=${FILEX_ASSET_SIGNING_SECRET:-$HMAC_SECRET}
EOF
  fi
  chmod 600 "$SECRETS_FILE"
  ok "密钥文件已创建: $SECRETS_FILE"
else
  ok "密钥文件已存在: $SECRETS_FILE"
fi
export FILEX_SECRETS_FILE="$SECRETS_FILE"

# ── helper: compose 命令（固定叠加顺序）────────────────────────

compose() {
  docker compose \
    -f docker/docker-compose.yml \
    -f docker/docker-compose.prod.yml \
    -f docker/docker-compose.pdf-inspector.yml \
    -f docker/docker-compose.gpu.yml \
    "$@"
}

# ── helper: 按指纹决定是否重建镜像 ──────────────────────────────

rebuild_if_changed() {
  local tag="$1" fingerprint="$2" build_cmd="$3"
  if docker image inspect "$tag" >/dev/null 2>&1; then
    local stored
    stored=$(docker image inspect "$tag" --format '{{index .Config.Labels "filex.fingerprint"}}' 2>/dev/null || true)
    if [[ "$stored" == "$fingerprint" ]]; then
      log "复用镜像: ${tag}（依赖未变）"
      return 0
    fi
    log "重建镜像: ${tag}（依赖已变更）"
  else
    log "构建镜像: ${tag}（不存在）"
  fi
  eval "$build_cmd"
}

# ── 4. 构建镜像 ────────────────────────────────────────────────

log ""
log "=== Step 4/7: 构建 Docker 镜像 ==="

# ── 4a. GPU base 镜像（Dockerfile.gpu）──

gpu_deps_fp()     { sha256sum docker/Dockerfile.gpu | awk '{print $1}'; }
mineru_gpu_fp()   { { sha256sum docker/Dockerfile.gpu docker/mineru-sidecar/requirements.common.txt docker/mineru-sidecar/requirements.gpu.txt docker/mineru-sidecar/sitecustomize.py; printf '%s\n' "$MINERU_GPU_PYTORCH_INDEX_URL"; } | sha256sum | awk '{print $1}'; }
mineru_base_identity_fp() { { printf 'ref=%s\n' "$MINERU_GPU_TAG"; if [[ -n "$MINERU_DEPS_IMAGE" ]]; then docker image inspect "$MINERU_DEPS_IMAGE" --format '{{.Id}}' 2>/dev/null || true; fi; } | sha256sum | awk '{print $1}'; }
docling_gpu_fp()  {
  {
    sed -n '/^FROM ${CUDA_BASE_IMAGE} AS filex-os-base-gpu/,/^FROM filex-os-base-gpu AS filex-mineru-base-gpu/p' docker/Dockerfile.gpu
    sed -n '/^FROM filex-os-base-gpu AS filex-docling-base-gpu/,$p' docker/Dockerfile.gpu
    sha256sum docker/docling-sidecar/requirements.txt
  } | sha256sum | awk '{print $1}'
}
docling_base_identity_fp() { { printf 'ref=%s\n' "$DOCLING_GPU_TAG"; if [[ -n "$DOCLING_DEPS_IMAGE" ]]; then docker image inspect "$DOCLING_DEPS_IMAGE" --format '{{.Id}}' 2>/dev/null || true; fi; } | sha256sum | awk '{print $1}'; }

rebuild_if_changed "$OS_GPU_TAG" "$(gpu_deps_fp)" '
  docker build -f docker/Dockerfile.gpu --target filex-os-base-gpu \
    -t "$OS_GPU_TAG" --label "filex.fingerprint=$(gpu_deps_fp)" "$ROOT"
'

if [[ -n "$MINERU_DEPS_IMAGE" ]]; then
  log "拉取 MinerU 稳定依赖基础镜像: $MINERU_GPU_TAG"
  docker pull "$MINERU_GPU_TAG"
else
  rebuild_if_changed "$MINERU_GPU_TAG" "$(mineru_gpu_fp)" '
    docker build -f docker/Dockerfile.gpu --target filex-mineru-base-gpu \
      -t "$MINERU_GPU_TAG" \
      --build-arg "PYTORCH_INDEX_URL=$MINERU_GPU_PYTORCH_INDEX_URL" \
      --label "filex.fingerprint=$(mineru_gpu_fp)" "$ROOT"
  '
fi

if [[ -n "$DOCLING_DEPS_IMAGE" ]]; then
  log "拉取 Docling 稳定依赖基础镜像: $DOCLING_GPU_TAG"
  docker pull "$DOCLING_GPU_TAG"
else
  rebuild_if_changed "$DOCLING_GPU_TAG" "$(docling_gpu_fp)" '
    docker build -f docker/Dockerfile.gpu --target filex-docling-base-gpu \
      -t "$DOCLING_GPU_TAG" --label "filex.fingerprint=$(docling_gpu_fp)" "$ROOT"
  '
fi

ok "GPU base 镜像就绪"

# ── 4b. CPU base 镜像（非 GPU 服务仍需 CPU 镜像）──

os_cpu_fp()     { sed -n '1,32p' docker/Dockerfile.base | sha256sum | awk '{print $1}'; }
app_base_fp()   { { os_cpu_fp; sha256sum backend/requirements.txt; } | sha256sum | awk '{print $1}'; }

rebuild_if_changed "$OS_CPU_TAG" "$(os_cpu_fp)" '
  docker build -f docker/Dockerfile.base --target filex-os-base \
    -t "$OS_CPU_TAG" --build-arg "PYTHON_IMAGE=$PY_313" \
    --label "filex.fingerprint=$(os_cpu_fp)" "$ROOT"
'

rebuild_if_changed "$APP_BASE_TAG" "$(app_base_fp)" '
  docker build -f docker/Dockerfile.base --target filex-app-base \
    -t "$APP_BASE_TAG" \
    --build-arg "FILEX_OS_BASE_IMAGE=$OS_CPU_TAG" \
    --label "filex.fingerprint=$(app_base_fp)" "$ROOT"
'

extract_fp() {
  { os_cpu_fp; sha256sum backend/requirements.txt backend/requirements-extract.txt;
    sed -n "/AS filex-extract-base/,/pip install/p" docker/Dockerfile.base | sha256sum; } | sha256sum | awk '{print $1}'
}
rebuild_if_changed "$EXTRACT_BASE_TAG" "$(extract_fp)" '
  docker build -f docker/Dockerfile.base --target filex-extract-base \
    -t "$EXTRACT_BASE_TAG" \
    --build-arg "FILEX_OS_BASE_IMAGE=$OS_CPU_TAG" \
    --label "filex.fingerprint=$(extract_fp)" "$ROOT"
'

ok "CPU base 镜像就绪"

# ── 4c. 业务运行时镜像 ──

app_fp()   { { app_base_fp; git rev-parse HEAD; } | sha256sum | awk '{print $1}'; }
extract_runtime_fp() { { extract_fp; git rev-parse HEAD; } | sha256sum | awk '{print $1}'; }
mineru_runtime_fp()  { { mineru_gpu_fp; mineru_base_identity_fp; sha256sum docker/mineru-sidecar/requirements.mineru.txt; git rev-parse HEAD; } | sha256sum | awk '{print $1}'; }
docling_runtime_fp() { { docling_gpu_fp; docling_base_identity_fp; git rev-parse HEAD; } | sha256sum | awk '{print $1}'; }

rebuild_if_changed "$APP_TAG" "$(app_fp)" '
  docker build -f docker/Dockerfile -t "$APP_TAG" \
    --build-arg "APP_BASE_IMAGE=$APP_BASE_TAG" \
    --build-arg "NODE_IMAGE=$NODE_20" \
    --build-arg "VITE_APP_BUILD_VERSION=${FILEX_APP_BUILD_VERSION}" \
    --label "filex.fingerprint=$(app_fp)" "$ROOT"
'

rebuild_if_changed "$EXTRACT_TAG" "$(extract_runtime_fp)" '
  docker build -f docker/Dockerfile.extract -t "$EXTRACT_TAG" \
    --build-arg "EXTRACT_BASE_IMAGE=$EXTRACT_BASE_TAG" \
    --label "filex.fingerprint=$(extract_runtime_fp)" "$ROOT"
'

rebuild_if_changed "$MINERU_RUNTIME_TAG" "$(mineru_runtime_fp)" '
  docker build -f docker/Dockerfile.mineru-sidecar --target mineru-runtime \
    -t "$MINERU_RUNTIME_TAG" \
    --build-arg "MINERU_BASE_IMAGE=$MINERU_GPU_TAG" \
    --label "filex.fingerprint=$(mineru_runtime_fp)" "$ROOT"
'

rebuild_if_changed "$DOCLING_RUNTIME_TAG" "$(docling_runtime_fp)" '
  docker build -f docker/Dockerfile.docling-sidecar --target docling-runtime \
    -t "$DOCLING_RUNTIME_TAG" \
    --build-arg "DOCLING_BASE_IMAGE=$DOCLING_GPU_TAG" \
    --label "filex.fingerprint=$(docling_runtime_fp)" "$ROOT"
'

ok "业务镜像就绪"

verify_mineru_gpu_runtime() {
  log "验证 MinerU CUDA 运行时..."
  if ! docker run --rm --gpus all --entrypoint python3 "$MINERU_RUNTIME_TAG" -c '
import torch
from mineru.cli.main import app

assert torch.cuda.is_available(), "CUDA is unavailable"
assert torch.cuda.device_count() > 0, "no CUDA devices are visible"
print(f"MinerU CUDA ready: {torch.cuda.get_device_name(0)}")
'; then
    die "MinerU GPU 镜像未通过 CUDA 运行时校验；不会启动或替换 filex-mineru"
  fi
}

verify_mineru_gpu_runtime

# ── 5. 数据库迁移 ──────────────────────────────────────────────

log ""
log "=== Step 5/7: 数据库迁移 ==="

log "启动基础服务（postgres / rabbitmq / redis）..."
compose up -d --no-build postgres rabbitmq redis

log "等待 postgres healthy..."
for i in $(seq 1 60); do
  if compose ps --format json 2>/dev/null | python3 -c "
import sys, json
for line in sys.stdin:
    try:
        s = json.loads(line.strip())
        if s.get('Service') == 'postgres' and s.get('Health') == 'healthy':
            print('ok')
            break
    except: pass
" 2>/dev/null | grep -q ok; then
    ok "postgres healthy"
    break
  fi
  sleep 2
done

log "执行数据库迁移..."
compose run --rm --no-deps db-migrate
ok "数据库迁移完成"

# ── 6. 启动全栈 ────────────────────────────────────────────────

log ""
log "=== Step 6/7: 启动全栈服务 ==="

# 预拉取外部镜像
log "拉取 Ollama / TEI GPU 镜像..."
docker pull docker.m.daocloud.io/ollama/ollama:latest 2>/dev/null || docker pull ollama/ollama:latest 2>/dev/null || warn "Ollama 拉取失败，启动时重试"
docker pull ghcr.io/huggingface/text-embeddings-inference:1.9.3 2>/dev/null || warn "TEI GPU 拉取失败（可能需要代理）"

log "启动 FileX 全栈（GPU 加速）..."
compose up -d --no-build \
  filex-ollama \
  kb-rerank \
  filex \
  kb-indexer \
  kb-post \
  kb-ragas-eval \
  kb-extract \
  gpu-scheduler \
  filex-mineru \
  filex-docling

ok "全栈服务已启动"

# ── 7. 健康检查 ────────────────────────────────────────────────

log ""
log "=== Step 7/7: 健康检查 ==="

check_health() {
  local svc="$1" max_wait="${2:-600}"
  local waited=0 interval=10
  while [[ $waited -lt $max_wait ]]; do
    local status
    status=$(compose ps --format json 2>/dev/null | python3 -c "
import sys, json
for line in sys.stdin:
    try:
        s = json.loads(line.strip())
        if s.get('Service') == '$svc':
            print(s.get('Health', 'unknown'))
            break
    except: pass
" 2>/dev/null || echo "unknown")
    case "$status" in
      healthy) ok "$svc healthy (${waited}s)"; return 0 ;;
      starting|"") sleep "$interval"; waited=$((waited + interval)) ;;
      *) warn "$svc: $status (${waited}s)"; sleep "$interval"; waited=$((waited + interval)) ;;
    esac
  done
  warn "$svc 未在 ${max_wait}s 内 healthy"
  return 1
}

check_health postgres 120
check_health rabbitmq 60
check_health redis 60
check_health filex-ollama 300
check_health filex-mineru 720 || warn "MinerU 模型可能在下载中，稍后检查: docker logs filex-mineru"
check_health filex-docling 720 || warn "Docling 模型可能在下载中，稍后检查: docker logs filex-docling"
check_health filex 120
check_health kb-indexer 300
check_health kb-post 300
check_health kb-ragas-eval 120
check_health kb-extract 120
check_health gpu-scheduler 300

# ── GPU 验证 ────────────────────────────────────────────────────

log ""
log "--- GPU 验证 ---"

if docker exec filex-ollama nvidia-smi --query-gpu=name,memory.total --format=csv,noheader 2>/dev/null; then
  ok "Ollama GPU 可见"
else
  warn "Ollama 未检测到 nvidia-smi（embedding 仍可工作，检查容器日志）"
fi

if docker exec filex-mineru python3 -c "
import torch
ok = torch.cuda.is_available()
name = torch.cuda.get_device_name(0) if ok else 'N/A'
print(f'CUDA: {ok}, Device: {name}')
" 2>/dev/null; then
  ok "MinerU CUDA 可用"
else
  warn "MinerU CUDA 检测失败: docker logs filex-mineru"
fi

if docker exec filex-docling python3 -c "
import torch
ok = torch.cuda.is_available()
name = torch.cuda.get_device_name(0) if ok else 'N/A'
print(f'CUDA: {ok}, Device: {name}')
" 2>/dev/null; then
  ok "Docling CUDA 可用"
else
  warn "Docling CUDA 检测失败: docker logs filex-docling"
fi

# ── 汇总 ────────────────────────────────────────────────────────

echo ""
echo "=============================================="
echo -e "  ${GREEN}FileX 部署完成（amd64 + NVIDIA GPU）${NC}"
echo "=============================================="
echo ""
compose ps --format "table {{.Name}}\t{{.Status}}\t{{.Health}}" 2>/dev/null || \
  docker compose -f docker/docker-compose.yml -f docker/docker-compose.prod.yml -f docker/docker-compose.pdf-inspector.yml -f docker/docker-compose.gpu.yml ps
echo ""
echo "常用命令:"
echo "  查看日志:  cd $REPO_DIR && docker compose -f docker/docker-compose.yml -f docker/docker-compose.prod.yml -f docker/docker-compose.pdf-inspector.yml -f docker/docker-compose.gpu.yml logs -f filex"
echo "  重启服务:  cd $REPO_DIR && docker compose -f docker/docker-compose.yml -f docker/docker-compose.prod.yml -f docker/docker-compose.pdf-inspector.yml -f docker/docker-compose.gpu.yml restart filex"
echo "  GPU 状态:  docker exec filex-mineru python3 -c 'import torch; print(torch.cuda.get_device_name(0))'"
echo ""
echo "后续更新:"
echo "  cd $REPO_DIR && git pull origin $BRANCH"
echo "  ./scripts/deploy/deploy-filex-amd64-nvidia.sh"
echo ""
