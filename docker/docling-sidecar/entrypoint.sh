#!/bin/sh
set -eu

MODELS_DIR="${DOCLING_MODELS_DIR:-/models}"
CACHE_DIR="${DOCLING_CACHE_DIR:-/cache}"
ARTIFACTS_DIR="${DOCLING_ARTIFACTS_PATH:-${MODELS_DIR}/artifacts}"
DOCLING_EXPECTED_VERSION="${DOCLING_EXPECTED_VERSION:-2.117.0}"
MODEL_BUNDLE_ID="${DOCLING_MODEL_BUNDLE_ID:-docling-${DOCLING_EXPECTED_VERSION}-standard-default}"
MODEL_MANIFEST="${ARTIFACTS_DIR}/.filex-model-manifest"

_models_ready() {
  [ -f "$MODEL_MANIFEST" ] && \
  grep -Fxq "${MODEL_BUNDLE_ID}" "$MODEL_MANIFEST" && \
  find "$ARTIFACTS_DIR" -type f ! -name "$(basename "$MODEL_MANIFEST")" -print -quit | grep -q .
}

_download_models() {
  export HF_ENDPOINT="${HF_ENDPOINT:-https://hf-mirror.com}"
  export HF_HUB_ENDPOINT="${HF_HUB_ENDPOINT:-$HF_ENDPOINT}"
  export HF_HUB_DISABLE_XET="${HF_HUB_DISABLE_XET:-1}"
  if [ -n "${DOCLING_HTTP_PROXY:-}" ]; then
    export HTTP_PROXY="$DOCLING_HTTP_PROXY"
    export HTTPS_PROXY="${DOCLING_HTTPS_PROXY:-$DOCLING_HTTP_PROXY}"
    export http_proxy="$HTTP_PROXY"
    export https_proxy="$HTTPS_PROXY"
  fi
  max_attempts="${DOCLING_MODEL_DOWNLOAD_RETRIES:-3}"
  attempt=1
  staging_dir="${ARTIFACTS_DIR}.staging.$$"
  previous_dir="${ARTIFACTS_DIR}.previous.$$"
  rm -rf "$staging_dir" "$previous_dir"
  mkdir -p "$staging_dir"
  while [ "$attempt" -le "$max_attempts" ]; do
    echo "[entrypoint] docling models download attempt ${attempt}/${max_attempts} -> ${staging_dir} bundle=${MODEL_BUNDLE_ID} proxy=${HTTP_PROXY:-none}"
    if docling-tools models download -o "$staging_dir"; then
      printf '%s\n' "$MODEL_BUNDLE_ID" > "$staging_dir/$(basename "$MODEL_MANIFEST")"
      if [ -e "$ARTIFACTS_DIR" ]; then
        mv "$ARTIFACTS_DIR" "$previous_dir"
      fi
      mv "$staging_dir" "$ARTIFACTS_DIR"
      rm -rf "$previous_dir"
      return 0
    fi
    echo "[entrypoint] download failed (attempt ${attempt}/${max_attempts})" >&2
    attempt=$((attempt + 1))
    [ "$attempt" -le "$max_attempts" ] && sleep 5
  done
  rm -rf "$staging_dir"
  return 1
}

mkdir -p "$MODELS_DIR" "$CACHE_DIR" "$ARTIFACTS_DIR"

if _models_ready; then
  echo "[entrypoint] docling model bundle ${MODEL_BUNDLE_ID} present at ${ARTIFACTS_DIR}; skip download"
else
  echo "[entrypoint] docling model bundle missing or stale; downloading default standard model set..."
  _download_models || exit 1
  touch "${MODELS_DIR}/.artifacts_ready"
  echo "[entrypoint] docling model bundle ${MODEL_BUNDLE_ID} installed to ${ARTIFACTS_DIR}"
fi

export DOCLING_ARTIFACTS_PATH="$ARTIFACTS_DIR"

echo "[entrypoint] DOCLING_MODELS_DIR=${MODELS_DIR} DOCLING_CACHE_DIR=${CACHE_DIR} DOCLING_ARTIFACTS_PATH=${DOCLING_ARTIFACTS_PATH}"

exec uvicorn main:app --host 0.0.0.0 --port 8080
