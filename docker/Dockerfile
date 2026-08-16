# ============================================================
# Stage 1: 构建前端
# ============================================================
# 前端为 React 19 + Vite（frontend/ 内 npm run build 产出 dist）
# 国内构建可在 compose 中指定镜像加速前缀，避免失效的 registry-mirrors（如 USTC）
# 用于 FROM 的 ARG 必须写在第一个 FROM 之前（多阶段共用）
ARG NODE_IMAGE=node:20-alpine
ARG PYTHON_IMAGE=python:3.13-slim
ARG APP_BASE_IMAGE=filex-app-base

FROM ${NODE_IMAGE} AS build-frontend

ARG BUILD_HTTP_PROXY=
ARG NPM_REGISTRY=https://registry.npmmirror.com

WORKDIR /build

ENV HTTP_PROXY=${BUILD_HTTP_PROXY} \
    HTTPS_PROXY=${BUILD_HTTP_PROXY} \
    NO_PROXY=localhost,127.0.0.1,.local,.internal,host.docker.internal

# 前端 npm 默认走国内镜像；可通过 NPM_REGISTRY 覆盖
RUN npm config set registry "${NPM_REGISTRY}" && \
    npm config set replace-registry-host always

COPY frontend/package.json frontend/package-lock.json ./
RUN npm ci

COPY frontend/ .
ARG VITE_APP_BUILD_VERSION=
ENV VITE_APP_BUILD_VERSION=$VITE_APP_BUILD_VERSION
RUN npm run build

# ============================================================
# Stage 2: 运行后端（基础依赖见 docker/Dockerfile.base → filex-app-base）
# ============================================================
FROM ${APP_BASE_IMAGE}

# libreoffice-impress 已移入 docker/Dockerfile.base → filex-app-base，避免 --no-cache 每次 apt-get
WORKDIR /app

# 复制后端代码
COPY backend/ .

# FileX 技能包（GET /filex-skill-update）
COPY skill/ding /app/skill/ding

# MCP 唯一源码（GET /filex-skill-agent-update 的自包含 agent zip）
COPY integrations/filex-mcp-server/src/filex_mcp_server /app/integrations/filex-mcp-server/src/filex_mcp_server

# 复制前端构建产物（后端会自动挂载此目录提供静态文件）
COPY --from=build-frontend /build/dist /frontend/dist

# 创建数据目录
RUN mkdir -p /app/uploads /app/logs

# 默认环境变量（可在 docker-compose 中覆盖）
ENV DATABASE_URL=postgresql://filebox:filebox@postgres:5432/filebox
ENV UPLOAD_DIR=/app/uploads
ENV PYTHONPATH=/app
ENV FILEX_REPOSITORY_ROOT=/app
ENV FILEX_LOG_TIMEZONE=Asia/Shanghai

# 暴露端口
EXPOSE 8000

# 启动服务（先运行数据库迁移再启动应用）
CMD ["sh", "-c", "python -c \"from database import wait_for_database; wait_for_database()\" && alembic upgrade head && uvicorn main:app --host 0.0.0.0 --port 8000"]
