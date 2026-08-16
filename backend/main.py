# Copyright (c) 2026 徐泽宇
"""main 模块。

Authors:
    徐泽宇
"""

from logging_setup import setup_logging

setup_logging()

import os
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import Depends, FastAPI
from fastapi.responses import FileResponse, JSONResponse, Response
from fastapi.staticfiles import StaticFiles

from scalar_fastapi import get_scalar_api_reference

from database import init_db, SessionLocal, get_db
from sqlalchemy.orm import Session
from config import (
    FRONTEND_DIST,
    UPLOAD_DIR,
    FILEX_BOOTSTRAP_USERNAME,
    FILEX_BOOTSTRAP_PASSWORD,
    FILEX_ENV,
    OPENAPI_ENABLED,
    validate_production_secrets,
    RABBITMQ_URL,
)
import structlog

validate_production_secrets()

from services import skill_runtime_service as skill_runtime
from services import skill_cache_service as skill_cache
from services import skill_repository as skill_repo
from services.license_cache_service import get_cached_status
from services.license_service import license_http_body

from routers import (
    auth,
    wechat,
    files,
    folders,
    share,
    admin,
    api_keys,
    external_uploads,
    knowledge_base,
    knowledge_base_quality,
    settings as settings_router,
    ws_kb_index,
    ws_mq_status,
    mq,
    workspaces,
    admin_workspaces,
    admin_external_sync,
    filex_skill,
    admin_skill,
    license as license_router,
    account,
    agent_runs,
)
from routers import insavlo_webhook

from messaging.kb_index_notify import start_notify_consumer, stop_notify_consumer
from messaging.settings_invalidate_consumer import (
    start_settings_invalidate_consumer,
    stop_settings_invalidate_consumer,
)
from messaging.mq_status_watcher import start_mq_status_watcher, stop_mq_status_watcher
from messaging.mq_ws_manager import mq_ws_manager
from messaging.ws_manager import kb_index_ws_manager
from middleware.request_logging import RequestLoggingMiddleware
from middleware.license import LicenseMiddleware


@asynccontextmanager
async def _lifespan(app: FastAPI):
    import asyncio

    loop = asyncio.get_running_loop()
    kb_index_ws_manager.bind_loop(loop)
    mq_ws_manager.bind_loop(loop)
    from services.kb_association_worker import start_association_worker, stop_association_worker
    start_association_worker()
    if not RABBITMQ_URL:
        structlog.get_logger("filex.main").warning("rabbitmq_url_unset_background_skipped")
    else:
        start_notify_consumer()
        start_settings_invalidate_consumer(service=None)
        start_mq_status_watcher()
    from services.license_cache_service import warm_license_cache

    db = SessionLocal()
    try:
        warm_license_cache(db)
    except Exception:
        structlog.get_logger("filex.main").exception("license_cache_warm_failed")
    finally:
        db.close()
    from services.system_setting_service import migrate_insavlo_timeout_hours_to_minutes

    db = SessionLocal()
    try:
        migrated = migrate_insavlo_timeout_hours_to_minutes(db)
        if not migrated:
            structlog.get_logger("filex.main").info(
                "insavlo_timeout_migration_skipped",
                reason="advisory_lock_held",
            )
    except Exception:
        structlog.get_logger("filex.main").exception("insavlo_timeout_migration_failed")
    finally:
        db.close()
    from services.agent_run_service import purge_expired_agent_runs

    db = SessionLocal()
    try:
        purged = purge_expired_agent_runs(db)
        if purged:
            structlog.get_logger("filex.main").info(
                "agent_runs_purge_on_startup",
                purged=purged,
            )
    except Exception:
        structlog.get_logger("filex.main").exception("agent_runs_purge_failed")
    finally:
        db.close()
    from services.wiki_lint_scheduler import wiki_lint_scheduler_loop

    wiki_task = asyncio.create_task(wiki_lint_scheduler_loop())
    # 044: Insavlo webhook write-back loop (restart recovery + async write-back).
    # Decoupled from RABBITMQ_URL: the write-back core (Markdown persist,
    # kb_index sync, index enqueue) does not need MQ; only index/notify
    # publishes do and they are failure-tolerant. Tests skip via
    # FILEX_SKIP_INSAVLO_WRITEBACK_LOOP (see conftest).
    insavlo_task = None
    if os.environ.get("FILEX_SKIP_INSAVLO_WRITEBACK_LOOP") != "1":
        from services.insavlo_webhook_writeback import (
            bind_insavlo_writeback_loop,
            insavlo_webhook_writeback_loop,
        )

        bind_insavlo_writeback_loop()
        insavlo_task = asyncio.create_task(insavlo_webhook_writeback_loop())
    # 044 stage 5: Insavlo webhook timeout scanner (900s, advisory lock 900044).
    insavlo_timeout_task = None
    if os.environ.get("FILEX_SKIP_INSAVLO_TIMEOUT_SCHEDULER") != "1":
        from services.insavlo_webhook_timeout_scheduler import insavlo_webhook_timeout_loop

        insavlo_timeout_task = asyncio.create_task(insavlo_webhook_timeout_loop())
    yield
    stop_association_worker()
    wiki_task.cancel()
    if insavlo_task is not None:
        insavlo_task.cancel()
    if insavlo_timeout_task is not None:
        insavlo_timeout_task.cancel()
    stop_mq_status_watcher()
    stop_settings_invalidate_consumer()
    stop_notify_consumer()


_openapi_url = "/openapi.json" if OPENAPI_ENABLED else None
_docs_url = "/docs" if OPENAPI_ENABLED else None
_redoc_url = "/redoc" if OPENAPI_ENABLED else None

app = FastAPI(
    title="FileX",
    description="AI智能体的资料库",
    version="1.0.0",
    lifespan=_lifespan,
    openapi_url=_openapi_url,
    docs_url=_docs_url,
    redoc_url=_redoc_url,
)
app.add_middleware(RequestLoggingMiddleware)
app.add_middleware(LicenseMiddleware)

structlog.get_logger("filex.main").info("fastapi_app_created")

init_db()


def _ensure_bootstrap_admin():
    """空库时可通过环境变量创建首个管理员（公开注册已关闭）。

    开发环境（FILEX_ENV=development）：若库中已有用户，则将 FILEX_BOOTSTRAP_USERNAME
    对应的管理员账号密码同步为 FILEX_BOOTSTRAP_PASSWORD。
    """
    if not FILEX_BOOTSTRAP_USERNAME or not FILEX_BOOTSTRAP_PASSWORD:
        return
    from models.user import User
    from services.auth_service import create_user, hash_password, verify_password

    db = SessionLocal()
    try:
        if db.query(User).count() == 0:
            create_user(db, FILEX_BOOTSTRAP_USERNAME, FILEX_BOOTSTRAP_PASSWORD, is_admin=True)
            return

        if FILEX_ENV == "development":
            user = (
                db.query(User)
                .filter(User.username == FILEX_BOOTSTRAP_USERNAME, User.is_admin.is_(True))
                .first()
            )
            if user and not verify_password(FILEX_BOOTSTRAP_PASSWORD, user.password_hash):
                user.password_hash = hash_password(FILEX_BOOTSTRAP_PASSWORD)
                user.password_rev = int(user.password_rev or 0) + 1
                db.commit()
    finally:
        db.close()


_ensure_bootstrap_admin()


def _bootstrap_skill_store():
    db = SessionLocal()
    try:
        skill_repo.bootstrap_skill_store(db)
        if skill_repo.is_data_ready(db):
            skill_cache.warm_all(db)
    except Exception:
        structlog.get_logger("filex.main").exception("skill_bootstrap_failed")
    finally:
        db.close()


if os.environ.get("FILEX_SKIP_SKILL_BOOTSTRAP") != "1":
    _bootstrap_skill_store()

os.makedirs(UPLOAD_DIR, exist_ok=True)

app.include_router(auth.router, prefix="/api/auth", tags=["认证"])
app.include_router(wechat.router, prefix="/api/wechat", tags=["微信"])
app.include_router(files.router, prefix="/api/files", tags=["资料"])
app.include_router(folders.router, prefix="/api/folders", tags=["文件夹"])
app.include_router(workspaces.router, prefix="/api/workspaces", tags=["知识空间"])
app.include_router(share.router, prefix="/api/share", tags=["分享"])
app.include_router(admin.router, prefix="/api/admin", tags=["管理"])
app.include_router(admin_workspaces.router, prefix="/api/admin/workspaces", tags=["管理-知识空间"])
app.include_router(admin_external_sync.router, prefix="/api/admin/external-sync", tags=["管理-外部同步"])
app.include_router(settings_router.router, prefix="/api/settings", tags=["系统设置"])
app.include_router(api_keys.router, prefix="/api/api-keys", tags=["API 密钥"])
app.include_router(knowledge_base.router, prefix="/api/knowledge-base", tags=["资料库索引"])
app.include_router(knowledge_base_quality.router, prefix="/api/knowledge-base", tags=["资料库质量工作台"])
app.include_router(mq.router, prefix="/api/mq", tags=["MQ 任务"])
app.include_router(external_uploads.router, prefix="/api/external", tags=["外部上传"])
app.include_router(filex_skill.router, prefix="/api/filex-skill", tags=["钉技能 Runtime"])
app.include_router(admin_skill.router, prefix="/api/admin/skill", tags=["管理-钉技能"])
app.include_router(ws_kb_index.router, prefix="/api/ws", tags=["WebSocket"])
app.include_router(ws_mq_status.router, prefix="/api/ws", tags=["WebSocket"])
app.include_router(license_router.router, prefix="/api/license", tags=["License"])
app.include_router(account.router, prefix="/api/account", tags=["账户"])
app.include_router(agent_runs.router, prefix="/api/agent-runs", tags=["智能体运行记录"])
app.include_router(license_router.admin_router, prefix="/api/admin/license", tags=["管理-授权"])
app.include_router(insavlo_webhook.router, prefix="/api/webhooks/insavlo", tags=["Webhook-Insavlo"])


@app.get("/api/health")
def health():
    return {"status": "ok"}


@app.get("/api/meta/runtime")
def runtime_meta():
    """供前端展示当前服务端运行环境（无需鉴权）。"""
    return {"filex_env": FILEX_ENV or None}


# ── API 文档（仅 development）──────────────────────────────────

if OPENAPI_ENABLED:

    @app.get("/doc", include_in_schema=False)
    def scalar_doc():
        return get_scalar_api_reference(
            openapi_url=app.openapi_url,
            title=app.title,
        )


@app.get("/filex-skill-update")
def filex_skill_update(db: Session = Depends(get_db)):
    """公开 zip：ding/SKILL.md 与同目录 API 参考，供智能体同步本地技能。"""
    license_status = get_cached_status(db)
    if not license_status.valid:
        return JSONResponse(status_code=403, content=license_http_body(license_status))
    if not skill_runtime.data_ready(db):
        return JSONResponse(
            status_code=503,
            content={"detail": "FileX 技能数据未初始化。"},
        )
    payload = skill_runtime.build_zip_bytes(db)
    if payload is None:
        return JSONResponse(
            status_code=503,
            content={"detail": "FileX 技能包不完整。"},
        )
    return Response(
        content=payload,
        media_type="application/zip",
        headers={
            "Content-Disposition": 'attachment; filename="filex-skill.zip"',
            "Cache-Control": "public, max-age=300",
        },
    )


@app.get("/filex-skill-agent-update")
def filex_skill_agent_update(db: Session = Depends(get_db)):
    """公开 zip：ding/agent/ 链接入库脚本，解压到 skills 根目录后与 bootstrap 并列。"""
    license_status = get_cached_status(db)
    if not license_status.valid:
        return JSONResponse(status_code=403, content=license_http_body(license_status))
    if not skill_runtime.data_ready(db):
        return JSONResponse(
            status_code=503,
            content={"detail": "FileX 技能数据未初始化。"},
        )
    payload = skill_runtime.build_agent_zip_bytes(db)
    if payload is None:
        return JSONResponse(
            status_code=503,
            content={"detail": "FileX 链接入库脚本包不可用（检查部署镜像内 skill/ding/agent）。"},
        )
    return Response(
        content=payload,
        media_type="application/zip",
        headers={
            "Content-Disposition": 'attachment; filename="filex-skill-agent.zip"',
            "Cache-Control": "public, max-age=300",
        },
    )


# ── 前端 SPA 静态文件服务（最后匹配，不影响 API 路由）────────────

if os.path.exists(FRONTEND_DIST):
    # 静态资源（非 HTML）由 StaticFiles 处理
    app.mount("/assets", StaticFiles(directory=os.path.join(FRONTEND_DIST, "assets")), name="assets")

    def _safe_frontend_dist_file(url_path: str) -> Path | None:
        """dist 根目录下的 favicon.ico、shell-bg*.svg 等；禁止路径跳出 FRONTEND_DIST。"""
        if not url_path or url_path.startswith("assets/"):
            return None
        try:
            root = Path(FRONTEND_DIST).resolve()
            full = (root / url_path).resolve()
            full.relative_to(root)
        except ValueError:
            return None
        return full if full.is_file() else None

    # SPA 路由：所有非 API/文档路径返回 index.html
    @app.get("/{path:path}", include_in_schema=False)
    def serve_frontend(path: str):
        # 放行 API 路径和文档路径，让它们由其他路由处理
        if path.startswith("api/") or path.startswith("api\\") or path in ("docs", "redoc", "openapi.json", "doc"):
            from fastapi.responses import JSONResponse
            return JSONResponse(status_code=404, content={"detail": "Not Found"})
        static_file = _safe_frontend_dist_file(path)
        if static_file is not None:
            return FileResponse(static_file)
        return FileResponse(os.path.join(FRONTEND_DIST, "index.html"))
