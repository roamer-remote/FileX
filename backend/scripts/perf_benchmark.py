from __future__ import annotations

import argparse
import json
import os
import statistics
import sys
import time
import tracemalloc
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import patch

BACKEND_DIR = Path(__file__).resolve().parents[1]
REPO_DIR = BACKEND_DIR.parent
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

os.environ.setdefault(
    "DATABASE_URL",
    os.environ.get("TEST_DATABASE_URL", "postgresql://filebox:filebox@127.0.0.1:5432/filebox_test"),
)
os.environ.setdefault("FILEX_SECRET_KEY", "perf-benchmark-secret")
os.environ.setdefault("FILEX_SKIP_SKILL_BOOTSTRAP", "1")

from sqlalchemy import event

from config import OLLAMA_EMBED_DIM
from database import SessionLocal
from models.file import File as FileModel
from models.folder import Folder  # noqa: F401
from models.kb_chunk import KbChunk
from tests.helpers.kb_chunk_seed import create_kb_chunk
from models.kb_extract_job import KbExtractJob
from models.kb_index_job import KbIndexJob
from models.workspace import Workspace, WorkspaceMember  # noqa: F401
from models.tag import Tag, file_tags
from models.user import User
from services.auth_service import hash_password
from services.knowledge_base_index_service import auto_sync_kb_index
from services.rabbitmq_status_service import get_mq_status
from services.tag_service import build_user_tag_graph, build_user_tag_heatmap
from services.workspace_service import ensure_personal_workspace

SCALES = {
    "small": (1000, 10000),
    "medium": (5000, 50000),
    "large": (10000, 100000),
}


class SqlCounter:
    def __init__(self, engine):
        self.engine = engine
        self.count = 0

    def _before(self, conn, cursor, statement, parameters, context, executemany):
        self.count += 1

    def __enter__(self):
        event.listen(self.engine, "before_cursor_execute", self._before)
        return self

    def __exit__(self, exc_type, exc, tb):
        event.remove(self.engine, "before_cursor_execute", self._before)


def _deny_unsafe_db(url: str, allow_dev_db: bool) -> None:
    if allow_dev_db:
        return
    if "_test" not in url and "filebox_test" not in url:
        raise SystemExit("Refusing to run benchmark outside TEST_DATABASE_URL without --allow-dev-db")


def _percentile(values: list[float], pct: float) -> float:
    if not values:
        return 0.0
    if len(values) == 1:
        return values[0]
    return statistics.quantiles(values, n=100, method="inclusive")[int(pct) - 1]


def _user(db, run_id: str) -> User:
    username = f"perf_{run_id}"
    user = db.query(User).filter(User.username == username).first()
    if user:
        return user
    from services.enterprise_rbac_seed import get_unassigned_department_id

    user = User(
        username=username,
        password_hash=hash_password("password123"),
        is_admin=False,
        is_active=True,
        primary_department_id=get_unassigned_department_id(db),
    )
    db.add(user)
    db.flush()
    ensure_personal_workspace(db, user)
    db.commit()
    db.refresh(user)
    return user


def cleanup(run_id: str) -> None:
    db = SessionLocal()
    try:
        user = db.query(User).filter(User.username == f"perf_{run_id}").first()
        if not user:
            return
        file_ids = [r[0] for r in db.query(FileModel.id).filter(FileModel.user_id == user.id).all()]
        if file_ids:
            db.query(KbChunk).filter(KbChunk.file_id.in_(file_ids)).delete(synchronize_session=False)
            db.query(KbIndexJob).filter(KbIndexJob.file_id.in_(file_ids)).delete(synchronize_session=False)
            db.query(KbExtractJob).filter(KbExtractJob.file_id.in_(file_ids)).delete(synchronize_session=False)
            db.execute(file_tags.delete().where(file_tags.c.file_id.in_(file_ids)))
            db.query(FileModel).filter(FileModel.id.in_(file_ids)).delete(synchronize_session=False)
        db.query(Tag).filter(Tag.user_id == user.id).delete(synchronize_session=False)
        db.delete(user)
        db.commit()
    finally:
        db.close()


def seed(run_id: str, scale: str) -> int:
    files_count, chunks_count = SCALES[scale]
    db = SessionLocal()
    try:
        user = _user(db, run_id)
        ws = ensure_personal_workspace(db, user)
        existing = db.query(FileModel).filter(FileModel.user_id == user.id).count()
        if existing >= files_count:
            return user.id
        files = []
        for i in range(existing, files_count):
            files.append(
                FileModel(
                    user_id=user.id,
                    workspace_id=ws.id,
                    filename=f"perf-{run_id}-{i}.md",
                    original_name=f"perf-{run_id}-{i}.md",
                    file_path=f"/tmp/perf-{run_id}-{i}.md",
                    file_size=128,
                    mime_type="text/markdown",
                    md5_hash=f"{i:032x}"[-32:],
                    has_md=True,
                    index_status="ready",
                    publish_status="published",
                )
            )
        db.add_all(files)
        db.commit()
        file_ids = [r[0] for r in db.query(FileModel.id).filter(FileModel.user_id == user.id).order_by(FileModel.id).all()]
        chunk_existing = db.query(KbChunk).filter(KbChunk.user_id == user.id).count()
        if chunk_existing < chunks_count:
            vec = [0.1] * OLLAMA_EMBED_DIM
            batch = []
            for i in range(chunk_existing, chunks_count):
                fid = file_ids[i % len(file_ids)]
                batch.append(
                    {
                        "user_id": user.id,
                        "workspace_id": ws.id,
                        "file_id": fid,
                        "chunk_index": i // len(file_ids),
                        "source": "perf",
                        "text": f"benchmark query content {i}",
                        "char_start": 0,
                        "char_end": 24,
                        "embedding": vec,
                        "embedding_model": "perf-mock",
                    }
                )
                if len(batch) >= 500:
                    for kw in batch:
                        create_kb_chunk(db, **kw)
                    db.commit()
                    batch.clear()
            if batch:
                for kw in batch:
                    create_kb_chunk(db, **kw)
                db.commit()
        for i, fid in enumerate(file_ids[: min(100, len(file_ids))]):
            db.add(KbIndexJob(user_id=user.id, file_id=fid, status="queued" if i % 2 else "running"))
            db.add(KbExtractJob(user_id=user.id, file_id=fid, status="queued" if i % 2 else "running"))
        db.commit()
        return user.id
    finally:
        db.close()


@contextmanager
def maybe_mock_embed(enabled: bool):
    if not enabled:
        vec = [0.1] * OLLAMA_EMBED_DIM
        with patch("services.kb_ollama_embed.embed_text", return_value=vec), patch(
            "services.kb_search_service.embed_text", return_value=vec
        ):
            yield
    else:
        yield


def _run_once(name: str, user_id: int, with_ollama: bool) -> dict:
    db = SessionLocal()
    counter = SqlCounter(db.get_bind())
    tracemalloc.start()
    start = time.perf_counter()
    meta: dict = {}
    try:
        with counter:
            if name == "files":
                list(db.query(FileModel).filter(FileModel.user_id == user_id).order_by(FileModel.id).limit(100).all())
            elif name == "search":
                from services.kb_search_service import search_kb

                t0 = time.perf_counter()
                with maybe_mock_embed(with_ollama):
                    items, _model, _k, search_meta = search_kb(db, user_id, "benchmark", top_k=8, hybrid=False)
                meta["search_ms"] = (time.perf_counter() - t0) * 1000
                meta["embed_ms"] = 0.0 if not with_ollama else None
                meta["acl_ms"] = 0.0
                meta["hits"] = len(items)
                meta["search_meta"] = search_meta
            elif name == "kb-index":
                auto_sync_kb_index(db, user_id, sync_scope="auto")
            elif name == "mq-status":
                get_mq_status(viewer=None)
            elif name == "tag-graph":
                build_user_tag_graph(db, user_id)
                build_user_tag_heatmap(db, user_id)
            else:
                raise ValueError(name)
    finally:
        elapsed = (time.perf_counter() - start) * 1000
        _cur, peak = tracemalloc.get_traced_memory()
        tracemalloc.stop()
        db.close()
    return {"ms": elapsed, "sql": counter.count, "peak_kb": peak / 1024, **meta}


def run(args) -> list[dict]:
    user_id = seed(args.run_id, args.scale)
    scenarios = ["files", "search", "kb-index", "mq-status", "tag-graph"] if args.scenario == "all" else [args.scenario]
    results = []
    for scenario in scenarios:
        runs = [_run_once(scenario, user_id, args.with_ollama) for _ in range(args.iterations)]
        results.append(
            {
                "scenario": scenario,
                "iterations": args.iterations,
                "p50_ms": _percentile([r["ms"] for r in runs], 50),
                "p95_ms": _percentile([r["ms"] for r in runs], 95),
                "sql_p50": _percentile([r["sql"] for r in runs], 50),
                "peak_kb_p95": _percentile([r["peak_kb"] for r in runs], 95),
                "runs": runs,
            }
        )
    return results


def write_report(results: list[dict], run_id: str, label: str) -> None:
    out_dir = REPO_DIR / "specs" / "041-python-backend-performance-optimization" / "benchmarks"
    out_dir.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now(timezone.utc).strftime("%Y%m%d-%H%M%S")
    base = out_dir / f"{label}-{stamp}"
    payload = {"run_id": run_id, "created_at": stamp, "results": results}
    (base.with_suffix(".json")).write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    lines = [f"# 041 benchmark {label}", "", f"- run_id: `{run_id}`", ""]
    lines.append("| scenario | iterations | p50_ms | p95_ms | sql_p50 | peak_kb_p95 |")
    lines.append("|---|---:|---:|---:|---:|---:|")
    for row in results:
        lines.append(
            f"| {row['scenario']} | {row['iterations']} | {row['p50_ms']:.2f} | {row['p95_ms']:.2f} | {row['sql_p50']:.1f} | {row['peak_kb_p95']:.1f} |"
        )
    (base.with_suffix(".md")).write_text("\n".join(lines) + "\n", encoding="utf-8")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--scenario", choices=["files", "search", "kb-index", "mq-status", "tag-graph", "all"], default="all")
    parser.add_argument("--scale", choices=sorted(SCALES), default="small")
    parser.add_argument("--run-id", default="default")
    parser.add_argument("--cleanup", action="store_true")
    parser.add_argument("--allow-dev-db", action="store_true")
    parser.add_argument("--with-ollama", action="store_true")
    parser.add_argument("--iterations", type=int, default=10)
    parser.add_argument("--label", default="baseline")
    args = parser.parse_args()

    _deny_unsafe_db(os.environ["DATABASE_URL"], args.allow_dev_db)
    if args.cleanup:
        cleanup(args.run_id)
        return
    results = run(args)
    write_report(results, args.run_id, args.label)


if __name__ == "__main__":
    main()
