#!/bin/bash
# 根据 Docker Desktop VM 资源导出 FILEX_* 环境变量，供 docker-compose.local.yml 使用。
# 调用方：start.sh（docker compose up 之前 source 本脚本）。

_tune_docker_mem_mib() {
    docker info --format '{{.MemTotal}}' 2>/dev/null | awk '{printf "%d", $1/1024/1024}'
}

_tune_docker_cpus() {
    docker info --format '{{.NCPU}}' 2>/dev/null
}

_tune_clamp_threads() {
    local threads="$1"
    local cpus="$2"
    if [ -n "$cpus" ] && [ "$cpus" -gt 2 ] 2>/dev/null; then
        local max=$((cpus - 2))
        if [ "$threads" -gt "$max" ]; then
            threads="$max"
        fi
    fi
    echo "$threads"
}

_tune_clamp_cpus() {
    local want="$1"
    local total="$2"
    if [ -z "$total" ] || [ "$total" -lt 1 ] 2>/dev/null; then
        echo "$want"
        return
    fi
    if [ "$want" -gt "$total" ]; then
        echo "$total"
    else
        echo "$want"
    fi
}

FILEX_DOCKER_MEM_MIB="$(_tune_docker_mem_mib)"
FILEX_DOCKER_CPUS="$(_tune_docker_cpus)"

if [ -z "$FILEX_DOCKER_MEM_MIB" ] || [ "$FILEX_DOCKER_MEM_MIB" -lt 512 ] 2>/dev/null; then
    return 0 2>/dev/null || exit 0
fi

export FILEX_DOCKER_MEM_MIB
export FILEX_DOCKER_CPUS

if [ "$FILEX_DOCKER_MEM_MIB" -lt 12000 ] 2>/dev/null; then
    echo "提示: Docker Desktop 内存约 ${FILEX_DOCKER_MEM_MIB} MiB，MinerU 与 kb-rerank 并发时易 OOM。" >&2
    echo "  建议: Docker Desktop → Settings → Resources → Memory 调至 16–24 GiB。" >&2
    export FILEX_MINERU_MEM_LIMIT="${FILEX_MINERU_MEM_LIMIT:-5g}"
    export FILEX_MINERU_SHM_SIZE="${FILEX_MINERU_SHM_SIZE:-1gb}"
    export FILEX_KB_RERANK_MEM_LIMIT="${FILEX_KB_RERANK_MEM_LIMIT:-3g}"
    export FILEX_MINERU_THREADS="${FILEX_MINERU_THREADS:-6}"
    export FILEX_MINERU_CPUS="${FILEX_MINERU_CPUS:-6}"
    export FILEX_KB_RERANK_CPUS="${FILEX_KB_RERANK_CPUS:-3}"
else
    export FILEX_MINERU_MEM_LIMIT="${FILEX_MINERU_MEM_LIMIT:-8g}"
    export FILEX_MINERU_SHM_SIZE="${FILEX_MINERU_SHM_SIZE:-2gb}"
    export FILEX_KB_RERANK_MEM_LIMIT="${FILEX_KB_RERANK_MEM_LIMIT:-4g}"
    export FILEX_MINERU_THREADS="${FILEX_MINERU_THREADS:-8}"
    export FILEX_MINERU_CPUS="${FILEX_MINERU_CPUS:-8}"
    export FILEX_KB_RERANK_CPUS="${FILEX_KB_RERANK_CPUS:-4}"
fi

FILEX_MINERU_THREADS="$(_tune_clamp_threads "${FILEX_MINERU_THREADS}" "${FILEX_DOCKER_CPUS}")"
export FILEX_MINERU_THREADS
export FILEX_MINERU_CPUS="$(_tune_clamp_cpus "${FILEX_MINERU_CPUS}" "${FILEX_DOCKER_CPUS}")"
export FILEX_KB_RERANK_CPUS="$(_tune_clamp_cpus "${FILEX_KB_RERANK_CPUS}" "${FILEX_DOCKER_CPUS}")"

# T-1.2 Ollama 侧 NUM_PARALLEL（embedding 并发匹配）
# 默认 4，可被宿主机 OLLAMA_NUM_PARALLEL 覆盖；根据 CPU 适当上限
OLLAMA_NUM_PARALLEL="${OLLAMA_NUM_PARALLEL:-4}"
if [ -n "$FILEX_DOCKER_CPUS" ] && [ "$FILEX_DOCKER_CPUS" -gt 1 ] 2>/dev/null; then
    max_parallel=$(( FILEX_DOCKER_CPUS - 1 ))
    if [ "$OLLAMA_NUM_PARALLEL" -gt "$max_parallel" ] 2>/dev/null; then
        OLLAMA_NUM_PARALLEL=$max_parallel
    fi
fi
export OLLAMA_NUM_PARALLEL

echo "Docker 资源调优: mem=${FILEX_DOCKER_MEM_MIB}MiB cpus=${FILEX_DOCKER_CPUS} → mineru(limit=${FILEX_MINERU_MEM_LIMIT} threads=${FILEX_MINERU_THREADS} cpus=${FILEX_MINERU_CPUS}) rerank(limit=${FILEX_KB_RERANK_MEM_LIMIT} cpus=${FILEX_KB_RERANK_CPUS}) ollama(NUM_PARALLEL=${OLLAMA_NUM_PARALLEL})"
