# Copyright (c) 2026 徐泽宇
"""config 模块。

Authors:
    徐泽宇
"""

import os

BASE_DIR = os.path.dirname(os.path.abspath(__file__))

_DEFAULT_DATABASE_URL = "postgresql://filebox:filebox@127.0.0.1:5432/filebox"
DATABASE_URL = os.environ.get("DATABASE_URL") or _DEFAULT_DATABASE_URL

if DATABASE_URL.startswith("sqlite"):
    raise RuntimeError(
        "FileX 已不再支持 SQLite。请设置 DATABASE_URL 为 PostgreSQL，"
        f"例如：{_DEFAULT_DATABASE_URL}"
    )
if not DATABASE_URL.startswith("postgresql"):
    raise RuntimeError("DATABASE_URL 须为 PostgreSQL 连接串（postgresql://…）")

# SQLAlchemy QueuePool（默认 5+10；生产 filex API 经 compose 放大，见 docker-compose.yml）
DATABASE_POOL_SIZE = max(1, int(os.environ.get("DATABASE_POOL_SIZE") or "5"))
DATABASE_MAX_OVERFLOW = max(0, int(os.environ.get("DATABASE_MAX_OVERFLOW") or "10"))
DATABASE_POOL_TIMEOUT = max(1.0, float(os.environ.get("DATABASE_POOL_TIMEOUT") or "30"))

# 资料库向量索引（仅 Ollama /api/embeddings，禁止 chat/generate）
OLLAMA_BASE_URL = (os.environ.get("OLLAMA_BASE_URL") or "http://filex-ollama:11434").rstrip("/")
OLLAMA_EMBED_MODEL = os.environ.get("OLLAMA_EMBED_MODEL") or "bge-m3:latest"
OLLAMA_TIMEOUT_SEC = float(os.environ.get("OLLAMA_TIMEOUT_SEC") or "120")
# 单次 /api/embed 请求的文本条数上限；大文档分多批避免 ReadTimeout
OLLAMA_EMBED_BATCH_SIZE = max(1, int(os.environ.get("OLLAMA_EMBED_BATCH_SIZE") or "8"))
OLLAMA_EMBED_DIM = int(os.environ.get("OLLAMA_EMBED_DIM") or "1024")
KB_VECTOR_BACKEND = (os.environ.get("KB_VECTOR_BACKEND") or "pgvector").strip().lower()
OLLAMA_EMBED_MAX_CHARS = max(1, int(os.environ.get("OLLAMA_EMBED_MAX_CHARS") or "8192"))
# 061 P0-A：embed 输入向量缓存（P0-C 再暴露 Settings UI）
KB_EMBED_CACHE_ENABLED = (os.environ.get("KB_EMBED_CACHE_ENABLED") or "1").strip().lower() in (
    "1",
    "true",
    "yes",
)
KB_RAPTOR_USE_EMBED_CACHE = (os.environ.get("KB_RAPTOR_USE_EMBED_CACHE") or "0").strip().lower() in (
    "1",
    "true",
    "yes",
)
OLLAMA_CHAT_MODEL = os.environ.get("OLLAMA_CHAT_MODEL") or "qwen3.5:cloud"
# 030 P3：kb-indexer 可选 Ollama 结构化实体 JSON 抽取（默认关；非用户 Chat）
KB_ENTITY_EXTRACT_ENABLED = (os.environ.get("KB_ENTITY_EXTRACT_ENABLED") or "0").strip().lower() in (
    "1",
    "true",
    "yes",
)
KB_CHUNK_SIZE = int(os.environ.get("KB_CHUNK_SIZE") or "800")
KB_CHUNK_OVERLAP = int(os.environ.get("KB_CHUNK_OVERLAP") or "100")
KB_INDEX_CONCURRENCY = int(os.environ.get("KB_INDEX_CONCURRENCY") or "2")
OLLAMA_EMBED_CONCURRENCY = max(1, int(os.environ.get("OLLAMA_EMBED_CONCURRENCY") or "4"))
OLLAMA_NUM_PARALLEL = max(1, int(os.environ.get("OLLAMA_NUM_PARALLEL") or "4"))
KB_INDEX_POLL_SEC = float(os.environ.get("KB_INDEX_POLL_SEC") or "2")

RABBITMQ_URL = (os.environ.get("RABBITMQ_URL") or "").strip()
MQ_STATUS_WATCH_INTERVAL_SEC = float(os.environ.get("MQ_STATUS_WATCH_INTERVAL_SEC") or "3")
KB_INDEX_REPLAY_INTERVAL_SEC = float(os.environ.get("KB_INDEX_REPLAY_INTERVAL_SEC") or "60")
# 仅重发在库中 queued 且超过该秒数未更新的任务，避免周期性全量重发导致队列爆炸
KB_INDEX_REPLAY_STALE_SEC = float(os.environ.get("KB_INDEX_REPLAY_STALE_SEC") or "180")
# running 超过该秒数未 heartbeat 视为 stale；大文档 embed 可达 30–40min（097 默认 1h）
KB_INDEX_RUNNING_STALE_SEC = float(os.environ.get("KB_INDEX_RUNNING_STALE_SEC") or "3600")
KB_POST_CONCURRENCY = int(os.environ.get("KB_POST_CONCURRENCY") or "1")
KB_POST_REPLAY_INTERVAL_SEC = float(os.environ.get("KB_POST_REPLAY_INTERVAL_SEC") or "60")
KB_POST_REPLAY_STALE_SEC = float(os.environ.get("KB_POST_REPLAY_STALE_SEC") or "180")
KB_POST_RUNNING_STALE_SEC = float(os.environ.get("KB_POST_RUNNING_STALE_SEC") or "3600")
KB_VECTOR_UPSERT_BATCH_SIZE = max(
    32,
    min(2000, int(os.environ.get("KB_VECTOR_UPSERT_BATCH_SIZE") or "256")),
)
KB_SEARCH_TOP_K_DEFAULT = 8
KB_SEARCH_TOP_K_MAX = 50
TAG_COOC_MIN_EDGE_DEFAULT = int(os.environ.get("FILEX_TAG_COOC_MIN_EDGE") or "2")

# 每知识空间文件夹树最大深度（根目录为第 1 级）
FOLDER_MAX_DEPTH = max(1, int(os.environ.get("FOLDER_MAX_DEPTH") or "10"))

# 资料库报告：低于该文件数同步 refresh，否则 BackgroundTasks 异步
LIBRARY_REPORT_SYNC_THRESHOLD = max(1, int(os.environ.get("LIBRARY_REPORT_SYNC_THRESHOLD") or "500"))

# 智能体枚举：单空间 layout / files 全量上限（防 OOM）
AGENT_LAYOUT_MAX_FILES = max(100, int(os.environ.get("AGENT_LAYOUT_MAX_FILES") or "5000"))
AGENT_ENUMERATE_MAX_FILES = max(100, int(os.environ.get("AGENT_ENUMERATE_MAX_FILES") or "5000"))
# API Key 调用 GET /api/files 时 page_size 上限（Web JWT 仍为 100）
AGENT_FILES_PAGE_SIZE_MAX = max(100, int(os.environ.get("AGENT_FILES_PAGE_SIZE_MAX") or "500"))
# 余弦相似度下限（0 关闭）；低于该值的纯向量命中会被过滤，FTS 命中仍保留
KB_SEARCH_MIN_SCORE = float(os.environ.get("KB_SEARCH_MIN_SCORE") or "0.35")
# boost_keywords 命中每条关键词的加分上限（累计 capped 0.25）
KB_SEARCH_BOOST_KEYWORD_BONUS = float(os.environ.get("KB_SEARCH_BOOST_KEYWORD_BONUS") or "0.12")
# MMR 多样性：1.0 只看相关度，0.0 只看差异；0 关闭 MMR
KB_SEARCH_MMR_LAMBDA = float(os.environ.get("KB_SEARCH_MMR_LAMBDA") or "0.7")
# 文件名子串命中加分；0 关闭
KB_SEARCH_FILENAME_BOOST = float(os.environ.get("KB_SEARCH_FILENAME_BOOST") or "0.20")
# content_kind 模态意图加权；0 关闭
KB_SEARCH_MODALITY_BOOST = float(os.environ.get("KB_SEARCH_MODALITY_BOOST") or "0.15")
# 短查询（无空格且长度≤该值）须在 chunk 正文或文件名中出现，避免纯向量误召回
KB_SEARCH_KEYWORD_GUARD_MAX_LEN = int(os.environ.get("KB_SEARCH_KEYWORD_GUARD_MAX_LEN") or "16")
# 仅用于 Alembic 迁移种子；运行期开关见 system_settings.kb_search_hybrid_enabled
KB_SEARCH_HYBRID = (os.environ.get("KB_SEARCH_HYBRID") or "1").strip().lower() in ("1", "true", "yes")
KB_CHUNK_USE_STRUCTURE = (os.environ.get("KB_CHUNK_USE_STRUCTURE") or "1").strip().lower() in ("1", "true", "yes")
# FTS：zh_cn（zhparser）或 simple；运行期可被 system_settings.kb_fts_config 覆盖
KB_FTS_CONFIG = (os.environ.get("KB_FTS_CONFIG") or "zh_cn").strip().lower()
# 超过该长度的查询在 hybrid FTS 中跳过整句 plainto_tsquery，仅用 extract_query_terms OR
KB_FTS_LONG_QUERY_LEN = max(1, int(os.environ.get("KB_FTS_LONG_QUERY_LEN") or "10"))


# KB 正文提取（kb-extract worker，无 LLM）
KB_EXTRACT_CONCURRENCY = int(os.environ.get("KB_EXTRACT_CONCURRENCY") or "1")
KB_EXTRACT_MAX_ATTEMPTS = int(os.environ.get("KB_EXTRACT_MAX_ATTEMPTS") or "3")
KB_EXTRACT_REPLAY_INTERVAL_SEC = float(os.environ.get("KB_EXTRACT_REPLAY_INTERVAL_SEC") or "60")
KB_EXTRACT_REPLAY_STALE_SEC = float(os.environ.get("KB_EXTRACT_REPLAY_STALE_SEC") or "180")
KB_EXTRACT_RUNNING_STALE_SEC = float(os.environ.get("KB_EXTRACT_RUNNING_STALE_SEC") or "3600")
KB_EXTRACT_PDF_DPI = int(os.environ.get("KB_EXTRACT_PDF_DPI") or "200")
KB_EXTRACT_MAX_PAGES = int(os.environ.get("KB_EXTRACT_MAX_PAGES") or "500")
KB_PDF_INSPECTOR_ENABLED = (os.environ.get("KB_PDF_INSPECTOR_ENABLED") or "0").strip().lower() in (
    "1",
    "true",
    "yes",
)
KB_PDF_INSPECTOR_MODE = (os.environ.get("KB_PDF_INSPECTOR_MODE") or "off").strip().lower()
if KB_PDF_INSPECTOR_MODE not in {"off", "detect-only", "extract"}:
    KB_PDF_INSPECTOR_MODE = "off"
KB_PDF_INSPECTOR_MIN_CONFIDENCE = float(
    os.environ.get("KB_PDF_INSPECTOR_MIN_CONFIDENCE") or "0.90"
)
KB_PDF_INSPECTOR_TIMEOUT_SEC = float(
    os.environ.get("KB_PDF_INSPECTOR_TIMEOUT_SEC") or "120"
)
KB_EXTRACT_PAGE_TIMEOUT_SEC = float(os.environ.get("KB_EXTRACT_PAGE_TIMEOUT_SEC") or "120")
KB_EXTRACT_JOB_TIMEOUT_SEC = float(os.environ.get("KB_EXTRACT_JOB_TIMEOUT_SEC") or "3600")
KB_EXTRACT_LO_TIMEOUT_SEC = float(os.environ.get("KB_EXTRACT_LO_TIMEOUT_SEC") or "300")
KB_OCR_ENGINE = (os.environ.get("KB_OCR_ENGINE") or "rapid").strip().lower()
_KB_OCR_PDF_DPI_RAW = (os.environ.get("KB_OCR_PDF_DPI") or "").strip()
KB_OCR_PDF_DPI: int | None = (
    int(_KB_OCR_PDF_DPI_RAW) if _KB_OCR_PDF_DPI_RAW.isdigit() else None
)
KB_OCR_PREPROCESS_ENABLED = (os.environ.get("KB_OCR_PREPROCESS_ENABLED") or "0").strip().lower() in (
    "1",
    "true",
    "yes",
)
KB_OCR_PREPROCESS_ROTATE = (os.environ.get("KB_OCR_PREPROCESS_ROTATE") or "0").strip().lower() in (
    "1",
    "true",
    "yes",
)
KB_OCR_PREPROCESS_DESKEW = (os.environ.get("KB_OCR_PREPROCESS_DESKEW") or "0").strip().lower() in (
    "1",
    "true",
    "yes",
)
KB_OCR_PREPROCESS_CONTRAST = (os.environ.get("KB_OCR_PREPROCESS_CONTRAST") or "0").strip().lower() in (
    "1",
    "true",
    "yes",
)
KB_OCR_REVIEW_CONFIDENCE_THRESHOLD = float(
    os.environ.get("KB_OCR_REVIEW_CONFIDENCE_THRESHOLD") or "0.75"
)


def effective_ocr_pdf_dpi() -> int:
    """OCR-only PDF render DPI (103 FR-P1-002); text-layer pages ignore this."""
    if KB_OCR_PDF_DPI is not None:
        return KB_OCR_PDF_DPI
    if KB_OCR_PREPROCESS_ENABLED:
        return 300
    return KB_EXTRACT_PDF_DPI

KB_EXTRACT_XLSX_MAX_ROWS = int(os.environ.get("KB_EXTRACT_XLSX_MAX_ROWS") or "500")
KB_EXTRACT_XLSX_MAX_COLS = int(os.environ.get("KB_EXTRACT_XLSX_MAX_COLS") or "30")
# LiteParse provider（kb-extract 进程内 + RapidOCR HTTP 桥）
KB_EXTRACT_LITEPARSE_OCR_HOST = (os.environ.get("KB_EXTRACT_LITEPARSE_OCR_HOST") or "127.0.0.1").strip()
KB_EXTRACT_LITEPARSE_OCR_PORT = int(os.environ.get("KB_EXTRACT_LITEPARSE_OCR_PORT") or "18765")
KB_EXTRACT_LITEPARSE_OCR_URL = (
    os.environ.get("KB_EXTRACT_LITEPARSE_OCR_URL")
    or f"http://{KB_EXTRACT_LITEPARSE_OCR_HOST}:{KB_EXTRACT_LITEPARSE_OCR_PORT}/ocr"
).strip()
KB_EXTRACT_LITEPARSE_DPI = int(
    os.environ.get("KB_EXTRACT_LITEPARSE_DPI") or os.environ.get("KB_EXTRACT_PDF_DPI") or "200"
)
KB_EXTRACT_LITEPARSE_MAX_PAGES = int(
    os.environ.get("KB_EXTRACT_LITEPARSE_MAX_PAGES") or os.environ.get("KB_EXTRACT_MAX_PAGES") or "500"
)
KB_EXTRACT_LITEPARSE_OCR_LANG = (os.environ.get("KB_EXTRACT_LITEPARSE_OCR_LANG") or "chi_sim+eng").strip()
KB_EXTRACT_LITEPARSE_NUM_WORKERS = max(
    1, int(os.environ.get("KB_EXTRACT_LITEPARSE_NUM_WORKERS") or "2")
)
# legacy 路径内 Office / 文字层 PDF 首选 MarkItDown；false 时仅用原 PyMuPDF / python-docx 等
KB_MARKITDOWN_ENABLED = (os.environ.get("KB_MARKITDOWN_ENABLED") or "1").strip().lower() in (
    "1",
    "true",
    "yes",
)
# MinerU sidecar（032）：HTTP debug + MQ RPC 生产路径
KB_EXTRACT_MINERU_URL = (os.environ.get("KB_EXTRACT_MINERU_URL") or "").strip().rstrip("/")
KB_EXTRACT_MINERU_USE_MQ = (os.environ.get("KB_EXTRACT_MINERU_USE_MQ") or "0").strip().lower() in (
    "1",
    "true",
    "yes",
)
KB_EXTRACT_MINERU_TIMEOUT_SEC = float(os.environ.get("KB_EXTRACT_MINERU_TIMEOUT_SEC") or "900")
# HTTP debug 路径独立超时；笔记侧 MINERU_PARSE_TIMEOUT_SEC 默认 850，应小于 RPC 超时。
KB_EXTRACT_MINERU_HTTP_TIMEOUT_SEC = float(
    os.environ.get("KB_EXTRACT_MINERU_HTTP_TIMEOUT_SEC") or "300"
)
# Docling sidecar（070）：HTTP debug + MQ RPC 生产路径
KB_EXTRACT_DOCLING_URL = (os.environ.get("KB_EXTRACT_DOCLING_URL") or "").strip().rstrip("/")
KB_EXTRACT_DOCLING_USE_MQ = (os.environ.get("KB_EXTRACT_DOCLING_USE_MQ") or "0").strip().lower() in (
    "1",
    "true",
    "yes",
)
KB_EXTRACT_DOCLING_TIMEOUT_SEC = float(os.environ.get("KB_EXTRACT_DOCLING_TIMEOUT_SEC") or "600")
KB_EXTRACT_DOCLING_HTTP_TIMEOUT_SEC = float(
    os.environ.get("KB_EXTRACT_DOCLING_HTTP_TIMEOUT_SEC") or "630"
)
# sidecar assets_dir（/cache/...）→ kb-extract 可读路径；生产 compose 挂载点为 /docling-cache
KB_EXTRACT_DOCLING_CACHE_MOUNT = (
    os.environ.get("KB_EXTRACT_DOCLING_CACHE_MOUNT") or "/docling-cache"
).strip().rstrip("/") or "/docling-cache"
# 050 表格自动旋转：仅在 filex-mineru 笔记侧生效（kb-extract 主进程不执行）。
# KB_EXTRACT_TABLE_AUTO_ROTATE=0（默认关）；KB_EXTRACT_TABLE_ROTATE_MAX_TABLES=8；
# KB_EXTRACT_TABLE_ROTATE_TIMEOUT_SEC=30。配置写入 mineru 容器 environment。
FILEX_ENABLE_MINERU_PROVIDER = (
    os.environ.get("FILEX_ENABLE_MINERU_PROVIDER") or "0"
).strip().lower() in ("1", "true", "yes")
EXTRACT_MD_MAX_BYTES = 5 * 1024 * 1024  # 5 MiB，与 external_md 一致

KB_EXTRACT_INSAVLO_MAX_FILE_BYTES = 50 * 1024 * 1024  # Insavlo 单文件上限 50 MiB
KB_EXTRACT_INSAVLO_HTTP_TIMEOUT_SEC = float(
    os.environ.get("KB_EXTRACT_INSAVLO_HTTP_TIMEOUT_SEC") or "120"
)

UPLOAD_DIR = os.environ.get("UPLOAD_DIR") or os.path.join(BASE_DIR, "uploads")

_DEFAULT_SECRET_KEY = "change-me-in-production-use-env-var"
SECRET_KEY = os.environ.get("FILEX_SECRET_KEY", _DEFAULT_SECRET_KEY)
ALGORITHM = "HS256"
ACCESS_TOKEN_EXPIRE_MINUTES = 60 * 24  # 24 hours

# 105：笔记预览 extract-assets 短期 signed URL（HMAC capability，非用户 JWT）
EXTRACT_ASSET_SIGN_TTL_SECONDS = int(
    os.environ.get("FILEX_EXTRACT_ASSET_SIGN_TTL_SECONDS") or "1800"
)
EXTRACT_ASSET_SIGN_MAX_KEYS = int(
    os.environ.get("FILEX_EXTRACT_ASSET_SIGN_MAX_KEYS") or "64"
)
EXTRACT_ASSET_HINT_CACHE_SIZE = int(
    os.environ.get("FILEX_EXTRACT_ASSET_HINT_CACHE_SIZE") or "256"
)


def extract_asset_signing_secret() -> bytes:
    """HMAC secret for extract-asset signed URLs; prod should set FILEX_ASSET_SIGNING_SECRET."""
    raw = (os.environ.get("FILEX_ASSET_SIGNING_SECRET") or "").strip()
    if raw:
        return raw.encode("utf-8")
    return SECRET_KEY.encode("utf-8")

ALLOWED_EXTENSIONS = {
    "pdf", "doc", "docx", "ppt", "pptx", "xls", "xlsx",
    "jpg", "jpeg", "png", "gif", "bmp", "webp", "txt", "md", "markdown",
    "html", "htm", "eml",
}

MAX_FILE_SIZE = 10 * 1024 * 1024  # 10MB

THUMBNAIL_SIZE = (200, 200)

FRONTEND_DIST = os.path.join(os.path.dirname(BASE_DIR), "frontend", "dist")

API_KEY_PREFIX = "fb_"
API_KEY_BYTES = 48

# 数据库无任何用户时，若同时设置以下两项，启动时自动创建首个管理员（公开注册已关闭）
FILEX_BOOTSTRAP_USERNAME = (os.environ.get("FILEX_BOOTSTRAP_USERNAME") or "").strip()
FILEX_BOOTSTRAP_PASSWORD = os.environ.get("FILEX_BOOTSTRAP_PASSWORD") or ""

# 运行环境（如 development）；未设置表示常规部署，前端展示为「生产」
FILEX_ENV = (os.environ.get("FILEX_ENV") or "").strip()

# OpenAPI / Swagger / Scalar：仅 development 暴露；生产或未设 FILEX_ENV 时关闭
OPENAPI_ENABLED = FILEX_ENV.lower() == "development"

# 微信开放平台网站应用扫码登录
WECHAT_APP_ID = (os.environ.get("FILEX_WECHAT_APP_ID") or "").strip()
WECHAT_APP_SECRET = (os.environ.get("FILEX_WECHAT_APP_SECRET") or "").strip()
WECHAT_REDIRECT_URI = (os.environ.get("FILEX_WECHAT_REDIRECT_URI") or "").strip()
WECHAT_OAUTH_STATE_TTL_MINUTES = int(os.environ.get("FILEX_WECHAT_STATE_TTL_MINUTES") or "15")
WECHAT_AUTHORIZE_URL = "https://open.weixin.qq.com/connect/qrconnect"
WECHAT_ACCESS_TOKEN_URL = "https://api.weixin.qq.com/sns/oauth2/access_token"
WECHAT_USERINFO_URL = "https://api.weixin.qq.com/sns/userinfo"
MOCK_WECHAT_OPENID = "mock_openid_dev"


def wechat_configured() -> bool:
    return bool(WECHAT_APP_ID and WECHAT_APP_SECRET and WECHAT_REDIRECT_URI)

# 日志（详见 logging_setup.py）：FILEX_LOG_LEVEL / FILEX_LOG_FORMAT / FILEX_LOG_DIR 等

REDIS_URL = (os.environ.get("REDIS_URL") or "").strip()

# License 授权（021）：HMAC 签名 key；生产须设 FILEX_LICENSE_HMAC_SECRET
LICENSE_TRIAL_DAYS = 30
_DEV_LICENSE_HMAC_DEFAULT = "dev-secret-do-not-use-in-production"
FILEX_LICENSE_HMAC_SECRET = (os.environ.get("FILEX_LICENSE_HMAC_SECRET") or "").strip()

# 外部源同步凭据（049 Phase B）：AES-GCM 加密 Notion token 等；生产须设 FILEX_SYNC_SECRET_KEY
_DEV_SYNC_SECRET_DEFAULT = "dev-sync-secret-do-not-use-in-production"


def sync_secret_key() -> str:
    """外部同步 secret 加密密钥；development 未配置时使用固定 dev 默认值。"""
    raw = (os.environ.get("FILEX_SYNC_SECRET_KEY") or "").strip()
    if raw:
        return raw
    env = (os.environ.get("FILEX_ENV") or "").strip().lower()
    if env == "development":
        return _DEV_SYNC_SECRET_DEFAULT
    return ""


def license_hmac_secret() -> str:
    """验签/签发用 HMAC secret；development 未配置时使用固定 dev 默认值。"""
    raw = (os.environ.get("FILEX_LICENSE_HMAC_SECRET") or "").strip()
    if raw:
        return raw
    if FILEX_ENV.lower() == "development":
        return _DEV_LICENSE_HMAC_DEFAULT
    return ""


def license_hmac_secret_env() -> str:
    """FILEX_LICENSE_HMAC_SECRET 环境变量原值（未设置时为空字符串）。"""
    return (os.environ.get("FILEX_LICENSE_HMAC_SECRET") or "").strip()

# 可选：save md 后待编译 slug 达到阈值时 POST JSON 通知外部 Agent
FILEX_WIKI_COMPILE_WEBHOOK_URL = (os.environ.get("FILEX_WIKI_COMPILE_WEBHOOK_URL") or "").strip()

# 可选：覆盖 FileX 技能包目录（GET /filex-skill-update）；未设置时见 utils.pubmed_skill.resolve_pubmed_skill_dir

# 064 OKF bundle import/export
OKF_IMPORT_MAX_CONCEPTS = max(1, int(os.environ.get("OKF_IMPORT_MAX_CONCEPTS") or "200"))
OKF_IMPORT_BATCH_SIZE = max(1, int(os.environ.get("OKF_IMPORT_BATCH_SIZE") or "50"))
OKF_IMPORT_MAX_ZIP_BYTES = max(1, int(os.environ.get("OKF_IMPORT_MAX_ZIP_BYTES") or "104857600"))
OKF_IMPORT_MAX_FILE_BYTES = max(1, int(os.environ.get("OKF_IMPORT_MAX_FILE_BYTES") or "2097152"))
OKF_IMPORT_REWRITE_LINKS = (os.environ.get("OKF_IMPORT_REWRITE_LINKS") or "1").strip().lower() in (
    "1",
    "true",
    "yes",
)
OKF_CONCEPT_PATH_MAX_LEN = max(1, int(os.environ.get("OKF_CONCEPT_PATH_MAX_LEN") or "512"))

# 164 GPU 调度器：单实例 owner + gpu_id 列表；tick 周期与租约 TTL
GPU_SCHEDULER_OWNER_ID = (os.environ.get("GPU_SCHEDULER_OWNER_ID") or "filex-gpu-scheduler").strip()
GPU_SCHEDULER_GPU_IDS = [
    g.strip()
    for g in (os.environ.get("GPU_SCHEDULER_GPU_IDS") or "0").split(",")
    if g.strip()
]
GPU_SCHEDULER_TICK_SEC = max(1.0, float(os.environ.get("GPU_SCHEDULER_TICK_SEC") or "5"))
GPU_SCHEDULER_TTL_SEC = max(1, int(os.environ.get("GPU_SCHEDULER_TTL_SEC") or "30"))
# 164 §6：GPU 调度启用开关。开启后旧 extract/post consumer 只提交/回查持久化
# job 并投递 GPU route，不再自行执行 GPU 工作；filex.gpu.* 由 scheduler 单独消费。
GPU_SCHEDULER_ENABLED = (os.environ.get("GPU_SCHEDULER_ENABLED") or "").strip().lower() in (
    "1",
    "true",
    "yes",
)
# 164 §5.4/§11.1：High 档（32GiB+）常驻独立开关（默认关闭）与模型组峰值预留
# 预算。峰值预留为“预热峰值 + 并发/KV cache 上限”的实现方预算，WHB/生产实测
# 后按真实值覆盖。
GPU_HIGH_RESIDENT_ENABLED = (os.environ.get("GPU_HIGH_RESIDENT_ENABLED") or "").strip().lower() in (
    "1",
    "true",
    "yes",
)
GPU_HIGH_RAPTOR_PEAK_RESERVED_MB = max(0, int(os.environ.get("GPU_HIGH_RAPTOR_PEAK_RESERVED_MB") or "7168"))
GPU_HIGH_MINERU_PEAK_RESERVED_MB = max(0, int(os.environ.get("GPU_HIGH_MINERU_PEAK_RESERVED_MB") or "6144"))
GPU_HIGH_KV_CACHE_BUDGET_MB = max(0, int(os.environ.get("GPU_HIGH_KV_CACHE_BUDGET_MB") or "1024"))

# 087 个人空间备份 ZIP 体积上限兜底（默认 100MB；运行时优先读系统参数 workspace_backup_max_mb）
WORKSPACE_BACKUP_MAX_BYTES = max(1, int(os.environ.get("WORKSPACE_BACKUP_MAX_BYTES") or "104857600"))


def validate_production_secrets() -> None:
    """生产环境禁止使用默认 JWT/Fernet 密钥。"""
    env = (os.environ.get("FILEX_ENV") or "").strip().lower()
    if env == "development":
        return
    key = (os.environ.get("FILEX_SECRET_KEY") or _DEFAULT_SECRET_KEY).strip()
    if key == _DEFAULT_SECRET_KEY:
        raise RuntimeError(
            "生产环境必须设置 FILEX_SECRET_KEY（非默认值 change-me-in-production-use-env-var）。"
        )
