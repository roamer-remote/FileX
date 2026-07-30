# FileX Docker 安装指南

本仓库是 FileX 的 Docker 发行安装包。它不包含应用源码；安装时通过 Docker Compose 拉取预构建镜像并创建本机数据目录。

## 前置要求

- Docker Desktop 或 Docker Engine
- Docker Compose v2
- arm64 服务器或本机 Docker 环境
- 至少 16 GB 内存；启用 MinerU 文档解析建议 32 GB
- 首次启动需要拉取 Ollama embedding 模型，耗时取决于网络
- 默认 `FILEX_ENV=development` 便于本机试用；生产部署请切到 `production` 并配置授权密钥

如果镜像仓库未公开，需要先登录：

```bash
docker login ghcr.io
```

## 快速安装

```bash
git clone https://github.com/roamer-remote/FileX.git
cd FileX
cp .env.example .env
```

编辑 `.env`，至少修改：

```dotenv
FILEX_BOOTSTRAP_PASSWORD=your-admin-password
FILEX_SECRET_KEY=replace-with-random-secret
FILEX_ASSET_SIGNING_SECRET=replace-with-random-secret
POSTGRES_PASSWORD=replace-with-random-secret
RABBITMQ_DEFAULT_PASS=replace-with-random-secret
```

启动：

```bash
./scripts/install.sh
```

默认访问地址：

```text
http://127.0.0.1:8000
```

初始账号由 `.env` 中的 `FILEX_BOOTSTRAP_USERNAME` 和 `FILEX_BOOTSTRAP_PASSWORD` 决定。

## 常用命令

查看状态：

```bash
./scripts/status.sh
```

查看日志：

```bash
docker compose logs -f filex
docker compose logs -f kb-extract kb-indexer kb-post
```

升级：

```bash
git pull
docker compose pull
docker compose up -d
```

停止：

```bash
docker compose down
```

停止并删除本机数据：

```bash
docker compose down
rm -rf data
```

## 服务器部署

如需让局域网或反向代理访问，在 `.env` 中设置：

```dotenv
FILEX_HOST=0.0.0.0
FILEX_PORT=8000
FILEX_ORIGIN=https://your-domain.example
FILEX_ENV=production
FILEX_LICENSE_HMAC_SECRET=your-license-hmac-secret
```

生产环境建议放在 Nginx / Caddy 后面，由反向代理处理 HTTPS。

## 镜像说明

默认镜像名在 `.env.example` 中定义。当前公开发行包按 arm64 生产环境准备：

```dotenv
FILEX_APP_IMAGE=ghcr.io/roamer-remote/filex-app:${FILEX_VERSION}
FILEX_EXTRACT_IMAGE=ghcr.io/roamer-remote/filex-kb-extract:${FILEX_VERSION}
FILEX_MINERU_IMAGE=ghcr.io/roamer-remote/filex-mineru:${FILEX_VERSION}
FILEX_POSTGRES_IMAGE=ghcr.io/roamer-remote/filex-postgres:pg16-zh
```

如果使用私有镜像仓库，可以在 `.env` 中改成自己的镜像地址。

### NVIDIA GPU MinerU

Linux 主机安装 `nvidia-container-toolkit` 后，可使用 whb GPU 环境构建验证过的
MinerU 镜像。不要把 GPU 镜像覆盖到默认的 ARM64 `latest` 标签；在 `.env`
中单独指定 GPU tag：

```dotenv
FILEX_MINERU_IMAGE=ghcr.io/roamer-remote/filex-mineru:4.0.0a4-gpu
```

然后叠加 GPU Compose 配置：

```bash
docker compose -f docker-compose.yml -f docker-compose.gpu.yml pull filex-mineru
docker compose -f docker-compose.yml -f docker-compose.gpu.yml up -d filex-mineru
docker exec filex-mineru python3 -c 'import torch; assert torch.cuda.is_available(); print(torch.cuda.get_device_name(0))'
docker exec filex-mineru curl -sf http://127.0.0.1:8080/health/models
```

该镜像是 `amd64` GPU 发行包，不能用于 ARM64 主机；ARM64 用户继续使用默认
`ghcr.io/roamer-remote/filex-mineru:latest`。

注意：NVIDIA 驱动可见不等于所有 GPU 都能执行当前 PyTorch CUDA kernel。
例如 GTX 10xx（compute capability 6.1）在当前 `cu126` 运行时可能由 MinerU
自动回退 CPU；如需确认是否真正使用 GPU，应同时检查解析日志中的 GPU fallback。

## Rerank 说明

当前公开 Docker 发行包默认不启动 Cross-Encoder rerank 服务，`KB_RERANK_URL` 为空。语义检索、全文检索与向量检索仍可正常使用。

原因是项目现用的 Hugging Face TEI rerank CPU 镜像没有官方 arm64 镜像；在 arm64 生产环境中默认拉 amd64 仿真服务会增加部署风险。如需接入自建 rerank 服务，可在 `.env` 中设置：

```dotenv
KB_RERANK_URL=http://your-rerank-service/rerank
```

## Docling 说明

当前公开 Docker 发行包默认启用 MinerU 解析链路。Docling 镜像体积较大，暂未作为默认安装服务发布；后续如需启用 Docling，可在单独的 Compose overlay 中接入 `filex-docling` 服务。
