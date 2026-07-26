# FileX Docker 安装指南

本仓库是 FileX 的 Docker 发行安装包。它不包含应用源码；安装时通过 Docker Compose 拉取预构建镜像并创建本机数据目录。

## 前置要求

- Docker Desktop 或 Docker Engine
- Docker Compose v2
- 至少 16 GB 内存；启用 MinerU / Docling 文档解析建议 32 GB
- 首次启动需要拉取 Ollama embedding 模型，耗时取决于网络
- 默认 `FILEX_ENV=development` 便于本机试用；生产部署请切到 `production` 并配置授权密钥

如果镜像仓库未公开，需要先登录：

```bash
docker login ghcr.io
```

## 快速安装

```bash
git clone https://github.com/roamer-remote/filex.git
cd filex
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

默认镜像名在 `.env.example` 中定义：

```dotenv
FILEX_APP_IMAGE=ghcr.io/roamer-remote/filex-app:${FILEX_VERSION}
FILEX_EXTRACT_IMAGE=ghcr.io/roamer-remote/filex-kb-extract:${FILEX_VERSION}
FILEX_MINERU_IMAGE=ghcr.io/roamer-remote/filex-mineru:${FILEX_VERSION}
FILEX_DOCLING_IMAGE=ghcr.io/roamer-remote/filex-docling:${FILEX_VERSION}
FILEX_POSTGRES_IMAGE=ghcr.io/roamer-remote/filex-postgres:pg16-zh
FILEX_RERANK_IMAGE=ghcr.io/roamer-remote/filex-rerank:cpu-1.5
```

如果使用私有镜像仓库，可以在 `.env` 中改成自己的镜像地址。
