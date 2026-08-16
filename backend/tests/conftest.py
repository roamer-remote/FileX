# Copyright (c) 2026 徐泽宇
"""pytest fixtures for FileX backend tests (PostgreSQL + pgvector).

Authors:
    徐泽宇

Copyright:
    © 2026 徐泽宇
"""

import os
import shutil
from pathlib import Path

_tests_dir = Path(__file__).resolve().parent
_test_uploads_f = _tests_dir / "test_uploads"

TEST_DATABASE_URL = os.environ.get(
    "TEST_DATABASE_URL",
    "postgresql://filebox:filebox@127.0.0.1:5432/filebox_test",
)
os.environ["DATABASE_URL"] = TEST_DATABASE_URL
os.environ.setdefault("OLLAMA_EMBED_MODEL", "bge-m3:latest")
os.environ.setdefault("OLLAMA_EMBED_DIM", "1024")
os.environ.setdefault("KB_SEARCH_MIN_SCORE", "0")
os.environ.setdefault("KB_SEARCH_MMR_LAMBDA", "0")
os.environ["UPLOAD_DIR"] = str(_test_uploads_f.resolve())
os.environ["FILEX_SECRET_KEY"] = "test-secret-key-for-pytest"
os.environ.pop("FILEX_BOOTSTRAP_USERNAME", None)
os.environ.pop("FILEX_BOOTSTRAP_PASSWORD", None)
os.environ.pop("FILEX_ENV", None)
os.environ.pop("REDIS_URL", None)
os.environ["FILEX_SKIP_SKILL_BOOTSTRAP"] = "1"
# 044: keep Insavlo background loops out of the test event loop so per-test
# DB state stays deterministic (write-back / timeout scanners run in prod).
os.environ["FILEX_SKIP_INSAVLO_WRITEBACK_LOOP"] = "1"
os.environ["FILEX_SKIP_INSAVLO_TIMEOUT_SCHEDULER"] = "1"

import hashlib
from datetime import datetime, timedelta

import pytest
from fastapi.testclient import TestClient
from jose import jwt
from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker

from database import Base, get_db
from main import app
from config import SECRET_KEY, ALGORITHM, API_KEY_PREFIX, API_KEY_BYTES
from models.user import User
from models.api_key import ApiKey
from services.auth_service import hash_password, create_access_token
from services.enterprise_rbac_seed import get_unassigned_department_id

TEST_UPLOADS = str(_test_uploads_f.resolve())
TEST_DB_URL = os.environ["DATABASE_URL"]



# 062: test compat — KbChunk(..., embedding=...) still works in pytest
from sqlalchemy import event
from models.kb_chunk import KbChunk as _KbChunkModel


def _kb_chunk_test_init(self, **kwargs):
    emb = kwargs.pop("embedding", None)
    em = kwargs.pop("embedding_model", None)
    _KbChunkModel._kb_chunk_orig_init(self, **kwargs)
    if emb is not None:
        self._pending_vector = (list(emb), em or "test-model")


if not hasattr(_KbChunkModel, "_kb_chunk_orig_init"):
    _KbChunkModel._kb_chunk_orig_init = _KbChunkModel.__init__
    _KbChunkModel.__init__ = _kb_chunk_test_init

    def _kb_chunk_embedding_prop(self):
        from sqlalchemy.orm import object_session
        from services.vector_index import get_vector_index_backend
        pending = getattr(self, "_pending_vector", None)
        if self.id is None and pending:
            return pending[0]
        sess = object_session(self)
        if sess is None:
            return pending[0] if pending else None
        got = get_vector_index_backend(sess).get_many([int(self.id)])
        if int(self.id) in got:
            return got[int(self.id)][0]
        return pending[0] if pending else None

    def _kb_chunk_embedding_model_prop(self):
        from sqlalchemy.orm import object_session
        from services.vector_index import get_vector_index_backend
        pending = getattr(self, "_pending_vector", None)
        if self.id is None and pending:
            return pending[1]
        sess = object_session(self)
        if sess is None:
            return pending[1] if pending else ""
        got = get_vector_index_backend(sess).get_many([int(self.id)])
        if int(self.id) in got:
            return got[int(self.id)][1]
        return pending[1] if pending else ""

    _KbChunkModel.embedding = property(_kb_chunk_embedding_prop)
    _KbChunkModel.embedding_model = property(_kb_chunk_embedding_model_prop)

    @event.listens_for(_KbChunkModel, "after_insert")
    def _sync_kb_chunk_vector_after_insert(mapper, connection, target):
        pending = getattr(target, "_pending_vector", None)
        if pending is None:
            return
        embedding, embedding_model = pending
        from sqlalchemy.orm import Session
        from services.vector_index import VectorRecord, get_vector_index_backend
        sess = Session(bind=connection)
        try:
            get_vector_index_backend(sess).upsert_many(
                [
                    VectorRecord(
                        chunk_id=int(target.id),
                        file_id=int(target.file_id),
                        workspace_id=target.workspace_id,
                        user_id=int(target.user_id),
                        content_kind=target.content_kind,
                        embedding=list(embedding),
                        embedding_model=embedding_model,
                    )
                ]
            )
        finally:
            sess.close()


def pytest_sessionstart(session):
    import os as _os

    from alembic import command
    from alembic.config import Config

    backend_dir = Path(__file__).resolve().parent.parent
    cwd = _os.getcwd()
    try:
        _os.chdir(str(backend_dir))
        eng = create_engine(TEST_DB_URL, pool_pre_ping=True)
        if eng.dialect.name == "postgresql":
            with eng.connect() as conn:
                conn.execute(text("CREATE EXTENSION IF NOT EXISTS vector"))
                conn.commit()
        eng.dispose()
        cfg = Config("alembic.ini")
        command.upgrade(cfg, "head")
    finally:
        _os.chdir(cwd)


@pytest.fixture(scope="session", autouse=True)
def _cleanup_test_uploads():
    yield
    if _test_uploads_f.exists():
        shutil.rmtree(_test_uploads_f, ignore_errors=True)


@pytest.fixture(scope="session")
def engine():
    eng = create_engine(TEST_DB_URL, pool_pre_ping=True)
    yield eng
    eng.dispose()


@pytest.fixture(autouse=True)
def _kb_search_rank_settings_for_tests(db_session):
    """检索质量参数改读 system_settings；测试库迁移默认非零，统一归零以免干扰既有用例。"""
    from services.system_setting_service import (
        KEY_KB_POST_ASYNC_ENABLED,
        KEY_KB_SEARCH_MIN_SCORE,
        KEY_KB_SEARCH_MMR_LAMBDA,
        invalidate_settings_cache,
        update_settings,
    )

    invalidate_settings_cache()
    update_settings(
        db_session,
        {
            KEY_KB_SEARCH_MIN_SCORE: "0",
            KEY_KB_SEARCH_MMR_LAMBDA: "0",
            KEY_KB_POST_ASYNC_ENABLED: "false",
        },
    )
    yield
    invalidate_settings_cache()


@pytest.fixture
def db_session(engine):
    """每个用例在独立事务中运行；先清理库内可能由 SessionLocal 提交的泄漏 KB 行。"""
    connection = engine.connect()
    for stmt in (
        "DELETE FROM insavlo_webhook_events",
        "DELETE FROM kb_doc_entity_edges",
        "DELETE FROM kb_chunk_vectors",
        "DELETE FROM kb_chunks",
        "DELETE FROM kb_post_jobs",
        "DELETE FROM kb_index_jobs",
        "DELETE FROM kb_extract_jobs",
        "DELETE FROM gpu_scheduler_leases",
        "DELETE FROM gpu_scheduler_outbox",
        "DELETE FROM files",
    ):
        try:
            connection.execute(text(stmt))
        except Exception:
            pass
    connection.commit()
    transaction = connection.begin()
    session = sessionmaker(bind=connection)()
    yield session
    session.close()
    transaction.rollback()
    connection.close()


@pytest.fixture(autouse=True)
def _kb_index_test_heartbeat_compat(request, monkeypatch):
    """097：常规用例 noop heartbeat；stale heartbeat 专项自管 SessionLocal。"""
    if "test_kb_index_stale_heartbeat" in request.node.nodeid:
        return
    monkeypatch.setattr(
        "services.kb_index_service.touch_kb_index_job_heartbeat",
        lambda _job_id, **_kwargs: True,
    )


@pytest.fixture
def client(db_session):
    def _get_db_override():
        yield db_session

    app.dependency_overrides[get_db] = _get_db_override
    with TestClient(app) as c:
        yield c
    app.dependency_overrides.clear()


def _create_user(db, username: str, password: str = "password123",
                 is_admin: bool = False, is_active: bool = True) -> User:
    user = User(
        username=username,
        password_hash=hash_password(password),
        is_admin=is_admin,
        is_active=is_active,
        password_rev=0,
        primary_department_id=get_unassigned_department_id(db),
    )
    db.add(user)
    db.commit()
    db.refresh(user)
    from services.workspace_service import ensure_personal_workspace
    ensure_personal_workspace(db, user)
    db.commit()
    db.refresh(user)
    return user


def _create_api_key(db, user: User, is_active: bool = True) -> ApiKey:
    raw_key = f"{API_KEY_PREFIX}{hashlib.sha256(f'{user.id}:test'.encode()).hexdigest()[:API_KEY_BYTES - len(API_KEY_PREFIX)]}"
    key_hash = hashlib.sha256(raw_key.encode()).hexdigest()
    api_key = ApiKey(
        key_hash=key_hash,
        name=f"test-key-{user.username}",
        prefix=raw_key[:8],
        user_id=user.id,
        is_active=is_active,
    )
    db.add(api_key)
    db.commit()
    db.refresh(api_key)
    api_key._plaintext = raw_key  # type: ignore[attr-defined]
    return api_key


@pytest.fixture
def regular_user(db_session):
    return _create_user(db_session, "testuser")


@pytest.fixture
def admin_user(db_session):
    return _create_user(db_session, "adminuser", is_admin=True)


@pytest.fixture
def inactive_user(db_session):
    return _create_user(db_session, "inactiveuser", is_active=False)


@pytest.fixture
def active_api_key(db_session, regular_user):
    return _create_api_key(db_session, regular_user, is_active=True)


@pytest.fixture
def deactivated_api_key(db_session, regular_user):
    return _create_api_key(db_session, regular_user, is_active=False)


@pytest.fixture
def jwt_token(regular_user):
    return create_access_token(regular_user.id, regular_user.password_rev)


@pytest.fixture
def admin_jwt_token(admin_user):
    return create_access_token(admin_user.id, admin_user.password_rev)


def make_jwt(user_id: int, pwd_rev: int = 0,
             expire_delta: timedelta | None = None,
             secret: str | None = None) -> str:
    exp = datetime.utcnow() + (expire_delta or timedelta(hours=1))
    payload = {"sub": str(user_id), "exp": exp, "pwd_rev": pwd_rev}
    return jwt.encode(payload, secret or SECRET_KEY, algorithm=ALGORITHM)

@pytest.fixture
def seeded_skill_db(db_session):
    from services.skill_repository import bootstrap_skill_store, is_data_ready

    if not is_data_ready(db_session):
        bootstrap_skill_store(db_session, commit=False)
    return db_session
