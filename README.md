# FileX · Enterprise-Grade AI Knowledge Platform

[![React](https://img.shields.io/badge/React-18-61DAFB?logo=react)]()
[![Python](https://img.shields.io/badge/Python-3.12-3776AB?logo=python)]()
[![PostgreSQL](https://img.shields.io/badge/PostgreSQL-16-4169E1?logo=postgresql)]()

> **AI Knowledge Base for Agents** — Document management, RAG retrieval, multi-engine OCR (Docling/MinerU), vector search, wiki graph, and Agent skill integration.
>
> **AI 智能体资料库** — 个人与集团知识空间，RAG 检索、文档提取与向量索引、Wiki 互联、钉技能集成。

[**中文版**](README.zh-CN.md) · [English](README.md)

---

## Table of Contents

- [Product Overview](#product-overview)
- [Highlights](#highlights)
- [Core Features](#core-features)
  - [Login](#login)
  - [Knowledge Base Overview](#kb-overview-en)
  - [Knowledge Base Management](#kb-management-en)
    - [File List](#file-list)
    - [File Preview](#file-preview)
    - [Agent Notes](#agent-note)
    - [OKF Interop](#okf)
    - [Pipeline Trace](#process-trace)
    - [Multi-Engine Processing](#multi-process)
    - [RAPTOR Post-Processing](#raptor)
    - [Knowledge Base Analytics](#kb-analysis)
      - [Overview Metrics](#kb-metrics)
      - [Document Relation Graph](#wiki-graph)
      - [Tag Heatmap](#tag-heatmap)
  - [Pipeline Visualization](#process-viz-en)
  - [Agent Call Trace](#agent-trace-en)
  - [System Settings](#settings-en)
  - [Help Documentation](#help-docs-en)
- [Tech Stack](#tech-stack)
  - [Frontend](#frontend)
  - [Backend](#backend)
  - [Infrastructure](#infrastructure)
- [Architecture](#architecture)
- [Deployment](#deployment)
  - [Quick Start](#quick-start)
- [Project Status](#project-status)
- [License](#license)

---

## <a id="product-overview"></a>Product Overview [↑](#table-of-contents)

FileX is an AI-augmented knowledge management platform for teams and individuals. It integrates document management, semantic retrieval, knowledge graphs, AI Q&A, and automated workflows to help organizations turn scattered files and data into structured knowledge assets.

**Product Name: Ding** — FileX website, the Agent skill is called Ding

**Live Demo**: [ding.yyyou.top](https://ding.yyyou.top) — For evaluation only. Do not upload sensitive data. The database may be reset at any time; please keep backups.

**Contact**: WeChat `roamerxv` · Email [roamerxv@163.com](mailto:roamerxv@163.com)

---

## <a id="highlights"></a>Highlights [↑](#table-of-contents)

- **Multi-Engine Document Pipeline** — [Docling](https://github.com/IBM/docling) (IBM), [MinerU](https://github.com/opendatalab/MinerU) (OpenDataLab), and Insavlo engines auto-route by document type, covering Office, PDF, images and more. The full pipeline is visualized end-to-end.
- **RAPTOR Hierarchical Retrieval** — Stanford University's [RAPTOR algorithm](https://arxiv.org/abs/2401.18059) recursively summarizes indexed documents into a tree structure, significantly improving long-document and multi-document retrieval accuracy.
- **Document Relation Graph** — Using [Andrej Karpathy's knowledge base](https://github.com/karpathy) as an example, automatically builds citation and tag relationship networks to visualize knowledge topology and uncover implicit connections.
- **Editable Agent Notes** — OCR and parsing results are automatically formatted into structured Markdown notes for direct Agent consumption. Users can edit and enrich them on the fly.
- **One-Click Cross-Platform Deployment** — Docker Compose brings up all dependencies (PostgreSQL, RabbitMQ, Redis, Ollama) on macOS, Linux, and Windows.
- **Hot-Pluggable Configuration** — LLM routing, embedding engines, parsing strategies and more are centrally managed; changes take effect instantly with no service restart.

---

## <a id="core-features"></a>Core Features [↑](#table-of-contents)

<a id="login"></a>**Login** [↑](#table-of-contents)

Password and enterprise authentication with secure workspace switching.

<p align="center">
  <img src="screenshots/login.png" alt="Login" width="700">
</p>

<a id="kb-overview-en"></a>**Knowledge Base Overview** [↑](#table-of-contents)

Full view of your knowledge base with customizable directory structures and categories.

<p align="center">
  <img src="screenshots/kb.jpg" alt="Knowledge Base Overview" width="700">
</p>

<a id="kb-management-en"></a>**Knowledge Base Management** [↑](#table-of-contents)

<a id="file-list"></a>- Browse all uploaded files [↑](#table-of-contents)

<p align="center">
  <img src="screenshots/kb-overview.jpg" alt="File List" width="700">
</p>

<a id="file-preview"></a>- Preview file originals [↑](#table-of-contents)

<p align="center">
  <img src="screenshots/file-preview.png" alt="File Preview" width="700">
</p>

<a id="agent-note"></a>- Agent Notes: OCR'd documents become structured Markdown for Agents to read. Users can edit and extend them like online notes. [↑](#table-of-contents)

<p align="center">
  <img src="screenshots/file-markdown.png" alt="Agent Markdown" width="700">
</p>

<a id="okf"></a>- OKF Interop: Import, export, and validate Google OKF (Open Knowledge Format) bundles for cross-platform knowledge asset exchange. [↑](#table-of-contents)

<p align="center">
  <img src="screenshots/file-okf.png" alt="OKF Import/Export" width="700">
</p>

<a id="process-trace"></a>- Pipeline Trace: End-to-end visibility from upload through OCR, vector indexing, to search. Every stage status is inspectable and replayable. [↑](#table-of-contents)

<p align="center">
  <img src="screenshots/file-show-process.png" alt="Pipeline Trace" width="700">
</p>

<a id="multi-process"></a>- Multi-Engine Processing: Docling, MinerU, and Insavlo engines with configurable chunking strategies. Supports per-file re-extraction and re-indexing. [↑](#table-of-contents)

<p align="center">
  <img src="screenshots/file-multi-redo.png" alt="Multi-Engine Processing" width="700">
</p>

<p align="center">
  <img src="screenshots/multi-processor.png" alt="Processing Engines" width="700">
</p>

<a id="raptor"></a>- RAPTOR Post-Processing: Stanford's RAPTOR recursively summarizes indexed documents into a tree for hierarchical retrieval, boosting recall on long and multi-document queries. [↑](#table-of-contents)

<p align="center">
  <img src="screenshots/raptor.png" alt="RAPTOR" width="700">
</p>

<a id="kb-analysis"></a>- Knowledge Base Analytics [↑](#table-of-contents)
  <a id="kb-metrics"></a>  - Overview: Inspect file inventory, index status, and retrieval quality. [↑](#table-of-contents)

<p align="center">
  <img src="screenshots/kb-overview.png" alt="KB Analytics" width="700">
</p>

  <a id="wiki-graph"></a>  - Document Relation Graph: Auto-build citation and tag networks. Visualize knowledge topology and detect isolated assets. [↑](#table-of-contents)

<p align="center">
  <img src="screenshots/wiki-relation.png" alt="Wiki Relation Graph" width="700">
</p>

  <a id="tag-heatmap"></a>  - Tag Heatmap: Tag frequency and co-occurrence visualized as a heatmap to reveal topic distribution and blind spots. [↑](#table-of-contents)

<p align="center">
  <img src="screenshots/tag.png" alt="Tag Heatmap" width="700">
</p>

<a id="process-viz-en"></a>**Pipeline Visualization** [↑](#table-of-contents)

Real-time dashboard of the document processing pipeline — upload, extraction, indexing, and search — with stage-level status and timing. Supports manual retry, dead-letter queue drain, and index rebuild for operations.

<p align="center">
  <img src="screenshots/prcess-view.png" alt="Pipeline Dashboard" width="700">
</p>

<a id="agent-trace-en"></a>**Agent Call Trace** [↑](#table-of-contents)

Full trace of Agent inference requests: input, reasoning steps, tool calls, and final output. Navigate by session to debug and evaluate Agent behavior.

<p align="center">
  <img src="screenshots/agent-log-1.png" alt="Agent Log" width="700">
</p>

<p align="center">
  <img src="screenshots/agent-log-2.png" alt="Agent Trace Detail" width="700">
</p>

<a id="settings-en"></a>**System Settings** [↑](#table-of-contents)

Centralized configuration for LLM routing, embedding engines, parsing strategies, caching rules, and more. Changes apply instantly — no restart required. Hot-plug between Ollama, OpenAI, Azure, and other backends.

<p align="center">
  <img src="screenshots/params.png" alt="System Settings" width="700">
</p>

<a id="help-docs-en"></a>**Help Documentation** [↑](#table-of-contents)

Built-in help system covering everything from getting started to advanced operations — file management, retrieval tuning, Agent skill development, system configuration, and more. Full-text search and version-aware.

<p align="center">
  <img src="screenshots/help.png" alt="Help Documentation" width="700">
</p>

---

## <a id="tech-stack"></a>Tech Stack [↑](#table-of-contents)

### <a id="frontend"></a>Frontend [↑](#table-of-contents)

| Category | Technology |
|----------|------------|
| Framework | React 18 + TypeScript |
| Build | Vite 6 |
| Components | Ant Design 5 |
| State | Zustand |
| Routing | React Router 6 |
| i18n | i18next |
| Document Preview | docx-preview, pptx-preview, xlsx, KaTeX |
| Charts | ECharts |
| HTTP | Axios |

### <a id="backend"></a>Backend [↑](#table-of-contents)

| Category | Technology |
|----------|------------|
| Runtime | Python 3.12 |
| Framework | FastAPI |
| Database | PostgreSQL 16 + pgvector |
| AI/ML | LangChain, LLM (OpenAI / Azure / Ollama), Embedding models |
| OCR | Docling, MinerU |
| Agent | LangGraph, Ding Skill Engine |
| Task Queue | Celery / Redis |
| Search | Hybrid (BM25 + vector) |

### <a id="infrastructure"></a>Infrastructure [↑](#table-of-contents)

- Docker Compose deployment
- MinIO / S3 object storage
- Nginx reverse proxy + SSL

---

## <a id="architecture"></a>Architecture [↑](#table-of-contents)

See [docs/architecture.md](docs/architecture.md) for details.

```
User Layer  →  SPA (React)  →  API Gateway (Nginx)  →  FastAPI Backend
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

## <a id="deployment"></a>Deployment [↑](#table-of-contents)

FileX runs on Docker Compose and supports **macOS, Linux, and Windows**. A single server runs the full stack including PostgreSQL, RabbitMQ, Redis, and Ollama. NVIDIA GPU acceleration is available for OCR and embedding inference.

<p align="center">
  <img src="screenshots/docker.png" alt="Docker Deployment" width="700">
</p>

### <a id="quick-start"></a>Quick Start [↑](#table-of-contents)

```bash
git clone https://github.com/roamer-remote/filex.git
cd filex

# See deployment docs for configuration requirements
cat docs/deployment.md
```

> You will need to configure LLM API keys, a PostgreSQL database, and object storage. See the deployment manual for details.

---

## <a id="project-status"></a>Project Status [↑](#table-of-contents)

FileX is under active development with continuous feature iteration.

---

## <a id="license"></a>License [↑](#table-of-contents)

Proprietary software. All rights reserved.
