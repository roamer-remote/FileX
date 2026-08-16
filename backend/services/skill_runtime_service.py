# Copyright (c) 2026 徐泽宇
"""Runtime read path: Redis first, DB fallback.

Authors:
    徐泽宇

Copyright:
    © 2026 徐泽宇
"""

from __future__ import annotations

from sqlalchemy.orm import Session

from services import skill_cache_service as cache
from services import skill_repository as repo
from utils.pubmed_skill import (
    API_REF_MODULE_ID,
)


def data_ready(db: Session) -> bool:
    return repo.is_data_ready(db)


def get_manifest(db: Session) -> dict | None:
    return cache.get_manifest(db)


def read_module(db: Session, module_id: str) -> tuple[bytes, str, str] | None:
    fid = "api-ref" if module_id == API_REF_MODULE_ID else f"module:{module_id}"
    if repo.get_head(db, fid) is None:
        return None
    payload = cache.get_file(db, fid)
    if payload is None:
        return repo.read_module_runtime(db, module_id)
    return (
        payload["content"].encode("utf-8"),
        payload["etag"],
        payload.get("skill_version") or "",
    )


def build_zip_bytes(db: Session) -> bytes | None:
    return repo.build_zip_bytes(db)


def build_agent_zip_bytes(db: Session) -> bytes | None:
    """Agent URL-ingest scripts from on-disk skill/ding/agent (not in DB sync)."""
    if not data_ready(db):
        return None
    return repo._build_agent_zip_bytes_from_disk()
