# FileX · 企业级 AI 知识管理平台

[![React](https://img.shields.io/badge/React-18-61DAFB?logo=react)]()
[![Python](https://img.shields.io/badge/Python-3.12-3776AB?logo=python)]()
[![PostgreSQL](https://img.shields.io/badge/PostgreSQL-16-4169E1?logo=postgresql)]()

> **AI 智能体资料库** — 个人与集团知识空间，RAG 检索、文档提取与向量索引、Wiki 互联、钉技能集成。

---

## 目录

- [产品概述](#产品概述)
- [核心功能](#核心功能)
  - [登录](#login)
  - [知识库总览](#kb-overview)
  - [知识库管理](#kb-management)
    - [原始资料列表](#file-list)
    - [原件预览](#file-preview)
    - [智能体笔记](#agent-note)
    - [OKF 互操作](#okf)
    - [流程追踪](#process-trace)
    - [多样处理与重新索引](#multi-process)
    - [RAPTOR 后处理](#raptor)
    - [知识库多维度分析](#kb-analysis)
      - [查看知识库整体概况](#kb-metrics)
      - [文档关联图谱](#wiki-graph)
      - [标签热点分析](#tag-heatmap)
  - [处理过程可视化](#process-viz)
  - [智能体调用追踪](#agent-trace)
  - [系统配置中心](#settings)
  - [在线帮助文档](#help-docs)
- [技术栈](#技术栈)
  - [前端](#前端)
  - [后端](#后端)
  - [基础设施](#基础设施)
- [架构概览](#架构概览)
- [部署](#部署)
  - [快速开始](#快速开始)
- [项目状态](#项目状态)
- [许可证](#许可证)

## 产品概述 [↑](#目录)

FileX 是一个面向团队和个人的 AI 增强型知识管理平台。它将文档管理、语义检索、知识图谱、AI 问答与自动化工作流整合在一起，帮助组织从分散的文件和数据中构建结构化知识资产。

**产品名：钉** · [ding.yyyou.top](https://ding.yyyou.top)

---

## 核心功能 [↑](#目录)

<a id="login"></a>**登录** [↑](#目录)

支持账号密码登录与企业认证，提供安全的用户鉴权与工作空间切换入口。

<p align="center">
  <img src="screenshots/login.png" alt="登录界面" width="700">
</p>

<a id="kb-overview"></a>**知识库总览** [↑](#目录)

资料库的总体视图，支持自定义维护的目录结构与分类管理。

<p align="center">
  <img src="screenshots/kb.jpg" alt="知识库总览" width="700">
</p>

<a id="kb-management"></a>**知识库管理** [↑](#目录)

<a id="file-list"></a>- 显示用户所有的上传的原始资料列表 [↑](#目录)

<p align="center">
  <img src="screenshots/kb-overview.jpg" alt="原始资料列表" width="700">
</p>

<a id="file-preview"></a>- 预览资料的原始内容 [↑](#目录)

<p align="center">
  <img src="screenshots/file-preview.png" alt="文档原件预览" width="700">
</p>

<a id="agent-note"></a>- 智能体笔记：文档经过 OCR 或解析处理后生成的 Markdown 笔记，供智能体阅读使用。用户可随时修改、补充内容，类似在线笔记。 [↑](#目录)

<p align="center">
  <img src="screenshots/file-markdown.png" alt="文档识别后的 Agent Markdown" width="700">
</p>

<a id="okf"></a>- OKF 互操作：支持 Google OKF（Open Knowledge Format）规范的导入、导出与校验，实现跨平台知识资产交换。 [↑](#目录)

<p align="center">
  <img src="screenshots/file-okf.png" alt="OKF 导入导出" width="700">
</p>

<a id="process-trace"></a>- 流程追踪：文档从上传、OCR 解析、向量索引到检索匹配的完整流水线，每个环节的状态均可实时查看与回溯。 [↑](#目录)

<p align="center">
  <img src="screenshots/file-show-process.png" alt="流程追踪" width="700">
</p>

<a id="multi-process"></a>- 多样处理与重新索引：支持 Docling、MinerU、Insavlo 等多套解析引擎，可根据文档类型灵活路由；分块策略可调，支持对指定文件重新提取与索引。 [↑](#目录)

<p align="center">
  <img src="screenshots/file-multi-redo.png" alt="多样处理" width="700">
</p>

<p align="center">
  <img src="screenshots/multi-processor.png" alt="多种处理方法" width="700">
</p>

<a id="raptor"></a>- RAPTOR 后处理：采用斯坦福 RAPTOR 算法对已索引文档进行递归抽象与分层摘要，构建树形语义结构，提升长文档与多文档场景下的检索精度与知识库质量。 [↑](#目录)

<p align="center">
  <img src="screenshots/raptor.png" alt="RAPTOR 后处理" width="700">
</p>

<a id="kb-analysis"></a>- 知识库多维度分析 [↑](#目录)
  <a id="kb-metrics"></a>  - 查看知识库整体概况：从文件列表、索引状态、检索质量等多角度审视知识库，辅助评估与优化知识资产结构。 [↑](#目录)

<p align="center">
  <img src="screenshots/kb-overview.png" alt="知识库多维分析" width="700">
</p>

  <a id="wiki-graph"></a>  - 文档关联图谱：以 Andrej Karpathy 资料库为例，自动构建文档间的引用与标签关系网络，可视化知识单元的拓扑连接，辅助发现隐式关联与知识孤岛。 [↑](#目录)

<p align="center">
  <img src="screenshots/wiki-relation.png" alt="Wiki 关系图" width="700">
</p>

  <a id="tag-heatmap"></a>  - 标签热点分析：基于文档标签的使用频率与关联强度生成标签云与热点图，直观呈现知识库的主题分布，辅助快速定位高频话题与内容盲区。 [↑](#目录)

<p align="center">
  <img src="screenshots/tag.png" alt="标签热点图" width="700">
</p>

<a id="process-viz"></a>**处理过程可视化** [↑](#目录)

文档处理流水线的全程可视化看板，实时展示上传、提取、索引、检索等各环节的状态与耗时。支持对异常任务进行手动重试、死信队列排空与索引重建，帮助运维人员快速定位瓶颈与修复故障。

<p align="center">
  <img src="screenshots/prcess-view.png" alt="处理过程可视化" width="700">
</p>

<a id="agent-trace"></a>**智能体调用追踪** [↑](#目录)

智能体请求的完整调用链路追踪，记录每次 Agent 推理的输入、中间思考、工具调用及最终输出。支持按会话回溯执行过程，便于调试与效果评估。

<p align="center">
  <img src="screenshots/agent-log-1.png" alt="智能体调用日志" width="700">
</p>

<p align="center">
  <img src="screenshots/agent-log-2.png" alt="智能体调用详情" width="700">
</p>

<a id="settings"></a>**系统配置中心** [↑](#目录)

所有系统参数集中管理，涵盖 LLM 模型路由、嵌入引擎、解析策略、缓存规则等模块。配置变更即时生效，无需重启服务或重新部署，支持热插拔式切换后端服务（Ollama / OpenAI / Azure 等）。

<p align="center">
  <img src="screenshots/params.png" alt="系统配置中心" width="700">
</p>

<a id="help-docs"></a>**在线帮助文档** [↑](#目录)

内置完善的帮助系统，覆盖从入门到高级运维的全部操作指引，包括资料管理、检索调优、Agent 技能开发、系统配置等主题。支持全文搜索与版本对照，用户可随时查阅，降低学习与运维门槛。

<p align="center">
  <img src="screenshots/help.png" alt="在线帮助文档" width="700">
</p>

---

## 技术栈 [↑](#目录)

### 前端 [↑](#目录)

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

### 后端 [↑](#目录)

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

### 基础设施 [↑](#目录)

- Docker Compose 部署
- MinIO / S3 对象存储
- Nginx 反向代理 + SSL

---

## 架构概览 [↑](#目录)

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

## 部署 [↑](#目录)

FileX 基于 Docker Compose 构建，支持 **macOS、Linux、Windows** 跨平台部署。单服务器即可运行完整知识管理服务，含 PostgreSQL、RabbitMQ、Redis、Ollama 等全部依赖。支持 NVIDIA GPU 加速 OCR 与嵌入推理。

<p align="center">
  <img src="screenshots/docker.png" alt="Docker 部署" width="700">
</p>

### 快速开始 [↑](#目录)

```bash
git clone https://github.com/roamer-remote/filex.git
cd filex

# 查看部署文档了解配置要求
cat docs/deployment.md
```

> 提示：部署需要自行配置 LLM API Key、PostgreSQL 数据库和对象存储。详见部署手册。

---

## 项目状态 [↑](#目录)

FileX 处于活跃开发阶段，功能持续迭代。

---

## 许可证 [↑](#目录)

本项目为专有软件，保留所有权利。
