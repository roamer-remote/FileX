#!/bin/sh
# Start Ollama and ensure bge-m3:latest is present (069).
# 模型 blob 持久化在 /root/.ollama（compose volume）；已存在则跳过 pull，避免每次重启重下。
set -eu

PULL_MODEL="${OLLAMA_PULL_MODELS:-bge-m3:latest}"
FORCE_PULL="${OLLAMA_FORCE_PULL:-0}"
REQUIRE_GPU="${OLLAMA_REQUIRE_GPU:-0}"
GPU_WARM_MODEL="${OLLAMA_GPU_WARM_MODEL:-}"
GPU_START_RETRIES="${OLLAMA_GPU_START_RETRIES:-3}"

start_ollama() {
  # 容器内固定监听 0.0.0.0:11434；官方镜像无 curl，就绪探测用 ollama CLI。
  ollama serve &
  SERVE_PID=$!

  i=0
  while [ "$i" -lt 120 ]; do
    if ollama list >/dev/null 2>&1; then
      return 0
    fi
    i=$((i + 1))
    sleep 1
  done

  echo "ollama-entrypoint: Ollama did not become ready within 120s" >&2
  return 1
}

stop_ollama() {
  kill "$SERVE_PID" 2>/dev/null || true
  wait "$SERVE_PID" 2>/dev/null || true
}

cleanup() {
  stop_ollama
}
trap cleanup INT TERM

start_ollama || exit 1

ensure_model() {
  model=$(echo "$1" | tr -d ' ')
  [ -n "$model" ] || return 0
  if [ "$FORCE_PULL" != "1" ] && ollama show "$model" >/dev/null 2>&1; then
    echo "ollama-entrypoint: ${model} already present in volume, skip pull"
    return 0
  fi
  if [ "$FORCE_PULL" = "1" ]; then
    echo "ollama-entrypoint: OLLAMA_FORCE_PULL=1, pulling ${model}..."
  else
    echo "ollama-entrypoint: pulling ${model} (first run or incomplete)..."
  fi
  ollama pull "$model" || echo "ollama-entrypoint: pull ${model} failed (may retry on next start)" >&2
}

for model in $(echo "$PULL_MODEL" | tr ',' ' '); do
  ensure_model "$model"
done

require_gpu_runner() {
  [ "$REQUIRE_GPU" = "1" ] || return 0
  if [ -z "$GPU_WARM_MODEL" ]; then
    echo "ollama-entrypoint: OLLAMA_REQUIRE_GPU=1 requires OLLAMA_GPU_WARM_MODEL" >&2
    return 1
  fi

  ensure_model "$GPU_WARM_MODEL"
  attempt=1
  while [ "$attempt" -le "$GPU_START_RETRIES" ]; do
    # Loading the configured chat model makes Ollama report its actual runner.
    # GPU visibility alone is insufficient: a discovery timeout otherwise falls back to CPU.
    if ollama run "$GPU_WARM_MODEL" 'Reply with exactly: READY' >/dev/null 2>&1 && \
      ollama ps | awk -v model="$GPU_WARM_MODEL" '$1 == model && $0 ~ /GPU/ { found = 1 } END { exit !found }'; then
      echo "ollama-entrypoint: ${GPU_WARM_MODEL} is running on GPU"
      return 0
    fi

    if [ "$attempt" -eq "$GPU_START_RETRIES" ]; then
      echo "ollama-entrypoint: GPU validation failed after ${attempt} attempts; refusing CPU fallback" >&2
      return 1
    fi
    echo "ollama-entrypoint: GPU validation failed on attempt ${attempt}/${GPU_START_RETRIES}; restarting Ollama" >&2
    stop_ollama
    start_ollama || return 1
    attempt=$((attempt + 1))
  done
}

require_gpu_runner || exit 1

wait "$SERVE_PID"
