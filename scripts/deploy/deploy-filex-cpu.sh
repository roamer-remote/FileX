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

BUILD_VERSION_RE='^[0-9]{4}-[0-9]{2}-[0-9]{2}-[0-9]{2}-[0-9]{2}-[0-9]{2}-[0-9a-f]{7}$'
DATA_ROOT="${FILEX_DATA_ROOT:-/root/important/FileX/product}"
SECRETS_FILE="${FILEX_SECRETS_FILE:-/root/docker/important/FileX/secrets/filex.env}"
RERANK_SOURCE_IMAGE="${FILEX_RERANK_SOURCE_IMAGE:-ghcr.io/huggingface/text-embeddings-inference:cpu-1.9.3}"
RERANK_IMAGE="filex/tei-rerank:cpu-1.9.3"
FILEX_BASE_VERSION="${FILEX_BASE_VERSION:-py3.13}"
OS_BASE_IMAGE="filex/os-base:${FILEX_BASE_VERSION}"
APP_BASE_IMAGE="filex/app-base:${FILEX_BASE_VERSION}"
APP_IMAGE="filex/app:${FILEX_VERSION:-latest}"
PYTHON_313_IMAGE="${FILEX_PYTHON_313_IMAGE:-docker.m.daocloud.io/library/python:3.13-slim}"
NODE_20_IMAGE="${FILEX_NODE_20_IMAGE:-docker.m.daocloud.io/library/node:20-alpine}"
BUILD_HTTP_PROXY="${BUILD_HTTP_PROXY:-}"
HEALTH_ATTEMPTS="${FILEX_DEPLOY_HEALTH_ATTEMPTS:-60}"
HEALTH_INTERVAL="${FILEX_DEPLOY_HEALTH_INTERVAL:-2}"
FILEX_HEALTH_URL="${FILEX_HEALTH_URL:-http://127.0.0.1:8001/api/health}"

normalize_arch() {
  case "$(uname -m)" in
    x86_64|amd64) echo "amd64" ;;
    aarch64|arm64) echo "arm64" ;;
    *) echo "unsupported" ;;
  esac
}

require_build_version() {
  if [[ -z "${FILEX_APP_BUILD_VERSION:-}" ]]; then
    local build_date build_sha
    build_date="$(TZ=Asia/Shanghai date +%Y-%m-%d-%H-%M-%S)"
    build_sha="$(git rev-parse --short=7 HEAD)"
    export FILEX_APP_BUILD_VERSION="${build_date}-${build_sha}"
    echo "FILEX_APP_BUILD_VERSION=${FILEX_APP_BUILD_VERSION}" >&2
    return 0
  fi
  if [[ ! "$FILEX_APP_BUILD_VERSION" =~ $BUILD_VERSION_RE ]]; then
    echo "ERROR: FILEX_APP_BUILD_VERSION invalid: $FILEX_APP_BUILD_VERSION" >&2
    exit 1
  fi
}

ARCH="$(normalize_arch)"
if [[ "$ARCH" == "unsupported" ]]; then
  echo "unsupported architecture: $(uname -m)" >&2
  exit 12
fi
if ! command -v docker >/dev/null 2>&1 || ! docker compose version >/dev/null 2>&1; then
  echo "Docker prerequisite missing" >&2
  exit 13
fi
if [[ ! -f "$SECRETS_FILE" ]]; then
  echo "missing secrets file: $SECRETS_FILE" >&2
  exit 31
fi
export FILEX_DATA_ROOT="$DATA_ROOT"
export FILEX_SECRETS_FILE="$SECRETS_FILE"

if $CHECK_ONLY; then
  echo "check_only=true ARCH=$ARCH" >&2
  exit 0
fi

require_build_version

mkdir -p \
  "$DATA_ROOT/uploads" \
  "$DATA_ROOT/logs" \
  "$DATA_ROOT/redis/data" \
  "$DATA_ROOT/mineru/models" \
  "$DATA_ROOT/mineru/cache" \
  "$DATA_ROOT/docling/models" \
  "$DATA_ROOT/docling/cache" \
  "$DATA_ROOT/ollama" \
  "$DATA_ROOT/rerank_data/model" \
  "$DATA_ROOT/postgres/data"

COMPOSE_FILES=(-f docker/docker-compose.yml -f docker/docker-compose.prod.yml -f docker/docker-compose.pdf-inspector.yml)
if [[ "$ARCH" == "arm64" ]]; then
  if [[ "$(docker run --rm --platform linux/amd64 docker.m.daocloud.io/library/alpine:3.20 uname -m)" != *"x86_64"* ]]; then
    echo "ARM host cannot run linux/amd64 containers. Run: docker run --privileged --rm tonistiigi/binfmt --install amd64 && sudo systemctl restart docker" >&2
    exit 20
  fi
  docker pull --platform linux/amd64 "$RERANK_SOURCE_IMAGE"
  docker tag "$RERANK_SOURCE_IMAGE" "$RERANK_IMAGE"
  if [[ "$(docker image inspect "$RERANK_IMAGE" --format '{{.Architecture}}/{{.Os}}')" != "amd64/linux" ]]; then
    echo "kb-rerank linux/amd64 image unavailable" >&2
    exit 20
  fi
  COMPOSE_FILES+=(-f docker/docker-compose.arm64.yml)
fi

compose() {
  docker compose "${COMPOSE_FILES[@]}" "$@"
}

wait_service_healthy() {
  local service="$1"
  local status attempt
  for attempt in $(seq 1 "$HEALTH_ATTEMPTS"); do
    status="$(compose ps "$service" 2>/dev/null || true)"
    if [[ "$status" == *"healthy"* || "$status" == *"running"* || "$status" == *"Up"* ]]; then
      return 0
    fi
    sleep "$HEALTH_INTERVAL"
  done
  echo "service unhealthy: $service" >&2
  exit 40
}

wait_filex_http() {
  local attempt
  for attempt in $(seq 1 "$HEALTH_ATTEMPTS"); do
    if curl -fsS "$FILEX_HEALTH_URL" >/dev/null 2>&1; then
      return 0
    fi
    sleep "$HEALTH_INTERVAL"
  done
  echo "filex HTTP health unavailable: $FILEX_HEALTH_URL" >&2
  exit 41
}

docker build \
  -f docker/Dockerfile.base \
  --target filex-os-base \
  -t "$OS_BASE_IMAGE" \
  --build-arg "PYTHON_IMAGE=$PYTHON_313_IMAGE" \
  .

docker build \
  -f docker/Dockerfile.base \
  --target filex-app-base \
  -t "$APP_BASE_IMAGE" \
  --build-arg "FILEX_OS_BASE_IMAGE=$OS_BASE_IMAGE" \
  .

docker build \
  -f docker/Dockerfile \
  --add-host host.docker.internal:host-gateway \
  -t "$APP_IMAGE" \
  --build-arg "APP_BASE_IMAGE=$APP_BASE_IMAGE" \
  --build-arg "NODE_IMAGE=$NODE_20_IMAGE" \
  --build-arg "PYTHON_IMAGE=$PYTHON_313_IMAGE" \
  --build-arg "BUILD_HTTP_PROXY=$BUILD_HTTP_PROXY" \
  --build-arg "VITE_APP_BUILD_VERSION=$FILEX_APP_BUILD_VERSION" \
  .

compose build kb-extract filex-mineru filex-docling
compose up -d --no-build postgres rabbitmq redis filex-ollama kb-rerank
for service in postgres rabbitmq redis filex-ollama kb-rerank; do
  wait_service_healthy "$service"
done
compose run --rm --no-deps db-migrate
compose up -d --no-build filex kb-indexer kb-post kb-ragas-eval kb-extract filex-mineru filex-docling
for service in filex kb-indexer kb-post kb-ragas-eval kb-extract filex-mineru filex-docling; do
  wait_service_healthy "$service"
done
wait_filex_http

if [[ "$ARCH" == "arm64" ]]; then
  rerank_status="$(compose ps kb-rerank 2>/dev/null || true)"
  if [[ "$rerank_status" != *"running"* && "$rerank_status" != *"healthy"* ]]; then
    echo "kb-rerank linux/amd64 emulation unavailable or unhealthy" >&2
    exit 21
  fi
fi
