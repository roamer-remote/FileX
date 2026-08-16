# Copyright (c) 2026 徐泽宇
"""Redis cache for ding skill runtime reads.

Authors:
    徐泽宇

Copyright:
    © 2026 徐泽宇
"""

from __future__ import annotations

import json
import logging
from typing import Any

from sqlalchemy.orm import Session

from config import REDIS_URL
from models.skill_file import SkillFile
from services import skill_repository as repo

logger = logging.getLogger(__name__)

KEY_PREFIX = "filex:skill:"
MANIFEST_KEY = f"{KEY_PREFIX}manifest"
GEN_KEY = f"{KEY_PREFIX}gen"

_LOCAL_MANIFEST_KEY: tuple[tuple[str, str], ...] | None = None
_LOCAL_MANIFEST: dict[str, Any] | None = None


def enabled() -> bool:
    return bool(REDIS_URL)


def _file_key(file_id: str) -> str:
    return f"{KEY_PREFIX}file:{file_id}"


def _get_client():
    if not REDIS_URL:
        return None
    import redis

    return redis.from_url(REDIS_URL, decode_responses=True)


def _head_to_cache_payload(row_dict: dict[str, Any], skill_version: str) -> dict[str, Any]:
    return {
        "content": row_dict["content"],
        "etag": row_dict["etag"],
        "sha256": row_dict["sha256"],
        "kind": row_dict["kind"],
        "relative_path": row_dict["path"],
        "skill_version": skill_version,
        "updated_at": row_dict["updated_at"],
    }


def warm_all(db: Session) -> bool:
    """Load all heads + manifest into Redis. Returns False if Redis disabled or data incomplete."""
    if not repo.is_data_ready(db):
        return False
    manifest = repo.build_manifest_dict(db)
    if manifest is None:
        return False
    _set_local_manifest(db, manifest)
    if not enabled():
        return False
    client = _get_client()
    if client is None:
        return False
    skill_version = manifest["skill_version"]
    pipe = client.pipeline()
    heads = repo.list_heads(db)
    if heads is None:
        return False
    for item in heads:
        full = repo.get_head_dict(db, item["file_id"])
        if full is None:
            return False
        pipe.set(_file_key(item["file_id"]), json.dumps(_head_to_cache_payload(full, skill_version), ensure_ascii=False))
    pipe.set(MANIFEST_KEY, json.dumps(manifest, ensure_ascii=False))
    pipe.execute()
    client.incr(GEN_KEY)
    return True


def sync_after_write(db: Session, changed_file_ids: list[str]) -> bool:
    if not enabled():
        return False
    manifest = repo.build_manifest_dict(db)
    if manifest is None:
        return False
    client = _get_client()
    if client is None:
        return False
    skill_version = manifest["skill_version"]
    pipe = client.pipeline()
    ids = set(changed_file_ids)
    if _should_bump_on_save_any(changed_file_ids):
        ids.add("skill-version")
    for fid in ids:
        full = repo.get_head_dict(db, fid)
        if full is None:
            continue
        pipe.set(_file_key(fid), json.dumps(_head_to_cache_payload(full, skill_version), ensure_ascii=False))
    pipe.set(MANIFEST_KEY, json.dumps(manifest, ensure_ascii=False))
    pipe.execute()
    client.incr(GEN_KEY)
    return True


def _should_bump_on_save_any(file_ids: list[str]) -> bool:
    from utils.pubmed_skill import _should_bump_on_save

    return any(_should_bump_on_save(fid) for fid in file_ids)


def get_manifest(db: Session) -> dict[str, Any] | None:
    global _LOCAL_MANIFEST_KEY, _LOCAL_MANIFEST
    if enabled():
        client = _get_client()
        if client is not None:
            raw = client.get(MANIFEST_KEY)
            if raw:
                try:
                    manifest = json.loads(raw)
                    if (
                        isinstance(manifest, dict)
                        and manifest.get("schema_version") == repo.SKILL_SCHEMA_VERSION
                        and manifest.get("agent_source_fingerprint")
                        == repo.agent_source_fingerprint()
                    ):
                        return manifest
                    logger.info("skill_cache_manifest_stale_rebuilding")
                except json.JSONDecodeError:
                    logger.warning("skill_cache_manifest_invalid_json")
    local_key = _manifest_key(db)
    if local_key == _LOCAL_MANIFEST_KEY and _LOCAL_MANIFEST is not None:
        return _LOCAL_MANIFEST
    manifest = repo.build_manifest_dict(db)
    if manifest is not None and enabled():
        try:
            warm_all(db)
        except Exception:
            logger.exception("skill_cache_warm_after_manifest_miss")
    if manifest is not None:
        _set_local_manifest(db, manifest)
    return manifest


def _manifest_key(db: Session) -> tuple[tuple[str, str], ...] | None:
    if not repo.is_data_ready(db):
        return None
    rows = db.query(SkillFile.file_id, SkillFile.content_sha256).order_by(SkillFile.file_id).all()
    return (
        ("schema_version", str(repo.SKILL_SCHEMA_VERSION)),
        ("agent_source_fingerprint", repo.agent_source_fingerprint()),
        *tuple((row.file_id, row.content_sha256) for row in rows),
    )


def _set_local_manifest(db: Session, manifest: dict[str, Any]) -> None:
    global _LOCAL_MANIFEST_KEY, _LOCAL_MANIFEST
    _LOCAL_MANIFEST_KEY = _manifest_key(db)
    _LOCAL_MANIFEST = manifest


def get_file(db: Session, file_id: str) -> dict[str, Any] | None:
    if enabled():
        client = _get_client()
        if client is not None:
            raw = client.get(_file_key(file_id))
            if raw:
                try:
                    return json.loads(raw)
                except json.JSONDecodeError:
                    logger.warning("skill_cache_file_invalid_json file_id=%s", file_id)
    full = repo.get_head_dict(db, file_id)
    if full is None:
        return None
    manifest = repo.build_manifest_dict(db)
    skill_version = manifest["skill_version"] if manifest else ""
    payload = _head_to_cache_payload(full, skill_version)
    if enabled():
        try:
            client = _get_client()
            if client is not None:
                client.set(_file_key(file_id), json.dumps(payload, ensure_ascii=False))
        except Exception:
            logger.exception("skill_cache_set_file_failed file_id=%s", file_id)
    return payload


def try_sync_after_write(db: Session, changed_file_ids: list[str]) -> None:
    try:
        if not sync_after_write(db, changed_file_ids):
            warm_all(db)
    except Exception:
        logger.exception("skill_cache_sync_failed trying warm_all")
        try:
            warm_all(db)
        except Exception:
            logger.exception("skill_cache_warm_all_failed")
