# Copyright (c) 2026 徐泽宇
"""087/088 个人空间整包 ZIP 备份（归档，非 import）。"""

from __future__ import annotations

import json
import os
import tempfile
import zipfile
from dataclasses import dataclass
from datetime import datetime
from typing import Protocol

from sqlalchemy.orm import Session

from constants.workspace_backup_errors import WORKSPACE_BACKUP_TOO_LARGE
from models.file import File as FileModel
from models.folder import Folder
from models.user import User
from models.workspace import Workspace
from services.md_note_service import read_md_note_text
from services.md_paths import resolve_upload_path
from services.system_setting_service import get_workspace_backup_max_bytes
from services.wiki_page_filters import source_files_only
from services.wiki_page_service import wiki_pages_base_query
from services.workspace_backup_paths import ZipPathAllocator, sanitize_zip_path_segment
from utils.timezone import BEIJING_TZ, beijing_now


class WorkspaceBackupTooLargeError(Exception):
    """备份体积超过系统配置上限。"""

    def __init__(self, max_bytes: int, total_bytes: int, *, file_count: int) -> None:
        self.max_bytes = max_bytes
        self.total_bytes = total_bytes
        self.file_count = file_count
        self.detail = WORKSPACE_BACKUP_TOO_LARGE
        super().__init__(WORKSPACE_BACKUP_TOO_LARGE)


@dataclass(frozen=True)
class WorkspaceBackupResult:
    zip_path: str
    filename: str
    file_count: int
    total_bytes: int


@dataclass(frozen=True)
class BackupExportPlan:
    file_count: int
    content_bytes: int
    total_bytes: int
    slug: str
    prefix: str


class _BackupSink(Protocol):
    total_bytes: int

    def writestr(self, rel_path: str, data: bytes) -> None: ...

    def write_file(self, rel_path: str, disk_path: str) -> None: ...


@dataclass
class _ManifestSizeWriter:
    total_bytes: int


@dataclass
class _ContentAccumulator:
    prefix: str
    total_bytes: int = 0

    def writestr(self, rel_path: str, data: bytes) -> None:
        _assert_zip_entry_safe(self.prefix, rel_path)
        self.total_bytes += len(data)

    def write_file(self, rel_path: str, disk_path: str) -> None:
        _assert_zip_entry_safe(self.prefix, rel_path)
        self.total_bytes += os.path.getsize(disk_path)


def _backup_username(user: User) -> str:
    name = (user.username or "").strip()
    if name:
        return sanitize_zip_path_segment(name)
    return f"user-{user.id}"


def _backup_filename(username: str, exported_at: datetime) -> str:
    date_part = exported_at.astimezone(BEIJING_TZ).strftime("%Y%m%d")
    return f"{username}-backup-{date_part}.zip"


def _abort_and_unlink(zip_path: str) -> None:
    try:
        os.unlink(zip_path)
    except OSError:
        pass


def _assert_zip_entry_safe(prefix: str, rel_path: str) -> None:
    full = f"{prefix}{rel_path}".replace("\\", "/")
    if not full.startswith(prefix):
        raise ValueError(f"zip slip: entry outside prefix: {rel_path}")
    for part in rel_path.split("/"):
        if part in ("", ".", ".."):
            raise ValueError(f"zip slip: illegal segment in {rel_path}")


def _sidecar_basename(sanitized_original: str) -> str:
    return f"{sanitized_original}.md"


def _assets_dir_basename(sanitized_original: str) -> str:
    return f"{sanitized_original}.assets"


def _sanitize_asset_relpath(rel_name: str) -> str:
    """extract 资产相对路径逐段消毒（FR-087-007）。"""
    rel_norm = rel_name.replace("\\", "/").strip("/")
    if not rel_norm:
        return ""
    parts: list[str] = []
    for part in rel_norm.split("/"):
        if not part or part in (".", ".."):
            continue
        seg = sanitize_zip_path_segment(part)
        if seg and seg != "unknown":
            parts.append(seg)
    return "/".join(parts)


def _folder_relative_dirs(db: Session, workspace_id: int) -> dict[int | None, str]:
    rows = (
        db.query(Folder.id, Folder.name, Folder.parent_id)
        .filter(Folder.workspace_id == workspace_id)
        .all()
    )
    by_id: dict[int, tuple[str, int | None]] = {
        int(r.id): (r.name or f"folder-{r.id}", int(r.parent_id) if r.parent_id is not None else None)
        for r in rows
    }

    def path_for(folder_id: int) -> str:
        parts: list[str] = []
        seen: set[int] = set()
        cur: int | None = folder_id
        while cur is not None and cur in by_id:
            if cur in seen:
                break
            seen.add(cur)
            name, parent = by_id[cur]
            parts.insert(0, sanitize_zip_path_segment(name))
            cur = parent
        return "/".join(p for p in parts if p)

    out: dict[int | None, str] = {None: ""}
    for fid in by_id:
        out[fid] = path_for(fid)
    return out


def _list_asset_files(assets_dir: str) -> list[tuple[str, str]]:
    if not assets_dir or not os.path.isdir(assets_dir):
        return []
    out: list[tuple[str, str]] = []
    for root, _dirs, files in os.walk(assets_dir):
        for name in files:
            abs_path = os.path.join(root, name)
            rel = os.path.relpath(abs_path, assets_dir).replace("\\", "/")
            out.append((rel, abs_path))
    return sorted(out, key=lambda x: x[0])


def _resolved_assets_dir(f: FileModel) -> str | None:
    """只读探测 extract 资产目录；禁止 makedirs（备份不得改磁盘）。"""
    stream = resolve_upload_path(f.file_path) or f.file_path
    if not stream:
        return None
    candidates: list[str] = [os.path.join(os.path.dirname(stream), ".extract_assets", str(f.id))]
    if f.file_path and f.file_path != stream:
        candidates.append(
            os.path.join(os.path.dirname(f.file_path), ".extract_assets", str(f.id))
        )
    seen: set[str] = set()
    for path in candidates:
        norm = os.path.normpath(path)
        if norm in seen:
            continue
        seen.add(norm)
        if os.path.isdir(norm) and _list_asset_files(norm):
            return norm
    return None


def _manifest_bytes(manifest: dict, writer: _ManifestSizeWriter | _ZipWriter) -> bytes:
    """manifest.total_bytes 须含 manifest 自身（FR-087-008）。"""
    payload = dict(manifest)
    manifest_bytes = b""
    for _ in range(4):
        payload["total_bytes"] = writer.total_bytes + len(manifest_bytes)
        manifest_bytes = json.dumps(payload, ensure_ascii=False, indent=2).encode("utf-8")
        if payload["total_bytes"] == writer.total_bytes + len(manifest_bytes):
            break
    return manifest_bytes


class _ZipWriter:
    def __init__(
        self,
        zf: zipfile.ZipFile,
        prefix: str,
        max_bytes: int,
        *,
        file_count: int,
    ) -> None:
        self._zf = zf
        self._prefix = prefix
        self._max_bytes = max_bytes
        self._file_count = file_count
        self.total_bytes = 0

    def _bump(self, size: int) -> None:
        self.total_bytes += size
        if self.total_bytes > self._max_bytes:
            raise WorkspaceBackupTooLargeError(
                self._max_bytes,
                self.total_bytes,
                file_count=self._file_count,
            )

    def writestr(self, rel_path: str, data: bytes) -> None:
        _assert_zip_entry_safe(self._prefix, rel_path)
        self._bump(len(data))
        self._zf.writestr(f"{self._prefix}{rel_path}", data)

    def write_file(self, rel_path: str, disk_path: str) -> None:
        _assert_zip_entry_safe(self._prefix, rel_path)
        size = os.path.getsize(disk_path)
        self._bump(size)
        self._zf.write(disk_path, f"{self._prefix}{rel_path}")


def _wiki_note_basename(original_name: str) -> str:
    sanitized = sanitize_zip_path_segment(original_name or "unknown")
    lower = sanitized.lower()
    if lower.endswith(".md") or lower.endswith(".markdown"):
        return sanitized
    return f"{sanitized}.md"


def _query_wiki_pages(db: Session, workspace_id: int) -> list[FileModel]:
    return wiki_pages_base_query(db, workspace_id).all()


def _query_source_files(db: Session, workspace_id: int) -> list[FileModel]:
    return (
        source_files_only(db.query(FileModel))
        .filter(
            FileModel.workspace_id == workspace_id,
            FileModel.publish_status == "published",
        )
        .order_by(FileModel.id)
        .all()
    )


def _build_manifest_dict(
    workspace: Workspace,
    user: User,
    exported_at: datetime,
    entries: list[dict],
    warnings: list[str],
) -> dict:
    return {
        "format": "filex-workspace-backup",
        "format_version": "1",
        "import_supported": False,
        "workspace_id": workspace.id,
        "workspace_slug": workspace.slug,
        "workspace_name": workspace.name,
        "exported_at": exported_at.isoformat(),
        "exported_by_user_id": user.id,
        "exported_by_username": user.username or "",
        "file_count": len(entries),
        "entries": entries,
        "warnings": warnings,
    }


def _accumulate_source_file(
    sink: _BackupSink,
    f: FileModel,
    *,
    directory: str,
    allocator: ZipPathAllocator,
    warnings: list[str],
) -> dict:
    sanitized = sanitize_zip_path_segment(f.original_name or f.filename or "unknown")
    zip_paths: dict[str, str] = {}
    original_missing = False

    stream_path = resolve_upload_path(f.file_path) or f.file_path
    if stream_path and os.path.isfile(stream_path):
        orig_rel = allocator.allocate(directory, sanitized)
        sink.write_file(orig_rel, stream_path)
        zip_paths["original"] = orig_rel
    else:
        original_missing = True
        warnings.append(f"file_id={f.id}: original missing on disk")

    note_text = read_md_note_text(f)
    note_empty = not (note_text and note_text.strip())
    if not note_empty and note_text is not None:
        sidecar_rel = allocator.allocate(directory, _sidecar_basename(sanitized))
        sink.writestr(sidecar_rel, note_text.encode("utf-8"))
        zip_paths["note"] = sidecar_rel

    assets_dir = _resolved_assets_dir(f)
    if assets_dir:
        assets_bn = _assets_dir_basename(sanitized)
        assets_rel = allocator.allocate(directory, assets_bn)
        for rel_name, abs_path in _list_asset_files(assets_dir):
            sanitized_rel = _sanitize_asset_relpath(rel_name)
            if not sanitized_rel:
                continue
            subdir = os.path.dirname(sanitized_rel)
            parent_key = f"{assets_rel}/{subdir}" if subdir else assets_rel
            asset_bn = sanitize_zip_path_segment(os.path.basename(sanitized_rel))
            asset_rel = allocator.allocate(parent_key, asset_bn)
            sink.write_file(asset_rel, abs_path)
        zip_paths["assets"] = f"{assets_rel}/"

    entry: dict = {
        "file_id": f.id,
        "page_kind": "source",
        "original_name": f.original_name,
        "zip_paths": zip_paths,
        "note_empty": note_empty,
        "original_missing": original_missing,
    }
    if f.okf_reserved_role:
        entry["okf_reserved_role"] = f.okf_reserved_role
    return entry


def _accumulate_wiki_page(
    sink: _BackupSink,
    f: FileModel,
    *,
    directory: str,
    allocator: ZipPathAllocator,
) -> dict:
    """主题页仅导出笔记 .md；禁止将占位 file_path 当原件写入 zip（FR-087-005）。"""
    note_bn = _wiki_note_basename(f.original_name or f.filename or "unknown")
    note_rel = allocator.allocate(directory, note_bn)
    note_text = read_md_note_text(f)
    note_empty = not (note_text and note_text.strip())
    body = b"" if note_empty else (note_text or "").encode("utf-8")
    sink.writestr(note_rel, body)
    return {
        "file_id": f.id,
        "page_kind": f.page_kind,
        "original_name": f.original_name,
        "zip_paths": {"note": note_rel},
        "note_empty": note_empty,
    }


def _run_backup_accumulation(
    db: Session,
    workspace: Workspace,
    sink: _BackupSink,
) -> tuple[list[dict], list[str]]:
    entries: list[dict] = []
    warnings: list[str] = []
    folder_dirs = _folder_relative_dirs(db, workspace.id)
    allocator = ZipPathAllocator()
    for f in _query_source_files(db, workspace.id):
        directory = folder_dirs.get(f.folder_id, "")
        entries.append(
            _accumulate_source_file(
                sink,
                f,
                directory=directory,
                allocator=allocator,
                warnings=warnings,
            )
        )
    for f in _query_wiki_pages(db, workspace.id):
        directory = folder_dirs.get(f.folder_id, "")
        entries.append(
            _accumulate_wiki_page(
                sink,
                f,
                directory=directory,
                allocator=allocator,
            )
        )
    return entries, warnings


def _plan_backup_export(
    db: Session,
    user: User,
    workspace: Workspace,
    exported_at: datetime,
) -> BackupExportPlan:
    slug = sanitize_zip_path_segment(workspace.slug or f"ws-{workspace.id}")
    prefix = f"{slug}/"
    accumulator = _ContentAccumulator(prefix=prefix)
    entries, warnings = _run_backup_accumulation(db, workspace, accumulator)
    manifest = _build_manifest_dict(workspace, user, exported_at, entries, warnings)
    stub = _ManifestSizeWriter(total_bytes=accumulator.total_bytes)
    manifest_bytes = _manifest_bytes(manifest, stub)
    total_bytes = accumulator.total_bytes + len(manifest_bytes)
    return BackupExportPlan(
        file_count=len(entries),
        content_bytes=accumulator.total_bytes,
        total_bytes=total_bytes,
        slug=slug,
        prefix=prefix,
    )


def _check_backup_size(plan: BackupExportPlan, max_bytes: int) -> None:
    if plan.total_bytes > max_bytes:
        raise WorkspaceBackupTooLargeError(
            max_bytes,
            plan.total_bytes,
            file_count=plan.file_count,
        )


def estimate_workspace_backup(
    db: Session,
    user: User,
    workspace: Workspace,
) -> BackupExportPlan:
    """088 压缩前只读预检；不创建临时 zip。"""
    exported_at = beijing_now()
    plan = _plan_backup_export(db, user, workspace, exported_at)
    _check_backup_size(plan, get_workspace_backup_max_bytes(db))
    return plan


def build_workspace_backup_zip(
    db: Session,
    user: User,
    workspace: Workspace,
) -> WorkspaceBackupResult:
    exported_at = beijing_now()
    max_bytes = get_workspace_backup_max_bytes(db)
    plan = _plan_backup_export(db, user, workspace, exported_at)
    _check_backup_size(plan, max_bytes)

    tmp = tempfile.NamedTemporaryFile(delete=False, suffix=".zip")
    tmp_path = tmp.name
    tmp.close()

    entries: list[dict] = []
    warnings: list[str] = []
    total_bytes = 0

    try:
        with zipfile.ZipFile(tmp_path, "w", compression=zipfile.ZIP_DEFLATED) as zf:
            writer = _ZipWriter(
                zf,
                plan.prefix,
                max_bytes,
                file_count=plan.file_count,
            )
            entries, warnings = _run_backup_accumulation(db, workspace, writer)
            manifest = _build_manifest_dict(workspace, user, exported_at, entries, warnings)
            manifest_bytes = _manifest_bytes(manifest, writer)
            writer.writestr("manifest.json", manifest_bytes)
            total_bytes = writer.total_bytes
    except WorkspaceBackupTooLargeError:
        _abort_and_unlink(tmp_path)
        raise
    except Exception:
        _abort_and_unlink(tmp_path)
        raise

    return WorkspaceBackupResult(
        zip_path=tmp_path,
        filename=_backup_filename(_backup_username(user), exported_at),
        file_count=len(entries),
        total_bytes=total_bytes,
    )
