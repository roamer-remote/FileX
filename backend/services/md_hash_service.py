# Copyright (c) 2026 徐泽宇
"""MD note content hash for incremental extract skip (048)."""

from __future__ import annotations

import hashlib
import os

from sqlalchemy.orm import Session

from models.file import File as FileModel


def compute_md_content_hash(content: str) -> str:
    normalized = (content or "").strip().encode("utf-8")
    return hashlib.md5(normalized).hexdigest()


def read_md_note_content_for_hash(f: FileModel) -> str | None:
    """返回 body-only 正文用于 hash/extract skip（frontmatter 不参与 hash）。

    无笔记、或 sidecar 在磁盘上已不存在时返回 None，避免把磁盘缺失误判为空正文
    （空正文会得到固定 hash 并触发错误的 extract skip）。
    """
    from services.okf_note_service import read_okf_body_for_file
    from services.md_paths import resolve_upload_path

    if not f.has_md or not f.md_file_path:
        return None
    path = resolve_upload_path(f.md_file_path) or f.md_file_path
    if not os.path.isfile(path):
        return None
    return read_okf_body_for_file(f)


def touch_md_content_hash(db: Session, f: FileModel, *, content: str | None = None) -> str | None:
    """Single write entry for files.md_content_hash. Returns computed hash or None."""
    _ = db
    text = content if content is not None else read_md_note_content_for_hash(f)
    if text is None:
        f.md_content_hash = None
        return None
    digest = compute_md_content_hash(text)
    f.md_content_hash = digest
    return digest
