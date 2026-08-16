# Copyright (c) 2026 徐泽宇
"""OKF native sidecar note helpers."""

from __future__ import annotations

import json
import logging
import os
import re
import tempfile
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from fastapi import HTTPException, status

from models.file import File as FileModel
from models.folder import Folder
from services.file_service import get_extension
from services.md_hash_service import compute_md_content_hash
from services.md_note_service import decode_upload_markdown, is_markdown_upload
from services.md_paths import (
    is_legacy_flat_md_note_path,
    md_note_path,
    okf_sidecar_path,
    okf_workspace_root,
    resolve_upload_path,
)
from services.okf.frontmatter import (
    OkfParseError,
    merge_frontmatter,
    normalize_metadata_for_storage,
    split_frontmatter,
)
from services.tag_service import replace_file_tags

DEFAULT_OKF_TYPE = "FileX Source"
DEFAULT_OKF_VERSION = "0.1"
logger = logging.getLogger(__name__)
_CONCEPT_PATH_UNSAFE_RE = re.compile(r"[^0-9A-Za-z._\-\u4e00-\u9fff]+")


@dataclass(frozen=True)
class OkfNote:
    frontmatter: dict[str, Any]
    body: str
    raw: str
    is_legacy: bool


def _resolved_md_path(file_record: FileModel) -> str | None:
    if not file_record.md_file_path:
        return None

    return resolve_upload_path(file_record.md_file_path) or file_record.md_file_path


def _read_raw(file_record: FileModel) -> str | None:
    if not file_record.has_md and not file_record.md_file_path:
        legacy = md_note_path(file_record.id)
        if not os.path.isfile(legacy):
            return None
    candidates: list[str] = []
    if file_record.md_file_path:
        resolved = _resolved_md_path(file_record)
        if resolved:
            candidates.append(resolved)
    if file_record.okf_concept_path and file_record.workspace_id is not None:
        candidates.append(okf_sidecar_path(file_record.workspace_id, file_record.okf_concept_path))
    candidates.append(md_note_path(file_record.id))
    seen: set[str] = set()
    for path in candidates:
        if not path or path in seen:
            continue
        seen.add(path)
        if not os.path.isfile(path):
            continue
        try:
            with open(path, encoding="utf-8") as fh:
                return fh.read()
        except OSError:
            continue
    return None


def _note_path_for_write(file_record: FileModel, *, concept_path: str | None = None) -> str:
    existing = _resolved_md_path(file_record)
    if existing and os.path.isfile(existing) and is_legacy_flat_md_note_path(existing):
        parent = os.path.dirname(existing)
        if parent:
            os.makedirs(parent, exist_ok=True)
        return existing

    cp = (concept_path or file_record.okf_concept_path or "").strip()
    if cp and file_record.workspace_id is not None:
        path = okf_sidecar_path(file_record.workspace_id, cp)
        parent = os.path.dirname(path)
        if parent:
            os.makedirs(parent, exist_ok=True)
        return path

    if existing:
        parent = os.path.dirname(existing)
        if parent:
            os.makedirs(parent, exist_ok=True)
        return existing

    if file_record.md_file_path:
        path = file_record.md_file_path
        parent = os.path.dirname(path)
        if parent:
            os.makedirs(parent, exist_ok=True)
        return path

    path = md_note_path(file_record.id)
    parent = os.path.dirname(path)
    if parent:
        os.makedirs(parent, exist_ok=True)
    return path


def _write_raw(file_record: FileModel, raw: str, *, concept_path: str | None = None) -> None:
    path = _note_path_for_write(file_record, concept_path=concept_path)
    directory = os.path.dirname(path) or "."
    fd, tmp_path = tempfile.mkstemp(prefix=".okf-note-", suffix=".tmp", dir=directory, text=True)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as fh:
            fh.write(raw)
            fh.flush()
            os.fsync(fh.fileno())
        os.replace(tmp_path, path)
    except Exception:
        try:
            os.unlink(tmp_path)
        except OSError:
            pass
        raise
    file_record.has_md = True
    file_record.md_file_path = path


def _best_effort_rmdir_empty_okf_parents(file_path: str, workspace_id: int | None) -> None:
    if workspace_id is None:
        return
    root = os.path.normpath(okf_workspace_root(workspace_id))
    parent = os.path.dirname(file_path)
    while parent:
        parent_norm = os.path.normpath(parent)
        if parent_norm == root or not parent_norm.startswith(root + os.sep):
            break
        try:
            os.rmdir(parent)
        except OSError:
            break
        parent = os.path.dirname(parent)


def _remove_sidecar_file(path: str | None) -> None:
    if not path or not os.path.isfile(path):
        return
    try:
        os.remove(path)
    except OSError:
        pass


def _default_title(file_record: FileModel) -> str:
    name = file_record.original_name or file_record.filename or f"file-{file_record.id}"
    suffix = Path(name).suffix
    if suffix:
        return name[: -len(suffix)] or name
    ext = get_extension(name)
    if ext and name.lower().endswith(f".{ext.lower()}"):
        return name[: -(len(ext) + 1)] or name
    return name


def _concept_segment(value: str, fallback: str) -> str:
    raw = (value or fallback or "source").strip()
    raw = raw.replace("\x00", "").replace("..", ".")
    slug = _CONCEPT_PATH_UNSAFE_RE.sub("-", raw).strip(".-_")
    return slug or "source"


def _concept_basename(title: str, fallback: str) -> str:
    raw = (title or fallback or "source").strip().replace("\\", "/").split("/")[-1]
    return _concept_segment(raw, fallback)


def _folder_concept_parts(db, file_record: FileModel) -> list[str]:
    if not file_record.folder_id:
        return ["uncategorized"]

    parts: list[str] = []
    seen: set[int] = set()
    folder_id = file_record.folder_id
    for _ in range(50):
        if folder_id is None or folder_id in seen:
            break
        seen.add(folder_id)
        folder = (
            db.query(Folder)
            .filter(Folder.id == folder_id, Folder.workspace_id == file_record.workspace_id)
            .first()
        )
        if not folder:
            break
        parts.append(_concept_segment(folder.name, f"folder-{folder.id}"))
        folder_id = folder.parent_id
    if not parts:
        return ["uncategorized"]
    return list(reversed(parts))


def _default_concept_path(db, file_record: FileModel) -> str:
    basename = _concept_basename(_default_title(file_record), f"file-{file_record.id}")
    return "/".join(["sources", *_folder_concept_parts(db, file_record), basename])


def _unique_concept_path(db, file_record: FileModel, requested_path: str | None = None) -> str:
    if requested_path:
        base = requested_path.strip().strip("/")
    else:
        base = _default_concept_path(db, file_record)
    base = base.replace("\\", "/").replace("\x00", "")
    parts = [_concept_basename(part, "source") for part in base.split("/") if part.strip()]
    if not parts:
        parts = ["sources", "uncategorized", f"file-{file_record.id}"]
    concept_path = "/".join(parts)

    from config import OKF_CONCEPT_PATH_MAX_LEN

    if len(concept_path) > OKF_CONCEPT_PATH_MAX_LEN:
        suffix = f"-{file_record.id}"
        keep = max(1, OKF_CONCEPT_PATH_MAX_LEN - len(suffix))
        concept_path = concept_path[:keep].rstrip(".-/") + suffix

    q = db.query(FileModel).filter(
        FileModel.okf_concept_path == concept_path,
        FileModel.user_id == file_record.user_id,
        FileModel.workspace_id == file_record.workspace_id,
        FileModel.id != file_record.id,
    )
    if not q.first():
        return concept_path
    suffixed = f"{concept_path}-{file_record.id}"
    if len(suffixed) > OKF_CONCEPT_PATH_MAX_LEN:
        suffix = f"-{file_record.id}"
        suffixed = concept_path[: OKF_CONCEPT_PATH_MAX_LEN - len(suffix)].rstrip(".-/") + suffix
    return suffixed


def _utc_timestamp(value: datetime | None = None) -> str:
    dt = value or datetime.now(UTC)
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=UTC)
    dt = dt.astimezone(UTC).replace(microsecond=0)
    return dt.isoformat().replace("+00:00", "Z")


def _clean_tags(tags: list[str] | tuple[str, ...] | str | None) -> list[str]:
    if tags is None:
        return []
    if isinstance(tags, str):
        value = tags.strip()
        if not value:
            return []
        if value.startswith("["):
            try:
                parsed = json.loads(value)
            except json.JSONDecodeError:
                parsed = None
            if isinstance(parsed, list):
                raw_items = [str(item).strip() for item in parsed]
            else:
                raw_items = [item.strip() for item in value.split(",")]
        else:
            raw_items = [item.strip() for item in value.split(",")]
    else:
        raw_items = [str(item).strip() for item in tags]
    return [item for item in raw_items if item]


def _clean_frontmatter(frontmatter: dict[str, Any]) -> dict[str, Any]:
    cleaned: dict[str, Any] = {}
    for key, value in dict(frontmatter or {}).items():
        if value is None:
            continue
        if isinstance(value, str) and value == "":
            continue
        cleaned[key] = value
    return cleaned


def _filex_block(file_record: FileModel, existing: dict[str, Any] | None = None) -> dict[str, Any]:
    block = {
        "file_id": file_record.id,
        "workspace_id": file_record.workspace_id,
        "folder_id": file_record.folder_id,
        "source_mime": file_record.mime_type,
        "source_md5": file_record.md5_hash,
        "source_size": file_record.file_size,
        "original_name": file_record.original_name,
        "extract_status": file_record.extract_status,
        "extract_engine": file_record.extract_engine,
    }
    if existing and existing.get("concept_path_custom") is True:
        block["concept_path_custom"] = True
    return block


def _metadata_for_file(file_record: FileModel) -> dict[str, Any]:
    metadata = dict(file_record.okf_metadata or {})
    okf_type = file_record.okf_type or metadata.get("type") or DEFAULT_OKF_TYPE
    metadata["type"] = okf_type
    metadata.setdefault("title", _default_title(file_record))
    metadata.setdefault("resource", f"filex://files/{file_record.id}")
    metadata.setdefault("tags", [])
    metadata.setdefault("timestamp", _utc_timestamp())
    metadata.setdefault("okf_version", DEFAULT_OKF_VERSION)
    metadata.setdefault("filex", _filex_block(file_record))
    return metadata


def read_okf_note(file_record: FileModel) -> OkfNote:
    raw = _read_raw(file_record) or ""
    if not raw:
        return OkfNote(frontmatter={}, body="", raw="", is_legacy=True)
    try:
        frontmatter, body = split_frontmatter(raw)
    except OkfParseError as exc:
        logger.warning("invalid_okf_frontmatter file_id=%s error=%s", file_record.id, exc)
        return OkfNote(frontmatter={}, body=raw, raw=raw, is_legacy=True)
    if not frontmatter.get("type"):
        return OkfNote(frontmatter={}, body=raw, raw=raw, is_legacy=True)
    return OkfNote(frontmatter=frontmatter, body=body, raw=raw, is_legacy=False)


def read_okf_body_for_file(file_record: FileModel) -> str | None:
    if not file_record.has_md or not file_record.md_file_path:
        return None
    return read_okf_note(file_record).body


def effective_okf_frontmatter(file_record: FileModel) -> dict[str, Any]:
    """返回文件的生效 frontmatter：OKF 文件取解析结果，legacy/空壳取列派生默认值。"""
    note = read_okf_note(file_record)
    if not note.is_legacy and note.frontmatter:
        return dict(note.frontmatter)
    return _metadata_for_file(file_record)


def read_okf_body_plaintext_or_raise(file_record: FileModel) -> str:
    """读取 OKF body（body-only）；无笔记或文件缺失时抛 404，与 GET /files/{id}/md 一致。"""
    if not file_record.has_md or not file_record.md_file_path:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="该资料没有 Markdown 笔记",
        )
    path = _resolved_md_path(file_record)
    if not path or not os.path.isfile(path):
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Markdown 笔记已不存在",
        )
    return read_okf_note(file_record).body


def okf_concept_path_conflict_exists(db, file_record: FileModel, concept_path: str | None) -> bool:
    """检查 concept_path 在 (user, workspace) 范围内是否被其他资料占用（PUT meta 用，不自动去重）。"""
    target = (concept_path or "").strip().strip("/")
    if not target:
        return False
    q = db.query(FileModel).filter(
        FileModel.okf_concept_path == target,
        FileModel.user_id == file_record.user_id,
        FileModel.workspace_id == file_record.workspace_id,
        FileModel.id != file_record.id,
    )
    return q.first() is not None


def read_okf_raw_for_file(file_record: FileModel) -> str | None:
    if not file_record.has_md or not file_record.md_file_path:
        return None
    return read_okf_note(file_record).raw


def build_upload_okf_metadata(
    file_record: FileModel,
    *,
    okf_title: str | None = None,
    okf_type: str | None = None,
    okf_description: str | None = None,
    okf_tags: list[str] | tuple[str, ...] | str | None = None,
    okf_concept_path: str | None = None,
    timestamp: datetime | None = None,
) -> dict[str, Any]:
    _ = okf_concept_path
    metadata: dict[str, Any] = {
        "type": (okf_type or "").strip() or DEFAULT_OKF_TYPE,
        "title": (okf_title or "").strip() or _default_title(file_record),
        "resource": f"filex://files/{file_record.id}",
        "tags": _clean_tags(okf_tags),
        "timestamp": _utc_timestamp(timestamp),
        "okf_version": DEFAULT_OKF_VERSION,
        "filex": {
            "file_id": file_record.id,
            "workspace_id": file_record.workspace_id,
            "folder_id": file_record.folder_id,
            "source_mime": file_record.mime_type,
            "source_md5": file_record.md5_hash,
            "source_size": file_record.file_size,
            "original_name": file_record.original_name,
            "extract_status": file_record.extract_status,
            "extract_engine": file_record.extract_engine,
        },
    }
    description = (okf_description or "").strip()
    if description:
        metadata["description"] = description
    return metadata


def _initial_body_and_metadata(
    file_record: FileModel,
    content: bytes,
    metadata: dict[str, Any],
) -> tuple[dict[str, Any], str]:
    if not is_markdown_upload(file_record.original_name, file_record.mime_type):
        return metadata, ""

    raw_text = decode_upload_markdown(content)
    try:
        uploaded_meta, body = split_frontmatter(raw_text)
    except OkfParseError as exc:
        logger.warning("invalid_upload_okf_frontmatter file_id=%s error=%s", file_record.id, exc)
        return metadata, raw_text
    if not uploaded_meta.get("type"):
        return metadata, raw_text

    merged = dict(uploaded_meta)
    required_filex_meta = {"resource", "timestamp", "okf_version", "filex"}
    merged.update({key: value for key, value in metadata.items() if key in required_filex_meta})
    merged.setdefault("title", metadata.get("title"))
    merged.setdefault("tags", metadata.get("tags", []))
    return _clean_frontmatter(merged), body


def initialize_okf_note_for_upload(
    db,
    file_record: FileModel,
    content: bytes,
    *,
    okf_title: str | None = None,
    okf_type: str | None = None,
    okf_description: str | None = None,
    okf_tags: list[str] | tuple[str, ...] | str | None = None,
    okf_concept_path: str | None = None,
    timestamp: datetime | None = None,
) -> bool:
    """Create the native OKF sidecar for a newly uploaded source file.

    Returns True when the sidecar body is non-empty and should be indexed.
    """
    concept_path = _unique_concept_path(db, file_record, okf_concept_path)
    default_path = _default_concept_path(db, file_record)
    metadata = build_upload_okf_metadata(
        file_record,
        okf_title=okf_title,
        okf_type=okf_type,
        okf_description=okf_description,
        okf_tags=okf_tags,
        okf_concept_path=concept_path,
        timestamp=timestamp,
    )
    if okf_concept_path:
        requested = okf_concept_path.strip().strip("/").replace("\\", "/")
        if requested and requested != default_path:
            metadata.setdefault("filex", {})["concept_path_custom"] = True
    metadata, body = _initial_body_and_metadata(file_record, content, metadata)
    create_okf_note_shell(file_record, metadata, concept_path=concept_path)
    if body:
        save_okf_body_for_file(file_record, body, timestamp=timestamp)
    final_tags = list(metadata.get("tags") or [])
    if final_tags:
        replace_file_tags(db, file_record.user_id, file_record.id, final_tags)
    return bool(body.strip())


def sync_file_okf_fields_from_frontmatter(
    file_record: FileModel,
    frontmatter: dict[str, Any],
    *,
    concept_path: str | None = None,
) -> None:
    file_record.okf_concept_path = concept_path or file_record.okf_concept_path
    cleaned = _clean_frontmatter(frontmatter)
    file_record.okf_type = str(cleaned.get("type") or DEFAULT_OKF_TYPE).strip()
    file_record.okf_metadata = normalize_metadata_for_storage(cleaned)
    file_record.okf_reserved_role = None
    if file_record.page_kind not in ("entity", "concept", "synthesis"):
        file_record.page_kind = "source"
        file_record.wiki_slug = None


def save_okf_body_for_file(
    file_record: FileModel,
    body: str,
    *,
    timestamp: datetime | None = None,
) -> str:
    note = read_okf_note(file_record)
    frontmatter = dict(note.frontmatter) if not note.is_legacy else _metadata_for_file(file_record)
    frontmatter = _clean_frontmatter(frontmatter)
    okf_type = str(frontmatter.get("type") or DEFAULT_OKF_TYPE).strip() or DEFAULT_OKF_TYPE
    frontmatter["type"] = okf_type
    frontmatter.setdefault("okf_version", DEFAULT_OKF_VERSION)
    frontmatter.setdefault("title", _default_title(file_record))
    frontmatter.setdefault("resource", f"filex://files/{file_record.id}")
    frontmatter.setdefault("tags", [])
    frontmatter["timestamp"] = _utc_timestamp(timestamp)
    existing_filex = dict(note.frontmatter.get("filex") or {}) if not note.is_legacy else {}
    frontmatter["filex"] = _filex_block(file_record, existing_filex)
    raw = merge_frontmatter(frontmatter, okf_type, body)

    _write_raw(file_record, raw)
    file_record.md_content_hash = compute_md_content_hash(body)
    sync_file_okf_fields_from_frontmatter(file_record, frontmatter)
    return raw


def create_okf_note_shell(
    file_record: FileModel,
    frontmatter: dict[str, Any] | None = None,
    *,
    concept_path: str | None = None,
) -> str:
    metadata = dict(frontmatter or _metadata_for_file(file_record))
    okf_type = str(metadata.get("type") or DEFAULT_OKF_TYPE).strip() or DEFAULT_OKF_TYPE
    metadata["type"] = okf_type
    metadata.setdefault("okf_version", DEFAULT_OKF_VERSION)
    metadata = _clean_frontmatter(metadata)
    raw = merge_frontmatter(metadata, okf_type, "")

    _write_raw(file_record, raw, concept_path=concept_path)
    file_record.md_content_hash = compute_md_content_hash("")
    sync_file_okf_fields_from_frontmatter(file_record, metadata, concept_path=concept_path)
    return raw


def sync_okf_frontmatter_tags_for_file(file_record: FileModel, tags: list[str]) -> str | None:
    """将 file_tags 集合同步到 native OKF frontmatter tags；legacy 笔记 no-op。"""
    note = read_okf_note(file_record)
    if note.is_legacy or not note.frontmatter:
        return None
    frontmatter = dict(note.frontmatter)
    frontmatter["tags"] = _clean_tags(tags)
    return update_okf_frontmatter_for_file(file_record, frontmatter)


def update_okf_frontmatter_for_file(
    file_record: FileModel,
    frontmatter: dict[str, Any],
    *,
    concept_path: str | None = None,
    timestamp: datetime | None = None,
    db=None,
) -> str:
    note = read_okf_note(file_record)
    body = note.body
    metadata = _clean_frontmatter(frontmatter or {})
    okf_type = str(metadata.get("type") or DEFAULT_OKF_TYPE).strip()
    if not okf_type:
        okf_type = DEFAULT_OKF_TYPE
    metadata["type"] = okf_type
    metadata.setdefault("okf_version", DEFAULT_OKF_VERSION)
    metadata["timestamp"] = _utc_timestamp(timestamp)

    existing_filex = dict(note.frontmatter.get("filex") or {}) if not note.is_legacy else {}
    if db is not None and concept_path is not None:
        default_path = _default_concept_path(db, file_record)
        normalized = concept_path.strip().strip("/").replace("\\", "/")
        if normalized != default_path:
            existing_filex["concept_path_custom"] = True
        else:
            existing_filex.pop("concept_path_custom", None)
    metadata["filex"] = _filex_block(file_record, existing_filex)

    previous_concept_path = (file_record.okf_concept_path or "").strip().strip("/").replace("\\", "/")
    old_path = _resolved_md_path(file_record) if file_record.has_md and file_record.md_file_path else None
    write_concept_path = concept_path if concept_path is not None else file_record.okf_concept_path

    raw = merge_frontmatter(metadata, okf_type, body)
    _write_raw(file_record, raw, concept_path=write_concept_path)

    new_path = file_record.md_file_path
    paths_to_remove: list[str] = []
    if old_path:
        paths_to_remove.append(old_path)
    if (
        previous_concept_path
        and file_record.workspace_id is not None
        and write_concept_path is not None
    ):
        normalized_write = write_concept_path.strip().strip("/").replace("\\", "/")
        if normalized_write != previous_concept_path:
            prior_sidecar = okf_sidecar_path(file_record.workspace_id, previous_concept_path)
            paths_to_remove.append(prior_sidecar)
    seen_remove: set[str] = set()
    for path in paths_to_remove:
        if not path or not new_path:
            continue
        norm_old = os.path.normpath(path)
        norm_new = os.path.normpath(new_path)
        if norm_old == norm_new or norm_old in seen_remove:
            continue
        seen_remove.add(norm_old)
        _remove_sidecar_file(path)
        if not is_legacy_flat_md_note_path(path):
            _best_effort_rmdir_empty_okf_parents(path, file_record.workspace_id)

    sync_file_okf_fields_from_frontmatter(file_record, metadata, concept_path=concept_path)
    return raw


def is_okf_concept_path_custom(
    db,
    file_record: FileModel,
    *,
    snapshot_default_path: str | None = None,
) -> bool:
    """FR-112-007：frontmatter flag 优先；legacy 无 flag 时与 default path 比对。

    folder 变更场景须传入变更前 snapshot 的 default path，避免 folder_id 已更新后误判为 custom。
    """
    if not file_record.okf_concept_path:
        return False
    note = read_okf_note(file_record)
    if not note.is_legacy and note.frontmatter:
        filex = dict(note.frontmatter.get("filex") or {})
        if filex.get("concept_path_custom") is True:
            return True
        if filex.get("concept_path_custom") is False:
            return False
    current = file_record.okf_concept_path.strip().strip("/").replace("\\", "/")
    reference = (
        snapshot_default_path.strip().strip("/").replace("\\", "/")
        if snapshot_default_path
        else _default_concept_path(db, file_record)
    )
    return current != reference


def _default_concept_path_for_folder(db, file_record: FileModel, folder_id: int | None) -> str:
    saved = file_record.folder_id
    file_record.folder_id = folder_id
    try:
        return _default_concept_path(db, file_record)
    finally:
        file_record.folder_id = saved


def _folder_descendant_ids(db, root_folder_id: int, workspace_id: int) -> set[int]:
    ids = {root_folder_id}
    frontier = [root_folder_id]
    for _ in range(50):
        if not frontier:
            break
        children = (
            db.query(Folder.id)
            .filter(Folder.workspace_id == workspace_id, Folder.parent_id.in_(frontier))
            .all()
        )
        new_frontier: list[int] = []
        for (cid,) in children:
            if cid not in ids:
                ids.add(cid)
                new_frontier.append(cid)
        frontier = new_frontier
    return ids


def relocate_okf_sidecar_for_concept_path(
    db,
    file_record: FileModel,
    new_concept_path: str,
) -> str | None:
    """将 native OKF sidecar 搬迁至 new_concept_path；无变更或 legacy 时跳过。"""
    if not file_record.has_md or not file_record.md_file_path:
        return None
    note = read_okf_note(file_record)
    if note.is_legacy:
        return None
    normalized_new = new_concept_path.strip().strip("/").replace("\\", "/")
    old_normalized = (file_record.okf_concept_path or "").strip().strip("/").replace("\\", "/")
    if not normalized_new or normalized_new == old_normalized:
        return None
    unique_path = _unique_concept_path(db, file_record, normalized_new)
    frontmatter = effective_okf_frontmatter(file_record)
    return update_okf_frontmatter_for_file(
        file_record,
        frontmatter,
        concept_path=unique_path,
        db=db,
    )


def snapshot_okf_defaults_for_folder_tree(
    db,
    folder_id: int,
    workspace_id: int,
) -> dict[int, tuple[str, bool]]:
    """folder 树变更前 snapshot 各文件 default path 与 custom 判定（FR-112-007）。"""
    folder_ids = _folder_descendant_ids(db, folder_id, workspace_id)
    rows = (
        db.query(FileModel)
        .filter(
            FileModel.workspace_id == workspace_id,
            FileModel.folder_id.in_(folder_ids),
            FileModel.has_md.is_(True),
            FileModel.okf_concept_path.isnot(None),
        )
        .all()
    )
    out: dict[int, tuple[str, bool]] = {}
    for file_record in rows:
        snap_default = _default_concept_path(db, file_record)
        custom = is_okf_concept_path_custom(
            db, file_record, snapshot_default_path=snap_default
        )
        out[file_record.id] = (snap_default, custom)
    return out


def apply_okf_relocates_after_folder_tree_change(
    db,
    workspace_id: int,
    snapshots: dict[int, tuple[str, bool]],
) -> None:
    """folder 重命名/移动后，按变更前 snapshot 对非 custom 资料搬迁 sidecar。"""
    for file_id, (_snap_default, was_custom) in snapshots.items():
        file_record = db.query(FileModel).filter(FileModel.id == file_id).first()
        if not file_record or not file_record.has_md or not file_record.okf_concept_path:
            continue
        note = read_okf_note(file_record)
        if note.is_legacy:
            continue
        if was_custom:
            refresh_okf_filex_block(file_record)
            continue
        new_default = _default_concept_path(db, file_record)
        relocate_okf_sidecar_for_concept_path(db, file_record, new_default)
        refresh_okf_filex_block(file_record)


def maybe_relocate_okf_sidecar_on_folder_change(
    db,
    file_record: FileModel,
    *,
    new_folder_id: int | None,
    previous_folder_id: int | None,
) -> None:
    """FR-112-004(b)(c)：单文件 folder_id 变更时重算 default path 并搬迁（custom 冻结）。

    ``file_record.folder_id`` 须已更新为 ``new_folder_id``；``previous_folder_id`` 为变更前
    目录 id（未分类传 ``None``），用于 snapshot default 与 FR-112-007 custom 判定。
    """
    if not file_record.has_md or not file_record.okf_concept_path:
        return
    note = read_okf_note(file_record)
    if note.is_legacy:
        return
    snap_default = _default_concept_path_for_folder(db, file_record, previous_folder_id)
    if is_okf_concept_path_custom(db, file_record, snapshot_default_path=snap_default):
        refresh_okf_filex_block(file_record)
        return
    new_default = _default_concept_path_for_folder(db, file_record, new_folder_id)
    relocate_okf_sidecar_for_concept_path(db, file_record, new_default)
    refresh_okf_filex_block(file_record)


def remove_concept_sidecar_from_disk(file_record: FileModel) -> None:
    """删除 Concept sidecar；okf 树路径 best-effort 清理空父目录。"""
    if not file_record.has_md or not file_record.md_file_path:
        return
    path = resolve_upload_path(file_record.md_file_path) or file_record.md_file_path
    if not path or not os.path.isfile(path):
        return
    _remove_sidecar_file(path)
    if not is_legacy_flat_md_note_path(path):
        _best_effort_rmdir_empty_okf_parents(path, file_record.workspace_id)


def refresh_okf_filex_block(file_record: FileModel) -> str | None:
    """刷新 frontmatter 内 filex 块以镜像当前 DB 状态（保留 body，不动 hash）。

    用于不替换 body 的状态变更（如空提取置为 skipped），使 frontmatter 的
    filex.extract_status / extract_engine 与 DB 列保持一致。legacy 笔记无
    frontmatter，直接跳过并返回 None。
    """
    note = read_okf_note(file_record)
    if note.is_legacy or not note.frontmatter:
        return None
    frontmatter = dict(note.frontmatter)
    existing_filex = dict(frontmatter.get("filex") or {})
    frontmatter["filex"] = _filex_block(file_record, existing_filex)
    frontmatter["timestamp"] = _utc_timestamp()
    okf_type = str(frontmatter.get("type") or DEFAULT_OKF_TYPE).strip() or DEFAULT_OKF_TYPE
    frontmatter["type"] = okf_type
    raw = merge_frontmatter(frontmatter, okf_type, note.body)
    _write_raw(file_record, raw)
    sync_file_okf_fields_from_frontmatter(file_record, frontmatter)
    return raw


def touch_body_content_hash(file_record: FileModel, body: str | None = None) -> str | None:
    text = body if body is not None else read_okf_body_for_file(file_record)
    if text is None:
        file_record.md_content_hash = None
        return None
    digest = compute_md_content_hash(text)
    file_record.md_content_hash = digest
    return digest
