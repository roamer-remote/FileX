# Copyright (c) 2026 徐泽宇
"""Resolve, pack, and serve the FileX ding skill directory.

Authors:
    徐泽宇

Copyright:
    © 2026 徐泽宇
"""

from __future__ import annotations

import hashlib
import io
import json
import os
import zipfile
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

ZIP_INNER_PREFIX = "ding/"

SKILL_SCHEMA_VERSION = 2

API_REF_MODULE_ID = "api-ref"
API_REF_REL_PATH = "references/filex-agent-api.md"
API_REF_LEGACY_REL = "filex-agent-api.md"

FILE_ID_MAX_LEN = 64

SKIP_DIR_NAMES = frozenset({"agent", "__pycache__"})
ALLOWED_SUFFIXES = frozenset({".md", ".txt", ".json"})

FILEX_SKILL_ZIP_STATIC_ENTRIES: tuple[tuple[str, str], ...] = (
    ("SKILL.md", f"{ZIP_INNER_PREFIX}SKILL.md"),
    ("skill.version", f"{ZIP_INNER_PREFIX}skill.version"),
    ("skill.meta.json", f"{ZIP_INNER_PREFIX}skill.meta.json"),
    (API_REF_REL_PATH, f"{ZIP_INNER_PREFIX}{API_REF_REL_PATH}"),
)

FILEX_SKILL_ENTRIES = FILEX_SKILL_ZIP_STATIC_ENTRIES
PUBMED_SKILL_FILES = tuple(rel for rel, _ in FILEX_SKILL_ZIP_STATIC_ENTRIES)

ADMIN_STATIC_FILES: dict[str, tuple[str, str, str]] = {
    "bootstrap": ("SKILL.md", "markdown", "Bootstrap (SKILL.md)"),
    "skill-version": ("skill.version", "text", "skill.version"),
    "skill-meta": ("skill.meta.json", "json", "skill.meta.json"),
    "api-ref": (API_REF_REL_PATH, "markdown", "filex-agent-api.md"),
}

RUNTIME_PACKAGE_EXCLUDED_PREFIXES = ("evals/",)


def is_runtime_package_path(relative_path: str) -> bool:
    """Return whether a skill file belongs in the public runtime bootstrap zip."""
    normalized = relative_path.replace("\\", "/").lower()
    return not normalized.startswith(RUNTIME_PACKAGE_EXCLUDED_PREFIXES)


@dataclass(frozen=True)
class DiskSkillEntry:
    """disk技能条目 工具类型。

        Authors:
            徐泽宇

        Copyright:
            © 2026 徐泽宇

        Since:
            2026-05-28

        Attributes:
            file_id: 文件ID（str）。
            relative_path: relative路径（str）。
            kind: 类型（str）。
            label: label（str）。
            content: 内容（str）。
            sha256: sha256（str）。
            etag: etag（str）。
    """
    file_id: str
    relative_path: str
    kind: str
    label: str
    content: str
    sha256: str
    etag: str


def is_managed_skill_file_id(file_id: str) -> bool:
    if file_id in ADMIN_STATIC_FILES:
        return True
    return file_id.startswith("module:") or file_id.startswith("path:")


def module_id_from_file_id(file_id: str) -> str | None:
    if file_id == "api-ref":
        return API_REF_MODULE_ID
    if file_id.startswith("module:"):
        return file_id[len("module:") :]
    return None


def _admin_file_id_for_module(module_id: str) -> str:
    return f"module:{module_id}"


def _should_skip_path(rel: str) -> bool:
    parts = rel.replace("\\", "/").split("/")
    if parts and parts[0] in SKIP_DIR_NAMES:
        return True
    return any(p in SKIP_DIR_NAMES for p in parts)


def _is_syncable_file(path: Path, skill_dir: Path) -> bool:
    rel = str(path.relative_to(skill_dir)).replace("\\", "/")
    if _should_skip_path(rel):
        return False
    if path.name == "skill.version" and path.parent == skill_dir:
        return True
    suffix = path.suffix.lower()
    return suffix in ALLOWED_SUFFIXES


def _kind_for_path(path: Path) -> str:
    if path.suffix.lower() == ".json":
        return "json"
    if path.suffix.lower() == ".md":
        return "markdown"
    return "text"


def _normalize_file_id(file_id: str, rel: str) -> str:
    if len(file_id) <= FILE_ID_MAX_LEN:
        return file_id
    digest = hashlib.sha256(rel.encode("utf-8")).hexdigest()[:56]
    return f"path:h:{digest}"


def _file_id_for_relative(rel: str) -> str | None:
    rel = rel.replace("\\", "/")
    if rel == "SKILL.md":
        return "bootstrap"
    if rel == "skill.version":
        return "skill-version"
    if rel == "skill.meta.json":
        return "skill-meta"
    if rel == API_REF_REL_PATH or rel == API_REF_LEGACY_REL:
        return "api-ref"
    if rel.startswith("modules/") and rel.endswith(".md"):
        module_id = rel[len("modules/") : -3]
        if module_id and not module_id.startswith("."):
            return _normalize_file_id(_admin_file_id_for_module(module_id), rel)
        return None
    return _normalize_file_id(f"path:{rel}", rel)


def _label_for_relative(rel: str) -> str:
    return rel


def resolve_pubmed_skill_dir() -> Path | None:
    """Return first existing skill directory (env, Docker layout, then repo-root layout)."""
    backend_dir = Path(__file__).resolve().parent.parent
    env = (os.environ.get("FILEX_SKILL_DIR") or "").strip()
    if env:
        p = Path(env)
        return p if _skill_dir_usable(p) else None
    for candidate in (
        backend_dir / "skill" / "ding",
        backend_dir.parent / "skill" / "ding",
        backend_dir / "skill" / "filex",
        backend_dir.parent / "skill" / "filex",
        backend_dir / "skill" / "FileX",
        backend_dir.parent / "skill" / "FileX",
    ):
        if _skill_dir_usable(candidate):
            return candidate
    return None


def _skill_dir_usable(skill_dir: Path) -> bool:
    """Minimum layout: directory + bootstrap SKILL.md."""
    return skill_dir.is_dir() and (skill_dir / "SKILL.md").is_file()


def _resolve_entry_path(skill_dir: Path, rel: str) -> Path | None:
    path = skill_dir / rel
    if path.is_file():
        return path
    if rel == API_REF_REL_PATH:
        legacy = skill_dir / API_REF_LEGACY_REL
        if legacy.is_file():
            return legacy
    return None


def content_digest(text: str) -> tuple[str, str, int]:
    data = text.encode("utf-8")
    sha = hashlib.sha256(data).hexdigest()
    etag = f'"{sha[:16]}"'
    return sha, etag, len(data)


def _entry_from_path(
    file_id: str,
    path: Path,
    skill_dir: Path,
    kind: str,
    label: str,
) -> DiskSkillEntry:
    content = path.read_text(encoding="utf-8")
    sha, etag, _size = content_digest(content)
    rel = str(path.relative_to(skill_dir)).replace("\\", "/")
    return DiskSkillEntry(
        file_id=file_id,
        relative_path=rel,
        kind=kind,
        label=label,
        content=content,
        sha256=sha,
        etag=etag,
    )


def scan_skill_disk(skill_dir: Path) -> list[DiskSkillEntry]:
    """Recursively scan skill/ding; exclude agent/ and non-text files."""
    if not _skill_dir_usable(skill_dir):
        return []
    by_id: dict[str, DiskSkillEntry] = {}
    has_canonical_api_ref = (skill_dir / API_REF_REL_PATH).is_file()

    for path in sorted(skill_dir.rglob("*")):
        if not path.is_file():
            continue
        if not _is_syncable_file(path, skill_dir):
            continue
        rel = str(path.relative_to(skill_dir)).replace("\\", "/")
        if rel == API_REF_LEGACY_REL and has_canonical_api_ref:
            continue
        file_id = _file_id_for_relative(rel)
        if file_id is None:
            continue
        kind = _kind_for_path(path)
        if file_id in ADMIN_STATIC_FILES:
            _, kind, label = ADMIN_STATIC_FILES[file_id]  # type: ignore[misc]
        else:
            label = _label_for_relative(rel)
        entry = _entry_from_path(file_id, path, skill_dir, kind, label)
        by_id[file_id] = entry

    if "bootstrap" not in by_id:
        return []
    return list(by_id.values())


def _read_skill_version(skill_dir: Path) -> str | None:
    path = skill_dir / "skill.version"
    if not path.is_file():
        return None
    text = path.read_text(encoding="utf-8").strip()
    return text or None


def _read_bootstrap_min_version(skill_dir: Path) -> str:
    meta_path = skill_dir / "skill.meta.json"
    if meta_path.is_file():
        try:
            meta = json.loads(meta_path.read_text(encoding="utf-8"))
            val = (meta.get("bootstrap_min_version") or "").strip()
            if val:
                return val
        except json.JSONDecodeError:
            pass
    return _read_skill_version(skill_dir) or "2.0.0"

def _read_api_ref_version(skill_dir: Path) -> str:
    """API 参考版本号 = 内容 SHA256 前 12 位。"""
    ref_path = skill_dir / API_REF_REL_PATH
    if not ref_path.is_file():
        return ""
    data = ref_path.read_text(encoding="utf-8").encode("utf-8")
    return hashlib.sha256(data).hexdigest()[:12]


def _read_changelog(skill_dir: Path) -> dict[str, Any]:
    """Read skill.changelog.json from disk. Returns empty dict if missing."""
    cl_path = skill_dir / "skill.changelog.json"
    if not cl_path.is_file():
        return {}
    try:
        return json.loads(cl_path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return {}




def _aggregate_skill_version(skill_dir: Path, module_digests: dict[str, str]) -> str:
    explicit = _read_skill_version(skill_dir)
    if explicit:
        return explicit
    joined = "".join(module_digests[mid] for mid in sorted(module_digests))
    suffix = hashlib.sha256(joined.encode()).hexdigest()[:8]
    return f"2.0.0+{suffix}"


def _module_manifest_entry(module_id: str, entry: DiskSkillEntry) -> dict[str, Any]:
    if module_id == API_REF_MODULE_ID:
        url = "/api/filex-skill/references/filex-agent-api"
    else:
        url = f"/api/filex-skill/modules/{module_id}"
    return {
        "url": url,
        "etag": entry.etag,
        "sha256": entry.sha256,
        "size_bytes": len(entry.content.encode("utf-8")),
    }


def build_skill_manifest(skill_dir: Path) -> dict[str, Any] | None:
    """Build manifest dict from on-disk scan. Returns None if bootstrap missing."""
    scanned = scan_skill_disk(skill_dir)
    if not scanned:
        return None
    by_id = {e.file_id: e for e in scanned}
    if "bootstrap" not in by_id:
        return None
    modules: dict[str, dict[str, Any]] = {}
    digests: dict[str, str] = {}
    for entry in scanned:
        mid = module_id_from_file_id(entry.file_id)
        if mid is None:
            continue
        modules[mid] = _module_manifest_entry(mid, entry)
        digests[mid] = entry.sha256
    if not modules:
        return None
    updated_at = datetime.now(timezone.utc).replace(microsecond=0).isoformat()
    return {
        "schema_version": SKILL_SCHEMA_VERSION,
        "skill_version": _aggregate_skill_version(skill_dir, digests),
        "bootstrap_min_version": _read_bootstrap_min_version(skill_dir),
        "updated_at": updated_at,
        "api_ref_version": _read_api_ref_version(skill_dir),
        "changelog": _read_changelog(skill_dir),
        "modules": modules,
    }


def read_skill_module(skill_dir: Path, module_id: str) -> tuple[bytes, str, str] | None:
    """Return (content_bytes, etag, skill_version) or None."""
    manifest = build_skill_manifest(skill_dir)
    if manifest is None:
        return None
    mod = manifest["modules"].get(module_id)
    if mod is None:
        return None
    if module_id == API_REF_MODULE_ID:
        file_id = "api-ref"
    else:
        file_id = _admin_file_id_for_module(module_id)
    for entry in scan_skill_disk(skill_dir):
        if entry.file_id == file_id:
            return entry.content.encode("utf-8"), entry.etag, manifest["skill_version"]
    return None


def iter_zip_entries(skill_dir: Path) -> list[tuple[Path, str]] | None:
    scanned = scan_skill_disk(skill_dir)
    if not scanned:
        return None
    resolved: list[tuple[Path, str]] = []
    for entry in scanned:
        if not is_runtime_package_path(entry.relative_path):
            continue
        path = skill_dir / entry.relative_path
        if not path.is_file():
            return None
        arcname = f"{ZIP_INNER_PREFIX}{entry.relative_path}"
        resolved.append((path, arcname))
    return resolved


def build_pubmed_skill_zip(skill_dir: Path) -> bytes | None:
    """Build zip bytes with entries under ding/. Returns None if scan is empty."""
    resolved = iter_zip_entries(skill_dir)
    if resolved is None:
        return None
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", compression=zipfile.ZIP_DEFLATED) as zf:
        for path, arcname in resolved:
            zf.write(path, arcname=arcname)
    return buf.getvalue()

AGENT_BUNDLE_SUFFIXES = frozenset({".py", ".txt", ".md"})
MCP_SOURCE_RELATIVE_PATH = Path("integrations/filex-mcp-server/src/filex_mcp_server")
MCP_ZIP_PREFIX = f"{ZIP_INNER_PREFIX}agent/mcp_src/filex_mcp_server"
MCP_REPOSITORY_ROOT_ENV = "FILEX_REPOSITORY_ROOT"


def _is_agent_bundle_file(path: Path) -> bool:
    if path.name == "__init__.py":
        return False
    if path.suffix.lower() in AGENT_BUNDLE_SUFFIXES:
        return True
    return path.name in ("requirements.txt",)


def _repository_root() -> Path:
    return Path(__file__).resolve().parents[2]


def _configured_repository_root() -> Path | None:
    configured = (os.environ.get(MCP_REPOSITORY_ROOT_ENV) or "").strip()
    return Path(configured) if configured else None


def _iter_mcp_agent_zip_entries(
    repository_root: Path,
    *,
    source_relative: Path = MCP_SOURCE_RELATIVE_PATH,
) -> list[tuple[Path, str]] | None:
    """Return regular MCP source files only when they stay inside the repository."""
    if (
        not source_relative.parts
        or any(part in {"", ".", ".."} for part in source_relative.parts)
        or source_relative != MCP_SOURCE_RELATIVE_PATH
    ):
        raise ValueError("MCP source path traversal is not allowed")
    repository = repository_root.resolve()
    if not repository.is_dir():
        raise ValueError("MCP repository root is not a directory")
    source_dir = repository / MCP_SOURCE_RELATIVE_PATH
    if source_dir.is_symlink():
        raise ValueError("MCP source directory must not be a symbolic link")
    resolved_source = source_dir.resolve()
    try:
        resolved_source.relative_to(repository)
    except ValueError as exc:
        raise ValueError("MCP source path escapes repository root") from exc
    if not source_dir.is_dir():
        return None

    resolved: list[tuple[Path, str]] = []
    for path in sorted(source_dir.rglob("*"), key=lambda item: item.as_posix()):
        if path.is_symlink():
            raise ValueError("MCP source must not contain symbolic links")
        if not path.is_file():
            continue
        resolved_path = path.resolve()
        try:
            relative = resolved_path.relative_to(resolved_source)
        except ValueError as exc:
            raise ValueError("MCP source file escapes repository root") from exc
        if not relative.parts or any(part in {"", ".", ".."} for part in relative.parts):
            raise ValueError("MCP source file path traversal is not allowed")
        resolved.append((path, f"{MCP_ZIP_PREFIX}/{relative.as_posix()}"))

    if not (source_dir / "__init__.py").is_file() or not (source_dir / "server.py").is_file():
        return None
    return resolved


def iter_agent_zip_entries(
    skill_dir: Path,
    *,
    repository_root: Path | None = None,
) -> list[tuple[Path, str]] | None:
    """Zip entries under ding/agent/ for Agent host install (Playwright scripts)."""
    agent_dir = skill_dir / "agent"
    if agent_dir.is_symlink():
        raise ValueError("Agent source directory must not be a symbolic link")
    if not agent_dir.is_dir():
        return None
    resolved: list[tuple[Path, str]] = []
    for path in sorted(agent_dir.rglob("*")):
        if path.is_symlink():
            raise ValueError("Agent source must not contain symbolic links")
        if not path.is_file():
            continue
        if "__pycache__" in path.parts:
            continue
        if not _is_agent_bundle_file(path):
            continue
        rel = path.relative_to(skill_dir).as_posix()
        arcname = f"{ZIP_INNER_PREFIX}{rel}"
        resolved.append((path, arcname))
    if not (agent_dir / "filex_ingest_url.py").is_file():
        return None
    trusted_repository_root = repository_root or _configured_repository_root() or _repository_root()
    mcp_entries = _iter_mcp_agent_zip_entries(trusted_repository_root)
    if mcp_entries is None:
        return None
    resolved.extend(mcp_entries)
    return sorted(resolved, key=lambda entry: entry[1])


def build_agent_skill_zip(skill_dir: Path, *, repository_root: Path | None = None) -> bytes | None:
    """Build zip with ding/agent/*.py + requirements.txt + README.md."""
    resolved = iter_agent_zip_entries(skill_dir, repository_root=repository_root)
    if resolved is None:
        return None
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", compression=zipfile.ZIP_DEFLATED) as zf:
        for path, arcname in resolved:
            info = zipfile.ZipInfo(arcname)
            info.date_time = (1980, 1, 1, 0, 0, 0)
            info.compress_type = zipfile.ZIP_DEFLATED
            zf.writestr(info, path.read_bytes())
    return buf.getvalue()
