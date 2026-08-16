#!/bin/sh
set -eu

###############################################################################
# MinerU Sidecar Entrypoint
#
# 设计目标：
#   1. 容器启动时自动确保 MinerU 4 basic 本地模型完整。
#   2. 模型数据持久化在宿主机卷上（/models 由宿主机 bind mount 进来）。
#   3. 仅在缺失或被强制时才真正执行下载，避免每次启动重复下载大文件（数 GB）。
#   4. 下载成功后写入完成标记，供后续启动和 /health 快速判断。
#
# 关键文件：
#   - COMPLETE_MARKER = $MODELS_DIR/.pipeline_complete
#   - MinerU 4 使用 $MODELS_DIR/PDF-Extract-Kit-1.0；历史卷中的
#     $MODELS_DIR/pipeline 会以符号链接兼容复用，无需重复下载模型。
#
# 环境变量（可在 compose / 宿主机注入）：
#   MINERU_MODELS_DIR            默认 /models（宿主机持久化目录）
#   MINERU_TOOLS_CONFIG_JSON     默认 /models/mineru.json
#   MINERU_MODEL_SOURCE          下载源：modelscope（国内推荐）/ huggingface / local
#   MINERU_MODEL_STACK            full（FileX 默认，兼容 pipeline runner）/ light
#   FORCE_MINERU_MODEL_DOWNLOAD  =1 时强制重新下载（调试/升级模型时使用）
#
# 健康检查联动：
#   启动成功后 uvicorn 才开始监听，/health 会返回 models_ready 等字段。
#   Docker HEALTHCHECK 依赖 /health 返回 200。
#
# 持久化布局（宿主机示例）：
#   生产：/root/important/FileX/product/mineru/models
#   本地：docker/data/mineru/models
###############################################################################

MODELS_DIR="${MINERU_MODELS_DIR:-/models}"
PIPELINE_DIR="${MODELS_DIR}/pipeline"
V4_MODEL_DIR="${MODELS_DIR}/PDF-Extract-Kit-1.0"
COMPLETE_MARKER="${MODELS_DIR}/.pipeline_complete"
MODEL_STACK="${MINERU_MODEL_STACK:-full}"

case "$MODEL_STACK" in
  full|light) ;;
  *)
    echo "[entrypoint] MINERU_MODEL_STACK must be full or light, got: $MODEL_STACK" >&2
    exit 64
    ;;
esac

_mineru_version() {
  python3 - <<'PY'
from importlib import metadata

try:
    print(metadata.version("mineru"))
except metadata.PackageNotFoundError:
    print("unknown")
PY
}

# FileX's current runner uses MinerU's local pipeline, so full is the default.
# The light stack remains available for a future ONNX-native runner.
_models_ready() {
  [ -f "$COMPLETE_MARKER" ] || return 1
  if [ "$MODEL_STACK" = "full" ]; then
    [ -d "$V4_MODEL_DIR/models/Layout/PP-DocLayoutV2" ] &&
      [ -n "$(ls "$V4_MODEL_DIR/models/Layout/PP-DocLayoutV2" 2>/dev/null)" ] &&
      [ -f "$V4_MODEL_DIR/models/OCR/paddleocr_torch/ch_PP-OCRv6_small_det_infer.safetensors" ] || return 1
  else
    for model_dir in \
      PP-DocLayoutV2_onnx \
      PP-OCRv6_small_det_onnx \
      PP-OCRv6_small_rec_onnx \
      PP-FormulaNet_plus-M_onnx; do
      [ -d "$MODELS_DIR/$model_dir" ] && [ -n "$(ls "$MODELS_DIR/$model_dir" 2>/dev/null)" ] || return 1
    done
  fi
  mineru-kit models verify --tier basic --stack "$MODEL_STACK" >/dev/null 2>&1
}

echo "[entrypoint] mineru version: $(_mineru_version)"

# GPU overlay sets MINERU_DEVICE=cuda. Refuse to start if that image cannot
# actually execute CUDA, instead of accepting work that will silently fall back.
if [ "${MINERU_DEVICE:-cpu}" = "cuda" ]; then
  if ! python3 - <<'PY'
import torch

assert torch.cuda.is_available(), "CUDA is unavailable"
assert torch.cuda.device_count() > 0, "no CUDA devices are visible"
capability = torch.cuda.get_device_capability(0)
arch = f"sm_{capability[0]}{capability[1]}"
arch_list = torch.cuda.get_arch_list()
# The pinned cu118 torch 2.6 wheel exposes sm_60 for Pascal GPUs.  Its
# sm_60 kernels execute correctly on the GTX 1080 (sm_61), so do not reject
# this compatible minor architecture and accidentally fall back to CPU.
if arch not in arch_list and not (arch == "sm_61" and "sm_60" in arch_list):
    raise RuntimeError(
        f"GPU architecture {arch} is not compiled into this PyTorch wheel; "
        "refusing a CPU fallback"
    )
print(
    f"[entrypoint] CUDA ready: {torch.cuda.get_device_name(0)} "
    f"capability={arch}"
)
PY
  then
    echo "[entrypoint] MINERU_DEVICE=cuda requires a visible GPU with a supported PyTorch kernel" >&2
    exit 78
  fi
fi

FORCE_DOWNLOAD="${FORCE_MINERU_MODEL_DOWNLOAD:-0}"

# Reuse the persisted MinerU 3.x pipeline volume with MinerU 4's registry
# layout. Do not replace an already downloaded MinerU 4 model directory.
if [ ! -e "$V4_MODEL_DIR" ] && \
   [ -f "$PIPELINE_DIR/models/OCR/paddleocr_torch/ch_PP-OCRv6_small_det_infer.safetensors" ]; then
  ln -s "$PIPELINE_DIR" "$V4_MODEL_DIR"
fi

export MINERU_MODEL_BASE_DIR="$MODELS_DIR"

if _models_ready && [ "$FORCE_DOWNLOAD" != "1" ]; then
  echo "[entrypoint] complete MinerU 4 basic models found; skip download (models persisted on host volume)"
else
  if [ "$FORCE_DOWNLOAD" = "1" ]; then
    echo "[entrypoint] FORCE_MINERU_MODEL_DOWNLOAD=1; forcing re-download of MinerU 4 basic models..."
  else
    echo "[entrypoint] MinerU 4 basic models incomplete or marker missing; downloading..."
  fi

  # 确定下载源（默认 modelscope，国内网络更友好）
  DOWNLOAD_SOURCE="${MINERU_MODEL_SOURCE:-modelscope}"
  if [ "$DOWNLOAD_SOURCE" = "local" ]; then
    DOWNLOAD_SOURCE=modelscope
  fi
  export MINERU_MODEL_SOURCE="$DOWNLOAD_SOURCE"
  export MODELSCOPE_CACHE="${MODELS_DIR}/.ms_cache"
  mkdir -p "$MODELSCOPE_CACHE" "$MODELS_DIR"

  # 下载前清理旧标记，避免半失败状态
  rm -f "$COMPLETE_MARKER"

  # A legacy pipeline symlink can be verified and reused for the full stack.
  # Never recursively remove through that symlink.
  if [ -L "$V4_MODEL_DIR" ]; then
    rm -f "$V4_MODEL_DIR"
  elif [ -e "$V4_MODEL_DIR" ]; then
    rm -rf "$V4_MODEL_DIR"
  fi
  mineru-kit models download --tier basic --stack "$MODEL_STACK" --source "$DOWNLOAD_SOURCE" || exit 1
  mineru-kit models verify --tier basic --stack "$MODEL_STACK" || exit 1
  touch "$COMPLETE_MARKER"
  echo "[entrypoint] MinerU 4 basic models installed to ${V4_MODEL_DIR} (persisted on host)"
fi

# 运行时强制使用本地模型，避免容器再次尝试联网
export MINERU_MODEL_SOURCE=local

exec uvicorn main:app --host 0.0.0.0 --port 8080
