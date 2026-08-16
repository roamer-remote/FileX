# Copyright (c) 2026 徐泽宇
"""PostgreSQL mirror of ding skill files on disk (read-only for Runtime/Admin).

Authors:
    徐泽宇

Copyright:
    © 2026 徐泽宇
"""

from __future__ import annotations

import hashlib
import io
import json
import zipfile
from datetime import datetime, timezone
from typing import Any

from sqlalchemy.orm import Session

from models.skill_file import SkillFile

from utils.pubmed_skill import (
    API_REF_MODULE_ID,
    DiskSkillEntry,
    SKILL_SCHEMA_VERSION,
    ZIP_INNER_PREFIX,
    build_agent_skill_zip,
    iter_agent_zip_entries,
    content_digest,
    is_managed_skill_file_id,
    module_id_from_file_id,
    resolve_pubmed_skill_dir,
    scan_skill_disk,
    build_skill_manifest,
    is_runtime_package_path,
)


MODULE_RUNTIME_CONTRACTS: dict[str, dict[str, Any]] = {
    "routing": {"capabilities": ["route"], "depends_on": ["preflight"]},
    "preflight": {"capabilities": ["authenticate", "sync"]},
    "kb-search": {
        "capabilities": ["search", "evidence"],
        "depends_on": ["preflight", "routing"],
    },
    "research": {"capabilities": ["web-research"]},
    "maintain": {
        "capabilities": ["upload", "metadata-write"],
        "depends_on": ["preflight", "dual-path-synthesis"],
    },
    "dual-path-synthesis": {
        "capabilities": ["synthesis", "finalize"],
        "depends_on": ["preflight"],
    },
    "pending-ai": {
        "capabilities": ["pending-work"],
        "depends_on": ["preflight"],
    },
    "url-ingest": {
        "capabilities": ["capture", "ingest"],
        "depends_on": ["preflight", "maintain", "dual-path-synthesis"],
    },
    "wiki-lint": {
        "capabilities": ["lint", "link-audit"],
        "depends_on": ["preflight"],
    },
    "wiki-compile": {
        "capabilities": ["wiki-write"],
        "depends_on": ["preflight", "wiki-lint"],
    },
    "examples": {"capabilities": ["examples"]},
    "troubleshooting": {"capabilities": ["diagnostics"]},
    "humanize-output": {"capabilities": ["render"]},
    "platform-auth": {"capabilities": ["configure-auth"]},
    "api-ref": {"capabilities": ["api-reference"]},
}

_RUNTIME_ZIP_CACHE_KEY: tuple[tuple[str, str, str], ...] | None = None
_RUNTIME_ZIP_CACHE_BYTES: bytes | None = None
_AGENT_ZIP_CACHE_KEY: tuple[tuple[str, int, int], ...] | None = None
_AGENT_ZIP_CACHE_BYTES: bytes | None = None
_AGENT_ZIP_SOURCE_FINGERPRINT: str | None = None


def read_disk_skill_version() -> str | None:
    """当前 skill/ding 目录上的 skill 版本（与 Runtime manifest 聚合规则一致）。"""
    skill_dir = resolve_pubmed_skill_dir()
    if skill_dir is None:
        return None
    manifest = build_skill_manifest(skill_dir)
    if manifest is None:
        return None
    ver = (manifest.get("skill_version") or "").strip()
    return ver or None


def _group_for_file_id(file_id: str, relative_path: str = "") -> str:
    if file_id == "bootstrap":
        return "bootstrap"
    if file_id in ("skill-version", "skill-meta"):
        return "meta"
    if file_id == "api-ref":
        return "api-ref"
    if file_id.startswith("module:"):
        return "modules"
    rel = relative_path.replace("\\", "/")
    if file_id.startswith("path:") and (
        file_id.startswith("path:references/") or rel.startswith("references/")
    ):
        return "references"
    if file_id.startswith("path:"):
        return "other"
    return "other"


def is_data_ready(db: Session) -> bool:
    """True when bootstrap has been synced into DB."""
    row = db.query(SkillFile.file_id).filter(SkillFile.file_id == "bootstrap").first()
    return row is not None


def _upsert_entry(db: Session, entry: DiskSkillEntry, user_id: int | None) -> str:
    """Insert or overwrite row from disk. Returns 'added' or 'updated'."""
    row = db.query(SkillFile).filter(SkillFile.file_id == entry.file_id).first()
    if row is None:
        db.add(
            SkillFile(
                file_id=entry.file_id,
                kind=entry.kind,
                label=entry.label,
                relative_path=entry.relative_path,
                content=entry.content,
                content_sha256=entry.sha256,
                etag=entry.etag,
                revision=1,
                updated_by_user_id=user_id,
            )
        )
        return "added"
    changed = row.content != entry.content or row.content_sha256 != entry.sha256
    row.kind = entry.kind
    row.label = entry.label
    row.relative_path = entry.relative_path
    row.content = entry.content
    row.content_sha256 = entry.sha256
    row.etag = entry.etag
    row.updated_by_user_id = user_id
    return "updated" if changed else "unchanged"


def replace_all_from_disk(
    db: Session,
    user_id: int | None = None,
    *,
    commit: bool = True,
) -> dict[str, Any]:
    """Mirror skill/ding on disk into skill_files (overwrite + delete stale rows)."""
    skill_dir = resolve_pubmed_skill_dir()
    if skill_dir is None:
        return {
            "ok": False,
            "reason": "skill_dir_not_found",
            "skill_dir": None,
            "synced": [],
            "added": [],
            "updated": [],
            "removed": [],
            "data_ready": is_data_ready(db),
        }
    entries = scan_skill_disk(skill_dir)
    if not entries:
        return {
            "ok": is_data_ready(db),
            "reason": "scan_empty",
            "skill_dir": str(skill_dir),
            "synced": [],
            "added": [],
            "updated": [],
            "removed": [],
            "data_ready": is_data_ready(db),
        }
    disk_ids = {e.file_id for e in entries}
    if "bootstrap" not in disk_ids:
        return {
            "ok": is_data_ready(db),
            "reason": "scan_missing_bootstrap",
            "skill_dir": str(skill_dir),
            "synced": [],
            "added": [],
            "updated": [],
            "removed": [],
            "data_ready": is_data_ready(db),
        }
    disk_module_ids = {fid for fid in disk_ids if fid.startswith("module:")}
    existing_module_ids = [
        row.file_id
        for row in db.query(SkillFile).all()
        if row.file_id.startswith("module:")
    ]
    if existing_module_ids and not disk_module_ids:
        return {
            "ok": is_data_ready(db),
            "reason": "scan_no_modules",
            "skill_dir": str(skill_dir),
            "synced": [],
            "added": [],
            "updated": [],
            "removed": [],
            "data_ready": is_data_ready(db),
        }
    added: list[str] = []
    updated: list[str] = []
    synced: list[str] = []
    for entry in entries:
        action = _upsert_entry(db, entry, user_id)
        synced.append(entry.file_id)
        if action == "added":
            added.append(entry.file_id)
        elif action == "updated":
            updated.append(entry.file_id)
    removed: list[str] = []
    for row in db.query(SkillFile).all():
        if not is_managed_skill_file_id(row.file_id):
            continue
        if row.file_id in disk_ids:
            continue
        removed.append(row.file_id)
        db.delete(row)
    if commit:
        db.commit()
    else:
        db.flush()
    ready = is_data_ready(db)
    return {
        "ok": ready,
        "reason": None if ready else "incomplete",
        "skill_dir": str(skill_dir),
        "synced": synced,
        "added": added,
        "updated": updated,
        "removed": removed,
        "data_ready": ready,
    }


def bootstrap_skill_store(db: Session, user_id: int | None = None, *, commit: bool = True) -> dict[str, Any]:
    """Startup / admin button: full disk → DB mirror."""
    return replace_all_from_disk(db, user_id, commit=commit)


def list_heads(db: Session) -> list[dict[str, Any]] | None:
    if not is_data_ready(db):
        return None
    rows = db.query(SkillFile).order_by(SkillFile.relative_path, SkillFile.file_id).all()
    items: list[dict[str, Any]] = []
    for row in rows:
        if not is_managed_skill_file_id(row.file_id):
            continue
        updated = row.updated_at
        if updated is not None and updated.tzinfo is None:
            updated = updated.replace(tzinfo=timezone.utc)
        updated_at = (
            updated.astimezone(timezone.utc).replace(microsecond=0).isoformat()
            if updated
            else datetime.now(timezone.utc).replace(microsecond=0).isoformat()
        )
        items.append(
            {
                "file_id": row.file_id,
                "label": row.label,
                "path": row.relative_path,
                "kind": row.kind,
                "group": _group_for_file_id(row.file_id, row.relative_path),
                "etag": row.etag,
                "sha256": row.content_sha256,
                "size_bytes": len(row.content.encode("utf-8")),
                "updated_at": updated_at,
            }
        )
    return items


def get_head(db: Session, file_id: str) -> SkillFile | None:
    if not is_managed_skill_file_id(file_id):
        return None
    return db.query(SkillFile).filter(SkillFile.file_id == file_id).first()


def get_head_dict(db: Session, file_id: str) -> dict[str, Any] | None:
    row = get_head(db, file_id)
    if row is None:
        return None
    updated = row.updated_at
    if updated is not None and updated.tzinfo is None:
        updated = updated.replace(tzinfo=timezone.utc)
    updated_at = (
        updated.astimezone(timezone.utc).replace(microsecond=0).isoformat()
        if updated
        else datetime.now(timezone.utc).replace(microsecond=0).isoformat()
    )
    return {
        "file_id": row.file_id,
        "content": row.content,
        "etag": row.etag,
        "sha256": row.content_sha256,
        "kind": row.kind,
        "path": row.relative_path,
        "label": row.label,
        "size_bytes": len(row.content.encode("utf-8")),
        "updated_at": updated_at,
    }


def _read_skill_version_from_heads(db: Session) -> str | None:
    row = get_head(db, "skill-version")
    if row is None:
        return None
    text = row.content.strip()
    return text or None


def _read_bootstrap_min_version_from_db(db: Session) -> str:
    row = get_head(db, "skill-meta")
    if row is not None:
        try:
            meta = json.loads(row.content)
            val = (meta.get("bootstrap_min_version") or "").strip()
            if val:
                return val
        except json.JSONDecodeError:
            pass
    return _read_skill_version_from_heads(db) or "2.0.0"



def _api_ref_version_from_db(db: Session) -> str:
    row = get_head(db, "api-ref")
    if row is None:
        return ""
    return hashlib.sha256(row.content.encode("utf-8")).hexdigest()[:12]


def _read_changelog_from_db(db: Session) -> dict:
    row = get_head(db, "path:skill.changelog.json")
    if row is None:
        return {}
    import json
    try:
        return json.loads(row.content)
    except (json.JSONDecodeError, OSError):
        return {}


def _sha256_bytes(payload: bytes | None) -> str:
    if payload is None:
        return ""
    return hashlib.sha256(payload).hexdigest()


def _agent_version(skill_version: str, agent_zip: bytes | None) -> str:
    """Keep the readable skill version while aggregating all agent zip bytes."""
    digest = _sha256_bytes(agent_zip)
    return f"{skill_version}+agent.{digest[:12]}" if digest else skill_version


def build_agent_manifest_fields(skill_version: str) -> dict[str, str]:
    """Build the live agent metadata shared by endpoint and cached manifests."""
    agent_zip = _build_agent_zip_bytes_from_disk()
    return {
        "agent_version": _agent_version(skill_version, agent_zip),
        "agent_zip_sha256": _sha256_bytes(agent_zip),
    }


def _build_agent_zip_bytes_from_disk() -> bytes | None:
    global _AGENT_ZIP_CACHE_KEY, _AGENT_ZIP_CACHE_BYTES, _AGENT_ZIP_SOURCE_FINGERPRINT
    skill_dir = resolve_pubmed_skill_dir()
    if skill_dir is None:
        return None
    entries = iter_agent_zip_entries(skill_dir)
    if entries is None:
        return None
    source_fingerprint = _agent_source_fingerprint_from_entries(entries)
    cache_key = tuple(
        (str(path), path.stat().st_mtime_ns, path.stat().st_size)
        for path, _arcname in entries
    )
    if cache_key == _AGENT_ZIP_CACHE_KEY and source_fingerprint == _AGENT_ZIP_SOURCE_FINGERPRINT:
        return _AGENT_ZIP_CACHE_BYTES
    payload = build_agent_skill_zip(skill_dir)
    _AGENT_ZIP_CACHE_KEY = cache_key
    _AGENT_ZIP_CACHE_BYTES = payload
    _AGENT_ZIP_SOURCE_FINGERPRINT = source_fingerprint
    return payload


def _agent_source_fingerprint_from_entries(entries: list[tuple[Any, str]]) -> str:
    digest = hashlib.sha256()
    for path, arcname in entries:
        digest.update(arcname.encode("utf-8"))
        digest.update(b"\0")
        digest.update(hashlib.sha256(path.read_bytes()).digest())
    return digest.hexdigest()


def agent_source_fingerprint() -> str:
    """Return a stable digest for the files included in the agent update zip."""
    skill_dir = resolve_pubmed_skill_dir()
    if skill_dir is None:
        return ""
    entries = iter_agent_zip_entries(skill_dir)
    if entries is None:
        return ""
    return _agent_source_fingerprint_from_entries(entries)


def build_manifest_dict(db: Session) -> dict[str, Any] | None:
    if not is_data_ready(db):
        return None
    rows = db.query(SkillFile).filter(SkillFile.file_id.like("module:%") | (SkillFile.file_id == "api-ref")).all()
    modules: dict[str, dict[str, Any]] = {}
    for row in rows:
        mid = module_id_from_file_id(row.file_id)
        if mid is None:
            continue
        if mid == API_REF_MODULE_ID:
            url = "/api/filex-skill/references/filex-agent-api"
        else:
            url = f"/api/filex-skill/modules/{mid}"
        modules[mid] = {
            "url": url,
            "etag": row.etag,
            "sha256": row.content_sha256,
            "size_bytes": len(row.content.encode("utf-8")),
        }
        contract = MODULE_RUNTIME_CONTRACTS.get(mid, {})
        modules[mid].update(
            {
                "requires_api_key": mid != "research",
                "fallback_allowed": True,
                "min_agent_version": "2.0.0",
                "depends_on": list(contract.get("depends_on", [])),
                "capabilities": list(contract.get("capabilities", [])),
            }
        )
    if not modules:
        return None
    skill_version = _read_skill_version_from_heads(db)
    if not skill_version:
        joined = "".join(modules[mid]["sha256"] for mid in sorted(modules))
        suffix = hashlib.sha256(joined.encode()).hexdigest()[:8]
        skill_version = f"2.0.0+{suffix}"
    skill_zip = build_zip_bytes(db)
    agent_fields = build_agent_manifest_fields(skill_version)
    agent_fields["agent_source_fingerprint"] = (
        _AGENT_ZIP_SOURCE_FINGERPRINT or agent_source_fingerprint()
    )
    return {
        "schema_version": SKILL_SCHEMA_VERSION,
        "skill_version": skill_version,
        "bootstrap_min_version": _read_bootstrap_min_version_from_db(db),
        "skill_zip_sha256": _sha256_bytes(skill_zip),
        **agent_fields,
        "api_ref_version": _api_ref_version_from_db(db),
        "changelog": _read_changelog_from_db(db),
        "updated_at": datetime.now(timezone.utc).replace(microsecond=0).isoformat(),
        "modules": modules,
    }


def build_zip_bytes(db: Session) -> bytes | None:
    global _RUNTIME_ZIP_CACHE_KEY, _RUNTIME_ZIP_CACHE_BYTES
    if not is_data_ready(db):
        return None
    rows = db.query(SkillFile).order_by(SkillFile.relative_path).all()
    managed = [
        row
        for row in rows
        if is_managed_skill_file_id(row.file_id)
        and is_runtime_package_path(row.relative_path)
    ]
    if not managed:
        return None
    cache_key = tuple(
        (row.file_id, row.relative_path, row.content_sha256) for row in managed
    )
    if cache_key == _RUNTIME_ZIP_CACHE_KEY:
        return _RUNTIME_ZIP_CACHE_BYTES
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", compression=zipfile.ZIP_DEFLATED) as zf:
        for row in managed:
            arcname = f"{ZIP_INNER_PREFIX}{row.relative_path}"
            info = zipfile.ZipInfo(arcname)
            info.date_time = (1980, 1, 1, 0, 0, 0)
            info.compress_type = zipfile.ZIP_DEFLATED
            zf.writestr(info, row.content.encode("utf-8"))
    _RUNTIME_ZIP_CACHE_KEY = cache_key
    _RUNTIME_ZIP_CACHE_BYTES = buf.getvalue()
    return _RUNTIME_ZIP_CACHE_BYTES


def read_module_runtime(db: Session, module_id: str) -> tuple[bytes, str, str] | None:
    if module_id == API_REF_MODULE_ID:
        fid = "api-ref"
    else:
        fid = f"module:{module_id}"
    row = get_head(db, fid)
    manifest = build_manifest_dict(db)
    if row is None or manifest is None:
        return None
    mod = manifest["modules"].get(module_id)
    if mod is None:
        return None
    return row.content.encode("utf-8"), mod["etag"], manifest["skill_version"]
