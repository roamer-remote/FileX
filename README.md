# FileX · 企业级 AI 知识管理平台

[![License](https://img.shields.io/badge/license- Proprietary-red)]()
[![React](https://img.shields.io/badge/React-18-61DAFB?logo=react)]()
[![Python](https://img.shields.io/badge/Python-3.12-3776AB?logo=python)]()
[![PostgreSQL](https://img.shields.io/badge/PostgreSQL-16-4169E1?logo=postgresql)]()

> **AI 智能体资料库** — 个人与集团知识空间，RAG 检索、文档提取与向量索引、Wiki 互联、钉技能集成。

---

## 产品概述

FileX 是一个面向团队和个人的 AI 增强型知识管理平台。它将文档管理、语义检索、知识图谱、AI 问答与自动化工作流整合在一起，帮助组织从分散的文件和数据中构建结构化知识资产。

**产品名：钉** · [ding.yyyou.top](https://ding.yyyou.top)

---

## 核心功能

**登录**

支持账号密码登录与企业认证，提供安全的用户鉴权与工作空间切换入口。

<p align="center">
  <img src="screenshots/login.png" alt="登录界面" width="700">
</p>

**知识库总览**

资料库的总体视图，支持自定义维护的目录结构与分类管理。

<p align="center">
  <img src="screenshots/kb.jpg" alt="知识库总览" width="700">
</p>

**知识库管理**

- 多源文档接入：上传、导入、钉消息自动拉取
- 智能文档解析：OCR、版面分析、Markdown / HTML / PDF / Office 全格式支持
- 向量索引：基于 Embedding 的语义检索，支持多种向量模型
- 分块干预：手动调整文档分块策略，覆盖自动分割结果

<p align="center">
  <img src="screenshots/file-preview.png" alt="文档原件预览" width="700">
</p>

**智能体笔记**

文档经过 OCR 或解析处理后生成的 Markdown 笔记，供智能体阅读使用。用户可随时修改、补充内容，类似在线笔记。

<p align="center">
  <img src="screenshots/file-markdown.png" alt="文档识别后的 Agent Markdown" width="700">
</p>

<p align="center">
  <img src="screenshots/kb-overview.jpg" alt="智能体笔记编辑" width="700">
</p>

**RAG 语义检索**

- 混合检索：关键词 + 向量召回，支持重排序
- 文件名称 / ID 精准搜索
- Tag 协同过滤与智能联想
- Wiki 路径感知检索

**Wiki 互联知识网络**

- 自动构建文档间关联图谱
- Wiki 路径导航与上下文感知
- Agent 驱动的知识检索与问答

**AI Agent 与钉技能集成**

- 内置钉技能引擎：会话、工具调用、LangGraph 工作流
- 与钉钉深度集成：消息推送、审批流转、技能触发
- 自定义 Agent：支持 Ollama / OpenAI / Azure 等多种 LLM 后端

**系统管理**

- 工作空间与 ACL 权限体系
- API Key 管理与用量监控
- 系统设置：LLM 配置、模型路由、第三方集成
- 部署健康检查与运维面板

---

## 技术栈

### 前端

| 类别 | 技术 |
|---|---|
| 框架 | React 18 + TypeScript |
| 构建 | Vite 6 |
| 组件库 | Ant Design 5 |
| 状态管理 | Zustand |
| 路由 | React Router 6 |
| 国际化 | i18next |
| 文档预览 | docx-preview, pptx-preview, xlsx, KaTeX |
| 图表 | ECharts |
| HTTP | Axios |

### 后端

| 类别 | 技术 |
|---|---|
| 运行时 | Python 3.12 |
| 框架 | FastAPI |
| 数据库 | PostgreSQL 16 + pgvector |
| AI/ML | LangChain, LLM (OpenAI / Azure / Ollama), Embedding 模型 |
| OCR | Docling, MinerU |
| Agent | LangGraph, 钉技能引擎 |
| 任务队列 | Celery / Redis |
| 搜索 | 混合检索 (BM25 + 向量) |

### 基础设施

- Docker Compose 部署
- MinIO / S3 对象存储
- Nginx 反向代理 + SSL

---

## 架构概览

详细架构说明见 [docs/architecture.md](docs/architecture.md)。

```
用户层  →  SPA (React)  →  API Gateway (Nginx)  →  FastAPI Backend
                                                        ↓
                                              ┌───────────────────┐
                                              │  LLM Router       │
                                              │  Embedding Service │
                                              │  OCR/Extract Pipe  │
                                              │  Agent Engine      │
                                              └───────────────────┘
                                                        ↓
                                              ┌───────────────────┐
                                              │  PostgreSQL        │
                                              │  Redis / Celery    │
                                              │  S3 / MinIO        │
                                              └───────────────────┘
```

---

## 部署

FileX 支持 Docker Compose 一键部署，详细部署指南见项目文档。

### 快速开始

```bash
git clone https://github.com/roamer-remote/filex.git
cd filex

# 查看部署文档了解配置要求
cat docs/deployment.md
```

> 提示：部署需要自行配置 LLM API Key、PostgreSQL 数据库和对象存储。详见部署手册。

---

## 项目状态

FileX 处于活跃开发阶段，功能持续迭代。

---

## 许可证

本项目为专有软件，保留所有权利。
