#!/usr/bin/env bash
# 预下载 BAAI/bge-reranker-base 到 kb-rerank 本地模型目录（容器内 /data/model，TEI 离线加载）。
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/../.." && pwd)"
COMPOSE_PROJECT="${COMPOSE_PROJECT:-filex}"
COMPOSE_FILE="${COMPOSE_FILE:-$ROOT/docker/docker-compose.yml}"
HF_ENDPOINT="${HF_ENDPOINT:-https://hf-mirror.com}"
MODEL_ID="${KB_RERANK_MODEL_ID:-BAAI/bge-reranker-base}"
PYTHON_IMAGE="${PYTHON_IMAGE:-docker.m.daocloud.io/library/python:3.13-slim}"
# 生产 docker-compose.yml：rerank_data 挂载为 /data，模型在 /data/model
DATA_DIR="${KB_RERANK_DATA_DIR:-/root/important/FileBox/product/rerank_data}"
MODEL_DIR="${KB_RERANK_MODEL_DIR:-$DATA_DIR/model}"

mkdir -p "$MODEL_DIR"

echo "Prefetch $MODEL_ID -> $MODEL_DIR via $HF_ENDPOINT"

PROXY_ENV=()
if [[ -n "${HTTP_PROXY:-}" ]]; then PROXY_ENV+=(-e "HTTP_PROXY=$HTTP_PROXY"); fi
if [[ -n "${HTTPS_PROXY:-}" ]]; then PROXY_ENV+=(-e "HTTPS_PROXY=$HTTPS_PROXY"); fi

docker run --rm \
  -v "${MODEL_DIR}:/data/model" \
  -e HF_ENDPOINT="$HF_ENDPOINT" \
  -e HF_HUB_ENDPOINT="$HF_ENDPOINT" \
  -e HTTP_PROXY= \
  -e HTTPS_PROXY= \
  -e http_proxy= \
  -e https_proxy= \
  "${PROXY_ENV[@]}" \
  "$PYTHON_IMAGE" \
  bash -c "pip install -q huggingface_hub -i https://pypi.tuna.tsinghua.edu.cn/simple && hf download '$MODEL_ID' --local-dir /data/model"

echo "Done. Verify 1_Pooling exists:"
echo "  ls '$MODEL_DIR/1_Pooling'"
echo "Restart kb-rerank:"
echo "  docker compose -p $COMPOSE_PROJECT -f $COMPOSE_FILE up -d --force-recreate kb-rerank"
