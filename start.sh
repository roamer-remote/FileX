#!/bin/bash
# FileX 本地开发：Postgres + RabbitMQ + Redis + filex-ollama + kb-indexer + kb-post + kb-ragas-eval + filex(API) 用 Docker；
# kb-extract 在宿主机；Ollama 仅 Compose 内网 :11434，不映射宿主机。
# filex / kb-indexer 经 http://filex-ollama:11434 做向量嵌入与管理端探活。

set -e
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
COMPOSE_FILE="$SCRIPT_DIR/docker/docker-compose.yml"
COMPOSE_LOCAL="$SCRIPT_DIR/docker/docker-compose.local.yml"
PIP_INDEX="-i https://pypi.tuna.tsinghua.edu.cn/simple"

wait_ollama_ready() {
    for _ in $(seq 1 90); do
        if docker ps --format '{{.Names}}' 2>/dev/null | grep -qx 'filex-ollama'; then
            if "${COMPOSE[@]}" exec -T filex-ollama ollama list >/dev/null 2>&1; then
                return 0
            fi
        fi
        sleep 2
    done
    return 1
}

ollama_has_embed_model() {
    "${COMPOSE[@]}" exec -T filex-ollama ollama list 2>/dev/null | grep -q 'bge-m3'
}

if [ ! -d "$SCRIPT_DIR/.venv" ]; then
    echo "创建虚拟环境..."
    python3 -m venv "$SCRIPT_DIR/.venv"
fi
echo "安装/更新后端依赖..."
"$SCRIPT_DIR/.venv/bin/pip" install -q --upgrade pip $PIP_INDEX
"$SCRIPT_DIR/.venv/bin/pip" install -q -r "$SCRIPT_DIR/backend/requirements.txt" $PIP_INDEX

echo "安装/更新 kb-extract 依赖..."
"$SCRIPT_DIR/.venv/bin/pip" install -q -r "$SCRIPT_DIR/backend/requirements-extract.txt" $PIP_INDEX

echo "构建前端（写入 frontend/dist，供 filex 容器静态资源使用）..."
cd "$SCRIPT_DIR/frontend"
if [ ! -d node_modules ]; then
    npm install
fi
if command -v git >/dev/null 2>&1 && git -C "$SCRIPT_DIR" rev-parse --short=7 HEAD >/dev/null 2>&1; then
    export VITE_APP_BUILD_VERSION="$(TZ=Asia/Shanghai date +%Y-%m-%d)-$(git -C "$SCRIPT_DIR" rev-parse --short=7 HEAD)"
    echo "前端构建版本: ${VITE_APP_BUILD_VERSION}"
fi
npm run build
cd "$SCRIPT_DIR"

COMPOSE=(docker compose -p filex -f "$COMPOSE_FILE" -f "$COMPOSE_LOCAL")
RERANK_OK=1
MINERU_OK=0
DOCLING_OK=0
OLLAMA_OK=0
INDEXER_IN_DOCKER=0
POST_IN_DOCKER=0
RAGAS_EVAL_IN_DOCKER=0
FILEX_IN_DOCKER=0
export UPLOAD_DIR="${UPLOAD_DIR:-$SCRIPT_DIR/backend/uploads}"
mkdir -p "$UPLOAD_DIR"

if command -v docker >/dev/null 2>&1; then
    # shellcheck source=docker/scripts/tune-local-docker.sh
    . "$SCRIPT_DIR/docker/scripts/tune-local-docker.sh"

    # MinerU 内存默认 16g（大页数 PDF 推荐；可通过环境变量覆盖）
    export FILEX_MINERU_MEM_LIMIT="${FILEX_MINERU_MEM_LIMIT:-16g}"
    echo "  MinerU 内存限制: $FILEX_MINERU_MEM_LIMIT"

    echo "启动 PostgreSQL、RabbitMQ、Redis（见 docker-compose.local.yml）..."
    "${COMPOSE[@]}" up -d postgres rabbitmq redis
    if [ "${FILEX_SKIP_KB_RERANK:-0}" = "1" ]; then
        echo "已跳过 kb-rerank（FILEX_SKIP_KB_RERANK=1）"
        RERANK_OK=0
    else
        echo "启动 kb-rerank（可选；Apple Silicon 使用 linux/amd64 仿真镜像）..."
        RERANK_SRC="${FILEX_RERANK_SOURCE_IMAGE:-ghcr.io/huggingface/text-embeddings-inference:cpu-1.9.3}"
        if ! docker image inspect filex/tei-rerank:cpu-1.9.3 >/dev/null 2>&1; then
            echo "拉取 TEI rerank 镜像并标记为 filex/tei-rerank:cpu-1.9.3（linux/amd64，Apple Silicon 仿真）..."
            if docker pull --platform linux/amd64 "$RERANK_SRC" && docker tag "$RERANK_SRC" filex/tei-rerank:cpu-1.9.3; then
                :
            else
                RERANK_OK=0
                echo "警告: TEI rerank 镜像拉取失败，语义检索将跳过重排序。" >&2
                echo "  可手动执行: docker pull --platform linux/amd64 $RERANK_SRC && docker tag $RERANK_SRC filex/tei-rerank:cpu-1.9.3" >&2
                echo "  或设置 FILEX_SKIP_KB_RERANK=1 忽略；详见 docker/BUILD.md" >&2
            fi
        fi
        if ! "${COMPOSE[@]}" up -d kb-rerank; then
            RERANK_OK=0
            echo "警告: kb-rerank 未启动，语义检索将跳过重排序。" >&2
            echo "  可稍后执行: docker compose -p filex -f docker/docker-compose.yml -f docker/docker-compose.local.yml up -d kb-rerank" >&2
            echo "  或设置 FILEX_SKIP_KB_RERANK=1 忽略；详见 docker/BUILD.md" >&2
        fi
    fi
    if [ "${FILEX_SKIP_MINERU:-0}" = "1" ]; then
        echo "已跳过 filex-mineru（FILEX_SKIP_MINERU=1）"
    else
        echo "启动 filex-mineru（首次会下载 pipeline 模型，见 docker/data/mineru/models/）..."
        mkdir -p "$SCRIPT_DIR/docker/data/mineru/models" "$SCRIPT_DIR/docker/data/mineru/cache"
        echo "构建 MinerU 基础镜像（1/2 filex-os-base → 2/2 filex-mineru-base）..."
        if ! "${COMPOSE[@]}" --profile build-base build filex-os-base; then
            echo "警告: filex-os-base 构建失败，PDF 提取将走 legacy 路径。" >&2
        elif ! "${COMPOSE[@]}" --profile build-base build filex-mineru-base; then
            echo "警告: filex-mineru-base 构建失败，PDF 提取将走 legacy 路径。" >&2
        elif "${COMPOSE[@]}" up -d --build filex-mineru; then
            MINERU_OK=1
        else
            echo "警告: filex-mineru 未启动，PDF 提取将走 legacy 路径。" >&2
            echo "  可稍后执行: docker compose -p filex -f docker/docker-compose.yml -f docker/docker-compose.local.yml up -d --build filex-mineru" >&2
            echo "  或设置 FILEX_SKIP_MINERU=1 忽略。" >&2
        fi
    fi
    if [ "${FILEX_SKIP_DOCLING:-0}" = "1" ]; then
        echo "已跳过 filex-docling（FILEX_SKIP_DOCLING=1）"
    else
        echo "启动 filex-docling（首次会下载 Docling 模型，见 docker/data/docling/models/）..."
        mkdir -p "$SCRIPT_DIR/docker/data/docling/models" "$SCRIPT_DIR/docker/data/docling/cache"
        echo "构建 Docling 基础镜像（filex-docling-base）..."
        if ! "${COMPOSE[@]}" --profile build-base build filex-docling-base; then
            echo "警告: filex-docling-base 构建失败，Docling 提取将不可用。" >&2
        elif "${COMPOSE[@]}" up -d --build filex-docling; then
            DOCLING_OK=1
        else
            echo "警告: filex-docling 未启动。" >&2
            echo "  可稍后执行: docker compose -p filex -f docker/docker-compose.yml -f docker/docker-compose.local.yml up -d --build filex-docling" >&2
            echo "  或设置 FILEX_SKIP_DOCLING=1 忽略。" >&2
        fi
    fi
    if [ "${FILEX_SKIP_OLLAMA:-0}" = "1" ]; then
        echo "已跳过 filex-ollama（FILEX_SKIP_OLLAMA=1；索引嵌入将不可用）"
        OLLAMA_OK=0
    elif docker ps --format '{{.Names}}' 2>/dev/null | grep -qx 'filex-ollama'; then
        echo "filex-ollama 已在运行，等待就绪..."
        if wait_ollama_ready; then
            OLLAMA_OK=1
            if ! ollama_has_embed_model; then
                echo "提示: filex-ollama 已启动，bge-m3 仍在首次下载（约 1.2GB，视网速需十数分钟）。"
                echo "      kb-indexer 会先启动；向量索引需等模型就绪后生效。进度: docker logs -f filex-ollama"
            fi
        else
            echo "错误: filex-ollama 未在预期时间内就绪。" >&2
            echo "  请检查: docker compose -p filex logs filex-ollama --tail=50" >&2
            exit 1
        fi
    else
        echo "启动 filex-ollama（Compose 内网 :11434，不映射宿主机；首次可能拉取 bge-m3）..."
        mkdir -p "$SCRIPT_DIR/docker/data/ollama"
        if "${COMPOSE[@]}" up -d filex-ollama; then
            echo "等待 filex-ollama 就绪..."
            if wait_ollama_ready; then
                OLLAMA_OK=1
                if ! ollama_has_embed_model; then
                    echo "提示: filex-ollama 已启动，bge-m3 仍在首次下载（约 1.2GB，视网速需十数分钟）。"
                    echo "      kb-indexer 会先启动；向量索引需等模型就绪后生效。进度: docker logs -f filex-ollama"
                fi
            else
                echo "错误: filex-ollama 未在预期时间内就绪。" >&2
                echo "  请检查: docker compose -p filex logs filex-ollama --tail=50" >&2
                exit 1
            fi
        else
            echo "错误: filex-ollama 启动失败。" >&2
            exit 1
        fi
    fi
    echo "等待数据库就绪..."
    for i in $(seq 1 30); do
        if "${COMPOSE[@]}" exec -T postgres pg_isready -U filebox -d filebox >/dev/null 2>&1; then
            break
        fi
        sleep 1
    done
    # kb-extract 基础镜像（含 requirements-extract.txt）
    if ! "${COMPOSE[@]}" --profile build-base build kb-extract; then
        echo "警告: filex-extract-base 构建失败，将尝试用 filex/app 镜像运行。" >&2
    fi
else
    echo "警告: 未检测到 docker，请自行保证 PostgreSQL 可访问。" >&2
    RERANK_OK=0
    MINERU_OK=0
    DOCLING_OK=0
    OLLAMA_OK=0
fi

export FILEX_BOOTSTRAP_USERNAME="${FILEX_BOOTSTRAP_USERNAME:-admin}"
export FILEX_BOOTSTRAP_PASSWORD="${FILEX_BOOTSTRAP_PASSWORD:-roamer73}"
export KB_SEARCH_MIN_SCORE="${KB_SEARCH_MIN_SCORE:-0.35}"
if [ "$MINERU_OK" = "1" ]; then
    export FILEX_ENABLE_MINERU_PROVIDER="${FILEX_ENABLE_MINERU_PROVIDER:-1}"
else
    export FILEX_ENABLE_MINERU_PROVIDER="${FILEX_ENABLE_MINERU_PROVIDER:-0}"
fi
if [ "$DOCLING_OK" = "1" ]; then
    # Docling extract configs are set in docker-compose.local.yml kb-extract service
    :
fi
if [ "$RERANK_OK" = 1 ]; then
    export KB_RERANK_URL="${KB_RERANK_URL:-http://kb-rerank:80/rerank}"
else
    export KB_RERANK_URL=""
fi
export TZ="${TZ:-Asia/Shanghai}"
export FILEX_LOG_TIMEZONE="${FILEX_LOG_TIMEZONE:-Asia/Shanghai}"
export FILEX_LOG_FORMAT="${FILEX_LOG_FORMAT:-console}"
export FILEX_LOG_LEVEL="${FILEX_LOG_LEVEL:-INFO}"

echo "执行数据库迁移..."
if docker image inspect filex/app:latest >/dev/null 2>&1; then
    "${COMPOSE[@]}" run --rm --no-deps filex alembic upgrade head
else
    echo "构建 filex/app 镜像（供迁移使用）..."
    "${COMPOSE[@]}" build filex
    "${COMPOSE[@]}" run --rm --no-deps filex alembic upgrade head
fi

EXTRACT_PID=""
cleanup() {
    if [ -n "$EXTRACT_PID" ]; then
        echo "停止 kb-extract 容器..."
        "${COMPOSE[@]}" stop kb-extract 2>/dev/null || true
    fi
    if command -v docker >/dev/null 2>&1; then
        if [ "$FILEX_IN_DOCKER" = 1 ]; then
            echo "停止 filex 容器..."
            "${COMPOSE[@]}" stop filex 2>/dev/null || true
        fi
        if [ "$INDEXER_IN_DOCKER" = 1 ]; then
            echo "停止 kb-indexer 容器..."
            "${COMPOSE[@]}" stop kb-indexer 2>/dev/null || true
        fi
        if [ "$POST_IN_DOCKER" = 1 ]; then
            echo "停止 kb-post 容器..."
            "${COMPOSE[@]}" stop kb-post 2>/dev/null || true
        fi
        if [ "$RAGAS_EVAL_IN_DOCKER" = 1 ]; then
            echo "停止 kb-ragas-eval 容器..."
            "${COMPOSE[@]}" stop kb-ragas-eval 2>/dev/null || true
        fi
    fi
}
trap cleanup EXIT INT TERM

stop_stale_local_workers() {
    local mod pid
    for mod in kb_indexer kb_extract; do
        while read -r pid; do
            [ -n "$pid" ] || continue
            echo "停止残留 ${mod} (PID ${pid})..."
            kill "$pid" 2>/dev/null || true
        done < <(pgrep -f "${SCRIPT_DIR}/.venv/bin/python -m workers.${mod}" 2>/dev/null || true)
    done
    while read -r pid; do
        [ -n "$pid" ] || continue
        echo "停止残留 FileX API (PID ${pid})..."
        kill "$pid" 2>/dev/null || true
    done < <(pgrep -f "${SCRIPT_DIR}/.venv/bin/uvicorn main:app" 2>/dev/null || true)
    sleep 1
}

stop_stale_local_workers

cd "$SCRIPT_DIR/backend"

if [ "$OLLAMA_OK" = 1 ] && command -v docker >/dev/null 2>&1; then
    echo "启动 app workers（filex + kb-indexer + kb-post + kb-ragas-eval；共用 filex/app，须一并 force-recreate）..."
    if ! docker image inspect filex/app:latest >/dev/null 2>&1; then
        if [ "${FILEX_BUILD_INDEXER:-0}" = "1" ] || [ "${FILEX_BUILD:-0}" = "1" ]; then
            echo "本地无 filex/app:latest，正在构建（FILEX_BUILD=1）..."
            APP_WORKERS_UP=(up -d --force-recreate --build filex kb-indexer kb-post kb-ragas-eval)
        else
            echo "错误: 本地缺少 filex/app:latest 镜像，无法启动 kb-indexer / kb-post / kb-ragas-eval / filex 容器。" >&2
            echo "  一次性构建: FILEX_BUILD=1 ./start.sh" >&2
            echo "  或见 docker/BUILD.md 构建 filex/app-base 与 filex/app。" >&2
            exit 1
        fi
    else
        APP_WORKERS_UP=(up -d --force-recreate filex kb-indexer kb-post kb-ragas-eval)
        if [ "${FILEX_BUILD_INDEXER:-0}" = "1" ] || [ "${FILEX_BUILD:-0}" = "1" ]; then
            APP_WORKERS_UP=(up -d --force-recreate --build filex kb-indexer kb-post kb-ragas-eval)
        fi
    fi
    if "${COMPOSE[@]}" "${APP_WORKERS_UP[@]}"; then
        INDEXER_IN_DOCKER=1
        POST_IN_DOCKER=1
        RAGAS_EVAL_IN_DOCKER=1
        FILEX_IN_DOCKER=1
    else
        echo "错误: app workers 容器启动失败。" >&2
        echo "  查看: docker compose -p filex logs kb-indexer kb-post kb-ragas-eval filex --tail=80" >&2
        echo "  若为镜像构建 401/429，勿用 --build；依赖变更时再 FILEX_BUILD=1" >&2
        echo "  仅重启三容器: ./scripts/dev/restart-app-workers.sh" >&2
        exit 1
    fi
elif [ "${FILEX_SKIP_OLLAMA:-0}" != "1" ]; then
    echo "警告: Ollama 未就绪，跳过 kb-indexer 与 filex 容器。" >&2
fi

echo "启动 kb-extract（容器内）..."
"${COMPOSE[@]}" up -d --no-deps kb-extract
EXTRACT_PID=$("${COMPOSE[@]}" ps -q kb-extract 2>/dev/null || echo "")

if [ "$FILEX_IN_DOCKER" = 1 ]; then
    echo "登录: ${FILEX_BOOTSTRAP_USERNAME:-admin} / （见 FILEX_BOOTSTRAP_PASSWORD，默认 roamer73）"
    echo "访问: http://127.0.0.1:8000  （热更新前端: cd frontend && npm run dev → http://localhost:5173）"
    echo "API / 管理端 Ollama 探活均在 filex 容器内，经 http://filex-ollama:11434"
    docker logs -f filex
else
    echo "错误: filex 容器未启动，本地开发需要 Docker。" >&2
    exit 1
fi
