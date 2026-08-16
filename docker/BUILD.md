# Docker 构建说明

## 宿主机代理（:7890）与国内镜像加速

**原则**：已有国内镜像/国内源的步骤**直连**，不经宿主机代理；仅外网资源按需走 `BUILD_HTTP_PROXY`（默认 `http://host.docker.internal:7890`）。

| 资源 | 镜像/源 | 是否走代理 |
|------|---------|------------|
| 基础镜像 | `docker.m.daocloud.io/library/...` | 否（daemon 拉取） |
| apt | 阿里云 `mirrors.aliyun.com` | 否 |
| pip | 清华 `pypi.tuna.tsinghua.edu.cn` | 否 |
| npm（filex 前端） | 官方 `registry.npmjs.org` | **是** |
| SCWS | `xunsearch.com` | 否 |
| zhparser | GitHub | **是**（仅 clone 步骤） |

| Compose 注入 `BUILD_HTTP_PROXY` 的服务 | 说明 |
|------|------|
| `filex` | 前端 npm 构建阶段 |
| `postgres` | zhparser `git clone` |

`kb-extract`、`filex-mineru`、`filex-docling` 仅 apt/pip 国内源，compose **不**注入代理。

运行阶段镜像内不保留 `HTTP_PROXY`/`HTTPS_PROXY`，避免 Ollama、ModelScope 等误走代理。

**使用前请确认**（仅需代理的步骤）：宿主机 Clash/Surge 等已监听 **7890**，且 Docker 可访问 `host.docker.internal`（Linux 需 compose 的 `host-gateway`）。

```bash
# 生产常规发布：一行 build（filex/app + filex/kb-extract），再 up worker 容器
./scripts/deploy/bamboo-compose.sh build
./scripts/deploy/bamboo-compose.sh up -d --no-build filex kb-indexer kb-post kb-extract filex-mineru filex-docling

# 本地 MinerU 笔记侧：先构建可长期复用的 mineru base，再构建笔记侧
docker compose -p filex -f docker/docker-compose.yml -f docker/docker-compose.local.yml --profile build-base build filex-os-base
docker compose -p filex -f docker/docker-compose.yml -f docker/docker-compose.local.yml --profile build-base build filex-mineru-base
docker compose -p filex -f docker/docker-compose.yml -f docker/docker-compose.local.yml up -d --build filex-mineru
```

## 长期构建缓存：base 镜像与业务镜像分离

FileX 的生产与本地 compose 使用同一套 base 镜像约定：

| 镜像 | 内容 | 什么时候重建 |
|------|------|--------------|
| `filex/os-base:py3.13` | **共用底层**：`python:3.13-slim`、Debian 镜像、共用 apt、pip、时区 | `docker/Dockerfile.base` os 段变化 |
| `filex/app-base:py3.13` | `filex-os-base` + `backend/requirements.txt` | requirements 或 os-base 变化 |
| `filex/kb-extract-base:py3.13` | os-base + LibreOffice / imagemagick + extract requirements | extract 依赖或 os-base 变化 |
| `filex/mineru-base:py3.13` | os-base + gcc/tesseract + 公共依赖 + CPU PyTorch（不含 MinerU） | 平台依赖或 os-base 变化 |
| `filex/docling-base:py3.13` | os-base + gcc + docling requirements | docling 依赖或 os-base 变化 |
| `filex/app:*` | app-base + 后端代码 + 前端 dist（**kb-indexer 共用**） | 业务代码 / 前端 |
| `filex/kb-extract:*` | extract-base + 后端代码 | extract 代码 |
| `filex-filex-mineru:*` | mineru-base + MinerU pin + 笔记侧 `.py`（`mineru-runtime`） | MinerU 版本或笔记侧代码 |
| `filex-filex-docling:*` | docling-base + 笔记侧 `.py`（`docling-runtime`） | 笔记侧代码 |
| `filex/tei-rerank:cpu-1.9.3` | TEI rerank（自 `ghcr.io` 拉取一次并本地 tag） | 升级 TEI 版本时 |

日常业务发布不要运行裸 `docker compose build` 或 `up --build` 全量构建。请使用 `bamboo-compose.sh build`（或 `build-app-and-extract`）而非 compose 直连 build：

```bash
# 生产常规发布（推荐）
./scripts/deploy/bamboo-compose.sh build
./scripts/deploy/bamboo-compose.sh up -d --no-build filex kb-indexer kb-post kb-extract filex-mineru filex-docling

# 仅 API/前端/后处理变化（须同时 up filex + kb-indexer + kb-post，三者共用 filex/app 镜像）
./scripts/deploy/bamboo-compose.sh build-app-and-up-workers

# pdf-inspector / kb-extract 变化：构建并重建 app workers + kb-extract。
# CPU 与 NVIDIA GPU 均使用同一运行时 overlay，默认启用 inspector extract 模式。
./scripts/deploy/bamboo-compose.sh build-app-and-up-extract-workers

# inspector 运行时配置由 docker-compose.pdf-inspector.yml 提供默认值。
# 需要临时覆盖时，在 CI/CD 进程环境中设置（不是写入 FILEX_SECRETS_FILE）：
# KB_PDF_INSPECTOR_ENABLED=0 KB_PDF_INSPECTOR_MODE=disabled \
#   KB_PDF_INSPECTOR_TIMEOUT_SEC=17 ./scripts/deploy/bamboo-compose.sh up -d --no-build kb-extract

# 等价分步：
# ./scripts/deploy/bamboo-compose.sh build-app
# ./scripts/deploy/bamboo-compose.sh up-app-workers

# 仅 kb-extract 代码或依赖变化
./scripts/deploy/bamboo-compose.sh build-extract
./scripts/deploy/bamboo-compose.sh up -d --no-build kb-extract

# MinerU：仅改笔记侧代码时 build-mineru 会跳过 mineru-base（依赖指纹未变）
./scripts/deploy/bamboo-compose.sh build-mineru
./scripts/deploy/bamboo-compose.sh up -d --no-build filex-mineru

# Bamboo/WHB 使用全新 Docker builder 时，配置已发布的稳定 deps 镜像；
# 后续 MinerU 升级只拉取该镜像并构建 runtime 层。
export FILEX_MINERU_DEPS_IMAGE=ghcr.io/roamer-remote/filex-mineru-deps:py3.13-cpu
./scripts/deploy/bamboo-compose.sh build-mineru
./scripts/deploy/bamboo-compose.sh up -d --no-build filex-mineru

# WHB/GPU：使用仓库内固定的稳定 Docling GPU 依赖镜像，避免每次重新下载 PyTorch/Docling。
# bamboo-compose.sh 和 deploy-filex-amd64-nvidia.sh 会自动读取 docker/dependency-images.env。
./scripts/deploy/bamboo-compose.sh build-docling
./scripts/deploy/bamboo-compose.sh up -d --no-build filex-docling

# 仅 Docling 笔记侧
./scripts/deploy/bamboo-compose.sh build-docling
./scripts/deploy/bamboo-compose.sh up -d --no-build filex-docling

# 首次部署或核心依赖统一刷新
./scripts/deploy/bamboo-compose.sh build-core
```

`docker/Dockerfile.base` 统一 os/app/extract/mineru base；`Dockerfile.mineru-sidecar` 仅 `mineru-runtime`；compose 与 `build_mineru` 使用 `--target mineru-runtime`，避免代码变更触发 pip。`ensure_mineru_base` 按 requirements + Dockerfile 指纹决定是否重建 base。生产脚本对 `filex`、`kb-extract`、`filex-mineru` 使用精确 `docker build`，避免 `docker compose build filex` 连带构建 `depends_on` 中的 `postgres`。

**无代理环境**（如 GitHub Actions）：显式关闭代理，apt/pip 仍走国内源；postgres 的 zhparser 需能访问 GitHub 或设 `BUILD_HTTP_PROXY=` 并预置源码。

```bash
docker build -f docker/Dockerfile.postgres -t filex-postgres:pg16-zh --build-arg BUILD_HTTP_PROXY= .
BUILD_HTTP_PROXY= ./scripts/deploy/bamboo-compose.sh build-app
```

## 拉取基础镜像失败（USTC EOF）

若日志出现 `docker.mirrors.ustc.edu.cn` 且 `EOF`，说明宿主机 Docker 配置了已停用的中科大镜像。

**做法一（推荐）**：使用本仓库 `docker/docker-compose.yml` 已配置的 DaoCloud 直连前缀，无需改 daemon：

```bash
docker build -f docker/Dockerfile.base --target filex-os-base -t filex/os-base:py3.13 --no-cache .
docker build -f docker/Dockerfile.base --target filex-app-base -t filex/app-base:py3.13 --build-arg FILEX_OS_BASE_IMAGE=filex/os-base:py3.13 .
./scripts/deploy/bamboo-compose.sh build-app
```

**做法二**：修改构建机 `/etc/docker/daemon.json`，删除 `docker.mirrors.ustc.edu.cn`，可参考 `docker/daemon.json.example`，然后：

```bash
sudo systemctl restart docker
```

**海外或直连 Docker Hub**：构建时覆盖为空前缀的官方镜像名：

```bash
docker build -f docker/Dockerfile.base --target filex-os-base -t filex/os-base:py3.13 \
  --build-arg NODE_IMAGE=node:20-alpine \
  --build-arg PYTHON_IMAGE=python:3.13-slim
./scripts/deploy/bamboo-compose.sh build-app
```

并将 `postgres` 的 `image` 改回 `pgvector/pgvector:pg16`。

## kb-rerank 拉模型超时（huggingface.co Connection timed out）

`kb-rerank` 使用 TEI。**生产环境须离线加载**：模型放在宿主机 `rerank_data/model/`，compose 使用 `--model-id /data/model`（不再用 Hub ID 联网补拉 `1_Pooling/config.json` 等）。

**预下载（flat 目录，含 1_Pooling）**：

```bash
mkdir -p /root/important/FileBox/product/rerank_data/model
COMPOSE_PROJECT=filebox ./docker/scripts/prefetch-kb-rerank-model.sh
ls /root/important/FileBox/product/rerank_data/model/1_Pooling
docker compose -p filebox -f docker/docker-compose.yml up -d --force-recreate kb-rerank
docker logs -f filex-kb-rerank
```

若已有 Hub 缓存 `models--BAAI--bge-reranker-base/`，可先复制 snapshot 再补全缺失文件：

```bash
SNAP=$(ls -d /root/important/FileBox/product/rerank_data/models--BAAI--bge-reranker-base/snapshots/* | head -1)
mkdir -p /root/important/FileBox/product/rerank_data/model
cp -aL "$SNAP"/. /root/important/FileBox/product/rerank_data/model/
# 再执行 prefetch 或 hf download ... --local-dir 补 1_Pooling 等
```

**临时降级**：清空 `KB_RERANK_URL` 或停掉 `kb-rerank`，语义检索仍可用，只是无 Cross-Encoder 重排（后端会自动 passthrough）。

## 本地 app workers（filex + kb-indexer + kb-post）

三者共用 `filex/app:latest`（`docker-compose.local.yml` 挂载 `backend/`）。**kb-indexer / kb-post 无 `--reload`**，只 `docker compose restart filex` 时，后处理消费者仍跑旧进程内代码（118 force RAPTOR 等会表现为 API 已更新、post 仍 skip）。

| 场景 | 命令 |
|------|------|
| 日常启动 | `./start.sh`（已对三容器 `--force-recreate`） |
| 改后端 post/raptor 后 | `./scripts/dev/restart-app-workers.sh` |
| 依赖/镜像变更 | `FILEX_BUILD=1 ./scripts/dev/restart-app-workers.sh` |

验收：`docker compose -p filex exec kb-post python -c "from services.kb_post_service import _run_raptor_only_post_job; print('ok')"`

## 本地 Mac 资源调优（Apple Silicon + Docker Desktop）

本机物理内存充足时，**Docker Desktop 默认可能只分配 ~8 GiB**，与 MinerU 解析峰值（约 4–5 GiB）+ kb-rerank（amd64 仿真，约 3–4 GiB）叠加易 OOM。

**推荐（一次性）**：Docker Desktop → **Settings → Resources**

| 项 | 本机 M2 Max（96 GiB 物理内存）建议 |
|----|-----------------------------------|
| **Memory** | **16–24 GiB**（当前若仅 ~8 GiB 请上调） |
| **CPUs** | 10–12（与物理核数接近即可） |
| **Swap** | 2 GiB |
| **Resource Saver** | 解析 PDF 期间可暂时关闭，避免笔记侧被挂起 |

`./start.sh` 会在 `docker compose up` 前 **source** `docker/scripts/tune-local-docker.sh`，按 Docker VM 实际内存自动设置：

| Docker VM 内存 | MinerU `mem_limit` | 线程 | kb-rerank `mem_limit` |
|----------------|-------------------|------|----------------------|
| &lt; 12 GiB | 5g | 6 | 3g |
| ≥ 12 GiB | 8g | 8 | 4g |

手动覆盖（示例）：

```bash
export FILEX_MINERU_MEM_LIMIT=6g FILEX_MINERU_THREADS=8
export UPLOAD_DIR="$(pwd)/backend/uploads"
docker compose -p filex -f docker/docker-compose.yml -f docker/docker-compose.local.yml up -d --force-recreate filex-mineru kb-rerank
```

**MinerU 镜像**：本地 `filex-mineru` 为 **linux/arm64 原生**（M 系列更快）；`kb-rerank` 仍为 `linux/amd64` 仿真（TEI 无 arm64 官方镜像）。

## filex-mineru 本地开发（032）

`./start.sh` 默认构建并启动 `filex-mineru`（见 `docker-compose.local.yml`）：

- **镜像源**：与生产一致 — 基础镜像 `docker.m.daocloud.io/library/python:3.11-slim`，Dockerfile 内 apt 走阿里云、pip 走清华（不经宿主机代理）
- 模型与缓存：`docker/data/mineru/{models,cache}/`（已 gitignore）；应用日志：`docker/data/logs/filex-mineru.log`（与 filex 本地日志同目录）
- 健康检查：`http://127.0.0.1:8080/health`
- 宿主机 `kb-extract` 经 `kb.mineru` MQ RPC 调用笔记侧；`UPLOAD_DIR` 以同路径 bind mount 进容器
- 首次启动 entrypoint 会从 ModelScope 下载 pipeline 权重（数 GB，healthcheck `start_period` 10 分钟）
- 跳过：`FILEX_SKIP_MINERU=1 ./start.sh`
- 单独拉起：

```bash
export UPLOAD_DIR="$(pwd)/backend/uploads"
docker compose -p filex -f docker/docker-compose.yml -f docker/docker-compose.local.yml build filex-mineru-base
docker compose -p filex -f docker/docker-compose.yml -f docker/docker-compose.local.yml up -d --build filex-mineru
docker logs -f filex-mineru
```

## filex-docling 本地开发（070）

`./start.sh` 在 rabbitmq healthy 后构建并启动 `filex-docling`（见 `docker-compose.local.yml`）：

- **Python**：笔记侧 **3.11-slim**（与 MinerU 一致）；**无宿主机 `ports:`**，栈内 `http://filex-docling:8080`
- 模型与缓存：`docker/data/docling/{models,cache}/`；kb-extract 经 **`kb.docling` MQ RPC**（`KB_EXTRACT_DOCLING_USE_MQ=1`）
- 默认模型包：`docling-2.117.0-standard-default`；实际包含 `docling-layout-heron`、`DocumentFigureClassifier-v2.5`、`CodeFormulaV2`、新版 `docling-models` 表格模型和 RapidOCR。模型目录内的 `.filex-model-manifest` 用于识别旧缓存并触发重新下载
- 宿主机 kb-extract 读 assets：`KB_EXTRACT_DOCLING_CACHE_MOUNT` → `docker/data/docling/cache`
- 跳过：`FILEX_SKIP_DOCLING=1 ./start.sh`
- 健康检查 / debug HTTP（栈内）：

```bash
docker compose -p filex -f docker/docker-compose.yml -f docker/docker-compose.local.yml exec filex-docling curl -sf http://127.0.0.1:8080/health
docker compose -p filex -f docker/docker-compose.yml -f docker/docker-compose.local.yml build filex-docling-base
docker compose -p filex -f docker/docker-compose.yml -f docker/docker-compose.local.yml up -d --build filex-docling
docker logs -f filex-docling
```

---

## NVIDIA GPU 部署（130）

GPU 部署完全独立于 `bamboo-compose.sh`，使用自动分流入口或专用脚本：

```bash
./scripts/deploy/deploy-auto.sh
./scripts/deploy/deploy-filex-amd64-nvidia.sh
```

`deploy-auto.sh` 会在 amd64 + NVIDIA + Docker GPU runtime 可用时进入 GPU 专用脚本；amd64/arm64 无 GPU 时进入 `deploy-filex-cpu.sh`。GPU 专用脚本自包含全流程：前置校验 → 拉代码或 Bamboo current-checkout → 构建（GPU base + CPU base + runtime）→ 迁移 → 启动 → 健康检查 → GPU 验证。

### 前置条件

- 宿主机已安装 **NVIDIA 驱动**（`nvidia-smi` 可用）
- 已安装 **nvidia-container-toolkit**

### 首次部署

```bash
export FILEX_LICENSE_HMAC_SECRET="你的密钥"
./scripts/deploy/deploy-filex-amd64-nvidia.sh
```

### 后续更新

```bash
cd /root/important/FileX/product
git pull origin master
./scripts/deploy/deploy-filex-amd64-nvidia.sh
# 脚本会按指纹自动跳过未变更的镜像，只重建有变更的
```

Bamboo production 路径必须使用 current-checkout，不允许 GPU 下游 fetch/checkout/reset：

```bash
./scripts/deploy/deploy-auto.sh
# 或 GPU 专用：
./scripts/deploy/deploy-filex-amd64-nvidia.sh --current-checkout
```

### GPU 覆盖范围

| 服务 | CPU 模式 | GPU 模式 | 变更 |
|------|---------|---------|------|
| filex-ollama | `ollama/ollama:latest` CPU | 同镜像 + GPU device + `OLLAMA_NUM_PARALLEL_GPU` | compose overlay |
| kb-rerank | `text-embeddings-inference:cpu-1.9.3` | `text-embeddings-inference:1.9.3` + GPU device | compose overlay |
| filex-mineru | `filex/mineru-base:py3.13` 或 `FILEX_MINERU_DEPS_IMAGE` | `filex/mineru-base:py3.13-gpu` 或 `FILEX_MINERU_DEPS_IMAGE` + GPU device | deps base 镜像切换 |
| filex-docling | `filex/docling-base:py3.13` | `filex/docling-base:py3.13-gpu` + GPU device | base 镜像切换 |
| filex / kb-indexer / kb-post / kb-extract | 不变 | 不变 | 不覆盖 |

稳定 deps 镜像只在系统依赖或 PyTorch 配对变化时重建。CPU 基础镜像使用
`docker/Dockerfile.base --target filex-mineru-base`，GPU 基础镜像使用
`docker/Dockerfile.gpu --target filex-mineru-base-gpu`；构建完成后推送到
registry，部署通过 `FILEX_MINERU_DEPS_IMAGE` 拉取。CPU 与 GPU 必须使用不同
stable tag，不可交叉复用。

### 显存与并发调优

```bash
# GPU 模式下 Ollama 并行度（默认 8，按显存调整）
export OLLAMA_NUM_PARALLEL_GPU=8

# 指定 GPU（多卡时）
export CUDA_VISIBLE_DEVICES=0

# 启动（叠加 GPU overlay）
docker compose -f docker/docker-compose.yml -f docker/docker-compose.prod.yml -f docker/docker-compose.gpu.yml up -d --no-build filex-ollama
```

### CPU 模式（无 GPU 服务器）

全量自动部署使用 `deploy-auto.sh` 或 CPU 专用下游；日常 app workers 增量仍使用 `bamboo-compose.sh`：

```bash
./scripts/deploy/deploy-auto.sh
./scripts/deploy/deploy-filex-cpu.sh  # Bamboo/current-checkout 授权路径；人工仅 --check/--dry-run
./scripts/deploy/bamboo-compose.sh build-app-and-up-workers
```

---

## GitHub Packages 核心 CPU 多架构镜像

`filex-app`、`filex-kb-extract`、`filex-postgres` 都是 CPU 服务，公开镜像
统一发布 `linux/amd64` 和 `linux/arm64`，不创建 GPU 变体。发布定义位于
`docker/docker-bake.ghcr.hcl`，基础 target 通过 Bake target context
传给最终镜像，不向 GHCR 公开内部基础镜像。

### 发布顺序

```bash
# 1. 确认源码快照和登录状态
git status --short --branch
export SOURCE_TAG="$(git rev-parse --short=12 HEAD)"
gh auth token | docker login ghcr.io -u roamer-remote --password-stdin

# 2. 先发布不可变版本化标签
docker buildx bake -f docker/docker-bake.ghcr.hcl core-versioned

# 3. 验证三个版本化 OCI indexes
./scripts/release/verify-ghcr-core-multiarch.sh \
  ghcr.io/roamer-remote "${SOURCE_TAG}"

# 4. 对两个平台执行 app、extract、PostgreSQL smoke tests 后，再更新稳定标签
docker buildx bake -f docker/docker-bake.ghcr.hcl core-stable

# 5. 最终验证 GitHub 安装使用的稳定标签
./scripts/release/verify-ghcr-core-multiarch.sh \
  ghcr.io/roamer-remote stable
```

标签映射：

| 镜像 | 版本化标签 | 稳定标签 |
| --- | --- | --- |
| `filex-app` | `<SOURCE_TAG>` | `latest` |
| `filex-kb-extract` | `<SOURCE_TAG>` | `latest` |
| `filex-postgres` | `pg16-zh-<SOURCE_TAG>` | `pg16-zh` |

稳定标签只能在版本化标签的双架构 manifest 与运行 smoke test 都通过后
更新。需要回滚时，用 `docker buildx imagetools create` 将稳定标签重新
指向上一个已验证的版本化标签；不要从本地缓存重建旧版本。
